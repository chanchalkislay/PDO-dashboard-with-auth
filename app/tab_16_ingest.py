"""
tab_16_ingest.py — Data Ingestion Wizard (Admin only)
=====================================================
Upload-first wizard: the file is uploaded and auto-analysed first,
then the detected OMC / FY / Month are shown for confirmation.
No manual form-filling required in the normal case.

Steps
-----
0  Upload     — drop file; auto-detect OMC / FY / Month
1  Confirm    — show detected values; user can override before parsing
2  Dry-run    — parse + validate; show summary
3  Fuzzy      — confirm fuzzy district matches (if any)
4  Unknown    — resolve unknown SAP codes (if any)
5  Commit     — final review + commit button
6  Done       — result + rollback panel
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time

import pandas as pd
import streamlit as st

# ── ingest/ is one level above app/ ──────────────────────────────────────────
_APP_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.dirname(_APP_DIR)
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from ingest.parsers import detect_and_parse, detect_format, COVERAGE_DISTRICTS
from ingest.pipeline import Pipeline, _month_label, pvt_district_check, record_sap_remap

# ── Constants ─────────────────────────────────────────────────────────────────
_OMC_LIST   = ["IOCL", "BPCL", "HPCL", "NEL", "RBML", "SIMPL"]
_PVT_OMCS   = {"NEL", "RBML", "SIMPL"}
_FY_OPTIONS = [f"{y}-{str(y+1)[-2:]}" for y in range(2019, 2028)]
_MONTH_OPTS = {
    1: "April",   2: "May",      3: "June",     4: "July",
    5: "August",  6: "September",7: "October",  8: "November",
    9: "December",10: "January", 11: "February",12: "March",
}
_BACKUP_DIR = os.path.join(_PROJ_ROOT, "backups")

# Month-name → month_index (for filename parsing)
_MONTH_NAME_MAP = {
    "apr": 1, "april": 1,
    "may": 2,
    "jun": 3, "june": 3,
    "jul": 4, "july": 4,
    "aug": 5, "august": 5,
    "sep": 6, "sept": 6, "september": 6,
    "oct": 7, "october": 7,
    "nov": 8, "november": 8,
    "dec": 9, "december": 9,
    "jan": 10, "january": 10,
    "feb": 11, "february": 11,
    "mar": 12, "march": 12,
}

# Format label → OMC
_FMT_OMC_MAP = {
    "iocl_sap_dump":    "IOCL",
    "bpcl_q002_nagar":  "BPCL",
    "bpcl_q145_ps":     "BPCL",
    "hpcl_nagar":       "HPCL",
    "hpcl_ps":          "HPCL",
    "pvt_sales_format": None,   # OMC comes from inside the file
}


def _ss(key, default=None):
    return st.session_state.get(key, default)


def _reset():
    for k in list(st.session_state.keys()):
        if k.startswith("ing_"):
            del st.session_state[k]


# ── DB path selector (sidebar) ────────────────────────────────────────────────
def _get_db_path() -> str:
    from core import DB_PATH as PROD_PATH  # noqa
    test_path = os.path.join(_PROJ_ROOT, "test", "pune_do_test.db")
    options   = {"Production DB": PROD_PATH}
    if os.path.exists(test_path):
        options["Test DB (safe)"] = test_path

    choice = st.sidebar.radio(
        "🗄️ Target database", list(options.keys()),
        index=0, key="ing_db_choice",
        help="Use Test DB while validating; switch to Production DB to go live.",
    )
    path  = options[choice]
    label = "🟢 Production" if choice == "Production DB" else "🟡 Test DB"
    st.sidebar.caption(f"{label}: `{os.path.basename(path)}`")
    return path


# ── Auto-detection helpers ────────────────────────────────────────────────────

def _detect_from_filename(filename: str) -> tuple[int | None, str | None]:
    """
    Try to extract (month_index, fy_code) from a filename.
    Handles: 'July 2025', 'Jul-25', 'JUL25', 'MAY25', 'Nov25', 'March 2026'.
    Returns (None, None) if nothing conclusive found.
    """
    stem = os.path.splitext(filename)[0].lower()
    stem = re.sub(r"[_\-\.\s']+", " ", stem)

    month_index = None
    yr          = None

    # Pattern 1: MonYY or MonYYYY run together — e.g. "jul25", "may2025", "nov25"
    compound = re.search(
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
        r"(20\d{2}|\d{2})\b",
        stem
    )
    if compound:
        month_index = _MONTH_NAME_MAP.get(compound.group(1))
        raw_yr = compound.group(2)
        yr = int(raw_yr) if len(raw_yr) == 4 else 2000 + int(raw_yr)

    # Pattern 2: month name as whole word (with optional year separately)
    if month_index is None:
        for name in sorted(_MONTH_NAME_MAP, key=len, reverse=True):  # longest first
            if re.search(r"\b" + re.escape(name) + r"\b", stem):
                month_index = _MONTH_NAME_MAP[name]
                break

    # Pattern 3: year (4-digit preferred, then 2-digit)
    if yr is None:
        m4 = re.search(r"\b(20\d{2})\b", stem)
        if m4:
            yr = int(m4.group(1))
        else:
            m2 = re.search(r"\b(\d{2})\b", stem)
            if m2:
                yr = 2000 + int(m2.group(1))

    # Derive FY from calendar month + year
    fy_code = None
    if yr and month_index:
        if month_index <= 9:   # Apr–Dec: yr is the FY start year
            fy_code = f"{yr}-{str(yr + 1)[-2:]}"
        else:                  # Jan–Mar: yr is the FY end year
            fy_code = f"{yr - 1}-{str(yr)[-2:]}"

    return month_index, fy_code


def _auto_detect(tmp_path: str, filename: str) -> dict:
    """
    Run detect_format() on the file and derive as much as possible.
    Returns dict with keys: fmt, omc, month_index, fy_code, confidence.
    confidence: 'high' (all three known), 'medium' (some guessed), 'low' (mostly unknown)
    """
    try:
        fmt = detect_format(tmp_path, omc_hint=None)
    except Exception:
        fmt = "unknown"

    omc = _FMT_OMC_MAP.get(fmt)      # None for PVT or unknown
    mi, fy = _detect_from_filename(filename)

    confident_fields = sum([omc is not None, mi is not None, fy is not None])
    confidence = "high" if confident_fields == 3 else (
                 "medium" if confident_fields >= 1 else "low")

    return {
        "fmt":         fmt,
        "omc":         omc,
        "month_index": mi,
        "fy_code":     fy,
        "confidence":  confidence,
    }


# ── Step helpers ──────────────────────────────────────────────────────────────

def _suggest_next_period(db_path: str, omc: str | None) -> tuple[str | None, int | None]:
    """
    Query ingestion_log for the latest (fy_code, month_index) for the given OMC.
    Returns the NEXT expected period — e.g. last=Apr2026 → May2026.
    Returns (None, None) if nothing ingested yet or on any error.
    """
    if not omc:
        return None, None
    try:
        import sqlite3 as _sq
        with open(db_path, "rb") as f:
            data = f.read()
        t = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        t.close()
        with open(t.name, "wb") as f:
            f.write(data)
        con = _sq.connect(t.name)
        row = con.execute(
            "SELECT fy_code, month_index FROM ingestion_log "
            "WHERE omc=? ORDER BY fy_code DESC, month_index DESC LIMIT 1",
            (omc,)
        ).fetchone()
        con.close()
        os.unlink(t.name)
        if not row:
            return None, None
        last_fy, last_mi = row[0], int(row[1])
        if last_mi < 12:
            return last_fy, last_mi + 1
        # March (mi=12) → next is April (mi=1) of next FY
        start_yr = int(last_fy.split("-")[0])
        next_fy  = f"{start_yr + 1}-{str(start_yr + 2)[-2:]}"
        return next_fy, 1
    except Exception:
        return None, None


def _step_upload():
    """Step 0 — Upload file and auto-detect its content."""
    st.subheader("Step 1 — Upload file")
    st.caption(
        "Upload any OMC exchange file. The app reads the file to detect the OMC, "
        "month, and FY automatically — you just confirm before it runs."
    )

    uploaded = st.file_uploader(
        "Choose file (.xlsx or .xls)",
        type=["xlsx", "xls"],
        key="ing_upload",
        label_visibility="collapsed",
    )

    if uploaded:
        suffix  = os.path.splitext(uploaded.name)[1]
        tmp     = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.write(uploaded.read())
        tmp.close()

        with st.spinner("Reading file…"):
            detected = _auto_detect(tmp.name, uploaded.name)

        st.session_state.ing_tmp_path  = tmp.name
        st.session_state.ing_filename  = uploaded.name
        st.session_state.ing_detected  = detected

        # Show what was detected
        fmt = detected["fmt"]
        omc = detected["omc"]
        mi  = detected["month_index"]
        fy  = detected["fy_code"]

        st.success(f"✅ File read · Format detected: **{fmt}**")

        c1, c2, c3 = st.columns(3)
        c1.metric("OMC detected",   omc or "Auto (PVT)" if fmt == "pvt_sales_format" else "❓ Unknown")
        c2.metric("Month detected", _MONTH_OPTS.get(mi, "❓ Unknown") if mi else "❓ Unknown")
        c3.metric("FY detected",    fy or "❓ Unknown")

        if detected["confidence"] == "high":
            st.info("All three fields detected — click **Confirm & proceed** to continue.")
        elif fmt == "pvt_sales_format":
            st.info("PVT file — OMC / FY / Month will be read from inside the file during parsing.")
        else:
            st.warning(
                "Some fields could not be detected from the filename. "
                "You can set them manually on the next screen."
            )

        if st.button("Confirm & proceed →", type="primary"):
            st.session_state.ing_step = 1
            st.rerun()


def _step_confirm_meta(db_path: str):
    """Step 1 — Show detected values; allow override."""
    detected  = _ss("ing_detected", {})
    filename  = _ss("ing_filename", "")
    is_pvt    = detected.get("fmt") == "pvt_sales_format"

    st.subheader(f"Step 2 — Confirm details  ·  {filename}")

    if is_pvt:
        st.info(
            "PVT file detected. OMC, FY, and Month are embedded in the file "
            "and will be set automatically during parsing — no manual input needed."
        )
        if st.button("Next → Parse & validate", type="primary"):
            # For PVT let pipeline parse with no hints
            st.session_state.ing_omc   = None
            st.session_state.ing_fy    = None
            st.session_state.ing_mi    = None
            st.session_state.ing_label = None
            st.session_state.ing_step  = 2
            st.rerun()
        if st.button("← Back"):
            st.session_state.ing_step = 0
            st.rerun()
        return

    # Non-PVT: pre-fill dropdowns from detected values, let user override
    st.caption("Detected values are pre-filled. Change anything that looks wrong before proceeding.")

    omc_det    = detected.get("omc")
    fy_code_det = detected.get("fy_code")
    mi_det     = detected.get("month_index")

    # When the filename had no year, fall back to the next expected period from the DB
    if fy_code_det is None or mi_det is None:
        sugg_fy, sugg_mi = _suggest_next_period(db_path, omc_det)
        if fy_code_det is None and sugg_fy:
            fy_code_det = sugg_fy
        if mi_det is None and sugg_mi:
            mi_det = sugg_mi

    col1, col2, col3 = st.columns(3)
    omc_default = _OMC_LIST.index(omc_det) if omc_det in _OMC_LIST else 0
    fy_default  = (list(reversed(_FY_OPTIONS)).index(fy_code_det)
                   if fy_code_det in _FY_OPTIONS else 1)   # index 1 = current FY fallback
    mi_default  = mi_det or 1

    # Use _w-suffixed widget keys so that Streamlit does NOT own ing_omc/ing_fy/ing_mi.
    # On "Next" we copy the widget values into the plain keys; downstream steps
    # read from those plain keys.  This avoids both:
    #   (a) StreamlitAPIException from manually setting a widget-owned key, and
    #   (b) widget keys being cleared when the widget is no longer rendered.
    with col1:
        omc = st.selectbox("OMC", _OMC_LIST, index=omc_default, key="_ing_omc_w")
    with col2:
        fy  = st.selectbox("Financial Year", list(reversed(_FY_OPTIONS)),
                           index=fy_default, key="_ing_fy_w")
    with col3:
        mi  = st.selectbox(
            "Month", list(_MONTH_OPTS.keys()),
            format_func=lambda x: f"{_MONTH_OPTS[x]} ({x})",
            index=list(_MONTH_OPTS.keys()).index(mi_default),
            key="_ing_mi_w",
        )

    label = _month_label(fy, mi)

    # Already-ingested warning
    try:
        import sqlite3 as _sq, tempfile as _tf
        with open(db_path, "rb") as f: data = f.read()
        t = _tf.NamedTemporaryFile(suffix=".db", delete=False); t.close()
        with open(t.name, "wb") as f: f.write(data)
        con = _sq.connect(t.name)
        row = con.execute(
            "SELECT run_id, ingested_at FROM ingestion_log "
            "WHERE omc=? AND fy_code=? AND month_index=?", (omc, fy, mi)
        ).fetchone()
        con.close(); os.unlink(t.name)
        if row:
            st.warning(
                f"⚠️ {omc} {label} {fy} was already ingested "
                f"(run_id={row[0]}, at {row[1]}). "
                "Proceeding will **replace** existing data for the ROs in this file."
            )
    except Exception:
        pass

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← Back"):
            st.session_state.ing_step = 0
            st.rerun()
    with col2:
        if st.button("Next → Parse & validate", type="primary"):
            # Explicitly persist to non-widget keys — safe to write anytime.
            st.session_state.ing_omc   = omc
            st.session_state.ing_fy    = fy
            st.session_state.ing_mi    = mi
            st.session_state.ing_label = label
            st.session_state.ing_step  = 2
            st.rerun()


def _step_dry_run(db_path: str):
    """Step 2 — Parse file + show dry-run summary."""
    omc      = _ss("ing_omc")
    fy       = _ss("ing_fy")
    mi       = _ss("ing_mi")
    label    = _ss("ing_label")
    tmp_path = _ss("ing_tmp_path")
    filename = _ss("ing_filename", "")
    is_pvt   = _ss("ing_detected", {}).get("fmt") == "pvt_sales_format"

    st.subheader(f"Step 3 — Validate  ·  {filename}")

    with st.spinner("Parsing file…"):
        try:
            df = detect_and_parse(
                tmp_path,
                omc_hint    = None if is_pvt else omc,
                month_index = None if is_pvt else mi,
                fy_code     = None if is_pvt else fy,
            )
        except Exception as e:
            st.error(f"Parse failed: {e}")
            if st.button("← Back"):
                st.session_state.ing_step = 1
                st.rerun()
            return

    if df.empty:
        st.error("Parser returned 0 rows. Check OMC selection and file format.")
        if st.button("← Back"):
            st.session_state.ing_step = 1
            st.rerun()
        return

    # For PVT: override omc/fy/mi from parsed data
    if is_pvt and "omc" in df.columns:
        omc   = str(df["omc"].iloc[0])
        fy    = str(df["fy_code"].iloc[0])
        mi    = int(df["month_index"].iloc[0])
        label = _month_label(fy, mi)
        st.session_state.ing_omc   = omc
        st.session_state.ing_fy    = fy
        st.session_state.ing_mi    = mi
        st.session_state.ing_label = label
        st.info(f"PVT file: detected **{omc}  {label}  {fy}** from file contents.")

    pl = Pipeline(db_path, _BACKUP_DIR)
    with st.spinner("Running validation checks…"):
        summary = pl.dry_run(df, omc, fy, mi, label)

    st.session_state.ing_df      = df
    st.session_state.ing_summary = summary
    st.session_state.ing_pl      = pl

    # Summary metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total rows",   summary["total_rows"])
    c2.metric("Known ROs",    summary["known_ros"])
    c3.metric("Unknown ROs",  summary["unknown_ros"],
              delta=f"{summary['unknown_ros']} new" if summary["unknown_ros"] else None,
              delta_color="off")
    c4.metric("MS (KL)",      f"{summary['total_ms_kl']:,.1f}")
    c5.metric("HSD (KL)",     f"{summary['total_hsd_kl']:,.1f}")

    if summary["duplicate"]:
        d = summary["duplicate"]
        st.warning(
            f"⚠️ Already ingested: run_id={d['run_id']}, at {d['ingested_at']}. "
            "Proceeding will replace rows for ROs in this file."
        )
    if summary["outlier_count"]:
        with st.expander(f"⚠️ {summary['outlier_count']} volume outlier(s)"):
            st.dataframe(
                pd.DataFrame(summary["outliers"])[
                    ["sap_code", "ro_name", "product", "volume_kl", "outlier_reason"]
                ], use_container_width=True, hide_index=True
            )
    if summary["unknown_sap_codes"]:
        with st.expander(f"ℹ️ {summary['unknown_ros']} unknown SAP code(s) — will be staged"):
            udf = df[df["sap_code"].isin(summary["unknown_sap_codes"])][
                ["sap_code", "ro_name", "product", "volume_kl"]
            ].drop_duplicates(subset=["sap_code"])
            st.dataframe(udf, use_container_width=True, hide_index=True)
    if summary["fuzzy_districts"]:
        st.warning(f"⚠️ {len(summary['fuzzy_districts'])} RO(s) with uncertain district — confirm in next step.")

    st.divider()
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← Back"):
            st.session_state.ing_step = 1
            st.rerun()
    with col2:
        next_step = 3 if summary["fuzzy_districts"] else (
                    4 if summary["unknown_sap_codes"] else 5)
        if st.button("Next →", type="primary"):
            st.session_state.ing_step = next_step
            st.rerun()


def _step_fuzzy():
    """Step 3 — Confirm fuzzy district matches."""
    summary   = _ss("ing_summary", {})
    fuzzy     = summary.get("fuzzy_districts", [])
    decisions = _ss("ing_fuzzy_decisions", {})

    st.subheader("Step 4 — Confirm district matches")
    st.caption("Uncertain district names found. Confirm or reject each.")

    for row in fuzzy:
        sap, raw, norm = row["sap_code"], row["district_raw"], row["district"]
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**{sap}** — `{raw}` → **{norm}**")
        with col2:
            dec = st.radio("Accept?", ["✅ Yes", "❌ No — exclude"],
                           key=f"fuzz_{sap}", horizontal=True,
                           label_visibility="collapsed")
            decisions[sap] = "accept" if dec.startswith("✅") else "exclude"
    st.session_state.ing_fuzzy_decisions = decisions

    st.divider()
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← Back"):
            st.session_state.ing_step = 2
            st.rerun()
    with col2:
        next_step = 4 if summary.get("unknown_sap_codes") else 5
        if st.button("Confirm & continue →", type="primary"):
            excl = {s for s, d in decisions.items() if d == "exclude"}
            if excl:
                df = _ss("ing_df")
                df = df[~df["sap_code"].isin(excl)].copy()
                st.session_state.ing_df = df
            st.session_state.ing_step = next_step
            st.rerun()


def _lookup_ro(db_path: str, sap_code: str) -> dict | None:
    """Return dim_ro row dict for sap_code, or None if not found."""
    try:
        import sqlite3 as _sq
        with open(db_path, "rb") as f:
            data = f.read()
        t = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        t.close()
        with open(t.name, "wb") as f:
            f.write(data)
        con = _sq.connect(t.name)
        row = con.execute(
            "SELECT sap_code, ro_name, omc, district, rsa_code, rsa_name, trading_area "
            "FROM dim_ro WHERE sap_code=?", (sap_code.strip(),)
        ).fetchone()
        con.close(); os.unlink(t.name)
        if not row:
            return None
        keys = ["sap_code","ro_name","omc","district","rsa_code","rsa_name","trading_area"]
        return dict(zip(keys, row))
    except Exception:
        return None


def _step_unknown(db_path: str):
    """Step 4 — Classify unknown SAP codes."""
    df          = _ss("ing_df")
    summary     = _ss("ing_summary", {})
    unknown     = summary.get("unknown_sap_codes", [])
    resolutions = _ss("ing_unknown_resolutions", {})

    st.subheader("Step 5 — Unknown SAP codes")
    st.caption(
        "Not found in dim_ro. Options: **Stage for later** (queue without blocking), "
        "**Map to existing RO** (new code for same outlet — data folds into existing history), "
        "or **Skip**."
    )

    udf = df[df["sap_code"].isin(unknown)][
        ["sap_code", "ro_name", "product", "volume_kl"]
    ].drop_duplicates(subset=["sap_code"])

    all_valid = True
    for _, row in udf.iterrows():
        sap = row["sap_code"]
        vol_ms  = df[(df["sap_code"]==sap) & (df["product"]=="MS")]["volume_kl"].sum()
        vol_hsd = df[(df["sap_code"]==sap) & (df["product"]=="HSD")]["volume_kl"].sum()
        st.write(f"**{sap}** — {row['ro_name']}  ·  MS {vol_ms:,.1f} KL  ·  HSD {vol_hsd:,.1f} KL")

        res = st.radio(
            "Action",
            ["Stage for later (recommended)", "Map to existing RO", "Skip this run"],
            key=f"unk_{sap}", horizontal=True, label_visibility="collapsed",
        )

        if res.startswith("Map"):
            existing = st.text_input(
                "Existing SAP code to merge into",
                key=f"remap_input_{sap}",
                placeholder="e.g. 196740",
                help="Volume data will be attributed to the existing RO's SAP code. "
                     "The new code is recorded in legacy_sap_codes.",
            )
            if existing and existing.strip():
                found = _lookup_ro(db_path, existing.strip())
                if found:
                    st.success(
                        f"✅ Found: **{found['ro_name']}** · {found['district']} · "
                        f"{found['rsa_name'] or found['rsa_code']}"
                    )
                    resolutions[sap] = f"map:{existing.strip()}"
                else:
                    st.error(f"❌ SAP code {existing.strip()} not found in dim_ro.")
                    all_valid = False
                    resolutions[sap] = "stage"   # fallback until a valid code is entered
            else:
                all_valid = False   # force user to enter a code before proceeding
                resolutions[sap] = "stage"
        elif res.startswith("Stage"):
            resolutions[sap] = "stage"
        else:
            resolutions[sap] = "skip"

        st.divider()

    st.session_state.ing_unknown_resolutions = resolutions

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← Back"):
            back = 3 if summary.get("fuzzy_districts") else 2
            st.session_state.ing_step = back
            st.rerun()
    with col2:
        # Block "Confirm" if any "Map" choice is still missing a valid target code
        map_incomplete = any(
            st.session_state.get(f"unk_{s}", "").startswith("Map")
            and not resolutions.get(s, "").startswith("map:")
            for s in unknown
        )
        if map_incomplete:
            st.button("Confirm & continue →", type="primary", disabled=True)
            st.caption("⚠️ Enter a valid existing SAP code for each 'Map to existing RO' selection.")
        elif st.button("Confirm & continue →", type="primary"):
            df = _ss("ing_df").copy()

            # Apply SAP code remaps — rewrite new code → existing code in the df
            remaps = {s: r.split(":")[1] for s, r in resolutions.items() if r.startswith("map:")}
            if remaps:
                df["sap_code"] = df["sap_code"].replace(remaps)
                # Drop ro_name column artefacts so the correct name from dim_ro is used
                st.session_state.ing_sap_remaps = remaps

            # Drop skipped codes
            skip = {s for s, r in resolutions.items() if r == "skip"}
            if skip:
                df = df[~df["sap_code"].isin(skip)]

            st.session_state.ing_df   = df.copy()
            st.session_state.ing_step = 5
            st.rerun()


def _step_commit(db_path: str):
    """Step 5 — Final review + commit."""
    df    = _ss("ing_df")
    omc   = _ss("ing_omc")
    fy    = _ss("ing_fy")
    mi    = _ss("ing_mi")
    label = _ss("ing_label")
    fname = _ss("ing_filename", "")

    st.subheader("Step 6 — Review and Commit")

    ms_kl  = round(float(df[df["product"]=="MS"]["volume_kl"].sum()), 1)
    hsd_kl = round(float(df[df["product"]=="HSD"]["volume_kl"].sum()), 1)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OMC",           omc)
    c2.metric("Period",        f"{label} {fy}")
    c3.metric("MS (KL)",       f"{ms_kl:,.1f}")
    c4.metric("HSD (KL)",      f"{hsd_kl:,.1f}")

    # Optional PVT district cross-check
    district_totals = {}
    if omc in _PVT_OMCS:
        with st.expander("📋 Optional — enter district totals for cross-check"):
            for dist in sorted(COVERAGE_DISTRICTS):
                c1, c2 = st.columns(2)
                ms_t  = c1.number_input(f"{dist} MS (KL)",  min_value=0.0,
                                        step=0.1, key=f"dt_{dist}_MS")
                hsd_t = c2.number_input(f"{dist} HSD (KL)", min_value=0.0,
                                        step=0.1, key=f"dt_{dist}_HSD")
                if ms_t  > 0: district_totals[(dist, "MS")]  = ms_t
                if hsd_t > 0: district_totals[(dist, "HSD")] = hsd_t

    notes = st.text_input("Notes (optional)", key="ing_notes",
                          placeholder="e.g. Corrected re-upload")

    st.divider()
    st.warning("⚠️ This will write to the database. A snapshot backup is taken automatically.")

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← Back"):
            back = 4 if _ss("ing_summary",{}).get("unknown_sap_codes") else (
                   3 if _ss("ing_summary",{}).get("fuzzy_districts") else 2)
            st.session_state.ing_step = back
            st.rerun()
    with col2:
        if st.button("🚀 Commit to database", type="primary"):
            pl = _ss("ing_pl") or Pipeline(db_path, _BACKUP_DIR)
            with st.spinner("Writing to database…"):
                result = pl.commit(
                    df, omc, fy, mi, label,
                    district_totals = district_totals or None,
                    source_label    = fname,
                    notes           = notes,
                    force           = True,
                )
            # Record any SAP code remaps in dim_ro.legacy_sap_codes
            remaps = _ss("ing_sap_remaps", {})
            if remaps and result.get("ok"):
                for new_sap, existing_sap in remaps.items():
                    record_sap_remap(new_sap, existing_sap, omc, db_path)
            st.session_state.ing_result      = result
            st.session_state.ing_pl          = pl
            st.session_state.ing_commit_time = time.time()
            st.session_state.ing_step        = 6
            # CRITICAL (fix F1): invalidate all cached loaders so the
            # dashboard reflects the newly ingested data immediately —
            # without this, tabs keep serving pre-ingestion frames until
            # the server process restarts.
            if result.get("ok"):
                st.cache_data.clear()
            st.rerun()


def _step_done():
    """Step 6 — Result + rollback."""
    result      = _ss("ing_result", {})
    pl          = _ss("ing_pl")
    commit_time = _ss("ing_commit_time", 0)

    if result.get("ok"):
        st.success(f"✅ {result['message']}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rows inserted",    result.get("rows_inserted","—"))
        c2.metric("Branded rows",     result.get("branded_rows", 0))
        c3.metric("New ROs staged",   result.get("new_ros_found", 0))
        c4.metric("Outliers flagged", result.get("outliers_flagged", 0))

        g = result.get("reconciliation", {})
        st.divider()
        st.write("**Reconciliation guard** (FY 2025-26 baseline)")
        gc1, gc2, gc3, gc4 = st.columns(4)
        gc1.metric("MS share (Ind 6)",  f"{g.get('MS_ind','—'):.4f} pp",
                   delta=f"{g.get('MS_ind',0)-g.get('baseline_MS_ind',0):+.4f}",
                   delta_color="off")
        gc2.metric("HSD share (Ind 6)", f"{g.get('HSD_ind','—'):.4f} pp",
                   delta=f"{g.get('HSD_ind',0)-g.get('baseline_HSD_ind',0):+.4f}",
                   delta_color="off")
        gc3.metric("MS share (PSU 3)",  f"{g.get('MS_psu','—'):.4f} pp",
                   delta=f"{g.get('MS_psu',0)-g.get('baseline_MS_psu',0):+.4f}",
                   delta_color="off")
        gc4.metric("Guard passed",      "✅ Yes" if g.get("ok") else "❌ No")

        if result.get("district_discrepancies"):
            with st.expander("⚠️ District total mismatches"):
                st.dataframe(pd.DataFrame(result["district_discrepancies"]),
                             use_container_width=True, hide_index=True)

        # Rollback panel — 5-minute window
        if (time.time() - commit_time) < 300 and pl:
            st.divider()
            st.write("**↩️ Rollback** (available for 5 minutes)")
            snap = result.get("snapshot_path", "")
            st.caption(f"Snapshot: `{os.path.basename(snap)}`" if snap else "")
            if st.button("🔄 Roll back now", type="secondary"):
                with st.spinner("Restoring…"):
                    ok = pl.rollback()
                if ok:
                    st.success("✅ Rolled back to pre-commit state.")
                    st.cache_data.clear()   # fix F1 — reflect rollback too
                    _reset()
                    st.rerun()
                else:
                    st.error("Rollback failed — snapshot not found.")
    else:
        st.error(f"❌ {result.get('message','Unknown error')}")
        if result.get("reconciliation"):
            st.json(result["reconciliation"])

    st.divider()
    if st.button("🔁 Ingest another file", type="primary"):
        _reset()
        st.rerun()


# ── Progress bar ──────────────────────────────────────────────────────────────
_STEPS = ["Upload", "Confirm", "Validate", "Districts", "New ROs", "Commit", "Done"]

def _progress(step: int):
    cols = st.columns(len(_STEPS))
    for i, (col, name) in enumerate(zip(cols, _STEPS)):
        with col:
            if i < step:
                st.markdown(
                    f"<div style='text-align:center;color:#4CAF50;font-size:0.8em'>✔ {name}</div>",
                    unsafe_allow_html=True)
            elif i == step:
                st.markdown(
                    f"<div style='text-align:center;font-weight:bold;font-size:0.8em'>▶ {name}</div>",
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    f"<div style='text-align:center;color:#aaa;font-size:0.8em'>{name}</div>",
                    unsafe_allow_html=True)
    st.divider()


# ── Main entry point ──────────────────────────────────────────────────────────

def render():
    st.title("📥 Data Ingestion")
    st.caption(
        "Upload any OMC exchange file — the app detects the OMC, month, and FY "
        "automatically. Upload one file per run; files can be uploaded in any order."
    )

    db_path = _get_db_path()
    step    = _ss("ing_step", 0)
    _progress(step)

    summary = _ss("ing_summary", {})

    if step == 0:
        _step_upload()
    elif step == 1:
        _step_confirm_meta(db_path)
    elif step == 2:
        _step_dry_run(db_path)
    elif step == 3:
        if summary.get("fuzzy_districts"):
            _step_fuzzy()
        else:
            st.session_state.ing_step = 4 if summary.get("unknown_sap_codes") else 5
            st.rerun()
    elif step == 4:
        if summary.get("unknown_sap_codes"):
            _step_unknown(db_path)
        else:
            st.session_state.ing_step = 5
            st.rerun()
    elif step == 5:
        _step_commit(db_path)
    elif step == 6:
        _step_done()

"""
core.py — Pune DO Dashboard shared foundation
==============================================
Constants, formatters, DB connection, data loaders, nil helpers,
action-plan persistence, metric engine, and TA grid helpers.

All tab modules import from here. app.py imports from here too.
Nothing in this file calls Streamlit widgets (no st.sidebar, st.radio, etc.)
— it is pure data and computation. Only @st.cache_data / @st.cache_resource
decorators are used (those are safe to call at import time).
"""
from __future__ import annotations
import os
import sqlite3
import pandas as pd
import streamlit as st
import altair as alt  # re-exported so tab files can import from core

# --------------------------------------------------------------------------- #
# Path / DB resolution
# --------------------------------------------------------------------------- #
HERE = os.path.dirname(os.path.abspath(__file__))

def _find_db():
    env = os.environ.get("PUNE_DO_DB")
    if env and os.path.exists(env):
        return env
    for d in (HERE, os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, "pune_do.db")
        if os.path.exists(p):
            return p
    return os.path.join(HERE, "pune_do.db")

def _is_fuse_mount(path: str) -> bool:
    """Return True if *path* lives on a FUSE-mounted filesystem (macOS / Linux).

    FUSE mounts include exFAT/NTFS USB drives (Kingston etc.), network shares
    (SMB, NFS via FUSE), and cloud-synced folders backed by FUSE drivers.
    Running SQLite directly on a FUSE mount is unsafe — fsync() is not reliably
    honoured, which can silently corrupt the WAL/journal.
    """
    try:
        import subprocess
        # `df -T <path>` on macOS returns fstype in column 1
        result = subprocess.run(
            ["df", "-T", path],
            capture_output=True, text=True, timeout=3
        )
        output = result.stdout.lower()
        fuse_indicators = ("fuse", "ntfs", "exfat", "smbfs", "nfs", "cifs", "webdav")
        return any(ind in output for ind in fuse_indicators)
    except Exception:  # noqa: BLE001
        return False  # fail-open: don't block startup on detection errors

DB_PATH = _find_db()

# Warn loudly if the DB is on a FUSE mount — SQLite WAL corruption risk.
# This runs at import time so the warning appears in the dashboard banner.
_FUSE_WARNING = _is_fuse_mount(DB_PATH) if os.path.exists(DB_PATH) else False

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
PSU = ["IOCL", "BPCL", "HPCL"]
PVT = ["NEL", "RBML", "SIMPL"]
OMC_ORDER = PSU + PVT
OMC_SHORT = {"IOCL": "IOC", "BPCL": "BPC", "HPCL": "HPC",
             "NEL": "NEL", "RBML": "RBML", "SIMPL": "SIMPL"}
OMC_COLORS = {
    "IOCL":  "#F47920",   # IOC Orange
    "BPCL":  "#FFD100",   # BPC Lemon Yellow
    "HPCL":  "#00AEEF",   # HPC Sky Blue
    "NEL":   "#7B2D8B",   # Nayara Purple
    "RBML":  "#009E49",   # Reliance Green
    "SIMPL": "#FFC200",   # Shell Yellow-Orange
}

COM_LABELS = {"A": "A — Urban/City", "C": "C — Semi-Urban",
              "D1": "D1 — National Highway", "D2": "D2 — State Highway",
              "E": "E — Rural/Interior"}
# month_index 1 = Apr … 12 = Mar
MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep",
          "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
MIDX = {m: i + 1 for i, m in enumerate(MONTHS)}
QUARTERS = {"Q1 (Apr–Jun)": [1, 2, 3], "Q2 (Jul–Sep)": [4, 5, 6],
            "Q3 (Oct–Dec)": [7, 8, 9], "Q4 (Jan–Mar)": [10, 11, 12]}

# --------------------------------------------------------------------------- #
# Indian-style number formatting  (1,23,456.78)
# --------------------------------------------------------------------------- #
def indian(n, dec=0):
    if n is None or pd.isna(n):
        return "—"
    neg = n < 0
    n = abs(float(n))
    whole = int(n)
    frac = n - whole
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    if dec:
        s += f".{round(frac, dec):.{dec}f}"[2:].ljust(dec, "0")
        s = s if "." in s else s + "." + "0" * dec
    return ("-" if neg else "") + s

def pct(x, dec=2):
    return "—" if x is None or pd.isna(x) else f"{x:.{dec}f}%"

def pp(x, dec=2):
    return "—" if x is None or pd.isna(x) else f"{'+' if x >= 0 else ''}{x:.{dec}f}"

# --------------------------------------------------------------------------- #
# Growth-aware formatters  (↑ green / ↓ red) — for use in Styler.format()
# --------------------------------------------------------------------------- #
def fmt_gr(v, dec=2):
    """Growth % with directional arrow prefix."""
    if v is None or pd.isna(v):
        return "—"
    if v > 0:
        return f"↑ {v:.{dec}f}%"
    if v < 0:
        return f"↓ {abs(v):.{dec}f}%"
    return f"{v:.{dec}f}%"

def fmt_pp(v, dec=2):
    """Share-point change with directional arrow prefix."""
    if v is None or pd.isna(v):
        return "—"
    if v > 0:
        return f"↑ {v:.{dec}f}"
    if v < 0:
        return f"↓ {abs(v):.{dec}f}"
    return f"{v:.{dec}f}"

def fmt_notional(v, dec=1):
    """Notional KL with directional arrow prefix."""
    if v is None or pd.isna(v):
        return "—"
    if v > 0:
        return f"↑ {indian(v, dec)}"
    if v < 0:
        return f"↓ {indian(abs(v), dec)}"
    return indian(v, dec)

def _gcss(v):
    """Pandas Styler .map() function → CSS for a raw-numeric growth cell."""
    try:
        f = float(v)
        if pd.isna(f) or f == 0:
            return ""
        return "color:#2da44e;font-weight:600" if f > 0 else "color:#cf222e;font-weight:600"
    except Exception:
        return ""

def style_growth(df, cols):
    """Return a pd.Styler with green/red coloring on the named raw-float columns."""
    valid = [c for c in cols if c in df.columns]
    return df.style.map(_gcss, subset=valid)

def detail_table(row) -> pd.DataFrame:
    """Convert a single pandas row (Series, e.g. `df.iloc[0]`) into a clean
    two-column Field/Value table for display via st.dataframe — used for
    'record detail' panels so they render as a spreadsheet-style table
    instead of a raw JSON/code block. Handles numpy scalar -> native Python
    conversion and blanks out NaN/None."""
    fields, values = [], []
    for k, v in row.items():
        if pd.isna(v):
            v = ""
        elif hasattr(v, "item"):  # numpy scalar (int64/float64/bool_)
            v = v.item()
            # whole-number floats display as e.g. "30" not "30.0"
            if isinstance(v, float) and v.is_integer():
                v = int(v)
        fields.append(str(k).replace("_", " ").strip().title())
        values.append(str(v))
    # Force a single dtype on Value — a mixed int/str column trips Arrow's
    # (pyarrow) type inference used by st.dataframe.
    return pd.DataFrame({"Field": fields, "Value": pd.array(values, dtype="string")})

# --------------------------------------------------------------------------- #
# KLPM  (Rule #194 — locked definition)
# KLPM = Total Volume (KL) ÷ Months in Period ÷ Number of ROs in scope
# --------------------------------------------------------------------------- #
def klpm(volume_kl, n_months, n_ros):
    """Kilolitres Per Month Per RO.

    Args:
        volume_kl : total volume for the OMC / product / scope / period (KL)
        n_months  : number of months in the selected period (e.g. 12 for full FY)
        n_ros     : number of ROs under consideration in the same scope
                    • Regular products  → count from dim_ro (all ROs of that OMC in scope)
                    • Branded products  → count from fact_branded_monthly full history
                      (ROs with any positive uplift for that brand in scope; Rule #196)
    Returns:
        float KL/month/RO, or 0.0 if either denominator is zero.
    """
    if not n_months or not n_ros:
        return 0.0
    return float(volume_kl) / float(n_months) / float(n_ros)

# --------------------------------------------------------------------------- #
# Data layer
# --------------------------------------------------------------------------- #
@st.cache_resource
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def _hwy_type(series):
    hw = series.fillna("").astype(str).str.upper().str.strip()
    out = pd.Series("Non-Highway", index=series.index)
    out[hw.str.startswith("NH")] = "NH"
    out[hw.str.startswith("SH")] = "SH"
    return out

@st.cache_data
def load_monthly():
    """fact_monthly enriched with RO-master attributes (com, highway, names)."""
    c = get_conn()
    df = pd.read_sql("""
        SELECT f.sap_code, f.ta_code, f.rsa_code, f.omc, f.district,
               f.product, f.fy_code, f.month_index, f.volume_kl,
               r.com, r.highway_no, r.rsa_name, r.ro_name
        FROM fact_monthly f
        JOIN dim_ro r ON f.sap_code = r.sap_code
    """, c)
    df["hwy_type"] = _hwy_type(df["highway_no"])
    df["highway_no"] = df["highway_no"].fillna("").astype(str).str.strip()
    return df

@st.cache_data
def load_ro_master():
    df = pd.read_sql("SELECT * FROM dim_ro", get_conn())
    df["hwy_type"] = _hwy_type(df["highway_no"])
    df["highway_no"] = df["highway_no"].fillna("").astype(str).str.strip()
    return df

@st.cache_data
def load_ta_dim():
    return pd.read_sql("SELECT * FROM dim_ta", get_conn())

# --------------------------------------------------------------------------- #
# Branded products (XP95/XP100 = branded MS, XG = branded HSD, etc.)
# Locked branded master (HANDOFF 2026-06-04 §2b). One branded name per OMC×product.
# --------------------------------------------------------------------------- #
BRANDED_MASTER = {
    ("IOCL", "MS"):  "XP95",
    ("BPCL", "MS"):  "Speed",
    ("HPCL", "MS"):  "Power",
    ("IOCL", "HSD"): "XG",
    ("BPCL", "HSD"): "Hi Speed Diesel",
    ("HPCL", "HSD"): "Turbojet",
}
BRANDED_PSU = ["IOCL", "BPCL", "HPCL"]   # private OMCs carry no branded data

# IOCL MS has two branded products; all other OMC×product combos have one.
# Use this list wherever IOCL MS needs to be split by brand.
IOCL_MS_BRANDS = ["XP95", "XP100"]

def brand_of(omc, product):
    """Canonical branded name for an OMC×product, or '' if none."""
    return BRANDED_MASTER.get((omc, product), "")

_BRANDED_COLS = ["sap_code", "omc", "product", "brand", "fy_code", "month_index",
                 "month_label", "volume_kl", "district", "rsa_code", "rsa_name",
                 "ta_code", "com", "highway_no", "hwy_type", "ro_name"]

@st.cache_data
def load_branded():
    """fact_branded_monthly enriched with RO-master attributes for drill-down.

    Returns an empty (correctly-columned) frame if the table is absent, so the
    branded tab degrades gracefully on a DB that predates ingestion.
    """
    try:
        df = pd.read_sql("""
            SELECT b.sap_code, b.omc, b.product, b.brand, b.fy_code,
                   b.month_index, b.month_label, b.volume_kl,
                   r.district, r.rsa_code, r.rsa_name, r.ta_code, r.com,
                   r.highway_no, r.ro_name
            FROM fact_branded_monthly b
            JOIN dim_ro r ON b.sap_code = r.sap_code
        """, get_conn())
    except Exception:
        return pd.DataFrame(columns=_BRANDED_COLS)
    df["hwy_type"] = _hwy_type(df["highway_no"])
    df["highway_no"] = df["highway_no"].fillna("").astype(str).str.strip()
    return df

@st.cache_data
def fy_list():
    return pd.read_sql(
        "SELECT DISTINCT fy_code FROM fact_monthly ORDER BY fy_code",
        get_conn())["fy_code"].tolist()

def prev_fy(fy, fys):
    i = fys.index(fy)
    return fys[i - 1] if i > 0 else None

# --------------------------------------------------------------------------- #
# Nil-Selling calendar helpers
# --------------------------------------------------------------------------- #
_NIL_BASE_YEAR = 2018   # Apr of this calendar year = cal_pos 0

def _cal_pos(fy_code: str, month_idx: int) -> int:
    """Absolute calendar position (Apr 2018 = 0, May 2018 = 1, …)."""
    return (int(fy_code.split("-")[0]) - _NIL_BASE_YEAR) * 12 + (month_idx - 1)

def _from_cal_pos(pos: int):
    """(fy_code, month_idx) from absolute calendar position."""
    fy_start = pos // 12 + _NIL_BASE_YEAR
    month_idx = pos % 12 + 1
    return f"{fy_start}-{str(fy_start + 1)[-2:]}", month_idx

def _cal_label(fy_code: str, month_idx: int) -> str:
    """Human label: 'Mar 2025'. month_idx 1=Apr … 12=Mar."""
    fy_start = int(fy_code.split("-")[0])
    cal_year = fy_start if month_idx <= 9 else fy_start + 1
    return f"{MONTHS[month_idx - 1]} {cal_year}"

@st.cache_data
def available_months():
    """All (fy_code, month_index) pairs with data, sorted chronologically."""
    df = pd.read_sql(
        "SELECT DISTINCT fy_code, month_index FROM fact_monthly "
        "ORDER BY fy_code, month_index", get_conn())
    rows = [{"fy_code": r.fy_code, "month_index": r.month_index,
             "label": _cal_label(r.fy_code, r.month_index),
             "cal_pos": _cal_pos(r.fy_code, r.month_index)}
            for r in df.itertuples()]
    return sorted(rows, key=lambda x: x["cal_pos"])

# --------------------------------------------------------------------------- #
# Nil-Selling computation
# NOTE: `monthly` and `ta_name_map` are passed explicitly (not globals) so
# this function works cleanly when imported by a tab module.
# --------------------------------------------------------------------------- #
def _nil_compute(omcs: list, product: str, ref_fy: str, ref_mi: int,
                 ro_scope_df: pd.DataFrame,
                 monthly: pd.DataFrame,
                 ta_name_map) -> pd.DataFrame:
    """
    Compute NIL / About-to-Go-Nil / YTS / Revival flags for every RO of `omcs`
    in `ro_scope_df` as of reference month (ref_fy, ref_mi).

    Rules (all locked in Rules_and_Definitions_v1.2.1.csv):
      NIL        — zero upliftment in m0, m1, m2 (3 consecutive months)
      About-to-Go-Nil — zero in m0 and m1 only (m2 > 0)
      Revival    — positive in m0; was NIL at m-1 check (m1=m2=m3=0)
      PRCN rule  — negative volume clipped to 0 before any check
      YTS        — NIL RO commissioned ≤12 months ago; excluded from NIL list

    Returns DataFrame indexed by sap_code with flags, volumes, and display cols.
    """
    ref_pos = _cal_pos(ref_fy, ref_mi)
    # m0 = ref, m1 = ref-1, m2 = ref-2, m3 = ref-3
    mk = [_from_cal_pos(ref_pos - i) for i in range(4)]

    scope_saps = set(ro_scope_df[ro_scope_df["omc"].isin(omcs)]["sap_code"])
    if not scope_saps:
        return pd.DataFrame()

    # Pull only the 4 needed months from monthly
    needed_fys = list({k[0] for k in mk})
    raw = monthly[
        monthly["omc"].isin(omcs)
        & monthly["product"].eq(product)
        & monthly["sap_code"].isin(scope_saps)
        & monthly["fy_code"].isin(needed_fys)
    ].copy()
    raw["vol"] = raw["volume_kl"].clip(lower=0)
    raw["mk_key"] = list(zip(raw["fy_code"], raw["month_index"]))
    raw = raw[raw["mk_key"].isin(set(mk))]

    # Pivot: sap_code × month_key → summed volume
    agg = (raw.groupby(["sap_code", "mk_key"])["vol"]
               .sum()
               .unstack("mk_key", fill_value=0.0))
    agg = agg.rename(columns={mk[i]: f"m{i}" for i in range(4)})
    for col in ["m0", "m1", "m2", "m3"]:
        if col not in agg.columns:
            agg[col] = 0.0

    # ROs in scope with zero sales across all 4 months (not in fact_monthly)
    missing = scope_saps - set(agg.index)
    if missing:
        z = pd.DataFrame(0.0, index=list(missing),
                         columns=["m0", "m1", "m2", "m3"])
        z.index.name = "sap_code"
        agg = pd.concat([agg, z])

    # Flags
    agg["is_nil"]     = (agg.m0 == 0) & (agg.m1 == 0) & (agg.m2 == 0)
    agg["is_atrisk"]  = ~agg.is_nil    & (agg.m0 == 0) & (agg.m1 == 0)
    agg["is_revival"] = (agg.m0  > 0)  & (agg.m1 == 0) & (agg.m2 == 0) & (agg.m3 == 0)
    agg["streak"]     = 0
    agg["last_sale"]  = ""

    # Streak + last-sale month for NIL rows (scan full history)
    nil_saps = agg[agg.is_nil].index.tolist()
    if nil_saps:
        hist = monthly[
            monthly["sap_code"].isin(nil_saps)
            & monthly["product"].eq(product)
            & monthly["omc"].isin(omcs)
        ].copy()
        hist["vol"] = hist["volume_kl"].clip(lower=0)
        hist["cp"] = ((hist["fy_code"].str.split("-").str[0].astype(int)
                       - _NIL_BASE_YEAR) * 12 + hist["month_index"] - 1)
        hist = (hist[hist["cp"] <= ref_pos]
                .sort_values(["sap_code", "cp"], ascending=[True, False]))
        streaks, last_sales = {}, {}
        for sap, grp in hist.groupby("sap_code"):
            cnt = 0
            for v in grp["vol"].values:
                if v <= 0:
                    cnt += 1
                else:
                    break
            streaks[sap] = max(cnt, 3)   # floor at 3 (definition threshold)
            nz = grp[grp["vol"] > 0]
            last_sales[sap] = (_cal_label(nz.iloc[0]["fy_code"],
                                          nz.iloc[0]["month_index"])
                               if not nz.empty else "Never (in data)")
        for sap in nil_saps:
            agg.at[sap, "streak"]    = streaks.get(sap, 3)
            agg.at[sap, "last_sale"] = last_sales.get(sap, "Never (in data)")

    # ── YTS (Yet to Start) identification ─────────────────────────────────────
    agg["is_yts"]        = False
    agg["comm_label"]    = ""
    agg["doc_source"]    = ""
    agg["months_in_yts"] = 0
    if nil_saps:
        # An RO counts as "ever sold" only if it has >1 positive month
        # for this product. A single positive month is the commissioning
        # / inaugural stock fill — not commercial selling.
        ever_sold_s = (
            monthly[
                monthly["sap_code"].isin(nil_saps)
                & monthly["omc"].isin(omcs)
                & monthly["product"].eq(product)
            ]
            .groupby("sap_code")["volume_kl"]
            .apply(lambda x: bool((x.clip(lower=0) > 0).sum() > 1))
        )
        never_sold = [s for s in nil_saps if not ever_sold_s.get(s, False)]
        if never_sold:
            doc_lookup = {}
            if "doc" in ro_scope_df.columns:
                doc_lookup = (ro_scope_df[ro_scope_df["omc"].isin(omcs)]
                              [["sap_code", "doc"]].drop_duplicates("sap_code")
                              .set_index("sap_code")["doc"].to_dict())
            first_db = (
                monthly[monthly["sap_code"].isin(never_sold)
                        & monthly["omc"].isin(omcs)]
                .assign(cp=lambda d: (
                    d["fy_code"].str.split("-").str[0].astype(int)
                    - _NIL_BASE_YEAR) * 12 + d["month_index"] - 1)
                .groupby("sap_code")["cp"].min()
            )
            for sap in never_sold:
                comm_pos, src = None, ""
                doc_val = doc_lookup.get(sap)
                if doc_val and pd.notna(doc_val) and str(doc_val).strip():
                    try:
                        dt = pd.to_datetime(str(doc_val).strip(), dayfirst=True)
                        m_cal, y_cal = dt.month, dt.year
                        fy_s = y_cal if m_cal >= 4 else y_cal - 1
                        mi   = m_cal - 3 if m_cal >= 4 else m_cal + 9
                        comm_pos = _cal_pos(f"{fy_s}-{str(fy_s + 1)[-2:]}", mi)
                        src = "DOC (Master)"
                    except Exception:
                        pass
                if comm_pos is None and sap in first_db.index:
                    comm_pos = int(first_db[sap])
                    src = "Derived (first data)"
                if comm_pos is None:
                    continue
                elapsed = ref_pos - comm_pos
                if 1 <= elapsed <= 12:
                    agg.at[sap, "is_yts"]        = True
                    agg.at[sap, "comm_label"]    = _cal_label(*_from_cal_pos(comm_pos))
                    agg.at[sap, "doc_source"]    = src
                    agg.at[sap, "months_in_yts"] = elapsed

    # YTS are excluded from the NIL list
    agg["is_nil"] = agg["is_nil"] & ~agg["is_yts"]

    # ── Attach RO display columns ──────────────────────────────────────────────
    meta_cols = ["sap_code", "ro_name", "rsa_name", "district", "com", "ta_code"]
    if "doc" in ro_scope_df.columns:
        meta_cols.append("doc")
    ro_info = (ro_scope_df[ro_scope_df["omc"].isin(omcs)]
               [meta_cols].drop_duplicates("sap_code").set_index("sap_code"))
    agg = agg.join(ro_info, how="left")
    agg["ta_name"] = agg["ta_code"].map(ta_name_map).fillna("")
    return agg

# --------------------------------------------------------------------------- #
# Action-plan persistence  (nil_action_plans table in pune_do.db)
# --------------------------------------------------------------------------- #
def _ensure_ap_table():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("""
        CREATE TABLE IF NOT EXISTS nil_action_plans (
            sap_code    TEXT PRIMARY KEY,
            action_text TEXT DEFAULT '',
            officer     TEXT DEFAULT '',
            status      TEXT DEFAULT 'active',
            created_at  TEXT,
            updated_at  TEXT,
            cleared_at  TEXT
        )
    """)
    con.commit(); con.close()

@st.cache_data
def load_action_plans() -> pd.DataFrame:
    """Active action plans indexed by sap_code."""
    try:
        _ensure_ap_table()
        df = pd.read_sql(
            "SELECT sap_code, action_text, officer, updated_at "
            "FROM nil_action_plans WHERE status = 'active'",
            get_conn())
        return df.set_index("sap_code")
    except Exception:
        return pd.DataFrame(columns=["action_text", "officer", "updated_at"])

def save_action_plans(updates: list):
    """Upsert action plans. updates=[{sap_code, action_text, officer}]"""
    if not updates:
        return
    _ensure_ap_table()
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    for r in updates:
        con.execute("""
            INSERT OR REPLACE INTO nil_action_plans
                (sap_code, action_text, officer, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active',
                COALESCE((SELECT created_at FROM nil_action_plans
                          WHERE sap_code = ?), ?), ?)
        """, (r["sap_code"], r["action_text"], r["officer"],
              r["sap_code"], now, now))
    con.commit(); con.close()
    load_action_plans.clear()

def clear_plans_for_revivals(sap_codes: list):
    """Auto-clear action plans when an RO revives."""
    if not sap_codes:
        return
    _ensure_ap_table()
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    ph  = ",".join("?" * len(sap_codes))
    con.execute(
        f"UPDATE nil_action_plans "
        f"SET status='cleared_by_revival', cleared_at=? "
        f"WHERE sap_code IN ({ph}) AND status='active'",
        [now] + list(sap_codes))
    con.commit(); con.close()
    load_action_plans.clear()

def get_cleared_plans(sap_codes: list) -> pd.DataFrame:
    """Cleared action plans for display in the Revivals section."""
    if not sap_codes:
        return pd.DataFrame(columns=["action_text", "officer", "cleared_at"])
    try:
        _ensure_ap_table()
        ph = ",".join("?" * len(sap_codes))
        return pd.read_sql(
            f"SELECT sap_code, action_text, officer, cleared_at "
            f"FROM nil_action_plans "
            f"WHERE sap_code IN ({ph}) AND status='cleared_by_revival'",
            get_conn(), params=tuple(sap_codes)
        ).set_index("sap_code")
    except Exception:
        return pd.DataFrame(columns=["action_text", "officer", "cleared_at"])

# --------------------------------------------------------------------------- #
# XtraPower data loaders + action-plan persistence
# --------------------------------------------------------------------------- #
_XP_COLS = ["sap_code", "fy_code", "month_index", "month_label",
            "hsd_kl", "xp_kl", "ro_name", "rsa_code", "rsa_name",
            "district", "com", "ta_code", "highway_no", "hwy_type"]

@st.cache_data
def load_xtrapower():
    """fact_xtrapower_monthly enriched with RO-master attributes.

    Returns an empty correctly-columned frame if the table is absent
    (DB predates XP ingestion), so the tab degrades gracefully.
    """
    try:
        df = pd.read_sql("""
            SELECT x.sap_code, x.fy_code, x.month_index, x.month_label,
                   x.hsd_kl, x.xp_kl,
                   r.ro_name, r.rsa_code, r.rsa_name, r.district, r.com,
                   r.ta_code, r.highway_no
            FROM fact_xtrapower_monthly x
            JOIN dim_ro r ON x.sap_code = r.sap_code
        """, get_conn())
    except Exception:
        return pd.DataFrame(columns=_XP_COLS)
    df["hwy_type"]  = _hwy_type(df["highway_no"])
    df["highway_no"] = df["highway_no"].fillna("").astype(str).str.strip()
    return df

@st.cache_data
def load_itps():
    """dim_itps: sap_code → mid (Merchant ID; NULL string if no ITPS).

    Returns empty frame if table absent.
    """
    try:
        return pd.read_sql("SELECT sap_code, mid FROM dim_itps", get_conn())
    except Exception:
        return pd.DataFrame(columns=["sap_code", "mid"])

@st.cache_data
def xp_available_months():
    """All (fy_code, month_index) pairs present in fact_xtrapower_monthly,
    sorted chronologically. Returns [] if table absent."""
    try:
        df = pd.read_sql(
            "SELECT DISTINCT fy_code, month_index FROM fact_xtrapower_monthly "
            "ORDER BY fy_code, month_index",
            get_conn())
        rows = [{"fy_code":     r.fy_code,
                 "month_index": r.month_index,
                 "label":       _cal_label(r.fy_code, r.month_index),
                 "cal_pos":     _cal_pos(r.fy_code, r.month_index)}
                for r in df.itertuples()]
        return sorted(rows, key=lambda x: x["cal_pos"])
    except Exception:
        return []

def _ensure_xp_ap_table():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("""
        CREATE TABLE IF NOT EXISTS xp_action_plans (
            sap_code    TEXT NOT NULL,
            category    TEXT NOT NULL,
            action_text TEXT DEFAULT '',
            officer     TEXT DEFAULT '',
            status      TEXT DEFAULT 'active',
            created_at  TEXT,
            updated_at  TEXT,
            PRIMARY KEY (sap_code, category)
        )
    """)
    con.commit(); con.close()

@st.cache_data
def load_xp_action_plans(category: str) -> pd.DataFrame:
    """Active XP action plans for `category` ('no_itps' or 'nil_transacting')."""
    try:
        _ensure_xp_ap_table()
        df = pd.read_sql(
            "SELECT sap_code, action_text, officer, updated_at "
            "FROM xp_action_plans WHERE category=? AND status='active'",
            get_conn(), params=(category,))
        return df.set_index("sap_code")
    except Exception:
        return pd.DataFrame(columns=["action_text", "officer", "updated_at"])

def save_xp_action_plans(updates: list, category: str):
    """Upsert XP action plans.  updates = [{sap_code, action_text, officer}]"""
    if not updates:
        return
    _ensure_xp_ap_table()
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    for r in updates:
        con.execute("""
            INSERT OR REPLACE INTO xp_action_plans
                (sap_code, category, action_text, officer, status,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, 'active',
                COALESCE((SELECT created_at FROM xp_action_plans
                          WHERE sap_code=? AND category=?), ?), ?)
        """, (r["sap_code"], category, r["action_text"], r["officer"],
              r["sap_code"], category, now, now))
    con.commit(); con.close()
    load_xp_action_plans.clear()

# --------------------------------------------------------------------------- #
# Core metric engine  (vectorised — no python row loops)
# --------------------------------------------------------------------------- #
def _pivot(frame, group_cols, universe):
    """volume_kl summed → index=group_cols, one column per OMC in `universe`."""
    def _empty():
        idx = (pd.MultiIndex.from_tuples([], names=group_cols)
               if len(group_cols) > 1
               else pd.Index([], name=group_cols[0]))
        return pd.DataFrame(columns=universe, index=idx)
    if frame.empty:
        return _empty()
    sub = frame[frame.omc.isin(universe)]
    if sub.empty:
        return _empty()
    p = (sub.groupby(group_cols + ["omc"])["volume_kl"].sum()
             .unstack("omc"))
    return p.reindex(columns=universe, fill_value=0.0).fillna(0.0)

def share_frame(cy_f, ly_f, group_cols, universe):
    """Per-group CY/LY volume, share, +/- and notional for every OMC in universe.

    Returns a tidy DataFrame indexed by reset group_cols with, per omc:
      <omc>_cyvol, <omc>_lyvol, <omc>_cyshare, <omc>_lyshare,
      <omc>_diffvol, <omc>_gr, <omc>_ppt, <omc>_notional
    plus cy_tot / ly_tot.
    """
    cyp = _pivot(cy_f, group_cols, universe)
    lyp = _pivot(ly_f, group_cols, universe)
    idx = cyp.index.union(lyp.index)
    cyp = cyp.reindex(idx, fill_value=0.0)
    lyp = lyp.reindex(idx, fill_value=0.0)
    cy_tot = cyp.sum(axis=1)
    ly_tot = lyp.sum(axis=1)
    out = pd.DataFrame(index=idx)
    cy_tot_s = cy_tot.where(cy_tot > 0)
    ly_tot_s = ly_tot.where(ly_tot > 0)
    for omc in universe:
        cyv, lyv = cyp[omc], lyp[omc]
        cs = (cyv / cy_tot_s * 100).fillna(0.0)
        ls = (lyv / ly_tot_s * 100).fillna(0.0)
        out[f"{omc}_cyvol"] = cyv
        out[f"{omc}_lyvol"] = lyv
        out[f"{omc}_diffvol"] = cyv - lyv
        out[f"{omc}_gr"] = ((cyv - lyv) / lyv.where(lyv > 0) * 100).where(
            lyv > 0, pd.NA)
        out[f"{omc}_cyshare"] = cs
        out[f"{omc}_lyshare"] = ls
        out[f"{omc}_ppt"] = cs - ls
        out[f"{omc}_notional"] = (cs - ls) / 100 * cy_tot
    out["cy_tot"] = cy_tot
    out["ly_tot"] = ly_tot
    if group_cols:
        return out.reset_index()
    return out.reset_index(drop=True)

def totals_row(cy_f, ly_f, universe):
    """Single-row share_frame (whole selection).

    Returns a zero-filled Series if no data is available, so callers
    can safely read share/volume columns without an IndexError.
    """
    result = share_frame(cy_f.assign(_all=1), ly_f.assign(_all=1),
                         ["_all"], universe)
    if result.empty:
        return pd.Series({c: 0.0 for c in result.columns})
    return result.iloc[0]

def participation(ro_df, group_cols):
    """Network outlet count per OMC (distinct sap_code) at a scope."""
    if ro_df.empty:
        cols = group_cols + OMC_ORDER + ["Total"]
        return pd.DataFrame([[0] * len(cols)], columns=cols) if not group_cols \
            else pd.DataFrame(columns=cols)
    if not group_cols:
        s = ro_df.groupby("omc")["sap_code"].nunique().reindex(
            OMC_ORDER, fill_value=0).astype(int)
        row = {o: int(s[o]) for o in OMC_ORDER}
        row["Total"] = int(s.sum())
        return pd.DataFrame([row])
    p = (ro_df.groupby(group_cols + ["omc"])["sap_code"].nunique()
         .unstack("omc").reindex(columns=OMC_ORDER, fill_value=0)
         .fillna(0).astype(int))
    p["Total"] = p.sum(axis=1)
    return p.reset_index()

# --------------------------------------------------------------------------- #
# Trading-Area "Top TA by Volume in Industry" grid  (PPT format)
# --------------------------------------------------------------------------- #
def ta_volume_grid(src, ta, months, fy_cy, fy_ly, cy_pairs=None, ly_pairs=None):
    """Per-RO MS & HSD CY/LY volume for EVERY OMC's outlets in a TA.

    Pass cy_pairs/ly_pairs (sets of (fy_code, month_index) tuples) for
    multi-FY mode; leave None for single-FY mode (uses months + fy_cy/fy_ly).
    """
    base = src[src.ta_code == ta]
    ros = (base[["sap_code", "ro_name", "omc", "district"]]
           .drop_duplicates("sap_code"))
    def vol(fy, prod, pairs=None):
        if pairs:
            fymi = base.fy_code + "_" + base.month_index.astype(str)
            keys = {f"{f}_{m}" for f, m in pairs}
            d = base[fymi.isin(keys) & (base["product"] == prod)]
        elif fy:
            d = base[(base.fy_code == fy) & (base["product"] == prod)
                     & (base.month_index.isin(months))]
        else:
            return {}
        return d.groupby("sap_code")["volume_kl"].sum().to_dict()
    mcy = vol(fy_cy, "MS", cy_pairs)
    mly = vol(fy_ly, "MS", ly_pairs)
    hcy = vol(fy_cy, "HSD", cy_pairs)
    hly = vol(fy_ly, "HSD", ly_pairs)
    rows = []
    for r in ros.itertuples():
        rows.append(dict(
            ro=r.ro_name or r.sap_code, loc=r.district or "", omc=r.omc,
            ms_cy=float(mcy.get(r.sap_code, 0.0)),
            ms_ly=float(mly.get(r.sap_code, 0.0)),
            hs_cy=float(hcy.get(r.sap_code, 0.0)),
            hs_ly=float(hly.get(r.sap_code, 0.0))))
    df = pd.DataFrame(rows)
    tot = dict(ms_cy=sum(mcy.values()), ms_ly=sum(mly.values()),
               hs_cy=sum(hcy.values()), hs_ly=sum(hly.values()))
    return df, tot

def _block(cy, ly, tcy, tly):
    """One product's 8 figures: volCY,volLY,+/-,%GR,shrCY,shrLY,shrGr(pp),Not."""
    diff = cy - ly
    gr = (diff / ly * 100) if ly else None
    scy = (cy / tcy * 100) if tcy else 0.0
    sly = (ly / tly * 100) if tly else 0.0
    sgr = scy - sly
    return cy, ly, diff, gr, scy, sly, sgr, sgr / 100 * tcy

def render_ta_html(df, tot, ta_code, ta_name, period_lbl):
    """Faithful 'Top Trading Area by Volume in Industry' table as HTML.

    CRITICAL: output must have NO leading whitespace per line — Streamlit's
    markdown treats lines with 4+ leading spaces as code blocks.
    The final join strips all leading whitespace.
    """
    df = df.copy()
    df["tot_cy"] = df.ms_cy + df.hs_cy
    df["omc_rank"] = df.omc.map({o: i for i, o in enumerate(OMC_ORDER)})
    df = df.sort_values(["omc_rank", "tot_cy"], ascending=[True, False])

    def td(v, cls=""):
        return f'<td class="{cls}">{v}</td>'

    def _cspan(v, text):
        """Wrap growth text in a colored span based on sign of v."""
        if v is None:
            return "—"
        if v > 0:
            return f'<span style="color:#2da44e;font-weight:600">↑ {text}</span>'
        if v < 0:
            return f'<span style="color:#cf222e;font-weight:600">↓ {text}</span>'
        return text

    def data_tds(ms_cy, ms_ly, hs_cy, hs_ly):
        ms = _block(ms_cy, ms_ly, tot["ms_cy"], tot["ms_ly"])
        hs = _block(hs_cy, hs_ly, tot["hs_cy"], tot["hs_ly"])
        tds = []
        for blk in (ms, hs):
            cy_, ly_, diff, gr, *_ = blk
            tds += [td(indian(cy_, 1)), td(indian(ly_, 1)),
                    td(_cspan(diff, indian(abs(diff), 1))),
                    td(_cspan(gr, f"{abs(gr):.2f}%") if gr is not None else "—")]
        for blk in (ms, hs):
            *_, scy, sly, sgr, notv = blk
            tds += [td(pct(scy)), td(pct(sly)),
                    td(_cspan(sgr, f"{abs(sgr):.2f}")),
                    td(_cspan(notv, indian(abs(notv), 1)))]
        return "".join(tds)

    body = []
    sn = 0
    for r in df.itertuples():
        sn += 1
        body.append(
            f'<tr>'
            f'<td class="stk1">{sn}</td>'
            f'<td class="l stk2">{r.ro}</td>'
            f'<td class="l stk3">{r.loc}</td>'
            f'<td class="stk4">{OMC_SHORT.get(r.omc, r.omc)}</td>'
            + data_tds(r.ms_cy, r.ms_ly, r.hs_cy, r.hs_ly) + '</tr>')

    def agg(rows):
        return (rows.ms_cy.sum(), rows.ms_ly.sum(),
                rows.hs_cy.sum(), rows.hs_ly.sum())

    def sub(label, code, rows, cls, loc=""):
        s = agg(rows)
        return (f'<tr class="{cls}">'
                f'<td class="stk1"></td>'
                f'<td class="l stk2">{label}</td>'
                f'<td class="stk3">{loc}</td>'
                f'<td class="stk4">{code}</td>'
                + data_tds(*s) + '</tr>')

    for omc in OMC_ORDER:
        rows = df[df.omc == omc]
        if not rows.empty:
            body.append(sub(omc, "", rows, "sub",
                            loc=f"Total ROs: {len(rows)}"))
    psu = df[df.omc.isin(PSU)]
    pvt = df[df.omc.isin(PVT)]
    body.append(sub("Total PSU", "PSU", psu, "tot"))
    if not pvt.empty:
        body.append(sub("Total Pvt.", "Pvt", pvt, "tot"))
    body.append(sub("Total Industry", "Ind", df, "tot"))
    n = max(len(df), 1)
    avg_tds = data_tds(tot["ms_cy"] / n, tot["ms_ly"] / n,
                       tot["hs_cy"] / n, tot["hs_ly"] / n)
    body.append(
        f'<tr class="tot">'
        f'<td class="stk1"></td>'
        f'<td class="l stk2">Trading Area Average</td>'
        f'<td class="stk3"></td>'
        f'<td class="stk4">Avg</td>'
        f'{avg_tds}</tr>')

    # ── Sticky-column geometry (cols 1-4 fixed, balance scrolls) ────────────────
    # Col widths (px):  S.No=36  Name=190  Location=110  Oil Co.=50
    _W1, _W2, _W3, _W4 = 36, 190, 110, 50
    _L2, _L3, _L4 = _W1, _W1+_W2, _W1+_W2+_W3   # left offsets for stk2-4
    _SPAN_W = _W1+_W2+_W3+_W4                      # colspan-4 header min-width

    css = f"""<style>
.tagrid{{border-collapse:separate;border-spacing:0;font-size:11px;width:100%;}}
.tagrid td,.tagrid th{{border:1px solid #888;padding:2px 5px;text-align:right;white-space:nowrap;}}
.tagrid td.l,.tagrid th.l{{text-align:left;}}
.tagrid th{{background:#efe7d3;color:#1a3a6b;font-weight:700;text-align:center;}}
.tagrid th.ms{{background:#e8731c;color:#fff;}}
.tagrid th.hs{{background:#3aaed8;color:#fff;}}
.tagrid th.band{{background:#d9c9a3;color:#1a3a6b;}}
.tagrid tr.sub td{{background:#dcdcdc;font-weight:700;}}
.tagrid tr.tot td{{background:#d0e4f7;font-weight:700;}}
.tawrap{{overflow-x:auto;border:1px solid #888;}}
.stk1,.stk2,.stk3,.stk4{{position:sticky;z-index:2;}}
.stk1{{left:0;min-width:{_W1}px;}}
.stk2{{left:{_L2}px;min-width:{_W2}px;}}
.stk3{{left:{_L3}px;min-width:{_W3}px;}}
.stk4{{left:{_L4}px;min-width:{_W4}px;border-right:2px solid #555!important;}}
.tagrid tr td.stk1,.tagrid tr td.stk2,.tagrid tr td.stk3,.tagrid tr td.stk4{{background:#fff;}}
.tagrid tr.sub td.stk1,.tagrid tr.sub td.stk2,.tagrid tr.sub td.stk3,.tagrid tr.sub td.stk4{{background:#dcdcdc;}}
.tagrid tr.tot td.stk1,.tagrid tr.tot td.stk2,.tagrid tr.tot td.stk3,.tagrid tr.tot td.stk4{{background:#d0e4f7;}}
.tagrid th.stk1,.tagrid th.stk2,.tagrid th.stk3,.tagrid th.stk4{{background:#efe7d3;z-index:3;}}
.tagrid th.stk4{{border-right:2px solid #555!important;}}
.tagrid th.stk-span{{position:sticky;left:0;z-index:3;background:#d9c9a3;color:#1a3a6b;min-width:{_SPAN_W}px;}}
@media (prefers-color-scheme:dark){{
.tagrid th,.tagrid th.stk1,.tagrid th.stk2,.tagrid th.stk3,.tagrid th.stk4{{background:#2c3e6b;color:#e8d5b0;}}
.tagrid th.band,.tagrid th.stk-span{{background:#2c3e6b;color:#e8d5b0;}}
.tagrid th.ms{{background:#b85a10;}}
.tagrid th.hs{{background:#1e7a9e;}}
.tagrid tr td.stk1,.tagrid tr td.stk2,.tagrid tr td.stk3,.tagrid tr td.stk4{{background:#0e1117;}}
.tagrid tr.sub td{{background:#2a2a3a;}}
.tagrid tr.sub td.stk1,.tagrid tr.sub td.stk2,.tagrid tr.sub td.stk3,.tagrid tr.sub td.stk4{{background:#2a2a3a;}}
.tagrid tr.tot td{{background:#1e2e4a;}}
.tagrid tr.tot td.stk1,.tagrid tr.tot td.stk2,.tagrid tr.tot td.stk3,.tagrid tr.tot td.stk4{{background:#1e2e4a;}}
.stk4,.tagrid th.stk4{{border-right:2px solid #888!important;}}
}}
</style>"""
    head = (
        f'<tr><th class="l band stk-span" colspan="4">Trading Area: {ta_code} — {ta_name}'
        f' &nbsp;|&nbsp; Period: {period_lbl}</th>'
        f'<th class="band" colspan="8">Period — Volume (KL)</th>'
        f'<th class="band" colspan="8">Market Share in TA</th></tr>'
        f'<tr><th class="l stk1" rowspan="2">S.No</th>'
        f'<th class="l stk2" rowspan="2">Name of RO</th>'
        f'<th class="l stk3" rowspan="2">Location</th>'
        f'<th class="stk4" rowspan="2">Oil Co.</th>'
        f'<th class="ms" colspan="4">MS Vol (KL)</th>'
        f'<th class="hs" colspan="4">HSD Vol (KL)</th>'
        f'<th class="ms" colspan="4">MS</th>'
        f'<th class="hs" colspan="4">HSD</th></tr>'
        f'<tr>{"".join(f"<th>{c}</th>" for c in ["CY","LY","+/-","%GR","CY","LY","+/-","%GR","CY","LY","Gr pp","Not.Vol","CY","LY","Gr pp","Not.Vol"])}</tr>'
    )
    html = (css + '<div class="tawrap"><table class="tagrid">'
            + head + "".join(body) + "</table></div>")
    return "".join(line.strip() for line in html.splitlines())


# --------------------------------------------------------------------------- #
# v2 module loaders (COCO / Swagat / REMM / Commissioning / Lube / Alt-fuel /
# Geo). All cached; all degrade to empty frames if the table is absent.
# --------------------------------------------------------------------------- #
def _safe_sql(sql: str, cols: list, params=()):
    try:
        return pd.read_sql(sql, get_conn(), params=params)
    except Exception:
        return pd.DataFrame(columns=cols)

@st.cache_data
def load_coco_wo():
    """coco_work_orders joined with dim_ro attributes."""
    return _safe_sql("""
        SELECT w.*, r.ro_name, r.district, r.rsa_name, r.trading_area, r.ta_code
        FROM coco_work_orders w LEFT JOIN dim_ro r ON w.sap_code = r.sap_code
        WHERE w.status = 'Active'
    """, ["sap_code","coco_type","operation_mode","operator_name",
          "operator_original_sap","date_of_appointment","wo_period_months",
          "date_of_expiry","status","remarks","ro_name","district","rsa_name",
          "trading_area","ta_code"])

def coco_alert_tier(expiry_iso, appt_iso) -> tuple:
    """Return (tier_key, label, colour) for a COCO work order.

    NaN-safe (2026-07-06): SQL NULLs may surface as float NaN depending on
    the pandas version, and NaN is truthy — without _safe_date() a no-WO
    COCO would fall through and misreport as 'Active'."""
    appt, expiry = _safe_date(appt_iso), _safe_date(expiry_iso)
    if appt is None or expiry is None:
        return ("no_wo", "No Work Order", "#8c8c8c")
    days = (expiry - pd.Timestamp.today().normalize()).days
    if days < 0:      return ("expired",  "Expired",          "#cf222e")
    if days <= 30:    return ("critical", "Critical",         "#e5531a")
    if days <= 60:    return ("exp_crit", "Expiry Critical",  "#f79009")
    if days <= 90:    return ("exp_soon", "Expiring Soon",    "#eac54f")
    return ("active", "Active", "#2da44e")

@st.cache_data
def load_swagat_ext():
    return _safe_sql("SELECT * FROM swagat_extended_ta ORDER BY sr_no",
                     ["swagat_sap_code","sr_no","ro_sap_code","ro_name",
                      "omc","rsa_name","side"])

@st.cache_data
def load_remm():
    return _safe_sql("SELECT * FROM remm_master",
                     ["remm_id","rdb_code","ro_name","rsa_name","com",
                      "land_class","agreement_no","sub_agreement_no","mutation",
                      "vendor_code","vendor_name","lease_from","lease_validity",
                      "lease_area_sqft","initial_rent","revised_rent",
                      "vendor_pan","name_on_pan","vendor_gst","bank_ifsc",
                      "bank_account","legacy_rdb_codes","action_plan",
                      "action_taken","target_date","remarks"])

@st.cache_data
def load_remm_payments():
    return _safe_sql("SELECT * FROM remm_payments",
                     ["remm_id","fy_code","month_index","amount"])

def _safe_text(v) -> str:
    """Coerce any DB cell (None / NaN / pd.NA / str / other) to a plain string.
    Guards against the 'NaN is truthy' trap: `nan or ""` returns `nan` (not ""),
    which crashes downstream .strip()/.lower() calls with AttributeError."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass  # pd.isna() raises on some array-likes; not a concern for scalars here
    return str(v)


def _safe_date(v):
    """Coerce a DB cell to a pd.Timestamp, or None if missing/unparseable."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return pd.Timestamp(v)
    except Exception:
        return None


def remm_status(row) -> tuple:
    """Compute (code, label, colour) per REMM governance — NEVER stored."""
    lc = _safe_text(row.get("land_class")).strip().lower()
    validity = _safe_date(row.get("lease_validity"))
    agreement_no = _safe_text(row.get("agreement_no")).strip()

    if lc == "own land":
        return ("S0", "Own Land", "#57606a")
    if lc.startswith("govt"):
        if validity and validity < pd.Timestamp.today():
            return ("S7", "Govt — Validity Lapsed", "#8250df")
        return ("S7", "Govt Landlord", "#8250df")
    if not agreement_no or not validity:
        return ("S8", "Pending", "#8c8c8c")
    days = (validity - pd.Timestamp.today().normalize()).days
    if days < 0:        return ("S1", "Expired",          "#cf222e")
    if days <= 90:      return ("S2", "Emergency (<90d)", "#e5531a")
    if days <= 365:     return ("S3", "Critical (<1 yr)", "#f79009")
    if days <= 3*365:   return ("S4", "Warning (1–3 yrs)","#eac54f")
    if days <= 5*365:   return ("S5", "Watch (3–5 yrs)",  "#54aeff")
    return ("S6", "Active (>5 yrs)", "#2da44e")

@st.cache_data
def load_loi():
    return _safe_sql("SELECT * FROM loi_master", ["loi_id"])

@st.cache_data
def load_lube():
    return _safe_sql("""
        SELECT l.*, r.ro_name, r.rsa_name, r.district
        FROM fact_lube_monthly l LEFT JOIN dim_ro r ON l.sap_code = r.sap_code
    """, ["sap_code","product","fy_code","month_index","qty_l",
          "ro_name","rsa_name","district"])

@st.cache_data
def load_alt_fuel_master():
    return _safe_sql("""
        SELECT m.*, r.ro_name, r.district, r.rsa_name
        FROM alt_fuel_master m LEFT JOIN dim_ro r ON m.sap_code = r.sap_code
    """, ["sap_code","fuel_type","site_type","com","comm_year",
          "sales_start_date","cgd_company","corpus_flag","station_type",
          "ro_name","district","rsa_name"])

@st.cache_data
def load_alt_fuel():
    return _safe_sql("SELECT * FROM fact_alt_fuel_monthly",
                     ["sap_code","fuel_type","fy_code","month_index","qty_kg"])

@st.cache_data
def load_geo():
    return _safe_sql("SELECT * FROM dim_ro_geo", ["sap_code"])

"""Tab 22 — New RO Commissioning Pipeline (LOI register).

Data protocol (officer, 2026-07-04): monthly bulk Excel upload-replace PLUS
in-dashboard interim edits (audited in loi_edit_log). Pre-replace diff shows
local edits so nothing is silently lost.
Tracking keys pre-commissioning: Location SN + LOI number. SAP joins at
commissioning (final_status='Commissioned').
"""
from __future__ import annotations

import pandas as pd
import sqlite3
import streamlit as st
from components.downloads import df_download

from core import DB_PATH, detail_table, indian, load_loi

PERM_COLS = ["perm_mojnai", "perm_building_plan", "perm_police", "perm_nh_pwd",
             "perm_mseb", "perm_ind_safety", "perm_wildlife", "perm_forest"]
EDITABLE = ["commissionable", "site_readiness", "layout_drawing", "concept_note",
            "estimate", "io_available", "io_no", "tender_status", "wo_number",
            "wo_date", "contractor", "expected_noc_month", "expected_comm_month",
            "final_status", "sap_code"] + PERM_COLS

# Register sort order (officer decision, 2026-07-06): live pipeline stages first
# (1-6), then Commissioned (now a regular RO — deprioritised but still visible),
# then Cancelled at the very bottom.
STAGE_SORT = {
    "1. LOI Issued": 1, "2. NOCs in Process": 2, "3. NOCs Complete": 3,
    "4. IO Available": 4, "5. Tendering": 5, "6. Work Order": 6,
    "7. Commissioned": 7, "X. Cancelled": 8,
}

# Fields the combined search box matches against (substring, case-insensitive).
SEARCH_COLS = ["location_desc", "rsa_name", "loi_holder", "loi_number"]


def _v(r, col) -> str:
    """NaN-safe, whitespace-safe string value of a register field.

    CRITICAL: never use `if r.get(col):` on register fields — SQL NULLs can
    surface as float NaN depending on the pandas version, and float('nan') is
    TRUTHY. That bug put every live LOI into '6. Work Order' on deployments
    whose pandas returned NaN for NULL text columns (fixed 2026-07-06).
    """
    val = r.get(col)
    if val is None or (isinstance(val, float) and val != val) or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "-", "—") else s


def _age_bucket(loi_date):
    if loi_date is None or pd.isna(loi_date) or not str(loi_date).strip():
        return "Unknown"
    try:
        days = (pd.Timestamp.today() - pd.Timestamp(loi_date)).days
    except Exception:
        return "Unknown"
    if pd.isna(days):
        return "Unknown"
    for lim, lbl in [(182, "0-6M"), (365, "6-12M"), (730, "1-2Y"),
                     (1095, "2-3Y"), (1460, "3-4Y"), (1825, "4-5Y")]:
        if days <= lim: return lbl
    return ">5Y"


# Register vocabulary (observed 2026-07-06, incl. common typos):
_RECEIVED = ("received", "recieved", "recived", "yes")
_NA_OK    = ("na", "not required", "not applicable")


def _stage(r):
    """Current pipeline stage derived from the register fields (NaN-safe)."""
    fstat = _v(r, "final_status")
    if fstat.startswith("Commissioned"):
        return "7. Commissioned"
    if fstat.startswith("Cancelled"):
        return "X. Cancelled"
    # A real work order carries a WO number (>=4 digits) — placeholder texts
    # like 'NOC Awaited' / 'IO Awaited' do NOT count.
    wo = _v(r, "wo_number")
    if sum(ch.isdigit() for ch in wo) >= 4:
        return "6. Work Order"
    tender = _v(r, "tender_status").lower()
    if tender.startswith(("published", "awarded", "yes")):
        return "5. Tendering"
    if _v(r, "io_available").lower().startswith("y"):
        return "4. IO Available"
    perms = [_v(r, c).lower() for c in PERM_COLS]
    filled = [p for p in perms if p]
    if filled and all(p.startswith(_RECEIVED + _NA_OK) for p in filled)             and any(p.startswith(_RECEIVED) for p in filled):
        return "3. NOCs Complete"
    if any(p.startswith(("applied",) + _RECEIVED) for p in perms):
        return "2. NOCs in Process"
    return "1. LOI Issued"


def _edit_write(loi_number, field, old, new, who="dashboard"):
    import os, tempfile
    with open(DB_PATH, "rb") as f: data = f.read()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
    with open(tmp.name, "wb") as f: f.write(data)
    con = sqlite3.connect(tmp.name)
    con.execute(f"UPDATE loi_master SET {field}=? WHERE loi_number=?", (new, loi_number))
    con.execute("INSERT INTO loi_edit_log (loi_number, field, old_value, new_value, edited_by)"
                " VALUES (?,?,?,?,?)", (loi_number, field, str(old), str(new), who))
    con.commit(); con.close()
    with open(tmp.name, "rb") as f: nd = f.read()
    staging = DB_PATH + ".tmp"
    with open(staging, "wb") as f: f.write(nd); f.flush(); os.fsync(f.fileno())
    os.replace(staging, DB_PATH); os.unlink(tmp.name)
    st.cache_data.clear()


def render(ctx):
    loi = load_loi()
    if loi.empty:
        st.info("LOI register not loaded."); return
    loi["stage"] = loi.apply(_stage, axis=1)
    loi["loi_age"] = loi["loi_date"].map(_age_bucket)
    st.caption(f"Register snapshot: **{loi.snapshot_date.iloc[0]}** · {len(loi)} LOIs total")

    # ── Filter & Drilldown (applies to every section below) ────────────────
    st.subheader("🔎 Filter & Drilldown")
    search = st.text_input(
        "Search — Location Name / Sales Area / LOI Holder / LOI Number",
        key="comm_search", placeholder="Type any part of a location, sales area, holder name, or LOI number…")

    st.caption("Filters · independent, multi-select (empty = all)")
    any_filter_active = any(
        st.session_state.get(k) for k in
        ("comm_stage", "comm_srmp", "comm_com", "comm_dist", "comm_rsa")
    )
    if any_filter_active:
        def _clear_comm_filters():
            for k in ("comm_stage", "comm_srmp", "comm_com", "comm_dist", "comm_rsa"):
                st.session_state[k] = []
        st.button("✕ Clear all filters", on_click=_clear_comm_filters, key="comm_clear")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        f_stage = st.multiselect("Stage", sorted(loi.stage.unique()), key="comm_stage")
    with c2:
        f_srmp = st.multiselect("SRMP", sorted(loi.marketing_plan.dropna().unique()), key="comm_srmp")
    with c3:
        f_com = st.multiselect("COM", sorted(loi.market_class.dropna().unique()), key="comm_com")
    with c4:
        f_dist = st.multiselect("District", sorted(loi.district.dropna().unique()), key="comm_dist")
    with c5:
        f_rsa = st.multiselect("Sales Area", sorted(loi.rsa_name.dropna().unique()), key="comm_rsa")

    view = loi.copy()
    if search.strip():
        s = search.strip().lower()
        mask = False
        for col in SEARCH_COLS:
            mask = mask | view[col].fillna("").str.lower().str.contains(s, regex=False)
        view = view[mask]
    if f_stage: view = view[view.stage.isin(f_stage)]
    if f_srmp:  view = view[view.marketing_plan.isin(f_srmp)]
    if f_com:   view = view[view.market_class.isin(f_com)]
    if f_dist:  view = view[view.district.isin(f_dist)]
    if f_rsa:   view = view[view.rsa_name.isin(f_rsa)]
    view_live = view[~view.stage.isin(["X. Cancelled"])]
    st.caption(f"{len(view)} of {len(loi)} LOIs match the current selection.")

    # ── KPIs ───────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Live LOIs", len(view_live[view_live.stage != "7. Commissioned"]))
    k2.metric("Commissionable", len(view_live[view_live.commissionable.str.strip().str.lower().eq("yes").fillna(False)]))
    k3.metric("Commissioned (register)", len(view[view.stage == "7. Commissioned"]))
    k4.metric("Cancelled", len(view[view.stage == "X. Cancelled"]))
    k5.metric("LOIs > 2 years old",
              len(view_live[view_live.loi_age.isin(["2-3Y", "3-4Y", "4-5Y", ">5Y"])]))

    # ── Stage funnel ───────────────────────────────────────────────────────
    st.subheader("🪜 Pipeline Stage Funnel")
    _all_stages = [s for s in STAGE_SORT if s != "X. Cancelled"]
    fun = (view_live.stage.value_counts().reindex(_all_stages, fill_value=0)
           .rename_axis("Stage").reset_index(name="LOIs"))
    st.dataframe(fun, hide_index=True, use_container_width=True)
    df_download(fun, "comm_funnel")

    # ── Ageing × RSA matrix ────────────────────────────────────────────────
    st.subheader("⏳ LOI Ageing")
    order = ["0-6M", "6-12M", "1-2Y", "2-3Y", "3-4Y", "4-5Y", ">5Y", "Unknown"]
    mat = (view_live.pivot_table(index="rsa_name", columns="loi_age",
                            values="loi_number", aggfunc="count", fill_value=0)
               .reindex(columns=[c for c in order if c in view_live.loi_age.unique()]))
    mat["Total"] = mat.sum(axis=1)
    st.dataframe(mat, use_container_width=True)
    df_download(mat.reset_index(), "comm_ageing")

    # ── LOI Detail ───────────────────────────────────────────────────────────
    st.subheader("🗂️ LOI Detail (all permission stages)")
    if view.empty:
        st.info("No LOIs match the current search/filter selection.")
    else:
        opts = view.loi_number.fillna("(no LOI no) " + view.location_desc.fillna(""))
        pick = st.selectbox("LOI", opts, key="comm_pick")
        det = view[view.loi_number == pick]
        if det.empty:
            det = view[view.location_desc.fillna("").eq(pick.replace("(no LOI no) ", ""))]
        if not det.empty:
            st.dataframe(detail_table(det.iloc[0]), hide_index=True,
                         use_container_width=True, height=560)

    # ── Register (bottom of page; Commissioned/Cancelled sink to the end) ──
    st.subheader("📋 LOI Register")
    cols = ["location_sn", "loi_number", "loi_date", "loi_age", "location_desc",
            "loi_holder", "rsa_name", "district", "market_class", "site_type_ab",
            "ro_ksk", "stage", "commissionable", "site_readiness", "io_available",
            "tender_status", "wo_number", "expected_comm_month", "final_status",
            "sap_code"]
    reg = view.assign(_sort=view.stage.map(STAGE_SORT).fillna(99)) \
              .sort_values(["_sort", "loi_date"], ascending=[True, False])
    st.dataframe(reg[cols], hide_index=True, use_container_width=True, height=480)
    df_download(reg[cols], "comm_register")

    # ── Admin: interim edit + monthly upload-replace ───────────────────────
    if st.session_state.get("ingest_auth"):
        st.divider(); st.subheader("🔐 Admin")
        with st.form("loi_edit"):
            st.markdown("**Interim edit (audited)** — bulk changes should go via the monthly Excel upload")
            tgt = st.selectbox("LOI number", sorted(loi.loi_number.dropna().unique()))
            fld = st.selectbox("Field", EDITABLE)
            val = st.text_input("New value")
            if st.form_submit_button("Apply edit"):
                old = loi.loc[loi.loi_number == tgt, fld].iloc[0]
                _edit_write(tgt, fld, old, val)
                st.success(f"{tgt}.{fld}: '{old}' → '{val}' (logged)"); st.rerun()

        st.markdown("**Monthly register upload (replace)**")
        up = st.file_uploader("Upload 'LOI and Commissioning Master Sheet.xlsx'",
                              type=["xlsx"], key="comm_upload")
        if up is not None:
            st.info("Upload received. A pre-replace diff against local edits will be "
                    "shown before replacement. Run the seed script "
                    "(scripts/seed_loi.py pattern) or ask the assistant to process — "
                    "local edits made since the last upload are listed in loi_edit_log:")
            try:
                log = pd.read_sql("SELECT * FROM loi_edit_log ORDER BY edited_at DESC",
                                  sqlite3.connect(DB_PATH))
                st.dataframe(log.head(50), hide_index=True, use_container_width=True)
            except Exception:
                st.caption("No edit log entries.")

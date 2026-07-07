"""Global sidebar — product, period, independent geo filters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import streamlit as st

from core import COM_LABELS, MIDX, MONTHS, QUARTERS, available_months, prev_fy


@dataclass(frozen=True)
class SidebarState:
    product: str
    cy: str
    ly: Optional[str]
    ptype: str
    months: tuple
    period_lbl: str
    multi_fy_mode: bool
    cy_pairs: frozenset
    ly_pairs: frozenset
    sel_dist: tuple
    sel_rsa: tuple
    sel_com: tuple
    sel_hwytype: tuple
    sel_hwyno: tuple
    districts: tuple
    rsa_labels: dict
    coms: tuple
    hwy_nums: tuple


def _clear_sidebar_filters():
    for k in ("sb_dist", "sb_rsa", "sb_com", "sb_hwytype", "sb_hwyno"):
        st.session_state[k] = []


def render_sidebar(ro_master, fys) -> SidebarState:
    """Render global sidebar widgets and return the current filter state."""
    st.sidebar.title("⛽ Pune DO")
    st.sidebar.caption("Market Share Analytics · Layer 6 · monthly")

    product = st.sidebar.radio("Product", ["MS", "HSD"], horizontal=True, key="sb_product")
    cy = st.sidebar.selectbox("Current Year (CY)", fys, index=len(fys) - 1, key="sb_cy")
    ly = prev_fy(cy, fys)

    # Latest ingested month (for data-aware defaults). Falls back to Mar.
    _avail = available_months()
    if _avail:
        _latest = _avail[-1]
        latest_month_name = MONTHS[_latest["month_index"] - 1]
    else:
        latest_month_name = "Mar"

    st.sidebar.markdown("##### Time period")
    ptype = st.sidebar.selectbox(
        "Period type",
        ["Cumulative (Apr → month)", "Full year (Apr–Mar)",
         "Single month", "Quarter", "Custom months", "Custom (multi-FY)"],
        key="sb_ptype")

    multi_fy_mode = False
    cy_pairs: set = set()
    ly_pairs: set = set()

    if ptype == "Full year (Apr–Mar)":
        months = list(range(1, 13))
        period_lbl = "Apr–Mar (full year)"

    elif ptype == "Cumulative (Apr → month)":
        end = st.sidebar.select_slider("Up to month", MONTHS,
                                       value=latest_month_name, key="sb_cum_end")
        months = list(range(1, MIDX[end] + 1))
        period_lbl = f"Apr–{end} (cumulative)"

    elif ptype == "Single month":
        m = st.sidebar.selectbox("Month", MONTHS,
                                 index=MONTHS.index(latest_month_name),
                                 key="sb_single_month")
        months = [MIDX[m]]
        period_lbl = m

    elif ptype == "Quarter":
        q = st.sidebar.selectbox("Quarter", list(QUARTERS), key="sb_quarter")
        months = QUARTERS[q]
        period_lbl = q

    elif ptype == "Custom months":
        picks = st.sidebar.multiselect("Months", MONTHS,
                                       default=[latest_month_name], key="sb_custom_months")
        months = sorted(MIDX[m] for m in picks) or [12]
        period_lbl = ", ".join(m for m in MONTHS if MIDX[m] in months)

    else:
        multi_fy_mode = True
        months = []

        all_mo = available_months()
        label_to_cp = {m["label"]: m["cal_pos"] for m in all_mo}
        cp_to_pair = {m["cal_pos"]: (m["fy_code"], m["month_index"]) for m in all_mo}
        all_labels = [m["label"] for m in all_mo]

        cy_start = int(cy.split("-")[0])
        default_labels = [
            m["label"] for m in all_mo
            if int(m["fy_code"].split("-")[0]) == cy_start
        ]

        picks = st.sidebar.multiselect(
            "Select months (any FY)", all_labels,
            default=default_labels, key="sb_multify_picks")

        if picks:
            cy_cps = {label_to_cp[l] for l in picks}
            ly_cps = {cp - 12 for cp in cy_cps}
            cy_pairs = {cp_to_pair[cp] for cp in cy_cps if cp in cp_to_pair}
            ly_pairs = {cp_to_pair[cp] for cp in ly_cps if cp in cp_to_pair}
            period_lbl = f"{picks[0]} – {picks[-1]}"
        else:
            period_lbl = "no months selected"

    if multi_fy_mode:
        st.sidebar.caption(
            f"Multi-FY · period **{period_lbl}**  ·  LY = same months −1 year")
    else:
        st.sidebar.caption(
            f"CY **{cy}** vs LY **{ly or '—'}** · period **{period_lbl}**")

    st.sidebar.markdown("---")
    st.sidebar.markdown("##### Filters · independent (empty = all)")

    districts = tuple(sorted(ro_master.district.dropna().unique()))
    rsa_pairs = (ro_master[["rsa_code", "rsa_name"]].drop_duplicates()
                 .sort_values("rsa_name"))
    rsa_labels = {f"{r.rsa_name} ({r.rsa_code})": r.rsa_code
                  for r in rsa_pairs.itertuples()}
    coms = ("A", "C", "D1", "D2", "E")
    hwy_nums = tuple(sorted(x for x in ro_master.highway_no.unique() if x))

    user = st.session_state.get("user")
    locked_rsa_str = user.get("sales_area_code") if user else None
    role = user.get("role") if user else None

    locked_rsa = tuple(c.strip() for c in locked_rsa_str.split(",") if c.strip()) if locked_rsa_str else ()

    if role == "dealer":
        st.sidebar.info(f"🔒 Sales Area: {locked_rsa_str or 'All'}")
        sel_dist = ()
        sel_rsa = locked_rsa
        sel_com = ()
        sel_hwytype = ()
        sel_hwyno = ()
    elif locked_rsa:
        st.sidebar.info(f"🔒 Sales Area: {locked_rsa_str}")
        sel_rsa = locked_rsa
        any_filter_active = any(
            st.session_state.get(k) for k in
            ("sb_dist", "sb_com", "sb_hwytype", "sb_hwyno")
        )
        if any_filter_active:
            st.sidebar.button(
                "✕ Clear all filters", on_click=_clear_sidebar_filters,
                key="sb_clear", use_container_width=True)

        sel_dist = tuple(st.sidebar.multiselect("District", districts, key="sb_dist"))
        sel_com = tuple(st.sidebar.multiselect(
            "Class of Market (COM)", coms,
            format_func=lambda c: COM_LABELS[c], key="sb_com"))
        sel_hwytype = tuple(st.sidebar.multiselect(
            "Highway type", ["NH", "SH", "Non-Highway"], key="sb_hwytype"))
        sel_hwyno = tuple(st.sidebar.multiselect(
            "Highway number", hwy_nums, key="sb_hwyno"))
    else:
        any_filter_active = any(
            st.session_state.get(k) for k in
            ("sb_dist", "sb_rsa", "sb_com", "sb_hwytype", "sb_hwyno")
        )
        if any_filter_active:
            st.sidebar.button(
                "✕ Clear all filters", on_click=_clear_sidebar_filters,
                key="sb_clear", use_container_width=True)

        sel_dist = tuple(st.sidebar.multiselect("District", districts, key="sb_dist"))
        sel_rsa_lbl = st.sidebar.multiselect(
            "Sales Area (RSA)", list(rsa_labels), key="sb_rsa")
        sel_rsa = tuple(rsa_labels[l] for l in sel_rsa_lbl)
        sel_com = tuple(st.sidebar.multiselect(
            "Class of Market (COM)", coms,
            format_func=lambda c: COM_LABELS[c], key="sb_com"))
        sel_hwytype = tuple(st.sidebar.multiselect(
            "Highway type", ["NH", "SH", "Non-Highway"], key="sb_hwytype"))
        sel_hwyno = tuple(st.sidebar.multiselect(
            "Highway number", hwy_nums, key="sb_hwyno"))


    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Dashboard v3.0 · navigation shell\n\n"
        "Nil Selling + YTS + Action Plans (v2.2)\n\n"
        "XtraPower fleet-card analytics (v2.3)\n\n"
        "Finder & Reports (v2.4)\n\n"
        "Cross-FY period selector (v2.5)\n\n"
        "RO Benchmarking vs TA leader (v2.6)\n\n"
        "Tier-2 (MoU, Dhruva, NRO, Daily MIS) pending data.")

    return SidebarState(
        product=product,
        cy=cy,
        ly=ly,
        ptype=ptype,
        months=tuple(months),
        period_lbl=period_lbl,
        multi_fy_mode=multi_fy_mode,
        cy_pairs=frozenset(cy_pairs),
        ly_pairs=frozenset(ly_pairs),
        sel_dist=sel_dist,
        sel_rsa=sel_rsa,
        sel_com=sel_com,
        sel_hwytype=sel_hwytype,
        sel_hwyno=sel_hwyno,
        districts=districts,
        rsa_labels=rsa_labels,
        coms=coms,
        hwy_nums=hwy_nums,
    )

"""Tab 21 — REMM / Rent-Payment & Lease Monitoring (A-site ROs).

Governance (REMM_Data_Governance_Rules.docx):
- Lease status S0–S8 is COMPUTED at every load, never stored.
- S1/S2/S3 records raise an alert banner on entry.
- Govt-landlord rows (S7) shown separately from date-based urgency.
- FLAG (vendor incomplete) / PENDING (no agreement) / OWN semantics respected.
Default view = current month; drill-down district → sales area.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st
from components.downloads import df_download

from core import indian, load_remm, load_remm_payments, load_ro_master, remm_status

S_COLORS = {"S0": "#57606a", "S1": "#cf222e", "S2": "#e5531a", "S3": "#f79009",
            "S4": "#eac54f", "S5": "#54aeff", "S6": "#2da44e", "S7": "#8250df",
            "S8": "#8c8c8c"}


def render(ctx):
    remm = load_remm()
    pays = load_remm_payments()
    if remm.empty:
        st.info("REMM master not loaded."); return
    ro_master = ctx["ro_master"]

    # computed status + district enrichment
    stat = remm.apply(lambda r: remm_status(r), axis=1)
    remm = remm.assign(status_code=[t[0] for t in stat],
                       status_label=[t[1] for t in stat])
    dist_map = ro_master.set_index("sap_code")["district"].to_dict()
    remm["district"] = remm["rdb_code"].map(dist_map)

    # ── Alert banner (S1/S2/S3 on every load) ──────────────────────────────
    urgent = remm[remm.status_code.isin(["S1", "S2", "S3"])]
    chips = []
    order = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S0"]
    for sc in order:
        sub = remm[remm.status_code == sc]
        if sub.empty and sc not in ("S1", "S2", "S3"):
            continue
        dim = "opacity:.35;" if sub.empty else ""
        lbl = sub.status_label.iloc[0] if not sub.empty else \
              {"S1": "Expired", "S2": "Emergency (<90d)", "S3": "Critical (<1 yr)"}[sc]
        chips.append(f'<span style="{dim}display:inline-block;margin:2px 6px 2px 0;'
                     f'padding:6px 14px;border-radius:16px;background:{S_COLORS[sc]};'
                     f'color:#fff;font-weight:600;font-size:0.9rem;">'
                     f'{sc} {lbl}: {len(sub)}</span>')
    st.markdown("".join(chips), unsafe_allow_html=True)
    if not urgent.empty:
        with st.expander(f"🔔 {len(urgent)} lease(s) need action (Expired / Emergency / Critical)",
                         expanded=True):
            v = urgent[["remm_id", "rdb_code", "ro_name", "rsa_name", "status_label",
                        "lease_validity", "vendor_name", "action_plan"]]
            st.dataframe(v, hide_index=True, use_container_width=True)
            df_download(v, "remm_urgent")

    # ── Filters (in-tab: status/RSA drill only; geo comes from sidebar rule) ──
    c1, c2, c3 = st.columns(3)
    with c1:
        f_dist = st.selectbox("District", ["All"] + sorted(remm.district.dropna().unique()),
                              key="remm_dist")
    with c2:
        pool = remm if f_dist == "All" else remm[remm.district == f_dist]
        f_rsa = st.selectbox("Sales Area", ["All"] + sorted(pool.rsa_name.dropna().unique()),
                             key="remm_rsa")
    with c3:
        f_stat = st.selectbox("Status", ["All"] + order, key="remm_stat")
    view = remm.copy()
    if f_dist != "All": view = view[view.district == f_dist]
    if f_rsa != "All":  view = view[view.rsa_name == f_rsa]
    if f_stat != "All": view = view[view.status_code == f_stat]

    # ── KPI row ────────────────────────────────────────────────────────────
    lp = pays.groupby("remm_id").amount.sum()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Leases in scope", len(view))
    _rent = view["revised_rent"].fillna(view["initial_rent"]).fillna(0)
    c2.metric("Active rent (Rs/mo, current base)", indian(_rent.sum()))
    c3.metric("FY 2025-26 rent paid (Rs)",
              indian(lp.reindex(view.remm_id).fillna(0).sum()))
    c4.metric("Govt-landlord rows (separate channel)",
              len(view[view.status_code == "S7"]))

    # ── Master table ───────────────────────────────────────────────────────
    st.subheader("📋 REMM Register")
    show = view[["remm_id", "rdb_code", "ro_name", "rsa_name", "district", "com",
                 "land_class", "status_code", "status_label", "lease_from",
                 "lease_validity", "lease_area_sqft", "initial_rent", "revised_rent",
                 "vendor_name", "mutation",
                 "action_plan", "action_taken", "target_date"]].copy()
    show = show.sort_values("status_code")
    st.dataframe(show.style.format({"initial_rent": lambda v: indian(v),
                                    "revised_rent": lambda v: indian(v),
                                    "lease_area_sqft": lambda v: indian(v)},
                                   na_rep="—"),
                 hide_index=True, use_container_width=True, height=520)
    df_download(show, "remm_register")

    # ── Payments drill ─────────────────────────────────────────────────────
    with st.expander("💰 Monthly rent payments (FY 2025-26)"):
        if pays.empty:
            st.info("No payment rows loaded.")
        else:
            pm = pays[pays.remm_id.isin(view.remm_id)]
            piv = (pm.pivot_table(index="remm_id", columns="month_index",
                                  values="amount", aggfunc="sum")
                     .reindex(columns=range(1, 13)))
            piv.columns = ["Apr", "May", "Jun", "Jul", "Aug", "Sep",
                           "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
            piv["Total"] = piv.sum(axis=1)
            meta = view.set_index("remm_id")[["ro_name", "rsa_name"]]
            piv = meta.join(piv, how="right")
            st.dataframe(piv, use_container_width=True)
            df_download(piv.reset_index(), "remm_payments")

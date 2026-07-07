"""Tab 24 — Alternate Fuels (CNG / CBG sales; EVCS process-monitoring later).

Sales in kg (monthly, Apr'22 →). EVCS and the alt-fuel commissioning-process
module await the officer's tracker file.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st
from components.downloads import df_download

from core import MONTHS, indian, load_alt_fuel, load_alt_fuel_master


def render(ctx):
    master = load_alt_fuel_master()
    fact = load_alt_fuel()
    if master.empty:
        st.info("Alternate-fuel master not loaded."); return

    ftype = st.radio("Fuel", ["CNG", "CBG"], horizontal=True, key="af_type")
    m = master[master.fuel_type == ftype]
    f = fact[fact.fuel_type == ftype]

    cy, ly = ctx["cy"], ctx["ly"]
    months = ctx["months"]
    f_cy = f[(f.fy_code == cy) & (f.month_index.isin(months))]
    f_ly = f[(f.fy_code == ly) & (f.month_index.isin(months))] if ly else f.iloc[0:0]
    if f_cy.empty:
        fys_avail = sorted(f.fy_code.unique())
        if fys_avail:
            cy = fys_avail[-1]; ly = fys_avail[-2] if len(fys_avail) > 1 else None
            f_cy = f[f.fy_code == cy]; f_ly = f[f.fy_code == ly] if ly else f.iloc[0:0]
            st.caption(f"⚠️ No {ftype} rows for the sidebar period — showing FY {cy}.")

    v_cy, v_ly = f_cy.qty_kg.sum(), f_ly.qty_kg.sum()
    gr = (v_cy - v_ly) / v_ly * 100 if v_ly else None
    # nil-selling stations: commissioned but zero in last 3 data months
    mm = f.groupby(["fy_code", "month_index"]).qty_kg.sum().reset_index()
    mm = mm.sort_values(["fy_code", "month_index"])
    last3 = mm.tail(3)[["fy_code", "month_index"]].apply(tuple, axis=1).tolist()
    f["key"] = list(zip(f.fy_code, f.month_index))
    recent = f[f.key.isin(last3)]
    selling = set(recent[recent.qty_kg > 0].sap_code)
    nil_st = m[~m.sap_code.isin(selling)]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"{ftype} stations", len(m))
    c2.metric(f"CY {cy} sales (kg)", indian(v_cy))
    c3.metric("Growth %", f"{gr:+.1f}%" if gr is not None else "—")
    c4.metric("Nil-selling (last 3 mo)", len(nil_st))
    if len(nil_st):
        with st.expander(f"🚫 {len(nil_st)} station(s) with no {ftype} sales in the last 3 data months"):
            st.dataframe(nil_st[["sap_code", "ro_name", "rsa_name", "cgd_company",
                                 "comm_year", "corpus_flag"]],
                         hide_index=True, use_container_width=True)

    # ── Trend ──────────────────────────────────────────────────────────────
    st.subheader("📈 Monthly trend (kg)")
    mm["label"] = mm.apply(lambda r: f"{r.fy_code[:4]}-{r.month_index:02d} "
                                     f"{MONTHS[r.month_index-1]}", axis=1)
    ch = (alt.Chart(mm).mark_line(point=True).encode(
        x=alt.X("label:N", sort=None, title="Month"),
        y=alt.Y("qty_kg:Q", title="kg"),
        tooltip=["fy_code", "month_index", alt.Tooltip("qty_kg:Q", format=",")]
    ).properties(height=260))
    st.altair_chart(ch, use_container_width=True)

    # ── Station master + performance ───────────────────────────────────────
    st.subheader("🏭 Station-wise")
    s_cy = f_cy.groupby("sap_code").qty_kg.sum()
    s_ly = f_ly.groupby("sap_code").qty_kg.sum()
    tab = m.set_index("sap_code")[["ro_name", "rsa_name", "district", "site_type",
                                   "com", "comm_year", "sales_start_date",
                                   "cgd_company", "corpus_flag"]]
    tab["CY (kg)"] = s_cy; tab["LY (kg)"] = s_ly
    tab = tab.fillna({"CY (kg)": 0, "LY (kg)": 0})
    tab["+/- (kg)"] = tab["CY (kg)"] - tab["LY (kg)"]
    tab = tab.sort_values("CY (kg)", ascending=False).reset_index()
    st.dataframe(tab.style.format({"CY (kg)": lambda v: indian(v),
                                   "LY (kg)": lambda v: indian(v),
                                   "+/- (kg)": lambda v: indian(v)}, na_rep="—"),
                 hide_index=True, use_container_width=True, height=520)
    df_download(tab, f"alt_fuel_{ftype.lower()}")

    st.caption("EVCS and the CNG/CBG commissioning-process module will be added "
               "when the office tracker file is shared (pending).")

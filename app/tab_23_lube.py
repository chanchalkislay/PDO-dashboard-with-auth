"""Tab 23 — Lube Sales MIS (IOCL-only; manual monthly updates).

Products: 4T, Others, DEF (litres). 'Total' is always computed, never stored.
Data loaded Apr 2022 → latest; no industry comparison exists for lubes.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st
from components.downloads import df_download

from core import MONTHS, indian, load_lube


def render(ctx):
    lube = load_lube()
    if lube.empty:
        st.info("Lube data not loaded."); return

    prods = ["All", "4T", "Others", "DEF"]
    c1, c2 = st.columns([1, 3])
    with c1:
        prod = st.radio("Product", prods, horizontal=True, key="lube_prod")
    d = lube if prod == "All" else lube[lube["product"] == prod]

    cy, ly = ctx["cy"], ctx["ly"]
    months = ctx["months"]
    d_cy = d[(d.fy_code == cy) & (d.month_index.isin(months))]
    d_ly = d[(d.fy_code == ly) & (d.month_index.isin(months))] if ly else d.iloc[0:0]
    # fall back to latest FY with data if selection is empty
    if d_cy.empty:
        fys_avail = sorted(d.fy_code.unique())
        cy = fys_avail[-1]; ly = fys_avail[-2] if len(fys_avail) > 1 else None
        d_cy = d[d.fy_code == cy]; d_ly = d[d.fy_code == ly] if ly else d.iloc[0:0]
        st.caption(f"⚠️ No lube rows for the sidebar period — showing FY {cy} full-year.")

    v_cy, v_ly = d_cy.qty_l.sum(), d_ly.qty_l.sum()
    gr = (v_cy - v_ly) / v_ly * 100 if v_ly else None
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"CY {cy} volume (L)", indian(v_cy))
    c2.metric(f"LY {ly or '—'} volume (L)", indian(v_ly))
    c3.metric("Growth %", f"{gr:+.1f}%" if gr is not None else "—")
    c4.metric("Selling ROs (CY)", d_cy[d_cy.qty_l > 0].sap_code.nunique())

    # ── Trend chart (all history) ──────────────────────────────────────────
    st.subheader("📈 Monthly trend")
    tr = (d.groupby(["fy_code", "month_index"]).qty_l.sum().reset_index())
    tr["label"] = tr.apply(lambda r: f"{r.fy_code[:4]}-{r.month_index:02d} "
                                     f"{MONTHS[r.month_index-1]}", axis=1)
    tr = tr.sort_values(["fy_code", "month_index"])
    ch = (alt.Chart(tr).mark_line(point=True).encode(
        x=alt.X("label:N", sort=None, title="Month"),
        y=alt.Y("qty_l:Q", title="Litres"),
        tooltip=["fy_code", "month_index", alt.Tooltip("qty_l:Q", format=",")]
    ).properties(height=260))
    st.altair_chart(ch, use_container_width=True)

    # ── District / RSA summary ─────────────────────────────────────────────
    st.subheader("🗺️ District & RSA summary")
    lvl = st.radio("Level", ["District", "RSA"], horizontal=True, key="lube_lvl")
    key = "district" if lvl == "District" else "rsa_name"
    g_cy = d_cy.groupby(key).qty_l.sum().rename(f"CY (L)")
    g_ly = d_ly.groupby(key).qty_l.sum().rename(f"LY (L)")
    summ = pd.concat([g_cy, g_ly], axis=1).fillna(0.0)
    summ["+/- (L)"] = summ["CY (L)"] - summ["LY (L)"]
    summ["%GR"] = (summ["+/- (L)"] / summ["LY (L)"].replace(0, pd.NA) * 100)
    summ = summ.sort_values("CY (L)", ascending=False).reset_index()
    st.dataframe(summ.style.format({"CY (L)": lambda v: indian(v),
                                    "LY (L)": lambda v: indian(v),
                                    "+/- (L)": lambda v: indian(v),
                                    "%GR": "{:+.1f}%"}, na_rep="—"),
                 hide_index=True, use_container_width=True)
    df_download(summ, "lube_summary")

    # ── RO table ───────────────────────────────────────────────────────────
    st.subheader("⛽ RO-wise (CY vs LY)")
    r_cy = d_cy.groupby(["sap_code", "ro_name", "rsa_name", "district"]).qty_l.sum()
    r_ly = d_ly.groupby(["sap_code", "ro_name", "rsa_name", "district"]).qty_l.sum()
    ro = pd.concat([r_cy.rename("CY (L)"), r_ly.rename("LY (L)")], axis=1).fillna(0.0)
    ro["+/- (L)"] = ro["CY (L)"] - ro["LY (L)"]
    ro = ro.sort_values("CY (L)", ascending=False).reset_index()
    st.dataframe(ro.style.format({"CY (L)": lambda v: indian(v),
                                  "LY (L)": lambda v: indian(v),
                                  "+/- (L)": lambda v: indian(v)}),
                 hide_index=True, use_container_width=True, height=480)
    df_download(ro, "lube_ro_wise")

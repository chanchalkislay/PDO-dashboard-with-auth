"""Tab 2 — Market Share by RSA / District / COM / Highway type."""
import streamlit as st
from components.downloads import df_download
import pandas as pd
import altair as alt
from core import (share_frame, indian, pct, fmt_pp, fmt_notional, style_growth,
                  OMC_ORDER, OMC_COLORS, PSU, COM_LABELS)


def render(ctx):
    cy_f       = ctx["cy_f"]
    ly_f       = ctx["ly_f"]
    product    = ctx["product"]
    cy         = ctx["cy"]
    ly         = ctx["ly"]
    period_lbl = ctx["period_lbl"]

    cden, clev = st.columns(2)
    universe = cden.radio("Denominator", ["Industry", "PSU"], horizontal=True,
                          key="ms_univ")
    uset = OMC_ORDER if universe == "Industry" else PSU
    level = clev.radio("Break down by",
                       ["RSA", "District", "COM", "Highway type"],
                       horizontal=True, key="ms_lvl")
    gcol = {"RSA": "rsa_name", "District": "district",
            "COM": "com", "Highway type": "hwy_type"}[level]

    sf = share_frame(cy_f, ly_f, [gcol], uset)
    disp = pd.DataFrame({level: sf[gcol]})
    for omc in uset:
        disp[f"{omc} %"] = sf[f"{omc}_cyshare"].apply(pct)
    disp["IOCL +/- pp"]   = sf["IOCL_ppt"]
    disp["IOCL Vol (KL)"] = sf["IOCL_cyvol"].apply(lambda x: indian(x, 1))
    disp["Notional (KL)"] = sf["IOCL_notional"]
    if level == "COM":
        disp[level] = disp[level].map(lambda c: COM_LABELS.get(c, c))

    st.markdown(f"#### {product} {universe} share by {level} — {cy} vs {ly}")
    growth_cols = ["IOCL +/- pp", "Notional (KL)"]
    styled = (style_growth(disp, growth_cols)
              .format({
                  "IOCL +/- pp":   fmt_pp,
                  "Notional (KL)": lambda x: fmt_notional(x, 1),
              }))
    st.dataframe(styled, hide_index=True, use_container_width=True)
    df_download(styled, "t02_1")

    bar_df = pd.DataFrame({level: sf[gcol], "IOCL": sf["IOCL_cyshare"]})
    _avg = bar_df["IOCL"].mean()
    bar = alt.Chart(bar_df).mark_bar().encode(
        x=alt.X("IOCL:Q", title="IOCL share %"),
        y=alt.Y(f"{level}:N", sort="-x"),
        color=alt.condition(alt.datum.IOCL >= _avg,
                            alt.value(OMC_COLORS["IOCL"]),
                            alt.value("#F9C49A")),
        tooltip=[level, alt.Tooltip("IOCL:Q", format=".2f")]
    ).properties(height=28 * len(bar_df) + 40,
                 title=f"IOCL {universe} {product} share by {level}")
    st.altair_chart(bar, use_container_width=True)

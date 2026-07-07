"""Tab 9 — Notional Loss / Gain: by RSA and top TA movers."""
import streamlit as st
from components.downloads import df_download
import pandas as pd
import altair as alt
from core import (share_frame, indian, pct,
                  fmt_pp, fmt_notional, style_growth, OMC_ORDER, PSU)


def render(ctx):
    cy_f       = ctx["cy_f"]
    ly_f       = ctx["ly_f"]
    product    = ctx["product"]
    cy         = ctx["cy"]
    ly         = ctx["ly"]
    period_lbl = ctx["period_lbl"]
    TA_NAME    = ctx["TA_NAME"]

    if not ly:
        st.warning(
            f"Notional loss/gain for **{cy}** cannot be computed — "
            f"the database does not contain data prior to **{cy}**, "
            f"so there is no prior-year share to compare against. "
            f"Please select a later year.")
        return

    universe = st.radio("Denominator", ["Industry", "PSU"], horizontal=True,
                        key="nl_univ")
    uset = OMC_ORDER if universe == "Industry" else PSU
    st.markdown("#### IOCL notional volume by RSA")
    sf = share_frame(cy_f, ly_f, ["rsa_name"], uset).sort_values("IOCL_notional")

    disp = pd.DataFrame({
        "RSA":           sf["rsa_name"],
        "CY Share %":    sf["IOCL_cyshare"].apply(pct),
        "LY Share %":    sf["IOCL_lyshare"].apply(pct),
        "+/- pp":        sf["IOCL_ppt"],
        "Notional (KL)": sf["IOCL_notional"],
    })
    growth_cols = ["+/- pp", "Notional (KL)"]
    styled = (style_growth(disp, growth_cols)
              .format({
                  "+/- pp":        fmt_pp,
                  "Notional (KL)": lambda x: fmt_notional(x, 1),
              }))
    st.dataframe(styled, hide_index=True, use_container_width=True)
    df_download(styled, "t09_1")

    nl  = pd.DataFrame({"RSA": sf["rsa_name"], "Notional": sf["IOCL_notional"]})
    bar = alt.Chart(nl).mark_bar().encode(
        x=alt.X("Notional:Q"), y=alt.Y("RSA:N", sort="x"),
        color=alt.condition(alt.datum.Notional >= 0,
                            alt.value("#2da44e"), alt.value("#cf222e")),
        tooltip=["RSA", alt.Tooltip("Notional:Q", format=",.0f")]
    ).properties(height=28 * len(nl) + 40, title="IOCL notional volume by RSA")
    st.altair_chart(bar, use_container_width=True)

    st.markdown("#### IOCL TA-level notional — top movers")
    taf = share_frame(cy_f, ly_f, ["ta_code", "rsa_name"], uset)
    taf = taf[(taf["cy_tot"] > 0) | (taf["ly_tot"] > 0)]
    taf["Name"] = taf["ta_code"].map(TA_NAME)
    c1, c2 = st.columns(2)
    for col, asc, title in [(c1, False, "Top gainers"), (c2, True, "Top losers")]:
        d = taf.sort_values("IOCL_notional", ascending=asc).head(15)
        t = pd.DataFrame({
            "TA":            d["ta_code"],
            "Name":          d["Name"],
            "RSA":           d["rsa_name"],
            "Notional (KL)": d["IOCL_notional"],
        })
        styled = (style_growth(t, ["Notional (KL)"])
                  .format({"Notional (KL)": lambda x: fmt_notional(x, 1)}))
        col.markdown(f"**{title}**")
        col.dataframe(styled, hide_index=True, use_container_width=True)

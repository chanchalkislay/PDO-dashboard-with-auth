"""Tab 6 — TA Rankings: top gainers / losers by any of four metrics."""
import streamlit as st
import pandas as pd
from core import (share_frame, indian, pct, fmt_pp, fmt_notional, style_growth,
                  OMC_ORDER, PSU, COM_LABELS)


def render(ctx):
    cy_f       = ctx["cy_f"]
    ly_f       = ctx["ly_f"]
    product    = ctx["product"]
    period_lbl = ctx["period_lbl"]
    TA_NAME    = ctx["TA_NAME"]

    st.markdown("#### Trading-Area rankings")
    c1, c2, c3 = st.columns(3)
    universe = c1.radio("Denominator", ["Industry", "PSU"], horizontal=True,
                        key="rk_univ")
    uset         = OMC_ORDER if universe == "Industry" else PSU
    group_within = c2.selectbox(
        "Rank within", ["Whole DO", "District", "RSA", "COM", "Highway type"])
    metric       = c3.selectbox("Metric", [
        "Notional (KL)", "Share growth (pp)", "CY volume (KL)",
        "Volume growth (KL)"])
    metric_col = {"Notional (KL)":      "IOCL_notional",
                  "Share growth (pp)":  "IOCL_ppt",
                  "CY volume (KL)":     "IOCL_cyvol",
                  "Volume growth (KL)": "IOCL_diffvol"}[metric]
    grp_col = {"Whole DO": None, "District": "district", "RSA": "rsa_name",
               "COM": "com", "Highway type": "hwy_type"}[group_within]

    base_cols = ["ta_code", "rsa_name"] + ([grp_col] if grp_col and grp_col not in
                                           ("rsa_name",) else [])
    base_cols = list(dict.fromkeys(base_cols))
    sf = share_frame(cy_f, ly_f, base_cols, uset)
    sf["TA Name"] = sf["ta_code"].map(TA_NAME)
    n = st.slider("Top N", 5, 30, 15)

    is_growth_metric = metric in ("Notional (KL)", "Share growth (pp)",
                                  "Volume growth (KL)")

    def _render_group(d, container):
        cc1, cc2 = container.columns(2)
        top = d.sort_values(metric_col, ascending=False).head(n)
        bot = d.sort_values(metric_col, ascending=True).head(n)
        for col, dd, title in [(cc1, top, "Top gainers"), (cc2, bot, "Top losers")]:
            t = pd.DataFrame({
                "TA":      dd["ta_code"],
                "Name":    dd["TA Name"],
                "RSA":     dd["rsa_name"],
                "CY Vol":  dd["IOCL_cyvol"].apply(lambda x: indian(x, 1)),
                "Share %": dd["IOCL_cyshare"].apply(pct),
                metric:    dd[metric_col],
            })
            if is_growth_metric:
                fmt_fn = (fmt_pp if metric == "Share growth (pp)"
                          else lambda x: fmt_notional(x, 1))
                styled = style_growth(t, [metric]).format({metric: fmt_fn})
            else:
                styled = t.style.format({metric: lambda x: indian(x, 1)})
            col.markdown(f"**{title}**")
            col.dataframe(styled, hide_index=True, use_container_width=True)

    if grp_col is None:
        _render_group(sf, st)
    else:
        for gval in sorted(sf[grp_col].dropna().unique()):
            lbl = COM_LABELS.get(gval, gval) if group_within == "COM" else gval
            with st.expander(f"{group_within}: {lbl}"):
                _render_group(sf[sf[grp_col] == gval], st)

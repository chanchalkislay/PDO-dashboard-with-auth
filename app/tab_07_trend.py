"""Tab 7 — Market Share Trend (configurable scope, FY range, product and OMC view).

Scope filters are fully independent of the sidebar — the user narrows the
universe (RSA / District / COM / Highway) and the trend is computed for that
scope only.  Period (months) still follows the sidebar selection so every FY
is compared on a like-for-like basis.
"""
import streamlit as st
from components.downloads import df_download
import pandas as pd
import altair as alt
from core import _pivot, pct, pp, OMC_ORDER, OMC_COLORS, PSU, COM_LABELS


def render(ctx):
    monthly    = ctx["monthly"]       # full unfiltered data — tab applies own scope
    fys        = ctx["fys"]
    months     = ctx["months"]        # sidebar period months applied across all FYs
    period_lbl = ctx["period_lbl"]
    rsa_labels = ctx["rsa_labels"]

    st.subheader("Market Share Trend")
    st.caption(
        f"Each selected FY uses the same sidebar period: **{period_lbl}**  ·  "
        "Scope filters below are independent of the sidebar."
    )

    # ── Controls ──────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    tr_prod  = c1.radio("Product",     ["MS", "HSD", "Both"], horizontal=True,
                        key="tr_prod")
    universe = c2.radio("Denominator", ["Industry", "PSU"],   horizontal=True,
                        key="tr_univ")
    omc_mode = c3.radio("OMC view",    ["IOCL only", "All OMCs"], horizontal=True,
                        key="tr_omc")

    sel_fys = st.multiselect(
        "Financial Years to show", fys, default=fys, key="tr_fys")
    if not sel_fys:
        sel_fys = fys

    uset         = OMC_ORDER if universe == "Industry" else PSU
    display_omcs = ["IOCL"] if omc_mode == "IOCL only" else uset

    # ── Scope filters (independent of sidebar) ────────────────────────────────
    st.markdown("**Scope** — narrow the universe (empty = whole DO)")
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    f_rsa_lbl = sc1.multiselect("RSA",         list(rsa_labels),
                                key="tr_rsa")
    f_dist    = sc2.multiselect("District",     ctx["districts"],
                                key="tr_dist")
    f_com     = sc3.multiselect("COM",          ctx["coms"],
                                format_func=lambda c: COM_LABELS[c],
                                key="tr_com")
    f_hwytype = sc4.multiselect("Highway type", ["NH", "SH", "Non-Highway"],
                                key="tr_hwytype")
    f_hwyno   = sc5.multiselect("Highway no.",  ctx["hwy_nums"],
                                key="tr_hwyno")
    f_rsa = [rsa_labels[l] for l in f_rsa_lbl]

    # ── Filter ────────────────────────────────────────────────────────────────
    base = monthly
    if f_rsa:     base = base[base.rsa_code.isin(f_rsa)]
    if f_dist:    base = base[base.district.isin(f_dist)]
    if f_com:     base = base[base.com.isin(f_com)]
    if f_hwytype: base = base[base.hwy_type.isin(f_hwytype)]
    if f_hwyno:   base = base[base.highway_no.isin(f_hwyno)]

    prod_list = ["MS", "HSD"] if tr_prod == "Both" else [tr_prod]
    base = base[
        base["product"].isin(prod_list) &
        base.fy_code.isin(sel_fys) &
        base.month_index.isin(months)
    ]

    if base.empty:
        st.warning("No data for the selected scope / FYs.")
        return

    # ── Compute shares ────────────────────────────────────────────────────────
    piv = _pivot(base, ["fy_code"], uset)
    tot = piv.sum(axis=1)
    recs = []
    for fy in sorted(piv.index):
        for omc in display_omcs:
            vol = piv.loc[fy, omc] if omc in piv.columns else 0.0
            recs.append(dict(
                FY=fy, OMC=omc, Volume=vol,
                Share=(vol / tot[fy] * 100 if tot[fy] else 0.0)
            ))
    tr = pd.DataFrame(recs)

    # ── KPI cards ─────────────────────────────────────────────────────────────
    iocl_rows = tr[tr.OMC == "IOCL"].sort_values("FY")
    if not iocl_rows.empty:
        k1, k2, k3 = st.columns(3)
        k1.metric(f"IOCL share {iocl_rows.FY.iloc[0]}",
                  pct(iocl_rows.Share.iloc[0]))
        k2.metric(f"IOCL share {iocl_rows.FY.iloc[-1]}",
                  pct(iocl_rows.Share.iloc[-1]))
        k3.metric("Movement",
                  pp(iocl_rows.Share.iloc[-1] - iocl_rows.Share.iloc[0]) + " pp")

    # ── Chart ─────────────────────────────────────────────────────────────────
    prod_lbl = "MS + HSD" if tr_prod == "Both" else tr_prod
    _clrs = [OMC_COLORS[o] for o in display_omcs]
    chart = (
        alt.Chart(tr)
        .mark_line(point=True)
        .encode(
            x=alt.X("FY:N", title="Financial Year"),
            y=alt.Y("Share:Q", title=f"{universe} share %"),
            color=alt.Color(
                "OMC:N",
                scale=alt.Scale(domain=display_omcs, range=_clrs),
                sort=display_omcs),
            tooltip=[
                "FY", "OMC",
                alt.Tooltip("Share:Q",  format=".2f",   title="Share %"),
                alt.Tooltip("Volume:Q", format=",.0f",  title="Vol (KL)"),
            ]
        )
        .properties(height=340,
                    title=f"{prod_lbl} {universe} share trend · {period_lbl}")
    )
    st.altair_chart(chart, use_container_width=True)

    # ── Summary table ─────────────────────────────────────────────────────────
    pv = (
        tr.pivot(index="OMC", columns="FY", values="Share")
          .reindex(display_omcs)
          .reindex(columns=sorted(sel_fys))
    )
    st.dataframe(
        pv.map(lambda x: pct(x) if pd.notna(x) else "—"),
        use_container_width=True,
    )
    df_download(pv.map(lambda x: pct(x) if pd.notna(x) else "—"), "t07_1")

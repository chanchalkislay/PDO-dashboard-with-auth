"""Tab 4 — Trading-Area Analysis: participation + share + loss/gain per TA."""
import streamlit as st
from components.downloads import df_download
import pandas as pd
from core import (share_frame, participation, indian, pct,
                  fmt_pp, fmt_notional, style_growth, OMC_ORDER, PSU)


# ── TA Type classification (Rules 66–72) ─────────────────────────────────────
_TA_TYPE_ORDER = ["IOCL Absent", "IOCL Monopoly", "IOCL Dominated",
                  "OMC Dominated", "Error"]


def _classify_ta(iocl_ros, total_ros, iocl_share_pct, iocl_partic_pct):
    """Classify a single TA per Rules 66-72."""
    if total_ros == 0:
        return "Error"
    if iocl_ros == 0:
        return "IOCL Absent"
    if iocl_ros >= total_ros:          # IOCL present, all others = 0
        return "IOCL Monopoly"
    # Both IOCL and other OMCs present
    if iocl_share_pct > iocl_partic_pct:
        return "IOCL Dominated"
    return "OMC Dominated"


def _ta_type_series(ta_codes, ta_dim, ro_master, scope, ta_type_prod,
                    cy, months, multi_fy_mode, cy_pairs):
    """
    Compute TA Type string for each ta_code in ta_codes.

    RO counts:
      MS/HSD  → dim_ta product-specific columns
      Combined → participation(ro_master, ...) unique count across all products

    Volume (share) source: geo-filtered scope, CY period, TA Type product.
    """
    ta_idx = ta_dim.set_index("ta_code")

    # ── RO counts ────────────────────────────────────────────────────────────
    if ta_type_prod == "MS":
        iocl_ros  = ta_idx["cnt_iocl_ms"].fillna(0).astype(int)
        total_ros = ta_idx["total_ros_ms"].fillna(0).astype(int)
    elif ta_type_prod == "HSD":
        iocl_ros  = ta_idx["cnt_iocl_hsd"].fillna(0).astype(int)
        total_ros = ta_idx["total_ros_hsd"].fillna(0).astype(int)
    else:  # Combined — unique RO count from unfiltered master
        part = participation(ro_master, ["ta_code"]).set_index("ta_code")
        iocl_ros  = part["IOCL"].fillna(0).astype(int)
        total_ros = part["Total"].fillna(0).astype(int)

    # ── CY volume slice for TA Type product ──────────────────────────────────
    prod_list = ["MS", "HSD"] if ta_type_prod == "Combined" else [ta_type_prod]
    if multi_fy_mode and cy_pairs:
        fymi = scope.fy_code + "_" + scope.month_index.astype(str)
        keys = {f"{fy}_{mi}" for fy, mi in cy_pairs}
        tt_cy = scope[fymi.isin(keys) & scope["product"].isin(prod_list)]
    elif not multi_fy_mode:
        tt_cy = scope[(scope.fy_code == cy) & scope.month_index.isin(months)
                      & scope["product"].isin(prod_list)]
    else:
        tt_cy = scope.iloc[0:0]   # multi-FY but no pairs selected

    iocl_vol  = (tt_cy[tt_cy["omc"] == "IOCL"]
                 .groupby("ta_code")["volume_kl"].sum())
    total_vol = (tt_cy[tt_cy["omc"].isin(OMC_ORDER)]
                 .groupby("ta_code")["volume_kl"].sum()
                 .replace(0, float("nan")))
    iocl_share = (iocl_vol / total_vol * 100).fillna(0)

    # ── Classify each TA ─────────────────────────────────────────────────────
    results = {}
    for ta in ta_codes:
        ir  = int(iocl_ros.get(ta, 0))
        tr  = int(total_ros.get(ta, 0))
        ish = float(iocl_share.get(ta, 0.0))
        ip  = (ir / tr * 100) if tr > 0 else 0.0
        results[ta] = _classify_ta(ir, tr, ish, ip)

    return pd.Series(results, name="TA Type")


def render(ctx):
    cy_f       = ctx["cy_f"]
    ly_f       = ctx["ly_f"]
    ro_scope   = ctx["ro_scope"]
    ro_master  = ctx["ro_master"]
    scope      = ctx["scope"]
    ta_dim     = ctx["ta_dim"]
    product    = ctx["product"]
    cy         = ctx["cy"]
    ly         = ctx["ly"]
    months     = ctx["months"]
    period_lbl = ctx["period_lbl"]
    TA_NAME    = ctx["TA_NAME"]
    multi_fy_mode = ctx["multi_fy_mode"]
    cy_pairs      = ctx["cy_pairs"]

    st.markdown(f"#### Trading-Area analysis — {product}, {cy} vs {ly}, {period_lbl}")

    # ── Controls ──────────────────────────────────────────────────────────────
    c1, c2 = st.columns([2, 3])
    universe = c1.radio("Denominator", ["Industry", "PSU"], horizontal=True,
                        key="ta_univ")
    ta_type_prod = c2.radio(
        "TA Type product (independent)",
        ["MS", "HSD", "Combined"], horizontal=True, key="ta_type_prod")

    # ── Share frame (uses sidebar product / period) ───────────────────────────
    uset = OMC_ORDER if universe == "Industry" else PSU
    sf   = share_frame(cy_f, ly_f, ["ta_code", "rsa_name"], uset)
    part = participation(ro_scope, ["ta_code"]).set_index("ta_code")

    ta_codes = sf["ta_code"].tolist()

    # ── TA Type classification ────────────────────────────────────────────────
    tt = _ta_type_series(
        ta_codes, ta_dim, ro_master, scope, ta_type_prod,
        cy, months, multi_fy_mode, cy_pairs)

    # ── Build display DataFrame ───────────────────────────────────────────────
    g = pd.DataFrame({
        "TA Code":       sf["ta_code"],
        "TA Name":       sf["ta_code"].map(TA_NAME),
        "RSA":           sf["rsa_name"],
        "TA Type":       sf["ta_code"].map(tt),
        "IOCL ROs":      sf["ta_code"].map(part["IOCL"]).fillna(0).astype(int),
        "Total ROs":     sf["ta_code"].map(part["Total"]).fillna(0).astype(int),
        "IOCL Vol (KL)": sf["IOCL_cyvol"],
        "Mkt Vol (KL)":  sf["cy_tot"],
        "IOCL Share %":  sf["IOCL_cyshare"],
        "+/- pp":        sf["IOCL_ppt"],
        "Notional (KL)": sf["IOCL_notional"],
    })

    # ── TA Type summary ───────────────────────────────────────────────────────
    tt_counts = g["TA Type"].value_counts()
    summary_parts = [
        f"{t}: **{tt_counts.get(t, 0)}**"
        for t in _TA_TYPE_ORDER
        if tt_counts.get(t, 0) > 0
    ]
    st.caption("TA Type distribution (" + ta_type_prod + ")  ·  "
               + "  |  ".join(summary_parts))

    # ── Filters ───────────────────────────────────────────────────────────────
    f1, f2 = st.columns([3, 2])
    q = f1.text_input("Filter by TA name / code", "")
    tt_opts   = ["All"] + [t for t in _TA_TYPE_ORDER if tt_counts.get(t, 0) > 0]
    tt_filter = f2.selectbox("Filter by TA Type", tt_opts, key="ta_type_filt")

    if q:
        s = q.lower()
        g = g[g["TA Name"].fillna("").str.lower().str.contains(s)
              | g["TA Code"].str.lower().str.contains(s)]
    if tt_filter != "All":
        g = g[g["TA Type"] == tt_filter]

    sort_by = st.selectbox("Sort by", ["Notional (KL)", "IOCL Share %",
                                       "+/- pp", "IOCL Vol (KL)", "Mkt Vol (KL)"])
    g = g.sort_values(sort_by, ascending=False)
    st.caption(f"{len(g)} trading areas in scope")

    # ── Styled table ──────────────────────────────────────────────────────────
    growth_cols = ["+/- pp", "Notional (KL)"]
    styled = (style_growth(g, growth_cols)
              .format({
                  "IOCL Vol (KL)": lambda x: indian(x, 1),
                  "Mkt Vol (KL)":  lambda x: indian(x, 1),
                  "IOCL Share %":  pct,
                  "+/- pp":        fmt_pp,
                  "Notional (KL)": lambda x: fmt_notional(x, 1),
              }))
    st.dataframe(styled, hide_index=True, use_container_width=True, height=480)
    df_download(styled, "t04_1")

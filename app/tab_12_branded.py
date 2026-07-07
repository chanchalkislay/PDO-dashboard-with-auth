"""Tab 12 — Branded analytics (KLPM · Conversion % · CY vs LY).

Brands ingested:
  MS  — IOCL XP95, IOCL XP100, BPCL Speed, HPCL Power
  HSD — IOCL XG (XtraGreen) [pending ingestion]

IOCL MS has two brands (XP95 and XP100).  A toggle lets the user view
XP95 only, XP100 only, or Both combined.  Other OMCs have one brand each.

Metrics:
  KLPM       = branded KL ÷ months in period ÷ ROs with that branded facility
               (Rule #194/#196 — RO count = distinct ROs with any positive uplift
               in full history within current geographic scope)
  Conversion = branded KL ÷ mother product KL × 100
               (mother from fact_monthly, frozen)
  CY vs LY   = same month-index set in the previous FY

Drill-down: District · RSA · COM · Highway/NH · Trading Area · Retail Outlet,
combinable for cross-tab.
"""
import streamlit as st
from components.downloads import df_download
import pandas as pd
import altair as alt
from core import (indian, pct, pp, klpm,
                  BRANDED_MASTER, BRANDED_PSU, IOCL_MS_BRANDS, COM_LABELS)

LEVEL_MAP = {
    "District":      "district",
    "RSA":           "rsa_name",
    "COM":           "com",
    "Highway / NH":  "hwy_type",
    "Trading Area":  "ta_code",
    "Retail Outlet": "ro_name",
}
_COL_LABEL = {
    "district": "District", "rsa_name": "RSA", "com": "COM",
    "hwy_type": "Highway / NH", "ta_code": "Trading Area", "ro_name": "Retail Outlet",
}


def render(ctx):
    product       = ctx["product"]
    cy            = ctx["cy"]
    ly            = ctx["ly"]
    period_lbl    = ctx["period_lbl"]
    n_months      = max(len(ctx["months"]), 1)
    b_cy          = ctx["b_cy"]
    b_ly          = ctx["b_ly"]
    cy_f          = ctx["cy_f"]
    ly_f          = ctx["ly_f"]
    TA_NAME       = ctx["TA_NAME"]
    branded_scope = ctx["branded_scope"]   # geo-filtered, ALL periods — for RO count

    st.markdown(f"#### Branded {product} analytics — {cy} vs {ly} · {period_lbl}")
    st.caption(
        "**KLPM** = branded KL ÷ months in period ÷ ROs with that branded facility "
        "(any positive uplift in full history, within current geographic scope — Rule #196).  "
        f"**Conversion** = branded ÷ mother {product} × 100 "
        "(mother volumes from fact_monthly, frozen)."
    )

    if b_cy.empty and b_ly.empty:
        st.info(
            f"No branded **{product}** data found for the current selection.  "
            "For MS: XP95, XP100 (IOCL), Speed (BPCL), Power (HPCL) are loaded.  "
            "Branded HSD (XG) is pending ingestion."
        )
        return

    # OMCs that have a branded name for this product
    omcs = [o for o in BRANDED_PSU if BRANDED_MASTER.get((o, product))]

    # ── Volume helpers ────────────────────────────────────────────────────────
    def _vol_brands(frame, omc, brands):
        """Sum volume for an OMC filtered to specific brand(s)."""
        return float(
            frame[(frame.omc == omc) & (frame.brand.isin(brands))]["volume_kl"].sum()
        )

    def _vol_omc(frame, omc):
        """Total (all-brand) volume for an OMC — used for mother MS/HSD."""
        return float(frame[frame.omc == omc]["volume_kl"].sum())

    def _n_ros(scope_df, omc, brands):
        """Distinct ROs with any positive uplift for given brand(s), geo-filtered (Rule #196)."""
        return int(
            scope_df[
                (scope_df.omc == omc)
                & (scope_df.brand.isin(brands))
                & (scope_df.volume_kl > 0)
            ]["sap_code"].nunique()
        ) or 1

    # ── Focus OMC selector ────────────────────────────────────────────────────
    def _focus_label(o):
        if o == "IOCL" and product == "MS":
            return "IOCL — XP95 / XP100"
        return f"{o} — {BRANDED_MASTER.get((o, product), '')}"

    focus = st.selectbox("Focus OMC", omcs, index=0,
                         format_func=_focus_label, key="brand_focus")

    # ── Brand toggle (IOCL MS only) ───────────────────────────────────────────
    if focus == "IOCL" and product == "MS":
        brand_sel = st.radio(
            "Brand view", ["XP95", "XP100", "Both"],
            horizontal=True, key="brand_iocl_toggle",
            help="XP95 and XP100 are both branded MS products.  "
                 "'Both' shows combined volume and conversion.")
        brands_active = IOCL_MS_BRANDS if brand_sel == "Both" else [brand_sel]
        brand_label   = "XP95 / XP100" if brand_sel == "Both" else brand_sel
    else:
        brand_sel     = BRANDED_MASTER[(focus, product)]
        brands_active = [brand_sel]
        brand_label   = brand_sel

    # ── KPI cards ─────────────────────────────────────────────────────────────
    bcy_t = _vol_brands(b_cy, focus, brands_active)
    bly_t = _vol_brands(b_ly, focus, brands_active)
    mcy_t = _vol_omc(cy_f, focus)
    mly_t = _vol_omc(ly_f, focus)

    n_ros_kpi = _n_ros(branded_scope, focus, brands_active)
    klpm_cy   = klpm(bcy_t, n_months, n_ros_kpi)
    klpm_ly   = klpm(bly_t, n_months, n_ros_kpi)
    conv_cy   = (bcy_t / mcy_t * 100) if mcy_t else 0.0
    conv_ly   = (bly_t / mly_t * 100) if mly_t else 0.0
    vol_gr    = ((bcy_t - bly_t) / bly_t * 100) if bly_t else None

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"{brand_label} KLPM (CY)", indian(klpm_cy, 2),
              delta=f"{indian(klpm_cy - klpm_ly, 2)} vs LY")
    k2.metric("Conversion % (CY)", pct(conv_cy),
              delta=f"{pp(conv_cy - conv_ly)} pp vs LY")
    k3.metric(f"{brand_label} volume CY (KL)", indian(bcy_t, 1),
              delta=(f"{pct(vol_gr)} vs LY" if vol_gr is not None else "— vs LY"))
    k4.metric(f"{brand_label} ROs (facility count)", indian(n_ros_kpi),
              help="ROs with any positive uplift for the selected brand(s) "
                   "in full history (geo-filter applied). Denominator for KLPM.")

    # ── Summary table — one row per brand (XP95 and XP100 separate) ──────────
    st.markdown("##### Branded summary — current selection (whole DO unless filtered)")

    # Build (omc, brand) pairs for all brands with data
    summary_brands = []
    for o in omcs:
        if o == "IOCL" and product == "MS":
            for b in IOCL_MS_BRANDS:
                # Only show the row if this brand has any data in the DB
                if not branded_scope[(branded_scope.omc == o)
                                     & (branded_scope.brand == b)].empty:
                    summary_brands.append((o, b))
        else:
            b = BRANDED_MASTER.get((o, product))
            if b:
                summary_brands.append((o, b))

    sum_rows = []
    for o, b in summary_brands:
        bc = float(b_cy[(b_cy.omc == o) & (b_cy.brand == b)]["volume_kl"].sum())
        bl = float(b_ly[(b_ly.omc == o) & (b_ly.brand == b)]["volume_kl"].sum())
        mc = _vol_omc(cy_f, o)
        ml = _vol_omc(ly_f, o)
        cc = (bc / mc * 100) if mc else 0.0
        cl = (bl / ml * 100) if ml else 0.0
        gr = ((bc - bl) / bl * 100) if bl else None
        n_ros_o = _n_ros(branded_scope, o, [b])
        sum_rows.append({
            "OMC":             o,
            "Brand":           b,
            "Branded CY (KL)": indian(bc, 1),
            "KLPM CY":         indian(klpm(bc, n_months, n_ros_o), 2),
            "Conv % CY":       pct(cc),
            "Branded LY (KL)": indian(bl, 1),
            "KLPM LY":         indian(klpm(bl, n_months, n_ros_o), 2),
            "Conv % LY":       pct(cl),
            "KL Gr %":         pct(gr) if gr is not None else "—",
            "Conv +/- pp":     pp(cc - cl),
            "Branded ROs":     indian(n_ros_o),
        })

    # If IOCL MS and "Both", also add a combined row
    if focus == "IOCL" and product == "MS" and brand_sel == "Both":
        bc_all = _vol_brands(b_cy, "IOCL", IOCL_MS_BRANDS)
        bl_all = _vol_brands(b_ly, "IOCL", IOCL_MS_BRANDS)
        mc     = _vol_omc(cy_f, "IOCL")
        ml     = _vol_omc(ly_f, "IOCL")
        cc_all = (bc_all / mc * 100) if mc else 0.0
        cl_all = (bl_all / ml * 100) if ml else 0.0
        gr_all = ((bc_all - bl_all) / bl_all * 100) if bl_all else None
        n_both = _n_ros(branded_scope, "IOCL", IOCL_MS_BRANDS)
        sum_rows.insert(0, {
            "OMC":             "IOCL",
            "Brand":           "XP95 + XP100",
            "Branded CY (KL)": indian(bc_all, 1),
            "KLPM CY":         indian(klpm(bc_all, n_months, n_both), 2),
            "Conv % CY":       pct(cc_all),
            "Branded LY (KL)": indian(bl_all, 1),
            "KLPM LY":         indian(klpm(bl_all, n_months, n_both), 2),
            "Conv % LY":       pct(cl_all),
            "KL Gr %":         pct(gr_all) if gr_all is not None else "—",
            "Conv +/- pp":     pp(cc_all - cl_all),
            "Branded ROs":     indian(n_both),
        })

    st.dataframe(pd.DataFrame(sum_rows), hide_index=True, use_container_width=True)
    df_download(pd.DataFrame(sum_rows), "t12_1")

    # ── Drill-down (partial rerun) ────────────────────────────────────────────
    _render_drill_down(
        focus, product, brand_sel, brand_label, brands_active,
        b_cy, b_ly, cy_f, ly_f, branded_scope, n_months, TA_NAME,
    )


@st.fragment
def _render_drill_down(
    focus, product, brand_sel, brand_label, brands_active,
    b_cy, b_ly, cy_f, ly_f, branded_scope, n_months, TA_NAME,
):
    st.markdown("---")
    drill_header = (f"IOCL ({brand_label})"
                    if focus == "IOCL" and product == "MS"
                    else f"{focus} ({brand_label})")
    st.markdown(f"##### Drill-down — {drill_header}")

    def _clear_brand_drill():
        st.session_state["brand_level"] = ["RSA"]
        for k in ("bfilt_com", "bfilt_hwy_type", "bfilt_rsa_name", "bfilt_district"):
            if k in st.session_state:
                st.session_state[k] = []

    d1, d2, d3 = st.columns([3, 1, 1])
    levels_sel = d1.multiselect(
        "Break down by  (pick one or combine for cross-tab)",
        list(LEVEL_MAP.keys()), default=["RSA"], key="brand_level",
        help=("Select multiple dimensions to cross-tab them.  "
              "E.g. RSA + COM → one row per RSA × COM combination.  "
              "Tip: XP95/XP100 → try COM or RSA + COM.  "
              "XG → try Highway / NH or RSA + Highway / NH."),
    )
    only_active = d2.checkbox("Only areas with branded sales", value=True,
                              key="brand_active")
    _drill_non_default = (levels_sel != ["RSA"]) or any(
        st.session_state.get(k)
        for k in ("bfilt_com", "bfilt_hwy_type", "bfilt_rsa_name", "bfilt_district")
    )
    if _drill_non_default:
        d3.markdown('<div style="margin-top:1.7rem"></div>', unsafe_allow_html=True)
        d3.button("✕ Clear drill-down", on_click=_clear_brand_drill,
                  key="brand_clear_drill", use_container_width=True)

    if not levels_sel:
        st.info("Select at least one drill-down dimension.")
        return

    gcols = [LEVEL_MAP[l] for l in levels_sel]

    # Filter widgets — options built from focus OMC + active brands
    b_foc = b_cy[(b_cy.omc == focus) & (b_cy.brand.isin(brands_active))]

    def _opts(col):
        return sorted(b_foc[col].dropna().unique().tolist()) if col in b_foc.columns else []

    filter_specs = [
        ("com",      "Filter COM",         _opts("com")),
        ("hwy_type", "Filter Highway / NH", _opts("hwy_type")),
    ]
    if "rsa_name" in gcols:
        filter_specs.append(("rsa_name", "Filter RSA", _opts("rsa_name")))
    if "district" in gcols:
        filter_specs.append(("district", "Filter District", _opts("district")))

    filt_vals = {}
    if filter_specs:
        fcols = st.columns(len(filter_specs))
        for i, (col, lbl, opts) in enumerate(filter_specs):
            chosen = fcols[i].multiselect(lbl, opts, default=[], key=f"bfilt_{col}")
            if chosen:
                filt_vals[col] = chosen

    # Slice helpers — apply brand filter + drill-down geo filters
    def _slice_branded(frame, omc, brands):
        f = frame[(frame.omc == omc) & (frame.brand.isin(brands))].copy()
        for col, vals in filt_vals.items():
            if col in f.columns:
                f = f[f[col].isin(vals)]
        return f

    def _slice_mother(frame, omc):
        f = frame[frame.omc == omc].copy()
        for col, vals in filt_vals.items():
            if col in f.columns:
                f = f[f[col].isin(vals)]
        return f

    b_cy_d  = _slice_branded(b_cy,          focus, brands_active)
    b_ly_d  = _slice_branded(b_ly,          focus, brands_active)
    b_all_d = _slice_branded(branded_scope,  focus, brands_active)
    cy_d    = _slice_mother(cy_f,  focus)
    ly_d    = _slice_mother(ly_f,  focus)

    # Group by selected dimensions
    def _grp(frame):
        if frame.empty:
            # Return empty Series with properly-named index so that
            # index.union() with non-empty results preserves the level names.
            idx = (pd.MultiIndex.from_tuples([], names=gcols)
                   if len(gcols) > 1
                   else pd.Index([], name=gcols[0]))
            return pd.Series(dtype=float, index=idx)
        return frame.groupby(gcols)["volume_kl"].sum()

    bcy_g = _grp(b_cy_d)
    bly_g = _grp(b_ly_d)
    mcy_g = _grp(cy_d)
    mly_g = _grp(ly_d)

    idx = (bcy_g.index.union(bly_g.index)
                      .union(mcy_g.index)
                      .union(mly_g.index))
    if len(idx) == 0:
        st.info("No data for the current selection / filters.")
        return

    bcy_g = bcy_g.reindex(idx, fill_value=0.0)
    bly_g = bly_g.reindex(idx, fill_value=0.0)
    mcy_g = mcy_g.reindex(idx, fill_value=0.0)
    mly_g = mly_g.reindex(idx, fill_value=0.0)

    conv_cy_g = (bcy_g / mcy_g.where(mcy_g > 0) * 100).fillna(0.0)
    conv_ly_g = (bly_g / mly_g.where(mly_g > 0) * 100).fillna(0.0)
    gr_g      = ((bcy_g - bly_g) / bly_g.where(bly_g > 0) * 100)

    # Per-group branded RO count (Rule #196)
    if not b_all_d.empty and all(c in b_all_d.columns for c in gcols):
        _ros_df = (b_all_d[b_all_d.volume_kl > 0]
                   .groupby(gcols)["sap_code"].nunique())
    else:
        _ros_df = pd.Series(dtype=int)
    _ros_g    = _ros_df.reindex(idx, fill_value=0).clip(lower=1)
    klpm_cy_g = bcy_g / n_months / _ros_g
    klpm_ly_g = bly_g / n_months / _ros_g

    tbl = pd.DataFrame({
        "Branded CY (KL)": bcy_g.values,
        "_bly":            bly_g.values,
        "KLPM CY":         klpm_cy_g.values,
        "KLPM LY":         klpm_ly_g.values,
        "Branded ROs":     _ros_g.values,
        "Conv % CY":       conv_cy_g.values,
        "Conv % LY":       conv_ly_g.values,
        "Conv +/- pp":     (conv_cy_g - conv_ly_g).values,
        "KL Gr %":         gr_g.values,
        "Mother CY (KL)":  mcy_g.values,
    }, index=idx)

    tbl = tbl.reset_index()
    if len(gcols) == 1:
        tbl = tbl.rename(columns={gcols[0]: _COL_LABEL[gcols[0]]})
    else:
        for i, col in enumerate(gcols):
            old = f"level_{i}" if f"level_{i}" in tbl.columns else col
            tbl = tbl.rename(columns={old: _COL_LABEL[col]})

    dim_cols = [_COL_LABEL[c] for c in gcols]

    if "COM" in tbl.columns:
        tbl["COM"] = tbl["COM"].map(lambda c: COM_LABELS.get(c, c))
    if "Trading Area" in tbl.columns:
        tbl["Trading Area"] = tbl["Trading Area"].apply(
            lambda c: f"{c} — {TA_NAME.get(c, '')}".strip(" —"))

    if only_active:
        tbl = tbl[(tbl["Branded CY (KL)"] > 0) | (tbl["_bly"] > 0)]
    tbl = tbl.drop(columns="_bly")

    if tbl.empty:
        st.info("No branded sales at this level for the current selection.")
        return

    tbl = tbl.sort_values("Branded CY (KL)", ascending=False).reset_index(drop=True)

    disp = tbl.copy()
    disp["Branded CY (KL)"] = disp["Branded CY (KL)"].apply(lambda x: indian(x, 1))
    disp["KLPM CY"]         = disp["KLPM CY"].apply(lambda x: indian(x, 2))
    disp["KLPM LY"]         = disp["KLPM LY"].apply(lambda x: indian(x, 2))
    disp["Branded ROs"]     = disp["Branded ROs"].apply(lambda x: indian(int(x)))
    disp["Mother CY (KL)"]  = disp["Mother CY (KL)"].apply(lambda x: indian(x, 1))
    disp["Conv % CY"]       = disp["Conv % CY"].apply(pct)
    disp["Conv % LY"]       = disp["Conv % LY"].apply(pct)
    disp["Conv +/- pp"]     = disp["Conv +/- pp"].apply(pp)
    disp["KL Gr %"]         = disp["KL Gr %"].apply(
        lambda x: pct(x) if pd.notna(x) else "—")
    st.dataframe(disp, hide_index=True, use_container_width=True)
    df_download(disp, "t12_2")

    # Conversion bar chart — top 15 by Conv % CY
    tbl["_label"] = tbl[dim_cols].apply(
        lambda r: " — ".join(str(v) for v in r if pd.notna(v) and str(v).strip()), axis=1)
    chart_df = (tbl[tbl["Branded CY (KL)"] > 0]
                .nlargest(15, "Conv % CY")
                [["_label", "Conv % CY", "Branded CY (KL)"]])
    if not chart_df.empty:
        dim_label = " × ".join(levels_sel)
        bar = alt.Chart(chart_df).mark_bar(color="#e8731c").encode(
            x=alt.X("Conv % CY:Q", title="Conversion % (CY)"),
            y=alt.Y("_label:N", sort="-x", title=dim_label),
            tooltip=[
                alt.Tooltip("_label:N",              title=dim_label),
                alt.Tooltip("Conv % CY:Q",           format=".2f",  title="Conv % CY"),
                alt.Tooltip("Branded CY (KL):Q",     format=",.1f", title="Branded KL"),
            ],
        ).properties(
            height=max(26 * len(chart_df) + 40, 120),
            title=f"Top {brand_label} conversion by {dim_label} (CY)")
        st.altair_chart(bar, use_container_width=True)

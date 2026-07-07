"""Tab 3 — Market Participation & Network Effectiveness.

Metrics per OMC, per geographic group:
  No of ROs      — outlet count (product-specific from dim_ta for MS/HSD;
                   total from dim_ro when product = Both or geo = COM/Highway)
  MP %           — outlet share within selected universe (Industry or PSU)
  MS %           — volume share within selected universe
  NE             — Network Effectiveness = MS % ÷ MP %
                   > 1 → green (outperforming network strength)
                   < 1 → red   (underperforming)
                   ≈ 1 → black (in line with network strength)
"""

import streamlit as st
from components.downloads import df_download
import pandas as pd
import altair as alt
from core import OMC_ORDER, PSU, COM_LABELS, OMC_COLORS, load_ta_dim


# ── Independent scope filters (same pattern as tab_14_finder) ─────────────────

def _apply_ne_scope(df, f_rsa, f_dist, f_com, f_hwytype, f_hwyno, f_ta):
    """Apply Tab-3-local scope filters to a frame with standard columns."""
    m = pd.Series(True, index=df.index)
    if f_rsa:     m &= df["rsa_code"].isin(f_rsa)
    if f_dist:    m &= df["district"].isin(f_dist)
    if f_com:     m &= df["com"].isin(f_com)
    if f_hwytype: m &= df["hwy_type"].isin(f_hwytype)
    if f_hwyno:   m &= df["highway_no"].isin(f_hwyno)
    if f_ta:      m &= df["ta_code"].isin(f_ta)
    return df[m]


def _ne_scope_widgets(ctx):
    """Render scope-filter multiselects for Tab 3 — two rows of three.
    Key prefix 'ne3' avoids collisions with sidebar (sb_*) and other tabs.
    Returns (f_rsa_codes, f_dist, f_com, f_hwytype, f_hwyno, f_ta_codes)."""
    rsa_labels = ctx["rsa_labels"]   # dict: display label → rsa_code

    # Build TA label→code dict sorted by name
    ta_name_s = ctx["TA_NAME"]       # Series: ta_code → ta_name_canonical
    ta_labels = {f"{name} ({code})": code
                 for code, name in ta_name_s.sort_values().items()}

    # Row 1: geographic groupings
    c1, c2, c3 = st.columns(3)
    sel_rsa_lbl = c1.multiselect("RSA",      list(rsa_labels), key="ne3_rsa")
    sel_dist    = c2.multiselect("District", ctx["districts"], key="ne3_dist")
    sel_com     = c3.multiselect("COM",      ctx["coms"],
                                  format_func=lambda c: COM_LABELS.get(c, c),
                                  key="ne3_com")

    # Row 2: highway + trading area
    c4, c5, c6 = st.columns(3)
    sel_hwytype = c4.multiselect("Highway type", ["NH", "SH", "Non-Highway"],
                                  key="ne3_hwytype")
    sel_hwyno   = c5.multiselect("Highway no.",  ctx["hwy_nums"], key="ne3_hwyno")
    sel_ta_lbl  = c6.multiselect("Trading Area", list(ta_labels), key="ne3_ta")

    return (
        [rsa_labels[l] for l in sel_rsa_lbl],
        sel_dist, sel_com, sel_hwytype, sel_hwyno,
        [ta_labels[l] for l in sel_ta_lbl],
    )

_NE_TOL = 0.005          # |NE − 1.0| ≤ this → rendered black (floating-point equality band)
_NE_GREEN = "#1a7f37"
_NE_RED   = "#cf222e"
_NE_BLACK = "#1a1a1a"


# ── Styling helpers ───────────────────────────────────────────────────────────

def _ne_css(v):
    """Pandas Styler .map() function for the NE column.
    Receives the display string ('1.10', '0.87', '—') and returns CSS."""
    try:
        f = float(v)
    except (ValueError, TypeError):
        return ""
    if abs(f - 1.0) <= _NE_TOL:
        return f"color:{_NE_BLACK};font-weight:700"
    return (f"color:{_NE_GREEN};font-weight:700" if f > 1.0
            else f"color:{_NE_RED};font-weight:700")


def _total_row_css(row, geo_label):
    """Highlight the ★ TOTAL row."""
    if row[geo_label] == "★ TOTAL":
        return ["font-weight:700;background-color:#e8e8e8"] * len(row)
    return [""] * len(row)


# ── Outlet-count helpers ──────────────────────────────────────────────────────

def _counts_from_ta(product_sel, geo_level, geo_col, ta_scope):
    """Product-specific outlet counts from dim_ta (MS → cnt_*_ms, HSD → cnt_*_hsd).

    Returns wide DataFrame: index = geo group label, columns = OMC names (integers).
    Valid only when product_sel ∈ {MS, HSD} and geo_level ∈ {Whole DO, RSA, District, Trading Area}.
    """
    suffix  = "_ms" if product_sel == "MS" else "_hsd"
    col_map = {omc: f"cnt_{omc.lower()}{suffix}" for omc in OMC_ORDER}
    avail   = {omc: c for omc, c in col_map.items() if c in ta_scope.columns}

    if not avail or ta_scope.empty:
        df = pd.DataFrame(columns=list(avail.keys()))
        df.index.name = geo_col or "Scope"
        return df

    ta_cols = list(avail.values())

    if geo_level == "Whole DO":
        row = {omc: int(ta_scope[c].sum()) for omc, c in avail.items()}
        df  = pd.DataFrame([row])
        df.index = pd.Index(["Total DO"], name="Scope")
        return df

    grp = ta_scope.groupby(geo_col)[ta_cols].sum().astype(int)
    grp.columns = pd.Index(list(avail.keys()))
    return grp   # index = geo_col values


def _counts_from_ro(geo_level, geo_col, scope_ro):
    """Total outlet counts from dim_ro (product-agnostic).

    Used for product = Both, and always for COM / Highway type levels.
    Returns wide DataFrame: index = geo group label, columns = OMC names (integers).
    """
    if scope_ro.empty:
        df = pd.DataFrame(columns=OMC_ORDER)
        df.index.name = geo_col or "Scope"
        return df

    if geo_level == "Whole DO":
        s = (scope_ro.groupby("omc")["sap_code"].nunique()
             .reindex(OMC_ORDER, fill_value=0).astype(int))
        df = pd.DataFrame([s.to_dict()])
        df.index = pd.Index(["Total DO"], name="Scope")
        return df

    p = (scope_ro.groupby([geo_col, "omc"])["sap_code"].nunique()
         .unstack("omc")
         .reindex(columns=OMC_ORDER, fill_value=0)
         .fillna(0).astype(int))
    return p   # index = geo_col values


# ── Volume helper ─────────────────────────────────────────────────────────────

def _vols_wide(product_sel, geo_level, geo_col, cy_period, universe_omcs):
    """CY volumes per geographic group per OMC.

    cy_period — period-filtered monthly frame (CY FY + selected months), ALL products.
    Returns wide DataFrame: index = geo group, columns = OMC names (floats).
    """
    if product_sel == "MS":
        src = cy_period[cy_period["product"] == "MS"]
    elif product_sel == "HSD":
        src = cy_period[cy_period["product"] == "HSD"]
    else:
        src = cy_period      # Both: sum MS + HSD

    src = src[src["omc"].isin(universe_omcs)]

    if src.empty or geo_level == "Whole DO":
        if src.empty:
            df = pd.DataFrame([{o: 0.0 for o in universe_omcs}])
        else:
            s = (src.groupby("omc")["volume_kl"].sum()
                 .reindex(universe_omcs, fill_value=0.0))
            df = pd.DataFrame([s.to_dict()])
        df.index = pd.Index(["Total DO"], name="Scope")
        return df

    p = (src.groupby([geo_col, "omc"])["volume_kl"].sum()
         .unstack("omc")
         .reindex(columns=universe_omcs, fill_value=0.0)
         .fillna(0.0))
    return p


# ── NE row builder ────────────────────────────────────────────────────────────

def _ne_rows(counts_wide, vols_wide, universe_omcs, geo_label):
    """Merge wide count + volume tables → list of NE row dicts.

    Both inputs have the same index (geo group values) and OMC columns.
    """
    if counts_wide.empty and vols_wide.empty:
        return []

    all_groups = (counts_wide.index.union(vols_wide.index)
                  if not counts_wide.empty
                  else vols_wide.index)

    rows = []
    for grp in all_groups:
        cnt = (counts_wide.loc[grp].reindex(OMC_ORDER, fill_value=0)
               if (not counts_wide.empty and grp in counts_wide.index)
               else pd.Series(0, index=OMC_ORDER))
        vol = (vols_wide.loc[grp].reindex(universe_omcs, fill_value=0.0)
               if (not vols_wide.empty and grp in vols_wide.index)
               else pd.Series(0.0, index=universe_omcs))

        total_ros = sum(int(cnt.get(o, 0)) for o in universe_omcs)
        total_vol = sum(float(vol.get(o, 0.0)) for o in universe_omcs)

        for omc in universe_omcs:
            n  = int(cnt.get(omc, 0))
            v  = float(vol.get(omc, 0.0))
            mp = (n / total_ros * 100) if total_ros > 0 else 0.0
            ms = (v / total_vol * 100) if total_vol > 0 else 0.0
            ne = (ms / mp) if mp > 1e-9 else None
            rows.append({
                geo_label:   grp,
                "OMC":       omc,
                "No of ROs": n,
                "MP %":      round(mp, 2),
                "MS %":      round(ms, 2),
                "_ne_raw":   ne,
                "NE":        f"{ne:.2f}" if ne is not None else "—",
            })
    return rows


# ── Main render ───────────────────────────────────────────────────────────────

def render(ctx):
    ro_scope  = ctx["ro_scope"]
    scope     = ctx["scope"]          # geo-filtered, ALL periods, ALL products
    cy        = ctx["cy"]
    months    = ctx["months"]
    TA_NAME   = ctx["TA_NAME"]
    ro_master = ctx["ro_master"]      # unfiltered RO master (for RSA code→name map)
    ta_dim    = load_ta_dim()

    # RSA code → display name mapping (use dim_ro names — "Pune City RSA" etc.)
    # dim_ta uses short names ("Pune City"); dim_ro uses full names ("Pune City RSA").
    # We group by rsa_code (consistent across both sources) and display dim_ro names.
    rsa_code_to_name = ro_master.groupby("rsa_code")["rsa_name"].first().to_dict()

    # Period-filtered frame that is NOT pre-filtered by product
    # (cy_f in ctx is already product-filtered by the sidebar selector — we need all products
    #  here so the tab's own MS/HSD/Both selector can slice independently)
    cy_period = scope[(scope["fy_code"] == cy) & scope["month_index"].isin(months)]

    st.caption(
        "MP% = outlet share within universe  ·  "
        "MS% = volume share within universe  ·  "
        "NE = MS% ÷ MP%  |  "
        "**Green** NE > 1 — outperforming network strength  ·  "
        "**Red** NE < 1 — underperforming"
    )

    # ── Controls ──────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1, 1, 3])
    product_sel  = c1.radio("Product", ["MS", "HSD", "Both"],
                             horizontal=True, key="ne_prod")
    universe_sel = c2.radio("Denominator", ["Industry", "PSU only"],
                             horizontal=True, key="ne_univ")
    geo_sel      = c3.radio(
        "Group by",
        ["Whole DO", "RSA", "District", "COM", "Highway type", "Trading Area"],
        horizontal=True, key="ne_geo",
    )

    universe_omcs = PSU if universe_sel == "PSU only" else OMC_ORDER

    # ── Tab-local scope filters (on top of sidebar) ───────────────────────────
    st.caption("Scope filters — narrow the universe further (empty = full sidebar scope)")
    f_rsa, f_dist, f_com, f_hwytype, f_hwyno, f_ta = _ne_scope_widgets(ctx)

    # Apply PSU filter first, then tab-local scope filters
    scope_ro = (ro_scope[ro_scope["omc"].isin(PSU)].copy()
                if universe_sel == "PSU only" else ro_scope.copy())
    scope_ro = _apply_ne_scope(scope_ro, f_rsa, f_dist, f_com, f_hwytype, f_hwyno, f_ta)

    # Apply same scope to the CY period volume frame
    cy_period = _apply_ne_scope(cy_period, f_rsa, f_dist, f_com, f_hwytype, f_hwyno, f_ta)

    if scope_ro.empty:
        st.info("No outlets match the selected scope filters.")
        return

    # Scope dim_ta to TAs that contain at least one RO in the narrowed scope
    scope_tas = set(scope_ro["ta_code"].dropna())
    ta_scope  = ta_dim[ta_dim["ta_code"].isin(scope_tas)].copy()

    # ── Geographic column mapping ─────────────────────────────────────────────
    # RSA uses rsa_code internally (consistent across dim_ta and monthly/dim_ro).
    # Display names are applied after row-building via rsa_code_to_name.
    geo_col_map = {
        "Whole DO":     None,
        "RSA":          "rsa_code",   # ← code, not name; mapped to display name later
        "District":     "district",
        "COM":          "com",
        "Highway type": "hwy_type",
        "Trading Area": "ta_code",
    }
    geo_col   = geo_col_map[geo_sel]
    geo_label = geo_sel if geo_sel != "Whole DO" else "Scope"

    # ── Outlet counts ─────────────────────────────────────────────────────────
    # dim_ta provides product-specific counts (cnt_*_ms / cnt_*_hsd) and is the
    # preferred source when geo groups map to dim_ta columns (RSA/District/TA/Whole DO).
    # For COM and Highway type, or when product = Both, use dim_ro (product-agnostic).
    use_ta_counts = (
        product_sel != "Both"
        and geo_sel in ("Whole DO", "RSA", "District", "Trading Area")
    )

    counts_wide = (
        _counts_from_ta(product_sel, geo_sel, geo_col, ta_scope)
        if use_ta_counts
        else _counts_from_ro(geo_sel, geo_col, scope_ro)
    )

    # ── Volumes ───────────────────────────────────────────────────────────────
    vols = _vols_wide(product_sel, geo_sel, geo_col, cy_period, universe_omcs)

    # ── Build NE detail rows ──────────────────────────────────────────────────
    detail_rows = _ne_rows(counts_wide, vols, universe_omcs, geo_label)
    if not detail_rows:
        st.info("No data for the selected combination.")
        return

    detail_df = pd.DataFrame(detail_rows)

    # ── RSA code → display name ────────────────────────────────────────────────
    # Replace rsa_code values with full rsa_name (e.g. "M06" → "Pune City RSA")
    if geo_sel == "RSA":
        detail_df[geo_label] = detail_df[geo_label].map(
            lambda c: rsa_code_to_name.get(c, c))

    # ── COM label enrichment ───────────────────────────────────────────────────
    if geo_sel == "COM":
        detail_df[geo_label] = detail_df[geo_label].map(
            lambda c: COM_LABELS.get(c, c))

    # ── TA name column ─────────────────────────────────────────────────────────
    if geo_sel == "Trading Area":
        detail_df.insert(1, "TA Name",
                         detail_df[geo_label].map(lambda c: TA_NAME.get(c, c)))

    # ── Totals row (aggregate across all groups) ──────────────────────────────
    # For Whole DO, the detail IS the total — skip an extra row.
    if geo_sel != "Whole DO":
        safe_cnt = counts_wide.reindex(columns=universe_omcs, fill_value=0) \
                   if not counts_wide.empty else pd.DataFrame(columns=universe_omcs)
        safe_vol = vols.reindex(columns=universe_omcs, fill_value=0.0) \
                   if not vols.empty else pd.DataFrame(columns=universe_omcs)

        agg_cnt = safe_cnt.sum()
        agg_vol = safe_vol.sum()
        all_ros = int(agg_cnt.sum())
        all_vol = float(agg_vol.sum())

        total_rows = []
        for omc in universe_omcs:
            n  = int(agg_cnt.get(omc, 0))
            v  = float(agg_vol.get(omc, 0.0))
            mp = (n / all_ros * 100) if all_ros > 0 else 0.0
            ms = (v / all_vol * 100) if all_vol > 0 else 0.0
            ne = (ms / mp) if mp > 1e-9 else None
            total_rows.append({
                geo_label:   "★ TOTAL",
                "OMC":       omc,
                "No of ROs": n,
                "MP %":      round(mp, 2),
                "MS %":      round(ms, 2),
                "_ne_raw":   ne,
                "NE":        f"{ne:.2f}" if ne is not None else "—",
            })
        total_df = pd.DataFrame(total_rows)
        if geo_sel == "Trading Area":
            total_df.insert(1, "TA Name", "")

        bar_source = total_rows   # bar chart always uses scope-aggregate NE
        display_df = pd.concat([detail_df, total_df], ignore_index=True)
    else:
        bar_source = detail_rows
        display_df = detail_df

    # ── Styled table ──────────────────────────────────────────────────────────
    def _row_style(row):
        if row[geo_label] == "★ TOTAL":
            return ["font-weight:700;background-color:#e8e8e8"] * len(row)
        return [""] * len(row)

    cols_to_show = display_df.drop(columns=["_ne_raw"])
    styled = (
        cols_to_show.style
        .apply(_row_style, axis=1)
        .map(_ne_css, subset=["NE"])
        .format({"MP %": "{:.2f}%", "MS %": "{:.2f}%"})
    )
    st.dataframe(styled, hide_index=True, use_container_width=True, height=520)
    df_download(styled, "t03_1")

    # Advisory note for COM / Highway when product ≠ Both
    if geo_sel in ("COM", "Highway type") and product_sel != "Both":
        st.caption(
            f"ⓘ At {geo_sel} level, outlet counts use total ROs from the RO master — "
            "product-specific counts (from dim_ta) are not available at this geographic level."
        )

    # ── Bar chart — NE by OMC (scope aggregate) ───────────────────────────────
    _render_ne_chart(
        bar_source, universe_omcs, universe_sel, product_sel, geo_sel, geo_label)


@st.fragment
def _render_ne_chart(bar_source, universe_omcs, universe_sel, product_sel, geo_sel, geo_label):
    st.markdown("---")
    st.markdown(
        f"**Network Effectiveness by OMC** — "
        f"{universe_sel} · {product_sel} · {geo_sel} scope"
    )

    def _ne_label_color(v):
        if abs(v - 1.0) <= _NE_TOL:
            return _NE_BLACK
        return _NE_GREEN if v > 1.0 else _NE_RED

    bar_df = pd.DataFrame([
        {"OMC": r["OMC"], "NE": r["_ne_raw"],
         "MP %": r["MP %"], "MS %": r["MS %"],
         "ne_color": _ne_label_color(r["_ne_raw"])}
        for r in bar_source
        if r["_ne_raw"] is not None
           and r.get(geo_label) in ("★ TOTAL", "Total DO")
    ])

    if bar_df.empty:
        st.info("Bar chart unavailable — NE could not be computed for any OMC.")
        return

    max_ne = bar_df["NE"].max()
    min_ne = bar_df["NE"].min()
    y_max  = max(max_ne * 1.15, 1.30)
    y_min  = min(min_ne * 0.90, 0.85)   # always show headroom below NE=1

    # Bars anchored at NE=1: grow up for NE>1, down for NE<1
    bars = (
        alt.Chart(bar_df)
        .mark_bar(size=48)
        .encode(
            x=alt.X("OMC:N",
                     sort=universe_omcs,
                     axis=alt.Axis(labelAngle=0, labelFontSize=13, title=None)),
            y=alt.Y("NE:Q",
                     title="Network Effectiveness (NE)",
                     scale=alt.Scale(domain=[y_min, y_max])),
            y2=alt.Y2(datum=1.0),        # ← baseline anchored at NE = 1
            color=alt.Color(
                "OMC:N",
                scale=alt.Scale(
                    domain=list(OMC_COLORS.keys()),
                    range=list(OMC_COLORS.values())),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("OMC:N", title="OMC"),
                alt.Tooltip("NE:Q",   title="NE",   format=".3f"),
                alt.Tooltip("MP %:Q", title="MP %", format=".2f"),
                alt.Tooltip("MS %:Q", title="MS %", format=".2f"),
            ],
        )
    )

    # Solid baseline at NE = 1.0 (the "par" line)
    rule = (
        alt.Chart(pd.DataFrame({"y": [1.0]}))
        .mark_rule(color="black", strokeWidth=2.2)
        .encode(y="y:Q")
    )

    # "NE = 1.0" annotation
    annotation = (
        alt.Chart(pd.DataFrame({"y": [1.0], "label": ["NE = 1.0"]}))
        .mark_text(align="left", dx=4, dy=-8, color="black",
                   fontSize=11, fontStyle="italic")
        .encode(
            y=alt.Y("y:Q"),
            text=alt.Text("label:N"),
        )
    )

    # NE value labels: above bar tip for NE≥1, below bar tip for NE<1
    # (two separate layers so dy sign can differ)
    _above = bar_df[bar_df["NE"] >= (1.0 - _NE_TOL)]
    _below = bar_df[bar_df["NE"] <  (1.0 - _NE_TOL)]

    def _text_layer(df, dy_px):
        return (
            alt.Chart(df)
            .mark_text(dy=dy_px, fontSize=12, fontWeight="bold")
            .encode(
                x=alt.X("OMC:N", sort=universe_omcs),
                y=alt.Y("NE:Q"),
                text=alt.Text("NE:Q", format=".2f"),
                color=alt.Color("ne_color:N", scale=None, legend=None),
            )
        )

    layers = [bars, rule, annotation, _text_layer(_above, -10)]
    if not _below.empty:
        layers.append(_text_layer(_below, 12))

    chart = alt.layer(*layers).properties(height=340)
    st.altair_chart(chart, use_container_width=True)

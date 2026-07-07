"""Tab 1 — Overview: KPI cards + full OMC breakdown + donut chart."""
import streamlit as st
from components.downloads import df_download
import pandas as pd
import altair as alt
from core import (totals_row, indian, pct, klpm,
                  fmt_gr, fmt_pp, fmt_notional, style_growth,
                  OMC_ORDER, OMC_COLORS, PSU, PVT)
from components.kpi_row import kpi_row, metric_card


# ── PPT helpers ──────────────────────────────────────────────────────────────
def _last_pair(pairs_set):
    """Return (fy_code, month_index) for the last cell in a set of (fy, mi) pairs."""
    if not pairs_set:
        return None, None
    return max(pairs_set, key=lambda p: (p[0], int(p[1])))


def _ppt_ro_count(fact_f, omc, last_fy, last_mi):
    """Count distinct ROs for omc reporting in the last (fy_code, month_index) of period."""
    if last_fy is None or last_mi is None or fact_f.empty:
        return 0
    sub = fact_f[
        (fact_f.omc == omc) &
        (fact_f.fy_code == last_fy) &
        (fact_f.month_index == last_mi)
    ]
    return int(sub.sap_code.nunique())


def _fmt_ppt(v):
    """Format PPT value in KL/RO (1 decimal, Indian grouping)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return indian(v, 1)


def _fmt_ppt_diff(v):
    """PPT diff with directional arrow (↑ green / ↓ red via style_growth)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if v > 0:
        return f"↑ {indian(v, 1)}"
    if v < 0:
        return f"↓ {indian(abs(v), 1)}"
    return indian(v, 1)


def _bold_last_row(s):
    """Styler.apply(axis=0): bold the last (Total) row."""
    out = [""] * len(s)
    out[-1] = "font-weight:bold"
    return out


def render(ctx):
    cy_f       = ctx["cy_f"]
    ly_f       = ctx["ly_f"]
    ro_scope   = ctx["ro_scope"]
    product    = ctx["product"]
    cy         = ctx["cy"]
    period_lbl = ctx["period_lbl"]
    multi_fy_mode = ctx.get("multi_fy_mode", False)
    # Months in period — used as PPT divisor
    if multi_fy_mode:
        n_months = max(len(ctx.get("cy_pairs", set())), 1)
    else:
        n_months = max(len(ctx["months"]), 1)

    universe = st.radio("Denominator", ["Industry", "PSU"],
                        horizontal=True, key="ov_univ")
    uset = OMC_ORDER if universe == "Industry" else PSU

    ind = totals_row(cy_f, ly_f, uset)
    # Always compute within-PSU separately so the PSU card is available
    psu_row = totals_row(cy_f, ly_f, PSU)

    # IOCL KLPM — volume ÷ months ÷ IOCL ROs in scope (Rule #194 / #195)
    iocl_net   = int(ro_scope[ro_scope.omc == "IOCL"].sap_code.nunique())
    iocl_ly_net = int(
        ctx["ro_scope"][ctx["ro_scope"].omc == "IOCL"].sap_code.nunique()
    )  # same scope for LY (sidebar filters are period-independent)
    iocl_klpm_cy = klpm(ind["IOCL_cyvol"], n_months, iocl_net)
    iocl_klpm_ly = klpm(ind["IOCL_lyvol"], n_months, iocl_ly_net)

    c1, c2, c3, c4, c5 = kpi_row(5)
    metric_card(
        c1, f"IOCL {product} Volume (KL)", indian(ind["IOCL_cyvol"], 0),
        (fmt_gr(ind["IOCL_gr"]) + " vs LY") if pd.notna(ind["IOCL_gr"]) else None,
    )
    metric_card(c2, f"IOCL {universe} Share", pct(ind["IOCL_cyshare"]),
                fmt_pp(ind["IOCL_ppt"]) + " pp")
    if universe == "Industry":
        metric_card(c3, "IOCL within PSU Share", pct(psu_row["IOCL_cyshare"]),
                    fmt_pp(psu_row["IOCL_ppt"]) + " pp")
    else:
        metric_card(c3, "BPCL PSU Share", pct(ind["BPCL_cyshare"]),
                    fmt_pp(ind["BPCL_ppt"]) + " pp")
    metric_card(
        c4, "IOCL KLPM (KL/mo/RO)", indian(iocl_klpm_cy, 2),
        delta=f"{indian(iocl_klpm_cy - iocl_klpm_ly, 2)} vs LY",
        help_text="Volume ÷ months in period ÷ IOCL ROs in current scope (Rule #194)",
    )
    metric_card(c5, "IOCL network outlets", indian(iocl_net))

    st.markdown(f"#### {universe} breakdown — {cy}, {period_lbl}")

    # ── PPT: determine last (fy_code, month_index) of CY and LY periods ──────
    # Use the last month that actually has data in the filtered frame — not the
    # UI selection ceiling — so partial years (e.g. FY 2026-27 with Apr+May
    # only) return the correct denominator (May) rather than the selected end
    # month (Mar) which has no rows and would produce a zero count.
    if multi_fy_mode:
        last_cy_fy, last_cy_mi = _last_pair(ctx.get("cy_pairs", set()))
        last_ly_fy, last_ly_mi = _last_pair(ctx.get("ly_pairs", set()))
    else:
        last_cy_fy = ctx["cy"]
        last_cy_mi = (int(cy_f.month_index.max()) if not cy_f.empty else None)
        last_ly_fy = ctx.get("ly")
        last_ly_mi = (int(ly_f.month_index.max()) if not ly_f.empty else None)

    has_ly = bool(ctx.get("ly"))

    # ── Build OMC rows with PPT ───────────────────────────────────────────────
    rows = []
    total_cy_vol = 0.0
    total_ly_vol = 0.0
    total_ros_cy = 0
    total_ros_ly = 0

    for omc in uset:
        cy_vol = float(ind[f"{omc}_cyvol"])
        ly_vol = float(ind[f"{omc}_lyvol"])
        n_cy   = _ppt_ro_count(cy_f, omc, last_cy_fy, last_cy_mi)
        n_ly   = _ppt_ro_count(ly_f, omc, last_ly_fy, last_ly_mi) if has_ly else 0

        ppt_cy   = (cy_vol / n_months) / n_cy if n_cy > 0 else None
        ppt_ly   = (ly_vol / n_months) / n_ly if n_ly > 0 else None
        ppt_diff = (ppt_cy - ppt_ly) if (ppt_cy is not None and ppt_ly is not None) else None

        total_cy_vol += cy_vol
        total_ly_vol += ly_vol
        total_ros_cy += n_cy
        total_ros_ly += n_ly

        rows.append({
            "OMC":                 omc,
            "Type":                "PSU" if omc in PSU else "Private",
            "CY Vol (KL)":         cy_vol,
            "LY Vol (KL)":         ly_vol,
            "Growth %":            ind[f"{omc}_gr"],
            f"{universe} Share %": ind[f"{omc}_cyshare"],
            "+/- pp":              ind[f"{omc}_ppt"],
            "Notional (KL)":       ind[f"{omc}_notional"],
            "PPT CY":              ppt_cy,
            "PPT LY":              ppt_ly,
            "PPT Diff":            ppt_diff,
        })

    # ── Total row ─────────────────────────────────────────────────────────────
    total_ppt_cy   = (total_cy_vol / n_months) / total_ros_cy if total_ros_cy > 0 else None
    total_ppt_ly   = (total_ly_vol / n_months) / total_ros_ly if total_ros_ly > 0 else None
    total_ppt_diff = (
        (total_ppt_cy - total_ppt_ly)
        if (total_ppt_cy is not None and total_ppt_ly is not None) else None
    )
    total_gr = (
        (total_cy_vol - total_ly_vol) / total_ly_vol * 100
        if total_ly_vol > 0 else None
    )
    rows.append({
        "OMC":                 "Total",
        "Type":                "",
        "CY Vol (KL)":         total_cy_vol,
        "LY Vol (KL)":         total_ly_vol,
        "Growth %":            total_gr,
        f"{universe} Share %": None,
        "+/- pp":              None,
        "Notional (KL)":       None,
        "PPT CY":              total_ppt_cy,
        "PPT LY":              total_ppt_ly,
        "PPT Diff":            total_ppt_diff,
    })

    df = pd.DataFrame(rows)
    growth_cols = ["Growth %", "+/- pp", "Notional (KL)", "PPT Diff"]
    share_col   = f"{universe} Share %"
    styled = (style_growth(df, growth_cols)
              .format({
                  "CY Vol (KL)":     lambda x: indian(x, 1),
                  "LY Vol (KL)":     lambda x: indian(x, 1),
                  "Growth %":        fmt_gr,
                  share_col:         pct,
                  "+/- pp":          fmt_pp,
                  "Notional (KL)":   lambda x: fmt_notional(x, 1),
                  "PPT CY":          _fmt_ppt,
                  "PPT LY":          _fmt_ppt,
                  "PPT Diff":        _fmt_ppt_diff,
              })
              .apply(_bold_last_row, axis=0))
    st.dataframe(styled, hide_index=True, use_container_width=True)
    df_download(styled, "t01_1")

    bar_df = pd.DataFrame({
        "OMC":   uset,
        "Share": [ind[f"{o}_cyshare"] for o in uset],
        "Vol":   [ind[f"{o}_cyvol"]   for o in uset],
    })
    _clrs = [OMC_COLORS[o] for o in uset]
    bar = alt.Chart(bar_df).mark_bar().encode(
        x=alt.X("OMC:N", sort=uset, axis=alt.Axis(labelAngle=0), title=""),
        y=alt.Y("Share:Q", title=f"{universe} Share %"),
        color=alt.Color("OMC:N",
                        scale=alt.Scale(domain=uset, range=_clrs),
                        legend=None),
        tooltip=["OMC",
                 alt.Tooltip("Share:Q", format=".2f", title="Share %"),
                 alt.Tooltip("Vol:Q",   format=",.0f", title="Volume (KL)")]
    ).properties(height=280, title=f"{product} {universe} share — {cy}")
    lbl = bar.mark_text(dy=-8, fontSize=12, fontWeight="bold").encode(
        text=alt.Text("Share:Q", format=".1f")
    )
    st.altair_chart(bar + lbl, use_container_width=True)

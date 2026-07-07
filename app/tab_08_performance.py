"""Tab 8 — Performance (CY vs LY): MS-sheet layout with PSU/PVT/IND subtotals."""
import streamlit as st
from components.downloads import df_download
import pandas as pd
from core import (totals_row, indian, pct, klpm,
                  fmt_gr, fmt_pp, fmt_notional, style_growth, OMC_ORDER, PSU, PVT)


def render(ctx):
    cy_f       = ctx["cy_f"]
    ly_f       = ctx["ly_f"]
    ro_scope   = ctx["ro_scope"]
    product    = ctx["product"]
    cy         = ctx["cy"]
    ly         = ctx["ly"]
    period_lbl = ctx["period_lbl"]
    n_months   = max(len(ctx["months"]), 1)

    # RO counts per OMC in scope (from dim_ro master via ro_scope — Rule #195)
    ro_counts = (ro_scope.groupby("omc")["sap_code"].nunique()
                 .reindex(OMC_ORDER, fill_value=0).to_dict())

    if not ly:
        st.warning(
            f"Performance comparison for **{cy}** vs prior year cannot be displayed — "
            f"the database does not contain data prior to **{cy}**. "
            f"Please select a later year to enable year-on-year comparison.")
        return

    universe = st.radio("Denominator", ["Industry", "PSU"],
                        horizontal=True, key="perf_univ",
                        help="Use PSU when private OMC data is not yet available "
                             "for the selected period.")
    uset = OMC_ORDER if universe == "Industry" else PSU

    st.markdown(f"#### {product} (R) Performance — {cy} vs {ly}, {period_lbl}  "
                f"*[{universe} denominator]*")
    ind = totals_row(cy_f, ly_f, uset)
    # PSU-within-universe — only meaningful when universe=Industry
    psu_row = totals_row(cy_f, ly_f, PSU) if universe == "Industry" else ind
    cy_tot, ly_tot = ind["cy_tot"], ind["ly_tot"]

    # Total RO count for participation denominator (matches volume denominator: uset)
    total_ros = sum(ro_counts.get(o, 0) for o in uset)

    rows = []
    for omc in uset:
        n_ros = ro_counts.get(omc, 0)
        row = {
            "OMC":           omc,
            "ROs":           n_ros,
            "RO Part%":      n_ros / total_ros * 100 if total_ros else 0.0,
            "CY Vol (KL)":   ind[f"{omc}_cyvol"],
            "LY Vol (KL)":   ind[f"{omc}_lyvol"],
            "+/- (KL)":      ind[f"{omc}_diffvol"],
            "GR %":          ind[f"{omc}_gr"],
            "KLPM CY":       klpm(ind[f"{omc}_cyvol"], n_months, n_ros),
            "Shr CY":        ind[f"{omc}_cyshare"],
            "Shr LY":        ind[f"{omc}_lyshare"],
            "+/- pp":        ind[f"{omc}_ppt"],
            "Notional (KL)": ind[f"{omc}_notional"],
        }
        # PSU-within-industry column — only when Industry view (would be redundant in PSU view)
        if universe == "Industry" and omc in PSU:
            row["PSU Shr CY"] = psu_row[f"{omc}_cyshare"]
            row["PSU +/- pp"] = psu_row[f"{omc}_ppt"]
        rows.append(row)

    def subtotal(name, omcs):
        cyv  = sum(ind[f"{o}_cyvol"] for o in omcs)
        lyv  = sum(ind[f"{o}_lyvol"] for o in omcs)
        cs   = cyv / cy_tot * 100 if cy_tot else 0.0
        ls   = lyv / ly_tot * 100 if ly_tot else 0.0
        gr   = (cyv - lyv) / lyv * 100 if lyv else None
        pp_  = cs - ls
        n_sub = sum(ro_counts.get(o, 0) for o in omcs)
        row = {
            "OMC":           name,
            "ROs":           n_sub,
            "RO Part%":      n_sub / total_ros * 100 if total_ros else 0.0,
            "CY Vol (KL)":   cyv,
            "LY Vol (KL)":   lyv,
            "+/- (KL)":      cyv - lyv,
            "GR %":          gr,
            "KLPM CY":       klpm(cyv, n_months, n_sub),
            "Shr CY":        cs,
            "Shr LY":        ls,
            "+/- pp":        pp_,
            "Notional (KL)": pp_ / 100 * cy_tot,
        }
        if universe == "Industry":
            row["PSU Shr CY"] = None
            row["PSU +/- pp"] = None
        return row

    if universe == "Industry":
        out = (rows[:3] + [subtotal("PSU", PSU)] + rows[3:]
               + [subtotal("PVT", PVT), subtotal("IND", OMC_ORDER)])
    else:
        # PSU mode: only PSU rows + PSU subtotal; no PVT/IND subtotals
        out = rows + [subtotal("PSU", PSU)]

    df = pd.DataFrame(out)

    # Column label shows the actual denominator
    shr_label = f"{universe} Shr"
    df = df.rename(columns={"Shr CY": f"{shr_label} CY",
                             "Shr LY": f"{shr_label} LY",
                             "+/- pp": f"{shr_label} +/- pp",
                             "Notional (KL)": f"{shr_label} Notional (KL)"})

    shr_cy  = f"{shr_label} CY"
    shr_ly  = f"{shr_label} LY"
    shr_pp  = f"{shr_label} +/- pp"
    shr_not = f"{shr_label} Notional (KL)"

    growth_cols = ["GR %", "+/- (KL)", shr_pp, shr_not]
    fmt_dict = {
        "ROs":          lambda x: indian(int(x)) if pd.notna(x) else "—",
        "RO Part%":     lambda x: f"{x:.1f}%" if pd.notna(x) else "—",
        "CY Vol (KL)":  lambda x: indian(x, 1),
        "LY Vol (KL)":  lambda x: indian(x, 1),
        "+/- (KL)":     lambda x: fmt_notional(x, 1),
        "GR %":         fmt_gr,
        "KLPM CY":      lambda x: indian(x, 2) if pd.notna(x) else "—",
        shr_cy:         pct,
        shr_ly:         pct,
        shr_pp:         fmt_pp,
        shr_not:        lambda x: fmt_notional(x, 1),
    }
    if universe == "Industry":
        growth_cols += ["PSU +/- pp"]
        fmt_dict["PSU Shr CY"] = lambda x: pct(x) if x is not None and not pd.isna(x) else ""
        fmt_dict["PSU +/- pp"] = lambda x: fmt_pp(x) if x is not None and not pd.isna(x) else ""

    styled = (style_growth(df, growth_cols).format(fmt_dict))
    st.dataframe(styled, hide_index=True, use_container_width=True)
    df_download(styled, "t08_1")
    st.caption(
        f"Shares and **RO Part%** computed within **{universe}** total. "
        "**RO Part%** = OMC outlets ÷ total {universe} outlets in scope × 100 (from dim_ro master). "
        "Notional = (CY share − LY share) × CY denominator volume. "
        f"Volumes summed over {period_lbl}; LY uses the same months.  "
        "**KLPM** = CY volume ÷ months in period ÷ ROs in current scope (Rule #194)."
    )

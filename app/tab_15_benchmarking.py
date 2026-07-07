"""Tab 15 — RO Benchmarking: each IOCL RO vs the TA market leader (any OMC).

Leader = highest KLPM RO in the TA for the selected product and CY period,
computed from full DO data (unfiltered).  IOCL ROs shown follow sidebar geo
filters.  Network Effectiveness (NE = Market Share % ÷ RO Share %) is shown
as a per-RSA summary below the main table.
"""
import streamlit as st
from components.downloads import df_download
import pandas as pd
from core import (share_frame, participation, pct,
                  style_growth, OMC_ORDER, PSU, COM_LABELS)


# ── Core computation ──────────────────────────────────────────────────────────

def _bench_data(monthly, dim_ro, ro_scope, ta_dim, prod,
                cy, months, multi_fy_mode, cy_pairs):
    """
    Returns (bench_df, n_months).

    bench_df has one row per IOCL RO present in ro_scope (geo-filtered),
    with TA leader info joined from full (unfiltered) monthly data.
    """
    # ── CY period slice — FULL monthly, all OMCs (accurate TA leader) ────────
    if multi_fy_mode and cy_pairs:
        fymi = monthly.fy_code + "_" + monthly.month_index.astype(str)
        keys = {f"{fy}_{mi}" for fy, mi in cy_pairs}
        base = monthly[fymi.isin(keys) & (monthly["product"] == prod)]
        n_months = max(len(cy_pairs), 1)
    else:
        base = monthly[(monthly.fy_code == cy)
                       & monthly.month_index.isin(months)
                       & (monthly["product"] == prod)]
        n_months = max(len(months), 1)

    if base.empty:
        return pd.DataFrame(), n_months

    # ── Volume per RO per TA (all OMCs, full DO) ──────────────────────────────
    ro_vol = (base.groupby(["ta_code", "sap_code", "omc"])["volume_kl"]
              .sum().reset_index())
    ro_vol["klpm"] = ro_vol["volume_kl"] / n_months

    # ── TA leader = max KLPM RO per TA ───────────────────────────────────────
    leader_idx = ro_vol.groupby("ta_code")["klpm"].idxmax()
    leaders = (ro_vol.loc[leader_idx,
                          ["ta_code", "sap_code", "omc", "klpm"]]
               .rename(columns={"sap_code": "leader_sap",
                                "omc":      "leader_omc",
                                "klpm":     "leader_klpm"})
               .reset_index(drop=True))

    # Join leader RO name from full dim_ro
    ro_names = dim_ro[["sap_code", "ro_name"]].drop_duplicates("sap_code")
    leaders = leaders.merge(
        ro_names.rename(columns={"sap_code": "leader_sap",
                                 "ro_name":  "leader_ro_name"}),
        on="leader_sap", how="left")
    leaders["leader_ro_name"] = (leaders["leader_ro_name"]
                                 .fillna(leaders["leader_sap"].astype(str)))

    # ── IOCL RO volumes (full monthly) ───────────────────────────────────────
    iocl_vol = (ro_vol[ro_vol["omc"] == "IOCL"]
                [["ta_code", "sap_code", "klpm"]]
                .rename(columns={"klpm": "iocl_klpm"}))

    # ── IOCL RO master — geo-filtered (determines rows shown) ────────────────
    iocl_dim = (ro_scope[ro_scope["omc"] == "IOCL"]
                [["sap_code", "ro_name", "ta_code", "rsa_name",
                  "com", "ab_site", "district"]]
                .drop_duplicates("sap_code"))

    # ── Assemble ──────────────────────────────────────────────────────────────
    bench = iocl_dim.merge(iocl_vol, on=["sap_code", "ta_code"], how="left")
    bench["iocl_klpm"] = bench["iocl_klpm"].fillna(0.0)
    bench = bench.merge(leaders, on="ta_code", how="left")
    bench["leader_klpm"]    = bench["leader_klpm"].fillna(0.0)
    bench["leader_ro_name"] = bench["leader_ro_name"].fillna("—")
    bench["leader_omc"]     = bench["leader_omc"].fillna("—")
    bench["gap"]            = (bench["iocl_klpm"] - bench["leader_klpm"]).round(2)

    # TA name
    ta_name_map = ta_dim.set_index("ta_code")["ta_name_canonical"]
    bench["ta_name"] = bench["ta_code"].map(ta_name_map)

    def _status(row):
        if row["iocl_klpm"] == 0:
            return "Absent / NIL"
        if row["gap"] >= -0.01:          # leader is IOCL itself
            return "Market Leader"
        return "Lagging"

    bench["status"] = bench.apply(_status, axis=1)
    return bench, n_months


def _ne_table(scope, ro_scope, cy, months, multi_fy_mode, cy_pairs, prod, uset):
    """Network Effectiveness per RSA = Market Share % ÷ RO Share %."""
    if multi_fy_mode and cy_pairs:
        fymi = scope.fy_code + "_" + scope.month_index.astype(str)
        keys = {f"{fy}_{mi}" for fy, mi in cy_pairs}
        cy_f = scope[fymi.isin(keys) & (scope["product"] == prod)]
    else:
        cy_f = scope[(scope.fy_code == cy) & scope.month_index.isin(months)
                     & (scope["product"] == prod)]

    empty_ly = scope.iloc[0:0]
    sf   = share_frame(cy_f, empty_ly, ["rsa_name"], uset)
    mkt  = sf.set_index("rsa_name")["IOCL_cyshare"]       # %

    part = participation(ro_scope, ["rsa_name"]).set_index("rsa_name")
    ro_sh = (part["IOCL"] / part["Total"].replace(0, float("nan")) * 100).fillna(0)

    rows = []
    for rsa in sorted(set(mkt.index) | set(ro_sh.index)):
        ms = float(mkt.get(rsa, 0.0))
        rs = float(ro_sh.get(rsa, 0.0))
        ne = round(ms / rs, 2) if rs > 0 else 0.0
        rows.append({
            "RSA":         rsa,
            "IOCL ROs":    int(part.loc[rsa, "IOCL"])  if rsa in part.index else 0,
            "Total ROs":   int(part.loc[rsa, "Total"]) if rsa in part.index else 0,
            "RO Share %":  round(rs, 2),
            "Mkt Share %": round(ms, 2),
            "NE":          ne,
        })
    return pd.DataFrame(rows).sort_values("NE", ascending=False)


# ── Render ────────────────────────────────────────────────────────────────────

def render(ctx):
    monthly       = ctx["monthly"]
    scope         = ctx["scope"]
    ro_scope      = ctx["ro_scope"]
    dim_ro        = ctx["ro_master"]
    ta_dim        = ctx["ta_dim"]
    cy            = ctx["cy"]
    months        = ctx["months"]
    period_lbl    = ctx["period_lbl"]
    multi_fy_mode = ctx["multi_fy_mode"]
    cy_pairs      = ctx["cy_pairs"]

    st.subheader("RO Benchmarking — IOCL RO vs TA Market Leader")
    st.caption(
        f"CY **{cy}**  ·  period **{period_lbl}**  ·  "
        "Market leader = highest KLPM RO in the TA, any OMC, full DO data.  "
        "IOCL ROs shown follow sidebar geo filters."
    )

    # ── Controls ──────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([2, 2, 3])
    prod     = c1.radio("Product",   ["MS", "HSD"], horizontal=True,
                        key="bm_prod")
    universe = c2.radio("Denominator (NE)", ["Industry", "PSU"],
                        horizontal=True, key="bm_univ")
    sel_com  = c3.multiselect("COM filter (empty = all)",
                               ["A", "C", "D1", "D2", "E"],
                               format_func=lambda c: COM_LABELS[c],
                               key="bm_com")
    uset = OMC_ORDER if universe == "Industry" else PSU

    # ── Compute ───────────────────────────────────────────────────────────────
    bench, n_months = _bench_data(
        monthly, dim_ro, ro_scope, ta_dim, prod,
        cy, months, multi_fy_mode, cy_pairs)

    if bench.empty:
        st.warning("No data for the selected period.")
        return

    if sel_com:
        bench = bench[bench["com"].isin(sel_com)]
    if bench.empty:
        st.warning("No IOCL ROs match the COM filter.")
        return

    # ── KPI cards ─────────────────────────────────────────────────────────────
    n_total   = len(bench)
    n_leader  = (bench["status"] == "Market Leader").sum()
    n_lagging = (bench["status"] == "Lagging").sum()
    n_absent  = (bench["status"] == "Absent / NIL").sum()
    lag_gaps  = bench.loc[bench["status"] == "Lagging", "gap"]
    avg_gap   = lag_gaps.mean() if not lag_gaps.empty else float("nan")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Market Leaders",
              f"{n_leader} / {n_total}",
              f"{n_leader / n_total * 100:.1f}%")
    k2.metric("Lagging", str(n_lagging))
    k3.metric("Absent / NIL", str(n_absent))
    k4.metric("Avg Gap (Lagging ROs)",
              f"{avg_gap:.1f} KL/m" if pd.notna(avg_gap) else "—")

    # ── Search / filter / sort ────────────────────────────────────────────────
    f1, f2 = st.columns([3, 2])
    q = f1.text_input("Search RO name / TA name", "", key="bm_search")
    status_filter = f2.selectbox(
        "Status filter",
        ["All", "Market Leader", "Lagging", "Absent / NIL"],
        key="bm_status")

    if q:
        s = q.lower()
        bench = bench[
            bench["ro_name"].fillna("").str.lower().str.contains(s) |
            bench["ta_name"].fillna("").str.lower().str.contains(s) |
            bench["leader_ro_name"].fillna("").str.lower().str.contains(s)
        ]
    if status_filter != "All":
        bench = bench[bench["status"] == status_filter]

    sort_by = st.selectbox(
        "Sort by",
        ["Gap ↑ (worst first)", "IOCL KLPM ↓", "Leader KLPM ↓", "RSA", "COM"],
        key="bm_sort")

    sort_cfg = {
        "Gap ↑ (worst first)": ("gap",         True),
        "IOCL KLPM ↓":         ("iocl_klpm",   False),
        "Leader KLPM ↓":       ("leader_klpm", False),
        "RSA":                  ("rsa_name",    True),
        "COM":                  ("com",         True),
    }
    sc, sa = sort_cfg[sort_by]
    bench = bench.sort_values(sc, ascending=sa)
    st.caption(f"{len(bench)} IOCL ROs  ·  {n_months} month(s) in period")

    # ── Display table ─────────────────────────────────────────────────────────
    disp = pd.DataFrame({
        "SAP Code":       bench["sap_code"].astype(str),
        "RO Name":        bench["ro_name"],
        "Site":           bench["ab_site"].fillna("—"),
        "TA Name":        bench["ta_name"],
        "RSA":            bench["rsa_name"],
        "COM":            bench["com"],
        "IOCL KLPM":      bench["iocl_klpm"].round(1),
        "Leader KLPM":    bench["leader_klpm"].round(1),
        "Leader RO Name": bench["leader_ro_name"],
        "Leader OMC":     bench["leader_omc"],
        "Gap KL/m":       bench["gap"].round(1),
        "Status":         bench["status"],
    })

    def _status_style(v):
        if v == "Market Leader":  return "color: green; font-weight: bold"
        if v == "Lagging":        return "color: red"
        if v == "Absent / NIL":   return "color: grey"
        return ""

    def _gap_style(v):
        if not isinstance(v, (int, float)): return ""
        if v >= -0.01:  return "color: green"
        return "color: red"

    styled = (disp.style
              .map(_status_style, subset=["Status"])
              .map(_gap_style,    subset=["Gap KL/m"])
              .format({"IOCL KLPM":   "{:.1f}",
                       "Leader KLPM": "{:.1f}",
                       "Gap KL/m":    "{:.1f}"}))

    st.dataframe(styled, hide_index=True, use_container_width=True, height=460)
    df_download(styled, "t15_1")

    # ── Network Effectiveness ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Network Effectiveness — RSA level")
    st.caption(
        "NE = Market Share % ÷ RO Share %.  "
        "**NE > 1** → IOCL punching above network weight  |  "
        "**NE < 1** → underperforming relative to RO presence."
    )

    ne_df = _ne_table(scope, ro_scope, cy, months, multi_fy_mode,
                      cy_pairs, prod, uset)

    def _ne_style(v):
        if not isinstance(v, float): return ""
        if v >= 1.0:  return "color: green; font-weight: bold"
        if v >= 0.8:  return "color: orange"
        return "color: red"

    ne_styled = (ne_df.style
                 .map(_ne_style, subset=["NE"])
                 .format({"RO Share %":  "{:.2f}",
                          "Mkt Share %": "{:.2f}",
                          "NE":          "{:.2f}"}))
    st.dataframe(ne_styled, hide_index=True, use_container_width=True)
    df_download(ne_styled, "t15_2")

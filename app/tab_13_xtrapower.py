"""Tab 13 — XtraPower: ITPS Coverage · Transacting Status · Conversion % · Red Flags.

Four parameters reviewed:
  1. ITPS availability — does the RO have an ITPS POS with XtraPower integration?
  2. Transacting — is the RO recording XP fleet-card transactions?
  3. XP Conversion % — XP volume ÷ HSD volume (from XP source file; future: vs Mother HSD)
  4. Red Flags — Nil Transacting · Very High Conversion (>80%) · XP > HSD (data integrity)

Action plans can be recorded per RO for:
  - No ITPS: document reason + action to install ITPS
  - Nil Transacting: document reason + action to activate XP transactions
"""
from __future__ import annotations
import streamlit as st
from components.downloads import df_download
import pandas as pd

from core import (
    load_xtrapower, load_itps, xp_available_months,
    load_xp_action_plans, save_xp_action_plans,
    indian,
)

XP_CONV_HIGH = 80.0   # % threshold — above this is "Very High" (red flag)


def render(ctx):
    ro_scope = ctx["ro_scope"]   # sidebar-filtered master (all OMCs)
    TA_NAME  = ctx["TA_NAME"]

    st.caption(
        "XtraPower is IOCL's fleet-card loyalty programme for transporters, industries, "
        "and bulk HSD customers. ITPS (Integrated Transaction Payment System) is the POS "
        "machine through which XP transactions are processed. This tab covers four "
        "parameters: **ITPS availability**, **transacting status**, **XP conversion %**, "
        "and **red flags**."
    )

    # ── Load XtraPower data ──────────────────────────────────────────────────
    xp_all  = load_xtrapower()
    itps_df = load_itps()

    if xp_all.empty or itps_df.empty:
        st.warning(
            "XtraPower data not found. "
            "Run **`python ingest_xp.py`** from the `Development/` folder to load it."
        )
        return

    # ── Month / FY picker (independent of sidebar) ────────────────────────────
    avail     = xp_available_months()
    avail_fys = sorted({m["fy_code"] for m in avail})

    xp_c1, xp_c2, xp_c3 = st.columns([2, 2, 4])
    sel_fy = xp_c1.selectbox(
        "Financial Year", avail_fys,
        index=len(avail_fys) - 1, key="xp_fy")
    fy_months = [m for m in avail if m["fy_code"] == sel_fy]
    sel_month_lbl = xp_c2.selectbox(
        "Review Month",
        [m["label"] for m in fy_months],
        index=len(fy_months) - 1, key="xp_month")
    ref_m  = next(m for m in fy_months if m["label"] == sel_month_lbl)
    ref_mi = ref_m["month_index"]
    xp_c3.caption(
        f"Review month: **{sel_month_lbl}** · FY: **{sel_fy}**  \n"
        "Sidebar District / RSA / COM filters apply to the RO scope below."
    )

    # ── Scope: IOCL ROs passing sidebar filters ───────────────────────────────
    iocl_scope = (ro_scope[ro_scope["omc"] == "IOCL"]
                  [["sap_code", "ro_name", "rsa_code", "rsa_name",
                    "district", "com", "ta_code"]]
                  .drop_duplicates("sap_code")
                  .set_index("sap_code"))
    iocl_scope["ta_name"] = iocl_scope["ta_code"].map(TA_NAME).fillna("")
    iocl_saps = set(iocl_scope.index.astype(str))

    # ITPS flags for scoped ROs
    itps_scope = itps_df[itps_df["sap_code"].isin(iocl_saps)].set_index("sap_code")
    itps_has   = set(itps_scope[itps_scope["mid"].notna()].index)
    itps_none  = iocl_saps - itps_has

    # XP aggregates: review month and full FY, scoped
    xp_m_raw = xp_all[
        xp_all["sap_code"].isin(iocl_saps)
        & (xp_all["fy_code"] == sel_fy)
        & (xp_all["month_index"] == ref_mi)
    ]
    xp_fy_raw = xp_all[
        xp_all["sap_code"].isin(iocl_saps)
        & (xp_all["fy_code"] == sel_fy)
    ]
    m_agg  = (xp_m_raw.groupby("sap_code")[["hsd_kl","xp_kl"]].sum()
              .rename(columns={"hsd_kl":"hsd_m","xp_kl":"xp_m"}))
    fy_agg = (xp_fy_raw.groupby("sap_code")[["hsd_kl","xp_kl"]].sum()
              .rename(columns={"hsd_kl":"hsd_fy","xp_kl":"xp_fy"}))

    # Master frame: one row per IOCL RO in scope
    mf = iocl_scope.copy()
    mf["has_itps"] = mf.index.isin(itps_has)
    mf["mid"]      = itps_scope["mid"].reindex(mf.index).fillna("").astype(str)
    mf = mf.join(m_agg, how="left").join(fy_agg, how="left")
    for c in ["hsd_m","xp_m","hsd_fy","xp_fy"]:
        mf[c] = mf[c].fillna(0.0)

    mf["conv_m"]  = mf.apply(
        lambda r: r["xp_m"]  / r["hsd_m"]  * 100 if r["hsd_m"]  > 0 else 0.0, axis=1)
    mf["conv_fy"] = mf.apply(
        lambda r: r["xp_fy"] / r["hsd_fy"] * 100 if r["hsd_fy"] > 0 else 0.0, axis=1)

    # ── Derived flags ──────────────────────────────────────────────────────────
    mf["transacting_m"]  = mf["has_itps"] & (mf["xp_m"]  > 0)
    mf["transacting_fy"] = mf["has_itps"] & (mf["xp_fy"] > 0)
    mf["nil_m"]          = mf["has_itps"] & (mf["xp_m"]  == 0)
    mf["nil_fy"]         = mf["has_itps"] & (mf["xp_fy"] == 0)
    mf["nil_both"]       = mf["nil_m"] & mf["nil_fy"]
    mf["very_high"]      = mf["has_itps"] & (mf["conv_m"] > XP_CONV_HIGH)
    mf["xp_gt_hsd"]      = (mf["xp_m"] > mf["hsd_m"] + 0.5) & (mf["hsd_m"] > 0)

    # ── KPI cards ─────────────────────────────────────────────────────────────
    n_total       = len(mf)
    n_itps        = int(mf["has_itps"].sum())
    n_no_itps     = n_total - n_itps
    n_transacting = int(mf["transacting_m"].sum())
    n_nil_m       = int(mf["nil_m"].sum())
    n_nil_both    = int(mf["nil_both"].sum())
    n_very_high   = int(mf["very_high"].sum())
    n_xp_gt_hsd   = int(mf["xp_gt_hsd"].sum())

    tot_xp_m  = mf["xp_m"].sum()
    tot_hsd_m = mf["hsd_m"].sum()
    do_conv_m = tot_xp_m / tot_hsd_m * 100 if tot_hsd_m > 0 else 0.0

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("IOCL ROs in scope",         n_total)
    k2.metric("🟢 ITPS-enabled",            n_itps,
              help="ROs with a Merchant ID (MID) — ITPS POS installed and XP integrated")
    k3.metric("🔴 No ITPS",                n_no_itps,
              help="ROs without ITPS POS — cannot record XtraPower transactions")
    k4.metric("✅ Transacting this month",  n_transacting,
              help=f"ITPS ROs with XP > 0 in {sel_month_lbl}")
    k5.metric("⚠️ Nil Transacting",         n_nil_m,
              help=f"ITPS ROs with zero XP in {sel_month_lbl}")
    k6.metric(f"DO Conv% ({sel_month_lbl})", f"{do_conv_m:.2f}%",
              help="XP KL ÷ HSD KL across all IOCL ROs in scope (source file HSD)")

    st.markdown("---")

    # ── Shared action-plan helpers ─────────────────────────────────────────────
    def _ap_cols(df_indexed: pd.DataFrame, category: str):
        plans = load_xp_action_plans(category)
        df2 = df_indexed.copy()
        df2["Action Plan"] = df2.index.map(
            lambda s: plans.at[s, "action_text"] if s in plans.index else "")
        df2["Officer"]     = df2.index.map(
            lambda s: plans.at[s, "officer"]      if s in plans.index else "")
        df2["Last Updated"] = df2.index.map(
            lambda s: plans.at[s, "updated_at"]   if s in plans.index else "")
        return df2, plans

    def _save_btn(edited_df: pd.DataFrame, plans: pd.DataFrame,
                  category: str, key: str):
        if st.button("💾 Save Action Plans", key=f"xp_save_{key}"):
            updates = []
            for _, row in edited_df.iterrows():
                sap      = row["SAP Code"]
                orig_txt = plans.at[sap, "action_text"] if sap in plans.index else ""
                orig_off = plans.at[sap, "officer"]      if sap in plans.index else ""
                if row["Action Plan"] != orig_txt or row["Officer"] != orig_off:
                    updates.append({"sap_code":    sap,
                                    "action_text": row["Action Plan"],
                                    "officer":     row["Officer"]})
            if updates:
                save_xp_action_plans(updates, category)
                st.success(f"Saved {len(updates)} action plan(s).")
                st.rerun()
            else:
                st.info("No changes detected.")

    _BASE_DIS = ["SAP Code", "RO Name", "RSA", "District", "COM", "TA", "Last Updated"]
    _AP_CFG   = {
        "Action Plan":  st.column_config.TextColumn(
            "Action Plan", max_chars=500, width="large"),
        "Officer":      st.column_config.TextColumn("Officer", max_chars=100),
        "Last Updated": st.column_config.TextColumn(
            "Last Updated", disabled=True, width="small"),
    }

    # ========================================================================= #
    # PARAMETER 1 — ITPS Coverage
    # ========================================================================= #
    with st.expander(
            f"📡  Parameter 1 — ITPS Coverage  "
            f"({n_itps} enabled · {n_no_itps} not installed)",
            expanded=True):
        st.caption(
            "ITPS (Integrated Transaction Payment System) is the POS machine through "
            "which XP fleet-card transactions are recorded. An RO without ITPS cannot "
            "participate in the XtraPower programme."
        )

        # RSA-level coverage table
        cov_rows = []
        for rsa, grp in mf.groupby("rsa_name"):
            tot = len(grp)
            has = int(grp["has_itps"].sum())
            cov_rows.append({
                "RSA":           rsa,
                "Total IOCL ROs": tot,
                "ITPS-enabled":  has,
                "No ITPS":       tot - has,
                "Coverage %":    f"{has / tot * 100:.1f}%" if tot else "—",
            })
        cov_df = pd.DataFrame(cov_rows).sort_values(
            "Total IOCL ROs", ascending=False).reset_index(drop=True)
        st.dataframe(cov_df, hide_index=True, use_container_width=True)
        df_download(cov_df, "t13_1")

        st.markdown("---")
        st.markdown(f"**🔴 ROs without ITPS — {n_no_itps} outlets  ·  Action Plan**")
        if n_no_itps == 0:
            st.success("All IOCL ROs in the current scope have ITPS installed. ✅")
        else:
            no_itps_mf = mf[~mf["has_itps"]].copy()
            no_itps_base = pd.DataFrame({
                "SAP Code":  no_itps_mf.index.tolist(),
                "RO Name":   no_itps_mf["ro_name"].fillna("—").tolist(),
                "RSA":       no_itps_mf["rsa_name"].fillna("—").tolist(),
                "District":  no_itps_mf["district"].fillna("—").tolist(),
                "COM":       no_itps_mf["com"].fillna("—").tolist(),
                "TA":        no_itps_mf["ta_name"].tolist(),
            })
            no_itps_b, plans_no_itps = _ap_cols(
                no_itps_base.set_index("SAP Code"), "no_itps")
            no_itps_base = no_itps_b.reset_index()
            edited_no_itps = st.data_editor(
                no_itps_base,
                column_config={**_AP_CFG},
                disabled=_BASE_DIS,
                hide_index=True, use_container_width=True,
                key="xp_no_itps_ed")
            _save_btn(edited_no_itps, plans_no_itps, "no_itps", "no_itps")
            st.caption(
                "Record the reason ITPS is not yet installed and the planned action. "
                "Plans are saved to the database and persist across sessions."
            )

    # ========================================================================= #
    # PARAMETERS 2 & 3 — Transacting Status + Conversion %
    # ========================================================================= #
    with st.expander(
            f"📊  Parameters 2 & 3 — Transacting Status + Conversion %  "
            f"({n_transacting} transacting · {n_nil_m} nil this month)",
            expanded=True):
        st.caption(
            f"ITPS-enabled ROs only ({n_itps} in scope). "
            f"**XP KL** = fleet-card volume. "
            f"**Conv %** = XP ÷ HSD × 100 (source-file HSD used as denominator; "
            f"comparison to Mother HSD from fact_monthly is a future enhancement). "
            f"Review month: **{sel_month_lbl}** · FY cumulative: **{sel_fy}**."
        )
        itps_mf = mf[mf["has_itps"]].copy()
        if itps_mf.empty:
            st.info("No ITPS-enabled IOCL ROs in the current scope.")
        else:
            disp = pd.DataFrame({
                "SAP Code":                itps_mf.index.tolist(),
                "RO Name":                 itps_mf["ro_name"].fillna("—").tolist(),
                "RSA":                     itps_mf["rsa_name"].fillna("—").tolist(),
                "District":                itps_mf["district"].fillna("—").tolist(),
                "COM":                     itps_mf["com"].fillna("—").tolist(),
                f"HSD {sel_month_lbl} (KL)": [round(v, 2) for v in itps_mf["hsd_m"]],
                f"XP {sel_month_lbl} (KL)":  [round(v, 3) for v in itps_mf["xp_m"]],
                f"Conv% {sel_month_lbl}":     [f"{v:.2f}%" for v in itps_mf["conv_m"]],
                f"HSD {sel_fy} (KL)":        [round(v, 2) for v in itps_mf["hsd_fy"]],
                f"XP {sel_fy} (KL)":         [round(v, 3) for v in itps_mf["xp_fy"]],
                f"Conv% {sel_fy}":            [f"{v:.2f}%" for v in itps_mf["conv_fy"]],
                "Status": [
                    "✅ Transacting" if r.transacting_m else
                    ("🔴 Nil (month)" if r.nil_m else "➖ No HSD data")
                    for r in itps_mf.itertuples()
                ],
            })
            st.dataframe(disp, hide_index=True, use_container_width=True)
            df_download(disp, "t13_2")
            st.caption(
                f"Total ITPS ROs in scope: **{n_itps}** · "
                f"Transacting this month: **{n_transacting}** · "
                f"Nil this month: **{n_nil_m}** · "
                f"DO XP Conv% ({sel_month_lbl}): **{do_conv_m:.2f}%**"
            )

    # ========================================================================= #
    # PARAMETER 4 — Red Flags
    # ========================================================================= #
    with st.expander(
            f"🚨  Parameter 4 — Red Flags  "
            f"(No ITPS: {n_no_itps}  ·  Nil Transacting: {n_nil_both}  "
            f"·  Very High Conv: {n_very_high}  ·  XP>HSD: {n_xp_gt_hsd})",
            expanded=True):

        # ── 4a: No ITPS (summary reference; action plan is in Parameter 1) ────
        st.markdown(
            f"**🔴 a.  No ITPS** — {n_no_itps} outlets  "
            f"*(Action Plans are recorded in the Parameter 1 section above)*")

        st.markdown("---")

        # ── 4b: Nil Transacting ───────────────────────────────────────────────
        st.markdown(
            f"**🔴 b.  Nil Transacting** — {n_nil_both} ITPS-enabled ROs with "
            f"**zero XP in {sel_month_lbl} AND zero XP cumulative in {sel_fy}**")
        if n_nil_both == 0:
            st.success(
                f"No ITPS ROs with zero XP in both {sel_month_lbl} and all of {sel_fy}. ✅")
        else:
            nil_mf = mf[mf["nil_both"]].copy()
            nil_base = pd.DataFrame({
                "SAP Code":              nil_mf.index.tolist(),
                "RO Name":               nil_mf["ro_name"].fillna("—").tolist(),
                "RSA":                   nil_mf["rsa_name"].fillna("—").tolist(),
                "District":              nil_mf["district"].fillna("—").tolist(),
                "COM":                   nil_mf["com"].fillna("—").tolist(),
                "TA":                    nil_mf["ta_name"].tolist(),
                f"HSD {sel_month_lbl} (KL)": [round(v, 2) for v in nil_mf["hsd_m"]],
                f"HSD {sel_fy} (KL)":        [round(v, 2) for v in nil_mf["hsd_fy"]],
            })
            nil_b, plans_nil = _ap_cols(
                nil_base.set_index("SAP Code"), "nil_transacting")
            nil_base = nil_b.reset_index()
            num_dis = [f"HSD {sel_month_lbl} (KL)", f"HSD {sel_fy} (KL)"]
            edited_nil = st.data_editor(
                nil_base,
                column_config={
                    **_AP_CFG,
                    f"HSD {sel_month_lbl} (KL)": st.column_config.NumberColumn(
                        disabled=True, format="%.2f"),
                    f"HSD {sel_fy} (KL)":        st.column_config.NumberColumn(
                        disabled=True, format="%.2f"),
                },
                disabled=_BASE_DIS + num_dis,
                hide_index=True, use_container_width=True,
                key="xp_nil_ed")
            _save_btn(edited_nil, plans_nil, "nil_transacting", "nil")
            st.caption(
                f"These ROs have ITPS installed but zero XP transactions in "
                f"{sel_month_lbl} and across all months of {sel_fy}. "
                "Record the reason (machine not working, dealer not using XP, etc.) "
                "and the action plan."
            )

        st.markdown("---")

        # ── 4c: Very High Conversion (>80%) ───────────────────────────────────
        st.markdown(
            f"**🟡 c.  Very High Conversion (>{XP_CONV_HIGH:.0f}%)** — "
            f"{n_very_high} ROs in {sel_month_lbl}")
        if n_very_high == 0:
            st.success(
                f"No ITPS ROs above {XP_CONV_HIGH:.0f}% XP conversion in "
                f"{sel_month_lbl}. ✅")
        else:
            vh_mf = mf[mf["very_high"]].sort_values("conv_m", ascending=False).copy()
            vh_disp = pd.DataFrame({
                "SAP Code":              vh_mf.index.tolist(),
                "RO Name":               vh_mf["ro_name"].fillna("—").tolist(),
                "RSA":                   vh_mf["rsa_name"].fillna("—").tolist(),
                "District":              vh_mf["district"].fillna("—").tolist(),
                "COM":                   vh_mf["com"].fillna("—").tolist(),
                f"HSD {sel_month_lbl} (KL)": [round(v, 2) for v in vh_mf["hsd_m"]],
                f"XP {sel_month_lbl} (KL)":  [round(v, 3) for v in vh_mf["xp_m"]],
                f"Conv% {sel_month_lbl}":     [f"{v:.2f}%" for v in vh_mf["conv_m"]],
                f"Conv% {sel_fy}":            [f"{v:.2f}%" for v in vh_mf["conv_fy"]],
            })
            st.dataframe(vh_disp, hide_index=True, use_container_width=True)
            df_download(vh_disp, "t13_3")
            st.caption(
                f"XP conversion above {XP_CONV_HIGH:.0f}% is unusual. Possible causes: "
                "redemption transactions miscounted as new XP sales, fleet card swiped "
                "multiple times for a single dispensing, or source data error. "
                "Verify at RO level and escalate to XtraPower system team if needed."
            )

        st.markdown("---")

        # ── 4d: XP > HSD (data integrity) ─────────────────────────────────────
        st.markdown(
            f"**🔴 d.  XP Volume > HSD Volume (Data Integrity)** — "
            f"{n_xp_gt_hsd} ROs in {sel_month_lbl}")
        if n_xp_gt_hsd == 0:
            st.success(
                f"No XP > HSD violations in {sel_month_lbl}. Data integrity OK. ✅")
        else:
            xpg_mf = mf[mf["xp_gt_hsd"]].copy()
            xpg_disp = pd.DataFrame({
                "SAP Code":              xpg_mf.index.tolist(),
                "RO Name":               xpg_mf["ro_name"].fillna("—").tolist(),
                "RSA":                   xpg_mf["rsa_name"].fillna("—").tolist(),
                "District":              xpg_mf["district"].fillna("—").tolist(),
                f"HSD {sel_month_lbl} (KL)": [round(v, 2) for v in xpg_mf["hsd_m"]],
                f"XP {sel_month_lbl} (KL)":  [round(v, 3) for v in xpg_mf["xp_m"]],
                "XP − HSD (KL)": [
                    round(x - h, 3)
                    for x, h in zip(xpg_mf["xp_m"], xpg_mf["hsd_m"])
                ],
                f"Conv% {sel_month_lbl}": [f"{v:.2f}%" for v in xpg_mf["conv_m"]],
            })
            st.dataframe(xpg_disp, hide_index=True, use_container_width=True)
            df_download(xpg_disp, "t13_4")
            st.caption(
                "XP-recorded volume exceeds total HSD dispensed — physically impossible "
                "(you cannot swipe more fleet-card KL than the nozzle pumped). "
                "Most likely cause: redemption transactions recorded as new XP sales in "
                "the source data. Escalate to the XtraPower system team."
            )

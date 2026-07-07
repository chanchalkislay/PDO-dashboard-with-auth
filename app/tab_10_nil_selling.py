"""Tab 10 — Nil Selling: NIL · About to Go Nil · YTS · Revivals + Action Plans."""
import streamlit as st
from components.downloads import df_download
import pandas as pd
from core import (
    _nil_compute, available_months, _cal_label, _from_cal_pos,
    load_action_plans, save_action_plans, clear_plans_for_revivals,
    get_cleared_plans, OMC_ORDER, indian, MONTHS,
)


def render(ctx):
    monthly  = ctx["monthly"]
    ro_scope = ctx["ro_scope"]
    product  = ctx["product"]
    TA_NAME  = ctx["TA_NAME"]

    st.caption(
        "**NIL** = zero upliftment for 3 consecutive months · "
        "**About to Go Nil** = 2 consecutive months zero · "
        "**YTS** = commissioned ≤12 months ago, never sold · "
        "**Revival** = sold after being NIL · "
        "PRCN (negative volumes) treated as zero. FY boundary ignored.")

    # ── Controls ───────────────────────────────────────────────────────────────
    avail        = available_months()
    avail_labels = [m["label"] for m in avail]
    nil_c1, nil_c2 = st.columns([3, 1])
    sel_nil_month = nil_c1.selectbox(
        "Reference month (last of the 3 checked months)",
        avail_labels, index=len(avail_labels) - 1, key="nil_ref")
    sel_nil_omc = nil_c2.selectbox("OMC", OMC_ORDER, index=0, key="nil_omc")

    sel_m     = next(m for m in avail if m["label"] == sel_nil_month)
    ref_fy_n  = sel_m["fy_code"]
    ref_mi_n  = sel_m["month_index"]
    ref_pos_n = sel_m["cal_pos"]

    m0_lbl = _cal_label(*_from_cal_pos(ref_pos_n))
    m1_lbl = _cal_label(*_from_cal_pos(ref_pos_n - 1))
    m2_lbl = _cal_label(*_from_cal_pos(ref_pos_n - 2))
    m3_lbl = _cal_label(*_from_cal_pos(ref_pos_n - 3))

    st.caption(
        f"Checking: **{m2_lbl}** → **{m1_lbl}** → **{m0_lbl}**  "
        f"·  Product: **{product}**  ·  Sidebar filters apply")

    # ── Compute ────────────────────────────────────────────────────────────────
    with st.spinner("Computing nil-selling status…"):
        nd = _nil_compute([sel_nil_omc], product, ref_fy_n, ref_mi_n,
                          ro_scope, monthly, TA_NAME)

    if nd.empty:
        st.info("No ROs found for the selected OMC in the current filter scope.")
        return

    n_nil = int(nd.is_nil.sum())
    n_atr = int(nd.is_atrisk.sum())
    n_yts = int(nd.is_yts.sum())
    n_rev = int(nd.is_revival.sum())
    n_tot = len(nd)

    # Auto-clear action plans for ROs that have revived this month
    rev_saps = nd[nd.is_revival].index.tolist()
    if rev_saps:
        active_ap = load_action_plans()
        to_clear  = [s for s in rev_saps if s in active_ap.index]
        if to_clear:
            clear_plans_for_revivals(to_clear)

    # ── KPI cards ──────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(f"{sel_nil_omc} ROs in scope", n_tot)
    k2.metric("\U0001f534 NIL Selling", n_nil,
              help="Zero upliftment in all 3 checked months")
    k3.metric("\U0001f7e1 About to Go Nil", n_atr,
              help="Zero in last 2 months; sold in the month before")
    k4.metric("\U0001f535 Yet to Start (YTS)", n_yts,
              help="Commissioned ≤12 months ago, never sold — not counted as NIL")
    k5.metric("\U0001f7e2 Revivals", n_rev,
              help=f"Sold in {m0_lbl} after being NIL the month before")

    st.markdown("---")

    # ── Shared action-plan helpers ─────────────────────────────────────────────
    def _ap_cols(df_indexed):
        plans = load_action_plans()
        df_indexed = df_indexed.copy()
        df_indexed["Action Plan"] = df_indexed.index.map(
            lambda s: plans.at[s, "action_text"] if s in plans.index else "")
        df_indexed["Officer"]     = df_indexed.index.map(
            lambda s: plans.at[s, "officer"]      if s in plans.index else "")
        df_indexed["Last Updated"] = df_indexed.index.map(
            lambda s: plans.at[s, "updated_at"]   if s in plans.index else "")
        return df_indexed, plans

    def _save_btn(edited_df, plans, key):
        if st.button("\U0001f4be Save Action Plans", key=f"save_{key}"):
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
                save_action_plans(updates)
                st.success(f"Saved {len(updates)} action plan(s).")
                st.rerun()
            else:
                st.info("No changes detected.")

    _BASE_DIS = ["SAP Code", "RO Name", "RSA", "District",
                 "COM", "TA", "Last Updated"]
    _AP_CFG   = {
        "Action Plan": st.column_config.TextColumn(
            "Action Plan", max_chars=500, width="large"),
        "Officer": st.column_config.TextColumn("Officer", max_chars=100),
        "Last Updated": st.column_config.TextColumn(
            "Last Updated", disabled=True, width="small"),
    }

    # ── 🔴 NIL Selling ─────────────────────────────────────────────────────────
    with st.expander(f"\U0001f534 NIL Selling — {n_nil} outlets", expanded=True):
        if n_nil == 0:
            st.success("No NIL-selling outlets in the current scope.")
        else:
            nil_df = nd[nd.is_nil].copy()
            nil_df["nil_since_lbl"] = nil_df["streak"].apply(
                lambda s: _cal_label(*_from_cal_pos(ref_pos_n - int(s) + 1))
                if pd.notna(s) and int(s) > 0 else "—")
            nil_base = pd.DataFrame({
                "SAP Code":   nil_df.index,
                "RO Name":    nil_df["ro_name"].fillna("—"),
                "RSA":        nil_df["rsa_name"].fillna("—"),
                "District":   nil_df["district"].fillna("—"),
                "COM":        nil_df["com"].fillna("—"),
                "TA":         nil_df["ta_name"],
                "Last Sale":  nil_df["last_sale"],
                "Nil Since":  nil_df["nil_since_lbl"],
                "Months Nil": nil_df["streak"].fillna(3).astype(int),
            }).sort_values("Months Nil", ascending=False).reset_index(drop=True)
            nil_b, plans_nil = _ap_cols(nil_base.set_index("SAP Code"))
            nil_base = nil_b.reset_index()
            edited_nil = st.data_editor(
                nil_base,
                column_config={
                    **_AP_CFG,
                    "Last Sale":  st.column_config.TextColumn(disabled=True),
                    "Nil Since":  st.column_config.TextColumn(disabled=True),
                    "Months Nil": st.column_config.NumberColumn(disabled=True),
                },
                disabled=_BASE_DIS + ["Last Sale", "Nil Since", "Months Nil"],
                hide_index=True, use_container_width=True, key="nil_ap_ed")
            _save_btn(edited_nil, plans_nil, "nil")
            st.caption("Type an action plan and responsible officer name directly "
                       "in the table. Click \U0001f4be Save to persist to database. "
                       "Plans auto-clear when the RO revives.")

    # ── 🟡 About to Go Nil ─────────────────────────────────────────────────────
    with st.expander(f"\U0001f7e1 About to Go Nil — {n_atr} outlets", expanded=True):
        if n_atr == 0:
            st.success("No at-risk outlets in the current scope.")
        else:
            atr_df = nd[nd.is_atrisk].copy()
            disp_atr = pd.DataFrame({
                "SAP Code":            atr_df.index,
                "RO Name":             atr_df["ro_name"].fillna("—"),
                "RSA":                 atr_df["rsa_name"].fillna("—"),
                "District":            atr_df["district"].fillna("—"),
                "COM":                 atr_df["com"].fillna("—"),
                "TA":                  atr_df["ta_name"],
                f"Vol {m2_lbl} (KL)": atr_df["m2"].apply(lambda x: indian(x, 1)),
                f"Vol {m1_lbl} (KL)": atr_df["m1"].apply(lambda x: indian(x, 1)),
                f"Vol {m0_lbl} (KL)": atr_df["m0"].apply(lambda x: indian(x, 1)),
            })
            st.dataframe(disp_atr.sort_values("RSA"),
                         hide_index=True, use_container_width=True)
            df_download(disp_atr.sort_values("RSA"), "t10_1")
            st.caption(f"Vol {m1_lbl} and {m0_lbl} = 0. Last sold ≤ {m2_lbl}. "
                       "One more nil month moves these to the NIL list.")

    # ── 🔵 Yet to Start (YTS) ──────────────────────────────────────────────────
    with st.expander(f"\U0001f535 Yet to Start (YTS) — {n_yts} outlets",
                     expanded=True):
        if n_yts == 0:
            st.info("No YTS outlets in the current scope.")
        else:
            yts_df = nd[nd.is_yts].copy()
            yts_base = pd.DataFrame({
                "SAP Code":      yts_df.index,
                "RO Name":       yts_df["ro_name"].fillna("—"),
                "RSA":           yts_df["rsa_name"].fillna("—"),
                "District":      yts_df["district"].fillna("—"),
                "COM":           yts_df["com"].fillna("—"),
                "TA":            yts_df["ta_name"],
                "Commissioned":  yts_df["comm_label"],
                "DOC Source":    yts_df["doc_source"],
                "Months in YTS": yts_df["months_in_yts"].astype(int),
            }).sort_values("Months in YTS", ascending=False).reset_index(drop=True)
            yts_b, plans_yts = _ap_cols(yts_base.set_index("SAP Code"))
            yts_base = yts_b.reset_index()
            edited_yts = st.data_editor(
                yts_base,
                column_config={
                    **_AP_CFG,
                    "Commissioned":  st.column_config.TextColumn(disabled=True),
                    "DOC Source":    st.column_config.TextColumn(disabled=True),
                    "Months in YTS": st.column_config.NumberColumn(disabled=True),
                },
                disabled=_BASE_DIS + ["Commissioned", "DOC Source", "Months in YTS"],
                hide_index=True, use_container_width=True, key="yts_ap_ed")
            _save_btn(edited_yts, plans_yts, "yts")
            st.caption(
                "YTS = commissioned within last 12 months, no sales yet. "
                "Not counted as NIL. Action plan tracks commissioning follow-up. "
                "Auto-moves to NIL if still unsold after 12 months from commissioning.")

    # ── 🟢 Revivals ────────────────────────────────────────────────────────────
    with st.expander(f"\U0001f7e2 Revivals — {n_rev} outlets", expanded=True):
        if n_rev == 0:
            st.info(f"No revivals recorded in {m0_lbl}.")
        else:
            rev_df  = nd[nd.is_revival].copy()
            cleared = get_cleared_plans(rev_df.index.tolist())
            disp_rev = pd.DataFrame({
                "SAP Code":                    rev_df.index,
                "RO Name":                     rev_df["ro_name"].fillna("—"),
                "RSA":                         rev_df["rsa_name"].fillna("—"),
                "District":                    rev_df["district"].fillna("—"),
                "COM":                         rev_df["com"].fillna("—"),
                "TA":                          rev_df["ta_name"],
                f"Revival Vol {m0_lbl} (KL)": rev_df["m0"].apply(
                                                  lambda x: indian(x, 1)),
                "Prev. Action Plan": rev_df.index.map(
                    lambda s: cleared.at[s, "action_text"]
                    if s in cleared.index else "—"),
                "Prev. Officer": rev_df.index.map(
                    lambda s: cleared.at[s, "officer"]
                    if s in cleared.index else "—"),
            })
            st.caption(
                f"Zero upliftment in {m3_lbl}, {m2_lbl}, {m1_lbl} "
                f"— resumed selling in {m0_lbl}. "
                "Action plans were auto-cleared on revival and are shown above "
                "for reference.")
            st.dataframe(disp_rev.sort_values("RSA"),
                         hide_index=True, use_container_width=True)
            df_download(disp_rev.sort_values("RSA"), "t10_2")

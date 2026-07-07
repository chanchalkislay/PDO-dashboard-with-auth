"""Tab 17 — COCO Management (work-order alerts + sales monitoring).

Confirmed layout (HANDOFF_FOR_FABLE5.md):
  1. Alert banner — coloured tier chips (incl. grey 'No Work Order')
  2. Sales performance vs TA average + Policy Target
  3. Work-order status table (urgency-sorted, colour badges)
  4. Detail panel per COCO
Admin (unlocked via sidebar): Add COCO (conversion) / Mark Closed–Regularised.
"""
from __future__ import annotations

import pandas as pd
import sqlite3
import streamlit as st
from components.downloads import df_download

from core import (DB_PATH, available_months, coco_alert_tier, detail_table,
                  indian, load_coco_wo, render_ta_html, ta_volume_grid, pct)

TIER_ORDER = ["expired", "critical", "exp_crit", "exp_soon", "active", "no_wo"]
TIER_LABEL = {"expired": "Expired", "critical": "Critical",
              "exp_crit": "Expiry Critical", "exp_soon": "Expiring Soon",
              "active": "Active", "no_wo": "No Work Order"}
TIER_COLOR = {"expired": "#cf222e", "critical": "#e5531a", "exp_crit": "#f79009",
              "exp_soon": "#eac54f", "active": "#2da44e", "no_wo": "#8c8c8c"}


def _wo_write(sql: str, params: tuple):
    """FUSE-safe write to coco_work_orders / dim_ro."""
    import os, tempfile
    with open(DB_PATH, "rb") as f:
        data = f.read()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
    with open(tmp.name, "wb") as f:
        f.write(data)
    con = sqlite3.connect(tmp.name)
    con.execute(sql, params)
    con.commit(); con.close()
    with open(tmp.name, "rb") as f:
        nd = f.read()
    staging = DB_PATH + ".tmp"
    with open(staging, "wb") as f:
        f.write(nd); f.flush(); os.fsync(f.fileno())
    os.replace(staging, DB_PATH); os.unlink(tmp.name)
    st.cache_data.clear()


def render(ctx):
    wo = load_coco_wo()
    if wo.empty:
        st.info("No active COCO work orders in the database.")
        return
    monthly = ctx["monthly"]
    TA_NAME = ctx["TA_NAME"]

    # tiers + days remaining
    tiers = wo.apply(lambda r: coco_alert_tier(r["date_of_expiry"],
                                               r["date_of_appointment"]), axis=1)
    wo = wo.assign(tier=[t[0] for t in tiers],
                   tier_label=[t[1] for t in tiers])
    wo["days_left"] = wo["date_of_expiry"].map(
        lambda e: (pd.Timestamp(e) - pd.Timestamp.today().normalize()).days
        if (e is not None and pd.notna(e) and str(e).strip()) else None)

    # ── 1. Alert banner ────────────────────────────────────────────────────
    st.subheader("⚠️ Work-Order Alerts")
    chips = []
    for t in TIER_ORDER:
        sub = wo[wo.tier == t]
        n = len(sub)
        dim = "opacity:.35;" if n == 0 else ""
        names = " · ".join(sub["ro_name"].fillna(sub["sap_code"]).tolist()) or "none"
        chips.append(
            f'<span title="{names}" style="{dim}display:inline-block;margin:2px 6px 2px 0;'
            f'padding:6px 14px;border-radius:16px;background:{TIER_COLOR[t]};'
            f'color:#fff;font-weight:600;font-size:0.9rem;">'
            f'{TIER_LABEL[t]}: {n}</span>')
    st.markdown("".join(chips), unsafe_allow_html=True)
    urgent = wo[wo.tier.isin(["expired", "critical", "exp_crit"])]
    if not urgent.empty:
        with st.expander(f"🔔 {len(urgent)} COCO(s) need appointment action", expanded=True):
            for _, r in urgent.sort_values("days_left").iterrows():
                st.markdown(
                    f"- **{r['ro_name'] or r['sap_code']}** ({r['sap_code']}) — "
                    f"{r['tier_label']}, expiry {r['date_of_expiry'] or '—'} "
                    f"({r['days_left']} days), operator: {r['operator_name'] or '—'}")

    # ── 2. Sales performance ───────────────────────────────────────────────
    st.subheader("📊 Sales Performance")
    avail = available_months()
    if not avail:
        st.warning("No sales data."); return
    latest = avail[-1]
    lfy, lmi = latest["fy_code"], latest["month_index"]
    st.caption(f"Current month: **{latest['label']}** · CY cumulative: Apr → {latest['label']}")

    cur = monthly[(monthly.fy_code == lfy) & (monthly.month_index == lmi)]
    cy = monthly[(monthly.fy_code == lfy) & (monthly.month_index <= lmi)]

    rows = []
    for _, r in wo.iterrows():
        sap, ta = r["sap_code"], r["ta_code"]
        m_cur = cur[cur.sap_code == sap]
        m_cy = cy[cy.sap_code == sap]
        ms_m = m_cur[m_cur["product"] == "MS"].volume_kl.sum()
        hs_m = m_cur[m_cur["product"] == "HSD"].volume_kl.sum()
        ms_cy = m_cy[m_cy["product"] == "MS"].volume_kl.sum()
        hs_cy = m_cy[m_cy["product"] == "HSD"].volume_kl.sum()
        # TA average (IOCL ROs in same TA, current month, MS+HSD per RO)
        ta_cur = cur[(cur.ta_code == ta) & (cur.omc == "IOCL")]
        n_ta = ta_cur.sap_code.nunique()
        ta_avg = ta_cur.volume_kl.sum() / n_ta if n_ta else 0.0
        # Policy target: highest IOCL RO avg KLPM in TA, 12 months pre-appointment
        pol = None
        if pd.notna(r["date_of_appointment"]) and r["date_of_appointment"] \
                and pd.notna(ta) and ta:
            appt = pd.Timestamp(r["date_of_appointment"])
            months = [(appt - pd.DateOffset(months=i)) for i in range(1, 13)]
            keys = set()
            for d in months:
                fy_s = d.year if d.month >= 4 else d.year - 1
                keys.add((f"{fy_s}-{str(fy_s+1)[-2:]}", d.month - 3 if d.month >= 4 else d.month + 9))
            hist = monthly[(monthly.ta_code == ta) & (monthly.omc == "IOCL")]
            hist = hist[[k in keys for k in zip(hist.fy_code, hist.month_index)]]
            if not hist.empty:
                per_ro = hist.groupby("sap_code").volume_kl.sum() / 12.0
                per_ro = per_ro.drop(sap, errors="ignore")
                if not per_ro.empty:
                    pol = float(per_ro.max())
        tot_m = ms_m + hs_m
        rows.append({
            "SAP": sap, "COCO": r["ro_name"] or sap, "District": r["district"],
            "TA": TA_NAME.get(ta, r["trading_area"] or ""),
            "MS (mo)": ms_m, "HSD (mo)": hs_m,
            "MS CY": ms_cy, "HSD CY": hs_cy,
            "TA avg (mo)": ta_avg,
            "Policy Tgt (KLPM)": pol,
            "vs TA avg %": (tot_m / ta_avg - 1) * 100 if ta_avg else None,
            "vs Policy %": (tot_m / pol - 1) * 100 if pol else None,
        })
    perf = pd.DataFrame(rows)
    fmt = {c: (lambda v: indian(v, 1)) for c in
           ["MS (mo)", "HSD (mo)", "MS CY", "HSD CY", "TA avg (mo)", "Policy Tgt (KLPM)"]}
    fmt.update({c: (lambda v: pct(v, 1)) for c in ["vs TA avg %", "vs Policy %"]})
    st.dataframe(perf.style.format(fmt, na_rep="—"),
                 hide_index=True, use_container_width=True, height=600)
    df_download(perf, "coco_sales_perf")

    # TA-profile PPT view for a chosen COCO (re-uses Tab 05 logic)
    with st.expander("📋 Trading-Area view (PPT format) for a COCO"):
        pick = st.selectbox("COCO", perf["COCO"] + "  (" + perf["SAP"] + ")",
                            key="coco_ta_pick")
        sap = pick.split("(")[-1].rstrip(")")
        ta = wo.loc[wo.sap_code == sap, "ta_code"].iloc[0]
        if pd.notna(ta) and ta:
            df_g, tot = ta_volume_grid(monthly, ta, ctx["months"], ctx["cy"], ctx["ly"],
                                       ctx.get("cy_pairs") or None,
                                       ctx.get("ly_pairs") or None)
            st.markdown(render_ta_html(df_g, tot, ta, TA_NAME.get(ta, ""),
                                       ctx["period_lbl"]), unsafe_allow_html=True)
        else:
            st.info("This COCO has no TA code assigned in dim_ro.")

    # ── 3. Work-order status ───────────────────────────────────────────────
    st.subheader("📋 Work-Order Status")
    wo_view = wo.sort_values("days_left", na_position="last")[[
        "sap_code", "ro_name", "coco_type", "operation_mode", "operator_name",
        "operator_original_sap", "date_of_appointment", "wo_period_months",
        "date_of_expiry", "tier_label", "days_left"]].rename(columns={
        "sap_code": "SAP", "ro_name": "COCO", "coco_type": "Perm/Temp",
        "operation_mode": "Mode", "operator_name": "Dealer / Service Provider",
        "operator_original_sap": "Dealer's Own SAP",
        "date_of_appointment": "Appointed", "wo_period_months": "WO (months)",
        "date_of_expiry": "Expiry", "tier_label": "Alert", "days_left": "Days left"})
    def _row_style(row):
        c = TIER_COLOR.get({v: k for k, v in TIER_LABEL.items()}.get(row["Alert"], ""), "")
        return [f"color:{c};font-weight:700" if col == "Alert" else "" for col in row.index]
    st.dataframe(wo_view.style.apply(_row_style, axis=1), hide_index=True,
                 use_container_width=True, height=600)
    df_download(wo_view, "coco_work_orders")

    # ── 4. Detail panel ────────────────────────────────────────────────────
    with st.expander("🔎 COCO detail"):
        pick2 = st.selectbox("Select COCO", wo["ro_name"].fillna(wo["sap_code"])
                             + "  (" + wo["sap_code"] + ")", key="coco_detail_pick")
        sap2 = pick2.split("(")[-1].rstrip(")")
        det = wo[wo.sap_code == sap2].iloc[0]
        st.dataframe(detail_table(det), hide_index=True,
                     use_container_width=True, height=560)

    # ── Admin actions (require ingestion unlock) ───────────────────────────
    if st.session_state.get("ingest_auth"):
        st.divider(); st.subheader("🔐 Admin — COCO lifecycle")
        c1, c2 = st.columns(2)
        with c1, st.form("coco_add"):
            st.markdown("**Add COCO (conversion of existing RO)**")
            sap_new = st.text_input("SAP code of existing IOCL RO")
            ctype = st.selectbox("Type", ["Temporary", "Permanent"])
            mode = st.selectbox("Operation", ["Adhoc", "Service Provider"])
            op_name = st.text_input("Dealer / Service-provider name")
            op_sap = st.text_input("Dealer's original SAP (optional)")
            appt = st.date_input("Date of appointment")
            months = st.number_input("Work-order period (months)", 1, 60, 12)
            if st.form_submit_button("Add COCO"):
                exp = (pd.Timestamp(appt) + pd.DateOffset(months=int(months))
                       ).strftime("%Y-%m-%d")
                _wo_write("""INSERT INTO coco_work_orders
                    (sap_code, coco_type, operation_mode, operator_name,
                     operator_original_sap, date_of_appointment,
                     wo_period_months, date_of_expiry, status)
                    VALUES (?,?,?,?,?,?,?,?,'Active')""",
                    (sap_new.strip(), ctype, mode, op_name, op_sap or None,
                     pd.Timestamp(appt).strftime("%Y-%m-%d"), int(months), exp))
                _wo_write("UPDATE dim_ro SET coco_flag=1 WHERE sap_code=?",
                          (sap_new.strip(),))
                st.success(f"COCO added for {sap_new}."); st.rerun()
        with c2, st.form("coco_close"):
            st.markdown("**Mark Closed — Regularised**")
            pick3 = st.selectbox("COCO", wo["ro_name"].fillna(wo["sap_code"])
                                 + "  (" + wo["sap_code"] + ")")
            if st.form_submit_button("Close COCO"):
                sap3 = pick3.split("(")[-1].rstrip(")")
                _wo_write("""UPDATE coco_work_orders SET status='Closed',
                    closed_at=strftime('%Y-%m-%d','now')
                    WHERE sap_code=? AND status='Active'""", (sap3,))
                _wo_write("UPDATE dim_ro SET coco_flag=0 WHERE sap_code=?", (sap3,))
                st.success(f"{sap3} closed — history retained."); st.rerun()

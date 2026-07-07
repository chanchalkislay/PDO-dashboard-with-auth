"""Tab 18 — Swagat Monitoring (extended trading area + XP conversion + MoU).

Confirmed layout (HANDOFF_FOR_FABLE5.md):
  1. Swagat RO header card
  2. Extended-TA summary (OMC-wise, LHS/RHS, volumes, share)
  3. Extended-TA in PPT format (re-uses Tab 05 grid renderer)
  4. XtraPower conversion for IOCL ROs in the extended TA
  5. MoU % (Swagat growth vs extended-TA growth; PSU variant)
Multi-Swagat ready: selector appears when >1 Swagat exists.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st
from components.downloads import df_download

from core import (OMC_ORDER, PSU, available_months, indian, load_swagat_ext,
                  load_xtrapower, pct, render_ta_html)


def _vol(df, saps, product=None):
    d = df[df.sap_code.isin(saps)]
    if product:
        d = d[d["product"] == product]
    return d.volume_kl.sum()


def render(ctx):
    ext_all = load_swagat_ext()
    ro_master = ctx["ro_master"]
    monthly = ctx["monthly"]
    if ext_all.empty:
        st.info("No Swagat extended-TA data loaded."); return

    swagats = sorted(ext_all.swagat_sap_code.unique())
    if len(swagats) > 1:
        s_sap = st.selectbox("Swagat RO", swagats, key="swagat_pick")
    else:
        s_sap = swagats[0]
    ext = ext_all[ext_all.swagat_sap_code == s_sap]

    info = ro_master[ro_master.sap_code == s_sap]
    info = info.iloc[0] if not info.empty else None

    # ── 1. Header card ─────────────────────────────────────────────────────
    avail = available_months(); latest = avail[-1]
    lfy, lmi = latest["fy_code"], latest["month_index"]
    cur = monthly[(monthly.fy_code == lfy) & (monthly.month_index == lmi)]
    prv_fy, prv_mi = (lfy, lmi - 1) if lmi > 1 else (ctx["ly"], 12)
    prv = monthly[(monthly.fy_code == prv_fy) & (monthly.month_index == prv_mi)]
    ms_now = _vol(cur, [s_sap], "MS"); hs_now = _vol(cur, [s_sap], "HSD")
    ms_prv = _vol(prv, [s_sap], "MS"); hs_prv = _vol(prv, [s_sap], "HSD")

    name = info["ro_name"] if info is not None else s_sap
    st.markdown(
        f"### 🔵 {name}\n"
        f"**SAP** {s_sap} · **RSA** "
        f"{(info['rsa_name'] if info is not None and pd.notna(info['rsa_name']) else '—')} · "
        f"**Highway** "
        f"{(info['highway_no'] if info is not None and pd.notna(info['highway_no']) and str(info['highway_no']).strip() else '—')} · "
        f"Badge: **IOCL Swagat**")
    c1, c2, c3 = st.columns(3)
    c1.metric(f"MS {latest['label']} (KL)", indian(ms_now, 1),
              f"{ms_now - ms_prv:+.1f} MoM")
    c2.metric(f"HSD {latest['label']} (KL)", indian(hs_now, 1),
              f"{hs_now - hs_prv:+.1f} MoM")
    c3.metric("Extended TA ROs", f"{len(ext)} (LHS {len(ext[ext.side=='LHS'])} / "
                                 f"RHS {len(ext[ext.side=='RHS'])})")

    # scope: period frames restricted to extended-TA ROs
    saps = ext.ro_sap_code.tolist()
    cy_f = monthly[(monthly.fy_code == ctx["cy"])
                   & (monthly.month_index.isin(ctx["months"]))
                   & (monthly.sap_code.isin(saps))]
    ly_f = (monthly[(monthly.fy_code == ctx["ly"])
                    & (monthly.month_index.isin(ctx["months"]))
                    & (monthly.sap_code.isin(saps))]
            if ctx["ly"] else monthly.iloc[0:0])

    # ── 2. Extended-TA summary ─────────────────────────────────────────────
    st.subheader("🗺️ Extended Trading Area — OMC-wise")
    st.caption(f"Period: **{ctx['period_lbl']}** · CY {ctx['cy']}"
               f" · both MS and HSD shown")
    tot_all = cy_f.volume_kl.sum()
    rows = []
    for omc in OMC_ORDER:
        e = ext[ext.omc == omc]
        if e.empty: continue
        s_ = e.ro_sap_code.tolist()
        ms_v = _vol(cy_f, s_, "MS"); hs_v = _vol(cy_f, s_, "HSD")
        rows.append({"OMC": omc, "ROs": len(e),
                     "LHS": len(e[e.side == "LHS"]), "RHS": len(e[e.side == "RHS"]),
                     "MS (KL)": ms_v, "HSD (KL)": hs_v,
                     "Share %": ((ms_v + hs_v) / tot_all * 100) if tot_all else 0.0})
    summ = pd.DataFrame(rows)
    st.dataframe(summ.style.format({"MS (KL)": lambda v: indian(v, 1),
                                    "HSD (KL)": lambda v: indian(v, 1),
                                    "Share %": lambda v: pct(v, 1)}),
                 hide_index=True, use_container_width=True)
    df_download(summ, "swagat_ext_summary")
    missing = ext[~ext.ro_sap_code.isin(monthly.sap_code.unique())]
    if not missing.empty:
        st.caption(f"⚠️ {len(missing)} extended-TA RO code(s) not found in sales data "
                   f"(competitor codes outside dim_ro): "
                   + ", ".join(missing.ro_name.head(6)))

    # ── 3. Extended TA in PPT format ───────────────────────────────────────
    st.subheader("📋 Extended TA — PPT format")
    ros = (ext.rename(columns={"ro_sap_code": "sap_code"})
              [["sap_code", "ro_name", "omc", "side"]])
    def vol_map(frame, prod):
        d = frame[frame["product"] == prod]
        return d.groupby("sap_code").volume_kl.sum().to_dict()
    mcy, mly = vol_map(cy_f, "MS"), vol_map(ly_f, "MS")
    hcy, hly = vol_map(cy_f, "HSD"), vol_map(ly_f, "HSD")
    grid = []
    for r in ros.itertuples():
        nm = r.ro_name + (" ⭐" if r.sap_code == s_sap else "")
        grid.append(dict(ro=nm, loc=r.side, omc=r.omc,
                         ms_cy=float(mcy.get(r.sap_code, 0.0)),
                         ms_ly=float(mly.get(r.sap_code, 0.0)),
                         hs_cy=float(hcy.get(r.sap_code, 0.0)),
                         hs_ly=float(hly.get(r.sap_code, 0.0))))
    gdf = pd.DataFrame(grid)
    tot = dict(ms_cy=gdf.ms_cy.sum(), ms_ly=gdf.ms_ly.sum(),
               hs_cy=gdf.hs_cy.sum(), hs_ly=gdf.hs_ly.sum())
    st.markdown(render_ta_html(gdf, tot, "EXT", f"{name} — Extended TA (50+50 km)",
                               ctx["period_lbl"]), unsafe_allow_html=True)

    # ── 4. XP conversion (IOCL ROs) ────────────────────────────────────────
    st.subheader("🔋 XtraPower Conversion — IOCL ROs in Extended TA")
    xp = load_xtrapower()
    iocl_ext = ext[ext.omc == "IOCL"]
    if xp.empty or iocl_ext.empty:
        st.info("No XtraPower data for extended-TA IOCL ROs.")
    else:
        xrows = []
        for r in iocl_ext.itertuples():
            sap = r.ro_sap_code
            x = xp[xp.sap_code == sap]
            x_m  = x[(x.fy_code == lfy) & (x.month_index == lmi)]
            x_cy = x[(x.fy_code == ctx["cy"]) & (x.month_index.isin(ctx["months"]))]
            x_ly = x[(x.fy_code == ctx["ly"]) & (x.month_index.isin(ctx["months"]))] \
                   if ctx["ly"] else x.iloc[0:0]
            def conv(fr):
                h, xk = fr.hsd_kl.sum(), fr.xp_kl.sum()
                return xk, (xk / h * 100 if h else 0.0)
            xm, cm = conv(x_m); xc, cc = conv(x_cy); xl_, cl = conv(x_ly)
            xrows.append({
                "RO": r.ro_name + (" ⭐" if sap == s_sap else ""), "Side": r.side,
                "Mo XP (KL)": xm, "Mo %Conv": cm,
                "CUM.CY XP (KL)": xc, "CUM.CY %Conv": cc,
                "CUM.LY XP (KL)": xl_, "CUM.LY %Conv": cl,
                "Cum +/- KL": xc - xl_, "Cum +/- %Conv": cc - cl})
        xdf = pd.DataFrame(xrows)
        xdf = pd.concat([xdf[xdf["RO"].str.contains("⭐")],
                         xdf[~xdf["RO"].str.contains("⭐")]])
        numc = [c for c in xdf.columns if c not in ("RO", "Side")]
        st.dataframe(xdf.style.format({c: (lambda v: indian(v, 1)) if "KL" in c
                                       else (lambda v: pct(v, 1)) for c in numc}),
                     hide_index=True, use_container_width=True)
        df_download(xdf, "swagat_xp_conversion")

    # ── 5. MoU performance ─────────────────────────────────────────────────
    st.subheader("📈 MoU Performance (growth vs Extended TA)")
    def growth(cy_v, ly_v):
        return ((cy_v - ly_v) / ly_v * 100) if ly_v else None
    sw_g  = growth(_vol(cy_f, [s_sap]), _vol(ly_f, [s_sap]))
    ta_g  = growth(cy_f.volume_kl.sum(), ly_f.volume_kl.sum())
    psu_saps = ext[ext.omc.isin(PSU)].ro_sap_code.tolist()
    psu_g = growth(_vol(cy_f, psu_saps), _vol(ly_f, psu_saps))
    c1, c2, c3 = st.columns(3)
    c1.metric("Swagat growth %", pct(sw_g, 2) if sw_g is not None else "—")
    c2.metric("MoU % (vs whole ext. TA)",
              pct(sw_g - ta_g, 2) if None not in (sw_g, ta_g) else "—",
              help="Swagat growth − Extended-TA growth. Positive = outperforming.")
    c3.metric("PSU MoU % (vs PSU-only ext. TA)",
              pct(sw_g - psu_g, 2) if None not in (sw_g, psu_g) else "—")

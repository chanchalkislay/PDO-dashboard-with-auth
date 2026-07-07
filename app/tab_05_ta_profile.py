"""Tab 5 — TA Profile (PPT): full per-RO grid in PPT 'Top TA' layout."""
import streamlit as st
from core import (share_frame, totals_row, ta_volume_grid, render_ta_html,
                  OMC_ORDER, PSU, PVT, COM_LABELS, pct, pp, indian)


def render(ctx):
    monthly    = ctx["monthly"]
    ro_master  = ctx["ro_master"]
    ta_dim     = ctx["ta_dim"]
    cy         = ctx["cy"]
    ly         = ctx["ly"]
    months     = ctx["months"]
    period_lbl = ctx["period_lbl"]
    product    = ctx["product"]
    TA_NAME    = ctx["TA_NAME"]
    rsa_labels = ctx["rsa_labels"]
    districts  = ctx["districts"]
    coms       = ctx["coms"]
    hwy_nums   = ctx["hwy_nums"]

    multi_fy_mode = ctx.get("multi_fy_mode", False)
    cy_pairs      = ctx.get("cy_pairs", frozenset())
    ly_pairs      = ctx.get("ly_pairs", frozenset())

    st.caption("Self-contained: the selected TA's full RO list (all OMCs, both "
               "products) is shown regardless of the sidebar District/COM/Highway "
               "filters, for the chosen period. LY uses the same months of "
               f"{ly or '—'}.")

    # Denominator for ranking mode share computations
    universe = st.radio("Ranking denominator", ["Industry", "PSU"],
                        horizontal=True, key="tap_univ",
                        help="Applies to the Top-Bottom ranking share calculations. "
                             "The PPT grid always shows full TA shares (all OMCs).")
    uset = OMC_ORDER if universe == "Industry" else PSU

    mode = st.radio("Find a Trading Area by",
                    ["Name / attribute filter", "Top–Bottom ranking"],
                    horizontal=True, key="tap_mode")
    ta = None

    if mode == "Name / attribute filter":
        def _clear_tap_filters():
            for k in ("tap_rsa", "tap_dist", "tap_com", "tap_nh"):
                st.session_state[k] = []

        c1, c2, c3, c4 = st.columns(4)
        f_rsa  = c1.multiselect("Sales Area (RSA)", list(rsa_labels), key="tap_rsa")
        f_dist = c2.multiselect("District", districts, key="tap_dist")
        f_com  = c3.multiselect("COM", coms,
                                format_func=lambda c: COM_LABELS[c], key="tap_com")
        f_nh   = c4.multiselect("NH/SH number", hwy_nums, key="tap_nh")

        if f_rsa or f_dist or f_com or f_nh:
            _, _cb = st.columns([5, 1])
            _cb.button("✕ Clear all filters", on_click=_clear_tap_filters,
                       key="tap_clear", use_container_width=True)

        cand = ro_master
        if f_rsa:
            cand = cand[cand.rsa_code.isin([rsa_labels[l] for l in f_rsa])]
        if f_dist:
            cand = cand[cand.district.isin(f_dist)]
        if f_com:
            cand = cand[cand.com.isin(f_com)]
        if f_nh:
            cand = cand[cand.highway_no.isin(f_nh)]
        ta_codes = sorted(cand.ta_code.dropna().unique())
        opts = {f"{t} — {TA_NAME.get(t, '')}": t for t in ta_codes}
        st.caption(f"{len(opts)} trading areas match")
        if opts:
            ta = opts[st.selectbox("Trading Area", list(opts), key="tap_pick_n")]
        else:
            st.info("No trading area matches these attribute filters.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        rmetric   = c1.selectbox("Rank by", ["IOCL share growth (pp)",
                                              "IOCL volume (KL)"], key="tap_metric")
        direction = c2.selectbox("Show", ["Top", "Bottom"], key="tap_dir")
        within    = c3.selectbox("Within", ["Whole DO", "District", "RSA", "COM",
                                            "NH/SH number"], key="tap_within")
        pool = monthly
        if within == "District":
            pool = pool[pool.district == c4.selectbox("District", districts,
                                                      key="tap_wd")]
        elif within == "RSA":
            rl = c4.selectbox("RSA", list(rsa_labels), key="tap_wr")
            pool = pool[pool.rsa_code == rsa_labels[rl]]
        elif within == "COM":
            pool = pool[pool.com == c4.selectbox(
                "COM", coms, format_func=lambda c: COM_LABELS[c], key="tap_wc")]
        elif within == "NH/SH number":
            pool = pool[pool.highway_no == c4.selectbox("NH/SH", hwy_nums,
                                                        key="tap_wn")]
        if multi_fy_mode and cy_pairs:
            _fymi = pool.fy_code + "_" + pool.month_index.astype(str)
            _ck   = {f"{f}_{m}" for f, m in cy_pairs}
            _lk   = {f"{f}_{m}" for f, m in ly_pairs}
            cyp = pool[_fymi.isin(_ck) & (pool["product"] == product)]
            lyp = pool[_fymi.isin(_lk) & (pool["product"] == product)] if ly_pairs else pool.iloc[0:0]
        else:
            cyp = pool[(pool.fy_code == cy) & (pool["product"] == product)
                       & (pool.month_index.isin(months))]
            lyp = (pool[(pool.fy_code == ly) & (pool["product"] == product)
                        & (pool.month_index.isin(months))] if ly else pool.iloc[0:0])
        rsf   = share_frame(cyp, lyp, ["ta_code"], uset)
        mcol  = "IOCL_ppt" if rmetric.startswith("IOCL share") else "IOCL_cyvol"
        rsf   = rsf.sort_values(mcol, ascending=(direction == "Bottom"))
        n     = st.slider("List size", 5, 30, 15, key="tap_n")
        rsf   = rsf.head(n)
        st.caption(f"{direction} {len(rsf)} TAs by {rmetric} "
                   f"({product}, {period_lbl}) within {within} [{universe} denom.]")
        opts = {}
        for r in rsf.itertuples():
            v   = getattr(r, mcol)
            tag = pp(v) + " pp" if "ppt" in mcol else indian(v, 1) + " KL"
            opts[f"{r.ta_code} — {TA_NAME.get(r.ta_code, '')}  ·  {tag}"] = r.ta_code
        if opts:
            ta = opts[st.selectbox("Trading Area", list(opts), key="tap_pick_r")]
        else:
            st.info("No trading areas in this ranking scope.")

    if ta:
        st.markdown(f"### {ta} — {TA_NAME.get(ta, '')}")

        # 1 - network-outlet profile
        trow = ta_dim[ta_dim.ta_code == ta]
        prof_rows = []
        for omc, key in [("IOCL", "iocl"), ("BPCL", "bpcl"), ("HPCL", "hpcl"),
                         ("NEL", "nel"), ("RBML", "rbml"), ("SIMPL", "simpl")]:
            ms  = int(trow[f"cnt_{key}_ms"].iloc[0])  if not trow.empty else 0
            hsd = int(trow[f"cnt_{key}_hsd"].iloc[0]) if not trow.empty else 0
            prof_rows.append({"OMC": omc, "MS outlets": ms, "HSD outlets": hsd})
        import pandas as pd
        prof = pd.DataFrame(prof_rows)
        prof.loc[len(prof)] = ["TOTAL", prof["MS outlets"].sum(),
                               prof["HSD outlets"].sum()]
        cprof, ck1, ck2 = st.columns([2, 1, 1])
        cprof.markdown("**Network outlets**")
        cprof.dataframe(prof, hide_index=True, use_container_width=True)
        ta_all = monthly[monthly.ta_code == ta]
        for prod, kcol in [("MS", ck1), ("HSD", ck2)]:
            if multi_fy_mode and cy_pairs:
                _fymi = ta_all.fy_code + "_" + ta_all.month_index.astype(str)
                _ck   = {f"{f}_{m}" for f, m in cy_pairs}
                _lk   = {f"{f}_{m}" for f, m in ly_pairs}
                _cy_ta = ta_all[_fymi.isin(_ck) & (ta_all["product"] == prod)]
                _ly_ta = ta_all[_fymi.isin(_lk) & (ta_all["product"] == prod)] if ly_pairs else ta_all.iloc[0:0]
            else:
                _cy_ta = ta_all[(ta_all.fy_code == cy) & (ta_all["product"] == prod)
                                & (ta_all.month_index.isin(months))]
                _ly_ta = (ta_all[(ta_all.fy_code == ly) & (ta_all["product"] == prod)
                                 & (ta_all.month_index.isin(months))]
                          if ly else ta_all.iloc[0:0])
            tcy = totals_row(_cy_ta, _ly_ta, OMC_ORDER)
            kcol.metric(f"IOCL {prod} share (TA)", pct(tcy["IOCL_cyshare"]),
                        pp(tcy["IOCL_ppt"]) + " pp")

        # 2 - PPT grid (always full TA / all OMCs)
        st.markdown("**Top Trading Area by Volume in Industry**")
        if multi_fy_mode and cy_pairs:
            gdf, gtot = ta_volume_grid(monthly, ta, months, cy, ly,
                                       cy_pairs=cy_pairs, ly_pairs=ly_pairs)
        else:
            gdf, gtot = ta_volume_grid(monthly, ta, months, cy, ly)
        if gdf.empty or (gtot["ms_cy"] == 0 and gtot["hs_cy"] == 0):
            st.info("No sales recorded in this TA for the selected period.")
        else:
            html = render_ta_html(gdf, gtot, ta, TA_NAME.get(ta, ""), period_lbl)
            st.markdown(
                f'<div class="pdo-ta-scroll">{html}</div>',
                unsafe_allow_html=True,
            )

            # ── Excel download ────────────────────────────────────────────────
            import io
            import pandas as pd

            def _ta_xlsx(gdf, gtot, ta_code, ta_name, period_lbl):
                """Tabular Excel export of the TA grid data."""
                OMC_SEQ = ["IOCL", "BPCL", "HPCL", "NEL", "RBML", "SIMPL"]

                def _blk(cy, ly, tcy, tly):
                    diff = round(cy - ly, 1)
                    gr   = f"{diff/ly*100:.2f}%" if ly else "—"
                    scy  = round(cy/tcy*100, 2) if tcy else 0.0
                    sly  = round(ly/tly*100, 2) if tly else 0.0
                    sgr  = round(scy - sly, 2)
                    notv = round(sgr/100*tcy, 1)
                    return round(cy, 1), round(ly, 1), diff, gr, scy, sly, sgr, notv

                hdrs = [
                    "S.No", "Name of RO", "Location", "Oil Co",
                    "MS CY (KL)", "MS LY (KL)", "MS +/-", "MS GR%",
                    "HSD CY (KL)", "HSD LY (KL)", "HSD +/-", "HSD GR%",
                    "MS Shr CY%", "MS Shr LY%", "MS ±pp", "MS Not(KL)",
                    "HSD Shr CY%", "HSD Shr LY%", "HSD ±pp", "HSD Not(KL)",
                ]

                rows_out = []
                gdf2 = gdf.copy()
                gdf2["tot_cy"] = gdf2["ms_cy"] + gdf2["hs_cy"]
                gdf2["_rank"] = gdf2.omc.map(
                    {o: i for i, o in enumerate(OMC_SEQ)}).fillna(99)
                gdf2 = gdf2.sort_values(["_rank", "tot_cy"],
                                        ascending=[True, False])

                sn = 0
                for r in gdf2.itertuples():
                    sn += 1
                    ms = _blk(r.ms_cy, r.ms_ly, gtot["ms_cy"], gtot["ms_ly"])
                    hs = _blk(r.hs_cy, r.hs_ly, gtot["hs_cy"], gtot["hs_ly"])
                    rows_out.append([sn, r.ro, r.loc, r.omc] + list(ms) + list(hs))

                # OMC subtotals
                for omc in OMC_SEQ:
                    sub = gdf2[gdf2.omc == omc]
                    if sub.empty:
                        continue
                    ms = _blk(sub.ms_cy.sum(), sub.ms_ly.sum(),
                              gtot["ms_cy"], gtot["ms_ly"])
                    hs = _blk(sub.hs_cy.sum(), sub.hs_ly.sum(),
                              gtot["hs_cy"], gtot["hs_ly"])
                    rows_out.append(
                        ["", f"{omc} Sub Total", f"Total ROs: {len(sub)}", ""]
                        + list(ms) + list(hs))

                # Grand totals
                PSU = ["IOCL", "BPCL", "HPCL"]
                PVT = ["NEL", "RBML", "SIMPL"]
                for label, grp in [("Total PSU", PSU),
                                    ("Total Pvt.", PVT),
                                    ("Total Industry", OMC_SEQ)]:
                    sub = gdf2[gdf2.omc.isin(grp)]
                    ms = _blk(sub.ms_cy.sum(), sub.ms_ly.sum(),
                              gtot["ms_cy"], gtot["ms_ly"])
                    hs = _blk(sub.hs_cy.sum(), sub.hs_ly.sum(),
                              gtot["hs_cy"], gtot["hs_ly"])
                    rows_out.append(["", label, "", ""] + list(ms) + list(hs))

                # Average
                n = max(len(gdf2), 1)
                ms = _blk(gtot["ms_cy"]/n, gtot["ms_ly"]/n,
                          gtot["ms_cy"], gtot["ms_ly"])
                hs = _blk(gtot["hs_cy"]/n, gtot["hs_ly"]/n,
                          gtot["hs_cy"], gtot["hs_ly"])
                rows_out.append(["", "TA Average", "", "Avg"] + list(ms) + list(hs))

                df_out = pd.DataFrame(rows_out, columns=hdrs)

                # Write to xlsx
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    df_out.to_excel(writer, index=False, sheet_name=ta_code[:30])
                    ws = writer.sheets[ta_code[:30]]
                    # Bold header row + subtotal/total rows
                    from openpyxl.styles import Font
                    for cell in ws[1]:
                        cell.font = Font(bold=True)
                    for row_idx, row_data in enumerate(rows_out, start=2):
                        if isinstance(row_data[0], str) and row_data[0] == "":
                            for cell in ws[row_idx]:
                                cell.font = Font(bold=True)
                    # Auto-width
                    for col in ws.columns:
                        max_len = max(
                            len(str(cell.value or "")) for cell in col)
                        ws.column_dimensions[
                            col[0].column_letter].width = min(max_len + 2, 35)
                return buf.getvalue()

            xlsx_bytes = _ta_xlsx(gdf, gtot, ta,
                                  TA_NAME.get(ta, ""), period_lbl)
            st.download_button(
                label="⬇ Download table as Excel (.xlsx)",
                data=xlsx_bytes,
                file_name=f"TA_{ta}_{cy}_{period_lbl}.xlsx".replace(" ", "_"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"ta_dl_{ta}",
            )

        # 3 - Action plan shell
        st.markdown("**Remarks on Performance in TA / Action plan**")
        st.info("Target / MoU / commissioning data is Tier-2 (not in pune_do.db). "
                "Use this space to record planned interventions: NRO/RRO "
                "commissioning, facility upgrades, XtraPower push, competitor "
                "watch. Populate once the target sheets are loaded.")

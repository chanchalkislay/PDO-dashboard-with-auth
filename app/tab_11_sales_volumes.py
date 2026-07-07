"""Tab 11 — Sales Volumes: RO-level flat table, Excel-style view.

Volume type selector covers all product layers:
  MS / HSD             — from fact_monthly (mother volumes)
  XP95 / XP100 / XG   — from fact_branded_monthly (specific brand)
  Branded MS           — all branded MS brands summed per RO×month
  Branded HSD          — all branded HSD brands summed per RO×month
  Plain MS             — Mother MS minus all branded MS (floor 0)
  Plain HSD            — Mother HSD minus all branded HSD (floor 0)

Controls: Volume type · OMC · RSA (independent of sidebar RSA filter) · Sort
Download: Excel (.xlsx)
"""
import io
import streamlit as st
from components.downloads import df_download
import pandas as pd
from core import OMC_ORDER, MONTHS, indian


VOL_OPTIONS = [
    "MS", "HSD",
    "XP95", "XP100", "XG",
    "Branded MS", "Branded HSD",
    "Plain MS", "Plain HSD",
]

_VOL_HELP = (
    "**MS / HSD** — total mother volumes from fact_monthly.  "
    "**XP95 / XP100 / XG** — specific branded product (IOCL; other OMCs show 0).  "
    "**Branded MS / HSD** — sum of all branded volumes for each OMC.  "
    "**Plain MS / HSD** — Mother minus all branded (floor 0); "
    "non-branded OMCs (NEL/RBML/SIMPL) show full mother volume."
)


def render(ctx):
    scope         = ctx["scope"]           # geo-filtered fact_monthly (all products, all FYs)
    branded_scope = ctx["branded_scope"]   # geo-filtered fact_branded_monthly (all FYs)
    ro_scope      = ctx["ro_scope"]
    cy            = ctx["cy"]
    ly            = ctx["ly"]
    months        = ctx["months"]
    period_lbl    = ctx["period_lbl"]
    TA_NAME       = ctx["TA_NAME"]

    st.markdown("#### Sales Volumes — RO Level Detail")
    st.caption("One row per outlet. Fixed info columns + monthly CY / LY / Δ triplets. "
               "Sidebar geo-filters apply. RSA and Volume type are independent in-tab controls.")

    # ── Controls ──────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([2, 2, 2])
    vol_product  = c1.selectbox("Volume type", VOL_OPTIONS,
                                key="vol_product_sel", help=_VOL_HELP)
    sel_omcs     = c2.multiselect("OMC", OMC_ORDER, default=["IOCL"], key="vol_omcs")
    rsa_opts     = sorted(ro_scope["rsa_name"].dropna().unique().tolist())
    sel_rsa      = c3.multiselect("RSA", rsa_opts, default=[], key="vol_rsa",
                                   help="Further filter by RSA — independent of the sidebar RSA filter")

    vol_sort = st.radio("Sort by", ["RSA", "Total CY ↓", "RO Name", "OMC"],
                        horizontal=True, key="vol_sort")

    if not sel_omcs:
        st.info("Select at least one OMC.")
        return

    sorted_months = sorted(months)

    # ── RO list: apply OMC + in-tab RSA filter ────────────────────────────────
    ro_v = ro_scope[ro_scope.omc.isin(sel_omcs)]
    if sel_rsa:
        ro_v = ro_v[ro_v.rsa_name.isin(sel_rsa)]

    all_saps = ro_v["sap_code"].drop_duplicates().tolist()
    n_ro     = len(all_saps)
    st.caption(f"**{vol_product}** · CY {cy} vs LY {ly or '—'} · {period_lbl} · "
               f"{n_ro} outlets in scope · Volumes in KL (1 dp)")

    # ── Volume data loader ────────────────────────────────────────────────────
    def _get_vol(fy_code):
        """Long-format DataFrame (sap_code, month_index, volume_kl) for one FY."""
        if not fy_code:
            return pd.DataFrame(columns=["sap_code", "month_index", "volume_kl"])

        bs = scope[
            scope.fy_code.eq(fy_code)
            & scope.month_index.isin(sorted_months)
            & scope.omc.isin(sel_omcs)
        ]
        bb = branded_scope[
            branded_scope.fy_code.eq(fy_code)
            & branded_scope.month_index.isin(sorted_months)
            & branded_scope.omc.isin(sel_omcs)
        ]
        # In-tab RSA filter on both frames
        if sel_rsa:
            bs = bs[bs.rsa_name.isin(sel_rsa)]
            if "rsa_name" in bb.columns:
                bb = bb[bb.rsa_name.isin(sel_rsa)]

        def _agg(df):
            if df.empty:
                return pd.DataFrame(columns=["sap_code", "month_index", "volume_kl"])
            return (df.groupby(["sap_code", "month_index"])["volume_kl"]
                      .sum().reset_index())

        if vol_product == "MS":
            return _agg(bs[bs["product"] == "MS"])

        if vol_product == "HSD":
            return _agg(bs[bs["product"] == "HSD"])

        if vol_product in ("XP95", "XP100", "XG"):
            return _agg(bb[bb.brand == vol_product])

        if vol_product == "Branded MS":
            return _agg(bb[bb["product"] == "MS"])

        if vol_product == "Branded HSD":
            return _agg(bb[bb["product"] == "HSD"])

        # Plain MS: Mother MS − all branded MS per RO×month (floor 0)
        if vol_product == "Plain MS":
            m = _agg(bs[bs["product"] == "MS"]).set_index(
                ["sap_code", "month_index"])["volume_kl"]
            b = _agg(bb[bb["product"] == "MS"]).set_index(
                ["sap_code", "month_index"])["volume_kl"]
            b = b.reindex(m.index, fill_value=0.0)
            plain = (m - b).clip(lower=0).reset_index()
            plain.columns = ["sap_code", "month_index", "volume_kl"]
            return plain

        # Plain HSD: Mother HSD − all branded HSD per RO×month (floor 0)
        if vol_product == "Plain HSD":
            m = _agg(bs[bs["product"] == "HSD"]).set_index(
                ["sap_code", "month_index"])["volume_kl"]
            b = _agg(bb[bb["product"] == "HSD"]).set_index(
                ["sap_code", "month_index"])["volume_kl"]
            b = b.reindex(m.index, fill_value=0.0)
            plain = (m - b).clip(lower=0).reset_index()
            plain.columns = ["sap_code", "month_index", "volume_kl"]
            return plain

        return pd.DataFrame(columns=["sap_code", "month_index", "volume_kl"])

    cy_v = _get_vol(cy)
    ly_v = _get_vol(ly) if ly else pd.DataFrame(
        columns=["sap_code", "month_index", "volume_kl"])

    # ── Pivot to wide (sap_code × month_index) ────────────────────────────────
    def _wide(df):
        if df.empty:
            return pd.DataFrame(columns=sorted_months,
                                index=pd.Index([], name="sap_code"), dtype=float)
        p = (df.groupby(["sap_code", "month_index"])["volume_kl"]
               .sum().unstack("month_index", fill_value=0.0))
        return p.reindex(columns=sorted_months, fill_value=0.0)

    cy_wide = _wide(cy_v).reindex(all_saps, fill_value=0.0)
    ly_wide = _wide(ly_v).reindex(all_saps, fill_value=0.0)

    # ── RO master attributes ──────────────────────────────────────────────────
    ro_attr = (ro_v[["sap_code", "ro_name", "omc", "district",
                      "com", "highway_no", "rsa_name", "ta_code"]]
               .drop_duplicates("sap_code").set_index("sap_code"))

    tbl = pd.DataFrame(index=pd.Index(all_saps, name="sap_code"))
    tbl["SAP Code"]    = all_saps
    tbl["Name of RO"]  = ro_attr["ro_name"].reindex(all_saps).fillna("—")
    tbl["Location"]    = ro_attr["district"].reindex(all_saps).fillna("—")
    tbl["COM"]         = ro_attr["com"].reindex(all_saps).fillna("")
    tbl["Highway No"]  = ro_attr["highway_no"].reindex(all_saps).fillna("")
    tbl["RSA"]         = ro_attr["rsa_name"].reindex(all_saps).fillna("—")
    tbl["Trading Area"] = (ro_attr["ta_code"].reindex(all_saps)
                           .map(TA_NAME).fillna(""))
    if len(sel_omcs) > 1:
        tbl.insert(1, "OMC", ro_attr["omc"].reindex(all_saps).fillna("—"))

    # ── Monthly columns ───────────────────────────────────────────────────────
    for mi in sorted_months:
        m     = MONTHS[mi - 1]
        cy_col = cy_wide[mi].round(1)
        tbl[f"{m} CY"] = cy_col
        if ly:
            ly_col = ly_wide[mi].round(1)
            tbl[f"{m} LY"] = ly_col
            tbl[f"{m} Δ"]  = (cy_col - ly_col).round(1)

    # ── Totals columns ────────────────────────────────────────────────────────
    tbl["Total CY"] = cy_wide[sorted_months].sum(axis=1).round(1)
    if ly:
        tbl["Total LY"] = ly_wide[sorted_months].sum(axis=1).round(1)
        tbl["Total Δ"]  = (tbl["Total CY"] - tbl["Total LY"]).round(1)

    tbl = tbl.reset_index(drop=True)

    # ── Sort ──────────────────────────────────────────────────────────────────
    sort_map = {
        "RSA":       (["RSA", "Name of RO"],    [True, True]),
        "Total CY ↓":(["Total CY"],             [False]),
        "RO Name":   (["Name of RO"],           [True]),
        "OMC":       (["OMC", "RSA", "Name of RO"]
                      if len(sel_omcs) > 1 else ["RSA", "Name of RO"],
                      [True, True, True]),
    }
    scols, sasc = sort_map.get(vol_sort, sort_map["RSA"])
    sasc = (sasc + [True] * len(scols))[:len(scols)]
    valid = [c for c in scols if c in tbl.columns]
    tbl = tbl.sort_values(valid, ascending=sasc[:len(valid)]).reset_index(drop=True)

    # ── Totals row ────────────────────────────────────────────────────────────
    vol_cols = [c for c in tbl.columns
                if c.startswith("Total") or any(
                    c.startswith(MONTHS[mi - 1]) for mi in sorted_months)]
    tot_row = {c: "" for c in tbl.columns}
    tot_row["Name of RO"] = "TOTAL"
    for c in vol_cols:
        if pd.api.types.is_numeric_dtype(tbl[c]):
            tot_row[c] = round(tbl[c].sum(), 1)
    tbl = pd.concat([tbl, pd.DataFrame([tot_row])], ignore_index=True)

    # ── Display ───────────────────────────────────────────────────────────────
    st.dataframe(tbl, hide_index=True, use_container_width=True, height=600)
    df_download(tbl, "t11_1")

    # ── Excel download ────────────────────────────────────────────────────────
    def _to_xlsx(df):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Sales Volumes")
        return buf.getvalue()

    rsa_tag  = ("_" + "_".join(sel_rsa)) if sel_rsa else ""
    omc_tag  = "_".join(sel_omcs)
    filename = (f"sales_{vol_product}_{omc_tag}{rsa_tag}_{cy}_{period_lbl}.xlsx"
                .replace(" ", "_").replace("→", "-").replace("/", "-"))

    st.download_button(
        label="⬇ Download as Excel (.xlsx)",
        data=_to_xlsx(tbl),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="vol_dl_xlsx",
    )

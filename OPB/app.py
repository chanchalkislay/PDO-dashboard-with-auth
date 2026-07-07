import sys
import os
import pandas as pd
from fastapi import FastAPI, Request, Query
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Setup sys.path to import core from app folder
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PROJ_ROOT, "app"))
sys.path.insert(0, PROJ_ROOT)

import core

app = FastAPI(title="Pune DO Dashboard - Option B Trial")
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))

# Define custom filters for Jinja2 template formatting
def format_indian_filter(val, dec=0):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    return core.indian(val, dec)

def format_pct_filter(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    return f"{val:.2f}%"

def format_pp_filter(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}"

def format_gr_filter(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    arrow = "↑ " if val > 0 else ("↓ " if val < 0 else "")
    return f"{arrow}{abs(val):.2f}%"

def get_growth_class_filter(val):
    if val is None or (isinstance(val, float) and pd.isna(val)) or val == 0:
        return ""
    return "text-emerald-400 font-semibold" if val > 0 else "text-rose-400 font-semibold"

# Register filters in Jinja2
templates.env.filters["indian"] = format_indian_filter
templates.env.filters["pct"] = format_pct_filter
templates.env.filters["pp"] = format_pp_filter
templates.env.filters["gr"] = format_gr_filter
templates.env.filters["growth_class"] = get_growth_class_filter

def parse_filters(request: Request):
    q = request.query_params
    product = q.get("product", "MS")
    cy = q.get("cy", "2025-26")
    ly = q.get("ly", "2024-25")
    
    # Months mapping
    months_str = q.get("months", "1,2,3,4,5,6,7,8,9,10,11,12")
    months_list = [int(m) for m in months_str.split(",") if m]
    
    # Selected filters (single value for trial simplicity, list-backed)
    sel_dist = q.getlist("district")
    sel_rsa = q.getlist("rsa")
    sel_com = q.getlist("com")
    
    # Load and filter
    monthly = core.load_monthly()
    ro_master = core.load_ro_master()
    
    # Apply filters
    def apply_filt(df):
        m = pd.Series(True, index=df.index)
        if sel_dist: m &= df.district.isin(sel_dist)
        if sel_rsa: m &= df.rsa_code.isin(sel_rsa)
        if sel_com: m &= df.com.isin(sel_com)
        return df[m]
        
    scope = apply_filt(monthly)
    ro_scope = apply_filt(ro_master)
    
    cy_f = scope[(scope.fy_code == cy) & (scope["product"] == product) & (scope.month_index.isin(months_list))]
    ly_f = scope[(scope.fy_code == ly) & (scope["product"] == product) & (scope.month_index.isin(months_list))] if ly else scope.iloc[0:0]
    
    return {
        "product": product,
        "cy": cy,
        "ly": ly,
        "months": months_list,
        "sel_dist": sel_dist,
        "sel_rsa": sel_rsa,
        "sel_com": sel_com,
        "cy_f": cy_f,
        "ly_f": ly_f,
        "ro_scope": ro_scope,
        "n_months": max(len(months_list), 1)
    }

def get_shared_context(request: Request):
    # Fetch filter options to render sidebar select tags
    ro = core.load_ro_master()
    ta = core.load_ta_dim()
    fys = core.fy_list()
    
    districts = sorted(ro.district.dropna().unique().tolist())
    rsa_unique = ro[["rsa_code", "rsa_name"]].dropna().drop_duplicates()
    rsas = [{"code": r.rsa_code, "name": r.rsa_name} for r in rsa_unique.itertuples()]
    coms = sorted(ro.com.dropna().unique().tolist())
    
    # TAs
    tas = [{"code": t.ta_code, "name": t.ta_name_canonical} for t in ta.itertuples()]
    
    return {
        "districts": districts,
        "rsas": rsas,
        "coms": coms,
        "tas": tas,
        "fys": fys
    }

@app.get("/")
@app.get("/overview")
def overview(request: Request):
    f = parse_filters(request)
    shared = get_shared_context(request)
    universe = request.query_params.get("universe", "Industry")
    
    uset = core.OMC_ORDER if universe == "Industry" else core.PSU
    ind = core.totals_row(f["cy_f"], f["ly_f"], uset)
    psu_row = core.totals_row(f["cy_f"], f["ly_f"], core.PSU)
    
    # Network outlets
    iocl_net = int(f["ro_scope"][f["ro_scope"].omc == "IOCL"].sap_code.nunique())
    iocl_ly_net = iocl_net
    iocl_klpm_cy = core.klpm(ind["IOCL_cyvol"], f["n_months"], iocl_net)
    iocl_klpm_ly = core.klpm(ind["IOCL_lyvol"], f["n_months"], iocl_ly_net)
    
    kpis = {
        "iocl_vol_cy": ind["IOCL_cyvol"],
        "iocl_gr": ind["IOCL_gr"],
        "iocl_share_cy": ind["IOCL_cyshare"],
        "iocl_share_ppt": ind["IOCL_ppt"],
        "iocl_psu_share_cy": psu_row["IOCL_cyshare"] if universe == "Industry" else ind["BPCL_cyshare"],
        "iocl_psu_share_ppt": psu_row["IOCL_ppt"] if universe == "Industry" else ind["BPCL_ppt"],
        "iocl_klpm_cy": iocl_klpm_cy,
        "iocl_klpm_diff": iocl_klpm_cy - iocl_klpm_ly,
        "iocl_outlets": iocl_net
    }
    
    # OMC Breakdown Table
    last_cy_fy = f["cy"]
    last_cy_mi = int(f["cy_f"].month_index.max()) if not f["cy_f"].empty else None
    last_ly_fy = f["ly"]
    last_ly_mi = int(f["ly_f"].month_index.max()) if not f["ly_f"].empty else None
    
    def ppt_ro_count(fact_f, omc, last_fy, last_mi):
        if last_fy is None or last_mi is None or fact_f.empty:
            return 0
        sub = fact_f[(fact_f.omc == omc) & (fact_f.fy_code == last_fy) & (fact_f.month_index == last_mi)]
        return int(sub.sap_code.nunique())
        
    table_rows = []
    total_cy_vol = 0.0
    total_ly_vol = 0.0
    total_ros_cy = 0
    total_ros_ly = 0
    
    for omc in uset:
        cy_vol = float(ind[f"{omc}_cyvol"])
        ly_vol = float(ind[f"{omc}_lyvol"])
        n_cy = ppt_ro_count(f["cy_f"], omc, last_cy_fy, last_cy_mi)
        n_ly = ppt_ro_count(f["ly_f"], omc, last_ly_fy, last_ly_mi) if f["ly"] else 0
        
        ppt_cy = (cy_vol / f["n_months"]) / n_cy if n_cy > 0 else None
        ppt_ly = (ly_vol / f["n_months"]) / n_ly if n_ly > 0 else None
        ppt_diff = (ppt_cy - ppt_ly) if (ppt_cy is not None and ppt_ly is not None) else None
        
        total_cy_vol += cy_vol
        total_ly_vol += ly_vol
        total_ros_cy += n_cy
        total_ros_ly += n_ly
        
        table_rows.append({
            "omc": omc,
            "type": "PSU" if omc in core.PSU else "Private",
            "cy_vol": cy_vol,
            "ly_vol": ly_vol,
            "growth": ind[f"{omc}_gr"],
            "share": ind[f"{omc}_cyshare"],
            "ppt": ind[f"{omc}_ppt"],
            "notional": ind[f"{omc}_notional"],
            "ppt_cy": ppt_cy,
            "ppt_ly": ppt_ly,
            "ppt_diff": ppt_diff
        })
        
    total_ppt_cy = (total_cy_vol / f["n_months"]) / total_ros_cy if total_ros_cy > 0 else None
    total_ppt_ly = (total_ly_vol / f["n_months"]) / total_ros_ly if total_ros_ly > 0 else None
    total_ppt_diff = (total_ppt_cy - total_ppt_ly) if (total_ppt_cy is not None and total_ppt_ly is not None) else None
    total_gr = (total_cy_vol - total_ly_vol) / total_ly_vol * 100 if total_ly_vol > 0 else None
    
    totals = {
        "omc": "Total",
        "type": "",
        "cy_vol": total_cy_vol,
        "ly_vol": total_ly_vol,
        "growth": total_gr,
        "share": None,
        "ppt": None,
        "notional": None,
        "ppt_cy": total_ppt_cy,
        "ppt_ly": total_ppt_ly,
        "ppt_diff": total_ppt_diff
    }
    
    return templates.TemplateResponse(
        request,
        "overview.html",
        {
            "active_tab": "overview",
            "filters": f,
            "shared": shared,
            "universe": universe,
            "kpis": kpis,
            "table": table_rows,
            "totals": totals,
            "omc_colors": core.OMC_COLORS
        }
    )

@app.get("/performance")
def performance(request: Request):
    f = parse_filters(request)
    shared = get_shared_context(request)
    universe = request.query_params.get("universe", "Industry")
    
    uset = core.OMC_ORDER if universe == "Industry" else core.PSU
    ro_counts = (f["ro_scope"].groupby("omc")["sap_code"].nunique()
                 .reindex(core.OMC_ORDER, fill_value=0).to_dict())
    total_ros = sum(ro_counts.get(o, 0) for o in uset)
    
    ind = core.totals_row(f["cy_f"], f["ly_f"], uset)
    psu_row = core.totals_row(f["cy_f"], f["ly_f"], core.PSU) if universe == "Industry" else ind
    cy_tot = ind["cy_tot"]
    ly_tot = ind["ly_tot"]
    
    table_rows = []
    for omc in uset:
        n_ros = ro_counts.get(omc, 0)
        row = {
            "omc": omc,
            "ros": n_ros,
            "ro_part": n_ros / total_ros * 100 if total_ros else 0.0,
            "cy_vol": ind[f"{omc}_cyvol"],
            "ly_vol": ind[f"{omc}_lyvol"],
            "diff_vol": ind[f"{omc}_diffvol"],
            "gr": ind[f"{omc}_gr"],
            "klpm_cy": core.klpm(ind[f"{omc}_cyvol"], f["n_months"], n_ros),
            "share_cy": ind[f"{omc}_cyshare"],
            "share_ly": ind[f"{omc}_lyshare"],
            "share_ppt": ind[f"{omc}_ppt"],
            "share_notional": ind[f"{omc}_notional"]
        }
        if universe == "Industry" and omc in core.PSU:
            row["psu_share_cy"] = psu_row[f"{omc}_cyshare"]
            row["psu_share_ppt"] = psu_row[f"{omc}_ppt"]
        table_rows.append(row)
        
    def subtotal(name, omcs):
        cyv = sum(ind[f"{o}_cyvol"] for o in omcs)
        lyv = sum(ind[f"{o}_lyvol"] for o in omcs)
        cs = cyv / cy_tot * 100 if cy_tot else 0.0
        ls = lyv / ly_tot * 100 if ly_tot else 0.0
        gr = (cyv - lyv) / lyv * 100 if lyv else None
        pp_ = cs - ls
        n_sub = sum(ro_counts.get(o, 0) for o in omcs)
        row = {
            "omc": name,
            "ros": n_sub,
            "ro_part": n_sub / total_ros * 100 if total_ros else 0.0,
            "cy_vol": cyv,
            "ly_vol": lyv,
            "diff_vol": cyv - lyv,
            "gr": gr,
            "klpm_cy": core.klpm(cyv, f["n_months"], n_sub),
            "share_cy": cs,
            "share_ly": ls,
            "share_ppt": pp_,
            "share_notional": pp_ / 100 * cy_tot
        }
        return row
        
    subtotals = []
    if universe == "Industry":
        subtotals.append(subtotal("PSU", core.PSU))
        subtotals.append(subtotal("PVT", core.PVT))
        subtotals.append(subtotal("IND", core.OMC_ORDER))
    else:
        subtotals.append(subtotal("PSU", core.PSU))
        
    return templates.TemplateResponse(
        request,
        "performance.html",
        {
            "active_tab": "performance",
            "filters": f,
            "shared": shared,
            "universe": universe,
            "table": table_rows,
            "subtotals": subtotals
        }
    )

@app.get("/ta_profile")
def ta_profile(request: Request):
    f = parse_filters(request)
    shared = get_shared_context(request)
    
    ta_code = request.query_params.get("ta_code", "T02-005")
    
    # 1. Network outlet profile counts
    ta_dim = core.load_ta_dim()
    trow = ta_dim[ta_dim.ta_code == ta_code]
    
    networks = []
    if not trow.empty:
        for omc, key in [("IOCL", "iocl"), ("BPCL", "bpcl"), ("HPCL", "hpcl"),
                         ("NEL", "nel"), ("RBML", "rbml"), ("SIMPL", "simpl")]:
            ms = int(trow[f"cnt_{key}_ms"].iloc[0])
            hsd = int(trow[f"cnt_{key}_hsd"].iloc[0])
            networks.append({"omc": omc, "ms_outlets": ms, "hsd_outlets": hsd})
    else:
        for omc in core.OMC_ORDER:
            networks.append({"omc": omc, "ms_outlets": 0, "hsd_outlets": 0})
            
    # Add TOTAL row
    networks.append({
        "omc": "TOTAL",
        "ms_outlets": sum(n["ms_outlets"] for n in networks),
        "hsd_outlets": sum(n["hsd_outlets"] for n in networks)
    })
    
    # 2. IOCL TA shares
    monthly = core.load_monthly()
    ta_all = monthly[monthly.ta_code == ta_code]
    
    shares = {}
    for prod in ["MS", "HSD"]:
        _cy_ta = ta_all[(ta_all.fy_code == f["cy"]) & (ta_all["product"] == prod) & (ta_all.month_index.isin(f["months"]))]
        _ly_ta = ta_all[(ta_all.fy_code == f["ly"]) & (ta_all["product"] == prod) & (ta_all.month_index.isin(f["months"]))] if f["ly"] else ta_all.iloc[0:0]
        tcy = core.totals_row(_cy_ta, _ly_ta, core.OMC_ORDER)
        shares[prod] = {
            "share_cy": tcy["IOCL_cyshare"],
            "share_ppt": tcy["IOCL_ppt"]
        }
        
    # 3. PPT Grid Data
    gdf, gtot = core.ta_volume_grid(monthly, ta_code, f["months"], f["cy"], f["ly"])
    grid_rows = []
    
    if not gdf.empty:
        gdf = gdf.copy()
        gdf["tot_cy"] = gdf.ms_cy + gdf.hs_cy
        gdf["omc_rank"] = gdf.omc.map({o: i for i, o in enumerate(core.OMC_ORDER)}).fillna(99)
        gdf = gdf.sort_values(["omc_rank", "tot_cy"], ascending=[True, False])
        
        for r in gdf.itertuples():
            grid_rows.append({
                "ro": r.ro,
                "loc": r.loc,
                "omc": r.omc,
                "ms_cy": r.ms_cy,
                "ms_ly": r.ms_ly,
                "hs_cy": r.hs_cy,
                "hs_ly": r.hs_ly
            })
            
    return templates.TemplateResponse(
        request,
        "ta_profile.html",
        {
            "active_tab": "ta_profile",
            "filters": f,
            "shared": shared,
            "selected_ta": ta_code,
            "networks": networks,
            "shares": shares,
            "grid": grid_rows,
            "grid_totals": gtot
        }
    )

if __name__ == "__main__":
    import uvicorn
    # Port 8602 for Option B trial
    uvicorn.run(app, host="0.0.0.0", port=8602)


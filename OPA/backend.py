import sys
import os
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Setup sys.path to import core from app folder
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PROJ_ROOT, "app"))
sys.path.insert(0, PROJ_ROOT)

import core

app = FastAPI(title="Pune DO Dashboard - Option A Trial")

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def parse_filters(
    product: str = "MS",
    cy: str = "2025-26",
    ly: str = "2024-25",
    months: str = "1,2,3,4,5,6,7,8,9,10,11,12",
    districts: str = "",
    rsas: str = "",
    coms: str = "",
    hwy_types: str = "",
    hwy_nos: str = ""
):
    # Resolve months list
    months_list = [int(m) for m in months.split(",") if m]
    # Resolve lists
    d_list = [d.strip() for d in districts.split(",") if d.strip()]
    r_list = [r.strip() for r in rsas.split(",") if r.strip()]
    c_list = [c.strip() for c in coms.split(",") if c.strip()]
    ht_list = [h.strip() for h in hwy_types.split(",") if h.strip()]
    hn_list = [h.strip() for h in hwy_nos.split(",") if h.strip()]
    
    # Load and filter
    monthly = core.load_monthly()
    ro_master = core.load_ro_master()
    
    # Apply filters
    def apply_filt(df):
        m = pd.Series(True, index=df.index)
        if d_list: m &= df.district.isin(d_list)
        if r_list: m &= df.rsa_code.isin(r_list)
        if c_list: m &= df.com.isin(c_list)
        if ht_list: m &= df.hwy_type.isin(ht_list)
        if hn_list: m &= df.highway_no.isin(hn_list)
        return df[m]
        
    scope = apply_filt(monthly)
    ro_scope = apply_filt(ro_master)
    
    cy_f = scope[(scope.fy_code == cy) & (scope["product"] == product) & (scope.month_index.isin(months_list))]
    ly_f = scope[(scope.fy_code == ly) & (scope["product"] == product) & (scope.month_index.isin(months_list))] if ly else scope.iloc[0:0]
    
    return cy_f, ly_f, ro_scope, months_list

@app.get("/api/filters")
def get_filters():
    ro = core.load_ro_master()
    ta = core.load_ta_dim()
    fys = core.fy_list()
    
    districts = sorted(ro.district.dropna().unique().tolist())
    
    # RSA labels as mapping
    rsa_unique = ro[["rsa_code", "rsa_name"]].dropna().drop_duplicates()
    rsas = [{"code": r.rsa_code, "name": r.rsa_name} for r in rsa_unique.itertuples()]
    
    coms = sorted(ro.com.dropna().unique().tolist())
    hwy_types = sorted(ro.hwy_type.dropna().unique().tolist())
    hwy_nos = sorted(ro.highway_no.dropna().unique().tolist())
    hwy_nos = [h for h in hwy_nos if h] # remove empty
    
    # TAs
    ta_list = []
    for t in ta.itertuples():
        ta_list.append({"code": t.ta_code, "name": t.ta_name_canonical})
        
    return {
        "districts": districts,
        "rsas": rsas,
        "coms": coms,
        "hwy_types": hwy_types,
        "hwy_nos": hwy_nos,
        "tas": ta_list,
        "fys": fys
    }

@app.get("/api/overview")
def get_overview(
    product: str = "MS",
    cy: str = "2025-26",
    ly: str = "2024-25",
    months: str = "1,2,3,4,5,6,7,8,9,10,11,12",
    districts: str = "",
    rsas: str = "",
    coms: str = "",
    hwy_types: str = "",
    hwy_nos: str = "",
    universe: str = "Industry"
):
    cy_f, ly_f, ro_scope, months_list = parse_filters(product, cy, ly, months, districts, rsas, coms, hwy_types, hwy_nos)
    n_months = max(len(months_list), 1)
    uset = core.OMC_ORDER if universe == "Industry" else core.PSU
    
    ind = core.totals_row(cy_f, ly_f, uset)
    psu_row = core.totals_row(cy_f, ly_f, core.PSU)
    
    # Network outlets
    iocl_net = int(ro_scope[ro_scope.omc == "IOCL"].sap_code.nunique())
    iocl_ly_net = iocl_net
    iocl_klpm_cy = core.klpm(ind["IOCL_cyvol"], n_months, iocl_net)
    iocl_klpm_ly = core.klpm(ind["IOCL_lyvol"], n_months, iocl_ly_net)
    
    # KPI cards
    kpi = {
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
    last_cy_fy = cy
    last_cy_mi = int(cy_f.month_index.max()) if not cy_f.empty else None
    last_ly_fy = ly
    last_ly_mi = int(ly_f.month_index.max()) if not ly_f.empty else None
    
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
        n_cy = ppt_ro_count(cy_f, omc, last_cy_fy, last_cy_mi)
        n_ly = ppt_ro_count(ly_f, omc, last_ly_fy, last_ly_mi) if ly else 0
        
        ppt_cy = (cy_vol / n_months) / n_cy if n_cy > 0 else None
        ppt_ly = (ly_vol / n_months) / n_ly if n_ly > 0 else None
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
        
    total_ppt_cy = (total_cy_vol / n_months) / total_ros_cy if total_ros_cy > 0 else None
    total_ppt_ly = (total_ly_vol / n_months) / total_ros_ly if total_ros_ly > 0 else None
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
    
    return {
        "kpis": kpi,
        "table": table_rows,
        "totals": totals,
        "omc_colors": core.OMC_COLORS
    }

@app.get("/api/performance")
def get_performance(
    product: str = "MS",
    cy: str = "2025-26",
    ly: str = "2024-25",
    months: str = "1,2,3,4,5,6,7,8,9,10,11,12",
    districts: str = "",
    rsas: str = "",
    coms: str = "",
    hwy_types: str = "",
    hwy_nos: str = "",
    universe: str = "Industry"
):
    cy_f, ly_f, ro_scope, months_list = parse_filters(product, cy, ly, months, districts, rsas, coms, hwy_types, hwy_nos)
    n_months = max(len(months_list), 1)
    uset = core.OMC_ORDER if universe == "Industry" else core.PSU
    
    ro_counts = (ro_scope.groupby("omc")["sap_code"].nunique()
                 .reindex(core.OMC_ORDER, fill_value=0).to_dict())
    total_ros = sum(ro_counts.get(o, 0) for o in uset)
    
    ind = core.totals_row(cy_f, ly_f, uset)
    psu_row = core.totals_row(cy_f, ly_f, core.PSU) if universe == "Industry" else ind
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
            "klpm_cy": core.klpm(ind[f"{omc}_cyvol"], n_months, n_ros),
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
            "klpm_cy": core.klpm(cyv, n_months, n_sub),
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
        
    return {
        "table": table_rows,
        "subtotals": subtotals
    }

@app.get("/api/ta_profile")
def get_ta_profile(
    ta_code: str,
    product: str = "MS",
    cy: str = "2025-26",
    ly: str = "2024-25",
    months: str = "1,2,3,4,5,6,7,8,9,10,11,12"
):
    months_list = [int(m) for m in months.split(",") if m]
    
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
        _cy_ta = ta_all[(ta_all.fy_code == cy) & (ta_all["product"] == prod) & (ta_all.month_index.isin(months_list))]
        _ly_ta = ta_all[(ta_all.fy_code == ly) & (ta_all["product"] == prod) & (ta_all.month_index.isin(months_list))] if ly else ta_all.iloc[0:0]
        tcy = core.totals_row(_cy_ta, _ly_ta, core.OMC_ORDER)
        shares[prod] = {
            "share_cy": tcy["IOCL_cyshare"],
            "share_ppt": tcy["IOCL_ppt"]
        }
        
    # 3. PPT Grid Data
    gdf, gtot = core.ta_volume_grid(monthly, ta_code, months_list, cy, ly)
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
            
    return {
        "networks": networks,
        "shares": shares,
        "grid": grid_rows,
        "grid_totals": gtot
    }

# Mount static files at /
app.mount("/", StaticFiles(directory=os.path.join(HERE, "static"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Port 8601 for Option A trial
    uvicorn.run("backend:app", host="0.0.0.0", port=8601, reload=True)

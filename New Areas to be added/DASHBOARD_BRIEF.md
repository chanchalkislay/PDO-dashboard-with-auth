# Pune DO Dashboard — Project Brief
*For Fable 5 orientation — read this before reading the handoff*

---

## What This Is

A **Streamlit-based market intelligence dashboard** for the Pune Divisional Office (DO) of Indian Oil Corporation Limited (IOCL). The Pune DO oversees petroleum retail operations across three districts: **Pune, Ahmednagar, and Satara** in Maharashtra, India.

The dashboard gives field officers and management a single screen to monitor:
- How IOCL is performing vs competitors (BPCL, HPCL, NEL, RBML, SIMPL)
- Which trading areas and outlets are growing, stagnant, or declining
- Operational flags — nil-selling outlets, branded fuel penetration, XtraPower programme

It is used **monthly** — each month, new sales data files from each Oil Marketing Company (OMC) are ingested via the pipeline and the dashboard updates.

---

## Business Context

### The Six OMCs
The petroleum retail market in Pune DO is served by six OMCs:
- **PSU-3**: IOCL (Indian Oil), BPCL (Bharat Petroleum), HPCL (Hindustan Petroleum)
- **Pvt-3**: NEL (Nayara Energy), RBML (Reliance BP Mobility), SIMPL (Shell)

Market share = OMC volume / PSU-3 total volume × 100 (industry convention).

### Fuel Products
- **MS** — Motor Spirit (petrol). Branded variants: XP95, XP100 (IOCL), Speed (BPCL), Power (HPCL)
- **HSD** — High Speed Diesel. Branded variant: XG (IOCL)

### The Financial Year
April to March. April = month_index 1, March = month_index 12.
FY 2026-27 means April 2026 to March 2027.

### Retail Outlet (RO) Types
- **A-site**: Land leased from third party; IOCL pays rent (REMM-tracked)
- **B-site**: Dealer-owned land; dealer operates the outlet
- **COCO**: Company-Owned Company-Operated — IOCL owns and operates directly
- **Swagat**: IOCL flagship highway outlet with driver-centric facilities
- **Priority RO**: Similar to Swagat, lesser tier
- **Apna Ghar**: Government of India designation for trucker-friendly highway ROs

### SAP Codes
Every RO has a unique 6-digit SAP code. This is the primary key across all tables.
Some ROs have changed SAP codes over time — old codes are stored as `legacy_sap_codes` in `dim_ro`.

---

## Technical Stack

| Layer | Technology |
|-------|-----------|
| UI | Streamlit (Python), multi-page via `st.navigation` |
| Database | SQLite (`pune_do.db`) — single file, ~30MB |
| Data processing | Pandas |
| Charts | Plotly |
| Ingestion pipeline | Custom Python (`ingest/pipeline.py`, `ingest/parsers.py`) |
| Hosting | Currently Streamlit Community Cloud; planning Oracle ARM VM |

---

## Key File Locations

| What | Path |
|------|------|
| Main repo | `D:\Github\PDO-Dashboard-Demo\` |
| Database | `D:\Github\PDO-Dashboard-Demo\app\pune_do.db` |
| App entry point | `D:\Github\PDO-Dashboard-Demo\app\app.py` |
| All tab pages | `D:\Github\PDO-Dashboard-Demo\app\pages\` |
| Sidebar | `D:\Github\PDO-Dashboard-Demo\app\sidebar.py` |
| Core query functions | `D:\Github\PDO-Dashboard-Demo\app\core.py` |
| Ingestion pipeline | `D:\Github\PDO-Dashboard-Demo\ingest\pipeline.py` |
| OMC parsers | `D:\Github\PDO-Dashboard-Demo\ingest\parsers.py` |
| Branded ingestion | `D:\Github\PDO-Dashboard-Demo\ingest\ingest_branded.py` |
| XtraPower ingestion | `D:\Github\PDO-Dashboard-Demo\ingest\ingest_xp.py` |
| New areas data files | `D:\Claude Cowork\Github Copy 1 July\New Areas to be added\` |
| Session notes/handoffs | `D:\Claude Cowork\Github Copy 1 July\June 2026\` |
| PDO DB Project folder | `D:\PDO DB Project\` |

---

## Current Database Schema

### `dim_ro` — 2,168 rows (RO master)
| Column | Type | Notes |
|--------|------|-------|
| sap_code | TEXT PK | 6-digit |
| ro_name | TEXT | |
| omc | TEXT | IOCL/BPCL/HPCL/NEL/RBML/SIMPL |
| district | TEXT | Pune / Ahmednagar / Satara |
| rsa_code | TEXT | Sales area code |
| rsa_name | TEXT | Sales area name |
| trading_area | TEXT | Local area name |
| ta_code | TEXT | e.g. M06-005 |
| com | TEXT | Commission category |
| category | TEXT | OPEN/SC/ST/OBC/UG etc. |
| ab_site | TEXT | 'A' or 'B' |
| yoc | TEXT | Year of commissioning e.g. '2020-21' |
| doc | TEXT | Date of commissioning |
| highway_no | TEXT | NH/SH number if on highway |
| legacy_sap_codes | TEXT | Comma-separated old SAP codes |
| data_complete_flag | TEXT | 'Yes'/'No' |

### `fact_monthly` — 372,620 rows (core sales fact)
| Column | Type | Notes |
|--------|------|-------|
| sap_code | TEXT | FK → dim_ro |
| ta_code | TEXT | |
| rsa_code | TEXT | |
| omc | TEXT | |
| district | TEXT | |
| product | TEXT | MS or HSD |
| fy_code | TEXT | e.g. '2026-27' |
| month_label | TEXT | e.g. 'JUN.26' |
| month_index | INT | 1=Apr … 12=Mar |
| volume_kl | REAL | Sales in kilolitres |
| is_negative | INT | 1 = return/negative |

**Coverage**: All 6 OMCs, Apr 2019 – Jun 2026 (BPCL/HPCL/IOCL); Apr 2019 – May 2026 (NEL/RBML); Apr 2019 – May 2026 (SIMPL)

### `fact_branded_monthly` — 17,446 rows
Branded fuel volumes: IOCL XP95/XP100/XG, BPCL Speed, HPCL Power.
Columns: sap_code, omc, product, brand, fy_code, month_index, month_label, volume_kl, source

### `fact_xtrapower_monthly` — 25,859 rows
IOCL XtraPower fleet card programme participation data.
Columns: sap_code, fy_code, month_index, month_label, hsd_kl, xp_kl, source

### `dim_ta` — 747 rows (trading area dimension)
TA-level counts of ROs by OMC and product.

### `dim_itps` — 663 rows
IOCL RO to MID/source mapping.

### Supporting tables (currently empty, structure in place)
- `ingestion_log` — tracks each ingestion run
- `staging_unknown_ros` — holds unmatched SAP codes for review
- `nil_action_plans` — action tracking for nil-selling ROs
- `xp_action_plans` — action tracking for XtraPower underperformers

---

## Existing Dashboard Tabs (16 pages)

| # | Page | What it shows |
|---|------|--------------|
| 01 | Overview | OMC-wise market share summary for selected period |
| 02 | Market Share | Detailed PSU market share table |
| 03 | Market Participation | % of ROs selling MS/HSD |
| 04 | TA Analysis | Trading area-level volume and share |
| 05 | TA Profile (PPT) | Single TA deep-dive for presentations |
| 06 | TA Rankings | League table of TAs |
| 07 | 7-Year Trend | Historical trend charts |
| 08 | Performance CY vs LY | RO-level CY vs last year comparison |
| 09 | Notional Loss/Gain | Volume gain/loss vs prior period |
| 10 | Nil Selling | Outlets with zero volume in reference month |
| 11 | Sales Volumes | District/RSA/TA volume drill-down |
| 12 | Branded | Branded fuel performance (XP95/XP100/XG/Speed/Power) |
| 13 | XtraPower | Fleet card programme monitoring |
| 14 | Finder & Reports | RO lookup and report export |
| 15 | RO Benchmarking | Outlet-level performance benchmarking |
| 16 | Ingest | Data ingestion UI for uploading monthly files |

---

## Ingestion Pipeline Architecture

The pipeline processes raw Excel files from each OMC's exchange system:

1. **parsers.py** — OMC-specific Excel parsers (IOCL SAP dump, BPCL Q002/Q145, HPCL Nagar/PS formats). Outputs normalised DataFrame with: sap_code, ro_name, product, brand, volume_kl, district. Already handles COVERAGE_DISTRICTS filtering, fuzzy district matching, MATERIAL_MAP for product identification.

2. **pipeline.py** — Core logic: dim_ro cross-check → volume outlier detection → duplicate guard → reconciliation check → INSERT into fact_monthly + fact_branded_monthly → log. FUSE-safe write (binary copy through /tmp). Handles legacy SAP code remapping.

3. **ingest_branded.py** — Branded fuel specific ingestion logic.

4. **ingest_xp.py** — XtraPower monthly data ingestion.

5. **tab_16_ingest.py** — Streamlit UI for the pipeline (file upload, dry-run, commit, review staging).

---

## IOCL-Specific Context

- **671 IOCL ROs** across Pune DO
- **16 COCO outlets** identified (name contains "COCO") — see `COCO/COCO_Master_Template.xlsx`
- **XtraPower**: Fleet card diesel programme — separate monthly data file from IOCL
- **Branded fuels tracked**: XP95 (MS), XP100 (MS), XG (HSD)
- **REMM**: Rent payment monitoring for A-site ROs — separate governance system
- **Commissioning**: New RO pipeline tracked separately in Excel

---

*Last updated: July 2026 | This brief is the starting orientation — see HANDOFF_FOR_FABLE5.md for the full development plan.*

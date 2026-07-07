# New Development Requirements — Pune DO Dashboard
*Verbatim capture of requirements as specified by the Divisional Officer*
*Date: July 2026*

---

## Guiding Intent

Use Fable 5 to comprehensively develop the database and dashboard for all required functionalities in one or two focused sessions. Master data files for each new area will be kept in the respective sub-folders. Fable should parse these files, understand the data structure, and decide how best to integrate them into the database and dashboard — rather than having the schema pre-designed by a previous session.

---

## New Feature Areas

### 1. Data Ingestion Pipeline Improvements

The existing pipeline (`ingest/pipeline.py`, `ingest/parsers.py`) is substantially built. Improvements required:

- Understand and pick up products **individually** (MS Mother, XP95, XP100, HSD Mother, XG) and route correctly
- Update the **branded fuel database** (`fact_branded_monthly`) as part of the regular ingestion, not as a separate step
- The pipeline should work without requiring AI assistance for routine monthly ingestion
- The proposed pipeline logic is already built and available in the repo (`ingest/` folder)
- Review parsers for NEL, RBML, SIMPL — check if they are complete or need to be added

---

### 2. COCO Management Tab

**Background:**
COCO = Company-Owned Company-Operated. IOCL runs these outlets directly instead of through a dealer.

**COCO Types:**
- **Temporary COCO**: Operated by an adhoc dealer appointed from existing dealers for a period of one year. At expiry, a new adhoc dealer is appointed.
- **Permanent COCO**: Operated either through a Service Provider selected via application/tendering (longer appointment period) OR through adhoc dealers like temporary COCOs.

**Identification:**
Parse `dim_ro` for all IOCL ROs where `ro_name LIKE '%COCO%'`. This is the COCO master list. Currently **16 COCOs** identified. The `COCO_Master_Template.xlsx` in the `COCO/` folder has all 16 pre-populated with SAP codes, legacy codes, RSA, district, location — the officer fills in operational details (type, dates, dealer names).

**Monitoring Requirements:**
1. **Work Order Validity Monitoring**:
   - Track: Date of appointment, Work Order period (months), Date of expiry (auto-calculated)
   - Generate alerts at **3 months, 2 months, and 1 month** before expiry so that the appointment process for next adhoc dealer / service provider can be initiated in time
   - Visual flag: Green (>3 months remaining) → Amber (1-3 months) → Red (expired or <1 month)

2. **Sales Monitoring**:
   - Track monthly and cumulative sales performance of each COCO
   - Performance relative to its Trading Area (same analysis as normal ROs, just filtered to COCOs)
   - No separate sales data — reads from existing `fact_monthly`

**COCO Master data columns** (for the DB table):
Sl No | SAP Code | Name of RO | Legacy Code/s | Legacy Names | Location | District | RSA | Permanent/Temp | Service Provider/Adhoc Dealer Name | Adhoc Dealer's Original RO SAP Code | Date of Appointment | Work Order Period (Months) | Date of Expiry (auto-calculated)

---

### 3. Swagat, Priority RO and Apna Ghar Monitoring

**Background:**
Three special categories of IOCL outlets tracked separately:

#### IOCL Brand Tags (two independent values):
- **Swagat**: IOCL flagship highway outlet. Driver-centric facilities: dormitory, restrooms, bathing, dhaba/cooking, secured parking, fuels.
- **Priority RO**: Flagship highway outlet, slightly below Swagat tier in facilities.

#### Government Tag (independent of IOCL brand):
- **Apna Ghar**: Government of India initiative for trucker-centric highway ROs. An RO can be declared Apna Ghar by government directive regardless of IOCL's own Swagat/Priority classification.

**Tag Independence:**
These are **two separate fields** in dim_ro:
- `iocl_brand_tag` → 'Swagat' / 'Priority RO' / NULL
- `apna_ghar_tag` → 'Yes' / NULL

An RO can have any combination. Treat them as separate dimensions throughout. Do NOT assume correlation.

**Module 1 — COCO Monitoring** *(see section 2 above)*

**Module 2 — Swagat and Priority RO Monitoring:**
For all ROs tagged Swagat or Priority RO, monitor:
- Monthly and cumulative sales performance
- Growth analysis and trends
- XtraPower performance (extract from `fact_xtrapower_monthly`)

**Trading Area Analysis for Swagat ROs:**
Each Swagat RO has two trading areas:
- **Standard trading area**: the normal TA it belongs to (same as any RO)
- **Extended trading area**: all OMC ROs (IOCL + competitors) within **50 km on each side** (RHS and LHS) of the National Highway the Swagat is on

The dashboard must show:
- List of all ROs (all OMCs) in the extended 50+50 km trading area
- Performance of the Swagat RO vs total market within its extended TA
- Growth analysis within the extended TA context

**Module 3 — Apna Ghar Monitoring:**
For all ROs tagged Apna Ghar, monitor:
- Facility availability status
- Sales performance and growth trends
- XtraPower performance
- Filterable independently of the Swagat/Priority RO view

---

### 4. REMM — Rent Payment and Lease Monitoring

**Background:**
REMM (Rent and Estate Management Module) governs rent payment for A-site ROs. For each A-site outlet, IOCL leases the land from a third-party landowner and pays periodic rent.

**Available files** (in `REMM Lease Payment/` folder):
- `REMM_Master_Sanitised_v1.xlsx` — master data of all A-site ROs with lease/rent details
- `REMM_Rules_and_Definitions.docx` — definitions of all fields and governance
- `REMM_Data_Governance_Rules.docx` — rules for data entry and maintenance

**Monitoring Requirements:**
- Track lease validity, rent amounts, payment status, and due dates
- Generate alerts for upcoming renewals and payment dues
- Drill-down to district and sales area level
- Data relates to current month primarily; maximum drill-down is district → sales area

---

### 5. Commissioning of New ROs

**Background:**
Three routes for commissioning new outlets:
1. **Land Advertisement** — IOCL advertises for land, gets offers, opens COCO
2. **Govt Sites** — IOCL requests site from government; RO operated by Govt department or by IOCL as COCO
3. **Advertisement** — Public applies, candidate selected, long formal approval process, commissioned as A-site or B-site dealer-operated RO

Once commissioned, the line item closes and the RO with SAP code moves to regular operations (dim_ro and fact_monthly).

**Available files** (to be placed in `Commissioning/` folder by officer):
- Existing Excel tracking file with current commissioning pipeline and workflow details
- The Excel itself demonstrates the structure and concepts to Fable

**Requirements:**
- Monitor all ROs in commissioning pipeline with their current stage/status
- Track progress against milestones specific to each route (Land Ad / Govt / Advertisement)
- When commissioned, RO should flow into dim_ro (with data_complete_flag='No') and be available in the main dashboard

---

### 6. Lube Sales Monitoring

**Background:**
IOCL sells lubricants (engine oil etc.) through its ROs. Unlike fuel data, lube data:
- Is **IOCL-only** — no industry/competitor comparison possible
- Requires **regular manual updating** — no automated OMC exchange file
- Initial phase: monitoring and MIS only; planning/intelligence layers to be added later

**Available files** (to be placed in `Lube Sales/` folder by officer):
- Monthly lube sales data file (format TBD by officer)

**Requirements:**
- Track lube sales by RO, RSA, district
- Monthly trend and cumulative views
- MIS reports

---

### 7. EVCS, CNG and CBG Monitoring

**Background:**
Alternate fuel infrastructure being added to existing ROs under Ministry of Petroleum push:
- **EVCS** — Electric Vehicle Charging Stations
- **CNG** — Compressed Natural Gas dispensing
- **CBG** — Compressed Biogas dispensing

**Requirements:**
- Monitor progress and commissioning status of EVCS/CNG/CBG at each RO
- Track which ROs have which alternate fuel options
- Report on Ministry targets vs actuals

**Available files** (to be placed in `EVCS CNG CBG/` folder by officer):
- Current tracker/Excel maintained by the office

---

### 8. Facility Management (Future Phase)

Monitor functioning of machines, storage facilities, automation systems, and mandatory facilities at ROs. This area will also include modernisation tracking. This is a **future phase** — not for immediate development. Noted here for awareness.

---

## General Improvements Required (All Tabs)

These apply globally across the existing dashboard:

**a. Download buttons** — All reports and tables should have an option for downloading (CSV/Excel). Currently missing from most tabs.

**b. Filter consolidation** — All applicable filters should be in the **side panel only**. Having filters in both sidebar and inside a tab creates confusion. The ONLY filters that should live inside a tab are:
- Industry / PSU selector (all-6 vs PSU-3)
- MS / HSD / Both selector
- Time period selection widgets specific to that tab's logic

**c. Time period fixes:**
- Nil Selling time period: reference month selection should remain intuitive (nil selling is always for a reference month)
- YTS (Year-To-Selected-month) and nil selling are always in reference to the selected month
- REMM should default to current month; max drill-down is district → sales area

**d. Monthly MIS generation** — Build a one-click button to generate the monthly MIS in the formats required by IOCL HQ and regional office. Should cover all key metrics in one report.

**e. Master rules and documentation** — Create a master record of all rules, definitions, data structures, dependencies, logic and algorithms of all Python scripts used. This is the living technical documentation of how the database works.

**f. Scalability for other DOs** — Build in provision for scaling to other Divisional Offices with different sets of geographical coverage, Sales Areas, and ROs. The `COVERAGE_DISTRICTS` concept already exists in `parsers.py` — this should be extended throughout the app so that changing one config value adapts the entire app for any DO.

**g. Data ingestion protocols for all new tabs** — Each new area (REMM, Commissioning, Lube, EVCS/CNG/CBG) needs a defined ingestion protocol: how data enters the system, how it is validated, how it is updated monthly.

---

## What Files Are Available for Fable to Read

| Area | Files Available | Location |
|------|----------------|----------|
| COCO | `COCO_Master_Template.xlsx` (16 COCOs pre-populated) | `COCO/` |
| REMM | `REMM_Master_Sanitised_v1.xlsx`, `REMM_Rules_and_Definitions.docx`, `REMM_Data_Governance_Rules.docx` | `REMM Lease Payment/` |
| Swagat/Priority/Apna Ghar | *Tag data to be filled by officer — ask for format* | `Swagat Priority Apna Ghar/` |
| Commissioning | *Excel to be placed by officer* | `Commissioning/` |
| Lube Sales | *Data file to be placed by officer* | `Lube Sales/` |
| EVCS/CNG/CBG | *Tracker to be placed by officer* | `EVCS CNG CBG/` |

---

*This requirements document is the complete, verbatim specification from the Divisional Officer.*
*Fable 5 should review this alongside the HANDOFF_FOR_FABLE5.md and the actual project files.*

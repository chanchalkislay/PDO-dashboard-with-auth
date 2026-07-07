# Handoff for Fable 5 — Pune DO Dashboard Expansion
*Comprehensive session brief | July 2026*

---

## Your Mission

You are picking up a live production dashboard project for the Pune Divisional Office of Indian Oil Corporation Limited. The existing dashboard is working, deployed on Streamlit Cloud, and used monthly. You are being asked to **expand it significantly** by adding new operational modules.

**Your job in this session is NOT to start coding immediately.**

Instead:
1. Read this handoff fully
2. Read `DASHBOARD_BRIEF.md` (same folder) for project orientation
3. Read `REQUIREMENTS.md` (same folder) for the complete specification
4. Then **systematically explore the actual project files** — the DB, the Python scripts, the existing tabs — so you understand what has already been built
5. Read all available master files in the sub-folders (`COCO/`, `REMM Lease Payment/`, etc.)
6. **Ask the officer for any data, files, or clarifications you need** before committing to a plan
7. Propose a detailed implementation plan
8. Get the plan approved before writing a single line of code

The officer's instruction: *"Give Fable 5 full opportunity to use his capabilities to design a plan, get it approved, and then implement."*

---

## Project File Map — Start Here

### The Live Repo (main working codebase)
```
D:\Github\PDO-Dashboard-Demo\
├── app\
│   ├── app.py               ← Streamlit entry point, navigation
│   ├── sidebar.py           ← Global sidebar filters
│   ├── core.py              ← All SQL query functions
│   ├── context.py           ← Session context builder
│   ├── bootstrap.py         ← DB initialization
│   ├── pune_do.db           ← THE DATABASE (SQLite, ~30MB)
│   ├── pages\               ← 16 tab pages (01_overview.py … 16_ingest.py)
│   └── components\          ← Shared UI components
└── ingest\
    ├── pipeline.py          ← Core ingestion orchestrator (527 lines)
    ├── parsers.py           ← OMC-specific Excel parsers (1,095 lines)
    ├── ingest_branded.py    ← Branded fuel ingestion (114 lines)
    └── ingest_xp.py         ← XtraPower ingestion (285 lines)
```

### Session Reference Files (not in repo)
```
D:\Claude Cowork\Github Copy 1 July\
├── June 2026\
│   ├── HANDOFF.md                        ← Prior session technical summary
│   ├── ingestion_algorithm_v2.svg        ← Flowchart of ingestion pipeline
│   ├── Planned Incorporation of LLM.md  ← Future LLM integration plan
│   └── Oracle VM Migration Plan.md      ← Hosting migration plan
└── New Areas to be added\               ← THIS FOLDER — you are here
    ├── DASHBOARD_BRIEF.md               ← Project orientation
    ├── REQUIREMENTS.md                  ← Full specification
    ├── HANDOFF_FOR_FABLE5.md            ← This file
    ├── COCO\
    │   └── COCO_Master_Template.xlsx    ← 16 COCOs pre-populated
    ├── REMM Lease Payment\
    │   ├── REMM_Master_Sanitised_v1.xlsx
    │   ├── REMM_Rules_and_Definitions.docx
    │   └── REMM_Data_Governance_Rules.docx
    ├── Swagat Priority Apna Ghar\       ← Empty — ask officer for data
    ├── Commissioning\                   ← Empty — officer to place Excel
    ├── Lube Sales\                      ← Empty — officer to place data file
    └── EVCS CNG CBG\                    ← Empty — officer to place tracker
```

### PDO DB Project (development history and reference)
```
D:\PDO DB Project\
├── Development\                         ← Earlier development versions
├── Handover\                            ← Multiple prior session handoffs
├── Rules_and_Definitions_v1.2.1.csv    ← Business rules reference
└── Pune_DO_Master_v1.2.xlsx            ← Original RO master spreadsheet
```

---

## What Is Already Built (Do Not Rebuild)

This is critical. A lot is already done. Understand it before planning additions.

### Fully working and deployed:
- **All 16 existing tabs** — Overview, Market Share, Trend, Performance, TA Analysis, TA Rankings, TA Profile, Market Participation, Nil Selling, Notional Loss, Sales Volumes, Branded, XtraPower, RO Benchmarking, Finder, Ingest
- **Branded fuel pipeline** — `fact_branded_monthly` table (17,446 rows), `ingest_branded.py`, `tab_12_branded.py` (page `12_branded.py`)
- **XtraPower pipeline** — `fact_xtrapower_monthly` table (25,859 rows), `ingest_xp.py`, `tab_13_xtrapower.py`
- **Core ingestion pipeline** — `pipeline.py` handles dim_ro cross-check, outlier detection, reconciliation guard, FUSE-safe DB writes, legacy SAP code remapping, staging of unknown codes
- **District resolution** — `parsers.py` has fuzzy district matching, COVERAGE_DISTRICTS config, all OMC format parsers
- **7 years of sales data** — Apr 2019 through Jun 2026 in `fact_monthly` (372,620 rows)

### What parsers.py already handles:
- IOCL SAP dump (Ship-To Party | Material | Inv.Qty format)
- BPCL Q002 Nagar format
- BPCL Q145 PS format
- HPCL Nagar format
- HPCL PS format
- pvt_ro_wise (generic user-compiled format)
- **CHECK**: NEL, RBML, SIMPL parser completeness — may need review

### What pipeline.py already does:
- Reads Excel via parsers.py
- Cross-checks SAP codes against dim_ro
- Detects volume outliers vs prior year
- Checks for duplicate ingestion
- Validates district totals (pvt_district_check)
- Runs reconciliation guard (IOCL share vs baseline)
- Inserts into fact_monthly WITH ta_code, rsa_code, district enrichment
- Inserts branded rows into fact_branded_monthly
- Stages unknown SAP codes for review
- Logs every run to ingestion_log
- FUSE-safe binary write-back to SQLite

---

## What Is Missing — Needs To Be Added

### Schema additions needed in `pune_do.db`:

#### Extend `dim_ro` (ALTER TABLE — no data loss):
```
swagat_tag        TEXT    -- 'Swagat' | 'Priority RO' | NULL
apna_ghar_tag     TEXT    -- 'Yes' | NULL
coco_flag         INT     -- 1 for IOCL COCOs (auto-derived from name), 0 otherwise
```

#### New tables (CREATE — empty, to be populated from master files):
```
coco_work_orders         -- COCO operational data: type, dealer, dates, alerts
swagat_extended_ta       -- Manual list of ROs in each Swagat's extended TA (see below)
remm_master              -- A-site lease/rent data (derive schema from REMM Excel)
commissioning_pipeline   -- New RO pipeline tracking (derive schema from officer's Excel)
fact_lube_monthly        -- Lube sales (IOCL-only, manual update)
fact_alternate_fuel      -- EVCS/CNG/CBG status per RO
```

**`swagat_extended_ta` — confirmed schema:**
| Column | Type | Notes |
|--------|------|-------|
| swagat_sap_code | TEXT | FK → dim_ro (the Swagat RO) |
| sr_no | INT | Display order (from officer's Excel) |
| ro_sap_code | TEXT | OMC code — may not exist in dim_ro for competitor ROs |
| ro_name | TEXT | Name as in officer's file |
| omc | TEXT | IOCL/BPCL/HPCL/NEL/RBML/SIMPL |
| rsa_name | TEXT | RSA this RO belongs to |
| side | TEXT | 'LHS' or 'RHS' (highway side) |

This table is **officer-maintained** — when a new Swagat is declared, officer adds the Swagat SAP code to dim_ro (swagat_tag='Swagat') and populates swagat_extended_ta with the RO list via a simple UI or direct data load.

*Note: Exact column definitions for coco_work_orders, remm_master, commissioning_pipeline, fact_lube_monthly, fact_alternate_fuel should be derived by Fable from reading the actual master files — not assumed.*

### New tabs needed (add to `app.py` navigation):
```
17_coco.py              -- COCO Management (work order alerts + sales)
18_swagat.py            -- Swagat Monitoring (extended TA + XP conversion)
19_apna_ghar.py         -- Apna Ghar Monitoring (separate tab, future session)
20_priority_ro.py       -- Priority RO Monitoring (separate tab, future session)
21_remm.py              -- REMM / Rent Payment Monitoring
22_commissioning.py     -- New RO Commissioning Pipeline
23_lube.py              -- Lube Sales MIS
24_evcs_cng_cbg.py      -- Alternate Fuel Monitoring
```

Priority RO and Apna Ghar get their own separate tabs (not combined with Swagat) to avoid clutter. Build Swagat tab first; Apna Ghar and Priority RO tabs follow in a subsequent session.

### Global improvements across existing tabs:
- **Download buttons** on all report tables (st.download_button with CSV/Excel)
- **Filter consolidation** — geo/RSA/COM/highway filters stay in sidebar only; only Industry/PSU, MS/HSD, and time-period controls remain in-tab
- **MIS report generator** — one-click monthly report covering all key metrics
- **Master documentation** — a living `MASTER_RULES.md` covering all business rules, data definitions, table relationships, pipeline logic

---

## Business Rules You Must Understand

### COCO Identification
Identify dynamically: `SELECT * FROM dim_ro WHERE omc='IOCL' AND ro_name LIKE '%COCO%'`
Currently returns 16 ROs. The COCO flag is derived from this — not manually maintained.

### COCO Alert Logic — 4-Tier System (Confirmed)

| Tier | Label | Condition | Colour |
|------|-------|-----------|--------|
| 0 | **Expired** | Expiry date has passed | Red |
| 1 | **Critical** | < 1 month remaining | Red / Dark Orange |
| 2 | **Expiry Critical** | 1–2 months remaining | Amber / Orange |
| 3 | **Expiring Soon** | 2–3 months remaining | Yellow |
| 4 | **Active** | > 3 months remaining | Green |

These tiers determine both the alert banner at the top of the COCO tab and the colour coding on each row in the work order table. The appointing process for the next adhoc dealer / service provider should be initiated well before the Critical tier.

### Swagat Extended Trading Area — Confirmed Approach

**Current Swagat RO**: SHRI SWAMI SAMARTH AUTO - KHARABWADI | SAP: **135645** | IOCL | Pimpri Chinchwad RSA
- Mark in dim_ro: `swagat_tag = 'Swagat'` (only this column needs to be added for now — Priority RO tag and Apna Ghar are handled in future sessions)

**Extended TA composition** (from `Swagat Trading Area.xlsx`):
- 38 ROs total (Swagat itself listed SR#15, plus 37 competitors)
- Two RSAs: **Pimpri Chinchwad RSA** (majority) + **Pune Wagholi RSA**
- Two sides: **LHS** (SR#1–23) and **RHS** (SR#24–38) of the highway
- OMC breakdown: IOCL 11 competitors + Swagat | BPCL 8 | HPCL 13 | NEL 3 | RBML 0 | SIMPL 1

**Approach to proximity** (no GPS): The officer manually maintains the list of which ROs fall in each Swagat's extended TA (the `Swagat Trading Area.xlsx` file). This is stored in `swagat_extended_ta` table. For future Swagat declarations, the officer will provide the list of ROs.

**Source file**: `D:\Claude Cowork\Github Copy 1 July\New Areas to be added\Swagat Priority Apna Ghar\Swagat Trading Area.xlsx` — use this to seed the initial `swagat_extended_ta` data for SAP 135645.

### Tag Independence
`swagat_tag` and `apna_ghar_tag` are completely independent. An RO can be:
- Swagat only
- Priority RO only
- Apna Ghar only
- Both Swagat + Apna Ghar
- Both Priority RO + Apna Ghar
- Neither

Never filter one based on the other.

### REMM Scope
REMM applies to **A-site ROs only** (`dim_ro.ab_site = 'A'`).
Currently 201 A-site IOCL ROs (Pune: 130, Ahmednagar: 43, Satara: 28).
Read the REMM governance documents before designing the REMM tab.

### Market Share Convention
Market share is always calculated as: OMC volume / PSU-3 (IOCL+BPCL+HPCL) total × 100
Not against all 6 OMCs. The dashboard has both "Industry" (all 6) and "PSU" (3) views.

### FY Convention
Financial year starts April (month_index=1) and ends March (month_index=12).
`fy_code` format: '2026-27'. June 2026 = fy_code='2026-27', month_index=3, month_label='JUN.26'.

### Pipeline Safety
The database may be on a FUSE-mounted USB/network drive. The pipeline uses a specific binary copy pattern (read → /tmp → modify → write back) to avoid filesystem corruption. Any new DB write operations must follow the same pattern using `pipeline._load_db()` and `pipeline._write_back()`. Do not use shutil.copy or direct file operations on the SQLite file.

### COVERAGE_DISTRICTS
`parsers.py` already has `COVERAGE_DISTRICTS = {"Pune", "Ahmednagar", "Satara"}`. This config should be centralised and imported by the app as well, so that changing one value adapts the entire dashboard for any DO. This is a planned improvement — factor it into any structural changes.

---

## The Approach the Officer Prefers

Rather than having the schema pre-designed by a previous AI session and handed to you, the officer wants Fable to:

1. **Read the actual master files** in each sub-folder
2. **Derive the schema** from what the data actually looks like
3. **Ask questions** where files are missing or structure is unclear
4. **Propose the plan** — DB migration + new tabs + global improvements — as a cohesive design
5. **Get approval** before implementation

This approach ensures the schema fits the real data, not a theoretical description of it.

---

## COCO Tab Design — Confirmed Layout

*This layout was reviewed and confirmed with the officer before handoff. Implement exactly as described.*

### Section 1 — Alert Banner (top of page, always visible)

A row of 4 coloured metric chips — one per alert tier — showing the count of COCOs in that category:

```
[ Expired: N ]  [ Critical: N ]  [ Expiry Critical: N ]  [ Expiring Soon: N ]
```

- Colours match the 4-tier table in Business Rules above.
- On mouseover OR click, show the names of COCOs in that category (tooltip or expander).
- If a tier has 0 COCOs, dim the chip (don't hide it — officers check for zero as confirmation).

### Section 2 — Sales Performance (first main content section)

This is the **most operationally relevant** view and should appear before the Work Order section.

Display a table of all 16 COCOs with:
- SAP Code | RO Name | District | Trading Area
- Current month MS volume (KL) | Current month HSD volume (KL)
- CY cumulative MS + HSD
- TA average for current month (all IOCL ROs in same TA)
- Policy Target: average KLPM of the **highest-selling IOCL RO** in the same TA for the 12 months preceding the COCO's appointment date (pulled from `coco_work_orders.appointment_date`, computed from `fact_monthly`)
- Performance vs TA average (% difference)
- Performance vs Policy Target (% difference)

Below the table, include the "Trading Area PPT format" view:
- A selector for COCO (by name or SAP code) and a month/period selector
- Renders the same TA profile view as Tab 05 (TA Profile PPT), filtered to that COCO's trading area
- This is a re-use of existing Tab 05 logic — not a new build

### Section 3 — Work Order Status

A table of all 16 COCOs showing:
- SAP Code | Name | Type (Perm/Temp) | Dealer/Service Provider Name
- Dealer's Original SAP Code (for Adhoc COCOs)
- Date of Appointment | Work Order Period (months) | Date of Expiry (auto-calculated)
- Alert tier (colour-coded badge: Expired / Critical / Expiry Critical / Expiring Soon / Active)
- Days remaining (negative if expired)

Sort default: by days remaining ascending (most urgent first).

### Section 4 — COCO Detail Panel (row selection expander)

Clicking/selecting any row in either table above opens a detail panel showing all fields for that COCO — full operational details from `coco_work_orders` joined with `dim_ro`.

---

## Swagat Tab Design — Confirmed Layout (Tab 18)

*Single-Swagat view for now (1 Swagat RO). When additional Swagat ROs are declared, a selector at the top will switch between them. Design with this in mind from day one.*

**Apna Ghar and Priority RO are NOT in this tab** — they get separate tabs in a future session.

### Section 1 — Swagat RO Header

A header card showing:
- RO Name | SAP Code | RSA | Highway (from `dim_ro.highway_no`)
- `swagat_tag` badge (e.g. "🔵 IOCL Swagat")
- Current month MS + HSD volume and MoM trend

### Section 2 — Extended TA Summary (OMC-wise breakdown)

A compact table showing the all-OMC composition of the extended TA:

| OMC | No. of ROs | LHS | RHS | Volume MS (KL) | Volume HSD (KL) | Share % |
|-----|------------|-----|-----|----------------|-----------------|---------|

- Volumes sourced from `fact_monthly` JOIN `swagat_extended_ta` on `ro_sap_code`
- Non-IOCL ROs in the extended TA: their volumes ARE in fact_monthly (all 6 OMCs are covered)
- Note: some competitor OMC codes in `swagat_extended_ta` may not be in `dim_ro` — join on `ro_sap_code = sap_code`, handle non-matches gracefully (show name from `swagat_extended_ta.ro_name`)

### Section 3 — Extended TA in PPT Format (TA Profile View)

Re-use the logic from **Tab 05 (TA Profile PPT)** but driven by `swagat_extended_ta` instead of the normal `dim_ta` trading area. This view should display the Swagat's extended TA in exactly the same "PPT format" as the TA Profile tab.

- Month selector and period selector (CY/LY/custom)
- Shows all ROs from `swagat_extended_ta`, grouped by OMC, with LHS/RHS column
- Highlights the Swagat RO row distinctly

### Section 4 — XtraPower (XP) Conversion Monitoring

For all **IOCL ROs** in the extended TA (join `swagat_extended_ta` where `omc='IOCL'` to `fact_xtrapower_monthly`):

| RO Name | Side | Month XP (KL) | Month % Conv | CY XP (KL) | CY % Conv | Month +/- KL | Month +/- % Conv | CUM.CY XP (KL) | CUM.CY % Conv | CUM.LY XP (KL) | CUM.LY % Conv | Cum +/- KL | Cum +/- % Conv |

- The Swagat RO (135645) row highlighted separately at the top
- "% Conv" = XP HSD volume / Total HSD volume × 100 (sourced from `fact_xtrapower_monthly.xp_kl / hsd_kl`)

### Section 5 — MoU Performance (Growth vs Extended TA Growth)

Two metrics shown for the Swagat RO:
- **MoU %**: Growth rate of Swagat RO vs growth rate of the entire extended TA (both MS + HSD, current month and CY cumulative)
- **PSU MoU %**: Same but vs PSU-only (IOCL+BPCL+HPCL) growth within the extended TA

Formula: `MoU = (Swagat growth % − Extended TA growth %)` — positive = outperforming TA.

### Adding a New Swagat (Future Flow)

When a new IOCL RO is declared Swagat:
1. Officer sets `dim_ro.swagat_tag = 'Swagat'` for the new SAP code (via a simple admin UI or direct edit)
2. Officer provides the Excel list of ROs in the new Swagat's extended TA (same format as `Swagat Trading Area.xlsx`)
3. Fable/dashboard loads these rows into `swagat_extended_ta` with the new `swagat_sap_code`
4. Tab 18 selector automatically adds the new Swagat as an option

---

## COCO Add / Remove Logic

### Adding a New COCO

Two distinct scenarios:

**Scenario A — New Commissioning (new SAP code)**

Sequence:
1. A new IOCL outlet is commissioned as a COCO (new SAP code assigned).
2. Its first monthly data file will contain a SAP code not in `dim_ro` → goes to `staging_unknown_ros`.
3. In Tab 16 (Ingest → Staging Review), the staging review table should have a new action option: **"Mark as new COCO"** — in addition to the existing "Add to dim_ro" and "Legacy Map" options.
4. Selecting "Mark as new COCO" → creates the dim_ro entry with `coco_flag=1` + opens a mini-form in the UI to fill in the `coco_work_orders` record (dealer name, appointment date, work order period).
5. After confirmation, row is cleared from staging and data is ingested.

**Scenario B — Conversion (existing RO becomes COCO)**

Sequence:
1. An existing RO (already in `dim_ro`) is converted to temporary/permanent COCO operation.
2. No SAP code change — the existing SAP code continues.
3. Officer uses the COCO tab → "Add COCO" button → enters SAP code of existing RO.
4. System: sets `dim_ro.coco_flag = 1` for that SAP code + creates a new record in `coco_work_orders` with the operational details.
5. The RO now appears in all COCO monitoring views.

### Removing a COCO

Sequence:
1. COCO period ends — new regular dealer appointed or COCO handed back.
2. Officer uses the COCO tab → selects the COCO row → "Mark as Closed – Regularised".
3. System: sets `coco_work_orders.status = 'Closed'` + sets `dim_ro.coco_flag = 0`.
4. The RO disappears from the COCO tab and returns to normal dashboard views.
5. **Historical fact_monthly data is NOT deleted** — the RO's sales history remains intact.
6. If the same SAP code is converted back to COCO in future, a new `coco_work_orders` record is created.

---

## COCO Master Data — Known Correction

**COCO Shevgaon (SAP 354938, Triratna Petroleum):**
Date of Appointment = **01.11.2025** (November 2025).

The `COCO_Master_Template.xlsx` may show 01.11.2026 — this is a typographical error confirmed by the officer. Use 01.11.2025 as the correct value when loading data into `coco_work_orders`. Verify the Excel value before loading; if it still shows 2026, override it programmatically or prompt the officer to confirm.

---

## Suggested (Not Finalised) Implementation Order

*This is a starting suggestion only. Fable should review and propose their own sequencing after examining the files.*

**Phase A — Foundation (do first, everything else depends on it):**
1. Read all master files; ask officer for any missing data
2. Design and present the complete schema migration (ALTER TABLE + new tables)
3. Get schema approved
4. Run schema migration on `pune_do.db`
5. Implement global improvements: download buttons, filter consolidation

**Phase B — COCO Tab:**
6. Load COCO master data into new `coco_work_orders` table
7. Build tab 17 — work order alert dashboard + sales monitoring view

**Phase C — Swagat / Apna Ghar:**
8. Add tag columns to dim_ro; populate from officer-provided data
9. Build tab 18 (Swagat/Priority RO) and tab 19 (Apna Ghar)
10. Clarify and implement extended TA logic for Swagat

**Phase D — REMM:**
11. Parse REMM master; design remm_master table
12. Build tab 20 (REMM / Rent Monitoring)

**Phase E — Commissioning + Lube + EVCS/CNG/CBG:**
13. Build tabs 21, 22, 23 once officer provides data files

**Phase F — MIS and Documentation:**
14. MIS report generator
15. Master rules documentation

---

## Questions to Ask the Officer Before Planning

Use these as a starting checklist — add your own as you review the files:

1. **Swagat / Priority RO list**: ✅ **ANSWERED for Swagat.** Current Swagat: SAP 135645 (SHRI SWAMI SAMARTH AUTO - KHARABWADI), Pimpri Chinchwad RSA. Extended TA data in `Swagat Priority Apna Ghar/Swagat Trading Area.xlsx`. **Priority RO** list still needed — ask officer when building Tab 20 (future session). dim_ro currently only needs `swagat_tag` column added.

2. **Apna Ghar list**: Needed when building Tab 19 (future session after Swagat tab). Ask officer at that stage.

3. **Swagat extended TA**: Do you have GPS coordinates for ROs, or should proximity to highway be defined by manually listing the relevant TAs for each Swagat RO?

4. **Commissioning Excel**: Please place your commissioning tracking Excel in the `Commissioning/` sub-folder. What are the main stages tracked?

5. **Lube sales format**: What does a monthly lube sales data file look like? Please place a sample in `Lube Sales/`.

6. **EVCS/CNG/CBG tracker**: Please place your current alternate fuel tracker in `EVCS CNG CBG/`. Is it a simple commissioned/not-commissioned list, or does it track volumes?

7. **MIS format**: Is there an existing MIS template used for monthly reports to HQ/Regional Office? If so, please share so the report generator can match the format exactly.

8. **COCO Master**: The `COCO_Master_Template.xlsx` has been filled by the officer — all 16 COCOs have operational details: Perm/Temp, dealer names, dealer SAP codes, appointment dates, work order periods, and remarks. **One known data correction: COCO Shevgaon (SAP 354938) appointment date is 01.11.2025** — the Excel may still show 01.11.2026 (typo). Treat 01.11.2025 as the authoritative value. Also confirm whether the TA averages and Policy Target columns in the Excel are pre-filled or whether you should compute them from the DB.

9. **Filter cleanup**: Can you confirm which filters are currently duplicated between sidebar and in-tab, and which in-tab filters you want to keep? The rule proposed is: geo/RSA/COM/highway → sidebar only; Industry/PSU + MS/HSD + time period → in-tab. Does this match your expectation?

10. **NEL/RBML/SIMPL parsers**: The pipeline currently has parsers for IOCL, BPCL, HPCL formats. Are the NEL, RBML, SIMPL monthly files in a different format? Can you share a sample file for each if parsers need to be added?

---

## Technical Constraints to Respect

- **No breaking changes** to existing tables or columns in `dim_ro`, `fact_monthly`, `fact_branded_monthly`, `fact_xtrapower_monthly`
- **SQLite only** — no migration to a different DB system
- **Python + Streamlit only** — no JavaScript frameworks or additional servers
- **FUSE-safe writes** — all DB writes must go through `/tmp` staging (see pipeline.py pattern)
- **Streamlit `st.navigation` pattern** — new pages go in `app/pages/` and are registered in `app.py`
- **Follow established UI conventions** — look at 2-3 existing tabs before building new ones to match style, filter patterns, and component usage

---

## Summary of Current DB State

| Table | Rows | Status |
|-------|------|--------|
| dim_ro | 2,168 | Complete for current ROs; missing new tag columns |
| fact_monthly | 372,620 | Apr'19–Jun'26; complete for PSU-3; May'26 for NEL/RBML; May'26 for SIMPL |
| fact_branded_monthly | 17,446 | Working |
| fact_xtrapower_monthly | 25,859 | Working |
| dim_ta | 747 | Complete |
| dim_itps | 663 | Complete |
| ingestion_log | 0 | Table exists, not yet populated in live DB |
| staging_unknown_ros | 0 | Table exists, clean |
| nil_action_plans | 0 | Table exists |
| xp_action_plans | 0 | Table exists |
| coco_work_orders | — | Does not exist yet |
| swagat_extended_ta | — | Does not exist yet; seed from `Swagat Trading Area.xlsx` (38 rows for SAP 135645) |
| remm_master | — | Does not exist yet |
| commissioning_pipeline | — | Does not exist yet |
| fact_lube_monthly | — | Does not exist yet |
| fact_alternate_fuel | — | Does not exist yet |

---

## Final Note to Fable

The officer is technically informed and has been closely involved in building this system. He understands the pipeline architecture, the DB schema, and the business domain. Be precise with him — he will notice hand-wavy answers.

When you propose the plan, be specific about:
- Exact table and column names
- Whether each new feature reads from existing tables or needs new ones
- What data the officer needs to provide vs what you can derive from the DB
- Realistic scope for one session vs two sessions

He is trusting you with a system that is used by his office every month. Design it well.

---

*Handoff prepared: July 2026*
*Prior session model: Claude Sonnet 4.6*
*Handoff target: Fable 5*

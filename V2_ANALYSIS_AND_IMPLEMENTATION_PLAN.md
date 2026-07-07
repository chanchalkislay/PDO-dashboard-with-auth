# Pune DO Dashboard v2 — Full Analysis & Implementation Plan
**Prepared by:** Fable 5 (CTO session) | **Date:** 4 July 2026
**Status:** DRAFT — awaiting officer approval

---

## 1. Verdict — Are We Good to Go?

**Yes, with four blockers that must be resolved before code is written.** The existing codebase is in far better shape than the caveat about the ingestion pipeline suggests — the app layer (core.py, context.py, 16 tabs) is well-architected, vectorised, and consistent. The pipeline does not need a from-scratch rewrite; it needs a focused v2 refactor (Section 5). What actually blocks production-readiness is not code quality — it is these:

| # | Blocker | Why it blocks |
|---|---------|---------------|
| B1 | **The DB in this folder is stale.** It has data only through **May 2026** (369,168 fact rows, dim_ro 2,164). HANDOFF.md describes a June-loaded DB (372,620 rows, dim_ro 2,168, 4 new BPCL ROs, Kokamthan remap). | Every schema migration and data seed must run against the true DB. Building on this copy means re-doing work or corrupting the live one on merge. |
| B2 | **Three module folders are empty**: Commissioning, Lube Sales, EVCS/CNG/CBG. | Their schemas are to be derived from real files (per your own instruction). Cannot design them yet. |
| B3 | **No NEL/RBML/SIMPL June files or format samples** for parser verification, and no HQ **MIS template** for the report generator. | Parser completeness and MIS output format can't be validated against thin air. |
| B4 | **Hosting decision pending** (Streamlit Cloud vs Oracle VM). This is not cosmetic — see Finding F3: ingestion through the cloud-hosted Tab 16 **does not persist** (ephemeral filesystem). The ingestion redesign must target the real deployment. | Pipeline v2's write path and the "self-service monthly ingestion" goal depend on it. |

Everything else — COCO, Swagat, REMM, global improvements, pipeline v2 — has complete input data and confirmed layouts, and can be fully built, tested, and delivered.

---

## 2. What Is Solid (audited, do not rebuild)

- **core.py** — clean separation (no widgets), cached loaders, vectorised metric engine (`share_frame`, `totals_row`), locked KLPM rule, Indian-format numbers, the PPT-format TA grid renderer. Reusable as-is for COCO §2 and Swagat §3 (both spec'd to re-use Tab 05 logic — confirmed feasible: `ta_volume_grid()` takes a frame filter, easy to drive from `swagat_extended_ta` instead of `ta_code`).
- **context.py / sidebar.py** — single shared context dict, filter state dataclass, cached period-frame computation keyed on filters. New tabs plug in with ~10-line page wrappers (pattern verified in `pages/01_overview.py`).
- **pipeline.py** — contrary to HANDOFF.md's claim, `_insert_fact_monthly()` in the repo **already enriches ta_code/rsa_code/district** from dim_ro (lines 300–315). The ta_code bug lives in the *Development-folder* pipeline (`commit_to_db()` — a function that doesn't exist in this repo). The two codebases have diverged; the repo one is the better base.
- Snapshot/rollback, reconciliation guard, duplicate guard, staging of unknown SAP codes, FUSE-safe writes — all present and sound in design.
- **DB integrity is good**: 0 orphan SAP codes, 0 duplicate fact keys, 0 NULL ta_codes, 0 dim_ro duplicates, ta_code in facts consistent with dim_ro. 16 COCOs and 201 A-site IOCL ROs confirmed by query — matching the handoff exactly.

---

## 3. Inconsistencies & Pain Points You Haven't Flagged Yet

Ordered by severity. F1–F5 are things that are hurting you **today**.

**F1 — Stale-data illusion after ingestion (hidden bug).** All loaders (`load_monthly`, `load_branded`, etc.) use `@st.cache_data` with no TTL, and Tab 16 never calls `.clear()` after a successful commit. After an officer ingests a month, **the dashboard keeps showing pre-ingestion numbers** until the server process restarts. On Streamlit Cloud that can be days. This alone explains "the pipeline creates errors" perceptions — the data went in fine; the app just didn't show it. Fix: one `st.cache_data.clear()` + `st.rerun()` in the commit-success path.

**F2 — Two divergent pipelines.** HANDOFF.md's fix-list targets `D:\PDO DB Project\Development\ingest\` (with `commit_to_db()`, inline `COVERAGE`), while this repo's `ingest/pipeline.py` is a different, more advanced implementation. `omc_pipeline.py` (446 lines) is a third, orphaned architecture — untracked, imported by nothing. Anyone (human or AI) picking this project up fixes the wrong file. Pipeline v2 must end with **exactly one** pipeline and the deletion of the other two.

**F3 — Cloud ingestion doesn't persist.** On Streamlit Community Cloud the container filesystem is ephemeral and the DB ships inside the git repo. Tab 16 writes to the container's local copy — it works until the app redeploys/restarts, then **everything ingested via the UI silently vanishes**. The real workflow (ingest locally → git push) works only because you've been doing it manually. Decision needed: Oracle VM (persistent disk — Tab 16 becomes genuinely self-service) or stay on Cloud (then Tab 16 must export a committed DB for download/push, and say so honestly in the UI).

**F4 — `fact_monthly` has no primary key, no unique constraint, and no indexes.** Duplicate protection exists only in pipeline code; any direct write path (like this session's manual June scripts) can silently double-count. Every query full-scans 369k rows. Fix: `UNIQUE(sap_code, product, fy_code, month_index)` (note: omc/district are attributes of sap_code, not part of the key) + indexes on `(fy_code, month_index)` and `(sap_code)`.

**F5 — Ingestion password.** `INGEST_KEY` defaults to `"123456"` in `app.py` on a public Streamlit URL. Set a real secret via Streamlit secrets / env var, remove the default.

**F6 — `month_label` inconsistency.** Pipeline writes `'APR.25'` style; the DB's FY 2026-27 rows contain `'Apr'`/`'May'` (manual ingestion artifact). Nothing breaks today because the app keys on `month_index`, but any future label-based logic (or MIS exports) will split on this. Standardise + backfill in migration.

**F7 — Blanket rounding is the wrong fix for the decimal artifacts.** HANDOFF.md proposes `round(volume_kl)` at insert. But the current DB has **796 legitimately decimal rows in FY 2026-27 alone** (BPCL 260, HPCL 99, IOCL 432, NEL 5 across Apr–May — half-KL and finer values). Rounding everything to integers alters correct data. The fix should target only the identified COCO formula-artifact rows, or be an OMC-specific rule you explicitly confirm.

**F8 — Reconciliation guard will go stale.** Baselines (`_GUARD_FY = "2025-26"`, three hard-coded share constants) are frozen in code. Correct concept, wrong home — move to a `config.py` / DB table with a documented annual re-baselining step.

**F9 — Deploy-branch confusion.** README says Streamlit deploys from `demo-jun26`; HANDOFF.md says live deploys from `main`; work sits on `ingestion-COCO-Swagat` with stashed changes. Needs one authoritative answer, recorded in MASTER_RULES.md.

**F10 — COVERAGE_DISTRICTS not centralised** (known, but worse than noted): `tab_16_ingest.py:670` also hard-codes `["Pune","Ahmednagar","Satara"]`. The planned `config.py` must be imported there too.

**F11 — COCO master file issues found on read:**
- Shevgaon (354938) shows **01.11.2026** — the known typo is still in the file; I will override to 01.11.2025 per your confirmation.
- **Rajgurunagar (232661)** and **Velhe (323570)** have no dealer, no appointment date, no work-order period. The schema and alert logic need an explicit "No active work order" state (I propose a 5th tier, grey) — otherwise these two either crash the expiry calculation or silently disappear.
- All computed columns (TA averages, policy target, current-month volumes) are blank — confirmed they must be computed from the DB, not loaded.

**F12 — Swagat file vs handoff mismatch.** The Excel contains HPCL **14**, IOCL 12 (incl. Swagat), BPCL 8, NEL 3, SIMPL 1 = 38 rows. The handoff says HPCL 13. I'll treat the Excel as authoritative unless you say otherwise.

**F13 — REMM master: 218 rows vs "201 A-site ROs".** Row count exceeds the A-site RO count (multiple agreements per RO / Own-Land / Pending rows). So `remm_master` must key on **REMM_ID, not sap_code**, with RDB Code as the FK to dim_ro — and the 12 month-columns (Apr-25…Mar-26) must be normalised into a `remm_payments` (remm_id, fy_code, month_index, amount) table, or every new FY needs a schema change.

**F14 — Docs drift.** DASHBOARD_BRIEF says charts are Plotly; the code uses Altair (requirements.txt has no plotly). Minor, but MASTER_RULES.md should become the single corrected reference.

**F15 — Hygiene.** 20+ `.fuse_hidden*` files in `app/`, committed `__pycache__/`, Excel lock files (`~$*.xlsx`) in the data folders. Add `.gitignore` entries and clean.

**F16 — UX gaps against your own requirements list** (confirmed by scan): download buttons exist in only 3 of 16 tabs (6 total); no "Both MS+HSD" product view anywhere (sidebar radio is MS/HSD only); sidebar month defaults point at "Mar" rather than the latest ingested month; `verify.py` covers only 3 tables and won't guard the six new ones.

---

## 4. Proposed Schema (derived from the actual files)

### 4.1 ALTER dim_ro (non-breaking)
```sql
ALTER TABLE dim_ro ADD COLUMN swagat_tag    TEXT;  -- 'Swagat' | 'Priority RO' | NULL
ALTER TABLE dim_ro ADD COLUMN apna_ghar_tag TEXT;  -- 'Yes' | NULL
ALTER TABLE dim_ro ADD COLUMN coco_flag     INT DEFAULT 0;  -- derived: IOCL + name LIKE '%COCO%'
```
Seed: `swagat_tag='Swagat'` for 135645; `coco_flag=1` for the 16 COCOs.

### 4.2 coco_work_orders (new — from COCO_Master_Template.xlsx, 27 cols read)
```sql
CREATE TABLE coco_work_orders (
    wo_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sap_code TEXT NOT NULL REFERENCES dim_ro(sap_code),
    coco_type TEXT,            -- 'Permanent' | 'Temporary'
    operation_mode TEXT,       -- 'Adhoc' | 'Service Provider' | NULL (no WO)
    operator_name TEXT,
    operator_original_sap TEXT,
    date_of_appointment TEXT,  -- ISO yyyy-mm-dd; NULL for no-WO COCOs
    wo_period_months INT,
    date_of_expiry TEXT,       -- computed on load: appointment + period
    status TEXT DEFAULT 'Active',   -- 'Active' | 'Closed'
    remarks TEXT,
    created_at TEXT, closed_at TEXT
);
```
Alert tier computed at render time (never stored): Expired / Critical(<1m) / Expiry-Critical(1–2m) / Expiring-Soon(2–3m) / Active(>3m) / **No-Work-Order (grey)**. TA averages and Policy Target (highest IOCL RO in TA, 12 months pre-appointment) computed from fact_monthly.

### 4.3 swagat_extended_ta (new — exactly the confirmed schema; seed 38 rows for 135645)
```sql
CREATE TABLE swagat_extended_ta (
    swagat_sap_code TEXT NOT NULL,
    sr_no INT, ro_sap_code TEXT, ro_name TEXT,
    omc TEXT, rsa_name TEXT, side TEXT,      -- 'LHS'|'RHS'
    PRIMARY KEY (swagat_sap_code, sr_no)
);
```

### 4.4 remm_master + remm_payments (new — from REMM_Master_Sanitised_v1.xlsx, 43 cols / 218 rows)
```sql
CREATE TABLE remm_master (
    remm_id TEXT PRIMARY KEY,              -- permanent, per governance doc
    rdb_code TEXT,                          -- FK → dim_ro.sap_code
    ro_name TEXT, rsa_name TEXT, com TEXT,
    land_class TEXT,                        -- Govt / Pvt / Own Land
    agreement_no TEXT, sub_agreement_no TEXT,
    mutation TEXT, vendor_code TEXT, vendor_name TEXT,
    lease_from TEXT, lease_validity TEXT,
    lease_area_sqft REAL, initial_rent REAL, revised_rent REAL,
    vendor_pan TEXT, name_on_pan TEXT, vendor_gst TEXT,
    bank_ifsc TEXT, bank_account TEXT,
    legacy_rdb_codes TEXT,
    action_plan TEXT, action_taken TEXT, target_date TEXT, remarks TEXT
);
CREATE TABLE remm_payments (
    remm_id TEXT, fy_code TEXT, month_index INT, amount REAL,
    PRIMARY KEY (remm_id, fy_code, month_index)
);
```
`lease_status_code` (S0–S8) and `agreement_status` are **computed at every load** from lease_validity vs today — per the governance rule "never stored". FLAG/PENDING/OWN semantics in REMM_ID respected (no payment processing flags). Login alert for S1/S2/S3.

### 4.5 Deferred until files arrive (B2)
`commissioning_pipeline`, `fact_lube_monthly`, `fact_alternate_fuel` — schemas derived from your Excels when placed, same review cycle.

### 4.6 Integrity & performance migration (fixes F4)
```sql
CREATE UNIQUE INDEX ux_fact_key ON fact_monthly(sap_code, product, fy_code, month_index);
CREATE INDEX ix_fact_fy_mi ON fact_monthly(fy_code, month_index);
CREATE INDEX ix_fact_sap   ON fact_monthly(sap_code);
```
(Pre-checked: zero duplicate keys exist today, so the unique index applies cleanly.)

---

## 5. Ingestion Pipeline v2 (refactor, not rewrite)

Keeping: Pipeline class shell, FUSE-safe write pattern, snapshot/rollback, staging, dry-run→commit UX. Changing:

1. **`config.py` at repo root** — `COVERAGE_DISTRICTS`, FY helpers, guard baselines, month-label format. Imported by parsers, pipeline, core, tab_16 (kills F8, F10).
2. **District auto-detection** — `detect_district_col()` + `filter_to_coverage()` per the v2 flowchart, so ad-hoc file layouts (like the June custom summaries) stop requiring manual scripts.
3. **New parser formats** — the three June 2026 custom formats (BPCL/HPCL 5-column, IOCL Industry-Sharing multi-sheet) become first-class recognised formats; NEL/RBML/SIMPL parsers verified against samples you provide (B3).
4. **Product routing** — MS-Mother/XP95/XP100/HSD-Mother/XG split verified end-to-end so `fact_branded_monthly` updates in the same commit (already designed in; will be tested per-OMC).
5. **`validate_totals()` hard gate** — file-total vs to-insert-total by district×product, 0.5 KL tolerance, blocks commit on mismatch.
6. **Cache invalidation on commit** (F1) and **month_label standardisation** (F6).
7. **Targeted decimal handling** per your ruling on F7 — not blanket ROUND.
8. **Staging review gains "Mark as new COCO"** action (creates dim_ro row with coco_flag=1 + opens the coco_work_orders mini-form), alongside existing Add-to-dim_ro / Legacy-map.
9. **Delete** `omc_pipeline.py`; retire the Development-folder pipeline (F2).
10. **Regression harness** — pytest suite that runs every parser against archived real files (June 2026 set as first fixtures) and asserts district totals; extends `verify.py` to all tables.

---

## 6. Implementation Phases

| Phase | Scope | Depends on | Est. effort |
|-------|-------|-----------|-------------|
| **0. Baseline & hygiene** | Reconcile true DB (B1); branch cleanup + single deploy branch (F9); .gitignore + junk removal (F15); `config.py`; index/unique migration (F4); INGEST_KEY secret (F5); cache-clear fix (F1) | B1 answered | 0.5 session |
| **1. Pipeline v2** | Section 5 items 2–10; smoke-tested on real June files for all 6 OMCs | Phase 0; B3 samples | 1 session |
| **2. Global improvements** | Shared `download_df()` component on every table (all 16 tabs); filter consolidation per your rule (geo→sidebar; Industry/PSU + MS/HSD/Both + period→in-tab); latest-month-aware defaults; MASTER_RULES.md v1 | Phase 0 | 0.5–1 session |
| **3. COCO tab (17)** | Schema 4.2 + seed (Shevgaon fix; no-WO state for 232661/323570); 4 confirmed sections incl. TA-PPT re-use, Add/Remove COCO flows | Phase 0 | 1 session |
| **4. Swagat tab (18)** | Schema 4.1/4.3 + 38-row seed; 5 confirmed sections (header, OMC-wise extended-TA summary, extended-TA PPT view, XP conversion table, MoU %) | Phase 0 | 1 session |
| **5. REMM tab (21)** | Schema 4.4 + loader from sanitised master; computed S0–S8 status; S1–S3 login alerts; district→RSA drill-down; current-month default | Phase 0 | 1 session |
| **6. MIS generator** | One-click monthly MIS (needs your HQ/RO template — B3); Excel/PDF export | Phases 1–5 | 0.5 session |
| **7. Commissioning / Lube / EVCS-CNG-CBG (22–24)** | Schema derivation + tabs, once files are placed (B2) | Officer data | 1–1.5 sessions |
| **8. Hosting** | Execute Oracle VM migration plan (or Cloud-honest ingestion flow), systemd + nginx + backup cron | B4 decision | 0.5–1 session |

Each phase ends with: verify.py green, parser regression suite green, and a diff summary for your review before commit.

---

## 7. What I Need From You (checklist)

1. **The current live DB** (post-June, from `D:\Github\PDO-Dashboard-Demo`) or confirmation to re-ingest June here from the three June files (both paths are fine — the files are in `June 2026/`).
2. NEL / RBML / SIMPL sample monthly files (and June 2026 actuals when received).
3. Commissioning tracker Excel → `Commissioning/`.
4. Lube sales sample file → `Lube Sales/`.
5. EVCS/CNG/CBG tracker → `EVCS CNG CBG/`.
6. HQ / Regional Office MIS format sample.
7. Rulings on: F7 (rounding policy), F12 (Swagat HPCL count — Excel wins?), COCO no-work-order display (grey 5th tier OK?), B4 (hosting).
8. Priority RO list and Apna Ghar list — only when we reach tabs 19/20 (future session, per handoff).

---

## 8. Session Plan Proposal *(superseded by Part II, Section 13)*

- ~~This session: Phase 0 + Phase 1 + Phase 2.~~ → Revised after DO Data review: **build everything with data in hand in one mega-phase** (officer's instruction, 4 Jul).

---
---

# PART II — DO Data Review (4 July 2026)
*Findings from parsing the new `DO Data/` folder; revised schemas and action plan.*

## 9. Decisions Locked (from officer, 4 Jul)

1. **DB baseline:** develop on this folder's DB; re-ingest June 2026 here — now upgraded: re-ingest from the **raw OMC files** in `DO Data/OMC Sales Figures files/` (not the custom summaries), making June the first live test of pipeline v2.
2. **Hosting:** Oracle VM migration is the target.
3. **Rounding:** targeted artifact fix only.
4. **Sequencing:** everything possible with existing data in **one phase**; later phases test and fill the missing links.

## 10. What I Understood From Each File

### 10.1 OMC raw sales files — parser coverage CONFIRMED
The raw formats map 1:1 onto the six parsers already in `parsers.py`. Pipeline v2 is a validation/refactor job, not new parser development:

| File | Format | Existing parser | Notes |
|------|--------|----------------|-------|
| BPC Jun'26 Ahmednagar | CC NO \| RO NAME \| DISTRICT \| MS \| HSD | `bpcl_q002_nagar` | MS/HSD only — **no Speed column** (see Q4 below) |
| BPCL Jun'26 Pune-Satara (.xls) | **MHTML web-archive** Q145 BI export, volumes ×1,000 L, CC codes, two period blocks | `bpcl_q145_ps` + `_read_mime_html_xls` | The .xls is a fake — it's a Web Archive; existing MIME reader handles this |
| HPC Jun'26 Ahmednagar | Sr \| CC \| **SAP** \| Name \| Loc \| Taluka \| Dist \| MS HIST/CURR \| HSD HIST/CURR \| **POWER HIST/CURR** | `hpcl_nagar` | Branded (Power) present in raw ✔ |
| HPC Jun'26 Pune-Satara | CC \| District \| Outlet \| Loc \| MS HIST/CURR \| HSD HIST/CURR | `hpcl_ps` | No branded columns |
| IOCL June SAP dump | Ship-To \| Sales district \| Sales Office \| Material \| Inv.Qty (KL) | `iocl_sap_dump` | Material codes → MATERIAL_MAP routes Mother/XP95/XP100/XG ✔ |
| SalesFormat_Apr/May'26 (.xls) | Company (518=NEL, 519=RBML, 521=SIMPL) \| ro_code \| yyyymm \| ms \| hsd | `pvt_sales_format` | Real OLE2 xls; company map already in parsers. June arrives ~7th–8th |

Nov-25 files included as historical fixtures — perfect for the pytest regression suite.

### 10.2 LOI & Commissioning Master (268 rows × 92 cols, 8 sheets)
The main register is a full lifecycle tracker: **LOI identity** (location, holder, LOI no/date/age, class A–E, Type A/B, RO/KSK, site type, MS/HSD potential, district, RSA) → **commissionability assessment** → **8 statutory permissions** (Mojnai, Building Plan/NA, Police, NH/PWD, MSEB, Industrial Safety, Wildlife, Forest — each Yet-to-Apply/Applied/Received/NA) → **site readiness → drawing/estimate/concept note → IO → advance tender → Work Order (no, date, contractor, target) → PESO → commissioning** (SAP code + RO name assigned on completion — 8 rows commissioned, 246 pending, 13 cancelled).
Supporting sheets: RSA-wise Summary pivot, monthly plan-vs-actual ("Review PPT update", Apr'26–Mar'27), "Planned 50 Sites" plan tracker, 10-year OMC commissioning history, NOC/advance-tender shortlist.
**Key insight you stated:** pre-commissioning tracking keys are (a) Location SN per advertisement and (b) LOI number — *not* SAP code. SAP joins the record only at commissioning, which is exactly the dim_ro hand-over point (`data_complete_flag='No'`).

### 10.3 CNG / CBG (62 + 25 rows)
Master attributes (RO Code=SAP, sales area, site type, COM, comm. year, sales start date, CGD company, "Under CNG Corpus" flag) + monthly sales columns **APR.22 → MAR.27** with FY totals. Values look like **kg**. Straightforward fact + master pair. The commissioning-*process* tracker for CNG/CBG (permissions, CGD coordination, infra) is **not yet shared**; EVCS likewise (process-monitoring only, no sales).

### 10.4 Lubes (692 + 689 rows)
RO-wise monthly: **4T / Others / Total** per month, plus separate **DEF** sheet. Data actually runs **Apr 2022 → Jun 2026** (the sheet name says Apr-25, but 51 months are present — so "earlier data later" is already partly moot; see Q3).

### 10.5 IOCL Dealer Lat-Long CSV (788 rows)
GPS coordinates, address, highway no, RO type, contact details, sales officer/DRSM hierarchy, and **Last Load date** — covering IOCL ROs including neighbouring DOs (Goa DO rows present). This changes an earlier assumption: the Swagat extended-TA handoff said "no GPS available." With this file we *can* compute highway-distance proximity for IOCL ROs, do map views, and derive a "days since last load" ops flag. Purpose/scope needs your confirmation (Q2).

## 11. Revised / New Schemas (additions to Section 4)

### 11.1 commissioning_pipeline (from LOI master)
One wide master table mirroring the register (the Excel stays the working document; DB gets a monthly full-refresh snapshot), keyed on a surrogate + natural keys:
```sql
CREATE TABLE loi_master (
    loi_id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_sn INT, loi_number TEXT, loi_date TEXT,
    location_desc TEXT, loi_holder TEXT, holder_contact TEXT,
    rsa_name TEXT, district TEXT, market_class TEXT, site_type_ab TEXT,
    ro_ksk TEXT, type_of_site TEXT, marketing_plan TEXT, category TEXT,
    ms_potential REAL, hsd_potential REAL, strategic TEXT,
    commissionable TEXT, comm_plan_fy TEXT, non_comm_reason TEXT,
    -- statutory permissions (each: Yet to Apply/Applied/Received/NA)
    perm_mojnai TEXT, perm_building_plan TEXT, perm_police TEXT,
    perm_nh_pwd TEXT, perm_mseb TEXT, perm_ind_safety TEXT,
    perm_wildlife TEXT, perm_forest TEXT,
    site_readiness TEXT, layout_drawing TEXT, concept_note TEXT,
    estimate TEXT, io_available TEXT, io_no TEXT,
    tender_status TEXT, wo_number TEXT, wo_date TEXT, contractor TEXT,
    wo_completion_target TEXT, site_handover_date TEXT,
    peso_prior TEXT, peso_final TEXT,
    expected_noc_month TEXT, expected_comm_month TEXT,
    final_status TEXT,          -- Pending / Commissioned / Cancelled
    sap_code TEXT,              -- filled at commissioning → joins dim_ro
    snapshot_date TEXT          -- refresh version stamp
);
```
Derived at render (never stored): LOI age & bucket, stage funnel position, permission-completion %. Tab 22 v1 reports: stage funnel, LOI-ageing matrix, RSA summary (replicates Summary sheet), monthly plan-vs-actual, commissioned-this-FY list with dim_ro link. Your specific HQ report formats slot in later without schema change.

### 11.2 alt_fuel_master + fact_alt_fuel_monthly (from CNG CBG.xlsx)
```sql
CREATE TABLE alt_fuel_master (
    sap_code TEXT, fuel_type TEXT,        -- 'CNG'|'CBG' ('EVCS' later)
    site_type TEXT, com TEXT, comm_year TEXT, sales_start_date TEXT,
    cgd_company TEXT, corpus_flag TEXT, station_type TEXT,
    PRIMARY KEY (sap_code, fuel_type)
);
CREATE TABLE fact_alt_fuel_monthly (
    sap_code TEXT, fuel_type TEXT, fy_code TEXT, month_index INT,
    qty_kg REAL,
    PRIMARY KEY (sap_code, fuel_type, fy_code, month_index)
);
```
Alt-fuel *commissioning-process* tables deferred until you share that tracker.

### 11.3 fact_lube_monthly (from Lubes.xlsx)
```sql
CREATE TABLE fact_lube_monthly (
    sap_code TEXT, product TEXT,          -- '4T' | 'Others' | 'DEF'
    fy_code TEXT, month_index INT, qty_l REAL,
    PRIMARY KEY (sap_code, product, fy_code, month_index)
);
```
('Total' is computed, never stored.) Loads Apr'22–Jun'26 immediately.

### 11.4 dim_ro geo enrichment (from Lat-Long CSV — pending Q2)
```sql
CREATE TABLE dim_ro_geo (
    sap_code TEXT PRIMARY KEY, latitude REAL, longitude REAL,
    address TEXT, pin_code TEXT, ro_type TEXT,
    sales_officer TEXT, so_mobile TEXT, last_load_date TEXT
);
```

## 12. Clarifications — RESOLVED 4 Jul (officer's rulings)

**Q1 — Commissioning ingestion protocol → BOTH.** Monthly bulk upload-replace at month end (Excel stays master) **plus** in-dashboard row edits between uploads to keep the dashboard current. Design consequence: `loi_master` gets an `edit_source`/`edited_at` audit trail (`loi_edit_log` table); on monthly upload, a pre-replace diff shows any local edits not yet reflected in the incoming Excel so nothing is silently lost — officer reconciles, then replace proceeds.

**Q2 — Lat-Long CSV → Geo + contacts.** Load into `dim_ro_geo`: map views, extended-TA distance support, dealer/officer contacts + Last Load in Finder.

**Q3 — Lubes → full range Apr 2022 → Jun 2026.**

**Q4 — BPCL Speed → arrives in shared Excel sheets (usually, or separate OMC sheets).** Pipeline rule: parsers must *detect* branded columns — Speed, Hi Speed Diesel / Speed Diesel — whenever present in any BPCL sheet and route them as daughter brands. **Locked rule: MS and HSD are Mother; all branded are daughters** — daughters always ingest alongside, never instead of, mother volumes.

**Q5 — CNG/CBG unit (kg?) and DEF unit (litres?)** — still to confirm, minor; will verify magnitudes against known station throughput during build.

**Q6 — Swagat HPCL count (Excel 14 vs handoff 13)** — treating Excel as authoritative unless you flag otherwise.

## 13. REVISED ACTION PLAN (supersedes Section 8)

### Mega-Phase 1 — "everything with data in hand" (this build cycle)
Ordered so each step's output is the next step's test bed:

| Step | Deliverable | Data source |
|------|------------|-------------|
| 1.1 | Phase-0 hygiene: true-DB baseline, config.py, unique index + indexes, cache-clear fix, INGEST_KEY, junk cleanup, branch decision | — |
| 1.2 | **Pipeline v2** refactor (Section 5) + pytest regression suite using Nov'25 + Apr/May/Jun'26 raw files as fixtures | `OMC Sales Figures files/` |
| 1.3 | **June 2026 re-ingestion from raw** through pipeline v2 (BPCL ×2, HPCL ×2, IOCL SAP dump) — validates B1 and the pipeline in one stroke; reconcile against HANDOFF.md June district totals | same |
| 1.4 | Global improvements: download buttons everywhere, filter consolidation, latest-month defaults, MASTER_RULES.md v1 | — |
| 1.5 | **COCO tab (17)** + coco_work_orders seed (Shevgaon fix, no-WO grey tier) | COCO master |
| 1.6 | **Swagat tab (18)** + tags + swagat_extended_ta seed (38 rows) | Swagat TA xlsx |
| 1.7 | **REMM tab (21)** + remm_master/remm_payments load, computed S0–S8, login alerts | REMM master |
| 1.8 | **Commissioning tab (22) v1** + loi_master load + upload-refresh protocol | LOI master |
| 1.9 | **Lube tab (23)** + fact_lube_monthly load (Apr'22–Jun'26) | Lubes.xlsx |
| 1.10 | **Alt-fuel tab (24) v1** — CNG/CBG sales monitoring + master | CNG CBG.xlsx |
| 1.11 | (pending Q2) dim_ro_geo load + map/contact features | Lat-Long CSV |
| 1.12 | Full verification: verify.py extended to all new tables, end-to-end smoke, diff report for your review | — |

### Phase 2 — testing & missing links (subsequent sessions)
- NEL/RBML/SIMPL June ingestion when received (~7th–8th) — *live test of pipeline v2 by you, self-service*
- Your specific commissioning report formats → added to Tab 22
- Alt-fuel commissioning-process module (CNG/CBG/EVCS) when tracker is shared
- MIS generator (needs HQ/RO template)
- Apna Ghar (19) + Priority RO (20) tabs (lists to be provided)
- Oracle VM migration + genuinely-persistent self-service ingestion
- LLM layer (per Planned Incorporation of LLM.md)

*Part II awaiting your approval. On "go": I start at Step 1.1.*

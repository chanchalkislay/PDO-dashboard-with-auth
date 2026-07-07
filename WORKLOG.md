# WORKLOG — Pune DO Dashboard v2 Build
**Build plan:** V2_ANALYSIS_AND_IMPLEMENTATION_PLAN.md (Part II, Section 13)
**Rule:** every completed step is logged here immediately. If a session ends mid-build, resume from the last ✅ entry. ⏳ = in progress. Each entry lists files touched + verification done.

## Resume instructions for a fresh session
1. Read V2_ANALYSIS_AND_IMPLEMENTATION_PLAN.md (both parts).
2. Read this log top to bottom; resume at the first non-✅ step.
3. DB work pattern: NEVER write SQLite directly on the mount — copy to /tmp, modify, binary write-back (see ingest/pipeline.py `_load_db`/`_write_back`).
4. Sandbox paths: project = `/sessions/<session>/mnt/Github Copy 1 July/` (bash) = `D:\Claude Cowork\Github Copy 1 July\` (file tools).

## Decisions taken autonomously
*(logged as they occur)*

---

## Step log

### ⏳ 1.1 Hygiene — STARTED 2026-07-04
Planned: junk-file cleanup; delete orphan ingest/omc_pipeline.py; config.py at repo root; DB migration (unique index + perf indexes on fact_monthly); cache-clear fix in tab_16; INGEST_KEY hardening; month_label standardisation; .gitignore.

### ✅ 1.1 Hygiene — DONE 2026-07-04
- Deleted: app/.fuse_hidden* (20+), all __pycache__, ingest/omc_pipeline.py (orphan third pipeline). NOTE: `~$*.xlsx` Excel lock files could not be deleted (held open by Excel on officer's machine) — harmless.
- **config.py created at repo root** — COVERAGE_DISTRICTS, MH_DISTRICTS, DISTRICT_ALIASES, OMC universe, FY helpers, canonical month_label(), RECON_GUARD baselines, OUTLIER_FACTOR, TOTALS_TOLERANCE_KL, BRANDED_DAUGHTERS (mother/daughter rule).
- ingest/parsers.py: COVERAGE_DISTRICTS now imported from config; added detect_district_col() + filter_to_coverage().
- ingest/pipeline.py: guard baselines + month_label from config; added validate_totals() (post-insert DB-vs-file hard gate, sap-scoped) + unknown_volume_gate() (unknown SAPs with volume block commit); both wired into Pipeline.commit().
- app/app.py: INGEST_KEY hardening — st.secrets → env → locked; NO default password. Repo root on sys.path.
- app/bootstrap.py: repo root on sys.path (enables `import config`, `import ingest.*` on every page).
- app/tab_16_ingest.py: st.cache_data.clear() after successful commit AND after rollback (fix F1 — stale-dashboard bug); hard-coded district list removed (uses config).
- **DB migration applied** (backup: app/backups/pune_do_backup_*_pre_migration_1_1.db):
  - ux_fact_key UNIQUE(sap_code,product,fy_code,month_index); ix_fact_fy_mi; ix_fact_sap; ix_fact_omc
  - month_label standardised to 'APR.25' canonical format — 8,640 rows updated; integrity_check ok
- .gitignore: added ~$*, backups/, *.db.tmp, tests caches.
- Verified: all app/*.py + ingest/*.py + config.py compile; imports OK; detect/filter helpers tested.

**⚠ ENVIRONMENT NOTE (important for future sessions):** host→VM file sync clips file TAILS when files are edited via file tools (Edit/Write). Four files (pipeline.py, parsers.py, app.py, tab_16_ingest.py) had truncated tails on the VM and were stitched back via bash. **RULE: modify existing files via bash (python inline edits); create new files with Write then verify VM-side line count.**

### ✅ 1.2 Pipeline v2 refactor + regression tests — DONE 2026-07-04
- detect_format: recognises BPCL Q145 BI exports saved as Web-Archive (.xls MIME HTML) via Bl:Volume/Division signature.
- _read_mime_html_xls: now scans ALL html parts and picks the largest table (was picking a 1×1 title table for some files).
- _parse_bpcl_q002_nagar REWRITTEN: header-label-driven MS/HSD column detection (regex word-boundary), per-row DISTRICT column support (June'26 simple format), classic section-header fallback, Speed / Hi Speed Diesel daughter auto-detection.
- _parse_bpcl_q145_ps: proper MS/HSD block selection + Speed/Hi-Speed-Diesel daughter extraction.
- **DAUGHTER SEMANTICS DISCOVERED & LOCKED (critical):** verified against DB history — IOCL SAP dump materials are EXCLUSIVE (fact = mother+daughters: Apr'26 DB MS 32,162 = 30,787+1,375); HPCL/BPCL daughter columns are INCLUSIVE subsets (fact = Mother only: Nov'25 DB HPCL Adnagar MS 6,610 = mother, Power 376.5 separate). Implemented as _fact_base() in pipeline.py, used by both _insert_fact_monthly and validate_totals. **Without this fix the old pipeline would have double-counted HPCL Power into MS.**
- tests/test_parsers_regression.py: 15 file cases with exact expected totals (all cross-verified vs HANDOFF June table and live DB April), daughter expectations, IOCL semantics test, and an end-to-end Pipeline.commit test on a throwaway DB (gates, mother-only rule, branded rows, JUN.26 label). ALL PASS.
- KNOWN OPERATOR CAVEAT: "BPC May'26 Ahmednagar.xls" is a CUMULATIVE Apr–May BI export (no monthly block) — such files must not be ingested as a month; officer should request monthly exports. To document in MASTER_RULES.md.
- Parser June totals match HANDOFF manual table EXACTLY (BPCL 8,208/19,004 + 35,851.2/52,837.1; HPCL 7,021.5/15,275.5 + 42,177.7/73,044.1).

### ✅ 1.3 June 2026 re-ingestion from raw files — DONE 2026-07-04
DB backups taken before each step in app/backups/. Final state: fact_monthly 372,631 rows; dim_ro 2,168; fact_branded 17,776; integrity ok; 8 ingestion_log runs; regression suite green.
- dim_ro prep per HANDOFF: +4 BPCL commissioning ROs (265362 Katke w/ NEW TA M06-078 Jambulwadi, 265220 Khandve → M06-036, 267354 Jyoti Kranti + 267390 Sujit as data_complete_flag='No'); legacy maps 196739→196740, 140947→194626, 100129→221676, 100115→183993, 41096501→41071411; Kokamthan 377124→393411 with 172 fact + 34 XP + 1 ITPS rows migrated.
- June committed via Pipeline v2 from RAW files: BPCL Nagar (372 rows), BPCL Q145 PS MHTML (724), HPCL Nagar (304), HPCL PS (858), IOCL SAP dump (1,203 = HANDOFF count exact) + 131 IOCL June branded rows + 59 HPCL branded rows auto-written.
- **Pipeline v2 fixes discovered during live run:**
  1. duplicate_check rewritten — data-driven SAP-overlap (BPCL/HPCL send a month as TWO files; omc+month key blocked the second file). ingestion_log rebuilt without UNIQUE(omc,fy,month) → per-file logging.
  2. ux_fact_key index rebuilt WITH omc (BPCL CC and IOCL SAP ranges collide numerically).
  3. **dim_ro matching + enrichment now OMC-SCOPED** (was OMC-blind: live case BPCL CC 180555 = IOCL sap 180555 'Bhosale Sales' — BPCL volume was silently attributed to the IOCL outlet; 2 bad rows created+removed; history scanned: 0 other cases ever).
- DECISION (officer to review): BPCL file code 180555 'NEELKANTH PETROLEUM' mapped → dim_ro 180556 'Neelkanth PETROLEUM' (BPCL, Satara, Karad–Masur Rd; adjacent code, exact name, target had no June rows). CONSEQUENCE vs HANDOFF table: 20 KL MS + 420 KL HSD moved Pune→Satara (officer's manual session had them under Pune under code 180555).
- DECISION: IOCL Pune MS is 22,249.5 vs HANDOFF 22,266.5 (−17.0 KL) — raw SAP dump is authoritative (manual session used the Industry Sharing summary sheet). All other 17 district×product cells match HANDOFF exactly.
- Targeted decimal fix (officer-approved): 17 multi-decimal artifact rows rounded (5 BPCL + 4 HPCL outlets, exactly the ones HANDOFF flagged). Legitimate .5 KL values untouched.
- April 2026 IOCL branded backfill: 140 rows (XP95/XP100/XG) from SAP Dump April.xlsx. GAP: May 2026 IOCL branded needs the May SAP dump (not in DO Data folder) — ask officer.
- staging_unknown_ros: clean (180555 resolved as mapped_to:180556).

### ✅ 1.4 Global improvements — DONE 2026-07-04
- components/downloads.py + CSV download buttons auto-wired under every st.dataframe across tabs 01–15 (20 buttons; tab_05 already had PPT download; tab_06 renders HTML grid). DECISION: CSV (UTF-8-BOM, Excel-openable) instead of .xlsx generation — keeps renders fast; officer can override.
- Filter consolidation AUDITED: all in-tab widgets are already compliant (denominator/sort/TA-picker/period only; no geo duplicates). No changes needed.
- sidebar.py: Single-month / Cumulative / Custom-months defaults now follow the LATEST INGESTED month (was hard-coded Mar).
- MASTER_RULES.md v1.0 written (architecture, locked conventions incl. daughter semantics, pipeline v2 flow+gates, format table, operator caveats, deployment notes, new-module schemas).
- DECISION: global Product radio stays in sidebar (single source of truth); "Both MS+HSD" view deferred to MIS generator rather than reworking 16 tabs. Officer can override.

### ✅ 1.5–1.11 New modules — DONE 2026-07-04
DB backup before module migration: app/backups/pune_do_backup_*_pre_modules.db
**Schema + seeds (all in pune_do.db):**
- dim_ro + swagat_tag/apna_ghar_tag/coco_flag; coco_flag=1 for 16 COCOs; swagat_tag='Swagat' for 135645.
- coco_work_orders: 16 rows (Shevgaon 354938 date corrected 01.11.2026→01.11.2025 per officer; Rajgurunagar 232661 + Velhe 323570 have no WO → grey 'No Work Order' tier).
- swagat_extended_ta: 38 rows for 135645 (Excel authoritative: HPCL 14).
- remm_master: 218 | remm_payments: 1,883 (FY2025-26 monthly).
- loi_master: 267 rows (246 Pending / 13 Cancelled / 8 Commissioned) + loi_edit_log.
- fact_lube_monthly: 100,650 rows Apr'22–May'26 (⚠ Jun'26 column BLANK in source workbook — officer to update file or provide values).
- alt_fuel_master: 49 CNG + 12 CBG stations | fact_alt_fuel_monthly: 3,050 rows (kg).
- dim_ro_geo: 788 rows (722 Pune DO + neighbouring DOs kept for border analysis).
**New tabs (all AppTest-green):**
- tab_17_coco (17_coco.py, 'Programmes'): alert chips incl. grey No-WO tier, sales vs TA-avg + Policy Target (highest IOCL RO KLPM 12mo pre-appointment, computed from fact_monthly), TA-PPT re-use, urgency-sorted WO table, detail panel, admin Add/Close COCO flows (FUSE-safe writes + cache clear).
- tab_18_swagat (18_swagat.py, 'Programmes'): header card, OMC-wise ext-TA summary (LHS/RHS), ext-TA PPT grid (Swagat ⭐-highlighted), XP conversion table (Swagat row first), MoU % + PSU MoU %; multi-Swagat selector auto-appears.
- tab_21_remm (21_remm.py, 'Assets & Infra'): computed S0–S8 (never stored), S1/S2/S3 login alert, district→RSA drill, register + FY payment matrix.
- tab_22_commissioning (22_commissioning.py): stage funnel (derived from permission/tender/WO/PESO fields), LOI-ageing × RSA matrix, filterable register, detail JSON, audited interim-edit form + monthly upload-replace entry point w/ edit-log display.
- tab_23_lube (23_lube.py, 'Operations'): product filter (4T/Others/DEF), trend chart, district/RSA + RO-wise CY-vs-LY.
- tab_24_alt_fuel (24_alt_fuel.py): CNG/CBG selector, nil-selling-station alert (last 3 data months), trend, station-wise table.
- tab_14_finder: new section ④ RO Location & Contacts — geo search, contact card, st.map (single + all-scope).
- core.py: 9 new cached loaders + coco_alert_tier() + remm_status() helpers.
- app.py navigation: Programmes + Assets & Infra groups; Lube under Operations.

### ✅ V4 repo debugging session — 2026-07-06 (Fable 5)
Repo: D:\Github\PDO-Dashboard-V4 (all debugging now here; officer pushes via GitHub Desktop).

**BUG 1 (reported) — Commissioning stage funnel showed only 2–3 stages.**
Root cause: `if r.get("wo_number"):` — SQL NULLs surface as float NaN on some pandas versions, and float('nan') is TRUTHY → every live LOI classified '6. Work Order'. Fix in tab_22:
- new `_v()` NaN-safe field getter used throughout `_stage()`;
- a real Work Order now requires ≥4 digits in wo_number (placeholder texts ignored);
- register vocabulary handled: tender 'Yes' → Tendering; NOC 'Received/Recieved/Recived/Yes' variants recognised;
- funnel now always lists ALL 7 stages (zeros included).
Verified identical, correct stage distribution in BOTH None- and NaN-returning pandas environments: 128 LOI Issued / 86 NOCs in Process / 1 NOCs Complete / 23 IO / 8 Tendering / 8 Commissioned / 13 Cancelled.

**BUG 2 (found) — `_age_bucket` sent missing/unparseable LOI dates to '>5Y'** (NaN days compare False all the way down). Now returns 'Unknown'.

**BUG 3 (found) — core.coco_alert_tier NaN trap:** a COCO without a work order could misreport as green 'Active' instead of grey 'No Work Order' on NaN-pandas. Now uses _safe_date().

**BUG 4 (found) — REMM 'Active rent' KPI always '—':** `revised_rent or initial_rent` returns NaN whenever revised_rent is NULL because REAL columns ALWAYS load as float NaN. Replaced with vectorised fillna chain. (This one occurred in every environment.)

**BUG 5 (found) — Finder geo map crash risk:** `if r.latitude and r.longitude` NaN-truthy → st.map(NaN). Now pd.notna guards.

**BUG 6 (cosmetic) — Swagat header showed 'nan'** for missing RSA/highway. Guarded.

**BUG 7 (found) — regression suite broke after GitHub push** because filenames were sanitised (apostrophes→underscores, e.g. BPC June_26 Ahmednahar.xlsx). Test fixtures now resolve names tolerantly via glob.

Also: tab_17 days_left/policy-target/TA-code NaN guards; tab_22 'Commissionable' KPI now strips whitespace ('Yes ' counted).

**Verification (this repo):** regression suite 3/3 PASS · verify.py 48/48 PASS · AppTest green on pages 01, 14, 17, 18, 21, 22, 23, 24.
**Committed locally — officer to push via GitHub Desktop.**

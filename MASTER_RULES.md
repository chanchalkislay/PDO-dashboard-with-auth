# MASTER RULES — Pune DO Dashboard
*Living technical documentation: business rules, data structures, pipeline logic.*
*v1.0 — 4 July 2026 (build session). Supplements Rules_and_Definitions_v1.2.1.csv (204 locked rules).*

## 1. Architecture
- Streamlit multi-page app (`app/app.py` → `st.navigation` → `app/pages/NN_*.py` wrappers → `app/tab_NN_*.py` modules).
- All queries/computation in `app/core.py`; shared filter state via `app/sidebar.py` + `app/context.py`; `app/bootstrap.py` runs on every page (sys.path + NRO banner).
- Single SQLite DB `app/pune_do.db`. All writes MUST use the FUSE-safe pattern: read → /tmp copy → modify → binary write-back via `os.replace` (see `ingest/pipeline.py:_load_db/_write_back`). Never shutil.copy or in-place sqlite on the mounted file.
- **Central config: repo-root `config.py`** — COVERAGE_DISTRICTS, OMC universe, FY helpers, canonical month_label(), reconciliation-guard baselines, tolerances, branded daughter registry. To adapt the app to another DO: change `COVERAGE_DISTRICTS` (and re-baseline RECON_GUARD after first clean FY).

## 2. Locked conventions
- **FY**: April=month_index 1 … March=12. `fy_code` = '2026-27'. June 2026 = ('2026-27', 3).
- **month_label**: canonical `'JUN.26'` format (config.month_label). All 372k+ rows standardised 2026-07-04.
- **Market share**: OMC ÷ selected universe (PSU-3 default; Industry-6 optional) × 100.
- **KLPM** (Rule #194): volume ÷ months-in-period ÷ ROs-in-scope.
- **Nil-selling** (Rules v1.2.1): NIL = 0 in m0..m2; About-to-go-nil = 0 in m0,m1; Revival = >0 in m0 after 3 zero months; PRCN: negatives clipped to 0; YTS = never-sold RO commissioned ≤12 months.
- **Mother/daughter rule (officer, 2026-07-04)**: MS and HSD are mother products; every branded fuel is a daughter tracked in `fact_branded_monthly`. Parsers auto-detect daughter columns whenever present.
- **Daughter semantics in fact_monthly (verified vs 7-yr history)**:
  - IOCL SAP dump: materials are EXCLUSIVE slices → fact volume = mother + daughters (16730 + 17295 + …).
  - HPCL / BPCL: daughter columns are subsets already inside the product figure → fact volume = Mother rows ONLY.
  - Implemented in `pipeline._fact_base()`; used by insert AND the totals gate.

## 3. fact_monthly integrity
- UNIQUE index `ux_fact_key(omc, sap_code, product, fy_code, month_index)` — omc is part of the key because BPCL CC numbers and IOCL SAP codes share numeric ranges (real case: 180555).
- All dim_ro matching in the pipeline is **OMC-scoped** (same reason).
- Perf indexes: (fy_code, month_index), (sap_code), (omc).

## 4. Ingestion pipeline v2 (`ingest/`)
Flow: parse (`parsers.detect_and_parse`) → OMC-scoped dim_ro cross-check → legacy-code remap → duplicate check (SAP-overlap based; a month legitimately arrives as multiple files, e.g. BPCL Nagar + Pune-Satara) → outlier check (>3× prior-FY same month) → **GATE 1: unknown SAP codes with volume block commit** (resolve as new-RO / legacy-map, or force to stage-and-skip) → snapshot → insert fact_monthly (+ta/rsa/district enrichment) + fact_branded_monthly → **GATE 2: post-insert DB totals must equal file totals (±0.5 KL)** → reconciliation guard (IOCL FY2025-26 share baselines ±0.5pp, config.RECON_GUARD — re-baseline yearly) → per-file ingestion_log entry → atomic write-back. Rollback available from snapshot.

### Recognised formats (regression-tested in tests/test_parsers_regression.py)
| Format | File pattern | Notes |
|---|---|---|
| iocl_sap_dump | Ship-To Party \| Material \| Inv.Qty | MATERIAL_MAP: 16730 MS, 17295 XP95, 17100/17101 XP100, 50700 HSD, 50800 XG |
| bpcl_q002_nagar | classic Q002 + simple `CC\|NAME\|DISTRICT\|MS\|HSD` | header-driven column order; per-row district |
| bpcl_q145_ps | Q145 BI export (.xlsx or **.xls Web-Archive MIME**) | volumes '* 1,000 L' = KL; first block = current month |
| hpcl_nagar | Sales Data sheet, MS/HSD HIST+CURR + Power/Turbojet | CURR used; daughters separate |
| hpcl_ps | Customer Code \| MS/HSD HIST+CURR | |
| pvt_sales_format | company(518 NEL/519 RBML/521 SIMPL) \| ro_code \| yyyymm | fy/month read from file |
| pvt_ro_wise | generic user-compiled | |

### Operator caveats
- **Cumulative BI exports**: some BPCL month files are Apr→month CUMULATIVE (e.g. "BPC May'26 Ahmednagar.xls" — single measure blocks, no month block). Never ingest as a month; request monthly export. Tell-tale: dry-run totals ≈ 2× a normal month.
- Excel lock files (`~$…`) and files open in Excel on the officer's PC cannot be read/deleted.
- May 2026 IOCL branded (XP95/XP100/XG) pending: needs May SAP dump.

## 5. Access & deployment
- Ingest admin unlock: `INGEST_KEY` via Streamlit secrets or env var. **No default password.** Unset ⇒ admin locked.
- Hosting decision (officer, 2026-07-04): migrate to Oracle VM (see June 2026/Oracle VM Migration Plan.md). Until then note: on Streamlit Community Cloud the container FS is EPHEMERAL — UI ingestion does not persist across redeploys; authoritative ingestion is local + git push.
- After any successful commit or rollback the app calls `st.cache_data.clear()` (fix F1) — dashboards reflect new data immediately.

## 6. New modules (build session Jul 2026)
Schemas per V2_ANALYSIS_AND_IMPLEMENTATION_PLAN.md Part I §4 / Part II §11:
- `coco_work_orders` — COCO register; alert tiers computed at render: Expired / Critical <1m / Expiry-Critical 1–2m / Expiring-Soon 2–3m / Active >3m / **No-Work-Order (grey)**. COCO identity: dim_ro.coco_flag=1 (IOCL + name LIKE '%COCO%'). Shevgaon 354938 appointment = 01.11.2025 (Excel typo 2026 overridden, officer-confirmed).
- `swagat_extended_ta` — officer-maintained extended-TA RO list per Swagat; seeded 38 rows for SAP 135645; competitor codes may not exist in dim_ro (join gracefully).
- `remm_master` + `remm_payments` — REMM_ID permanent key; lease status S0–S8 COMPUTED at load, never stored; S1/S2/S3 alerts on login; FLAG/PENDING/OWN REMM_ID semantics (no payment processing).
- `loi_master` (+ `loi_edit_log`) — commissioning register; monthly Excel upload-replace + in-dashboard interim edits; pre-replace diff protects local edits. Keys: location SN + LOI number; SAP joins only at commissioning.
- `fact_lube_monthly` — 4T/Others/DEF litres by RO-month (Apr'22–Jun'26 loaded); 'Total' always computed.
- `alt_fuel_master` + `fact_alt_fuel_monthly` — CNG/CBG station master + monthly kg; EVCS process-monitoring later.
- `dim_ro_geo` — lat/long, address, contacts, sales-officer hierarchy, last-load date (IOCL master CSV).

## 7. Global UI rules
- Geo/RSA/COM/highway filters live in the SIDEBAR ONLY. In-tab widgets restricted to: Industry/PSU denominator, product/brand focus, time-period and sort controls (verified compliant across tabs 01–15).
- Every report table has a CSV download (`components/downloads.py`; UTF-8-BOM so Excel opens it directly).
- Sidebar month defaults follow the latest ingested month.

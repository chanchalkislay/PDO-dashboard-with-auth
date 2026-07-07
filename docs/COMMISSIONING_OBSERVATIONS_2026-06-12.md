# New RO Commissioning — Identification & Inclusion Observations
**Date:** 2026-06-12  
**Session:** Demo branch build, data through May 2026  
**Purpose:** Capture every decision made when ingesting new commissionings so the WIP ingestion pipeline can be rebuilt with correct rules.

---

## 1. Data Source Format (Apr-May26.xlsx)

Single-sheet workbook with **2,162 RO rows** covering all 6 OMCs across all 3 districts.

**Column layout:**
| Col | Field | Notes |
|---|---|---|
| A | SAP CODE | Primary key for matching to dim_ro |
| B | RETAIL OUTLET NAME | May contain legacy codes/names in brackets |
| C | OIL CO | OMC identifier |
| D | YOC | Year of Commissioning (FY format e.g. "2026-27") |
| E | SALES AREA | RSA name (may not match dim_ro exactly) |
| F | DOC | Date of Commissioning (present for IOCL; absent for others) |
| G | Category | |
| H | TRADING AREA NAME | Free-text TA name (must be fuzzy-matched to dim_ta) |
| I | DISTRICT | Pune / Ahmednagar / Satara |
| J | CLASS OF MKT | A / C / D1 / D2 / E |
| K | HIGHWAY NO. | For D1/D2 sites |
| L/M | MS/HSD May 2026 | Current month volumes |
| N/O | MS/HSD Apr 2026 | Previous month volumes |
| P/Q | MS/HSD CUM.CY | Cumulative current year volumes |

**Key property:** This is a master-data-plus-volumes file. It is NOT a raw SAP dump. It contains pre-curated TA assignments, RSA assignments, COM classification, and highway details. This makes it highly reliable for commissioning identification but means it cannot be used as a substitute for the SAP dump for IOCL (which has material-code-level detail).

---

## 2. New Commissioning Identification Rules (Observed)

### Rule C-1: Primary identifier — SAP code not in dim_ro
Any SAP code present in the sales file that is absent from `dim_ro.sap_code` AND `dim_ro.legacy_sap_codes` is a candidate new commissioning or data error. Total found this session: **19 candidates** from 2,162 file rows.

### Rule C-2: Data entry error filter
Filter out candidates with implausibly short SAP codes (< 5 digits). This session: SAP codes "2" and "5" (HPCL) were single-digit — clearly data entry errors. These were resolved by matching RO name to existing dim_ro entries:
- File SAP "2" = dim_ro SAP `41052554` (B.V. Vikhe, HPCL Ahmednagar)
- File SAP "5" = dim_ro SAP `41052120-M` (Kamal Petrol Depot, HPCL Ahmednagar)

**Pipeline rule:** Reject SAP codes < 5 digits; flag to user with name-based match suggestion from dim_ro.

### Rule C-3: COCO / SAP Reassignment identification
COCO outlets and outlets with dealer changes frequently receive new SAP codes. These are NOT new physical outlets. Identification signature:
- New SAP code not in dim_ro
- RO name contains a bracketed reference to an older name and/or 6-digit code, e.g.: `COCO WADUJ (232087 - Torve Petrol Station)`
- Name-based fuzzy match against dim_ro returns a high-confidence existing entry
- **OR**: dim_ro contains an entry with matching name structure that has NO recent sales (suggesting it was already superseded)

This session examples:
- File `392208` (COCO WADUJ) → matched dim_ro `379479` via name
- File `392222` (COCO SHRIGONDA) → matched dim_ro `378277` via name

**Pipeline rule:** For SAP reassignments:
1. Update `dim_ro.sap_code` to new code
2. Move old sap_code to `dim_ro.legacy_sap_codes` (comma-separated)
3. Update `fact_monthly.sap_code` on ALL historical rows to new code (so history is continuous under active code)
4. Log the remap in `ingestion_log` with notes

**User confirmation required** before executing reassignment — pipeline should present the match and ask for approval.

### Rule C-4: Genuine new commissioning identification
After excluding data errors (C-2) and SAP reassignments (C-3), remaining unknown SAP codes are new commissionings. Confirmation signals:
- `YOC` field in file = current FY or recent past FY (2025-26, 2026-27)
- `DOC` field populated (IOCL files always have this; other OMCs often do not)
- Zero volumes in previous months, small volumes in first active month
- SAP code fits OMC numbering convention (IOCL 3xx-xxx, HPCL 4xxx-xxx, NEL 5183xxxx, RBML 5193xxxx)

This session new commissionings:
| OMC | Count | YOC | DOC available |
|---|---|---|---|
| IOCL | 7 | 2026-27 | Yes (all May 2026) |
| HPCL | 2 | 2026-27 | No |
| NEL | 2 | 2025-26 | No |
| RBML | 3 | 2025-26 | No |

**Pipeline rule:** Flag all confirmed new commissionings for user review before inserting into dim_ro. Show all available attributes. User confirms or corrects before commit.

---

## 3. dim_ro Data Completeness for New Commissionings

### Fields available from the sales file:
sap_code ✓ · ro_name ✓ · omc ✓ · district ✓ · rsa_name ✓ · ta_name (free text) ✓ · com ✓ · highway_no ✓ · yoc ✓ · doc (IOCL only) ✓

### Fields requiring resolution:
- **rsa_code**: Must be looked up from `dim_ro` by rsa_name match. All 14 new ROs resolved cleanly this session.
- **ta_code**: Must be fuzzy-matched from `dim_ta.ta_name_canonical` using the free-text TA name in the file. All 14 resolved this session (exact or near-exact string match).

### Fields absent from sales file (set to NULL for new commissionings):
- `ab_site` (AB site flag) — not in file
- `category` — present in file but empty for most new entries; set NULL
- `data_complete_flag` — set `'Yes'` if rsa_code and ta_code resolved; `'No'` if any gap

### Notable gap: non-IOCL DOC
HPCL, NEL, RBML do not include a Date of Commissioning in their monthly files. YOC (financial year) is the only commissioning date available for these OMCs. This limits the NIL/YTS rule application (Rule #138: YTS = commissioned ≤ 12 months ago) for non-IOCL outlets.

**Recommendation for pipeline:** Accept YOC as proxy for DOC when DOC is absent. Treat DOC = April 1 of the YOC financial year as a conservative approximation.

---

## 4. TA Code Resolution — Conflicts and Edge Cases

### Case 1: RSA conflict (observed: SAP 393128)
**Situation:** TA name in file ("Karad on NH48 RHS") matched two dim_ta entries:
- M45-026 ("Karad On NH 48 RHS") in Satara East RSA (M45)
- M69-018 ("Karad On NH 48 RHS") in Satara West RSA (M69)

The file's RSA column said "Satara West RSA" (M69). Correct assignment: M69-018.

**Resolution:** When a TA name matches multiple ta_codes in dim_ta, use the RSA name from the file as the tiebreaker. RSA name in the file takes precedence over TA string match.

**Pipeline rule:** After TA name match, validate that the matched ta_code's rsa_code agrees with the file's rsa_name lookup. If conflict, present both options to user; default to file's RSA.

### Case 2: TA name not in dim_ta
Not encountered this session (all 14 resolved), but the protocol when this occurs:
- If district + RSA combination is valid, flag to user
- User decides: assign to nearest existing TA, or create new TA entry
- New TA creation requires: ta_code (next sequential for that RSA), ta_name_canonical, rsa_code, rsa_name, district. All OMC outlet counts = 0 initially.

---

## 5. dim_ta Count Update Rules

When new ROs are added, `dim_ta` outlet counts must be incremented for the relevant TA.

**This session:** All 14 new ROs incremented both `cnt_{omc}_ms` and `cnt_{omc}_hsd` and both `total_ros_ms` and `total_ros_hsd` in their respective TAs.

**Open question for pipeline rebuild:** Should a new RO be counted for MS, HSD, or both? Options:
- **Conservative:** Count only for products where it has > 0 volume in its first month
- **Standard (used this session):** Count for both MS and HSD (all outlets are expected to sell both)

Recommendation: use Standard initially; add a data quality check post-ingest that flags if an outlet has 0 cumulative volume for a product after 3 months.

---

## 6. Active ROs Absent from File — Treatment

7 dim_ro entries were absent from the Apr-May26.xlsx file:
- 2 confirmed SAP reassignments (old codes, replaced by new → handled under Rule C-3)
- 2 data entry errors in file (single-digit SAP codes → skip)
- 1 always-zero entry (SAP "0" in DB — bad data entry in DB, not a real RO)
- **2 active ROs with significant FY25-26 sales absent from file without explanation:**
  - `41040833` ADHOC Shree Gurudutt PETROLEUM (HPCL Satara, 882 KL in FY25-26)
  - `41067506` Shivlal Premchand (HPCL Pune, 605 KL in FY25-26)

**Treatment this session:** Treated as NIL-selling for Apr+May 2026 (no rows inserted). This is the correct pipeline behaviour — absence from file = no volume that month.

**Pipeline rule:** When an active RO (non-zero sales in last 3 months) is absent from an OMC file, log a warning in `ingestion_log.notes`. Do not block ingestion. The RO will appear in the Nil Selling tab if absence persists for 3 consecutive months.

---

## 7. Volume Ingestion — Month/FY Derivation

**This file:** Explicit date columns in row 1 (datetime objects: 2026-05-01, 2026-04-01).

**FY derivation rule:**
- Month April (month=4) → FY start year = same calendar year → FY "2026-27"
- Month index within FY: April = 1, May = 2, … March = 12

**General rule for pipeline:** FY = `{year}-{year+1 2-digit}` where year = calendar year for Apr-Sep, calendar year - 1 for Oct-Mar.

---

## 8. Summary of DB Changes Made (Demo Session)

| Change type | Count | Details |
|---|---|---|
| SAP reassignments (COCO) | 2 | 379479→392208, 378277→392222; legacy codes set; 168 fact_monthly rows each remapped |
| New ROs added to dim_ro | 14 | IOCL×7, HPCL×2, NEL×2, RBML×3 |
| dim_ta counts updated | 14 TAs | +1 per product per OMC for each new RO's TA |
| fact_monthly rows inserted | 8,640 | 2,160 ROs × 2 months × 2 products |
| FY2025-26 guard (MS share) | Unchanged | 23.8196% ✓ |
| FY2025-26 guard (HSD share) | Unchanged | 26.3108% ✓ |

---

## 9. Recommendations for WIP Pipeline Rebuild

1. **Add legacy_sap_codes lookup to the unknown-SAP check.** Before flagging a SAP code as unknown, check if it appears in any `dim_ro.legacy_sap_codes` entry. If found, auto-resolve as a known legacy alias.

2. **Build a name-similarity match for SAP reassignments.** When a new SAP has no dim_ro match, run a fuzzy name match (e.g. token sort ratio > 80) against dim_ro.ro_name. Present the top match to the user for confirmation. This handles COCO and dealer-change cases cleanly.

3. **TA resolution must check RSA as tiebreaker.** Pure TA name matching is ambiguous when the same TA name exists in multiple RSAs (e.g. "Karad On NH 48 RHS" in both M45 and M69). Always validate ta_code against rsa_name from the file.

4. **DOC default for non-IOCL new commissionings.** Use April 1 of the YOC FY as a conservative DOC proxy. Store as `doc_source='yoc_proxy'` field or note in `ingestion_log`.

5. **Single-digit SAP code rejection.** Any SAP code < 5 digits should be immediately rejected at parse time with a name-based suggestion.

6. **dim_ta counts must be rebuilt (not just incremented) after any commissioning batch.** Incremental updates work but accumulate errors if any ingest is rolled back or re-run. A `rebuild_ta_counts()` function (re-derives counts from dim_ro) run after each ingestion session is safer than incremental +1.

7. **Absence-from-file logging.** Active ROs (sales in last 3 months) absent from an OMC's monthly file should be logged as warnings, not errors. They are NIL that month.

---

*End of commissioning observation document. Use this for the WIP ingestion pipeline rebuild.*

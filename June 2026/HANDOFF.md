# PDO Dashboard — Session Handoff Document
**Date:** 1 July 2026  
**Model at time of writing:** Claude Sonnet 4.6 (claude-sonnet-4-6)  
**Next model:** Claude Sonnet 5 (or later)  
**Project:** Pune Divisional Office Market Share Dashboard  
**Repo:** `D:\Github\PDO-Dashboard-Demo` (GitHub: PDO-Dashboard-Demo)  
**Dev environment:** `D:\PDO DB Project\Development\`  
**June 2026 working folder:** `D:\Claude Cowork\Github Copy 1 July\`

---

## 1. What Was Done This Session

### June 2026 Data Ingestion (Manual — 3 OMCs)
All three OMC files for June 2026 were processed manually using Python scripts
(the automated pipeline was not used; see Section 5 for why and what needs fixing).

| OMC | File | Rows Inserted | Notes |
|-----|------|--------------|-------|
| BPCL | `BPCL June 26.xlsx` | 1,087 fact_monthly rows | 4 new commissioning ROs added to dim_ro |
| HPCL | `HPCL June 2026.xlsx` | 1,162 fact_monthly rows | 3 new ROs added; several adhoc/legacy remaps |
| IOCL | `IOCL figure.xlsx` (Industry Sharing sheet) | 1,203 fact_monthly rows | 1 legacy remap (Kokamthan 377124→393411) |

### dim_ro Changes Made This Session
**4 new BPCL commissioning ROs** inserted (yoc='2026-27'):
- `265362` Katke Petroleum — Pune, RSA Pune City, TA M06-078 Jambulwadi (NEW TA created)
- `265220` Khandve Petroleum — Pune, RSA Pune City, TA M06-036 Lohegaon Wagholi Road
- `267354` Jyoti Kranti Petroleum — Ahmednagar (RSA/TA TBD)
- `267390` Sujit Petroleum — Ahmednagar (RSA/TA TBD)

**Legacy code remappings applied this session** (old_code → canonical sap_code):
- BPCL: `196739`→`196740`, `140947`→`194626`, `100129`→`221676`, `100115`→`183993`
- HPCL: `41096501`→`41071411` (Shree Gurudutt adhoc)
- IOCL: `377124`→`393411` (COCO Kokamthan — sap_code updated, historical fact_monthly migrated)

### GitHub State After This Session
- **Branch `ingestion-COCO-Swagat`**: contains the BPCL+HPCL June data commit (`4b924d3 Update pune_do.db`)
- **Branch `main`**: was merged with BPCL+HPCL data; IOCL was then added and committed separately
- **Live Streamlit app deploys from `main`**
- **IOCL data committed on `main`** — push to origin to make it live

### Known Data Issues (Unresolved)
1. **Decimal volumes** in BPCL/HPCL June data — formula artifacts from source Excel:
   - 5 BPCL outlets (BP-branded COCOs): volumes like 376.874, 237.604 etc.
   - 4 HPCL outlets (MSHSD HP Auto Care Centres): volumes like 262.83486 etc.
   - **Fix needed:** `ROUND(volume_kl)` for these rows, or ask OMC to provide corrected figures
   - **Impact:** Dashboard shows e.g. BPCL CY=18,371.9 instead of a whole number

2. **Pending OMCs for June 2026** — NEL, RBML, SIMPL not yet ingested

3. **April re-ingestion needed** — Ahmednagar files (BPCL Q002 Nagar + HPCL Nagar) were missing
   from the Development DB comparison. Both districts need re-ingestion in Dev environment.

### Bug Found and Fixed (ta_code missing for IOCL)
During IOCL insert, `ta_code` and `rsa_code` were not populated → IOCL volumes
showed 0 in all TA-level dashboard views. Fixed by running:
```sql
UPDATE fact_monthly
SET ta_code  = (SELECT ta_code  FROM dim_ro WHERE dim_ro.sap_code = fact_monthly.sap_code),
    rsa_code = (SELECT rsa_code FROM dim_ro WHERE dim_ro.sap_code = fact_monthly.sap_code)
WHERE omc='IOCL' AND fy_code='2026-27' AND month_index=3 AND ta_code IS NULL;
```
**This bug also exists in the automated pipeline's `commit_to_db()` function — it must be fixed there.**

---

## 2. Current DB State (pune_do.db — as of this handoff)

**Path:** `D:\Github\PDO-Dashboard-Demo\app\pune_do.db`

### June 2026 District Totals (fy_code='2026-27', month_index=3)

| OMC | District | MS (KL) | HSD (KL) |
|-----|----------|---------|---------|
| BPCL | Ahmednagar | 8,208.0 | 19,004.0 |
| BPCL | Pune | 30,374.7* | 43,539.6* |
| BPCL | Satara | 5,476.5 | 9,297.5 |
| HPCL | Ahmednagar | 7,021.5 | 15,275.5 |
| HPCL | Pune | 37,472.7* | 63,728.1* |
| HPCL | Satara | 4,705.0 | 9,316.0 |
| IOCL | Ahmednagar | 6,296.5 | 14,173.5 |
| IOCL | Pune | 22,266.5 | 42,714.5 |
| IOCL | Satara | 5,882.5 | 10,153.5 |

*Asterisked values contain decimal artifacts from Excel formula-derived COCO volumes. Pending rounding fix.

---

## 3. Ingestion Pipeline Redesign Plan

### 3a. The Big Idea: COVERAGE_DISTRICTS as Central Config

**Current problem:** The pipeline and app have the district list hard-coded in multiple places.  
**Solution:** One single config entry drives everything.

```python
# config.py  (create this at D:\PDO DB Project\Development\config.py)
# Also duplicate at D:\Github\PDO-Dashboard-Demo\app\config.py

COVERAGE_DISTRICTS = {"Pune", "Satara", "Ahmednagar"}

# To add a new DO (e.g., Nashik DO):
# COVERAGE_DISTRICTS = {"Pune", "Satara", "Ahmednagar", "Nashik", "Dhule"}
# That's the only change needed for the pipeline to work for a different/expanded office.
```

**Where this config must be imported:**
- `ingest/parsers.py` — for district column detection and row filtering
- `ingest/pipeline.py` — replaces the `COVERAGE = {"Pune", "Satara", "Ahmednagar"}` constant
- `app/core.py` — for dashboard filter dropdowns (district list)
- `app/context.py` — for any district-based data loading
- Any tab that currently has district names hard-coded in filter lists

**Effect:** Change one line in `config.py` → entire app (ingestion + dashboard) works for a different Divisional Office.

---

### 3b. Updated 12-Step Algorithm (v2 Flowchart)

The flowchart SVG was created in the session and shows:

```
START → Detect OMC → Detect Format
  → ★ AUTO-DETECT DISTRICT COLUMN (NEW)
  → Extract & Normalize rows
  → Filter to COVERAGE_DISTRICTS
  → ★ SPLIT: Mother (MS/HSD) vs Branded (Speed+/Power/XP95/XG/Turbojet)
       ↓ Mother track              → Branded track (parallel)
  → Build dim_ro lookup
  → Match SAP codes (canonical → legacy → unmatched)
       → Unmatched: Volume=0? skip : Investigate (new RO / legacy remap)
  → ★ CROSS-VALIDATE TOTALS (hard gate — stop if mismatch)
  → INSERT fact_monthly (with ta_code+rsa_code from dim_ro JOIN)
     INSERT fact_branded_monthly (branded track)
  → Integrity check → Binary write → Commit → Push
  → More OMCs? loop : END
```

---

### 3c. Exact Code Changes Required

#### FILE 1: `D:\PDO DB Project\Development\ingest\parsers.py`

**Add this function** (call it before any column-index assumptions):

```python
import re

# All Maharashtra districts — used for auto-detection only
_MH_DISTRICTS = {
    "Pune", "Satara", "Ahmednagar", "Nashik", "Kolhapur", "Solapur",
    "Aurangabad", "Chhatrapati Sambhajinagar", "Nagpur", "Thane",
    "Mumbai", "Raigad", "Ratnagiri", "Sindhudurg", "Dhule", "Jalgaon",
    "Nanded", "Latur", "Osmanabad", "Dharashiv", "Parbhani", "Hingoli",
    "Buldhana", "Akola", "Amravati", "Wardha", "Yavatmal", "Washim",
    "Beed", "Jalna", "Nandurbar", "Gondia", "Bhandara", "Gadchiroli",
    "Chandrapur",
}

def detect_district_col(df: pd.DataFrame) -> str | None:
    """
    Scan all columns and return the name of the column most likely to
    contain district names (highest count of values matching _MH_DISTRICTS).
    Returns None if no column scores > 0.
    """
    best_col, best_score = None, 0
    for col in df.columns:
        score = (
            df[col]
            .astype(str)
            .str.strip()
            .str.title()
            .isin(_MH_DISTRICTS)
            .sum()
        )
        if score > best_score:
            best_score, best_col = score, col
    return best_col


def filter_to_coverage(df: pd.DataFrame, district_col: str,
                       coverage: set[str]) -> pd.DataFrame:
    """
    Keep only rows where district_col value is in coverage set.
    Normalises to Title Case before comparing.
    """
    mask = df[district_col].astype(str).str.strip().str.title().isin(coverage)
    return df[mask].copy()
```

**Then in every existing parser function**, replace the hard-coded district column assumption with:
```python
dist_col = detect_district_col(df)
if dist_col is None:
    raise ValueError("Cannot detect district column in file")
df = filter_to_coverage(df, dist_col, COVERAGE_DISTRICTS)
```

#### FILE 2: `D:\PDO DB Project\Development\ingest\pipeline.py`

**Change 1 — Import COVERAGE_DISTRICTS from config instead of defining it inline:**
```python
# Remove:
COVERAGE = {"Pune", "Satara", "Ahmednagar"}

# Add at top:
from ..config import COVERAGE_DISTRICTS as COVERAGE
```

**Change 2 — Fix `commit_to_db()` to populate ta_code and rsa_code:**

In `commit_to_db()`, after building `to_insert`, add a lookup join:
```python
# Load ta_code, rsa_code from dim_ro for this OMC
dim_lookup = pd.read_sql(
    "SELECT sap_code, ta_code, rsa_code FROM dim_ro", con
).set_index("sap_code")

# Map onto insert rows using canonical_sap
to_insert["ta_code"]  = to_insert["canonical_sap"].map(dim_lookup["ta_code"])
to_insert["rsa_code"] = to_insert["canonical_sap"].map(dim_lookup["rsa_code"])
```

Then update the INSERT statement to include ta_code, rsa_code:
```python
cur.execute("""
    INSERT OR REPLACE INTO fact_monthly
        (sap_code, ta_code, rsa_code, omc, district, fy_code,
         month_index, month_label, product, volume_kl, is_negative)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    r["canonical_sap"],
    r.get("ta_code"),
    r.get("rsa_code"),
    r["omc"], r["effective_district"],
    fy_code, month_index,
    r.get("month_label", ""),
    r["product"],
    round(float(r["volume_kl"])),   # ← also round here to kill decimal artifacts
    int(r.get("is_negative", 0)),
))
```

**Change 3 — Add `validate_totals()` function:**
```python
def validate_totals(
    matched: pd.DataFrame,
    original_df: pd.DataFrame,
    district_col: str,
) -> dict:
    """
    Compare Σ volume by district between matched rows (to-be-inserted)
    and the original parsed DataFrame (full file).

    Returns: {"ok": bool, "mismatches": list_of_dicts}
    Raises ValueError if mismatches found (hard gate).
    """
    from_matched = (
        matched[matched["effective_district"].isin(COVERAGE)]
        .groupby(["effective_district", "product"])["volume_kl"]
        .sum()
    )
    from_file = (
        original_df.copy()
    )
    from_file["_district"] = (
        from_file[district_col].astype(str).str.strip().str.title()
    )
    from_file = (
        from_file[from_file["_district"].isin(COVERAGE)]
        .groupby(["_district", "product"])["volume_kl"]
        .sum()
    )

    mismatches = []
    for key in from_file.index:
        expected = from_file.get(key, 0)
        actual   = from_matched.get(key, 0)
        if abs(expected - actual) > 0.5:   # tolerance: 0.5 KL
            mismatches.append({
                "district": key[0], "product": key[1],
                "file_total": expected, "db_total": actual,
                "diff": expected - actual,
            })

    if mismatches:
        raise ValueError(
            f"Total mismatch before DB write:\n" +
            "\n".join(str(m) for m in mismatches)
        )
    return {"ok": True, "mismatches": []}
```

#### FILE 3 (NEW): `D:\PDO DB Project\Development\config.py`

```python
"""
Central configuration for the PDO Dashboard.

To adapt this app for a different Divisional Office, update
COVERAGE_DISTRICTS below. All pipeline filters and dashboard
dropdowns will automatically reflect the change.
"""

# Districts covered by this Divisional Office
COVERAGE_DISTRICTS: set[str] = {"Pune", "Satara", "Ahmednagar"}

# Financial year convention
FY_START_MONTH = 4   # April = month_index 1

# Fiscal year label helper
def fy_label(year: int) -> str:
    """e.g. fy_label(2026) → '2026-27'"""
    return f"{year}-{str(year+1)[2:]}"
```

Also create a copy at `D:\Github\PDO-Dashboard-Demo\app\config.py`
and update all imports in the app accordingly.

---

## 4. Pending Tasks (Priority Order)

### Immediate (before next month's data)
1. **Fix decimal volumes** in BPCL/HPCL June data — round the 10 affected rows
   ```sql
   UPDATE fact_monthly SET volume_kl = ROUND(volume_kl)
   WHERE omc IN ('BPCL','HPCL') AND fy_code='2026-27' AND month_index=3
   AND (volume_kl * 2 != CAST(volume_kl*2 AS INT));
   ```
   Then commit + push.

2. **Ingest NEL, RBML, SIMPL June 2026** — files not yet received/placed

3. **April re-ingestion (Ahmednagar)** — in Dev environment only:
   - Re-run ingestion for BPCL with Ahmednagar file (Q002 Nagar)
   - Re-run ingestion for HPCL with Ahmednagar file

### Pipeline Redesign (next dev session)
4. Create `config.py` with `COVERAGE_DISTRICTS`
5. Add `detect_district_col()` + `filter_to_coverage()` to `parsers.py`
6. Fix `commit_to_db()` — add ta_code/rsa_code join + ROUND on volume
7. Add `validate_totals()` to `pipeline.py`
8. Smoke test on June BPCL / HPCL / IOCL files
9. Update app imports to use `config.COVERAGE_DISTRICTS`

### Later
10. Update TA details for 267354 (Jyoti Kranti Petroleum) and 267390 (Sujit Petroleum) — RSA/TA TBD
11. Verify 265362 Katke Petroleum — new TA M06-078 Jambulwadi added but no RSA hierarchy yet

---

## 5. Why Manual Ingestion Was Used (Not the Pipeline)

The automated pipeline (`ingest/pipeline.py`) parses standard OMC exchange formats
(SAP dump, Q002 style). The June 2026 files provided were custom summary formats:
- BPCL: 5-column (SAP | Name | District | MS | HSD)
- HPCL: 5-column (SAP | Name | District | MS | HSD)
- IOCL: Multi-sheet (Industry Sharing + MS SAP Dump + HSD SAP Dump)

These formats bypassed the parsers entirely and were read with `pd.read_excel()` directly.
Future option: add these as recognized formats in parsers.py.

---

## 6. Repository & Branch Reference

| Branch | Purpose | State |
|--------|---------|-------|
| `main` | Live app on Streamlit | Has BPCL+HPCL+IOCL June 2026 (after push) |
| `ingestion-COCO-Swagat` | Development branch | 1 commit ahead of where it started; has stashed working tree changes |

**Uncommitted working tree items on `ingestion-COCO-Swagat` (harmless):**
- `app/tab_16_ingest.py` — shows as modified but content is identical to HEAD (timestamp issue)
- `ingest/parsers.py` — same (content-restored via Python binary write)
- `ingest/omc_pipeline.py` — untracked orphan file, OLD architecture, not imported anywhere

---

## 7. File Locations Quick Reference

| What | Where |
|------|-------|
| Live DB (GitHub repo) | `D:\Github\PDO-Dashboard-Demo\app\pune_do.db` |
| Dev DB | `D:\PDO DB Project\Development\pune_do.db` (or similar) |
| June 2026 source files | `D:\Claude Cowork\Github Copy 1 July\June 2026\` |
| This handoff file | `D:\Claude Cowork\Github Copy 1 July\June 2026\HANDOFF.md` |
| Pipeline code | `D:\PDO DB Project\Development\ingest\pipeline.py` |
| Parser code | `D:\PDO DB Project\Development\ingest\parsers.py` |
| GitHub Copy (1 Jul) | `D:\Claude Cowork\Github Copy 1 July\` |

---

*End of handoff — pick up from Section 4, Task #1 (fix decimal volumes) or Task #4 (pipeline redesign).*

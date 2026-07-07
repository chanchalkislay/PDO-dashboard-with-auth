#!/usr/bin/env python3
"""
parsers.py — OMC exchange file parsers for the Pune DO ingestion pipeline.

Each parser reads a raw Excel file and returns a normalised DataFrame with columns:
    sap_code  (str)   — RO identifier matching dim_ro.sap_code
    ro_name   (str)   — RO name as in the file (for new-RO detection)
    omc       (str)   — 'IOCL' | 'BPCL' | 'HPCL' | 'NEL' | 'RBML' | 'SIMPL'
    product   (str)   — 'MS' | 'HSD'
    brand     (str)   — 'Mother' | 'XP95' | 'XP100' | 'XG' | 'Power' | None
    volume_kl (float) — invoiced KL for the month
    district  (str)   — district name extracted from file (best-effort)
    is_negative (int) — 1 if PRCN (negative volume clipped), 0 otherwise

Public API
----------
    detect_and_parse(filepath, omc_hint, month_index, fy_code) -> pd.DataFrame
    detect_format(filepath, omc_hint) -> str   # format label for logging

Supported formats
-----------------
    iocl_sap_dump       — Ship-To Party | Material | Inv.Qty | Unit  (3–6 cols)
    bpcl_q002_nagar     — District | CC | Name | HSD | MS | HSD_LY | MS_LY
    bpcl_q145_ps        — multi-level header: CC Code | Name | MS | HSD | …
    hpcl_nagar          — Sr | CC | SAP CODE | Name | … | MS Hist | MS Curr | HSD Hist | HSD Curr | Power…
    hpcl_ps             — Sr no | Customer Code New | District | … | MS CY | MS LY | HSD CY | HSD LY | Power CY
    pvt_ro_wise         — generic: sap_code | ro_name | district | MS | HSD  (user-compiled)
"""
from __future__ import annotations

import os
import re
import warnings
from typing import Optional

import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MATERIAL_MAP = {
    "16730": ("MS",  "Mother"),
    "17295": ("MS",  "XP95"),
    "17100": ("MS",  "XP100"),   # plain XP100 (MS-XP100-BSVI)
    "17101": ("MS",  "XP100"),   # XP100 for RS without blending
    "50700": ("HSD", "Mother"),
    "50800": ("HSD", "XG"),
}

# ---------------------------------------------------------------------------
# Operational coverage configuration
# ---------------------------------------------------------------------------
# Set of districts managed by this IOCL DO unit — sourced from repo-root
# config.py (single source of truth). Fallback keeps standalone use working.
# An empty set means "accept all districts" (useful for state-level dashboards).
try:
    from config import COVERAGE_DISTRICTS, MH_DISTRICTS
except ImportError:  # standalone use without repo root on sys.path
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from config import COVERAGE_DISTRICTS, MH_DISTRICTS
    except ImportError:
        COVERAGE_DISTRICTS: set[str] = {"Pune", "Ahmednagar", "Satara"}
        MH_DISTRICTS: set[str] = set(COVERAGE_DISTRICTS)

# Legacy alias kept for backward compatibility
PUNE_DO_DISTRICTS = COVERAGE_DISTRICTS

def detect_district_col(df: pd.DataFrame) -> Optional[str]:
    """Scan all columns; return the one most likely holding district names
    (highest count of values matching MH_DISTRICTS after normalisation).
    Returns None if no column scores > 0. Used by parsers for ad-hoc /
    unrecognised layouts before any column-index assumption is made."""
    best_col, best_score = None, 0
    for col in df.columns:
        try:
            score = int(
                df[col].astype(str).str.strip().str.title()
                .isin(MH_DISTRICTS).sum()
            )
        except Exception:
            continue
        if score > best_score:
            best_score, best_col = score, col
    return best_col


def filter_to_coverage(df: pd.DataFrame, district_col: str,
                       coverage: Optional[set] = None) -> pd.DataFrame:
    """Keep only rows whose district_col value resolves into `coverage`
    (default COVERAGE_DISTRICTS). Normalises via _resolve_district so SAP
    codes / typos / renames all match."""
    cov = coverage if coverage is not None else COVERAGE_DISTRICTS
    if not cov:
        return df.copy()
    resolved = df[district_col].astype(str).map(lambda v: _resolve_district(v)[0])
    return df[resolved.isin(cov)].copy()


def _in_coverage(district: str, confidence: str = "exact") -> bool:
    """
    Return True if this row should be kept at parse time.

    Rules:
    - "exact" match: keep only if district is in COVERAGE_DISTRICTS (or coverage unconstrained)
    - "fuzzy" match: always keep — the pipeline will confirm with the user before committing
    - "unknown" match: always discard — no reasonable district could be identified
    """
    if confidence == "unknown":
        return False
    if confidence == "fuzzy":
        return True          # pipeline handles user confirmation
    if not COVERAGE_DISTRICTS:
        return True
    return district in COVERAGE_DISTRICTS

# ---------------------------------------------------------------------------
# District name resolution — exact variants + fuzzy matching
# ---------------------------------------------------------------------------

# All known exact/prefix variants of each canonical district name.
# Keys are upper-cased; values are canonical names.
# Includes:
#   - SAP district codes (MH022 = Pune, MH001 = Ahmednagar, MH026 = Satara)
#   - Common alternate spellings (Ahmadnagar, Ahmed Nagar)
#   - Common typos (Punr, Stara, Satra)
#   - Official rename: Ahmednagar → Ahilyanagar (Govt of Maharashtra; not yet
#     reflected in OMC data as of 2026 but will appear eventually)
_DIST_NORM: dict[str, str] = {
    # ── Pune ───────────────────────────────────────────────────────────────
    "PUNE":          "Pune",
    "PUNR":          "Pune",   # common typo
    "PUEN":          "Pune",   # common typo
    "MH022":         "Pune",
    "MH022 PUNE":    "Pune",
    "MH022  PUNE":   "Pune",
    # ── Ahmednagar ─────────────────────────────────────────────────────────
    "AHMEDNAGAR":       "Ahmednagar",
    "AHMADNAGAR":       "Ahmednagar",  # alternate official spelling
    "AHMED NAGAR":      "Ahmednagar",  # spaced variant
    "AHMAD NAGAR":      "Ahmednagar",  # spaced variant
    "AHMEDNAAGR":       "Ahmednagar",  # typo
    "AHMEDNGR":         "Ahmednagar",  # abbreviation-style typo
    # Official rename (Govt of Maharashtra, effective 2023)
    "AHILYANAGAR":      "Ahmednagar",
    "AHILYA NAGAR":     "Ahmednagar",
    "AHILYABAI NAGAR":  "Ahmednagar",
    "AHILYABAINAGAR":   "Ahmednagar",
    # Common short form used in field / informal references
    "NAGAR":            "Ahmednagar",
    "MH001":                "Ahmednagar",
    "MH001 AHMADNAGAR":     "Ahmednagar",
    "MH001  AHMADNAGAR":    "Ahmednagar",
    "MH001 AHMEDNAGAR":     "Ahmednagar",
    "MH001  AHMEDNAGAR":    "Ahmednagar",
    # ── Satara ─────────────────────────────────────────────────────────────
    "SATARA":  "Satara",
    "STARA":   "Satara",   # missing 'a' typo
    "SATRA":   "Satara",   # missing 'a' typo
    "SATRAA":  "Satara",   # doubled-a typo
    "SATARAA": "Satara",   # doubled-a typo
    "MH026":         "Satara",
    "MH026 SATARA":  "Satara",
    "MH026  SATARA": "Satara",
}

# Canonical names to fuzzy-match against. Covers all possible COVERAGE_DISTRICTS values.
# Each tuple: (canonical_name, [known aliases for difflib scoring])
_FUZZY_TARGETS = [
    "Pune",
    "Ahmednagar",
    "Ahilyanagar",   # for files that use the new name — always maps to Ahmednagar
    "Satara",
]

# Distance below which we attempt fuzzy resolution (Levenshtein-like via difflib)
_FUZZY_CUTOFF = 0.72  # ~1-2 character edits on short names


def _resolve_district(raw: str) -> tuple[str, str]:
    """
    Resolve a raw district string to a canonical name.

    Returns
    -------
    (canonical_name, confidence)
        confidence = "exact"   — matched a known variant in _DIST_NORM
                   = "fuzzy"   — close-enough match; pipeline should confirm with user
                   = "unknown" — no reasonable match; caller should discard the row

    The canonical_name for "Ahilyanagar" matches is returned as "Ahmednagar" so
    that coverage checks and DB queries work without special-casing the rename.
    """
    import difflib as _dl

    cleaned = str(raw).strip()
    upper   = cleaned.upper()
    # Strip MH-code prefix for fuzzy matching (e.g. "MH022  Punr" → "Punr")
    name_part = re.sub(r"^MH\d{3}\s*", "", upper).strip()

    # 1. Exact / prefix match in _DIST_NORM
    for k, v in _DIST_NORM.items():
        if upper.startswith(k):
            return v, "exact"

    # 2. No-space exact match (handles "AhmedNagar", "AhilyaNagar", etc.)
    nospace = upper.replace(" ", "").replace("-", "").replace("_", "")
    for k, v in _DIST_NORM.items():
        if nospace == k.replace(" ", "").replace("-", "").replace("_", ""):
            return v, "exact"

    # 3. Fuzzy match on the name part (after stripping any MH code prefix)
    candidates = [name_part, nospace]
    for candidate in candidates:
        if not candidate:
            continue
        matches = _dl.get_close_matches(
            candidate.title(), _FUZZY_TARGETS, n=1, cutoff=_FUZZY_CUTOFF
        )
        if matches:
            matched = matches[0]
            # Ahilyanagar is the renamed Ahmednagar — normalise to Ahmednagar
            canon = "Ahmednagar" if matched == "Ahilyanagar" else matched
            return canon, "fuzzy"

    return cleaned.title(), "unknown"


def _norm_dist(raw: str) -> str:
    """Backward-compatible wrapper — returns canonical name only."""
    name, _ = _resolve_district(raw)
    return name

def _sap_from_party(val: str) -> Optional[str]:
    """Extract numeric SAP code from 'NNNNNN  RO NAME' or plain 'NNNNNN'."""
    m = re.match(r"^\s*(\d{5,10})", str(val).strip())
    return m.group(1) if m else None

def _name_from_party(val: str) -> str:
    """Extract RO name from 'NNNNNN  RO NAME'."""
    s = str(val).strip()
    m = re.match(r"^\d+\s+(.*)", s)
    return m.group(1).strip() if m else s

def _mat_code(val: str) -> Optional[str]:
    """Extract material code from '16730  MS-BSVI-E20' or plain '16730'."""
    m = re.match(r"^\s*(\d{5,6})", str(val).strip())
    return m.group(1) if m else None

def _read_excel(filepath: str, **kwargs) -> pd.DataFrame:
    """Read .xls or .xlsx transparently."""
    ext = os.path.splitext(filepath)[1].lower()
    engine = "xlrd" if ext == ".xls" else "openpyxl"
    return pd.read_excel(filepath, engine=engine, **kwargs)

def _read_all_sheets(filepath: str, **kwargs) -> dict[str, pd.DataFrame]:
    ext = os.path.splitext(filepath)[1].lower()
    engine = "xlrd" if ext == ".xls" else "openpyxl"
    try:
        xl = pd.ExcelFile(filepath, engine=engine)
        return {sh: xl.parse(sh, **kwargs) for sh in xl.sheet_names}
    except Exception as e:
        # .xls files saved as "Single File Web Page" (MIME HTML) cannot be read
        # by xlrd. Fall back to parsing the embedded HTML table.
        if ext == ".xls" and "BOF" in str(e):
            return _read_mime_html_xls(filepath, **kwargs)
        raise

def _read_mime_html_xls(filepath: str, **kwargs) -> dict[str, pd.DataFrame]:
    """
    Read an Excel 97-2003 Web Archive (.xls saved as MIME HTML) via lxml.
    Returns a dict with a single key 'Sheet1' containing the parsed table.
    """
    import quopri, io as _io
    with open(filepath, "rb") as f:
        raw = f.read()
    decoded = quopri.decodestring(raw).decode("utf-8", errors="replace")
    # Split by MIME boundary; find the largest HTML part
    import re as _re
    boundary_pat = _re.search(r'boundary="([^"]+)"', decoded)
    if boundary_pat:
        parts = decoded.split(boundary_pat.group(1))
    else:
        parts = [decoded]
    html_parts = [p for p in parts if "<table" in p.lower()]
    if not html_parts:
        return {}
    kwargs.pop("nrows", None)
    best = None
    for html_part in html_parts:
        html_start = html_part.lower().find("<html")
        if html_start < 0:
            html_start = html_part.lower().find("<table")
        html_content = html_part[html_start:]
        try:
            dfs = pd.read_html(_io.StringIO(html_content), flavor="lxml", header=None)
        except Exception:
            continue
        for d in dfs:
            if best is None or d.size > best.size:
                best = d
    if best is not None:
        return {"Sheet1": best.reset_index(drop=True)}
    return {}

# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format(filepath: str, omc_hint: str) -> str:
    """
    Return one of: iocl_sap_dump | bpcl_q002_nagar | bpcl_q145_ps |
                   hpcl_nagar | hpcl_ps | pvt_ro_wise | unknown
    """
    omc = omc_hint.upper() if omc_hint else ""
    try:
        sheets = _read_all_sheets(filepath, header=None, nrows=6)
    except Exception:
        return "unknown"

    for sh_name, df in sheets.items():
        if df.empty:
            continue
        rows = df.fillna("").astype(str).values.tolist()
        flat = " ".join(" ".join(r) for r in rows).upper()

        if omc == "IOCL":
            # SAP dump: has both "SHIP-TO PARTY" and "MATERIAL" or material codes
            if "SHIP-TO PARTY" in flat or ("MS-BSVI" in flat or "HSD-BSVI" in flat):
                return "iocl_sap_dump"
            # Split-header variant: "SHIP-TO PAR" in first cell
            if any("SHIP-TO PAR" in str(r[0]).upper() for r in rows[:2]):
                return "iocl_sap_dump"
            # No-header variant: first cell is a bare SAP code (5-10 digits)
            if re.match(r"^\d{5,10}$", str(rows[0][0]).strip()):
                return "iocl_sap_dump"

        elif omc == "BPCL":
            if "Q145" in sh_name.upper() or "SOLD-TO PARTY" in flat or "CC CODE" in flat:
                return "bpcl_q145_ps"
            # Q145 BI export saved as Web Archive (.xls MIME HTML) or any
            # variant carrying the BI "Bl:Volume"/Division header signature
            if "BL:VOLUME" in flat.replace(" ", "") or \
               ("DIVISION" in flat and "1,000 L" in flat):
                return "bpcl_q145_ps"
            if "Q002" in sh_name.upper():
                return "bpcl_q002_nagar"
            # Custom named sheet (e.g. "BPC Jul-25") with District col
            if any(any(d in r for d in ["AHMEDNAGAR", "AHMADNAGAR"]) for r in rows):
                return "bpcl_q002_nagar"
            # May also be q145 if CC Code present
            if any("CC" in str(r[0]).upper() for r in rows[:5]):
                return "bpcl_q145_ps"

        elif omc == "HPCL":
            if "SALES DATA" in sh_name.upper():
                return "hpcl_nagar"
            if "CUSTOMER CODE" in flat:
                return "hpcl_ps"
            if df.shape[1] >= 14:
                return "hpcl_nagar"
            return "hpcl_ps"

        else:
            # Check for standardised PVT sales format (company|ro_code|yyyymm|ms_sales|hsd_sales)
            if "COMPANY" in flat and "RO_CODE" in flat and "YYYYMM" in flat:
                return "pvt_sales_format"
            return "pvt_ro_wise"

    # Top-level check: standardised PVT sales format can come with any omc_hint
    # (file contains all 3 PVT OMCs). Check first sheet regardless of omc_hint.
    first_df = next(iter(sheets.values()), pd.DataFrame())
    if not first_df.empty:
        row0 = " ".join(str(v).upper() for v in first_df.iloc[0] if not pd.isna(v))
        if "COMPANY" in row0 and "RO_CODE" in row0 and "YYYYMM" in row0:
            return "pvt_sales_format"

    return "unknown"

# ---------------------------------------------------------------------------
# Helpers — build normalised output row
# ---------------------------------------------------------------------------

def _row(sap, name, omc, product, brand, vol, district, is_neg=0,
         district_raw="", district_confidence="exact"):
    return {
        "sap_code":            str(sap).strip(),
        "ro_name":             str(name).strip(),
        "omc":                 omc,
        "product":             product,
        "brand":               brand,
        "volume_kl":           float(vol),
        "district":            district,
        "district_raw":        district_raw or district,  # original string from file
        "district_confidence": district_confidence,       # "exact" | "fuzzy"
        "is_negative":         is_neg,
    }

# ---------------------------------------------------------------------------
# IOCL SAP Dump parser
# ---------------------------------------------------------------------------

def _parse_iocl_sap_dump(filepath: str, product_hint: str = None) -> pd.DataFrame:
    """
    Handles all 3 SAP dump variants (basic, district+RSA, datewise) and the
    split-header Nov variant where Ship-To Party spans two columns.
    Returns normalised rows for fact_monthly AND fact_branded_monthly.
    """
    sheets = _read_all_sheets(filepath, header=None)
    # Use first non-empty sheet
    df_raw = next((s for s in sheets.values() if not s.empty), None)
    if df_raw is None:
        return pd.DataFrame()

    # Find header row (contains "Ship-To" or first cell looks like a SAP code)
    header_row = 0
    for i, row in df_raw.iterrows():
        vals = [str(v).strip() for v in row if str(v).strip() not in ("", "nan")]
        if vals and ("Ship-To" in vals[0] or "SHIP-TO" in vals[0].upper()):
            header_row = i
            break
        if vals and re.match(r"^\d{5,10}", vals[0]):
            # Data starts here directly (no header)
            header_row = -1
            break

    if header_row >= 0:
        df = df_raw.iloc[header_row + 1:].reset_index(drop=True)
        header = [str(v).strip() for v in df_raw.iloc[header_row]]
    else:
        df = df_raw.reset_index(drop=True)
        header = []

    df = df.dropna(how="all").reset_index(drop=True)

    # Detect column positions by inspecting first data row
    sample = [str(v).strip() for v in df.iloc[0]]

    # Determine if SAP+name are split (split-header variant: col0=SAP, col1=name)
    # vs combined (col0='125725  NATIONAL PETROLEUM')
    sap_col, name_col, mat_col, vol_col, dist_col = 0, None, None, None, None

    col0 = sample[0]
    if re.match(r"^\d{5,10}$", col0):
        # Split: col0=SAP, col1=name
        name_col = 1
        # Find material column (has digit+space+text or known mat codes)
        for i, v in enumerate(sample[2:], 2):
            if re.match(r"^\d{5,6}\s+", v) or v in MATERIAL_MAP:
                mat_col = i
                break
        # Volume = numeric column after mat
        if mat_col is not None:
            for i in range(mat_col + 1, len(sample)):
                try:
                    float(sample[i])
                    vol_col = i
                    break
                except (ValueError, TypeError):
                    pass
        # Fallback: no material column (single-product split-header file)
        # Find first numeric column after col 1
        if mat_col is None:
            for i in range(2, len(sample)):
                try:
                    float(sample[i])
                    vol_col = i
                    break
                except (ValueError, TypeError):
                    pass
        # District column
        for i, h in enumerate(header):
            if "district" in h.lower() or "sales district" in h.lower():
                dist_col = i
                break
    else:
        # Combined: col0='SAP NAME'
        # Find material column
        for i, v in enumerate(sample[1:], 1):
            if re.match(r"^\d{5,6}\s+", v):
                mat_col = i
                break
        if mat_col is None:
            # Might be header variant: locate by column header
            for i, h in enumerate(header):
                if "material" in h.lower():
                    mat_col = i
                    break
        if mat_col is not None:
            for i in range(mat_col + 1, len(sample)):
                try:
                    float(sample[i])
                    vol_col = i
                    break
                except (ValueError, TypeError):
                    pass
        else:
            # Simple MS/HSD-only file: 5 cols, vol at position 3 or 4
            vol_col = 3 if len(sample) <= 5 else 4

        for i, h in enumerate(header):
            if "district" in h.lower() or "sales district" in h.lower():
                dist_col = i
                break

    rows = []
    for _, r in df.iterrows():
        vals = [str(v).strip() if not pd.isna(v) else "" for v in r]
        if not vals or not vals[0]:
            continue

        sap = _sap_from_party(vals[sap_col]) if name_col is None else vals[sap_col]
        if not sap or not re.match(r"^\d{5,10}$", sap.strip()):
            continue

        ro_name = (_name_from_party(vals[sap_col]) if name_col is None
                   else vals[name_col])

        # Material
        if mat_col is not None and mat_col < len(vals):
            mc = _mat_code(vals[mat_col])
        else:
            mc = None

        if vol_col is None or vol_col >= len(vals):
            continue
        try:
            vol = float(vals[vol_col])
        except (ValueError, TypeError):
            continue

        # District
        dist, dist_conf = "", "exact"
        if dist_col is not None and dist_col < len(vals):
            dist_raw_val = vals[dist_col]
            dist, dist_conf = _resolve_district(dist_raw_val)
        else:
            dist_raw_val = ""

        # Map material → product + brand
        if mc and mc in MATERIAL_MAP:
            product, brand = MATERIAL_MAP[mc]
        elif mc is None:
            # No material column — single-product file; infer from filename hint
            product = product_hint if product_hint in ("MS", "HSD") else "MS"
            brand = "Mother"
        else:
            continue  # unknown material code, skip

        is_neg = 1 if vol < 0 else 0
        rows.append(_row(sap, ro_name, "IOCL", product, brand, abs(vol), dist, is_neg,
                         district_raw=dist_raw_val, district_confidence=dist_conf))

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["sap_code","ro_name","omc","product","brand","volume_kl","district","is_negative"])

# ---------------------------------------------------------------------------
# BPCL parsers
# ---------------------------------------------------------------------------

def _find_data_start_bpcl(df_raw: pd.DataFrame) -> tuple[int, dict]:
    """
    Scan rows until we hit a row where col[1] is a numeric CC code.
    Returns (first_data_row_index, col_positions_dict).
    """
    for i, row in df_raw.iterrows():
        vals = list(row)
        # CC code is typically in col 1 or col 0
        for cc_col in [1, 0]:
            v = str(vals[cc_col]).replace(".0","").strip()
            if re.match(r"^\d{5,7}$", v):
                return i, {"cc_col": cc_col}
    return -1, {}

def _parse_bpcl_q002_nagar(filepath: str) -> pd.DataFrame:
    """
    Ahmednagar BPCL formats:
      a) Q002 classic:  District-section rows | CC | Name | HSD_CY | MS_CY | HSD_LY | MS_LY
      b) Simple month:  CC NO | RO NAME | DISTRICT | MS | HSD   (e.g. June'26)
    Column order is resolved from header labels (\bMS\b / \bHSD\b); falls back
    to the classic HSD-first assumption. District comes from a per-row district
    column when one exists, else from section-header rows.
    Branded daughters (Speed / Hi Speed Diesel / Speed Diesel) are auto-detected
    per the locked mother/daughter rule and emitted as separate brand rows.
    """
    sheets = _read_all_sheets(filepath, header=None)
    df_raw = next(s for s in sheets.values() if not s.empty)
    df_raw = df_raw.reset_index(drop=True)

    start_row, col_info = _find_data_start_bpcl(df_raw)
    if start_row < 0:
        return pd.DataFrame()
    cc_col0 = col_info.get("cc_col", 0)

    # ── header-driven column identification ────────────────────────────────
    header_rows = df_raw.iloc[:start_row].fillna("").astype(str).values
    col_labels = [" ".join(str(header_rows[r][c]) for r in range(len(header_rows))
                            ).upper().strip()
                  for c in range(df_raw.shape[1])]

    def _first_col(pattern, exclude=None, min_col=0):
        for i, lbl in enumerate(col_labels):
            if i < min_col:
                continue
            if re.search(pattern, lbl) and not (exclude and re.search(exclude, lbl)):
                return i
        return None

    dist_col  = _first_col(r"\bDISTRICT\b|\bDIST\b")
    ms_col    = _first_col(r"\bMS\b|\bPETROL\b", exclude=r"\bLY\b|LAST", min_col=cc_col0 + 1)
    hsd_col   = _first_col(r"\bHSD\b|\bDIESEL\b", exclude=r"\bLY\b|LAST|SPEED", min_col=cc_col0 + 1)
    # Branded daughters (officer rule 2026-07-04): detect when present
    speed_col = _first_col(r"\bSPEED\b", exclude=r"HI\s*SPEED|SPEED\s*DIESEL|\bHSD\b")
    hsdie_col = _first_col(r"HI\s*SPEED\s*DIESEL|SPEED\s*DIESEL")

    header_resolved = ms_col is not None and hsd_col is not None

    def _flt(v):
        try:
            x = float(str(v).replace(",", ""))
            return x if x == x else 0.0    # NaN guard
        except (ValueError, TypeError):
            return 0.0

    rows = []
    current_dist, current_dist_conf, current_dist_raw = "", "exact", ""
    for i in range(start_row, len(df_raw)):
        r = list(df_raw.iloc[i])
        vals = [str(v).replace(".0", "").strip() if not pd.isna(v) else "" for v in r]

        # District section-header row (classic Q002 layout)
        if vals[0] and not re.match(r"^\d", vals[0]) and not vals[1]:
            current_dist, current_dist_conf = _resolve_district(vals[0])
            current_dist_raw = vals[0]
            continue
        if vals[0] in ("nan", "") and not vals[1]:
            continue

        cc_col = cc_col0
        if not re.match(r"^\d{5,7}$", vals[cc_col]):
            alt = 1 if cc_col == 0 else 0
            if re.match(r"^\d{5,7}$", vals[alt]):
                cc_col = alt
            else:
                continue
        cc = vals[cc_col]
        name = vals[cc_col + 1] if cc_col + 1 < len(vals) else ""

        if header_resolved:
            ms_cy  = _flt(r[ms_col])  if ms_col  < len(r) else 0.0
            hsd_cy = _flt(r[hsd_col]) if hsd_col < len(r) else 0.0
        else:
            # legacy fallback: first two numerics after name = HSD, MS
            vol_positions = []
            for j in range(cc_col + 2, min(cc_col + 6, len(r))):
                try:
                    float(str(r[j]).replace(",", ""))
                    vol_positions.append(j)
                    if len(vol_positions) == 2:
                        break
                except (ValueError, TypeError):
                    pass
            if len(vol_positions) < 2:
                continue
            hsd_cy = _flt(r[vol_positions[0]])
            ms_cy  = _flt(r[vol_positions[1]])

        # District: per-row column beats section header
        if dist_col is not None and dist_col < len(vals) and vals[dist_col]:
            dist, dist_conf = _resolve_district(vals[dist_col])
            dist_raw = vals[dist_col]
        elif vals[0] and not re.match(r"^\d", vals[0]) and vals[0] != cc:
            dist, dist_conf = _resolve_district(vals[0])
            dist_raw = vals[0]
        else:
            dist, dist_conf, dist_raw = current_dist, current_dist_conf, current_dist_raw
        if not _in_coverage(dist, dist_conf):
            continue

        if ms_cy:
            rows.append(_row(cc, name, "BPCL", "MS", "Mother", ms_cy, dist,
                             district_raw=dist_raw, district_confidence=dist_conf))
        if hsd_cy:
            rows.append(_row(cc, name, "BPCL", "HSD", "Mother", hsd_cy, dist,
                             district_raw=dist_raw, district_confidence=dist_conf))
        # daughters (volumes are PART of the mother figures above)
        if speed_col is not None and speed_col < len(r):
            sv = _flt(r[speed_col])
            if sv:
                rows.append(_row(cc, name, "BPCL", "MS", "Speed", sv, dist,
                                 district_raw=dist_raw, district_confidence=dist_conf))
        if hsdie_col is not None and hsdie_col < len(r):
            hv = _flt(r[hsdie_col])
            if hv:
                rows.append(_row(cc, name, "BPCL", "HSD", "Hi Speed Diesel", hv, dist,
                                 district_raw=dist_raw, district_confidence=dist_conf))

    return pd.DataFrame(rows) if rows else pd.DataFrame()

def _parse_bpcl_q145_ps(filepath: str) -> pd.DataFrame:
    """
    Pune+Satara BPCL format (Q145 sheet name pattern).
    Multi-level header (4 rows). Data: CC Code | Name | MS | HSD | total | MS_LY | HSD_LY | total_LY
    Volumes in KL (despite '* 1,000 L' label — confirmed by reconciliation).
    Some variants have Division cols (10=MS, 11=HSD) or Speed as separate col.
    """
    sheets = _read_all_sheets(filepath, header=None)
    df_raw = next(s for s in sheets.values() if not s.empty)
    df_raw = df_raw.reset_index(drop=True)

    start_row, col_info = _find_data_start_bpcl(df_raw)
    if start_row < 0:
        return pd.DataFrame()

    cc_col0 = col_info.get("cc_col", 0)   # col index of CC code in data rows
    name_off = 1                            # name is cc_col + name_off

    def _flt(v):
        try: return float(str(v).replace(",",""))
        except: return 0.0

    # Inspect header rows to find MS and HSD column positions
    header_rows = df_raw.iloc[:start_row].fillna("").astype(str).values
    # Flatten into one string per column
    col_labels = [" ".join(str(header_rows[r][c]) for r in range(len(header_rows))
                            ).upper().strip()
                  for c in range(df_raw.shape[1])]

    # Identify MS / HSD mother columns and branded daughter columns from header.
    # First matching column wins (the current-period block precedes LY blocks).
    data_start_col = cc_col0 + 2
    ms_col, hsd_col, speed_col, hsdie_col = None, None, None, None
    for i, lbl in enumerate(col_labels):
        if i < data_start_col:
            continue
        c = lbl.replace(" ", "")
        if ("HISPEEDDIESEL" in c or "SPEEDDIESEL" in c) and hsdie_col is None:
            hsdie_col = i
        elif "SPEED" in c and "HSD" not in c and speed_col is None:
            speed_col = i
        elif re.search(r"\bMS\b", lbl) and "HSD" not in lbl and ms_col is None:
            ms_col = i
        elif "HSD" in lbl and hsd_col is None:
            hsd_col = i

    # Fallback: use positions relative to cc_col
    if ms_col is None: ms_col = cc_col0 + 2
    if hsd_col is None: hsd_col = cc_col0 + 3

    rows = []
    for i in range(start_row, len(df_raw)):
        r = list(df_raw.iloc[i])
        vals = [str(v).replace(".0","").strip() if not pd.isna(v) else "" for v in r]

        cc = vals[cc_col0] if cc_col0 < len(vals) else ""
        if not re.match(r"^\d{5,7}$", cc):
            continue
        name = vals[cc_col0 + name_off] if cc_col0 + name_off < len(vals) else ""

        ms  = _flt(r[ms_col])  if ms_col  < len(r) else 0.0
        hsd = _flt(r[hsd_col]) if hsd_col < len(r) else 0.0

        if ms:
            rows.append(_row(cc, name, "BPCL", "MS", "Mother", ms, ""))
        if hsd:
            rows.append(_row(cc, name, "BPCL", "HSD", "Mother", hsd, ""))
        # branded daughters (part of mother volumes) — auto-detected
        if speed_col is not None and speed_col < len(r):
            sv = _flt(r[speed_col])
            if sv:
                rows.append(_row(cc, name, "BPCL", "MS", "Speed", sv, ""))
        if hsdie_col is not None and hsdie_col < len(r):
            hv = _flt(r[hsdie_col])
            if hv:
                rows.append(_row(cc, name, "BPCL", "HSD", "Hi Speed Diesel", hv, ""))

    return pd.DataFrame(rows) if rows else pd.DataFrame()

# ---------------------------------------------------------------------------
# HPCL parsers
# ---------------------------------------------------------------------------

def _parse_hpcl_nagar(filepath: str) -> pd.DataFrame:
    """
    Ahmednagar HPCL format — 'Sales Data' sheet.
    Cols: Sr | CC | SAP CODE | Name | Location | Taluka | District |
          MS Hist | MS Curr | HSD Hist | HSD Curr | Power Hist | Power Curr |
          Turbo Hist | Turbo Curr   (15–16 columns)
    Filters to Pune DO districts only.
    Extracts Power (branded MS) into separate rows.
    """
    def _flt(v):
        try: return float(str(v).replace(",",""))
        except: return 0.0

    sheets = _read_all_sheets(filepath, header=None)
    df_raw = sheets.get("Sales Data")
    if df_raw is None or df_raw.empty:
        df_raw = next((s for s in sheets.values() if not s.empty), None)
    if df_raw is None:
        return pd.DataFrame()
    df_raw = df_raw.reset_index(drop=True)

    # Header row: contains 'SAP CODE' or 'MS CURR'
    header_row = 0
    for i, row in df_raw.iterrows():
        flat = " ".join(str(v).upper() for v in row if not pd.isna(v))
        if "SAP CODE" in flat or "MS CURR" in flat or "MS HIS" in flat:
            header_row = i
            break

    df = df_raw.iloc[header_row + 1:].reset_index(drop=True)
    header = [str(v).strip().upper() for v in df_raw.iloc[header_row]]

    # Resolve column positions from header
    def _find_col(keywords, start=0):
        for i, h in enumerate(header[start:], start):
            if any(k in h for k in keywords):
                return i
        return None

    sap_col  = _find_col(["SAP CODE", "SAP"]) or 2
    name_col = _find_col(["NAME"]) or 3
    dist_col = _find_col(["DIST"]) or 6

    # MS/HSD columns: find pairs HIST then CURR
    ms_hist  = _find_col(["MS HIST", "MS HIS"]) or 7
    ms_curr  = _find_col(["MS CURR"], ms_hist) or ms_hist + 1
    hsd_hist = _find_col(["HSD HIST", "HSD HIS"]) or ms_curr + 1
    hsd_curr = _find_col(["HSD CURR"], hsd_hist) or hsd_hist + 1
    pow_curr = None
    tur_curr = None

    # Power and Turbo (optional)
    pw_hist = _find_col(["POWER HIST", "POWER HIS"])
    if pw_hist is not None:
        pow_curr = pw_hist + 1
    tu_hist = _find_col(["TURBO HIST", "TURBO HIS"])
    if tu_hist is not None:
        tur_curr = tu_hist + 1

    rows = []
    for _, r in df.iterrows():
        vals = [str(v).strip() if not pd.isna(v) else "" for v in r]
        if not vals[0].replace(".","").isdigit():
            continue

        dist_raw_val = vals[dist_col] if dist_col < len(vals) else ""
        dist, dist_conf = _resolve_district(dist_raw_val)
        if not _in_coverage(dist, dist_conf):
            continue

        sap_raw = vals[sap_col] if sap_col < len(vals) else ""
        sap = sap_raw.replace(".0","").strip()
        if not re.match(r"^\d{5,10}$", sap):
            continue

        name = vals[name_col] if name_col < len(vals) else ""
        ms  = _flt(r.iloc[ms_curr])  if ms_curr  < len(r) else 0.0
        hsd = _flt(r.iloc[hsd_curr]) if hsd_curr < len(r) else 0.0
        power = _flt(r.iloc[pow_curr]) if pow_curr is not None and pow_curr < len(r) else 0.0
        turbo = _flt(r.iloc[tur_curr]) if tur_curr is not None and tur_curr < len(r) else 0.0

        if ms:
            rows.append(_row(sap, name, "HPCL", "MS",  "Mother", ms,    dist,
                             district_raw=dist_raw_val, district_confidence=dist_conf))
        if hsd:
            rows.append(_row(sap, name, "HPCL", "HSD", "Mother", hsd,   dist,
                             district_raw=dist_raw_val, district_confidence=dist_conf))
        if power:
            rows.append(_row(sap, name, "HPCL", "MS",  "Power",  power, dist,
                             district_raw=dist_raw_val, district_confidence=dist_conf))
        if turbo:
            rows.append(_row(sap, name, "HPCL", "HSD", "Turbojet", turbo, dist,
                             district_raw=dist_raw_val, district_confidence=dist_conf))

    return pd.DataFrame(rows) if rows else pd.DataFrame()

def _parse_hpcl_ps(filepath: str) -> pd.DataFrame:
    """
    Pune+Satara HPCL format (Sheet1).
    Cols: Sr no | Customer Code New | District | Outlet name | Location |
          MS CY | MS LY | HSD CY | HSD LY | Power CY | Power LY
    """
    def _flt(v):
        try: return float(str(v).replace(",",""))
        except: return 0.0

    sheets = _read_all_sheets(filepath, header=None)
    df_raw = next(s for s in sheets.values() if not s.empty)
    df_raw = df_raw.reset_index(drop=True)

    # Find header row
    header_row = 0
    for i, row in df_raw.iterrows():
        flat = " ".join(str(v).upper() for v in row if not pd.isna(v))
        if "CUSTOMER CODE" in flat or "SR NO" in flat:
            header_row = i
            break

    header = [str(v).strip().upper() for v in df_raw.iloc[header_row]]
    df = df_raw.iloc[header_row + 1:].reset_index(drop=True)

    def _fc(keywords, start=0):
        for i, h in enumerate(header[start:], start):
            if any(k in h for k in keywords):
                return i
        return None

    sap_col  = _fc(["CUSTOMER CODE"]) or 1
    dist_col = _fc(["DISTRICT"]) or 2
    name_col = _fc(["OUTLET", "NAME"]) or 3

    # MS col: first col containing "MS" and month/year hint and not "LY"/"24"/"HIST"
    ms_col, hsd_col, pow_col = None, None, None
    for i, h in enumerate(header):
        if i <= sap_col: continue
        if re.search(r"MS.*2[0-9]", h) and "LY" not in h and ms_col is None:
            ms_col = i
        elif re.search(r"HSD.*2[0-9]", h) and "LY" not in h and hsd_col is None:
            hsd_col = i
        elif re.search(r"POWER.*2[0-9]", h) and "LY" not in h and pow_col is None:
            pow_col = i
        # Also handle generic "Total MS" or positional fallback
        elif "TOTAL MS" in h and ms_col is None:
            ms_col = i
        elif "TOTAL HSD" in h and hsd_col is None:
            hsd_col = i

    # Positional fallbacks
    if ms_col is None:  ms_col  = sap_col + 3
    if hsd_col is None: hsd_col = ms_col + 2

    rows = []
    for _, r in df.iterrows():
        vals = [str(v).strip() if not pd.isna(v) else "" for v in r]
        sap_raw = vals[sap_col] if sap_col < len(vals) else ""
        sap = sap_raw.replace(".0","").strip()
        if not re.match(r"^\d{5,10}$", sap):
            continue

        dist_raw_val = vals[dist_col] if dist_col < len(vals) else ""
        dist, dist_conf = _resolve_district(dist_raw_val)
        if not _in_coverage(dist, dist_conf):
            continue
        name = vals[name_col] if name_col < len(vals) else ""

        ms    = _flt(r.iloc[ms_col])  if ms_col  < len(r) else 0.0
        hsd   = _flt(r.iloc[hsd_col]) if hsd_col < len(r) else 0.0
        power = _flt(r.iloc[pow_col]) if pow_col is not None and pow_col < len(r) else 0.0

        if ms:
            rows.append(_row(sap, name, "HPCL", "MS",  "Mother", ms,    dist,
                             district_raw=dist_raw_val, district_confidence=dist_conf))
        if hsd:
            rows.append(_row(sap, name, "HPCL", "HSD", "Mother", hsd,   dist,
                             district_raw=dist_raw_val, district_confidence=dist_conf))
        if power:
            rows.append(_row(sap, name, "HPCL", "MS",  "Power",  power, dist,
                             district_raw=dist_raw_val, district_confidence=dist_conf))

    return pd.DataFrame(rows) if rows else pd.DataFrame()

# ---------------------------------------------------------------------------
# PVT OMC generic parser
# ---------------------------------------------------------------------------

def _parse_pvt_ro_wise(filepath: str, omc: str) -> pd.DataFrame:
    """
    Generic parser for user-compiled PVT OMC (NEL/RBML/SIMPL) RO-wise files.
    Expected columns (any order, case-insensitive):
        sap_code / cc_code / ro_code | ro_name | district | ms | hsd
    """
    def _flt(v):
        try: return float(str(v).replace(",",""))
        except: return 0.0

    sheets = _read_all_sheets(filepath, header=None)
    df_raw = next(s for s in sheets.values() if not s.empty)

    # Find header row
    header_row = 0
    for i, row in df_raw.iterrows():
        flat = " ".join(str(v).upper() for v in row if not pd.isna(v))
        if any(k in flat for k in ["SAP", "CC CODE", "RO CODE", "DEALER"]):
            header_row = i
            break

    header = [str(v).strip().upper() for v in df_raw.iloc[header_row]]
    df = df_raw.iloc[header_row + 1:].reset_index(drop=True)

    def _fc(keywords):
        for i, h in enumerate(header):
            if any(k in h for k in keywords):
                return i
        return None

    sap_col  = _fc(["SAP", "CC CODE", "RO CODE", "CC NO"]) or 0
    name_col = _fc(["NAME", "DEALER", "OUTLET"]) or 1
    dist_col = _fc(["DISTRICT", "DIST"])
    ms_col   = _fc(["MS", "PETROL", "MOTOR SPIRIT"])
    hsd_col  = _fc(["HSD", "DIESEL"])

    if ms_col is None or hsd_col is None:
        return pd.DataFrame()

    rows = []
    for _, r in df.iterrows():
        vals = [str(v).strip() if not pd.isna(v) else "" for v in r]
        sap = vals[sap_col].replace(".0","").strip() if sap_col < len(vals) else ""
        if not re.match(r"^\d{4,10}$", sap):
            continue
        name = vals[name_col] if name_col and name_col < len(vals) else ""
        dist_raw_val = vals[dist_col] if dist_col and dist_col < len(vals) else ""
        dist, dist_conf = _resolve_district(dist_raw_val) if dist_raw_val else ("", "exact")
        ms  = _flt(r.iloc[ms_col])
        hsd = _flt(r.iloc[hsd_col])

        if ms:
            rows.append(_row(sap, name, omc, "MS",  "Mother", ms,  dist,
                             district_raw=dist_raw_val, district_confidence=dist_conf))
        if hsd:
            rows.append(_row(sap, name, omc, "HSD", "Mother", hsd, dist,
                             district_raw=dist_raw_val, district_confidence=dist_conf))

    return pd.DataFrame(rows) if rows else pd.DataFrame()

# ---------------------------------------------------------------------------
# PVT OMC standardised sales format (company | ro_code | yyyymm | ms_sales | hsd_sales)
# ---------------------------------------------------------------------------

# Company code → OMC name mapping (as received in Pune DO exchange files)
_PVT_COMPANY_MAP: dict[str, str] = {
    "518": "NEL",
    "519": "RBML",
    "521": "SIMPL",
}

def _yyyymm_to_fy_month(yyyymm: str) -> tuple[str, int]:
    """
    Convert 'YYYYMM' string to (fy_code, month_index).
    FY convention: Apr=1 … Mar=12.
    e.g. '202512' → FY '2025-26', month_index 9
         '202604' → FY '2026-27', month_index 1
    """
    try:
        year  = int(str(yyyymm)[:4])
        month = int(str(yyyymm)[4:6])
    except (ValueError, TypeError):
        return "", 0
    # Apr–Mar FY: months Apr(4)–Mar(3)
    if month >= 4:
        fy_code     = f"{year}-{str(year + 1)[-2:]}"
        month_index = month - 3           # Apr=1, May=2, …, Dec=9
    else:
        fy_code     = f"{year - 1}-{str(year)[-2:]}"
        month_index = month + 9           # Jan=10, Feb=11, Mar=12
    return fy_code, month_index


def _parse_pvt_sales_format(filepath: str) -> pd.DataFrame:
    """
    Standardised PVT OMC exchange format used by Pune DO.
    Single 'Sales' sheet.  Row 0 = header.

    Columns: company | ro_code | yyyymm | ms_sales | hsd_sales
        company  — numeric code mapped to OMC via _PVT_COMPANY_MAP
        ro_code  — SAP code matching dim_ro.sap_code
        yyyymm   — month as YYYYMM; FY + month_index derived here
        ms_sales — MS volume in KL
        hsd_sales— HSD volume in KL

    No district column in file — district populated from dim_ro at pipeline time.

    Returns one row per product per RO (MS and HSD kept separate).
    district_confidence is set to 'exact' (no district ambiguity — all ROs pre-validated).
    """
    def _flt(v):
        try: return float(str(v).replace(",", "").strip())
        except: return 0.0

    sheets = _read_all_sheets(filepath, header=None)
    df_raw = sheets.get("Sales")
    if df_raw is None or df_raw.empty:
        df_raw = next((s for s in sheets.values() if not s.empty), None)
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()

    # Row 0 = header; confirm column names
    header = [str(v).strip().lower() for v in df_raw.iloc[0]]
    df = df_raw.iloc[1:].reset_index(drop=True)

    # Resolve column positions by name — fall back to positional if header absent
    def _col(names):
        for i, h in enumerate(header):
            if any(n in h for n in names):
                return i
        return None

    co_col  = _col(["company"]) if _col(["company"]) is not None else 0
    rc_col  = _col(["ro_code", "ro code"]) if _col(["ro_code", "ro code"]) is not None else 1
    ym_col  = _col(["yyyymm", "month"]) if _col(["yyyymm", "month"]) is not None else 2
    ms_col  = _col(["ms_sales", "ms sales", "ms"]) if _col(["ms_sales", "ms sales", "ms"]) is not None else 3
    hsd_col = _col(["hsd_sales", "hsd sales", "hsd"]) if _col(["hsd_sales", "hsd sales", "hsd"]) is not None else 4

    rows = []
    for _, r in df.iterrows():
        vals = [str(v).replace(".0", "").strip() if not pd.isna(v) else "" for v in r]

        sap = vals[rc_col] if rc_col < len(vals) else ""
        if not re.match(r"^\d{5,10}$", sap):
            continue

        co_code = vals[co_col] if co_col < len(vals) else ""
        omc = _PVT_COMPANY_MAP.get(co_code, co_code)  # fallback: use raw code

        yyyymm = vals[ym_col] if ym_col < len(vals) else ""
        fy_code, month_idx = _yyyymm_to_fy_month(yyyymm)

        ms  = _flt(r.iloc[ms_col])  if ms_col  < len(r) else 0.0
        hsd = _flt(r.iloc[hsd_col]) if hsd_col < len(r) else 0.0

        # District not in file — left blank; pipeline fills from dim_ro
        kwargs = dict(district_raw="", district_confidence="exact")

        if ms:
            row = _row(sap, "", omc, "MS", "Mother", ms, "", **kwargs)
            row["fy_code"]     = fy_code
            row["month_index"] = month_idx
            rows.append(row)
        if hsd:
            row = _row(sap, "", omc, "HSD", "Mother", hsd, "", **kwargs)
            row["fy_code"]     = fy_code
            row["month_index"] = month_idx
            rows.append(row)

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["sap_code","ro_name","omc","product","brand","volume_kl",
                 "district","district_raw","district_confidence","is_negative",
                 "fy_code","month_index"])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_and_parse(filepath: str, omc_hint: str,
                     month_index: int = None, fy_code: str = None) -> pd.DataFrame:
    """
    Auto-detect file format and return normalised DataFrame.
    month_index and fy_code are attached to each row for pipeline use.
    """
    fmt = detect_format(filepath, omc_hint)
    omc = omc_hint.upper() if omc_hint else ""

    # Infer product from filename for single-product IOCL files (e.g. "IOC MS 2025.xlsx")
    fname_upper = os.path.basename(filepath).upper()
    if " MS" in fname_upper or fname_upper.startswith("MS") or "_MS" in fname_upper:
        _prod_hint = "MS"
    elif " HSD" in fname_upper or fname_upper.startswith("HSD") or "_HSD" in fname_upper:
        _prod_hint = "HSD"
    else:
        _prod_hint = None

    if fmt == "iocl_sap_dump":
        df = _parse_iocl_sap_dump(filepath, product_hint=_prod_hint)
    elif fmt == "bpcl_q002_nagar":
        df = _parse_bpcl_q002_nagar(filepath)
    elif fmt == "bpcl_q145_ps":
        df = _parse_bpcl_q145_ps(filepath)
    elif fmt == "hpcl_nagar":
        df = _parse_hpcl_nagar(filepath)
    elif fmt == "hpcl_ps":
        df = _parse_hpcl_ps(filepath)
    elif fmt == "pvt_sales_format":
        df = _parse_pvt_sales_format(filepath)
    elif fmt == "pvt_ro_wise":
        df = _parse_pvt_ro_wise(filepath, omc)
    else:
        raise ValueError(f"Could not detect format for {os.path.basename(filepath)} "
                         f"(omc_hint={omc_hint}). Please check the file.")

    if df.empty:
        return df

    df["format_detected"] = fmt
    # pvt_sales_format embeds fy_code + month_index from the yyyymm column;
    # don't overwrite those with caller-supplied values.
    if fmt != "pvt_sales_format":
        if month_index is not None:
            df["month_index"] = month_index
        if fy_code is not None:
            df["fy_code"] = fy_code

    return df.reset_index(drop=True)

"""
config.py — Central configuration for the PDO Dashboard (repo root).
====================================================================
Single source of truth for everything that changes when this app is
adapted to a different Divisional Office, plus locked conventions.

Imported by:  ingest/parsers.py, ingest/pipeline.py, app/core.py,
              app/tab_16_ingest.py (and any new module needing coverage).

To adapt for another DO: change COVERAGE_DISTRICTS (and re-baseline
RECON_GUARD after the first clean full-FY load). Nothing else.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Geographic coverage — THE one line to change for a different DO
# --------------------------------------------------------------------------- #
COVERAGE_DISTRICTS: set[str] = {"Pune", "Ahmednagar", "Satara"}

# All Maharashtra districts — used for district-column auto-detection only.
MH_DISTRICTS: set[str] = {
    "Pune", "Satara", "Ahmednagar", "Nashik", "Kolhapur", "Solapur",
    "Aurangabad", "Chhatrapati Sambhajinagar", "Nagpur", "Thane",
    "Mumbai", "Raigad", "Ratnagiri", "Sindhudurg", "Dhule", "Jalgaon",
    "Nanded", "Latur", "Osmanabad", "Dharashiv", "Parbhani", "Hingoli",
    "Buldhana", "Akola", "Amravati", "Wardha", "Yavatmal", "Washim",
    "Beed", "Jalna", "Nandurbar", "Gondia", "Bhandara", "Gadchiroli",
    "Chandrapur", "Ahilyanagar",  # Ahmednagar's official new name
}

# Alternate spellings normalised to canonical coverage names.
DISTRICT_ALIASES: dict[str, str] = {
    "Ahmadnagar": "Ahmednagar",
    "Ahilyanagar": "Ahmednagar",
    "A.Nagar": "Ahmednagar",
    "Nagar": "Ahmednagar",
}

# --------------------------------------------------------------------------- #
# OMC universe
# --------------------------------------------------------------------------- #
PSU_OMCS: tuple = ("IOCL", "BPCL", "HPCL")
PVT_OMCS: tuple = ("NEL", "RBML", "SIMPL")
ALL_OMCS: tuple = PSU_OMCS + PVT_OMCS

# --------------------------------------------------------------------------- #
# Financial year convention (locked: Rules #1, #5)
# April = month_index 1 … March = month_index 12
# --------------------------------------------------------------------------- #
FY_START_MONTH = 4

_MONTH_ABBR = {
    1: "APR", 2: "MAY", 3: "JUN", 4: "JUL", 5: "AUG", 6: "SEP",
    7: "OCT", 8: "NOV", 9: "DEC", 10: "JAN", 11: "FEB", 12: "MAR",
}


def fy_label(start_year: int) -> str:
    """fy_label(2026) → '2026-27'."""
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def month_label(fy_code: str, month_index: int) -> str:
    """Canonical month label: month_label('2026-27', 3) → 'JUN.26'.

    This is THE stored format for fact_monthly.month_label. Any other
    format found in legacy rows is migrated (see Step 1.1 migration).
    """
    try:
        start_year = int(fy_code.split("-")[0])
        cal_year = start_year if month_index <= 9 else start_year + 1
        return f"{_MONTH_ABBR.get(month_index, 'UNK')}.{str(cal_year)[-2:]}"
    except (ValueError, IndexError, AttributeError):
        return ""


def cal_to_fy(cal_year: int, cal_month: int) -> tuple[str, int]:
    """Calendar (2026, 6) → ('2026-27', 3)."""
    if cal_month >= FY_START_MONTH:
        return fy_label(cal_year), cal_month - FY_START_MONTH + 1
    return fy_label(cal_year - 1), cal_month + (12 - FY_START_MONTH + 1)


# --------------------------------------------------------------------------- #
# Ingestion safeguards
# --------------------------------------------------------------------------- #
OUTLIER_FACTOR = 3.0        # flag volume > N× same OMC/RO/product prior FY month
TOTALS_TOLERANCE_KL = 0.5   # validate_totals hard-gate tolerance per district×product

# Reconciliation guard — IOCL share baselines for a frozen historical FY.
# Re-baseline yearly after the FY closes (document in MASTER_RULES.md).
RECON_GUARD = {
    "fy": "2025-26",
    "ms_industry": 23.8196,   # IOCL MS share vs all-6
    "hsd_industry": 26.3108,  # IOCL HSD share vs all-6
    "ms_psu": 26.5011,        # IOCL MS share vs PSU-3
    "tolerance_pp": 0.50,
}

# --------------------------------------------------------------------------- #
# Branded fuel rule (locked, officer 2026-07-04):
# MS and HSD are MOTHER products; every branded product is a DAUGHTER.
# Daughters ingest ALONGSIDE mother volumes, never instead of them.
# Parsers must auto-detect daughter columns when present in any sheet.
# --------------------------------------------------------------------------- #
BRANDED_DAUGHTERS = {
    "IOCL": {"MS": ["XP95", "XP100"], "HSD": ["XG"]},
    "BPCL": {"MS": ["Speed"], "HSD": ["Hi Speed Diesel", "Speed Diesel"]},
    "HPCL": {"MS": ["Power"], "HSD": ["Turbojet"]},
}

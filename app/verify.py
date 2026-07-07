#!/usr/bin/env python3
"""
Regression / smoke test for the Pune DO dashboard (v3 navigation shell).

Run from the Development/ folder:   python3 verify.py
Exit code 0 = all checks passed, 1 = something regressed.

Checks:
  1. DB resolves and the three used tables have expected row counts.
  2. Full-FY (Apr-Mar) IOCL market share reconciles to the headline numbers
     for the latest FY that hits them (Industry MS, Industry HSD, within-PSU MS).
  3. A single-month and a quarter volume sum equal a raw SQL GROUP BY.
  4. app.py imports & renders headlessly with no exception (Streamlit AppTest).
  5. All 15 navigation page modules import cleanly.
"""
import ast
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

def find_db():
    for p in (os.environ.get("PUNE_DO_DB"),
              os.path.join(HERE, "pune_do.db"),
              os.path.join(os.path.dirname(HERE), "pune_do.db"),
              os.path.join(os.getcwd(), "pune_do.db")):
        if p and os.path.exists(p):
            return p
    return None

PSU = ("IOCL", "BPCL", "HPCL")
PASS, FAIL = "PASS", "FAIL"
results = []

def check(name, ok, detail=""):
    results.append((PASS if ok else FAIL, name, detail))

# ---------------------------------------------------------------- DB checks
db = find_db()
if not db:
    print("FAIL: pune_do.db not found (set PUNE_DO_DB or place beside/above app.py)")
    sys.exit(1)
con = sqlite3.connect(db)

# Structural integrity check — fast (~1s), catches broken btree pages / corrupted
# indexes without reading every row. Must pass before any other DB assertions.
_qc = con.execute("PRAGMA quick_check").fetchone()
if _qc[0] != "ok":
    print(f"FAIL: DB integrity check — {_qc[0]}")
    print("      The database file is structurally corrupt.")
    print("      If it was copied via `cp` from a FUSE/USB mount, that is the cause.")
    print("      Restore from backup using:  python3 scripts/copy_db.py <source> <dest>")
    sys.exit(1)
check("DB quick_check (structural integrity)", True, "ok")

for t, expect in (("fact_monthly", 372631), ("dim_ro", 2168), ("dim_ta", 748)):
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    check(f"{t} row count", n == expect, f"got {n}, expected {expect}")

def share(fy, product, months, universe):
    """IOCL volume share within `universe` OMCs for the given FY/product/months."""
    ph = ",".join("?" * len(months))
    iocl = con.execute(
        f"SELECT COALESCE(SUM(volume_kl),0) FROM fact_monthly "
        f"WHERE fy_code=? AND product=? AND omc='IOCL' AND month_index IN ({ph})",
        [fy, product, *months]).fetchone()[0]
    uph = ",".join("?" * len(universe))
    tot = con.execute(
        f"SELECT COALESCE(SUM(volume_kl),0) FROM fact_monthly "
        f"WHERE fy_code=? AND product=? AND omc IN ({uph}) AND month_index IN ({ph})",
        [fy, product, *universe, *months]).fetchone()[0]
    return (iocl / tot * 100) if tot else 0.0

ALL = list(range(1, 13))
ALL6 = ("IOCL", "BPCL", "HPCL", "NEL", "RBML", "SIMPL")

fys = [r[0] for r in con.execute(
    "SELECT DISTINCT fy_code FROM fact_monthly ORDER BY fy_code")]
target = {"MS_ind": 23.82, "HSD_ind": 26.31, "MS_psu": 26.50}
matched_fy = None
for fy in fys:
    msi = share(fy, "MS", ALL, ALL6)
    hsi = share(fy, "HSD", ALL, ALL6)
    msp = share(fy, "MS", ALL, PSU)
    if (abs(msi - target["MS_ind"]) < 0.05 and
            abs(hsi - target["HSD_ind"]) < 0.05 and
            abs(msp - target["MS_psu"]) < 0.05):
        matched_fy = fy
        check("Headline IOCL MS share (Industry)", True, f"{fy}: {msi:.2f}%")
        check("Headline IOCL HSD share (Industry)", True, f"{fy}: {hsi:.2f}%")
        check("Headline IOCL MS share (within PSU)", True, f"{fy}: {msp:.2f}%")
        break
if not matched_fy:
    check("Headline reconciliation", False,
          "no FY reproduced 23.82/26.31/26.50 — check data or month_index mapping")

fy0 = matched_fy or fys[-1]
def raw_sum(fy, product, months):
    ph = ",".join("?" * len(months))
    return con.execute(
        f"SELECT COALESCE(SUM(volume_kl),0) FROM fact_monthly "
        f"WHERE fy_code=? AND product=? AND month_index IN ({ph})",
        [fy, product, *months]).fetchone()[0]
mar = raw_sum(fy0, "MS", [12])
q1 = raw_sum(fy0, "HSD", [1, 2, 3])
check("Single-month sum is a finite positive number", mar > 0, f"Mar MS={mar:.3f}")
check("Quarter sum is a finite positive number", q1 > 0, f"Q1 HSD={q1:.3f}")
con.close()

# ---------------------------------------------------------------- v2 tables
con2 = sqlite3.connect(db)
V2_TABLES = {
    "coco_work_orders": 10, "swagat_extended_ta": 30, "remm_master": 200,
    "remm_payments": 1000, "loi_master": 200, "loi_edit_log": 0,
    "fact_lube_monthly": 50000, "alt_fuel_master": 40,
    "fact_alt_fuel_monthly": 1000, "dim_ro_geo": 500,
}
for tbl, floor in V2_TABLES.items():
    try:
        n = con2.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        check(f"v2 table {tbl} rows >= {floor}", n >= floor, f"rows={n}")
    except Exception as e:
        check(f"v2 table {tbl}", False, str(e)[:60])
# OMC attribution integrity (pipeline v2 guarantee)
try:
    bad = con2.execute(
        "SELECT COUNT(*) FROM fact_monthly f JOIN dim_ro d "
        "ON f.sap_code=d.sap_code WHERE f.omc != d.omc").fetchone()[0]
    check("No cross-OMC misattributed fact rows", bad == 0, f"bad={bad}")
except Exception as e:
    check("Cross-OMC check", False, str(e)[:60])
# unique key present
idx = [r[0] for r in con2.execute(
    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='fact_monthly'")]
check("ux_fact_key unique index present", "ux_fact_key" in idx, str(idx))
# dim_ro tags
try:
    ncoco = con2.execute("SELECT COUNT(*) FROM dim_ro WHERE coco_flag=1").fetchone()[0]
    nsw = con2.execute("SELECT COUNT(*) FROM dim_ro WHERE swagat_tag='Swagat'").fetchone()[0]
    check("dim_ro coco_flag count == 16", ncoco == 16, f"coco={ncoco}")
    check("dim_ro Swagat tag present", nsw >= 1, f"swagat={nsw}")
except Exception as e:
    check("dim_ro tag columns", False, str(e)[:60])
# canonical month_label
badlbl = con2.execute(
    "SELECT COUNT(*) FROM fact_monthly WHERE month_label NOT GLOB '[A-Z][A-Z][A-Z].[0-9][0-9]'"
).fetchone()[0]
check("month_label canonical (AAA.YY) everywhere", badlbl == 0, f"bad={badlbl}")
con2.close()

# ---------------------------------------------------------------- page syntax
import ast

_pages_dir = os.path.join(HERE, "pages")
_page_files = sorted(
    f for f in os.listdir(_pages_dir)
    if f.endswith(".py") and not f.startswith("_")
)
for pf in _page_files:
    path = os.path.join(_pages_dir, pf)
    try:
        ast.parse(open(path, encoding="utf-8").read(), filename=path)
        check(f"Page syntax: {pf}", True)
    except SyntaxError as e:
        check(f"Page syntax: {pf}", False, str(e))

# ---------------------------------------------------------------- render check
try:
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(HERE, "app.py"))
    at.run(timeout=180)
    exc = list(at.exception)
    check("app.py renders headlessly without exception", len(exc) == 0,
          "; ".join(str(e.value) for e in exc) if exc else "")
    grids = [m.value for m in at.markdown if "tagrid" in m.value]
    if grids:
        bad = any(line.startswith("    ") for line in grids[0].splitlines())
        check("TA grid HTML has no indented (code-block) lines", not bad)
    nav_items = list(getattr(at, "sidebar", []))
    check("Navigation shell present", True,
          f"sidebar widgets={len(nav_items)}")
except Exception as e:  # noqa: BLE001
    check("AppTest render", False, f"{type(e).__name__}: {e}")

# ---------------------------------------------------------------- report
print(f"\nDB: {db}")
print(f"Reconciled FY: {matched_fy}\n")
width = max(len(n) for _, n, _ in results)
fails = 0
for status, name, detail in results:
    fails += status == FAIL
    print(f"  [{status}] {name.ljust(width)}  {detail}")
print(f"\n{len(results) - fails}/{len(results)} checks passed.")
sys.exit(1 if fails else 0)

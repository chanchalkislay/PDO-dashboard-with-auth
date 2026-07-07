"""
Parser + pipeline regression suite — Pune DO Dashboard v2.
Run from repo root:  python3 -m pytest tests/ -q   (or python3 tests/test_parsers_regression.py)

Fixtures = real OMC exchange files in "DO Data/OMC Sales Figures files/".
Expected totals were cross-verified on 2026-07-04 against:
  - HANDOFF.md June 2026 district totals (manual ingestion session), and
  - the live DB's April 2026 figures (pipeline-ingested).
Daughter-semantics convention (locked): IOCL fact = mother+daughters;
HPCL/BPCL fact = Mother rows only.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings; warnings.filterwarnings("ignore")

from ingest.parsers import detect_and_parse, detect_format

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "DO Data", "OMC Sales Figures files")

# (relpath, omc_hint, month_index, expected mother MS, mother HSD, tol, expected_format)
CASES = [
    ("BPCL Files/BPC June'26 Ahmednahar.xlsx",  "BPCL", 3,  8208.0, 19004.0, 0.5, "bpcl_q002_nagar"),
    ("BPCL Files/BPCL Sales June 2026 Pune Satara.xls", "BPCL", 3, 35851.2, 52837.1, 0.5, "bpcl_q145_ps"),
    ("BPCL Files/BPC Apr26 fig Nagar.xlsx",     "BPCL", 1,  7418.0, 17572.0, 0.5, None),
    ("BPCL Files/BPCL April 26 Vs April 25 Sales Data Pune Satara.xlsx",
                                                 "BPCL", 1, 33972.7, 50305.3, 0.5, None),
    ("BPCL Files/BPC Nov25 aHMEDNAGAR.xlsx",    "BPCL", 8,  7296.0, 18322.0, 0.5, None),
    ("BPCL Files/BPCL Figures Nov-25 Pune and Satara.xlsx",
                                                 "BPCL", 8, 32829.8, 48314.6, 0.5, None),
    ("BPCL Files/BPCL May26 Pune Satara.xls",   "BPCL", 2, 37562.7, 54196.6, 0.5, None),
    ("HPCL Files/HPC JUN 2026 Ahmednagar.xlsx", "HPCL", 3,  7021.5, 15275.5, 0.5, "hpcl_nagar"),
    ("HPCL Files/HPC Sales Jun-26_Pune Satara.xlsx",
                                                 "HPCL", 3, 42177.7, 73044.1, 0.5, "hpcl_ps"),
    ("HPCL Files/HPC APR 2026 Nagar.xlsx",      "HPCL", 1,  6303.0, 14694.0, 0.5, None),
    ("HPCL Files/HPC Sales Apr-26_IND Pune Satara.xlsx",
                                                 "HPCL", 1, 39231.1, 67632.1, 0.5, None),
    ("IOCL SAP Dump/June SAP dump.xlsx",        "IOCL", 3, 33066.5, 66704.0, 0.5, "iocl_sap_dump"),
    ("IOCL SAP Dump/SAP Dump April.xlsx",       "IOCL", 1, 30787.0, 63276.0, 0.5, None),
    ("Private files/SalesFormat_Apr'26.xls",    None,   1, 12291.0, 15586.5, 0.5, "pvt_sales_format"),
    ("Private files/SalesFormat_May'26.xls",    None,   2, 11034.0, 14470.0, 0.5, None),
]

# Daughter expectations (brand → volume) for files carrying branded columns
DAUGHTERS = {
    "HPCL Files/HPC JUN 2026 Ahmednagar.xlsx": {"Power": 518.5, "Turbojet": 39.5},
    "IOCL SAP Dump/June SAP dump.xlsx": {"XG": 337.5, "XP100": 32.0, "XP95": 1330.0},
    "IOCL SAP Dump/SAP Dump April.xlsx": {"XG": 403.0, "XP100": 33.0, "XP95": 1342.0},
}

# April 2026 fact-convention cross-check (verified vs live DB 2026-07-04):
#   IOCL DB Apr MS = 32,162.0 = mother 30,787 + XP95 1,342 + XP100 33
APRIL_IOCL_FACT_MS = 32162.0


def _resolve(rel):
    """Find the fixture even if punctuation was sanitised during git push
    (e.g. apostrophes -> underscores)."""
    p = os.path.join(BASE, rel)
    if os.path.exists(p):
        return p
    import glob as _g
    d, name = os.path.split(rel)
    pat = "".join("?" if not (c.isalnum() or c in " .-") else c for c in name)
    hits = _g.glob(os.path.join(BASE, d, pat))
    if hits:
        return hits[0]
    raise FileNotFoundError(rel)


def _run_case(rel, hint, mi, ms, hsd, tol, fmt):
    path = _resolve(rel)
    if fmt:
        det = detect_format(path, hint)
        assert det == fmt, f"{rel}: format {det} != {fmt}"
    df = detect_and_parse(path, hint, month_index=mi, fy_code="2026-27")
    assert len(df) > 0, f"{rel}: empty parse"
    mo = df[df["brand"] == "Mother"].groupby("product")["volume_kl"].sum()
    assert abs(mo.get("MS", 0) - ms) <= tol,  f"{rel}: MS {mo.get('MS',0)} != {ms}"
    assert abs(mo.get("HSD", 0) - hsd) <= tol, f"{rel}: HSD {mo.get('HSD',0)} != {hsd}"
    exp_d = DAUGHTERS.get(rel)
    if exp_d:
        got = df[df["brand"] != "Mother"].groupby("brand")["volume_kl"].sum().round(1).to_dict()
        for b, v in exp_d.items():
            assert abs(got.get(b, 0) - v) <= tol, f"{rel}: {b} {got.get(b,0)} != {v}"


def test_all_cases():
    for case in CASES:
        _run_case(*case)


def test_iocl_fact_semantics():
    """IOCL fact volume = mother + daughters (exclusive SAP materials)."""
    df = detect_and_parse(_resolve("IOCL SAP Dump/SAP Dump April.xlsx"),
                          "IOCL", month_index=1, fy_code="2026-27")
    total_ms = df[df["product"] == "MS"]["volume_kl"].sum()
    assert abs(total_ms - APRIL_IOCL_FACT_MS) <= 0.5


def test_pipeline_gates_and_commit():
    """End-to-end: commit June HPCL Nagar into a THROWAWAY copy of the DB;
    verify daughter semantics + hard gates + branded rows."""
    import sqlite3, tempfile, shutil
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_db = os.path.join(root, "app", "pune_do.db")
    tmpdir = tempfile.mkdtemp()
    db = os.path.join(tmpdir, "test.db")
    shutil.copyfile(src_db, db)

    from ingest.pipeline import Pipeline
    df = detect_and_parse(_resolve("HPCL Files/HPC JUN 2026 Ahmednagar.xlsx"),
                          "HPCL", month_index=3, fy_code="2026-27")
    pl = Pipeline(db, backup_dir=os.path.join(tmpdir, "bak"))
    res = pl.commit(df, "HPCL", "2026-27", 3, force=True)
    assert res["ok"], res.get("message")
    con = sqlite3.connect(db)
    saps = tuple(df["sap_code"].unique().tolist())
    ph = ",".join("?" * len(saps))
    ms = con.execute(f"SELECT ROUND(SUM(volume_kl),1) FROM fact_monthly "
                     f"WHERE omc='HPCL' AND fy_code='2026-27' AND month_index=3 "
                     f"AND product='MS' AND sap_code IN ({ph})", saps).fetchone()[0]
    assert abs(ms - 7021.5) <= 0.5, f"fact MS {ms} != 7021.5 (mother-only rule)"
    br = con.execute("SELECT ROUND(SUM(volume_kl),1) FROM fact_branded_monthly "
                     "WHERE omc='HPCL' AND fy_code='2026-27' AND month_index=3 "
                     "AND brand='Power'").fetchone()[0]
    assert abs(br - 518.5) <= 0.5, f"branded Power {br} != 518.5"
    lbl = con.execute("SELECT DISTINCT month_label FROM fact_monthly "
                      "WHERE fy_code='2026-27' AND month_index=3 AND omc='HPCL'").fetchall()
    assert lbl == [("JUN.26",)], f"month_label {lbl}"
    con.close(); shutil.rmtree(tmpdir)


if __name__ == "__main__":
    test_all_cases(); print("test_all_cases OK")
    test_iocl_fact_semantics(); print("test_iocl_fact_semantics OK")
    test_pipeline_gates_and_commit(); print("test_pipeline_gates_and_commit OK")
    print("ALL REGRESSION TESTS PASSED")

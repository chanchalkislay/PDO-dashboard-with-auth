#!/usr/bin/env python3
"""
ingest_branded.py — (re)build fact_branded_monthly in the LOCAL pune_do.db
from data/Branded MS.xlsx. Safe to re-run any time (DROP + CREATE).

Run from the development_additional_features folder:
    python ingest_branded.py
or point at a specific DB:
    PUNE_DO_DB=/path/to/pune_do.db python ingest_branded.py

Why this exists: OneDrive must NOT sync a live SQLite DB — it can overwrite the
branded table. Rebuild it locally with this script instead of relying on a synced
copy. The Excel source and this script are small text/spreadsheet files that sync
fine; only the .db should never be cloud-synced while in use.
"""
import os, sys, sqlite3
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_XLSX = os.path.join(HERE, "data", "Branded MS.xlsx")
SRC_TAG  = "Branded MS.xlsx"
BRAND = {"IOCL": "XP95", "BPCL": "Speed", "HPCL": "Power"}  # branded MS; one brand per PSU OMC

def find_db():
    env = os.environ.get("PUNE_DO_DB")
    if env and os.path.exists(env):
        return env
    for d in (HERE, os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, "pune_do.db")
        if os.path.exists(p):
            return p
    sys.exit("ERROR: pune_do.db not found (set PUNE_DO_DB or place beside this script).")

def main():
    try:
        import openpyxl
    except ImportError:
        sys.exit("ERROR: openpyxl not installed. Run:  pip install openpyxl")
    if not os.path.exists(SRC_XLSX):
        sys.exit(f"ERROR: source not found: {SRC_XLSX}")

    db = find_db()
    print(f"DB     : {db}")
    print(f"Source : {SRC_XLSX}")

    wb = openpyxl.load_workbook(SRC_XLSX, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    hdr0 = rows[0]
    MONTHS = ["APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC","JAN","FEB","MAR"]
    colmap = {}
    for i in range(4, 95):
        v = hdr0[i]
        if isinstance(v, str) and "." in v:
            mon, yy = v.split(".")
            midx = MONTHS.index(mon.strip().upper()[:3]) + 1
            yr = 2000 + int(yy)
            fy = f"{yr}-{str(yr+1)[2:]}" if midx <= 9 else f"{yr-1}-{str(yr)[2:]}"
            colmap[i] = (fy, midx, v.strip())
    data = [r for r in rows[2:] if isinstance(r[0], (int, float)) and r[1] is not None]

    con = sqlite3.connect(db)
    cur = con.cursor()
    ro = {str(s): o for s, o in cur.execute("SELECT sap_code, omc FROM dim_ro")}
    ms = defaultdict(float)
    for s, fy, mi, vol in cur.execute(
            "SELECT sap_code, fy_code, month_index, volume_kl "
            "FROM fact_monthly WHERE product='MS'"):
        ms[(str(s), fy, mi)] += vol or 0

    cur.execute("DROP TABLE IF EXISTS fact_branded_monthly")
    cur.execute("""CREATE TABLE fact_branded_monthly (
        sap_code TEXT NOT NULL, omc TEXT NOT NULL, product TEXT NOT NULL,
        brand TEXT NOT NULL, fy_code TEXT NOT NULL, month_index INTEGER NOT NULL,
        month_label TEXT NOT NULL, volume_kl REAL NOT NULL, source TEXT,
        PRIMARY KEY (sap_code, product, brand, fy_code, month_index))""")
    cur.execute("CREATE INDEX ix_branded_sap ON fact_branded_monthly(sap_code)")
    cur.execute("CREATE INDEX ix_branded_fy ON fact_branded_monthly(fy_code, month_index)")

    ins, dropped, priv, unknown = [], [], 0, []
    for r in data:
        sap, omc = str(r[1]), r[3]
        if sap not in ro:
            unknown.append(sap); continue
        if omc not in BRAND:
            priv += 1; continue
        brand = BRAND[omc]
        for i, (fy, mi, mlab) in colmap.items():
            b = r[i] or 0
            if b <= 0:
                continue
            if ms.get((sap, fy, mi), 0) <= 0:
                dropped.append((sap, omc, fy, mlab, b)); continue
            ins.append((sap, omc, "MS", brand, fy, mi, mlab, float(b), SRC_TAG))
    cur.executemany("INSERT INTO fact_branded_monthly VALUES (?,?,?,?,?,?,?,?,?)", ins)
    con.commit()

    print(f"\nInserted {len(ins)} rows | dropped(MotherMS=0)={len(dropped)} "
          f"| skipped private={priv} | unknown SAP={unknown}")
    print("By OMC/brand:",
          cur.execute("SELECT omc,brand,COUNT(*),ROUND(SUM(volume_kl)) "
                      "FROM fact_branded_monthly GROUP BY omc,brand").fetchall())
    bad = cur.execute("""SELECT COUNT(*) FROM fact_branded_monthly b
        LEFT JOIN (SELECT sap_code,fy_code,month_index,SUM(volume_kl) mv
                   FROM fact_monthly WHERE product='MS' GROUP BY 1,2,3) m
        ON b.sap_code=m.sap_code AND b.fy_code=m.fy_code AND b.month_index=m.month_index
        WHERE m.mv IS NULL OR b.volume_kl > m.mv+0.5""").fetchone()[0]
    print(f"branded<=MotherMS violations: {bad}  (must be 0)")
    print(f"integrity_check: {cur.execute('PRAGMA integrity_check').fetchone()[0]}")
    con.close()
    print("\nDONE. Restart the dashboard and open the Branded MS tab.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
ingest_xp.py — Ingest XtraPower (fleet card) data into the database.

Source: data/Xtrapower.xlsx  (wide format, 663 IOCL ROs)
  Row 0: month date headers (datetime), FY-total string labels, comparison labels
  Row 1: column labels — SL.NO | SAP | MID | NAME OF THE RETAIL OUTLET |
          then repeating: HSD | XP | %Conv  (for every month + every FY total)
  Rows 2+: one row per IOCL RO

Creates / populates three tables (idempotent on fact_xtrapower_monthly + dim_itps):
  fact_xtrapower_monthly — sap_code × fy_code × month_index with hsd_kl, xp_kl
  dim_itps               — sap_code → mid (Merchant ID; NULL if no ITPS)
  xp_action_plans        — created once if absent (not cleared — preserves user data)

Rules:
  - Only IOCL ROs cross-checked against dim_ro
  - MID present → ITPS installed; MID absent → no ITPS (stored as NULL in dim_itps)
  - Negative HSD/XP values are rounding artefacts in source — clipped to 0
  - Rows stored only where clipped HSD > 0 OR clipped XP > 0 (skip fully-zero months)
  - XP > HSD cells are flagged at console but still inserted (surfaced as red flag in tab)
  - FY2026-27 skipped (Rule #184)
  - Idempotent: fact_xtrapower_monthly and dim_itps are fully replaced on each run;
    xp_action_plans is never cleared (preserves officer notes)

Run from Development/ folder:
    python ingest_xp.py
or point at a specific DB:
    PUNE_DO_DB=/path/to/pune_do.db python ingest_xp.py
"""
import os, sys, sqlite3, datetime

HERE    = os.path.dirname(os.path.abspath(__file__))
SRC     = os.path.join(HERE, "data", "Xtrapower.xlsx")
SRC_TAG = "Xtrapower.xlsx"

MONTH_LABELS = ["APR", "MAY", "JUN", "JUL", "AUG", "SEP",
                "OCT", "NOV", "DEC", "JAN", "FEB", "MAR"]

def find_db():
    env = os.environ.get("PUNE_DO_DB")
    if env and os.path.exists(env):
        return env
    for d in (HERE, os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, "pune_do.db")
        if os.path.exists(p):
            return p
    sys.exit("ERROR: pune_do.db not found.")


def main():
    try:
        import openpyxl
    except ImportError:
        sys.exit("ERROR: openpyxl not installed.  pip install openpyxl")
    if not os.path.exists(SRC):
        sys.exit(f"ERROR: source not found: {SRC}")

    db_path = find_db()
    print(f"DB     : {db_path}")
    print(f"Source : {SRC}")
    print()

    # ── Parse source file ────────────────────────────────────────────────────
    wb   = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws   = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))

    hdr0 = rows[0]  # row 0: date/label headers

    # Build column index → (fy_code, month_index, month_label)
    # Each datetime col marks the start of a 3-col group: HSD | XP | %Conv
    # Skip FY-total string entries (e.g. '2022-23') and comparison cols at end
    colmap = {}  # col_idx (of HSD) → (fy_code, month_index, month_label)
    for i, v in enumerate(hdr0):
        if not isinstance(v, datetime.datetime):
            continue
        month = v.month
        year  = v.year
        midx  = month - 3 if month >= 4 else month + 9
        fy_s  = year if month >= 4 else year - 1
        if fy_s >= 2026:          # Rule #184 — exclude FY2026-27
            continue
        fy   = f"{fy_s}-{str(fy_s + 1)[-2:]}"
        cal_yr = fy_s if month >= 4 else fy_s + 1
        mlab = f"{MONTH_LABELS[midx - 1]}.{str(cal_yr)[-2:]}"
        colmap[i] = (fy, midx, mlab)  # col i = HSD, i+1 = XP, i+2 = %Conv

    print(f"Monthly columns mapped : {len(colmap)}")
    print(f"FY range               : "
          f"{min(v[0] for v in colmap.values())} → "
          f"{max(v[0] for v in colmap.values())}")

    # Data rows: col 1 = SAP code (int), col 2 = MID (int or None), col 3 = name
    data_rows = [r for r in rows[2:]
                 if isinstance(r[1], (int, float)) and r[1] is not None]
    print(f"Total RO rows in file  : {len(data_rows)}")
    with_mid    = sum(1 for r in data_rows if r[2] is not None)
    without_mid = sum(1 for r in data_rows if r[2] is None)
    print(f"ROs with MID (ITPS)    : {with_mid}")
    print(f"ROs without MID        : {without_mid}")
    print()

    # ── DB cross-checks ──────────────────────────────────────────────────────
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    def _sap(s):
        try:    return str(int(float(str(s).strip())))
        except: return str(s).strip()

    known_iocl = {_sap(s) for s, o in
                  cur.execute("SELECT sap_code, omc FROM dim_ro WHERE omc='IOCL'")}
    known_all  = {_sap(s) for s, in
                  cur.execute("SELECT sap_code FROM dim_ro")}

    # ── Create tables ────────────────────────────────────────────────────────
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS fact_xtrapower_monthly (
            sap_code    TEXT NOT NULL,
            fy_code     TEXT NOT NULL,
            month_index INTEGER NOT NULL,
            month_label TEXT NOT NULL,
            hsd_kl      REAL NOT NULL DEFAULT 0,
            xp_kl       REAL NOT NULL DEFAULT 0,
            source      TEXT,
            PRIMARY KEY (sap_code, fy_code, month_index)
        );
        CREATE INDEX IF NOT EXISTS ix_xp_fy
            ON fact_xtrapower_monthly (fy_code, month_index);
        CREATE INDEX IF NOT EXISTS ix_xp_sap
            ON fact_xtrapower_monthly (sap_code);

        CREATE TABLE IF NOT EXISTS dim_itps (
            sap_code    TEXT PRIMARY KEY,
            mid         TEXT,
            source      TEXT
        );

        CREATE TABLE IF NOT EXISTS xp_action_plans (
            sap_code    TEXT NOT NULL,
            category    TEXT NOT NULL,
            action_text TEXT DEFAULT '',
            officer     TEXT DEFAULT '',
            status      TEXT DEFAULT 'active',
            created_at  TEXT,
            updated_at  TEXT,
            PRIMARY KEY (sap_code, category)
        );
    """)

    # Idempotent clear of fact and dim tables (xp_action_plans preserved)
    cur.execute("DELETE FROM fact_xtrapower_monthly")
    cur.execute("DELETE FROM dim_itps")
    print("Cleared existing fact_xtrapower_monthly and dim_itps rows.")

    # ── Build insert lists ───────────────────────────────────────────────────
    xp_rows   = []   # (sap, fy, midx, mlab, hsd_kl, xp_kl, source)
    itps_rows = []   # (sap, mid, source)
    unknown   = []
    non_iocl  = []
    xp_gt_hsd = []   # data-integrity flags (stored but surfaced as red flag)

    for r in data_rows:
        sap = str(int(r[1]))
        mid = str(int(r[2])) if r[2] is not None else None

        if sap not in known_all:
            unknown.append(sap)
            continue
        if sap not in known_iocl:
            non_iocl.append(sap)
            continue

        # dim_itps: all confirmed IOCL ROs (MID may be None)
        itps_rows.append((sap, mid, SRC_TAG))

        # Monthly data
        for hsd_col, (fy, midx, mlab) in colmap.items():
            raw_hsd = r[hsd_col]
            raw_xp  = r[hsd_col + 1]
            hsd_v = max(0.0, float(raw_hsd) if raw_hsd is not None else 0.0)
            xp_v  = max(0.0, float(raw_xp)  if raw_xp  is not None else 0.0)
            # Skip fully-zero months
            if hsd_v == 0.0 and xp_v == 0.0:
                continue
            # Log XP > HSD violations (still insert)
            if xp_v > hsd_v + 0.5 and hsd_v > 0.0:
                xp_gt_hsd.append((sap, fy, mlab, hsd_v, xp_v))
            xp_rows.append((sap, fy, midx, mlab, hsd_v, xp_v, SRC_TAG))

    # ── Console report ───────────────────────────────────────────────────────
    if unknown:
        print(f"WARNING: {len(unknown)} SAP codes not in dim_ro — skipped: "
              f"{unknown[:10]}{'…' if len(unknown) > 10 else ''}")
    if non_iocl:
        print(f"WARNING: {len(non_iocl)} non-IOCL SAP codes — skipped: {non_iocl}")
    if xp_gt_hsd:
        print(f"\n⚠  XP > HSD violations in source ({len(xp_gt_hsd)} cells — "
              f"inserted, flagged as red flag in tab):")
        for sap, fy, mlab, h, x in xp_gt_hsd[:10]:
            print(f"   SAP {sap}  {fy} {mlab}  HSD={h:.3f}  XP={x:.3f}")
        if len(xp_gt_hsd) > 10:
            print(f"   … and {len(xp_gt_hsd) - 10} more cells")

    print()
    total_xp_kl  = sum(r[5] for r in xp_rows)
    total_hsd_kl = sum(r[4] for r in xp_rows)
    print(f"dim_itps rows to insert          : {len(itps_rows)} IOCL ROs")
    print(f"fact_xtrapower_monthly to insert : {len(xp_rows)} rows  "
          f"({total_xp_kl:,.1f} XP KL  /  {total_hsd_kl:,.1f} HSD KL)")
    print()

    # ── Insert ───────────────────────────────────────────────────────────────
    cur.executemany(
        "INSERT OR REPLACE INTO dim_itps (sap_code, mid, source) "
        "VALUES (?,?,?)",
        itps_rows)

    cur.executemany(
        "INSERT INTO fact_xtrapower_monthly "
        "(sap_code, fy_code, month_index, month_label, hsd_kl, xp_kl, source) "
        "VALUES (?,?,?,?,?,?,?)",
        xp_rows)

    con.commit()

    # ── Post-insert verification ─────────────────────────────────────────────
    print("=== Post-insert verification ===")

    # By FY
    print("XP volume by FY:")
    for fy, n, xp, hsd in cur.execute(
            "SELECT fy_code, COUNT(*), ROUND(SUM(xp_kl),1), ROUND(SUM(hsd_kl),1) "
            "FROM fact_xtrapower_monthly GROUP BY fy_code ORDER BY fy_code"):
        conv = xp / hsd * 100 if hsd else 0.0
        print(f"  {fy}: {n:>5} rows  |  XP {xp:>12,.1f} KL  "
              f"HSD {hsd:>12,.1f} KL  Conv {conv:.2f}%")

    itps_r = cur.execute(
        "SELECT COUNT(*), SUM(CASE WHEN mid IS NOT NULL THEN 1 ELSE 0 END) "
        "FROM dim_itps").fetchone()
    print(f"\ndim_itps: {itps_r[0]} ROs  |  "
          f"ITPS-enabled (MID present): {itps_r[1]}  |  "
          f"No ITPS: {itps_r[0] - (itps_r[1] or 0)}")

    viol = cur.execute(
        "SELECT COUNT(*) FROM fact_xtrapower_monthly "
        "WHERE xp_kl > hsd_kl + 0.5 AND hsd_kl > 0").fetchone()[0]
    print(f"XP > HSD violations stored in DB: {viol}")

    # Reconciliation — fact_monthly must be untouched
    rec_fy = cur.execute(
        "SELECT MAX(fy_code) FROM fact_monthly").fetchone()[0]
    iocl_ms  = cur.execute(
        "SELECT SUM(volume_kl) FROM fact_monthly "
        "WHERE omc='IOCL' AND product='MS' AND fy_code=?", (rec_fy,)
    ).fetchone()[0] or 0
    tot_ms   = cur.execute(
        "SELECT SUM(volume_kl) FROM fact_monthly "
        "WHERE product='MS' AND fy_code=?", (rec_fy,)
    ).fetchone()[0] or 1
    iocl_hsd = cur.execute(
        "SELECT SUM(volume_kl) FROM fact_monthly "
        "WHERE omc='IOCL' AND product='HSD' AND fy_code=?", (rec_fy,)
    ).fetchone()[0] or 0
    tot_hsd  = cur.execute(
        "SELECT SUM(volume_kl) FROM fact_monthly "
        "WHERE product='HSD' AND fy_code=?", (rec_fy,)
    ).fetchone()[0] or 1
    print(f"\nReconciliation ({rec_fy}):")
    print(f"  IOCL MS share : {iocl_ms / tot_ms * 100:.2f}%  (must be 23.82%)")
    print(f"  IOCL HSD share: {iocl_hsd / tot_hsd * 100:.2f}%  (must be 26.31%)")
    print(f"  fact_monthly rows: "
          f"{cur.execute('SELECT COUNT(*) FROM fact_monthly').fetchone()[0]}"
          f"  (must be 360,528)")
    print(f"  integrity_check: "
          f"{cur.execute('PRAGMA integrity_check').fetchone()[0]}")

    con.close()
    print("\nDONE. XtraPower data ingested. Restart the dashboard to see Tab 13.")


if __name__ == "__main__":
    main()

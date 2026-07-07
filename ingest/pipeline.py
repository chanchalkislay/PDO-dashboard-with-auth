#!/usr/bin/env python3
"""
pipeline.py — Core ingestion logic for the Pune DO dashboard.

Public API
----------
    from ingest.pipeline import Pipeline
    pl = Pipeline(db_path="test/pune_do_test.db")
    summary = pl.dry_run(df, omc, fy_code, month_index, month_label)
    result  = pl.commit(df, omc, fy_code, month_index, month_label)
    pl.rollback()   # if needed after a commit

FUSE-mount safety (Kingston USB)
---------------------------------
NEVER use cp/shutil.copy/dd on SQLite files via FUSE mount.
All writes use: read → /tmp → modify → os.replace() write-back.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Central config (repo root config.py) — guard baselines, tolerances, labels
# ---------------------------------------------------------------------------
try:
    import config as _cfg
except ImportError:
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config as _cfg

_GUARD_FY      = _cfg.RECON_GUARD["fy"]
_GUARD_MS_IND  = _cfg.RECON_GUARD["ms_industry"]
_GUARD_HSD_IND = _cfg.RECON_GUARD["hsd_industry"]
_GUARD_MS_PSU  = _cfg.RECON_GUARD["ms_psu"]
_GUARD_TOL     = _cfg.RECON_GUARD["tolerance_pp"]

_ALL6 = _cfg.ALL_OMCS
_PSU  = _cfg.PSU_OMCS

OUTLIER_FACTOR      = _cfg.OUTLIER_FACTOR
TOTALS_TOLERANCE_KL = _cfg.TOTALS_TOLERANCE_KL

# Canonical month label ('JUN.26') — single implementation lives in config.
_month_label = _cfg.month_label


# ---------------------------------------------------------------------------
# FUSE-safe DB helpers
# ---------------------------------------------------------------------------

def _load_db(src: str) -> tuple[sqlite3.Connection, str]:
    """Copy DB to /tmp, return (connection, tmp_path). Close + unlink when done."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    with open(src, "rb") as f:
        data = f.read()
    with open(tmp.name, "wb") as f:
        f.write(data)
    con = sqlite3.connect(tmp.name)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con, tmp.name


def _write_back(tmp_path: str, dst: str) -> None:
    """Atomically write /tmp DB back to mount point."""
    with open(tmp_path, "rb") as f:
        new_data = f.read()
    staging = dst + ".tmp"
    with open(staging, "wb") as f:
        f.write(new_data); f.flush(); os.fsync(f.fileno())
    os.replace(staging, dst)


def _snapshot(tmp_path: str, backup_dir: str, label: str) -> str:
    """Save timestamped snapshot; return snapshot path."""
    os.makedirs(backup_dir, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"pune_do_backup_{ts}_{label}.db"
    dst  = os.path.join(backup_dir, name)
    shutil.copy2(tmp_path, dst)
    return dst


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _dim_ro_lookup(sap_codes: list[str], con: sqlite3.Connection,
                   omc: str = None) -> dict:
    """Return {sap_code: {ta_code, rsa_code, district}} for known codes.

    OMC-SCOPED (v2 fix): matching is restricted to dim_ro rows of the SAME
    OMC. BPCL CC numbers and IOCL SAP codes share a numeric range — an
    OMC-blind match can silently attribute one OMC's volume to another
    OMC's outlet (observed live: BPCL CC 180555 vs IOCL sap 180555).
    """
    if not sap_codes:
        return {}
    ph = ",".join("?" * len(sap_codes))
    omc_clause = " AND omc=?" if omc else ""
    args = list(sap_codes) + ([omc] if omc else [])
    rows = con.execute(
        f"SELECT sap_code, ta_code, rsa_code, district FROM dim_ro "
        f"WHERE sap_code IN ({ph}){omc_clause}",
        args
    ).fetchall()
    return {r[0]: {"ta_code": r[1], "rsa_code": r[2], "district": r[3]} for r in rows}


def dim_ro_cross_check(df: pd.DataFrame, con: sqlite3.Connection,
                       omc: str = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split df into (known_df, unknown_df) by OMC-scoped dim_ro membership."""
    codes = df["sap_code"].unique().tolist()
    lookup = _dim_ro_lookup(codes, con, omc)
    known_mask = df["sap_code"].isin(lookup.keys())
    return df[known_mask].copy(), df[~known_mask].copy()


def duplicate_check(omc: str, fy_code: str, month_index: int,
                    con: sqlite3.Connection,
                    sap_codes: list = None) -> Optional[dict]:
    """Data-driven duplicate detection.

    BPCL/HPCL legitimately deliver a month as MULTIPLE files (Nagar +
    Pune-Satara split), so omc+fy+month alone is NOT a duplicate. A real
    duplicate is when the INCOMING outlets already have rows for this
    omc+fy+month. Returns a dict when >10% of incoming SAP codes overlap.
    """
    if not sap_codes:
        return None
    ph = ",".join("?" * len(sap_codes))
    hit = con.execute(
        f"SELECT COUNT(DISTINCT sap_code) FROM fact_monthly "
        f"WHERE omc=? AND fy_code=? AND month_index=? AND sap_code IN ({ph})",
        [omc, fy_code, month_index, *sap_codes]
    ).fetchone()[0]
    if hit and hit > 0.10 * len(sap_codes):
        log = con.execute(
            "SELECT run_id, ingested_at, notes FROM ingestion_log "
            "WHERE omc=? AND fy_code=? AND month_index=? "
            "ORDER BY run_id DESC LIMIT 1",
            (omc, fy_code, month_index)).fetchone()
        return {"overlap_ros": int(hit), "incoming_ros": len(sap_codes),
                "run_id": log[0] if log else None,
                "ingested_at": log[1] if log else "(no log entry)",
                "rows_inserted": None,
                "notes": log[2] if log else ""}
    return None


def volume_outlier_check(df: pd.DataFrame, omc: str, fy_code: str,
                         month_index: int,
                         con: sqlite3.Connection) -> pd.DataFrame:
    """Flag rows where volume > OUTLIER_FACTOR × same omc/RO/product prior FY same month."""
    try:
        start_year = int(fy_code.split("-")[0])
        prior_fy   = f"{start_year - 1}-{str(start_year)[-2:]}"
    except (ValueError, IndexError):
        return pd.DataFrame()

    rows = con.execute(
        "SELECT sap_code, product, SUM(volume_kl) "
        "FROM fact_monthly "
        "WHERE omc=? AND fy_code=? AND month_index=? "
        "GROUP BY sap_code, product",
        (omc, prior_fy, month_index)
    ).fetchall()
    prior = {(r[0], r[1]): r[2] for r in rows}

    outliers = []
    for _, row in df.iterrows():
        key = (row["sap_code"], row["product"])
        prior_vol = prior.get(key, 0)
        if prior_vol > 0 and row["volume_kl"] > OUTLIER_FACTOR * prior_vol:
            r = row.to_dict()
            r["outlier_reason"] = (
                f"Volume {row['volume_kl']:.1f} KL is "
                f"{row['volume_kl'] / prior_vol:.1f}× prior year "
                f"({prior_vol:.1f} KL)"
            )
            outliers.append(r)
    return pd.DataFrame(outliers) if outliers else pd.DataFrame()


def pvt_district_check(df: pd.DataFrame, con: sqlite3.Connection,
                       district_totals: dict) -> list[dict]:
    """
    Compare summed RO volumes vs user-supplied district totals.
    district_totals = {("Pune", "MS"): 1240.0, ...}
    Returns list of discrepancy dicts.
    """
    if not district_totals:
        return []

    codes = df["sap_code"].unique().tolist()
    ph = ",".join("?" * len(codes))
    dist_map = {
        r[0]: r[1]
        for r in con.execute(
            f"SELECT sap_code, district FROM dim_ro WHERE sap_code IN ({ph})", codes
        ).fetchall()
    }
    df2 = df.copy()
    df2["_dist"] = df2["sap_code"].map(dist_map).fillna("")

    discrepancies = []
    for (district, product), supplied_total in district_totals.items():
        file_total = df2[
            (df2["_dist"] == district) & (df2["product"] == product)
        ]["volume_kl"].sum()
        diff     = file_total - supplied_total
        diff_pct = abs(diff / supplied_total * 100) if supplied_total else 0
        if diff_pct > 0.1:
            discrepancies.append({
                "district":       district,
                "product":        product,
                "file_total":     round(file_total, 2),
                "supplied_total": round(supplied_total, 2),
                "diff_kl":        round(diff, 2),
                "diff_pct":       round(diff_pct, 2),
            })
    return discrepancies


def _fact_base(df: pd.DataFrame, omc: str) -> pd.DataFrame:
    """Rows that constitute fact_monthly volume for this file (daughter
    semantics: IOCL SAP dump = mother+daughters; others = Mother only)."""
    if "brand" not in df.columns:
        return df
    fmt = ""
    if "format_detected" in df.columns and len(df):
        fmt = str(df["format_detected"].iloc[0])
    exclusive = (fmt == "iocl_sap_dump") or (fmt == "" and omc == "IOCL")
    return df if exclusive else df[df["brand"] == "Mother"]


def validate_totals(con: sqlite3.Connection, omc: str, fy_code: str,
                    month_index: int, known_df: pd.DataFrame) -> dict:
    """HARD GATE (v2): after insert, the DB totals for this omc+fy+month must
    equal the file's known-row totals per product, within TOTALS_TOLERANCE_KL.
    Catches insert bugs, partial writes, and silent row loss.

    Returns {"ok": bool, "mismatches": [...]} — caller rolls back if not ok.
    """
    base = _fact_base(known_df, omc)
    file_tot = (base.groupby("product")["volume_kl"].sum()).to_dict()
    # Restrict the DB side to the SAP codes present in THIS file — the same
    # omc+fy+month may legitimately hold rows from another district's file
    # (e.g. BPCL Pune-Satara committed before BPCL Ahmednagar).
    saps = known_df["sap_code"].unique().tolist()
    con.execute("CREATE TEMP TABLE IF NOT EXISTS _vt_saps (sap_code TEXT)")
    con.execute("DELETE FROM _vt_saps")
    con.executemany("INSERT INTO _vt_saps VALUES (?)", [(s,) for s in saps])
    mismatches = []
    for product, ftot in file_tot.items():
        db_tot = con.execute(
            "SELECT COALESCE(SUM(f.volume_kl),0) FROM fact_monthly f "
            "JOIN _vt_saps s ON f.sap_code = s.sap_code "
            "WHERE f.omc=? AND f.fy_code=? AND f.month_index=? AND f.product=?",
            (omc, fy_code, month_index, product)
        ).fetchone()[0]
        if abs(db_tot - ftot) > TOTALS_TOLERANCE_KL:
            mismatches.append({
                "product": product,
                "file_total": round(float(ftot), 3),
                "db_total": round(float(db_tot), 3),
                "diff": round(float(db_tot - ftot), 3),
            })
    return {"ok": not mismatches, "mismatches": mismatches}


def unknown_volume_gate(unknown_df: pd.DataFrame) -> dict:
    """HARD GATE (v2): unknown SAP codes carrying real volume must be resolved
    (new RO / legacy map) before commit — zero-volume unknowns pass through
    to staging silently. Returns {"ok", "withheld_kl", "codes"}."""
    if unknown_df.empty:
        return {"ok": True, "withheld_kl": 0.0, "codes": []}
    vol = float(unknown_df["volume_kl"].sum())
    codes = (unknown_df.groupby("sap_code")["volume_kl"].sum()
             .loc[lambda s: s > TOTALS_TOLERANCE_KL])
    return {
        "ok": len(codes) == 0,
        "withheld_kl": round(vol, 2),
        "codes": [{"sap_code": k, "volume_kl": round(float(v), 2)}
                  for k, v in codes.items()],
    }


# ---------------------------------------------------------------------------
# Reconciliation guard
# ---------------------------------------------------------------------------

def _iocl_share(fy: str, product: str, universe: tuple,
                con: sqlite3.Connection) -> float:
    ph_u = ",".join("?" * len(universe))
    iocl = con.execute(
        "SELECT COALESCE(SUM(volume_kl),0) FROM fact_monthly "
        "WHERE fy_code=? AND product=? AND omc='IOCL'",
        [fy, product]
    ).fetchone()[0]
    total = con.execute(
        f"SELECT COALESCE(SUM(volume_kl),0) FROM fact_monthly "
        f"WHERE fy_code=? AND product=? AND omc IN ({ph_u})",
        [fy, product, *universe]
    ).fetchone()[0]
    return round(iocl / total * 100, 4) if total else 0.0


def reconciliation_check(con: sqlite3.Connection) -> dict:
    msi = _iocl_share(_GUARD_FY, "MS",  _ALL6, con)
    hsi = _iocl_share(_GUARD_FY, "HSD", _ALL6, con)
    msp = _iocl_share(_GUARD_FY, "MS",  _PSU,  con)
    ok  = (
        abs(msi - _GUARD_MS_IND)  <= _GUARD_TOL and
        abs(hsi - _GUARD_HSD_IND) <= _GUARD_TOL and
        abs(msp - _GUARD_MS_PSU)  <= _GUARD_TOL
    )
    return {
        "ok": ok,
        "MS_ind":  msi,
        "HSD_ind": hsi,
        "MS_psu":  msp,
        "baseline_MS_ind":  _GUARD_MS_IND,
        "baseline_HSD_ind": _GUARD_HSD_IND,
        "baseline_MS_psu":  _GUARD_MS_PSU,
    }


# ---------------------------------------------------------------------------
# Insert helpers
# ---------------------------------------------------------------------------

def _insert_fact_monthly(df: pd.DataFrame, omc: str, fy_code: str,
                         month_index: int, month_label: str,
                         dim_ro_map: dict,
                         con: sqlite3.Connection) -> tuple[int, int]:
    """
    INSERT OR REPLACE aggregated (sap_code, product) rows into fact_monthly.
    dim_ro_map: {sap_code: {ta_code, rsa_code, district}}
    Returns (rows_inserted, rows_replaced).
    """
    # Aggregate to sap_code+product total for fact_monthly.
    #
    # DAUGHTER SEMANTICS (locked convention, verified against 7-yr history
    # 2026-07-04):
    #   IOCL SAP dump  — materials are EXCLUSIVE slices (16730 regular MS,
    #                    17295 XP95 …) → fact volume = mother + daughters.
    #   HPCL / BPCL    — daughter columns (Power, Speed …) are subsets already
    #                    contained in the reported product figure → fact
    #                    volume = Mother rows ONLY (daughters go solely to
    #                    fact_branded_monthly).
    base = _fact_base(df, omc)
    agg = (
        base.groupby(["sap_code", "product"])["volume_kl"]
        .sum()
        .reset_index()
    )

    # Batch-delete only the exact (sap_code, product) pairs being replaced,
    # via a temp table — avoids wiping other-district rows already committed
    # for the same omc+fy+month from a separate file (e.g. PS + Nagar split).
    con.execute("CREATE TEMP TABLE IF NOT EXISTS _del_keys "
                "(sap_code TEXT, product TEXT)")
    con.execute("DELETE FROM _del_keys")
    con.executemany("INSERT INTO _del_keys VALUES (?,?)",
                    [(r["sap_code"], r["product"]) for _, r in agg.iterrows()])

    existing = con.execute(
        "SELECT COUNT(*) FROM fact_monthly f "
        "JOIN _del_keys k ON f.sap_code=k.sap_code AND f.product=k.product "
        "WHERE f.omc=? AND f.fy_code=? AND f.month_index=?",
        (omc, fy_code, month_index)
    ).fetchone()[0]
    if existing:
        con.execute(
            "DELETE FROM fact_monthly WHERE omc=? AND fy_code=? AND month_index=? "
            "AND EXISTS (SELECT 1 FROM _del_keys k "
            "WHERE k.sap_code=fact_monthly.sap_code AND k.product=fact_monthly.product)",
            (omc, fy_code, month_index)
        )

    inserted = 0
    for _, row in agg.iterrows():
        sap  = row["sap_code"]
        meta = dim_ro_map.get(sap, {})
        con.execute(
            """INSERT INTO fact_monthly
               (sap_code, ta_code, rsa_code, omc, district, product,
                fy_code, month_label, month_index, volume_kl, is_negative)
               VALUES (?,?,?,?,?,?,?,?,?,?,0)""",
            (sap,
             meta.get("ta_code", ""),
             meta.get("rsa_code", ""),
             omc,
             meta.get("district", ""),
             row["product"],
             fy_code,
             month_label,
             month_index,
             round(float(row["volume_kl"]), 3))
        )
        inserted += 1

    replaced = min(existing, inserted)
    return inserted, replaced


def _insert_fact_branded(df: pd.DataFrame, omc: str, fy_code: str,
                         month_index: int, month_label: str,
                         source_label: str,
                         con: sqlite3.Connection) -> int:
    """INSERT OR REPLACE branded rows (brand != 'Mother') into fact_branded_monthly."""
    if "brand" not in df.columns:
        return 0
    branded = df[df["brand"] != "Mother"].copy()
    if branded.empty:
        return 0

    inserted = 0
    for _, row in branded.iterrows():
        con.execute(
            """INSERT OR REPLACE INTO fact_branded_monthly
               (sap_code, omc, product, brand, fy_code, month_index,
                month_label, volume_kl, source)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (row["sap_code"], omc, row["product"], row["brand"],
             fy_code, month_index, month_label,
             round(float(row["volume_kl"]), 3), source_label)
        )
        inserted += 1
    return inserted


def _stage_unknown_ros(unknown_df: pd.DataFrame, omc: str, fy_code: str,
                       month_index: int, con: sqlite3.Connection) -> int:
    """Queue unknown SAP codes into staging_unknown_ros for later resolution."""
    if unknown_df.empty:
        return 0
    existing = {
        r[0] for r in con.execute(
            "SELECT sap_code FROM staging_unknown_ros WHERE omc=?", (omc,)
        ).fetchall()
    }
    inserted = 0
    for sap in unknown_df["sap_code"].unique():
        if sap in existing:
            continue
        name_row = unknown_df[unknown_df["sap_code"] == sap].iloc[0]
        con.execute(
            """INSERT OR IGNORE INTO staging_unknown_ros
               (sap_code, ro_name, omc, first_seen_fy, first_seen_month, resolution)
               VALUES (?,?,?,?,?,'pending')""",
            (sap, name_row.get("ro_name", ""), omc, fy_code, month_index)
        )
        inserted += 1
    return inserted


def _log_ingestion(con: sqlite3.Connection, **kw) -> int:
    cur = con.execute(
        """INSERT INTO ingestion_log
           (omc, fy_code, month_index, month_label, district,
            rows_inserted, rows_replaced, total_ms_kl, total_hsd_kl,
            new_ros_found, outliers_flagged, notes, snapshot_path)
           VALUES (:omc,:fy_code,:month_index,:month_label,:district,
                   :rows_inserted,:rows_replaced,:total_ms_kl,:total_hsd_kl,
                   :new_ros_found,:outliers_flagged,:notes,:snapshot_path)""",
        kw
    )
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------

class Pipeline:
    """
    Orchestrates validation, dry-run, commit, and rollback for a single
    OMC × month ingestion.

    Parameters
    ----------
    db_path    : str — path to pune_do.db (may be on a FUSE mount)
    backup_dir : str — directory for pre-commit snapshots
    """

    def __init__(self, db_path: str, backup_dir: str = None):
        self.db_path    = db_path
        self.backup_dir = backup_dir or os.path.join(
            os.path.dirname(os.path.abspath(db_path)), "backups"
        )
        self._snapshot_path: Optional[str] = None

    # ── internal ────────────────────────────────────────────────────────────

    def _validate(self, df: pd.DataFrame, omc: str, fy_code: str,
                  month_index: int, con: sqlite3.Connection) -> dict:
        known_df, unknown_df = dim_ro_cross_check(df, con, omc)
        dup      = duplicate_check(omc, fy_code, month_index, con,
                                   known_df["sap_code"].unique().tolist())
        outliers = volume_outlier_check(known_df, omc, fy_code, month_index, con)

        fuzzy_rows = []
        if "district_confidence" in df.columns:
            fuzzy_rows = (
                df[df["district_confidence"] == "fuzzy"]
                [["sap_code", "ro_name", "district_raw", "district"]]
                .drop_duplicates()
                .to_dict("records")
            )

        return {
            "total_rows":        len(df),
            "known_ros":         int(known_df["sap_code"].nunique()),
            "unknown_ros":       int(unknown_df["sap_code"].nunique()),
            "unknown_sap_codes": unknown_df["sap_code"].unique().tolist(),
            "duplicate":         dup,
            "outlier_count":     len(outliers),
            "outliers":          outliers.to_dict("records") if not outliers.empty else [],
            "fuzzy_districts":   fuzzy_rows,
            "total_ms_kl":       round(float(df[df["product"] == "MS"]["volume_kl"].sum()), 2),
            "total_hsd_kl":      round(float(df[df["product"] == "HSD"]["volume_kl"].sum()), 2),
            "_known_df":         known_df,
            "_unknown_df":       unknown_df,
        }

    # ── public ──────────────────────────────────────────────────────────────

    def dry_run(self, df: pd.DataFrame, omc: str, fy_code: str,
                month_index: int, month_label: str = None,
                district_totals: dict = None) -> dict:
        """
        Validate df and return a summary dict — no DB writes.
        """
        if not month_label:
            month_label = _month_label(fy_code, month_index)

        con, tmp = _load_db(self.db_path)
        try:
            v = self._validate(df, omc, fy_code, month_index, con)
            v["omc"]          = omc
            v["fy_code"]      = fy_code
            v["month_index"]  = month_index
            v["month_label"]  = month_label
            v["dry_run"]      = True
            v["district_discrepancies"] = (
                pvt_district_check(v["_known_df"], con, district_totals)
                if district_totals else []
            )
            # Remove internal keys before returning
            v.pop("_known_df", None); v.pop("_unknown_df", None)
            return v
        finally:
            con.close()
            if os.path.exists(tmp): os.unlink(tmp)

    def commit(self, df: pd.DataFrame, omc: str, fy_code: str,
               month_index: int, month_label: str = None,
               district: str = "",
               district_totals: dict = None,
               source_label: str = "",
               notes: str = "",
               force: bool = False) -> dict:
        """
        Validate → snapshot → insert → guard check → write back.

        force=True allows re-ingestion of an already-logged omc+fy+month
        (replaces existing data).
        """
        if not month_label:
            month_label = _month_label(fy_code, month_index)
        if not source_label:
            source_label = f"{omc}_{month_label}"

        con, tmp = _load_db(self.db_path)
        try:
            v = self._validate(df, omc, fy_code, month_index, con)

            if v["duplicate"] and not force:
                con.close(); os.unlink(tmp)
                return {
                    "ok": False,
                    "message": (
                        f"Duplicate data: {v['duplicate']['overlap_ros']} of "
                        f"{v['duplicate']['incoming_ros']} incoming outlets already "
                        f"have {omc} {month_label} {fy_code} rows "
                        f"(last log: {v['duplicate']['ingested_at']}). "
                        "Pass force=True to replace."
                    ),
                    "duplicate": v["duplicate"],
                }

            known_df   = v["_known_df"]
            unknown_df = v["_unknown_df"]

            # v2 HARD GATE 1 — unknown SAP codes carrying volume block commit
            # (resolve as new RO / legacy map in the ingest UI, or force=True
            # to consciously stage-and-proceed).
            ugate = unknown_volume_gate(unknown_df)
            if not ugate["ok"] and not force:
                con.close(); os.unlink(tmp)
                return {
                    "ok": False,
                    "message": (
                        f"Blocked: {len(ugate['codes'])} unknown SAP code(s) "
                        f"carry {ugate['withheld_kl']} KL. Resolve them "
                        "(new RO / legacy map) or pass force=True to stage "
                        "them and commit without their volume."
                    ),
                    "unknown_volume_gate": ugate,
                    "unknown_sap_codes": v["unknown_sap_codes"],
                }

            # Snapshot before any write
            snap = _snapshot(tmp, self.backup_dir,
                             f"{omc}_{fy_code}_m{month_index:02d}")
            self._snapshot_path = snap

            # dim_ro lookup for ta_code/rsa_code/district enrichment
            dim_ro_map = _dim_ro_lookup(
                known_df["sap_code"].unique().tolist(), con, omc
            )

            # Stage unknown ROs
            new_ros = _stage_unknown_ros(unknown_df, omc, fy_code, month_index, con)

            # Insert fact_monthly (all product rows aggregated)
            rows_ins, rows_rep = _insert_fact_monthly(
                known_df, omc, fy_code, month_index, month_label, dim_ro_map, con
            )

            # Insert fact_branded_monthly (brand != Mother rows)
            branded_ins = _insert_fact_branded(
                known_df, omc, fy_code, month_index, month_label, source_label, con
            )

            # PVT district cross-check (warn, don't block)
            discrepancies = (
                pvt_district_check(known_df, con, district_totals)
                if district_totals else []
            )
            if discrepancies:
                disc_str = "; ".join(
                    f"{d['district']} {d['product']}: Δ{d['diff_kl']:+.1f} KL ({d['diff_pct']:.1f}%)"
                    for d in discrepancies
                )
                notes = f"DISTRICT_MISMATCH: {disc_str}" + (f" | {notes}" if notes else "")

            # Outlier note
            if v["outlier_count"]:
                notes = (f"OUTLIERS({v['outlier_count']})" +
                         (f" | {notes}" if notes else ""))

            # v2 HARD GATE 2 — DB totals must equal file totals after insert
            vt = validate_totals(con, omc, fy_code, month_index, known_df)
            if not vt["ok"]:
                con.close(); os.unlink(tmp)
                # tmp discarded → live DB untouched; snapshot kept for audit
                return {
                    "ok": False,
                    "message": (
                        "Blocked: post-insert totals do not match file totals "
                        f"(tolerance {TOTALS_TOLERANCE_KL} KL): {vt['mismatches']}. "
                        "No changes written to the live DB."
                    ),
                    "validate_totals": vt,
                    "snapshot_path": snap,
                }

            # Post-commit reconciliation guard
            recon = reconciliation_check(con)

            if not recon["ok"]:
                # Auto-rollback — don't write back
                con.close(); os.unlink(tmp)
                _restore_snapshot(snap, self.db_path)
                return {
                    "ok": False,
                    "message": (
                        "Reconciliation guard broken — auto-rolled back. "
                        f"MS_ind={recon['MS_ind']} (baseline {_GUARD_MS_IND}), "
                        f"HSD_ind={recon['HSD_ind']} (baseline {_GUARD_HSD_IND})"
                    ),
                    "reconciliation": recon,
                    "snapshot_path":  snap,
                }

            # Log
            run_id = _log_ingestion(
                con,
                omc=omc, fy_code=fy_code, month_index=month_index,
                month_label=month_label, district=district,
                rows_inserted=rows_ins, rows_replaced=rows_rep,
                total_ms_kl=v["total_ms_kl"], total_hsd_kl=v["total_hsd_kl"],
                new_ros_found=new_ros, outliers_flagged=v["outlier_count"],
                notes=notes, snapshot_path=snap,
            )

            con.commit()
            con.close()
            _write_back(tmp, self.db_path)

            return {
                "ok":                    True,
                "run_id":                run_id,
                "message":               (
                    f"OK — {omc} {month_label} {fy_code}: "
                    f"{rows_ins} rows, {branded_ins} branded rows, "
                    f"{new_ros} new ROs staged, "
                    f"{v['outlier_count']} outliers flagged."
                ),
                "rows_inserted":          rows_ins,
                "rows_replaced":          rows_rep,
                "branded_rows":           branded_ins,
                "new_ros_found":          new_ros,
                "outliers_flagged":       v["outlier_count"],
                "outliers":               v["outliers"],
                "unknown_sap_codes":      v["unknown_sap_codes"],
                "reconciliation":         recon,
                "snapshot_path":          snap,
                "district_discrepancies": discrepancies,
            }

        except Exception:
            con.close()
            if os.path.exists(tmp): os.unlink(tmp)
            raise

    def rollback(self) -> bool:
        """Restore DB from the snapshot taken during the last commit()."""
        if not self._snapshot_path or not os.path.exists(self._snapshot_path):
            return False
        _restore_snapshot(self._snapshot_path, self.db_path)
        self._snapshot_path = None
        return True


def _restore_snapshot(snap: str, dst: str) -> None:
    with open(snap, "rb") as f:
        data = f.read()
    staging = dst + ".tmp"
    with open(staging, "wb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(staging, dst)


# ---------------------------------------------------------------------------
# New-RO resolution helper
# ---------------------------------------------------------------------------

def resolve_new_ro(sap_code: str, ro_name: str, omc: str,
                   district: str, ta_code: str, rsa_code: str,
                   db_path: str) -> dict:
    """
    Add a newly confirmed RO to dim_ro with data_complete_flag='No'.
    Used after dim_ro_cross_check identifies an unknown SAP code.
    """
    con, tmp = _load_db(db_path)
    try:
        exists = con.execute(
            "SELECT 1 FROM dim_ro WHERE sap_code=?", (sap_code,)
        ).fetchone()
        if exists:
            con.close(); os.unlink(tmp)
            return {"ok": False, "message": f"{sap_code} already in dim_ro"}

        con.execute(
            """INSERT INTO dim_ro
               (sap_code, ro_name, omc, district, ta_code, rsa_code, data_complete_flag)
               VALUES (?,?,?,?,?,?,'No')""",
            (sap_code, ro_name, omc, district, ta_code, rsa_code)
        )
        con.execute(
            "UPDATE staging_unknown_ros SET resolution='new_ro', resolved_at=? "
            "WHERE sap_code=? AND omc=?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sap_code, omc)
        )
        con.commit()
        _write_back(tmp, db_path)
        con.close()
        return {"ok": True,
                "message": f"Added {sap_code} ({ro_name}) to dim_ro (data_complete_flag=No)"}
    except Exception as e:
        con.close()
        if os.path.exists(tmp): os.unlink(tmp)
        return {"ok": False, "message": str(e)}


def record_sap_remap(new_sap: str, existing_sap: str, omc: str, db_path: str) -> dict:
    """
    Record that new_sap is a code reassignment for the outlet currently known as existing_sap.

    Actions:
    1. Appends new_sap to dim_ro.legacy_sap_codes for the existing_sap row
       (comma-separated if multiple legacy codes already exist).
    2. Updates staging_unknown_ros resolution to 'mapped_to:<existing_sap>'
       so the NRO banner doesn't fire for this code.

    The actual fact_monthly data was already written under existing_sap by the
    caller (SAP codes were remapped in the DataFrame before commit).
    """
    con, tmp = _load_db(db_path)
    try:
        # 1. Update legacy_sap_codes for the existing RO
        row = con.execute(
            "SELECT legacy_sap_codes FROM dim_ro WHERE sap_code=?", (existing_sap,)
        ).fetchone()
        if row is None:
            con.close(); os.unlink(tmp)
            return {"ok": False, "message": f"Existing SAP {existing_sap} not in dim_ro"}

        current = row[0] or ""
        legacy_codes = [c.strip() for c in current.split(",") if c.strip()]
        if new_sap not in legacy_codes:
            legacy_codes.append(new_sap)
        con.execute(
            "UPDATE dim_ro SET legacy_sap_codes=? WHERE sap_code=?",
            (",".join(legacy_codes), existing_sap)
        )

        # 2. Resolve staging entry so NRO banner clears
        con.execute(
            """INSERT OR IGNORE INTO staging_unknown_ros
               (sap_code, omc, resolution, resolved_at)
               VALUES (?, ?, ?, ?)""",
            (new_sap, omc,
             f"mapped_to:{existing_sap}",
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        con.execute(
            "UPDATE staging_unknown_ros SET resolution=?, resolved_at=? "
            "WHERE sap_code=? AND omc=?",
            (f"mapped_to:{existing_sap}",
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             new_sap, omc)
        )

        con.commit()
        _write_back(tmp, db_path)
        con.close()
        return {
            "ok": True,
            "message": f"Mapped {new_sap} -> {existing_sap}; legacy_sap_codes updated."
        }
    except Exception as e:
        con.close()
        if os.path.exists(tmp): os.unlink(tmp)
        return {"ok": False, "message": str(e)}

# EOF marker — pipeline.py v2 (Step 1.1/1.2 edits applied 2026-07-04)

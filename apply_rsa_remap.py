"""
One-time script to correct RSA mappings in dim_ta and propagate
new TA codes to fact_monthly and dim_ro.

Run from the repo root:  python apply_rsa_remap.py
"""
import sqlite3, os, shutil
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "app", "pune_do.db")

# ── Backup ────────────────────────────────────────────────────────────────────
backup_dir = os.path.join(os.path.dirname(__file__), "app", "backups")
os.makedirs(backup_dir, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = os.path.join(backup_dir, f"pune_do_backup_{ts}_pre_rsa_remap.db")
shutil.copy2(DB_PATH, backup_path)
print(f"Backup saved → {backup_path}")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

def remap(old, new, rsa_code, rsa_name):
    cur.execute(
        "UPDATE dim_ta SET ta_code=?, rsa_code=?, rsa_name=? WHERE ta_code=?",
        (new, rsa_code, rsa_name, old)
    )
    cur.execute("UPDATE fact_monthly SET ta_code=? WHERE ta_code=?", (new, old))
    cur.execute("UPDATE dim_ro     SET ta_code=? WHERE ta_code=?", (new, old))

# ── 9 M40 TAs → M69 (Satara West) ───────────────────────────────────────────
for old, new in [
    ("M40-034", "M69-066"),
    ("M40-033", "M69-067"),
    ("M40-031", "M69-068"),
    ("M40-024", "M69-069"),
    ("M40-030", "M69-070"),
    ("M40-028", "M69-071"),
    ("M40-049", "M69-072"),
    ("M40-048", "M69-073"),
    ("M40-060", "M69-074"),
]:
    remap(old, new, "M69", "Satara West")
    print(f"  {old} → {new}")

# ── M40-050 → M67 (Pune Wagholi) ─────────────────────────────────────────────
remap("M40-050", "M67-084", "M67", "Pune Wagholi")
print("  M40-050 → M67-084")

# ── M41-030 → M93 (Pune Hadapsar) ────────────────────────────────────────────
remap("M41-030", "M93-050", "M93", "Pune Hadapsar")
print("  M41-030 → M93-050")

# ── 15 M45 TAs → M69 (Satara West) ──────────────────────────────────────────
for old, new in [
    ("M45-019", "M69-075"),
    ("M45-040", "M69-076"),
    ("M45-076", "M69-077"),
    ("M45-010", "M69-078"),
    ("M45-080", "M69-079"),
    ("M45-075", "M69-080"),
    ("M45-033", "M69-081"),
    ("M45-050", "M69-082"),
    ("M45-046", "M69-083"),
    ("M45-031", "M69-084"),
    ("M45-087", "M69-085"),
    ("M45-026", "M69-086"),
    ("M45-005", "M69-087"),
    ("M45-027", "M69-088"),
    ("M45-071", "M69-089"),
]:
    remap(old, new, "M69", "Satara West")
    print(f"  {old} → {new}")

# ── Merge M69-014 (Jambhud) into M69-041 (Monopoly) ─────────────────────────
cur.execute("UPDATE dim_ro     SET ta_code='M69-041' WHERE ta_code='M69-014'")
cur.execute("UPDATE fact_monthly SET ta_code='M69-041' WHERE ta_code='M69-014'")
cur.execute("DELETE FROM dim_ta WHERE ta_code='M69-014'")
print("  M69-014 (Jambhud) merged into M69-041 (Monopoly)")

conn.commit()

# Force WAL checkpoint so changes land in the main .db file
conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
conn.commit()
conn.close()
print("\nAll done. WAL checkpointed. Commit app/pune_do.db to git.")

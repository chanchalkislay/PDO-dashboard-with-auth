"""
bootstrap.py — Runs at the top of every page (via `import bootstrap`).

Responsibilities
----------------
1. Ensure the app/ directory is on sys.path so all local modules resolve.
2. Show an NRO warning banner if any newly-commissioned ROs or unclassified
   SAP codes are pending attention in the database.

NRO banner logic
----------------
Two conditions trigger the banner:

  A) dim_ro rows where data_complete_flag != 'Yes'
     → ROs added via resolve_new_ro() that still need RSA/TA details filled in.

  B) staging_unknown_ros rows where resolution = 'pending'
     → SAP codes seen during file ingestion that have not yet been classified
       (added to dim_ro or marked as errors).

The check is cached for 5 minutes so it doesn't hit the filesystem on every
widget interaction.
"""
from __future__ import annotations

import os
import sys
import tempfile

import streamlit as st

# ── 1. Path setup ─────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# Repo root (parent of app/) — required for `import config` and `import ingest.*`
_REPO_ROOT = os.path.dirname(_ROOT)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── 2. NRO warning banner ─────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _nro_check(db_path: str) -> dict:
    """
    Return counts of pending NRO items.
    Cached for 5 minutes. Pass db_path as arg so cache key is DB-specific.
    """
    import sqlite3

    try:
        with open(db_path, "rb") as f:
            data = f.read()
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with open(tmp.name, "wb") as f:
            f.write(data)

        con = sqlite3.connect(tmp.name)

        # A) ROs in dim_ro with incomplete data
        incomplete = con.execute(
            "SELECT sap_code, ro_name, omc, district "
            "FROM dim_ro WHERE COALESCE(data_complete_flag,'') != 'Yes'"
        ).fetchall()

        # B) Staged unknown SAPs pending classification
        # (table may not exist on older DB versions — handle gracefully)
        try:
            staged = con.execute(
                "SELECT sap_code, ro_name, omc, first_seen_fy, first_seen_month "
                "FROM staging_unknown_ros WHERE resolution = 'pending'"
            ).fetchall()
        except Exception:
            staged = []

        con.close()
        os.unlink(tmp.name)

        return {
            "incomplete_ros": [
                {"sap_code": r[0], "ro_name": r[1], "omc": r[2], "district": r[3]}
                for r in incomplete
            ],
            "staged_unknowns": [
                {"sap_code": r[0], "ro_name": r[1], "omc": r[2],
                 "fy": r[3], "month": r[4]}
                for r in staged
            ],
        }
    except Exception:
        return {"incomplete_ros": [], "staged_unknowns": []}


def _show_nro_banner(db_path: str) -> None:
    """Render the NRO warning banner if any items need attention."""
    result = _nro_check(db_path)
    inc    = result["incomplete_ros"]
    stg    = result["staged_unknowns"]

    if not inc and not stg:
        return

    # Build summary line
    parts = []
    if inc:
        parts.append(f"**{len(inc)}** RO(s) with incomplete master data")
    if stg:
        parts.append(f"**{len(stg)}** unclassified SAP code(s) pending classification")

    banner_text = "🔔 NRO Alert: " + " · ".join(parts) + "."

    with st.warning(banner_text):
        if inc:
            with st.expander(f"Incomplete ROs ({len(inc)}) — need RSA / TA details"):
                import pandas as pd
                st.dataframe(
                    pd.DataFrame(inc)[["sap_code", "ro_name", "omc", "district"]],
                    use_container_width=True,
                    hide_index=True,
                )

        if stg:
            with st.expander(f"Unclassified SAP codes ({len(stg)}) — from recent file ingestion"):
                import pandas as pd
                df = pd.DataFrame(stg)
                # Build human-readable month label
                _abbr = {1:"APR",2:"MAY",3:"JUN",4:"JUL",5:"AUG",6:"SEP",
                         7:"OCT",8:"NOV",9:"DEC",10:"JAN",11:"FEB",12:"MAR"}
                df["period"] = df.apply(
                    lambda r: f"{_abbr.get(r['month'],'?')}.{str(r['fy'])[-2:]}"
                    if r["month"] else r["fy"], axis=1
                )
                st.dataframe(
                    df[["sap_code", "ro_name", "omc", "period"]],
                    use_container_width=True,
                    hide_index=True,
                )
        st.caption(
            "Go to **Admin → Data Ingestion** to classify new SAP codes. "
            "Update RSA/TA details directly in dim_ro for incomplete ROs."
        )


# ── Run banner on every page load ─────────────────────────────────────────────
try:
    from core import DB_PATH
    _show_nro_banner(DB_PATH)
except Exception:
    pass  # Never let a banner failure crash the dashboard

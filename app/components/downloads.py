"""CSV download buttons for report tables (global improvement 1.4).

Usage:  df_download(df_or_styler, "unique_key_hint", label="Download CSV")
Accepts a DataFrame or a pandas Styler (uses .data). Empty frames are skipped.
CSV (UTF-8 with BOM) opens directly in Excel — chosen over .xlsx generation
to keep page renders fast on Streamlit's free tier.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st


def df_download(obj, key_hint: str, label: str = "⬇ CSV"):
    df = getattr(obj, "data", obj)
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return
    try:
        csv = df.to_csv(index=not df.index.equals(pd.RangeIndex(len(df))))
    except Exception:
        try:
            csv = df.to_csv()
        except Exception:
            return
    st.download_button(
        label, csv.encode("utf-8-sig"),
        file_name=f"pdo_{key_hint}.csv", mime="text/csv",
        key=f"dl_{key_hint}",
    )

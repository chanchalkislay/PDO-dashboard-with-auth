"""Standardized KPI metric row wrapper."""
from __future__ import annotations

import streamlit as st


def kpi_row(n_cols: int = 5):
    """Return a list of Streamlit columns with pdo-kpi-card class wrappers."""
    cols = st.columns(n_cols)
    return cols


def metric_card(col, label: str, value: str, delta=None, *, help_text: str | None = None):
    """Render a styled metric inside a column.

    Note: st.markdown open/close div wrappers around st.metric do NOT work —
    Streamlit renders each call as a sibling element, so the div appears as an
    empty box with the metric below it.  Styling is applied via CSS targeting
    [data-testid="stMetric"] directly in dashboard.css instead.
    """
    with col:
        st.metric(label, value, delta, help=help_text)

"""Compact active-filter chips below the page header."""
from __future__ import annotations

import streamlit as st


def render_filters_banner(ctx: dict):
    """Show active sidebar filters as compact chips when any are set."""
    chips = []
    scope = ctx.get("scope")
    monthly = ctx.get("monthly")
    if scope is None or monthly is None:
        return

    if len(scope) < len(monthly):
        chips.append(f"Geo scope: {len(scope):,} rows")

    if ctx.get("multi_fy_mode"):
        chips.append("Multi-FY period")

    if not chips:
        return

    html = '<div class="pdo-filter-chips">' + "".join(
        f'<span class="pdo-chip">{c}</span>' for c in chips
    ) + "</div>"
    st.markdown(html, unsafe_allow_html=True)

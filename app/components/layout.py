"""Dashboard shell — page header and empty-state helpers."""
from __future__ import annotations

import streamlit as st

from components.filters_banner import render_filters_banner


def render_page_header(title: str, ctx: dict, *, section: str | None = None):
    """Render consistent page header with filter summary."""
    breadcrumb = f"{section} / {title}" if section else title
    st.markdown(
        f'<div class="pdo-page-header">'
        f'<p class="pdo-breadcrumb">{breadcrumb}</p>'
        f'<h1 class="pdo-page-title">{title}</h1>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.caption(ctx.get("filt_note", ""))
    render_filters_banner(ctx)


import inspect
import os
import auth

def guard_data(ctx: dict) -> bool:
    """Return False and show warning if cy_f is empty or user not logged in."""
    if "user" not in st.session_state:
        st.error("Access Denied: Please log in.")
        st.stop()
        
    user = st.session_state.user
    try:
        caller_path = inspect.stack()[1].filename
        basename = os.path.basename(caller_path)
        key = basename.split(".")[0]
        if "_" in key:
            parts = key.split("_")
            if parts[0].isdigit():
                key = "_".join(parts[1:])
        st.session_state.ingest_auth = auth.has_edit_permission(user, key)
    except Exception:
        st.session_state.ingest_auth = (user.get("role") in ("creator", "admin"))

    if ctx["cy_f"].empty:
        st.warning("No data for the selected filters / period.")
        return False
    return True

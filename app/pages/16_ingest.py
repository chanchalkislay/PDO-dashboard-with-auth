"""
Data Ingestion page — Admin only.
Auth guard enforced here (second layer) in case someone navigates directly.
"""
import streamlit as st

if not st.session_state.get("ingest_auth"):
    st.error("🔒 Access denied. Please enter the ingestion password in the sidebar.")
    st.stop()

import bootstrap  # noqa: F401 — shared CSS + DB guard
import tab_16_ingest

tab_16_ingest.render()

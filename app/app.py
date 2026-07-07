"""
Pune DO — Market Share Dashboard (v3 navigation shell)
=======================================================
Sidebar → shared context → st.navigation pages.
All logic lives in core.py and tab_XX_*.py modules.

Run:  streamlit run app.py
DB lookup order: PUNE_DO_DB env var → same folder → parent folder → cwd.
"""
from __future__ import annotations

import os
import sys

import streamlit as st

from core import (
    DB_PATH,
    _FUSE_WARNING,
    fy_list,
    load_branded,
    load_monthly,
    load_ro_master,
    load_ta_dim,
)
from context import build_context

# --------------------------------------------------------------------------- #
# Page config (must be first Streamlit call)
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Pune DO — Market Share",
    layout="wide",
    page_icon="⛽",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Global CSS
# --------------------------------------------------------------------------- #
_HERE = os.path.dirname(os.path.abspath(__file__))

# Collapsible nav section script — injected once per render.
# Wires click-toggle onto each stNavSectionHeader; persists collapsed state
# in localStorage so user preferences survive page navigation re-renders.
_COLLAPSIBLE_NAV = """
<script>
(function() {
  var LS_KEY = 'pdo_nav_collapsed';

  function getCollapsed() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}'); }
    catch(e) { return {}; }
  }
  function saveCollapsed(state) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch(e) {}
  }

  function applyState(hdr, collapsed) {
    var parent = hdr.parentElement;
    var lis = Array.from(parent.children).filter(function(c){ return c.tagName === 'LI'; });
    var icon = hdr.querySelector('[data-testid="stIconMaterial"]');
    if (collapsed) {
      hdr.classList.add('pdo-nav-collapsed');
      lis.forEach(function(li){ li.style.display = 'none'; });
      if (icon) icon.style.transform = 'rotate(-90deg)';
    } else {
      hdr.classList.remove('pdo-nav-collapsed');
      lis.forEach(function(li){ li.style.display = ''; });
      if (icon) icon.style.transform = 'rotate(0deg)';
    }
  }

  function initCollapsible() {
    var state = getCollapsed();
    var headers = document.querySelectorAll('[data-testid="stNavSectionHeader"]');
    headers.forEach(function(hdr) {
      if (hdr.dataset.pdoInit) {
        // Already initialised — just re-apply stored state (re-render may have reset display)
        var key = hdr.textContent.replace('expand_more','').trim();
        applyState(hdr, !!state[key]);
        return;
      }
      hdr.dataset.pdoInit = '1';
      var key = hdr.textContent.replace('expand_more','').trim();
      // Apply stored state on first load
      applyState(hdr, !!state[key]);

      hdr.addEventListener('click', function() {
        var k = hdr.textContent.replace('expand_more','').trim();
        var s = getCollapsed();
        s[k] = !s[k];
        saveCollapsed(s);
        applyState(hdr, s[k]);
      });
    });
  }

  // Run immediately, then watch sidebar for Streamlit re-renders
  setTimeout(initCollapsible, 100);
  var mo = new MutationObserver(function() { initCollapsible(); });
  function attachObserver() {
    var sb = document.querySelector('[data-testid="stSidebar"]');
    if (sb) { mo.observe(sb, { childList: true, subtree: true }); }
    else { setTimeout(attachObserver, 200); }
  }
  attachObserver();
})();
</script>
"""
_CSS_PATH = os.path.join(_HERE, "assets", "dashboard.css")
if os.path.exists(_CSS_PATH):
    with open(_CSS_PATH, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.markdown(_COLLAPSIBLE_NAV, unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# DB guard
# --------------------------------------------------------------------------- #
if not os.path.exists(DB_PATH):
    st.error(
        f"Database not found at: {DB_PATH}\n\n"
        "Place pune_do.db next to app.py or set the PUNE_DO_DB env var."
    )
    st.stop()

# --------------------------------------------------------------------------- #
# Authentication Gate & DB Init
# --------------------------------------------------------------------------- #
import auth
auth.init_db()

if "user" not in st.session_state:
    st.markdown("""
        <div style="text-align: center; margin-top: 50px;">
            <span style="font-size: 50px;">⛽</span>
            <h1 style="color: #F47920; font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 700; margin-bottom: 5px;">Pune DO Dashboard</h1>
            <p style="color: #94a3b8; font-size: 14px;">Enter credentials to access the Market Share Analytics platform</p>
        </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.form("login_form", border=True):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
            
            if submitted:
                user = auth.authenticate_user(username, password)
                if user:
                    st.session_state.user = user
                    st.success("Access Granted! Loading dashboard...")
                    st.rerun()
                else:
                    st.error("Invalid Username or Password.")
    st.stop()

# --------------------------------------------------------------------------- #
# Data load (cached — runs once per session)
# --------------------------------------------------------------------------- #
monthly = load_monthly()
ro_master = load_ro_master()
ta_dim = load_ta_dim()
branded = load_branded()
fys = fy_list()
TA_NAME = ta_dim.set_index("ta_code")["ta_name_canonical"]

# --------------------------------------------------------------------------- #
# Sidebar + shared context
# --------------------------------------------------------------------------- #
build_context(monthly, ro_master, ta_dim, branded, fys, TA_NAME)

# --------------------------------------------------------------------------- #
# FUSE mount safety warning
# --------------------------------------------------------------------------- #
if _FUSE_WARNING:
    st.sidebar.warning(
        "⚠️ **DB on FUSE mount detected.**\n\n"
        "The database file appears to be on a USB/network drive. "
        "Running the dashboard directly from a FUSE-mounted volume risks silent SQLite corruption. "
        "Copy the entire project folder to your local drive (Documents / Desktop) and run from there.\n\n"
        "To copy the DB safely: `python3 scripts/copy_db.py`"
    )

# --------------------------------------------------------------------------- #
# Account Status & Log Out
# --------------------------------------------------------------------------- #
user = st.session_state.user
with st.sidebar.expander(f"👤 Account: {user['username']}", expanded=True):
    st.markdown(f"**Role**: `{user['role'].upper()}`")
    if user.get("sales_area_code"):
        st.markdown(f"**Sales Area**: `{user['sales_area_code']}`")
    if user.get("ro_code"):
        st.markdown(f"**RO Code**: `{user['ro_code']}`")
        
    st.markdown("---")
    if st.checkbox("🔑 Change Password", key="sb_chg_pwd_chk"):
        with st.form("sb_chg_pwd_form", border=False):
            old_p = st.text_input("Current Password", type="password", key="sb_old_pwd")
            new_p = st.text_input("New Password", type="password", key="sb_new_pwd")
            confirm_p = st.text_input("Confirm Password", type="password", key="sb_conf_pwd")
            if st.form_submit_button("Update Password", use_container_width=True):
                if new_p != confirm_p:
                    st.error("Passwords do not match.")
                elif len(new_p) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    conn = auth.get_db_connection()
                    stored_h = conn.execute("SELECT password_hash FROM app_users WHERE username=?", (user["username"],)).fetchone()
                    if stored_h and auth.verify_password(old_p, stored_h[0]):
                        h_pass = auth.hash_password(new_p)
                        conn.execute("UPDATE app_users SET password_hash=? WHERE username=?", (h_pass, user["username"]))
                        conn.commit()
                        st.success("Password updated successfully!")
                    else:
                        st.error("Incorrect current password.")
                    conn.close()
                    
    st.markdown("---")
    if st.button("Log Out", key="sb_logout", use_container_width=True):
        del st.session_state.user
        if "_pdo_ctx" in st.session_state:
            del st.session_state["_pdo_ctx"]
        st.rerun()

# --------------------------------------------------------------------------- #
# Navigation — dynamically generated based on user authorizations
# --------------------------------------------------------------------------- #
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

nav_pages = auth.get_authorized_navigation_pages(st.session_state.user)
pg = st.navigation(nav_pages)
pg.run()

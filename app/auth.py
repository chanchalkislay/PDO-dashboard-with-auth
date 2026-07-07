import sqlite3
import hashlib
import uuid
import os
import streamlit as st
from typing import Optional, Dict, Any, List

# Locate the SQLite database relative to this script
_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "pune_do.db")

PAGES_REGISTRY = {
    "overview": {"title": "Overview", "icon": "📊", "file": "pages/01_overview.py", "group": "Executive"},
    "market_share": {"title": "Market Share", "icon": "📈", "file": "pages/02_market_share.py", "group": "Executive"},
    "trend": {"title": "Trend Analysis Historical", "icon": "📉", "file": "pages/07_trend.py", "group": "Executive"},
    "performance": {"title": "Performance (CY vs LY)", "icon": "⚡", "file": "pages/08_performance.py", "group": "Executive"},
    
    "market_participation": {"title": "Market Participation", "icon": "🌐", "file": "pages/03_market_participation.py", "group": "Network"},
    "ta_analysis": {"title": "Trading-Area Analysis", "icon": "🗺️", "file": "pages/04_ta_analysis.py", "group": "Network"},
    "ta_rankings": {"title": "TA Rankings", "icon": "🏆", "file": "pages/06_ta_rankings.py", "group": "Network"},
    "ro_benchmarking": {"title": "RO Benchmarking", "icon": "🎯", "file": "pages/15_ro_benchmarking.py", "group": "Network"},
    
    "coco": {"title": "COCO Management", "icon": "🏪", "file": "pages/17_coco.py", "group": "Programmes"},
    "swagat": {"title": "Swagat Monitoring", "icon": "🛣️", "file": "pages/18_swagat.py", "group": "Programmes"},
    
    "remm": {"title": "REMM — Rent & Lease", "icon": "🏠", "file": "pages/21_remm.py", "group": "Assets & Infra"},
    "commissioning": {"title": "Commissioning Pipeline", "icon": "🏗️", "file": "pages/22_commissioning.py", "group": "Assets & Infra"},
    "alt_fuel": {"title": "Alt Fuels (CNG/CBG)", "icon": "⚡", "file": "pages/24_alt_fuel.py", "group": "Assets & Infra"},
    
    "ta_profile": {"title": "TA Profile (PPT)", "icon": "📋", "file": "pages/05_ta_profile.py", "group": "Trading Area"},
    
    "notional": {"title": "Notional Loss/Gain", "icon": "💹", "file": "pages/09_notional.py", "group": "Operations"},
    "nil_selling": {"title": "Nil Selling", "icon": "🚫", "file": "pages/10_nil_selling.py", "group": "Operations"},
    "sales_volumes": {"title": "Sales Volumes", "icon": "📦", "file": "pages/11_sales_volumes.py", "group": "Operations"},
    "branded": {"title": "Branded", "icon": "⭐", "file": "pages/12_branded.py", "group": "Operations"},
    "xtrapower": {"title": "XtraPower", "icon": "🔋", "file": "pages/13_xtrapower.py", "group": "Operations"},
    "lube": {"title": "Lube Sales", "icon": "🛢️", "file": "pages/23_lube.py", "group": "Operations"},
    
    "finder": {"title": "Finder & Reports", "icon": "🔍", "file": "pages/14_finder.py", "group": "Tools"},
    
    "ingest": {"title": "Data Ingestion", "icon": "📥", "file": "pages/16_ingest.py", "group": "Admin"},
    "user_management": {"title": "User Management", "icon": "👥", "file": "pages/30_user_management.py", "group": "Admin"}
}

def hash_password(password: str, salt: Optional[str] = None) -> str:
    if salt is None:
        salt = uuid.uuid4().hex
    hashed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return f"{salt}:{hashed}"

def verify_password(password: str, stored: str) -> bool:
    try:
        salt, hashed = stored.split(":")
        return hash_password(password, salt).split(":")[1] == hashed
    except Exception:
        return False

def init_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                sales_area_code TEXT,
                ro_code TEXT,
                authorized_tabs TEXT
            )
        """)
        # Check if creator superuser chanchalkislay exists
        res = conn.execute("SELECT username FROM app_users WHERE role='creator'").fetchone()
        if not res:
            # Seed creator superuser
            # Default password is SuperAdmin123!
            h = hash_password("SuperAdmin123!")
            conn.execute("""
                INSERT INTO app_users (username, password_hash, role, authorized_tabs)
                VALUES ('chanchalkislay', ?, 'creator', 'all')
            """, (h,))
            conn.commit()
    finally:
        conn.close()

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT username, password_hash, role, sales_area_code, ro_code, authorized_tabs FROM app_users WHERE username=?",
            (username.strip(),)
        ).fetchone()
        if row and verify_password(password, row[1]):
            return {
                "username": row[0],
                "role": row[2],
                "sales_area_code": row[3],
                "ro_code": row[4],
                "authorized_tabs": row[5]
            }
    finally:
        conn.close()
    return None

def is_page_authorized(user: Dict[str, Any], page_key: str) -> bool:
    role = user.get("role")
    if role in ("creator", "admin"):
        return True
    
    # Authorized tabs check
    auth_tabs_str = user.get("authorized_tabs", "")
    if auth_tabs_str == "all":
        return True
        
    auth_tabs = [t.strip() for t in auth_tabs_str.split(",") if t.strip()]
    if page_key in auth_tabs:
        return True
        
    # Default roles check
    if role == "do_manager":
        # DO Managers see everything by default except admin/user_management
        return page_key not in ("ingest", "user_management")
        
    if role == "field_officer":
        # Field Officers default view rights
        return page_key in ("overview", "market_share", "performance", "ta_profile", "nil_selling", "sales_volumes", "finder")
        
    if role == "sr_officer":
        # Senior Officers default view rights
        return page_key in ("overview", "market_share", "performance", "ta_profile", "finder")
        
    if role == "dealer":
        # Dealers view rights strictly restricted
        return page_key in ("overview", "market_share", "performance", "ta_profile", "ro_benchmarking")
        
    return False

def get_authorized_navigation_pages(user: Dict[str, Any]) -> Dict[str, List[st.Page]]:
    nav_dict = {}
    
    for key, pinfo in PAGES_REGISTRY.items():
        if is_page_authorized(user, key):
            group = pinfo["group"]
            if group not in nav_dict:
                nav_dict[group] = []
            
            page_path = os.path.join(_HERE, pinfo["file"])
            nav_dict[group].append(
                st.Page(page_path, title=pinfo["title"], icon=pinfo["icon"])
            )
            
    return nav_dict

def has_edit_permission(user: Dict[str, Any], page_key: str) -> bool:
    role = user.get("role")
    if role in ("creator", "admin"):
        return True
    if role == "dealer":
        return False
        
    auth_tabs_str = user.get("authorized_tabs", "")
    if auth_tabs_str == "all":
        return True
        
    auth_tabs = [t.strip() for t in auth_tabs_str.split(",") if t.strip()]
    return page_key in auth_tabs


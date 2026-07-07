import streamlit as st
import bootstrap  # noqa: F401
import auth
import core
import pandas as pd

# Check if logged in and has Creator or Admin rights
if "user" not in st.session_state:
    st.warning("Please log in to access this page.")
    st.stop()

cur_user = st.session_state.user
if cur_user["role"] not in ("creator", "admin"):
    st.error("Access Denied: You do not have permission to view this page.")
    st.stop()

st.title("👥 User Management")
st.markdown("Add, edit, or delete user accounts and define their roles, sales areas, and page permissions.")

auth.init_db()
conn = auth.get_db_connection()

# Load references for RSA and RO selection
ro_master = core.load_ro_master()
rsa_df = ro_master[["rsa_code", "rsa_name"]].dropna().drop_duplicates().sort_values("rsa_name")
rsa_options = {f"{r.rsa_name} ({r.rsa_code})": r.rsa_code for r in rsa_df.itertuples()}

ro_df = ro_master[["sap_code", "ro_name"]].dropna().drop_duplicates().sort_values("ro_name")
ro_options = {f"{r.ro_name} ({r.sap_code})": str(r.sap_code) for r in ro_df.itertuples()}

# Available roles
ROLES = {
    "admin": "Admin (Full Data View, Edits & Users Management)",
    "do_manager": "DO Manager (Full Data View, Tab-restricted Edits)",
    "field_officer": "Field Officer (Restricted to Sales Area, Limited Edits)",
    "sr_officer": "Senior Officer (Restricted to Sales Area, View Only)",
    "dealer": "Dealer (Restricted to specific Retail Outlet & Sales Area, View Only)"
}

# Sub-tab structure
t_list, t_create, t_edit = st.tabs(["📋 Users List", "➕ Create User", "✏️ Edit / Delete User"])

with t_list:
    st.subheader("Active User Accounts")
    users = conn.execute(
        "SELECT username, role, sales_area_code, ro_code, authorized_tabs FROM app_users"
    ).fetchall()
    
    if users:
        df_users = pd.DataFrame(users, columns=["Username", "Role", "Sales Area (RSA)", "Retail Outlet (RO)", "Authorized Tabs"])
        df_users["Sales Area (RSA)"] = df_users["Sales Area (RSA)"].apply(lambda x: x if x else "All")
        df_users["Retail Outlet (RO)"] = df_users["Retail Outlet (RO)"].apply(lambda x: x if x else "All")
        st.dataframe(df_users, use_container_width=True, hide_index=True)
    else:
        st.info("No users registered.")

with t_create:
    st.subheader("Register a New User Account")
    new_username = st.text_input("Username", key="new_username_input").strip()
    new_password = st.text_input("Password", type="password", key="new_password_input")
    new_role = st.selectbox("Role", list(ROLES.keys()), format_func=lambda x: ROLES[x], key="new_role_input")
    
    st.markdown("---")
    st.markdown("##### Jurisdictions / Filters Lock")
    
    new_rsa = []
    new_ro = []
    if new_role == "dealer":
        new_rsa = st.multiselect("Sales Area (RSA Code)", list(rsa_options.keys()), key="new_rsa_input", help="Leave blank for All Sales Areas")
        new_ro = st.multiselect("Retail Outlet (RO SAP Code)", list(ro_options.keys()), key="new_ro_input", help="Leave blank for All Outlets")
    elif new_role in ("field_officer", "sr_officer"):
        new_rsa = st.multiselect("Sales Area (RSA Code)", list(rsa_options.keys()), key="new_rsa_input", help="Leave blank for All Sales Areas")
        
    st.markdown("---")
    st.markdown("##### Dynamic Page Permissions")
    
    if new_role == "do_manager":
        tabs_all_label = "Grant full edit access to all tabs/pages"
        multiselect_label = "Edit-Authorized Tabs (Only selected tabs can be modified)"
    else:
        tabs_all_label = "Grant default view access to all role tabs/pages"
        multiselect_label = "View-Authorized Tabs (Restrict view to only selected tabs)"
        
    new_tabs_all = st.checkbox(tabs_all_label, value=True, key="new_tabs_all_chk")
    
    selected_pages = []
    if not new_tabs_all:
        selected_pages = st.multiselect(
            multiselect_label,
            list(auth.PAGES_REGISTRY.keys()),
            format_func=lambda x: f"{auth.PAGES_REGISTRY[x]['icon']} {auth.PAGES_REGISTRY[x]['title']}",
            key="new_tabs_sel"
        )
        
    if st.button("Register User", key="create_user_btn"):
        if not new_username or not new_password:
            st.error("Please fill in both username and password.")
        else:
            dup = conn.execute("SELECT username FROM app_users WHERE username=?", (new_username,)).fetchone()
            if dup:
                st.error(f"Username '{new_username}' already exists.")
            else:
                h_pass = auth.hash_password(new_password)
                tabs_val = "all" if new_tabs_all else ",".join(selected_pages)
                rsa_code = ",".join(rsa_options[l] for l in new_rsa) if new_rsa else ""
                ro_code = ",".join(ro_options[l] for l in new_ro) if new_ro else ""
                
                conn.execute("""
                    INSERT INTO app_users (username, password_hash, role, sales_area_code, ro_code, authorized_tabs)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (new_username, h_pass, new_role, rsa_code, ro_code, tabs_val))
                conn.commit()
                st.success(f"User '{new_username}' registered successfully!")
                st.rerun()

with t_edit:
    st.subheader("Edit or Delete User Accounts")
    
    all_users = [r[0] for r in conn.execute("SELECT username FROM app_users").fetchall()]
    if cur_user["role"] == "admin" and "chanchalkislay" in all_users:
        all_users.remove("chanchalkislay")
        
    if not all_users:
        st.info("No editable users found.")
    else:
        target_username = st.selectbox("Select User to Edit/Delete", all_users, key="edit_target_user")
        
        user_row = conn.execute(
            "SELECT role, sales_area_code, ro_code, authorized_tabs FROM app_users WHERE username=?",
            (target_username,)
        ).fetchone()
        
        if user_row:
            u_role, u_rsa, u_ro, u_tabs = user_row
            
            # Map values back for UI defaults
            default_rsa_labels = []
            if u_rsa:
                rsa_codes_set = set(u_rsa.split(","))
                default_rsa_labels = [lbl for lbl, code in rsa_options.items() if code in rsa_codes_set]
                
            default_ro_labels = []
            if u_ro:
                ro_codes_set = set(u_ro.split(","))
                default_ro_labels = [lbl for lbl, code in ro_options.items() if code in ro_codes_set]
                        
            role_options_list = list(ROLES.keys())
            if target_username == "chanchalkislay":
                role_options_list = ["creator"]
                
            edit_role = st.selectbox("Modify Role", role_options_list, 
                                     index=role_options_list.index(u_role) if u_role in role_options_list else 0,
                                     key="edit_role_input")
            
            edit_password = st.text_input("Change Password (leave blank to keep current)", type="password", key="edit_password_input")
            
            st.markdown("---")
            st.markdown("##### Jurisdictions / Filters Lock")
            
            edit_rsa = []
            edit_ro = []
            if edit_role == "dealer":
                edit_rsa = st.multiselect("Sales Area (RSA Code)", list(rsa_options.keys()), default=default_rsa_labels, key="edit_rsa_input", help="Leave blank for All Sales Areas")
                edit_ro = st.multiselect("Retail Outlet (RO SAP Code)", list(ro_options.keys()), default=default_ro_labels, key="edit_ro_input", help="Leave blank for All Outlets")
            elif edit_role in ("field_officer", "sr_officer"):
                edit_rsa = st.multiselect("Sales Area (RSA Code)", list(rsa_options.keys()), default=default_rsa_labels, key="edit_rsa_input", help="Leave blank for All Sales Areas")
            
            st.markdown("---")
            st.markdown("##### Dynamic Page Permissions")
            
            if edit_role == "do_manager":
                tabs_all_label = "Grant full edit access to all tabs/pages"
                multiselect_label = "Edit-Authorized Tabs (Only selected tabs can be modified)"
            else:
                tabs_all_label = "Grant default view access to all role tabs/pages"
                multiselect_label = "View-Authorized Tabs (Restrict view to only selected tabs)"
                
            edit_tabs_all = st.checkbox(tabs_all_label, value=(u_tabs == "all"), key="edit_tabs_all_chk")
            
            edit_pages = []
            if not edit_tabs_all:
                default_sel_tabs = []
                if u_tabs and u_tabs != "all":
                    default_sel_tabs = [t.strip() for t in u_tabs.split(",") if t.strip()]
                    
                edit_pages = st.multiselect(
                    multiselect_label,
                    list(auth.PAGES_REGISTRY.keys()),
                    default=[t for t in default_sel_tabs if t in auth.PAGES_REGISTRY],
                    format_func=lambda x: f"{auth.PAGES_REGISTRY[x]['icon']} {auth.PAGES_REGISTRY[x]['title']}",
                    key="edit_tabs_sel"
                )
                
            c_update, c_delete = st.columns(2)
            
            with c_update:
                if st.button("💾 Save Changes", use_container_width=True):
                    rsa_val = ",".join(rsa_options[l] for l in edit_rsa) if edit_rsa else ""
                    ro_val = ",".join(ro_options[l] for l in edit_ro) if edit_ro else ""
                    
                    critical_edit = (edit_role != u_role or rsa_val != (u_rsa or "") or ro_val != (u_ro or ""))
                    if critical_edit:
                        st.session_state["pending_edit"] = {
                            "username": target_username,
                            "role": edit_role,
                            "password": edit_password,
                            "rsa": rsa_val,
                            "ro": ro_val,
                            "tabs": "all" if edit_tabs_all else ",".join(edit_pages)
                        }
                        st.rerun()
                    else:
                        tabs_val = "all" if edit_tabs_all else ",".join(edit_pages)
                        
                        if edit_password:
                            h_pass = auth.hash_password(edit_password)
                            conn.execute("""
                                UPDATE app_users 
                                SET password_hash=?, role=?, sales_area_code=?, ro_code=?, authorized_tabs=?
                                WHERE username=?
                            """, (h_pass, edit_role, rsa_val, ro_val, tabs_val, target_username))
                        else:
                            conn.execute("""
                                UPDATE app_users 
                                SET role=?, sales_area_code=?, ro_code=?, authorized_tabs=?
                                WHERE username=?
                            """, (edit_role, rsa_val, ro_val, tabs_val, target_username))
                        conn.commit()
                        st.success(f"User '{target_username}' updated successfully!")
                        st.rerun()
                        
            with c_delete:
                if target_username == "chanchalkislay":
                    st.button("❌ Delete User", disabled=True, use_container_width=True, help="Super User cannot be deleted.")
                else:
                    if st.button("❌ Delete User", use_container_width=True):
                        st.session_state["pending_delete"] = target_username
                        st.rerun()

            if "pending_edit" in st.session_state:
                pe = st.session_state["pending_edit"]
                st.warning(f"⚠️ **CONFIRM CRITICAL EDIT**: You are changing the role or jurisdiction for '{pe['username']}'.")
                c1, c2 = st.columns(2)
                if c1.button("Confirm Edit", key="confirm_pe_btn"):
                    tabs_val = pe["tabs"]
                    rsa_code = pe["rsa"]
                    ro_code = pe["ro"]
                    if pe["password"]:
                        h_pass = auth.hash_password(pe["password"])
                        conn.execute("""
                            UPDATE app_users 
                            SET password_hash=?, role=?, sales_area_code=?, ro_code=?, authorized_tabs=?
                            WHERE username=?
                        """, (h_pass, pe["role"], rsa_code, ro_code, tabs_val, pe["username"]))
                    else:
                        conn.execute("""
                            UPDATE app_users 
                            SET role=?, sales_area_code=?, ro_code=?, authorized_tabs=?
                            WHERE username=?
                        """, (pe["role"], rsa_code, ro_code, tabs_val, pe["username"]))
                    conn.commit()
                    del st.session_state["pending_edit"]
                    st.success("User updated successfully!")
                    st.rerun()
                if c2.button("Cancel", key="cancel_pe_btn"):
                    del st.session_state["pending_edit"]
                    st.rerun()
                    
            if "pending_delete" in st.session_state:
                pd_user = st.session_state["pending_delete"]
                st.error(f"🚨 **CONFIRM DELETION**: Are you absolutely sure you want to delete user '{pd_user}'? This action cannot be undone.")
                c1, c2 = st.columns(2)
                if c1.button("Yes, Delete User", key="confirm_pd_btn"):
                    conn.execute("DELETE FROM app_users WHERE username=?", (pd_user,))
                    conn.commit()
                    del st.session_state["pending_delete"]
                    st.success(f"User '{pd_user}' deleted successfully!")
                    st.rerun()
                if c2.button("Cancel Deletion", key="cancel_pd_btn"):
                    del st.session_state["pending_delete"]
                    st.rerun()

conn.close()

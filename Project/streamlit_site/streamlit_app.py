import streamlit as st
st.set_page_config(layout="wide")

from imports import *

# --- PAGE SETUP ---
signin_page = st.Page(
    page="views/signin.py",
    title="Staff Sign In",
    icon="👤",
    default=True,
)

pdf_import_page = st.Page(
    page="views/manual_import.py",
    title="PDF Manual Import",
    icon="📥",
)

pdf_manage_page = st.Page(
    page="views/manage_database.py",
    title="Manage Bikes",
    icon="🛢️",
)

acc_manage_page = st.Page(
    page="views/manage_accounts.py",
    title="Manage Accounts",
    icon="👤",
)

dashboard_1_page = st.Page(
    page="views/rfq_dashboard.py",
    title="RFQ Dashboard",
    icon="📊",
)

dashbaord_2_page = st.Page(
    page="views/inventory_dashboard.py",
    title="Inventory Dashboard",
    icon="📊",
)

# --- DEFAULT to guest if no user_type in session ---
valid_user_types = {"guest", "staff", "admin"}

# --- Define page groups ---
guest_pages = {
    "User": [signin_page],
}
staff_pages = {
    "Staff": [pdf_import_page, pdf_manage_page],
}
dashboard_pages = {
    "Dashboards": [dashboard_1_page, dashbaord_2_page],
}
admin_pages = {
    "Admin": [acc_manage_page],
}

if "user_type" not in st.session_state:
    cookie_user_type = cookies.get("user_type", "").lower().strip()
    cookie_user_name = cookies.get("user_name", "").strip()

    if cookie_user_type in valid_user_types:
        st.session_state.user_type = cookie_user_type
        st.session_state.user_name = cookie_user_name
    else:
        st.session_state.user_type = "guest"
        st.session_state.user_name = ""

# Build allowed pages dynamically
accessible_pages = {}

if st.session_state.user_type == "guest":
    accessible_pages.update(guest_pages)

elif st.session_state.user_type == "staff":
    accessible_pages.update(staff_pages)
    accessible_pages.update(dashboard_pages)

elif st.session_state.user_type == "admin":
    accessible_pages.update(staff_pages)
    accessible_pages.update(dashboard_pages)
    accessible_pages.update(admin_pages)

# --- Log Out for authenticated users ---
if st.session_state.user_type != "guest":
    with st.sidebar:
        if st.button("🔓 Log Out"):
            cookies["user_type"] = "guest"
            cookies["user_name"] = "guest"
            cookies.save()
            st.session_state.clear()
            st.success("Logged out.")
            st.rerun()

with st.sidebar:
    st.markdown("### Current Session State")
    st.json(st.session_state)

# --- Run navigation ---
pg = st.navigation(accessible_pages)
pg.run()
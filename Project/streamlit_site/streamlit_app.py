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
    page="views/logs_dashboard.py",
    title="Logs Dashboard",
    icon="📊",
)

dashboard_2_page = st.Page(
    page="views/inventory_dashboard.py",
    title="inventory Dashboard",
    icon="📊",
)

# Handle post-login or post-logout rerun
if st.session_state.get("just_logged_in") or st.session_state.get("just_logged_out"):
    st.session_state.pop("just_logged_in", None)
    st.session_state.pop("just_logged_out", None)
    st.rerun()

# --- DEFAULT to guest if no user_type in session ---
valid_user_types = {"guest", "staff", "admin"}

# --- Define page groups ---
guest_pages = {
    "User": [signin_page],
}
staff_pages = {
    "Bike Management": [pdf_import_page, pdf_manage_page],
}
dashboard_pages = {
    "Dashboards": [dashboard_2_page],
}
admin_pages = {
    "Admin": [acc_manage_page, dashboard_1_page],
}

# --- DEFAULT to guest unless valid account_id found ---
if "account_id" not in st.session_state:
    if cookies.ready():
        cookie_id = cookies.get("account_id")
        if cookie_id:
            st.session_state.account_id = int(cookie_id)

if "account_id" in st.session_state:
    # Fetch user info from DB
    metadata = MetaData()
    metadata.reflect(bind=engine)
    accounts = metadata.tables.get("accounts")

    with engine.connect() as conn:
        stmt = select(accounts).where(accounts.c.account_id == st.session_state.account_id)
        result = conn.execute(stmt).fetchone()

        if result:
            row = result._mapping
            st.session_state.user_name = row["staff_name"]
            st.session_state.user_type = row["role"]
        else:
            # Account no longer exists, fallback to guest
            st.session_state.clear()
            st.session_state.user_type = "guest"
            st.session_state.user_name = ""
            cookies.clear()
else:
    st.session_state.user_type = "guest"
    st.session_state.user_name = ""

# Build allowed pages dynamically
accessible_pages = {}

if st.session_state.user_type == "guest":
    accessible_pages.update(guest_pages)

elif st.session_state.user_type == "staff":
    accessible_pages.update(dashboard_pages)
    accessible_pages.update(staff_pages)

elif st.session_state.user_type == "admin":
    accessible_pages.update(dashboard_pages)
    accessible_pages.update(staff_pages)
    accessible_pages.update(admin_pages)

# --- Log Out for authenticated users ---
if st.session_state.user_type != "guest":
    with st.sidebar:
        if st.button("🔓 Log Out"):
            # Ensure account_id cookie is deleted properly
            cookies["account_id"] = ""
            cookies.set_cookie_with_expiry("account_id", "", datetime.utcnow())  # expired
            cookies.save()

            st.session_state.clear()
            st.rerun()

# with st.sidebar:
#     st.markdown("### Current Session State")
#     st.json(st.session_state)

# --- Run navigation ---
pg = st.navigation(accessible_pages)
pg.run()
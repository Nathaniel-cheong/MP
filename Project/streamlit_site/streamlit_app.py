import streamlit as st
st.set_page_config(layout="wide")

from imports import *

# Logs user out after a day since last log in
if "login_timestamp" in cookies:
    login_time = datetime.fromisoformat(cookies["login_timestamp"])
    if datetime.now() - login_time < timedelta(days=1):
        cookies["login_timestamp"] = (datetime.now() - timedelta(days=2)).isoformat()
        cookies.save()

# --- PAGE SETUP ---
signin_page = st.Page(
    page="views/signin.py",
    title="Staff Sign In",
    icon="👤",
    default=True,
)

pdf_import_page = st.Page(
    page="views/manual_import.py",
    title="PDF Import",
    icon="📥",
)

pdf_manage_page = st.Page(
    page="views/manage_database.py",
    title="Manage Database",
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

pdf_dusbin_page = st.Page(
    page="views/pdf_dustbin.py",
    title="PDF Archives",
    icon="🗑️",
)

# Handle post-login or post-logout rerun
if st.session_state.get("just_logged_in") or st.session_state.get("just_logged_out"):
    st.session_state.pop("just_logged_in", None)
    st.session_state.pop("just_logged_out", None)
    st.rerun()

# User types
valid_user_types = {"guest", "staff", "admin"}

# Defining page groups
guest_pages = {
    "User": [signin_page],
}
homepage = {
    "": [dashboard_2_page],
}
staff_pages = {
    "Bike Management": [pdf_import_page, pdf_manage_page, pdf_dusbin_page],
}
admin_pages = {
    "Admin": [acc_manage_page, dashboard_1_page],
}

# DEFAULT to guest unless valid account_id found
if "account_id" not in st.session_state:
    if cookies.ready():
        cookie_id = cookies.get("account_id")
        if cookie_id:
            st.session_state.account_id = int(cookie_id)

if "account_id" in st.session_state:
    # reflect the metadata
    metadata = MetaData()
    metadata.reflect(bind=engine)
    accounts = metadata.tables.get("accounts")

    with engine.connect() as conn:
        stmt = select(accounts).where(accounts.c.account_id == st.session_state.account_id)
        result = conn.execute(stmt).fetchone()

        # If valid account_id found
        if result:
            row = result._mapping
            st.session_state.user_name = row["staff_name"]
            st.session_state.user_type = row["role"]
        else:
            # Error handling for invalid account_id > fallback to guest
            st.session_state.clear()
            st.session_state.user_type = "guest"
            st.session_state.user_name = ""
            cookies.clear()
else:
    st.session_state.user_type = "guest"
    st.session_state.user_name = ""

# Pages for authenticated users
accessible_pages = {}

if st.session_state.user_type == "guest":
    # Only able to view login page
    accessible_pages.update(guest_pages)

elif st.session_state.user_type == "staff":
    # Able to view homepage and staff pages
    accessible_pages.update(homepage)
    accessible_pages.update(staff_pages)

elif st.session_state.user_type == "admin":
    # Able to view all pages
    accessible_pages.update(homepage)
    accessible_pages.update(staff_pages)
    accessible_pages.update(admin_pages)

# Log out button
if st.session_state.user_type != "guest":
    with st.sidebar:
        if st.button("🔓 Log Out"):
            # Reset cookies
            cookies["account_id"] = ""
            cookies.set_cookie_with_expiry("account_id", "", datetime.utcnow())  # expired
            cookies.save()

            st.session_state.clear()
            st.rerun()

# For session state debugging
# with st.sidebar:
#     st.markdown("### Current Session State")
#     st.json(st.session_state)

# Run navigation bar for accessible pages
pg = st.navigation(accessible_pages)
pg.run()
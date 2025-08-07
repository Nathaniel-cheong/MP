import streamlit as st
st.set_page_config(layout="wide")

from imports import *

# Intitalize default session states (Guest by default)
st.session_state.setdefault("user_type", "guest")
st.session_state.setdefault("user_name", "")

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

# If valid account detected
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

            # If account deactived
            if not row["is_enabled"]:
                # Treat user as guest
                cookies.set_cookie_with_expiry("account_id", "", datetime.utcnow())  # Expire cookie
                cookies.save()
                st.session_state["user_type"] = "guest"
                st.session_state["user_name"] = ""
                st.session_state.pop("account_id", None)
                st.toast("Your account has been deactivated.", icon="🔒")
                time.sleep(2)
                st.rerun()

            # If Valid & active account
            st.session_state.user_name = row["staff_name"]
            st.session_state.user_type = row["role"]
        else:
            # Error handling for invalid account_id > fallback to guest
            st.session_state.clear()
            st.session_state.user_type = "guest"
            st.session_state.user_name = ""
            cookies.clear()
else:
    # Error handling for invalid account_id > fallback to guest
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
with st.sidebar:
    if st.button("Clear Cache"):
        st.cache_data.clear()
#     st.markdown("### Current Session State")
#     st.json(st.session_state)

# Run navigation bar for accessible pages
pg = st.navigation(accessible_pages)
pg.run()
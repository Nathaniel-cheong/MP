from imports import *

st.set_page_config(layout="wide")

# --- PAGE SETUP ---
signin_page = st.Page(
    page="views/signin.py",
    title="Staff Sign In",
    icon="👤",
)

home_page = st.Page(
    page="views/homepage.py",
    title="Homepage",
    icon="🏠",
    default=True,
)

# checkout_page = st.Page(
#     page="views/checkout.py",
#     title="Checkout",
#     icon="🛒",
# )

manual_import_page = st.Page(
    page="views/manual_import.py",
    title="Import PDF Manuals here",
    icon="📥",
)

db_manage_page = st.Page(
    page="views/manage_database.py",
    title="Manage Database",
    icon="🛢️",
)

db_manage_page = st.Page(
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
    page="views/rfq_dashboard.py",
    title="RFQ Dashboard",
    icon="📊",
)

dashbaord_2_page = st.Page(
    page="views/inventory_dashboard.py",
    title="Inventory Dashboard",
    icon="📊",
)

test_page = st.Page(
    page="views/test.py",
    title="Testing Page",
)

# --- DEFAULT to guest if no user_type in session ---
if "user_type" not in st.session_state:
    cookie_user_type = cookies.get("user_type")
    if cookie_user_type:
        st.session_state.user_type = cookie_user_type
    else:
        st.session_state.user_type = "guest"

# --- BASED ON ROLE ---
if st.session_state.user_type == "guest":
    pg = st.navigation({
        "User": [home_page, signin_page],
    })

else:
    if st.session_state.user_type == "staff":
        pg = st.navigation({
            "User": [home_page, signin_page],
            "Staff": [manual_import_page, test_page, db_manage_page],
            # "Dashboards": [dashboard_1_page, dashbaord_2_page],
        })

    elif st.session_state.user_type == "admin":
        pg = st.navigation({
            "User": [home_page, signin_page],
            "Staff": [manual_import_page, db_manage_page, test_page],
            "Admin": [acc_manage_page],
            #"Dashboards": [dashboard_1_page, dashbaord_2_page],
        })
    with st.sidebar:
        if st.button("🔓 Log Out"):
            cookies.set("user_type", "guest")
            st.session_state.user_type = "guest"
            st.rerun()

with st.sidebar:
    st.markdown("### Current Session State")
    st.json(st.session_state)

# --- Run navigation ---
pg.run()
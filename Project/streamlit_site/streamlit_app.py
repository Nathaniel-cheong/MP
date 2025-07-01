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

admin_1_page = st.Page(
    page="views/manual_import.py",
    title="Import PDF Manuals here",
    icon="📥",
)

admin_2_page = st.Page(
    page="views/view_images.py",
    title="Image Viewer",
    icon="🖼️",
)

admin_3_page = st.Page(
    page="views/manage_database.py",
    title="Manage Database",
    icon="🛢️",
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

elif st.session_state.user_type == "staff":
    pg = st.navigation({
        "User": [home_page, signin_page],
        "Staff": [admin_1_page, test_page, admin_3_page],
        # "Dashboards": [dashboard_1_page, dashbaord_2_page],
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
from imports import *

# Icons: https://emojidb.org/import-emojis

# --- PAGE SETUP ---
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

# --- NAVGIATION SETUP [WITHOUT SECTIONS] ---
#pg = st.navigation(pages=[about_page, project_1_page, project_2_page])

# --- NAVGIATION SETUP [WITH SECTIONS] ---
pg = st.navigation(
    {
        "": [home_page],
        "Admin": [admin_1_page, admin_2_page, admin_3_page],
        "Dashboards": [dashboard_1_page, dashbaord_2_page],
    }
)

# --- SHARED ON ALL PAGES ---
#st.logo("") # image file path (Will be located at the top left of the naviation bar)
#st.sidebar.text("Made with streamlit")

# --- RUN NAVIGATION ---
pg.run()
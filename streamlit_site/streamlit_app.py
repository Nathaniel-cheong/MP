from imports import *

# ─── A. Where to store the pickle ────────────────────────────────────────
PICKLE_FILENAME = "cart_data.pkl"
PICKLE_PATH = os.path.join(os.getcwd(), PICKLE_FILENAME)

def load_cart_from_disk():
    """Return cart_data dict from pickle file, or None if missing/invalid."""
    if os.path.exists(PICKLE_PATH):
        try:
            with open(PICKLE_PATH, "rb") as f:
                data = pickle.load(f)
            # Basic sanity check
            if (
                isinstance(data, dict)
                and "basket_id" in data
                and "part_no" in data
                and "quantity" in data
                and isinstance(data["basket_id"], list)
                and isinstance(data["part_no"], list)
                and isinstance(data["quantity"], list)
            ):
                return data
        except Exception:
            pass
    return None

def save_cart_to_disk():
    """Write current session_state.cart_data to pickle file."""
    try:
        with open(PICKLE_PATH, "wb") as f:
            pickle.dump(st.session_state.cart_data, f)
    except Exception as e:
        st.error(f"Couldn't save cart: {e}")

# ─── 1. Initialize or reload cart_data into session_state ───────────────
if "cart_data" not in st.session_state:
    disk_data = load_cart_from_disk()
    if disk_data:
        st.session_state.cart_data = disk_data
    else:
        st.session_state.cart_data = {
            "basket_id": [1],   # only one basket
            "part_no": [[]],    # inner list holds part strings
            "quantity": [[]]    # parallel list of quantities
        }
        save_cart_to_disk()

# Track which part is awaiting removal confirmation
if "pending_remove" not in st.session_state:
    st.session_state.pending_remove = None
if "remove_max_qty" not in st.session_state:
    st.session_state.remove_max_qty = 0

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

checkout_page = st.Page(
    page="views/checkout.py",
    title="Checkout",
    icon="🛒",
)
# --- NAVGIATION SETUP [WITHOUT SECTIONS] ---
#pg = st.navigation(pages=[about_page, project_1_page, project_2_page])

# --- NAVGIATION SETUP [WITH SECTIONS] ---
pg = st.navigation(
    {
        "": [home_page],
        "Admin": [admin_1_page, admin_2_page, admin_3_page],
        "Dashboards": [dashboard_1_page, dashbaord_2_page],
        "Checkout": [checkout_page],
    }
)

# --- SHARED ON ALL PAGES ---
#st.logo("") # image file path (Will be located at the top left of the naviation bar)
#st.sidebar.text("Made with streamlit")

# --- RUN NAVIGATION ---
pg.run()
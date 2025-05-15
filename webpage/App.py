from imports import *
from Auth import login_form

# Set page config
st.set_page_config(page_title="Yamaha App", layout="wide")

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login_form()
    st.stop()

# Navigation options AFTER login
st.sidebar.title("Navigation")
page = st.sidebar.radio("Navigation", ["Main Page", "RFQ Dashboard", "Manual Imports"])


# Logout button
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()

# Manual routing
if page == "Main Page":
    from hidden_pages import Main
    Main.render()
elif page == "RFQ Dashboard":
    from hidden_pages import RFQ_Dashboard
    RFQ_Dashboard.render()
elif page == "Manual Imports":
    from website.hidden_pages import Manual_Imports
    Manual_Imports.render()


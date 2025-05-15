from imports import *

# Dummy credentials (replace with database or secure store)
USERS = {
    "admin": "123",
}

def login_form():
    st.title("Staff Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if username in USERS and USERS[username] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("Login successful.")
            st.rerun()  # Redirect after login
        else:
            st.error("Invalid credentials.")

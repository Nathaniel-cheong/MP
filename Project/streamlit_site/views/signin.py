from imports import *
cookies = CookieController()

if "user_type" not in st.session_state:
    st.session_state.user_type = cookies.get("user_type")
if "user_name" not in st.session_state:
    st.session_state.user_name = cookies.get("user_name")

st.title("Staff Log In")

if st.button("Staff: Tom"):
    st.session_state.user_type = "staff"
    st.session_state.user_name = "Tom"
    cookies.set("user_type", "staff")
    cookies.set("user_name", "Tom")
    st.success("Signed in as Staff")
    st.rerun()

if st.button("Staff: Bob"):
    st.session_state.user_type = "staff"
    st.session_state.user_name = "Bob"
    cookies.set("user_type", "staff")
    cookies.set("user_name", "Bob")
    st.success("Signed in as Staff")
    st.rerun()

if st.button("Admin: Admin"):
    st.session_state.user_type = "admin"
    st.session_state.user_name = "admin"
    cookies.set("user_type", "admin")
    cookies.set("user_name", "admin")
    st.success("Signed in as Admin")
    st.rerun()


if st.session_state.user_type:
    st.info(f"Current user type: **{st.session_state.user_type.capitalize()}**")

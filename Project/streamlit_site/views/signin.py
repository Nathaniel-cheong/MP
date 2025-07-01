from imports import *

st.title("Staff Log In")

if st.button("Staff: Tom"):
    st.session_state.user_type = "staff"
    st.session_state.user_name = "Tom"
    cookies.set("user_type", "staff") # doesnt work
    st.success("Signed in as Staff")
    st.rerun()

if st.button("Staff: Bob"):
    st.session_state.user_type = "staff"
    st.session_state.user_name = "Bob"
    st.success("Signed in as Staff")
    st.rerun()

if st.session_state.user_type:
    st.info(f"Current user type: **{st.session_state.user_type.capitalize()}**")

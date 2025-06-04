from imports import *
import streamlit as st

if "user_type" not in st.session_state:
    st.session_state.user_type = None

st.title("Sign In")
st.write("Please select your user type:")

col1, col2 = st.columns(2)

with col1:
    if st.button("Guest"):
        st.session_state.user_type = "guest"
        save_to_cache("guest", "user_role.pkl")
        st.success("Signed in as Guest")
        st.rerun()

with col2:
    if st.button("Staff"):
        st.session_state.user_type = "staff"
        save_to_cache("staff", "user_role.pkl")
        st.success("Signed in as Staff")
        st.rerun()

if st.session_state.user_type:
    st.info(f"Current user type: **{st.session_state.user_type.capitalize()}**")
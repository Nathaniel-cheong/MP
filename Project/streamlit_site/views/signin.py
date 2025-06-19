from imports import *
import streamlit as st

if "user_type" not in st.session_state:
    st.session_state.user_type = None

st.title("Staff Log In")

if st.button("Staff"):
    st.session_state.user_type = "staff"
    save_to_cache("staff", "user_role.pkl")
    st.success("Signed in as Staff")
    st.rerun()
 
if st.session_state.user_type:
    st.info(f"Current user type: **{st.session_state.user_type.capitalize()}**")
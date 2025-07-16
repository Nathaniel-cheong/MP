import streamlit as st
from imports import *

st.title("Staff Log In")

if st.button("Staff: Tom"):
    st.session_state.user_type = "staff"
    st.session_state.user_name = "Tom"
    cookies["user_type"] = "staff"
    cookies["user_name"] = "Tom"
    cookies.save()
    st.success("Signed in as Staff")
    st.rerun()

if st.button("Staff: Bob"):
    st.session_state.user_type = "staff"
    st.session_state.user_name = "Bob"
    cookies["user_type"] = "staff"
    cookies["user_name"] = "Bob"
    cookies.save()
    st.success("Signed in as Staff")
    st.rerun()

if st.button("Admin: Admin"):
    st.session_state.user_type = "admin"
    st.session_state.user_name = "admin"
    cookies["user_type"] = "admin"
    cookies["user_name"] = "admin"
    cookies.save()
    st.success("Signed in as Admin")
    st.rerun()

if st.session_state.user_type:
    st.info(f"Current user type: **{st.session_state.user_type.capitalize()}**")

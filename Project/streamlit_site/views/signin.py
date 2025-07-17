from imports import *

st.title("Staff Log In")

# Expiry time set to 1 day from now
expiry = datetime.utcnow() + timedelta(days=1)

if st.button("Staff: Tom"):
    st.session_state.user_type = "staff"
    st.session_state.user_name = "Tom"
    cookies.set_cookie_with_expiry("user_type", "staff", expiry)
    cookies.set_cookie_with_expiry("user_name", "Tom", expiry)
    cookies.save()
    st.success("Signed in as Staff")
    st.rerun()

if st.button("Staff: Bob"):
    st.session_state.user_type = "staff"
    st.session_state.user_name = "Bob"
    cookies.set_cookie_with_expiry("user_type", "staff", expiry)
    cookies.set_cookie_with_expiry("user_name", "Bob", expiry)
    cookies.save()
    st.success("Signed in as Staff")
    st.rerun()

if st.button("Admin: Admin"):
    st.session_state.user_type = "admin"
    st.session_state.user_name = "admin"
    cookies.set_cookie_with_expiry("user_type", "admin", expiry)
    cookies.set_cookie_with_expiry("user_name", "admin", expiry)
    cookies.save()
    st.success("Signed in as Admin")
    st.rerun()

if st.session_state.user_type:
    st.info(f"Current user type: **{st.session_state.user_type.capitalize()}**")
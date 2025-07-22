def old_signin_buttons():
    # Expiry time set to 1 day from now
    expiry = datetime.now(timezone.utc) + timedelta(days=1)

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

from imports import *

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

st.title("🔐 Staff Sign In (case-sensitive)")

# Load table
metadata = MetaData()
metadata.reflect(bind=engine)
accounts = metadata.tables.get("accounts")

# Input fields
user_name_email = st.text_input("Username or Email:")
password = st.text_input("Password:", type="password")

# --- Login Logic ---
if st.button("Login"):
    if not user_name_email or not password:
        st.warning("Please fill in both fields.")
        st.stop()

    with engine.connect() as conn:
        stmt = select(accounts).where(
            or_(
                accounts.c.email == user_name_email,
                accounts.c.staff_name == user_name_email
            )
        )
        result = conn.execute(stmt).fetchone()

        if result:
            row = result._mapping
            stored_hash = row["password"]

            if bcrypt.checkpw(password.encode(), stored_hash.encode()):
                # Update last_login timestamp
                conn.execute(
                    accounts.update()
                    .where(accounts.c.account_id == row["account_id"])
                    .values(last_login=datetime.utcnow().isoformat())
                )
                conn.commit()

                # Store only account_id in session and cookie
                st.session_state.account_id = row["account_id"]
                cookies["account_id"] = str(row["account_id"])
                cookies.save()

                st.success(f"Welcome back, {row['staff_name']}!")
                st.session_state.just_logged_in = True
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Incorrect password.")
        else:
            st.error("❌ Account not found.")

# --- Optional Quick Login Buttons (for testing only) ---
st.divider()
st.caption("Quick login (for testing only)")

if st.button("Tom (Staff)"):
    st.session_state.account_id = 1  # Adjust to match real account_id
    cookies["account_id"] = "1"
    cookies.save()
    st.rerun()

if st.button("Bob (Staff)"):
    st.session_state.account_id = 2
    cookies["account_id"] = "2"
    cookies.save()
    st.rerun()

if st.button("Admin"):
    st.session_state.account_id = 3
    cookies["account_id"] = "3"
    cookies.save()
    st.rerun()

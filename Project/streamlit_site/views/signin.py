from imports import *

st.title("🔐 Staff Sign In (case-sensitive)")

# reflect the metadata
metadata = MetaData()
metadata.reflect(bind=engine)
accounts = metadata.tables.get("accounts")

# --- Login Form (case-sensitive) ---
with st.form("login_form"):
    # Able to login by username or email
    user_name_email = st.text_input("Username or Email:")
    password = st.text_input("Password:", type="password")
    submit = st.form_submit_button("Login")

# --- Temporary error handler (Display and clear error message after a set time)---
if st.session_state.get("login_error"):
    st.error(st.session_state["login_error"])
    time.sleep(2)
    st.session_state["login_error"] = None
    st.rerun()

# Login logic
if submit:
    # Error handling for empty fields
    if not user_name_email or not password:
        st.session_state["login_error"] = "Please fill in both fields."
        st.rerun()

    # Fetch user info from DB
    with engine.connect() as conn:
        stmt = select(accounts).where(
            or_(
                accounts.c.email == user_name_email,
                accounts.c.staff_name == user_name_email
            )
        )
        result = conn.execute(stmt).fetchone()
        
        # Check account details
        if result:
            row = result._mapping
            # Get hashed password from the database
            stored_hash = row["password"]

            # Check if account is enabled
            if row.get("is_enabled") == 0:
                st.session_state["login_error"] = "❌ This account has been disabled."
                st.rerun()

            # Check if password is correct (refering to stored hashed password)
            if bcrypt.checkpw(password.encode(), stored_hash.encode()):
                with engine.begin() as trans_conn:
                    # Updates the login time for account
                    trans_conn.execute(
                        accounts.update()
                        .where(accounts.c.account_id == row["account_id"])
                        .values(last_login=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )

                # Used later on to get name and role of user
                st.session_state.account_id = row["account_id"]
                cookies["account_id"] = str(row["account_id"])
                cookies.save()
                
                st.success(f"Welcome back, {row['staff_name']}!")
                st.session_state.just_logged_in = True
                time.sleep(1)
                st.rerun()
            else:
                # Error handling for wrong password
                st.session_state["login_error"] = "❌ Incorrect details."
                st.rerun()
        else:
            # Error handling for wrong username/email
            st.session_state["login_error"] = "❌ Incorrect details."
            st.rerun()

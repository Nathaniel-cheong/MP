from imports import *

st.title("🔐 Staff Sign In (case-sensitive)")

# Load table
metadata = MetaData()
metadata.reflect(bind=engine)
accounts = metadata.tables.get("accounts")

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

# --- Login Form ---
with st.form("login_form"):
    user_name_email = st.text_input("Username or Email:")
    password = st.text_input("Password:", type="password")
    submit = st.form_submit_button("Login")

# --- Temporary error handler ---
if st.session_state.get("login_error"):
    st.error(st.session_state["login_error"])
    time.sleep(2)
    st.session_state["login_error"] = None
    st.rerun()

# --- Login Logic ---
if submit:
    if not user_name_email or not password:
        st.session_state["login_error"] = "Please fill in both fields."
        st.rerun()

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

            # Check if account is enabled
            if row.get("is_enabled") == 0:
                st.session_state["login_error"] = "❌ This account has been disabled."
                st.rerun()

            if bcrypt.checkpw(password.encode(), stored_hash.encode()):
                with engine.begin() as trans_conn:
                    trans_conn.execute(
                        accounts.update()
                        .where(accounts.c.account_id == row["account_id"])
                        .values(last_login=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )

                st.session_state.account_id = row["account_id"]
                cookies["account_id"] = str(row["account_id"])
                cookies.save()

                st.success(f"Welcome back, {row['staff_name']}!")
                st.session_state.just_logged_in = True
                time.sleep(1)
                st.rerun()
            else:
                st.session_state["login_error"] = "❌ Incorrect password."
                st.rerun()
        else:
            st.session_state["login_error"] = "❌ Account not found."
            st.rerun()

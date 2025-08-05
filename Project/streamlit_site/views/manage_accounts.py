from imports import *

st.title("👥 Manage Accounts")

# Initialize session states
st.session_state.setdefault("account_edit_mode", False)
st.session_state.setdefault("edit_account_id", None)

# Reflect the metadata
metadata = MetaData()
metadata.reflect(bind=engine)
accounts = metadata.tables.get("accounts")

# Load accounts table
def load_accounts_table():
    with engine.connect() as conn:
        return pd.read_sql_table("accounts", con=conn)

# --- Default Page (Not edit mode) ---
if st.session_state.account_edit_mode == False:
    accounts_df = load_accounts_table()

    # Exclude admin accounts
    accounts_df = accounts_df[accounts_df["role"].str.lower() != "admin"]

    # Check if accounts is empty
    if accounts_df.empty:
        st.info("No accounts found.")
        st.stop()

    # Search bar for staff name (As long as name contains query, Not case-sensitive, Doesnt need to be exact)
    search_query = st.text_input("🔍 Search by staff name only:")
    if search_query:
        query = search_query.strip().lower()
        accounts_df = accounts_df[accounts_df["staff_name"].astype(str).str.lower().str.contains(query)]

    # Add accounts button (Brings user to account edit page)
    if st.button("➕ Add Account"):
        st.session_state.account_edit_mode = True
        st.session_state.edit_account_id = None
        st.rerun()

    # Order accoutns like in database by sorting by account id ascending
    accounts_df = accounts_df.sort_values("account_id")
    rows = accounts_df.to_dict(orient="records")

    # Display only two accounts per row
    for i in range(0, len(rows), 2):
        cols = st.columns(2)
        for j in range(2):
            if i + j < len(rows):
                row = rows[i + j]
                with cols[j]:
                    with st.container(border=True):
                        account_key = str(row['account_id'])
                        # Display account details
                        st.markdown(f"""
                            **👤 Name:** {row['staff_name']}  
                            **📧 Email:** {row['email']}  
                            **🛡️ Role:** {row['role']}  
                            **📅 Created:** {row['created_at']}  
                            **🕒 Last Login:** {row['last_login']}  
                            **✅ Enabled:** {'Yes' if row['is_enabled'] == 1 else 'No'}
                        """)

                        # Activate / Deactivate Account (Locks account, prevent user from logging in)
                        activate_label = "❌ Deactivate" if row["is_enabled"] == 1 else "✅ Activate"
                        if st.button(activate_label, key=f"toggle_{account_key}"):
                            new_status = 0 if row["is_enabled"] == 1 else 1
                            with engine.begin() as conn:
                                conn.execute(
                                    accounts.update()
                                    .where(accounts.c.account_id == row["account_id"])
                                    .values(is_enabled=new_status)
                                )
                            st.success(f"Account {'deactivated' if new_status == 0 else 'activated'}")
                            st.rerun()

                        # Reset Password button
                        if st.button("🔁 Reset Password", key=f"reset_btn_{account_key}"):
                            st.session_state[f"show_reset_input_{account_key}"] = True

                        if st.session_state.get(f"show_reset_input_{account_key}", False):
                            new_pw = st.text_input(f"Enter new password for {row['staff_name']}:", key=f"pw_input_{account_key}")
                            if st.button("✅ Confirm Reset", key=f"confirm_reset_{account_key}"):
                                if new_pw:
                                    # Hash password to hide actual password from showing in the database
                                    hashed_pw = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
                                    with engine.begin() as conn:
                                        conn.execute(
                                            accounts.update()
                                            .where(accounts.c.account_id == row["account_id"])
                                            .values(password=hashed_pw)
                                        )
                                    st.success(f"Password updated for {row['staff_name']}")
                                    del st.session_state[f"show_reset_input_{account_key}"]
                                    st.rerun()
                                else:
                                    st.warning("Password cannot be empty.")

                        # Delete Account button (With double confirmation)
                        delete_key = f"delete_{account_key}"
                        confirm_key = f"confirm_delete_{account_key}"
                        confirm_button_key = f"confirm_button_{account_key}"
                        cancel_button_key = f"cancel_button_{account_key}"

                        if st.button("🗑️ Delete", key=delete_key):
                            st.session_state[confirm_key] = True
                        
                        if st.session_state.get(confirm_key, False):
                            st.warning(f"Are you sure you want to delete account: {row['staff_name']}?")

                            if st.button("✅ Confirm Delete", key=confirm_button_key):
                                with engine.begin() as conn:
                                    conn.execute(accounts.delete().where(accounts.c.account_id == row["account_id"]))
                                st.success(f"Deleted account: {row['staff_name']}")
                                st.session_state[confirm_key] = False
                                st.rerun()

                            if st.button("❌ Cancel", key=cancel_button_key):
                                st.session_state[confirm_key] = False
                                st.rerun()

# --- Edit Page (edit mode) ---
if st.session_state.account_edit_mode == True:
    st.header("✏️ Add Account Details")
    
    # Back button
    if st.button("🔙 Back to Accounts"):
        st.session_state.account_edit_mode = False
        st.session_state.edit_account_id = None
        st.rerun()

    # Form for required account details to create new account
    with st.form("add_account_form"):
        staff_name = st.text_input("Staff Name")
        email = st.text_input("Email")
        role = st.selectbox("Role", ["staff", "admin"])
        # Enables the account by default after creating
        is_enabled = 1
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")

        if st.form_submit_button("Add Account"):
            # Ensure the passwords match
            if password != confirm_password:
                st.error("Passwords do not match.")
            else:
                # Hash password to hide actual password from showing in the database
                hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                with engine.begin() as conn:
                    conn.execute(
                        accounts.insert().values(
                            staff_name=staff_name,
                            email=email,
                            role=role,
                            is_enabled=1 if is_enabled else 0,
                            password=hashed_pw,
                            created_at=datetime.now(),
                            last_login=datetime.now()
                        )
                    )
                st.success("Account successfully added!")
                st.session_state.account_edit_mode = False
                st.rerun()

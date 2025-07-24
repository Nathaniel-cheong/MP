from imports import *
import bcrypt

st.title("👥 Manage Accounts")

# --- Session Defaults ---
st.session_state.setdefault("account_edit_mode", False)
st.session_state.setdefault("edit_account_id", None)

# --- Reflect metadata ---
metadata = MetaData()
metadata.reflect(bind=engine)
accounts = metadata.tables.get("accounts")

# --- Load accounts table ---
def load_accounts_table():
    with engine.connect() as conn:
        return pd.read_sql_table("accounts", con=conn)

# --- Main View (Not Editing) ---
if st.session_state.account_edit_mode == False:
    accounts_df = load_accounts_table()

    # Exclude admin accounts
    accounts_df = accounts_df[accounts_df["role"].str.lower() != "admin"]

    # Stop if empty
    if accounts_df.empty:
        st.info("No accounts found.")
        st.stop()

    search_col, button_col = st.columns([5, 1])

    with search_col:
        search_query = st.text_input("🔍 Search by staff name only:")

    with button_col:
        st.write("")  # Adds vertical spacing to align button
        if st.button("➕ Add Account"):
            st.session_state.account_edit_mode = True
            st.session_state.edit_account_id = None
            st.rerun()


    if search_query:
        query = search_query.strip().lower()
        accounts_df = accounts_df[
            accounts_df["staff_name"].astype(str).str.lower().str.contains(query)
        ]

    # Sort and prepare rows
    accounts_df = accounts_df.sort_values("account_id")
    rows = accounts_df.to_dict(orient="records")

    # Display two accounts per row
    for i in range(0, len(rows), 2):
        cols = st.columns(2)
        for j in range(2):
            if i + j < len(rows):
                row = rows[i + j]
                with cols[j]:
                    with st.container(border=True):
                        account_key = str(row['account_id'])

                        st.markdown(f"""
                            **👤 Name:** {row['staff_name']}  
                            **📧 Email:** {row['email']}  
                            **🛡️ Role:** {row['role']}  
                            **📅 Created:** {row['created_at']}  
                            **🕒 Last Login:** {row['last_login']}  
                            **✅ Enabled:** {'Yes' if row['is_enabled'] == 1 else 'No'}
                        """)

                        # Activate / Deactivate
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

                        # Edit
                        if st.button("✏️ Edit", key=f"edit_{account_key}"):
                            st.session_state.edit_account_id = row["account_id"]
                            st.session_state.account_edit_mode = True
                            st.rerun()

                        # Delete with confirmation
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

# --- Edit Mode ---
if st.session_state.account_edit_mode == True:
    st.header("✏️ Edit Account Details")
    st.write(f"Editing account ID: `{st.session_state.edit_account_id}`")

    # Back button
    if st.button("🔙 Back to Accounts"):
        st.session_state.account_edit_mode = False
        st.session_state.edit_account_id = None
        st.rerun()

    # You can expand this section to add editable fields and update logic as needed

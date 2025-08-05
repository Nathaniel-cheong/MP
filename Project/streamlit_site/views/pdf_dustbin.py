from imports import *

st.title("🗑️ Archived PDFs")

# --- Session Defaults ---
st.session_state.setdefault("dustbin_page", False)

# Reflect the metadata
metadata = MetaData()
metadata.reflect(bind=engine)
pdf_log_table = metadata.tables.get("pdf_log")
pdf_info_table = metadata.tables.get("pdf_info")
accounts_table = metadata.tables.get("accounts")

# --- Check if table was found ---
if None in (pdf_log_table, pdf_info_table, accounts_table):
    st.error("❌ Could not find one or more required tables.")
    st.stop()

# --- Cached loader functions ---
def load_archived_pdfs():
    # First, find PDFs that are in the "dustbin" (is_active=0, is_current=0, archived=1)
    archived_pdfs_join = (
        pdf_log_table
        .join(pdf_info_table, pdf_log_table.c.pdf_id == pdf_info_table.c.pdf_id)
        .join(accounts_table, pdf_log_table.c.account_id == accounts_table.c.account_id)
    )

    query = select(
        pdf_log_table,
        pdf_info_table,
        accounts_table.c.staff_name.label("staff_name")
    ).select_from(archived_pdfs_join).where(
        pdf_log_table.c.is_active == 0, 
        pdf_log_table.c.is_current == 0,
        pdf_log_table.c.archived == 1  # Only get archived PDFs
    )

    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()

    return pd.DataFrame(rows, columns=result.keys())

# Load the archived PDFs
archived_pdfs_df = load_archived_pdfs()

# Stop if no archived PDFs
if archived_pdfs_df.empty:
    st.info("No archived PDFs found.")
    st.stop()

# Display archived PDFs with delete and restore buttons
for index, row in archived_pdfs_df.iterrows():
    with st.container():
        image_col, pdf_details_col, action_button_col = st.columns([1, 2, 1])

        with image_col:
            if row["bike_image"]:
                try:
                    st.image(row["bike_image"], width=200)
                except Exception:
                    st.write("⚠️ Image could not be displayed.")
            else:
                st.write("🚫 No image available")

        with pdf_details_col:
            details_col, changes_col = st.columns(2)

            ts = datetime.fromisoformat(str(row['timestamp']))
            date_str = ts.strftime("%Y-%m-%d")
            time_str = ts.strftime("%H:%M")
            status_str = (
                '<span style="color:green; font-weight:bold;">Active</span>'
                if row["is_active"] == 1
                else '<span style="color:red; font-weight:bold;">Not Active</span>'
            )

            with details_col:
                st.markdown(f"""
                    <u><b>PDF DETAILS:</b></u><br>
                    <b>Model:</b> {row['model']}<br>
                    <b>Batch ID:</b> {row['batch_id']}<br>
                    <b>Year:</b> {row['year']}<br>
                    <b>Brand:</b> {row['brand']}<br>
                    <b>CC:</b> {row['cc']}<br>
                """, unsafe_allow_html=True)

            with changes_col:
                st.markdown(f"""
                    <u><b>RECENT CHANGES:</b></u><br>
                    <b>Staff:</b> {row['staff_name']}<br>
                    <b>Date:</b> {date_str}<br>
                    <b>Time:</b> {time_str}<br>
                    <b>Status:</b> {status_str}
                """, unsafe_allow_html=True)

        with action_button_col:
            # Add a unique key by using the index for each button
            delete_key = f"delete_{row['pdf_id']}_{index}"
            confirm_key = f"confirm_delete_{row['pdf_id']}_{index}"
            confirm_button_key = f"confirm_button_{row['pdf_id']}_{index}"
            cancel_button_key = f"cancel_button_{row['pdf_id']}_{index}"

            restore_key = f"restore_{row['pdf_id']}_{index}"

            # Delete Button
            if st.button("❌ Delete", key=delete_key):
                st.session_state[confirm_key] = True

            if st.session_state.get(confirm_key, False):
                st.warning(f"Are you sure you want to permanently delete PDF ID {row['pdf_id']}?")

                if st.button("✅ Confirm Delete", key=confirm_button_key):
                    with engine.begin() as conn:
                        # Perform the permanent delete from pdf_log
                        conn.execute(delete(pdf_log_table).where(pdf_log_table.c.pdf_id == row['pdf_id']))

                        # Perform the permanent delete from pdf_info if needed
                        conn.execute(delete(pdf_info_table).where(pdf_info_table.c.pdf_id == row['pdf_id']))

                    st.success(f"Deleted PDF ID {row['pdf_id']} permanently.")
                    st.session_state[confirm_key] = False
                    st.rerun()

                if st.button("❌ Cancel", key=cancel_button_key):
                    st.session_state[confirm_key] = False
                    st.rerun()

            # Restore Button (same column as Delete)
            if st.button("🔄 Restore", key=restore_key):
                with engine.begin() as conn:
                    # Step 1: Set all existing logs for this PDF to inactive & not current
                    update_stmt = (
                        update(pdf_log_table)
                        .where(pdf_log_table.c.pdf_id == row["pdf_id"])
                        .values(is_active=0, is_current=0, archived=0)
                    )
                    conn.execute(update_stmt)

                    # Step 2: Insert a new log entry to reflect the restored state
                    restored_log_entry = pd.DataFrame([{
                        "pdf_id": row["pdf_id"],
                        "account_id": st.session_state["account_id"],
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "is_active": 0,     # Not reactivating, just unarchiving
                        "is_current": 1,    # Most recent log entry
                        "archived": 0,       # Unarchived
                        "description": "Restored PDF"
                    }])

                    restored_log_entry.to_sql("pdf_log", con=conn, if_exists="append", index=False)

                st.cache_data.clear()
                st.success("PDF successfully restored (unarchived).")
                time.sleep(1)
                st.rerun()

        st.divider()

from imports import *

st.title("🗑️ Archived PDFs")

# Reflect the metadata
metadata = MetaData()
metadata.reflect(bind=engine)
pdf_log_table = metadata.tables.get("pdf_log")
pdf_info_table = metadata.tables.get("pdf_info")
accounts_table = metadata.tables.get("accounts")

# Setting the day limit before being able to delete permanently
DELETION_GRACE_DAYS = 7
st.info("Archived PDFs can be permanently deleted after " + str(DELETION_GRACE_DAYS) + " days.")

# Check if table was found
if None in (pdf_log_table, pdf_info_table, accounts_table):
    st.error("❌ Could not find one or more required tables.")
    st.stop()

# function to query archived PDFs
def load_archived_pdfs():
    # Get latest log timestamp for each archived PDF
    latest_archived_logs_subquery = (
        select(
            pdf_log_table.c.pdf_id,
            func.max(pdf_log_table.c.timestamp).label("latest_timestamp")
        )
        .select_from(
            pdf_log_table.join(pdf_info_table, pdf_log_table.c.pdf_id == pdf_info_table.c.pdf_id)
        )
        .where(pdf_info_table.c.archived == 1)
        .group_by(pdf_log_table.c.pdf_id)
        .subquery()
    )

    # Join the latest log entry with pdf_info (bike details) and accounts (staff details)
    latest_archived_logs_join = (
        pdf_log_table
        .join(latest_archived_logs_subquery,
              (pdf_log_table.c.pdf_id == latest_archived_logs_subquery.c.pdf_id) &
              (pdf_log_table.c.timestamp == latest_archived_logs_subquery.c.latest_timestamp)
              )
        .join(pdf_info_table, pdf_log_table.c.pdf_id == pdf_info_table.c.pdf_id)
        .join(accounts_table, pdf_log_table.c.account_id == accounts_table.c.account_id)
    )

    # Final query
    query = (
        select(
            pdf_log_table,
            pdf_info_table,
            accounts_table.c.staff_name.label("staff_name")
        )
        .select_from(latest_archived_logs_join)
        .order_by(pdf_log_table.c.timestamp.desc())
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

# --- Filter Logic (Brand, Year, CC) ---
unique_brands = sorted(archived_pdfs_df["brand"].dropna().unique())
unique_years = sorted(archived_pdfs_df["year"].dropna().unique())
unique_ccs = sorted(archived_pdfs_df["cc"].dropna().unique())

with st.container():
    brand_filter_col, year_filter_col = st.columns(2)

    with brand_filter_col:
        st.session_state.setdefault("archived_filter_brand", "All")
        st.session_state["archived_filter_brand"] = st.selectbox(
            "Filter by Brand",
            ["All"] + unique_brands,
            index=(["All"] + unique_brands).index(st.session_state["archived_filter_brand"])
        )

    with year_filter_col:
        st.session_state.setdefault("archived_filter_year", "All")
        year_options = ["All"] + [str(year) for year in unique_years]
        st.session_state["archived_filter_year"] = st.selectbox(
            "Filter by Year",
            year_options,
            index=year_options.index(st.session_state["archived_filter_year"])
        )

# Apply filters
if st.session_state["archived_filter_brand"] != "All":
    archived_pdfs_df = archived_pdfs_df[archived_pdfs_df["brand"] == st.session_state["archived_filter_brand"]]

if st.session_state["archived_filter_year"] != "All":
    archived_pdfs_df = archived_pdfs_df[archived_pdfs_df["year"] == int(st.session_state["archived_filter_year"])]

# Display archived PDFs details with delete and restore buttons
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
                else '<span style="color:red; font-weight:bold;">Inctive</span>'
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
            restore_key = f"restore_{row['pdf_id']}_{index}"

            if st.button("🔄 Restore", key=restore_key):
                with engine.begin() as conn:
                    update_stmt = (
                        update(pdf_info_table)
                        .where(pdf_info_table.c.pdf_id == row["pdf_id"])
                        .values(archived=0)
                    )
                    conn.execute(update_stmt)

                    restored_log_entry = pd.DataFrame([{
                        "pdf_id": row["pdf_id"],
                        "account_id": st.session_state["account_id"],
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "description": "Restored PDF"
                    }])
                    restored_log_entry.to_sql("pdf_log", con=conn, if_exists="append", index=False)

                st.cache_data.clear()
                st.toast("PDF successfully restored.", icon="✅")
                time.sleep(1)
                st.rerun()

            # Delete button with grace period
            delete_key = f"delete_{row['pdf_id']}_{index}"
            confirm_key = f"confirm_delete_{row['pdf_id']}_{index}"
            confirm_button_key = f"confirm_button_{row['pdf_id']}_{index}"
            cancel_button_key = f"cancel_button_{row['pdf_id']}_{index}"

            archived_on = datetime.fromisoformat(str(row["timestamp"]))
            days_since_archived = (datetime.now() - archived_on).days

            delete_clicked = st.button(
                "❌ Delete",
                key=delete_key,
                disabled=days_since_archived < DELETION_GRACE_DAYS,
                help=(
                    f"Available in {DELETION_GRACE_DAYS - days_since_archived} day(s)"
                    if days_since_archived < DELETION_GRACE_DAYS
                    else "Permanently delete this PDF"
                )
            )

            if days_since_archived >= DELETION_GRACE_DAYS and delete_clicked:
                st.session_state[confirm_key] = True

            if st.session_state.get(confirm_key, False):
                st.warning(f"Are you sure you want to permanently delete PDF ID {row['pdf_id']}?")

                if st.button("✅ Confirm Delete", key=confirm_button_key):
                    with engine.begin() as conn:
                        conn.execute(delete(pdf_log_table).where(pdf_log_table.c.pdf_id == row['pdf_id']))
                        conn.execute(delete(pdf_info_table).where(pdf_info_table.c.pdf_id == row['pdf_id']))

                    st.success(f"Deleted PDF ID {row['pdf_id']} permanently.")
                    st.session_state[confirm_key] = False
                    st.rerun()

                if st.button("❌ Cancel", key=cancel_button_key):
                    st.session_state[confirm_key] = False
                    st.rerun()

    st.divider()

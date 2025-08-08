from imports import *
import io

st.title("Manage Bikes")

# initlize session states
for key in ["edit_page", "edit_page_mpl_list", "edit_page_pdf_info", "edit_page_pdf_section", 'pdf_updated']:
    st.session_state.setdefault(key, False)

# Reflect the metadata
metadata = MetaData()
metadata.reflect(bind=engine)
mpl_table = metadata.tables.get("master_parts_list")
pdf_info_table = metadata.tables.get("pdf_info")
pdf_log_table = metadata.tables.get("pdf_log")
pdf_section_table = metadata.tables.get("pdf_section")
accounts_table = metadata.tables.get("accounts")

# --- Check if table was found ---
if None in (mpl_table, pdf_info_table, pdf_log_table, pdf_section_table, accounts_table):
    st.error("❌ Could not find one or more required tables.")
    st.stop()

# --- Cached DB query functions ---
# (latest pdf_log + pdf_info + accounts)
@st.cache_data(ttl=300)
def load_pdf_details():
    # Subquery: Get the latest log timestamp for each PDF
    latest_logs_subquery = (
        select(
            pdf_log_table.c.pdf_id,
            func.max(pdf_log_table.c.timestamp).label("latest_timestamp")
        )
        .group_by(pdf_log_table.c.pdf_id)
        .subquery()
    )

    # Join the latest log entry
    latest_logs_join = (
        pdf_log_table
        .join(
            latest_logs_subquery,
            (pdf_log_table.c.pdf_id == latest_logs_subquery.c.pdf_id) &
            (pdf_log_table.c.timestamp == latest_logs_subquery.c.latest_timestamp)
        )
        .join(pdf_info_table, pdf_log_table.c.pdf_id == pdf_info_table.c.pdf_id)
        .join(accounts_table, pdf_log_table.c.account_id == accounts_table.c.account_id)
    )

    # Apply filter: only non-archived PDFs
    query = (
        select(
            pdf_log_table.c.description,
            pdf_log_table.c.timestamp,
            accounts_table.c.staff_name.label("staff_name"),
            pdf_info_table  # Includes is_active, archived, and all pdf metadata
        )
        .select_from(latest_logs_join)
        .where(pdf_info_table.c.archived == 0)  # 👈 Add this line
        .order_by(pdf_log_table.c.timestamp.asc())  # Optional: for consistency
    )

    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()

    return pd.DataFrame(rows, columns=result.keys())

@st.cache_data(ttl=300)
def load_pdf_info_table():
    with engine.connect() as conn:
        return pd.read_sql_table("pdf_info", con=conn)

@st.cache_data(ttl=300)
def load_mpl_table():
    with engine.connect() as conn:
        return pd.read_sql_table("master_parts_list", con=conn)

@st.cache_data(ttl=300)
def load_pdf_sections_without_image():
    with engine.connect() as conn:
        return pd.read_sql_table("pdf_section", con=conn, columns=["section_id", "section_no", "section_name", "pdf_id"])

@st.cache_resource(ttl=300)
def get_pdf_sections_by_pdf_id(pdf_id):
    """
    Fetch all sections for a given PDF ID from the pdf_section table.
    Automatically handles DB connection.
    """
    with engine.connect() as conn:
        query = text("SELECT * FROM pdf_section WHERE pdf_id = :pdf_id")
        df = pd.read_sql_query(query, con=conn, params={"pdf_id": pdf_id})
    return df

# Default page (Not edit mode)
if st.session_state.edit_page == False:
    pdf_details_df = load_pdf_details()
    
    # Creating filters
    if not pdf_details_df.empty:
        # Get unique values
        unique_brands = sorted(pdf_details_df["brand"].dropna().unique())
        unique_years = sorted(pdf_details_df["year"].dropna().unique())
        unique_ccs = sorted(pdf_details_df["cc"].dropna().unique())

        # Seperating 3 equal columns for filters for layout
        with st.container():
            year_col, brand_col, cc_col = st.columns(3)

            with year_col:
                st.session_state.setdefault("filter_brand", "All")
                st.session_state["filter_brand"] = st.selectbox("Filter by Brand", ["All"] + unique_brands, index=(["All"] + unique_brands).index(st.session_state["filter_brand"]))

            with brand_col:
                st.session_state.setdefault("filter_year", "All")
                year_options = ["All"] + [str(year) for year in unique_years]
                st.session_state["filter_year"] = st.selectbox("Filter by Year", year_options, index=year_options.index(st.session_state["filter_year"]))

            with cc_col:
                st.session_state.setdefault("filter_cc", "All")
                cc_options = ["All"] + [str(cc) for cc in unique_ccs]
                st.session_state["filter_cc"] = st.selectbox("Filter by CC", cc_options, index=cc_options.index(st.session_state["filter_cc"]))

    # Save filters to session
    selected_brand = st.session_state["filter_brand"]
    selected_year = st.session_state["filter_year"]
    selected_cc = st.session_state["filter_cc"]

    # Loading PDF and Change details
    if not pdf_details_df.empty:
        pdf_details_df = pdf_details_df.copy()

        # Apply filters
        if st.session_state["filter_brand"] != "All":
            pdf_details_df = pdf_details_df[pdf_details_df["brand"] == st.session_state["filter_brand"]]

        if st.session_state["filter_year"] != "All":
            pdf_details_df = pdf_details_df[pdf_details_df["year"] == int(st.session_state["filter_year"])]

        if st.session_state["filter_cc"] != "All":
            pdf_details_df = pdf_details_df[pdf_details_df["cc"].astype(str) == st.session_state["filter_cc"]]

        st.divider()
    
        for index, row in pdf_details_df.iterrows():
            with st.container():
                # Seperating 4 equal columns for layout
                image_col, pdf_details_col, edit_button_col, delete_button_col = st.columns([1, 2, 1, 1])

                # Bike image display
                with image_col:
                    if row["bike_image"]:
                        try:
                            st.image(row["bike_image"], width=200)
                        except Exception:
                            st.write("⚠️ Image could not be displayed.")
                    else:
                        st.write("🚫 No image available")

                # PDF details and changes display
                with pdf_details_col:
                    details_col, changes_col = st.columns(2)

                    ts = datetime.fromisoformat(str(row['timestamp']))
                    date_str = ts.strftime("%Y-%m-%d")
                    time_str = ts.strftime("%H:%M")
                    # Status text color: Green if active, red if inactive
                    status_str = (
                        '<span style="color:green; font-weight:bold;">Active</span>'
                        if row["is_active"] == 1
                        else '<span style="color:red; font-weight:bold;">Inactive</span>'
                    )

                    # PDF details display
                    with details_col:
                        st.markdown(f"""
                            <u><b>PDF DETAILS:</b></u><br>
                            <b>Model:</b> {row['model']}<br>
                            <b>Batch ID:</b> {row['batch_id']}<br>
                            <b>Year:</b> {row['year']}<br>
                            <b>Brand:</b> {row['brand']}<br>
                            <b>CC:</b> {row['cc']}<br>
                        """, unsafe_allow_html=True)

                    # PDF changes display
                    with changes_col:
                        st.markdown(f"""
                            <u><b>RECENT CHANGES:</b></u><br>
                            <b>Staff:</b> {row['staff_name']}<br>
                            <b>Date:</b> {date_str}<br>
                            <b>Time:</b> {time_str}<br>
                            <b>Status</b>: {status_str}
                        """, unsafe_allow_html=True)

                # Edit buttons (Edit tables and Activate/Deactivate PDF)
                with edit_button_col:
                    # Edit tables brings to next page where user can choose which table they want to edit
                    if st.button("✏️ Edit Details", key=f"edit_{row['pdf_id']}"):
                        st.session_state.edit_page = True
                        st.session_state.selected_pdf_id = row['pdf_id']
                        st.rerun()

                    # Activate/Deactivate button
                    toggle_label = "🔄 Set Inactive" if row["is_active"] == 1 else "✅ Set Active"
                    toggle_key = f"toggle_status_{row['pdf_id']}"

                    if st.button(toggle_label, key=toggle_key):
                        new_status = 0 if row["is_active"] == 1 else 1
                        with engine.begin() as conn:
                            stmt = update(pdf_info_table).where(
                                pdf_info_table.c.pdf_id == row['pdf_id']
                            ).values(is_active=new_status)
                            conn.execute(stmt)
                            
                            new_log_entry = pd.DataFrame([{
                                        "pdf_id": row["pdf_id"],
                                        "account_id": st.session_state["account_id"],
                                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "description": "Updated PDF"
                            }])

                            new_log_entry.to_sql("pdf_log", conn, if_exists="append", index=False)

                        st.cache_data.clear()
                        st.toast(f"Status for PDF ID {row['pdf_id']} updated.", icon="✅")
                        time.sleep(1)
                        st.rerun()

                # Delete button
                with delete_button_col:
                    delete_key = f"delete_{row['pdf_id']}"
                    confirm_key = f"confirm_delete_{row['pdf_id']}"
                    confirm_button_key = f"confirm_button_{row['pdf_id']}"
                    cancel_button_key = f"cancel_button_{row['pdf_id']}"

                    if st.button("❌ Delete", key=delete_key, help="Store into PDF Archive"):
                        st.session_state[confirm_key] = True

                    # Get user to double confirm
                    if st.session_state.get(confirm_key, False):
                        st.warning(f"Are you sure you want to delete PDF ID {row['pdf_id']}?")

                        if st.button("✅ Confirm Delete", key=confirm_button_key):
                            try:
                                with engine.begin() as conn:
                                    update_stmt = (
                                        update(pdf_info_table)
                                        .where(pdf_info_table.c.pdf_id == row["pdf_id"])
                                        .values(is_active=0, archived=1)
                                    )
                                    conn.execute(update_stmt)

                                    new_log_entry = pd.DataFrame([{
                                        "pdf_id": row["pdf_id"],
                                        "account_id": st.session_state["account_id"],
                                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "description": "Archived PDF"
                                    }])
                                    new_log_entry.to_sql("pdf_log", con=conn, if_exists="append", index=False)

                                st.cache_data.clear()
                                st.toast(f"Archived PDF ID {row['pdf_id']}", icon="🗑️")
                                time.sleep(1)
                                st.session_state[confirm_key] = False
                                st.rerun()

                            # Error handling
                            except Exception as e:
                                st.error(f"❌ Failed to delete PDF: {e}")
                                st.session_state[confirm_key] = False
                                st.rerun()

                        # Cancel delete action
                        if st.button("❌ Cancel", key=cancel_button_key):
                            st.session_state[confirm_key] = False
                            st.rerun()
                            
                st.divider()
    else:
        # Error handling
        st.info("Unable to join tables. Please check your table.")

# Edit options (Select which table to edit + edit mode)
if st.session_state.edit_page:
    # Get the selected PDF ID
    pdf_id = st.session_state.get("selected_pdf_id")
    # Error handling
    if not pdf_id:
        st.warning("No PDF selected.")
        st.stop()
    
    # Back to table selection button (When in editing any tables)
    if any([
        st.session_state.edit_page_mpl_list,
        st.session_state.edit_page_pdf_info,
        st.session_state.edit_page_pdf_section
    ]):
        # Handle back button (For multi-page in 1 file)
        if st.button("🔙 Back to Table Selection"):
            for key in ["edit_page_mpl_list", "edit_page_pdf_info", "edit_page_pdf_section"]:
                st.session_state[key] = False
            st.session_state["section_page"] = 0
            st.rerun()

    # Back to default page button (When selecting which table to edit)
    elif st.button("🔙 Back to All PDFs"):
        # Clear all editing page flags
        for key in [
            "edit_page", "edit_page_mpl_list", "edit_page_pdf_info", "edit_page_pdf_section",
            "mpl_df", "mpl_pdf_id", "mpl_edit_mode", "mpl_show_excel_reimport", "mpl_reimport_temp_df",
            "pdf_info_pdf_id", "pdf_info_df", "pdf_info_edit_mode", "pdf_info_edit_image",
            "section_page", "selected_section_id"
        ]:
            st.session_state.pop(key, None)
        st.session_state.pop("selected_pdf_id", None)
        st.rerun()

    # Edit table selection UI: Choose which table to edit page
    if not any([
        st.session_state.edit_page_mpl_list,
        st.session_state.edit_page_pdf_info,
        st.session_state.edit_page_pdf_section
    ]):
        st.subheader(f"Choose table to edit for PDF ID: {pdf_id}")
        # Flag which table selected by user for the session
        if st.button("Edit pdf_info"):
            st.session_state.edit_page_pdf_info = True
            st.rerun()
        if st.button("Edit master_parts_list"):
            st.session_state.edit_page_mpl_list = True
            st.rerun()
        if st.button("Edit pdf_section"):
            st.session_state.edit_page_pdf_section = True
            st.rerun()

    with engine.connect() as conn:
        # Edit PDF Info page
        if st.session_state.edit_page_pdf_info:
            st.divider()
            st.subheader("Edit: pdf_info")

            # Load + cache PDF info table and subset by pdf_id
            pdf_info_df = load_pdf_info_table()
            edit_pdf_info_df = pdf_info_df[pdf_info_df["pdf_id"] == pdf_id]

            # Error handling
            if edit_pdf_info_df.empty:
                st.warning("No data found for PDF ID.")
                st.stop()

            # Intitalize session states to track changes being made
            st.session_state.setdefault("pdf_info_pdf_id", pdf_id) 
            st.session_state.setdefault("pdf_info_df", edit_pdf_info_df.copy())
            st.session_state.setdefault("pdf_info_edit_mode", False)
            st.session_state.setdefault("pdf_info_edit_image", False)

            # Display table
            st.dataframe(st.session_state["pdf_info_df"], use_container_width=True)

            # Remove image button
            if st.button("❌ Remove Image", key="remove_image_button"):
                st.session_state["pdf_info_df"].iloc[0, st.session_state["pdf_info_df"].columns.get_loc("bike_image")] = None
                st.success("🗑️ Image removed from draft.")
                st.rerun()

            # Upload image button flag
            if st.button("📤 Upload Image", key="upload_image_button"):
                st.session_state["pdf_info_edit_image"] = True
            
            # Upload image UI
            if st.session_state["pdf_info_edit_image"]:
                with st.form("upload_image_form"):
                    st.subheader("Upload Image")

                    # Image uploader
                    uploaded_image = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"])
                    preview_image = st.form_submit_button("🖼️ Preview Image")

                    # Image preview button
                    if preview_image:
                        if uploaded_image:
                            try:
                                image_data = uploaded_image.getvalue()
                                st.image(image_data, width=200)
                            except Exception as e:
                                st.error("❌ Unable to read image.")
                                st.caption(str(e))
                        else:
                            st.warning("⚠️ No image uploaded.")

                    st.divider()
                    # Confirm/Cancel buton for image upload into draft
                    confirm_upload = st.form_submit_button("✅ Confirm Upload")
                    cancel_upload = st.form_submit_button("❌ Cancel")

                    if confirm_upload:
                        if uploaded_image:
                            try:
                                image_data = uploaded_image.getvalue()
                                st.session_state["pdf_info_df"].iloc[0, st.session_state["pdf_info_df"].columns.get_loc("bike_image")] = image_data
                                st.success("✅ Image saved to draft.")
                                time.sleep(1)
                                # Close upload image form after sucessfull upload to draft
                                st.session_state["pdf_info_edit_image"] = False
                                st.rerun()
                            # Error handling
                            except Exception as e:
                                st.error("❌ Error saving image to draft.")
                                st.caption(str(e))
                        else:
                            st.warning("⚠️ No image uploaded.")

                    if cancel_upload:
                        st.info("❌ Image upload cancelled.")
                        st.session_state["pdf_info_edit_image"] = False
                        st.rerun()

            # Edit table flag
            if st.button("✏️ Edit Table", key="pdf_info_edit_button"):
                st.session_state["pdf_info_edit_mode"] = True

            # Edit table UI
            if st.session_state["pdf_info_edit_mode"]:
                with st.form("pdf_info_edit_form"):
                    st.subheader("📝 Edit PDF Info")

                    row = st.session_state["pdf_info_df"].iloc[0]

                    # Preview info that are fixed can cannot be changed
                    st.markdown(f"**PDF ID:** `{pdf_id}`")
                    st.markdown(f"**Model:** `{row['model']}`")
                    st.markdown(f"**Batch ID:** `{row['batch_id']}`")
                    st.markdown(f"**Status:** `{row['is_active']}`")
                    st.markdown(f"**Archived:** `{row['archived']}`")

                    # Bike image preview if image available
                    if "bike_image" in row and row["bike_image"]:
                        st.image(row["bike_image"], width=150, caption="Bike Image")

                    # Editable fields
                    year_col, brand_col, cc_col = st.columns(3)
                    with year_col:
                        edited_year = st.number_input("Year", value=int(row["year"]), step=1, format="%d")
                    with brand_col:
                        # Fixed to currently supported 2 brand
                        brands_options = ["Yamaha", "Honda"]
                        edited_brand = st.selectbox("Brand", brands_options, 
                            index=brands_options.index(row["brand"]) if row["brand"] in brands_options else 0)
                    with cc_col:
                        cc_options = ["<200", "200-400", ">400"]
                        edited_cc = st.selectbox("CC", cc_options, 
                            index=cc_options.index(row["cc"]) if row["cc"] in cc_options else 0)

                    # Upload draft buttons
                    confirm_btn = st.form_submit_button("✅ Save Draft")
                    cancel_btn = st.form_submit_button("❌ Cancel")

                    # Submit/Cancel buttons
                    if confirm_btn:
                        # Year validation: must be a 4-digit number between 1000 and 9999
                        if isinstance(edited_year, int) and 1000 <= edited_year <= 9999:
                            st.session_state["pdf_info_df"] = pd.DataFrame([{
                                "pdf_id": pdf_id,
                                "year": edited_year,
                                "brand": edited_brand,
                                "model": row["model"],
                                "batch_id": row["batch_id"],
                                "bike_image": row.get("bike_image", None),
                                "cc": edited_cc,
                                "is_active": row["is_active"],
                                "archived": row["archived"]
                            }])
                            # Close form after successful upload to draft
                            st.session_state["pdf_info_edit_mode"] = False
                            st.success("✅ Draft saved in session.")
                            time.sleep(1)
                            st.rerun()
                        # Error message
                        else:
                            st.error("❌ Please enter a valid year.")

                    elif cancel_btn:
                        st.session_state["pdf_info_edit_mode"] = False
                        st.info("❌ Edit cancelled.")
                        time.sleep(1)
                        st.rerun()

            st.divider()

            # Reset draft: overwrite changes with orignal data from DB
            if st.button("🔄 Reset Changes"):
                st.session_state.pop("pdf_info_pdf_id", None)
                st.session_state.pop("pdf_info_df", None)
                st.session_state.pop("pdf_info_edit_mode", None)
                st.session_state.pop("show_image_previews", None)
                st.rerun()

            # Update changes to DB
            if st.button("✅ Save changes"):
                try:
                    edited_row = st.session_state["pdf_info_df"].iloc[0].to_dict()

                    stmt = (
                        update(pdf_info_table)
                        .where(pdf_info_table.c.pdf_id == edited_row["pdf_id"])
                        .values({
                            "year": edited_row["year"],
                            "brand": edited_row["brand"],
                            "model": edited_row["model"],
                            "batch_id": edited_row["batch_id"],
                            "bike_image": edited_row.get("bike_image", None),
                            "cc": edited_row["cc"]
                        })
                    )

                    with engine.begin() as conn:
                        result = conn.execute(stmt)

                    # Check if any rows were updated succesfully into DB
                    if result.rowcount == 0:
                        st.warning("⚠️ No rows were updated. Please check if the PDF ID exists.")
                    else:
                        st.success("✅ PDF Info successfully updated in the database.")
                        st.session_state['pdf_updated'] = True
                        st.cache_data.clear()

                    # Clear session states after successful upload
                    st.session_state.pop("pdf_info_pdf_id", None)
                    st.session_state.pop("pdf_info_df", None)
                    st.session_state.pop("pdf_info_edit_mode", None)
                    st.session_state.pop("show_image_previews", None)
                    st.rerun()

                # Error handling
                except Exception as e:
                    st.error(f"❌ Failed to update the database: {e}")
        
        # Edit master_parts_list page
        elif st.session_state.edit_page_mpl_list:
            st.subheader("Edit: master_parts_list")
            st.warning("Please do not touch the **mpl_id** column when editing")

            # Load + cache master_parts_list table and subset by pdf_id
            mpl_df = load_mpl_table()
            edit_mpl_df = mpl_df[mpl_df["pdf_id"] == pdf_id].sort_values("mpl_id")

            # Load + cache pdf_section table and subset by pdf_id for filter
            sections_df = load_pdf_sections_without_image()
            sections_df = sections_df[sections_df["pdf_id"] == pdf_id]

            # Error handling
            if edit_mpl_df.empty:
                st.warning("No entries found for this PDF ID.")
            else:
                # Intitalize session states to track changes being made
                st.session_state.setdefault("mpl_pdf_id", pdf_id)
                st.session_state.setdefault("mpl_df", edit_mpl_df.copy())
                st.session_state.setdefault("mpl_original_df", edit_mpl_df.copy())
                st.session_state.setdefault("mpl_show_excel_reimport", False)
                st.session_state.setdefault("mpl_edit_mode", False)
                st.session_state.setdefault("mpl_reimport_temp_df", None)

                # Section filter
                # Ensure types are correct
                sections_df["section_no"] = sections_df["section_no"].astype(str)
                sections_df["section_name"] = sections_df["section_name"].fillna("").astype(str)
                
                # Build label column
                sections_df["section_label"] = sections_df.apply(
                    lambda row: f"{row['section_no']} ({row['section_name']})", axis=1
                )

                # Sort by section_no numerically and alphabetically
                sections_df["sort_key"] = sections_df["section_no"].apply(filter_sorting) # function from imports.py
                sections_df = sections_df.sort_values("sort_key")

                # Filter mapping
                section_options = ["All"] + sections_df["section_label"].tolist()
                section_no_map = dict(zip(sections_df["section_label"], sections_df["section_no"]))
                
                # Filter UI
                selected_section = st.selectbox("Filter by Section", section_options)

                # Join section_no into session_state["mpl_df"] for filtering preview only
                preview_df = st.session_state["mpl_df"].copy()
                preview_df = preview_df.merge(
                    sections_df[["section_id", "section_no"]],
                    on="section_id",
                    how="left"
                )

                # Apply section filter (only affects preview, not stored data)
                if selected_section != "All":
                    section_no = section_no_map[selected_section]
                    preview_df = preview_df[preview_df["section_no"].astype(str) == section_no]

                # Drop section_no before preview
                preview_df = preview_df.drop(columns=["section_no"], errors="ignore")

                # Display preview
                st.dataframe(preview_df, use_container_width=True, hide_index=True)

                        
                # Download as Excel for editing
                buffer = io.BytesIO()
                st.session_state["mpl_df"].to_excel(buffer, index=False)
                st.download_button(
                    label="📥 Download master_parts_list Excel",
                    data=buffer.getvalue(),
                    file_name=f"master_parts_list_{pdf_id}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                # Reimport flag
                if st.button("📤 Reimport File", key="mpl_reimport_button"):
                    st.session_state["mpl_show_excel_reimport"] = True

                # Reimport UI
                if st.session_state["mpl_show_excel_reimport"]:
                    with st.form("mpl_reimport_excel_form"):
                        st.markdown("Upload an Excel file to replace the current Master Parts List.")
                        mpl_excel_upload = st.file_uploader("Upload Edited MPL Excel File (.xlsx)", type="xlsx")

                        # Validate excel
                        if mpl_excel_upload:
                            try:
                                new_df = pd.read_excel(mpl_excel_upload, engine="openpyxl")
                                original_cols = set(st.session_state["mpl_df"].columns)
                                new_cols = set(new_df.columns)

                                # Check if columns match
                                if original_cols != new_cols:
                                    st.error(f"❌ Column mismatch in uploaded file.\n\nExpected: {sorted(original_cols)}\nGot: {sorted(new_cols)}")
                                else:
                                    uploaded_pdf_ids = new_df["pdf_id"].dropna().unique()
                                    # Check if there is only 1 PDF_id and it has not been changed
                                    if len(uploaded_pdf_ids) != 1 or uploaded_pdf_ids[0] != pdf_id:
                                        st.error(f"❌ PDF ID mismatch.\nExpected: '{pdf_id}'\nFound in file: {uploaded_pdf_ids}")
                                    else:
                                        st.session_state["mpl_reimport_temp_df"] = new_df
                                        st.success("✅ File uploaded into draft. Please confirm import below.")
                            # Error handling
                            except Exception as e:
                                st.error(f"❌ Failed to read Excel file: {e}")

                        # Confirm/Cancel button for upload to draft 
                        confirm_import = st.form_submit_button("✅ Confirm Import")
                        cancel_import = st.form_submit_button("❌ Cancel")

                        if confirm_import and st.session_state.get("mpl_reimport_temp_df") is not None:
                            # replace current df with uploaded df
                            st.session_state["mpl_df"] = st.session_state["mpl_reimport_temp_df"]
                            st.session_state["mpl_reimport_temp_df"] = None
                            st.session_state["mpl_show_excel_reimport"] = False
                            st.success("✅ Data saved into draft. Press 'Save Changes' to apply.")
                            st.rerun()

                        elif cancel_import:
                            st.session_state["mpl_reimport_temp_df"] = None
                            st.session_state["mpl_show_excel_reimport"] = False
                            st.info("❌ Reimport cancelled.")
                            st.rerun()

                # Edit table flag
                if not st.session_state["mpl_edit_mode"]:
                    if st.button("✏️ Edit Table"):
                        st.session_state["mpl_edit_mode"] = True
                        st.rerun()

                # Edit table UI
                if st.session_state["mpl_edit_mode"]:
                    # Made use of form to prevent whole code from rerunning each time a letter/number is entered
                    with st.form("mpl_edit_form"):
                        st.write("Edit the table and save changes.")
                        # Table editor
                        edited_df = st.data_editor(st.session_state["mpl_df"], use_container_width=True)

                        # Confirm/Cancel button for upload to draft
                        confirm_btn = st.form_submit_button("✅ Save Draft")
                        cancel_btn = st.form_submit_button("❌ Cancel")

                        if confirm_btn:
                            st.session_state["mpl_df"] = edited_df
                            st.session_state["mpl_edit_mode"] = False
                            st.success("✅ Changes saved into draft. Press 'Save Changes' to apply to database.")
                            time.sleep(1)
                            st.rerun()
                        elif cancel_btn:
                            st.session_state["mpl_edit_mode"] = False
                            st.info("❌ Edit cancelled.")
                            time.sleep(1)
                            st.rerun()

                st.divider()

                # Reset data button
                if st.button("🔄 Reset Changes"):
                    try:
                        with engine.connect() as conn_refresh:
                            refreshed_df = load_mpl_table()
                            refreshed_df = refreshed_df[refreshed_df["pdf_id"] == pdf_id]
                            st.session_state["mpl_df"] = refreshed_df
                            st.session_state["mpl_edit_mode"] = False
                            st.session_state["mpl_reimport_temp_df"] = None
                            st.session_state["mpl_show_excel_reimport"] = False
                        st.success("🔄 Changes resetted")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to reset changes: {e}")

                # Upload to DB
                if "mpl_save_pending" not in st.session_state and st.button("✅ Save Changes"):
                    try:
                        original_df = st.session_state["mpl_original_df"].copy()
                        edited_df = st.session_state["mpl_df"].copy()

                        # Strip whitespace from string columns before comparison
                        original_df = strip_whitespace(original_df)
                        edited_df = strip_whitespace(edited_df)

                        # Compare and show changes made
                        common_cols = [col for col in edited_df.columns if col in original_df.columns and col != "mpl_id"]
                        original_df = original_df.sort_values("mpl_id").reset_index(drop=True)
                        edited_df = edited_df.sort_values("mpl_id").reset_index(drop=True)

                        comparison = edited_df[["mpl_id"] + common_cols]
                        original_comparison = original_df[["mpl_id"] + common_cols]

                        diffs = (comparison[common_cols] != original_comparison[common_cols])
                        changed_rows_mask = diffs.any(axis=1)
                        rows_to_update = comparison[changed_rows_mask]

                        original_ids = set(original_df["mpl_id"])
                        # Show new rows added
                        rows_to_insert = edited_df[~edited_df["mpl_id"].isin(original_ids)]
                        # Show rows deleted
                        rows_to_delete = original_df[~original_df["mpl_id"].isin(edited_df["mpl_id"])]
                        
                        # Show summary
                        if not rows_to_update.empty:
                            st.info("🔄 Rows that will be UPDATED:")
                            st.dataframe(rows_to_update, use_container_width=True)
                        if not rows_to_insert.empty:
                            st.info("➕ Rows that will be INSERTED:")
                            st.dataframe(rows_to_insert, use_container_width=True)
                        if not rows_to_delete.empty:
                            st.info("❌ Rows that will be DELETED:")
                            st.dataframe(rows_to_delete, use_container_width=True)
                        # If no changes at all, show message and skip buttons
                        if rows_to_update.empty and rows_to_insert.empty and rows_to_delete.empty:
                            st.success("✅ No changes detected.")
                            st.stop()

                        # Save intermediate state for confirmation
                        st.session_state["mpl_save_pending"] = {
                            "rows_to_update": rows_to_update,
                            "rows_to_insert": rows_to_insert,
                            "rows_to_delete": rows_to_delete
                        }

                        st.warning("⚠️ Please confirm to apply these changes.")
                    # Error handling
                    except Exception as e:
                        st.error(f"❌ Failed during change detection: {e}")

                # If pending confirmation, show confirm/cancel buttons
                if "mpl_save_pending" in st.session_state:
                    year_col, brand_col = st.columns([1, 1])
                    with year_col:
                        if st.button("✅ Confirm Apply"):
                            try:
                                changes = st.session_state["mpl_save_pending"]
                                rows_to_update = changes["rows_to_update"]
                                rows_to_insert = changes["rows_to_insert"]
                                rows_to_delete = changes["rows_to_delete"]

                                # Validate columns
                                required_cols = ["part_no", "description", "ref_no", "section_id", "pdf_id"]

                                # Define non-nullable columns
                                required_cols = ["part_no", "description", "ref_no", "section_id", "pdf_id"]

                                # Validate UPDATE rows
                                for col in required_cols:
                                    invalid_rows = rows_to_update[col].isna() | rows_to_update[col].astype(str).str.strip().eq("")
                                    if invalid_rows.any():
                                        bad_indices = rows_to_update[invalid_rows].index.tolist()
                                        st.error(f"❌ Cannot update: Column '{col}' has blank/null in rows: {bad_indices}")
                                        st.stop()

                                # Validate INSERT rows
                                for col in required_cols:
                                    invalid_rows = rows_to_insert[col].isna() | rows_to_insert[col].astype(str).str.strip().eq("")
                                    if invalid_rows.any():
                                        bad_indices = rows_to_insert[invalid_rows].index.tolist()
                                        st.error(f"❌ Cannot insert: Column '{col}' has blank/null in rows: {bad_indices}")
                                        st.stop()

                                # Applying changes to DB
                                with engine.begin() as conn:
                                    for _, row in rows_to_update.iterrows():
                                        stmt = (
                                            update(mpl_table)
                                            .where(mpl_table.c.mpl_id == row["mpl_id"])
                                            .values({col: row[col] for col in row.index if col != "mpl_id"})
                                        )
                                        conn.execute(stmt)

                                    if not rows_to_insert.empty:
                                        rows_to_insert.to_sql("master_parts_list", con=conn, if_exists="append", index=False)

                                    for mpl_id in rows_to_delete["mpl_id"]:
                                        conn.execute(delete(mpl_table).where(mpl_table.c.mpl_id == mpl_id))

                                # Clear states after succesful upload
                                for key in ["mpl_df", "mpl_pdf_id", "mpl_edit_mode", "mpl_show_excel_reimport", "mpl_reimport_temp_df", "mpl_original_df", "mpl_save_pending"]:
                                    st.session_state.pop(key, None)

                                st.success("✅ Changes successfully saved to the database.")
                                st.session_state['pdf_updated'] = True
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()
                            # Error handling
                            except Exception as e:
                                st.error(f"❌ Failed to apply changes: {e}")

                    with brand_col:
                        if st.button("❌ Cancel Save"):
                            st.session_state.pop("mpl_save_pending", None)
                            st.info("❌ Save operation cancelled.")
                            time.sleep(1)
                            st.rerun()

        # Edit PDF Section page
        elif st.session_state.edit_page_pdf_section:
            st.subheader("Edit: pdf_section")

            # Query all sections for selected PDF_id
            all_sections_df = get_pdf_sections_by_pdf_id(pdf_id)

            # Sort sections
            all_sections_df["__sort_key__"] = all_sections_df["section_no"].apply(filter_sorting) # from imports.py
            all_sections_df = all_sections_df.sort_values("__sort_key__").drop(columns="__sort_key__").reset_index(drop=True)

            # If user has selected the section to edit
            if st.session_state.get("selected_section_id"):
                selected_row = all_sections_df[all_sections_df["section_id"] == st.session_state["selected_section_id"]]
                # Back to section list button
                if st.button("🔙 Back to Section List"):
                            st.session_state["selected_section_id"] = None
                            st.rerun()

                if not selected_row.empty:
                    st.subheader(f"Editing Section ID: {st.session_state['selected_section_id']}")

                    # Intitalize session states to track changes being made
                    st.session_state.setdefault("section_edit_df", selected_row.copy())
                    st.session_state.setdefault("section_edit_mode", False)
                    st.session_state.setdefault("section_edit_image", False)

                    # Display table
                    st.dataframe(st.session_state["section_edit_df"], use_container_width=True)

                    # Reupload Image flag
                    if st.button("📤 Upload Image", key="upload_section_image_button"):
                        st.session_state["section_edit_image"] = True

                    # Reupload Image UI
                    if st.session_state["section_edit_image"]:
                        with st.form("upload_section_image_form"):
                            st.subheader("Upload Section Image")

                            # Image uploader
                            uploaded_image = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"])
                            # Preview image button
                            preview_image = st.form_submit_button("🖼️ Preview Image")
                            if preview_image:
                                if uploaded_image:
                                    try:
                                        image_data = uploaded_image.getvalue()
                                        st.image(image_data, width=200)
                                    except Exception as e:
                                        st.error("❌ Unable to read image.")
                                        st.caption(str(e))
                                else:
                                    st.warning("⚠️ No image uploaded.")

                            st.divider()
                            # Confirm/Cancel button for image upload into draft
                            confirm_upload = st.form_submit_button("✅ Confirm Upload")
                            cancel_upload = st.form_submit_button("❌ Cancel")

                            if confirm_upload:
                                if uploaded_image:
                                    try:
                                        image_data = uploaded_image.getvalue()
                                        st.session_state["section_edit_df"].iloc[0, st.session_state["section_edit_df"].columns.get_loc("section_image")] = image_data
                                        st.success("✅ Image saved to draft.")
                                        time.sleep(1)
                                        st.session_state["section_edit_image"] = False
                                        st.rerun()
                                    # Error handling
                                    except Exception as e:
                                        st.error("❌ Error saving image to draft.")
                                        st.caption(str(e))
                                else:
                                    st.warning("⚠️ No image uploaded.")

                            if cancel_upload:
                                st.info("❌ Image upload cancelled.")
                                st.session_state["section_edit_image"] = False
                                st.rerun()

                    # Edit table flag
                    if st.button("✏️ Edit Table", key="section_edit_button"):
                        st.session_state["section_edit_mode"] = True

                    # Edit table UI
                    if st.session_state["section_edit_mode"]:
                        with st.form("section_edit_form"):
                            st.subheader("📝 Edit Section")

                            row = st.session_state["section_edit_df"].iloc[0]

                            # Show fixed info that cannot be edited
                            st.markdown(f"**Section ID:** `{row['section_id']}`")

                            # Editable fields
                            name_col, section_col = st.columns(2)
                            with name_col:
                                edited_name = st.text_input("Section Name", value=row["section_name"])
                            with section_col:
                                edited_no = st.text_input("Section No", value=row["section_no"])

                            # Submit buttons
                            confirm_btn = st.form_submit_button("✅ Save Draft")
                            cancel_btn = st.form_submit_button("❌ Cancel")

                            if confirm_btn:
                                st.session_state["section_edit_df"] = pd.DataFrame([{
                                    "section_id": row["section_id"],
                                    "section_no": edited_no,
                                    "section_name": edited_name,
                                    "pdf_id": row["pdf_id"],
                                    "section_image": row.get("section_image", None)
                                }])
                                st.session_state["section_edit_mode"] = False
                                st.success("✅ Draft saved in session.")
                                time.sleep(1)
                                st.rerun()
                            elif cancel_btn:
                                st.session_state["section_edit_mode"] = False
                                st.info("❌ Edit cancelled.")
                                time.sleep(1)
                                st.rerun()

                    st.divider()

                    # Reset draft from DB
                    if st.button("🔄 Reset Changes"):
                        st.session_state.pop("section_edit_df", None)
                        st.session_state.pop("section_edit_mode", None)
                        st.rerun()

                    # Save changes to DB
                    if st.button("✅ Save changes"):
                        try:
                            edited_row = st.session_state["section_edit_df"].iloc[0].to_dict()

                            # Update data into DB
                            stmt = (
                                update(pdf_section_table)
                                .where(pdf_section_table.c.section_id == edited_row["section_id"])
                                .values({
                                    "section_name": edited_row["section_name"],
                                    "section_no": edited_row["section_no"],
                                    "section_image": edited_row.get("section_image", None)
                                })
                            )

                            with engine.begin() as conn:
                                result = conn.execute(stmt)

                            if result.rowcount == 0:
                                st.warning("⚠️ No rows were updated. Please check if the Section ID exists.")
                            else:
                                st.success("✅ Section Info successfully updated in the database.")
                                st.session_state['pdf_updated'] = True
                                st.cache_data.clear()

                            # Clear session state
                            st.session_state.pop("section_edit_df", None)
                            st.session_state.pop("section_edit_mode", None)
                            st.session_state["selected_section_id"] = None
                            st.rerun()

                        except Exception as e:
                            st.error(f"❌ Failed to update the database: {e}")
                # Error handling
                else:
                    st.error("⚠️ Could not find the selected section.")
                st.stop()

            # Default page: If no section is selected, Seperate PDF sections by pages.
            else:
                sections_per_page = 8
                total_sections = len(all_sections_df)
                total_pages = (total_sections - 1) // sections_per_page + 1
                st.session_state.setdefault("section_page", 0)
                current_page = st.session_state["section_page"]

                # Error handling
                if all_sections_df.empty:
                    st.warning("No PDF sections found for this PDF ID.")
                    st.stop()
                
                # Pagination
                start_idx = current_page * sections_per_page
                end_idx = start_idx + sections_per_page
                current_df = all_sections_df.iloc[start_idx:end_idx]

                # Display sections informations + image
                for idx, row in current_df.iterrows():
                    with st.container():
                        img_col, info_col, btn_col = st.columns([1.5, 3, 1])
                        with img_col:
                            img_data = row["section_image"]
                            if img_data:
                                try:
                                    if isinstance(img_data, (bytes, bytearray, memoryview)):
                                        image = Image.open(io.BytesIO(img_data))
                                        st.image(image, width=200)
                                    else:
                                        st.image(img_data, width=200)
                                except Exception as e:
                                    st.write("⚠️ Image could not be displayed.")
                                    st.caption(str(e))
                            else:
                                st.write("🚫 No image available")

                        with info_col:
                            st.markdown(f"""
                                <u><b>SECTION INFO:</b></u><br>
                                <b>Section ID:</b><br>{row['section_id']}<br>
                                <b>Name:</b><br>{row['section_name']}<br>
                                <b>Section No:</b><br>{row['section_no']}<br>
                            """, unsafe_allow_html=True)

                        with btn_col:
                            if st.button("Edit Details", key=f"edit_section_{row['section_id']}"):
                                st.session_state["selected_section_id"] = row["section_id"]
                                st.rerun()
 
                    st.divider()

                # Pagination controls
                year_col, brand_col, cc_col = st.columns([1, 2, 1])
                with year_col:
                    if current_page > 0:
                        if st.button("⬅️ Previous", key="prev_page"):
                            st.session_state["section_page"] -= 1
                            st.rerun()
                with brand_col:
                    st.markdown(f"<center>Page {current_page + 1} of {total_pages}</center>", unsafe_allow_html=True)
                with cc_col:
                    if end_idx < total_sections:
                        if st.button("Next ➡️", key="next_page"):
                            st.session_state["section_page"] += 1
                            st.rerun()

        # Generic logging for any updates made
        if st.session_state['pdf_updated']:
            time.sleep(1)
            try:
                Session = sessionmaker(bind=engine)
                with Session.begin() as session:
                    # Insert the new log row
                    logged_changes = pd.DataFrame([{
                        "pdf_id": pdf_id,
                        "account_id": st.session_state["account_id"],
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "description": "Updated PDF"
                    }])

                    logged_changes.to_sql("pdf_log", con=session.connection(), if_exists="append", index=False)

                # If all went well, reset the session flag
                st.session_state['pdf_updated'] = False

            except Exception as e:
                st.error(f"❌ Failed to update PDF log: {e}")
                st.stop()
                
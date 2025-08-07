from imports import *
import io
st.title("PDF Parts Catalogue Imports")

# Init session state
if "file_states" not in st.session_state:
    st.session_state["file_states"] = {}
if "uploaded_filename" not in st.session_state:
    st.session_state["uploaded_filename"] = ""

# --- File Upload ---
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
# Forces the user to upload a file before doing anything else
if uploaded_file is None:
    st.warning("Please upload a PDF file.")
    st.stop()

filename = uploaded_file.name
# Check if previously import PDF for this session
is_new_file = filename != st.session_state["uploaded_filename"]

# IF new file for session, intialize file state to persist throughout session
if is_new_file:
    st.session_state["uploaded_filename"] = filename
    st.session_state["file_states"][filename] = {
        "brand": "Select a Brand",
        "uploaded_file": uploaded_file,
        "model": extract_model(filename),
        "batch_id": "",
        "year": "",
        "preview_clicked": False,
        "pdf_id": "",
        "mpl_df": None,
        "pdf_section_df": None,
        "pdf_log": None,
        "mpl_reimport_temp_df": None,
        "pdf_section_reimport_temp_df": None,
        "preview_loaded": None
    }

# Open file states's session
file_state = st.session_state["file_states"][filename]

# Brand options
brand_options = ["Select a Brand", "Yamaha", "Honda"]

# Keep track of previous brand to detect change
if "previous_brand" not in file_state:
    file_state["previous_brand"] = "Select a Brand"

# Keep track of current brand selected to session
if "brand_select" not in st.session_state:
    st.session_state.brand_select = file_state["brand"]

# --- FORM (brand) ---
current_brand = st.selectbox("Brand:", brand_options, key="brand_select")
# Forces user to select a brand before continuing
if current_brand == "Select a Brand":
    st.warning("Please select a brand.")
    st.stop()

# If brand changed → clear session states
if st.session_state.brand_select != file_state["previous_brand"]:
    file_state["brand"] = st.session_state.brand_select
    file_state["batch_id"] = extract_batch_id(filename, file_state["brand"])
    file_state["year"] = extract_year(filename, file_state["brand"])
    file_state["model"] = extract_model(filename)
    file_state["previous_brand"] = st.session_state.brand_select
    file_state["preview_clicked"] = False
    file_state["preview_loaded"] = None

    file_state['mpl_df'] = None
    file_state['pdf_section_df'] = None
    file_state['pdf_log'] = None
    file_state['pdf_info'] = None

# --- FORM (page variables) ---
st.subheader("Data Preview Form")
# Let user know that some parts of the form has been autofilled
st.info("Please review all form fields. All values were auto-filled from the file name or loaded from previous session and may require correction.")

# Form inputs
form_model = st.text_input("Model:", value=file_state["model"])
form_batch_id = st.text_input("Batch ID:", value=file_state["batch_id"])
form_year = st.text_input("Year:", value=file_state["year"])
cc_options = ["<200", "200-400", ">400"]
form_cc = st.selectbox("Brand:", cc_options, key="cc")

# Ensure that user has selected the correct CC instead of the default "<200"
if form_cc == "<200":
    st.info("Ensure that you have selected the correct CC of the bike.")

# Flag if all inputs of the form is filled
form_filled = all([
    str(form_model).strip(),
    str(form_batch_id).strip(),
    str(form_year).strip()
])

# Bike image upload
form_image = st.file_uploader("Upload the bike image (Optional)", type=["jpg", "jpeg", "png"])
image_bytes = form_image.read() if form_image else None

# Form validation
form_accepted = False
# All form fields must be field except image
if not form_filled:
    st.warning("Please fill in all fields to enable 'Preview Data' button.")
# Year must be in a valid format
elif not re.fullmatch(r"\d{4}", str(form_year).strip()):
    st.error("Please enter a valid Year (format: YYYY).")
else:
    form_accepted = True

# Checkbox to enable preview button
checked_form = False
if form_accepted:
    checked_form = st.checkbox("Confirm")

preview_enabled = form_accepted and checked_form

if st.button("Preview Data", disabled=not preview_enabled):
    if file_state["preview_loaded"]:
        file_state['pdf_info'] = None

    # Store form values to file state after user confirmation
    file_state["model"] = form_model
    file_state["batch_id"] = form_batch_id
    file_state["year"] = form_year
    file_state["preview_clicked"] = True
    file_state["preview_loaded"] = True

# --- MAIN PROCESSING ---
if file_state["preview_clicked"] and form_filled:
    # Creating PDF_id
    file_state["pdf_id"] = file_state["model"] + "_" + file_state["batch_id"]

    # Passing parameters to processor
    parameters = [
        uploaded_file.read(),
        file_state["pdf_id"],
        file_state["brand"],
        file_state["year"],
        file_state["model"],
        file_state["batch_id"],
        form_cc,
        image_bytes
    ]

    # Intializing processor based of brand from imports.py
    if file_state["brand"] == "Yamaha":
        processor = YamahaProcessor(*parameters)

    elif file_state["brand"] == "Honda":
        processor = HondaProcessor(*parameters)
    
    # Extract all data if none has been stored in file state
    if file_state["pdf_info"] is None:
        # Structure PDF_info using form inputs that was passed into processor
        file_state["pdf_info"] = processor.get_pdf_info()

    if file_state["mpl_df"] is None or file_state["pdf_section_df"] is None:
        # Display processing status and time taken
        with st.status("Extracting Parts Data") as status:
            start_time = time.time()
            # mpl_df extraction
            file_state["mpl_df"] = processor.extract_master_parts_list()
            # Create the log for which staff is uploading the pdf
            file_state["pdf_log"] = processor.extract_pdf_log(st.session_state["account_id"], "Uploaded PDF")
            total_time = time.time() - start_time
            status.update(label=f"Parts data extraction completed in {total_time:.2f} seconds.", state="complete")

        with st.status("Extracting Images") as status:
            start_time = time.time()
            # pdf_section extraction (section info + image)
            file_state["pdf_section_df"] = processor.extract_pdf_section()
            total_time = time.time() - start_time
            status.update(label=f"Parts image extraction completed in {total_time:.2f} seconds.", state="complete")

    # --- TABLE DISPLAY ---
    # --- PDF info preview ---
    if file_state["pdf_info"] is not None:
        st.divider()
        st.subheader("PDF Information Preview")
        st.dataframe(file_state["pdf_info"], use_container_width=True)

    # --- MPL preview + edits UI ---
    if file_state["mpl_df"] is not None:
        st.subheader("Master Parts List Preview")
        st.dataframe(file_state["mpl_df"], use_container_width=True)

        # Download table as excel file to make changes
        buffer = io.BytesIO()
        file_state["mpl_df"].to_excel(buffer, index=False)
        st.download_button(
            label="📥 Download as Excel",
            data=buffer.getvalue(),
            file_name=f"master_parts_list_{file_state['mpl_df']['pdf_id'].iloc[0]}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="mpl_download_button"
        )

        # Intialize flags
        file_state.setdefault("mpl_show_excel_reimport", False)
        file_state.setdefault("mpl_excel_uploaded", False)
        file_state.setdefault("mpl_edit_mode", False)

        # Flag to show reimport UI
        if st.button("📤 Reimport File", key="mpl_reimport_button"):
            file_state["mpl_show_excel_reimport"] = True

        # Reimport UI
        if file_state["mpl_show_excel_reimport"]:
            # Made use of form to handle validation before applying changes to main file state
            with st.form("mpl_reimport_excel_form"):
                st.markdown("Upload an Excel file to replace the current Master Parts List.")
                mpl_excel_upload = st.file_uploader("Upload Edited MPL Excel File (.xlsx)", type="xlsx")

                # Validate data
                if mpl_excel_upload:
                    try:
                        # Check if columns match before upload
                        new_df = pd.read_excel(mpl_excel_upload, engine="openpyxl")
                        original_cols = set(file_state["mpl_df"].columns)
                        new_cols = set(new_df.columns)

                        if original_cols != new_cols:
                            st.error(f"❌ Column mismatch in uploaded file.\n\nExpected: {sorted(original_cols)}\nGot: {sorted(new_cols)}")
                        else:
                            uploaded_pdf_ids = new_df["pdf_id"].dropna().unique()
                            current_pdf_id = file_state["pdf_id"]

                            # Check if only there is only 1 PDF_id and it has not been changed
                            if len(uploaded_pdf_ids) != 1 or uploaded_pdf_ids[0] != current_pdf_id:
                                st.error(f"❌ PDF ID mismatch.\nExpected: '{current_pdf_id}'\nFound in file: {uploaded_pdf_ids}")
                            else:
                                file_state["mpl_reimport_temp_df"] = new_df
                                st.success("✅ File uploaded. Applying changes")
                    # Error handling
                    except Exception as e:
                        st.error(f"❌ Failed to read Excel file: {e}")

                # Form action buttons
                confirm_import = st.form_submit_button("✅ Confirm Import")
                cancel_import = st.form_submit_button("❌ Cancel")

                if confirm_import:
                    # Check if a valid file has been uploaded
                    if file_state.get("mpl_reimport_temp_df") is not None:
                        file_state["mpl_df"] = file_state["mpl_reimport_temp_df"]
                        file_state["mpl_reimport_temp_df"] = None
                        file_state["mpl_excel_uploaded"] = True
                        file_state["mpl_show_excel_reimport"] = False
                        st.success("✅ Excel file imported and table updated.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning("⚠️ Please upload a valid Excel file before confirming.")

                elif cancel_import:
                    # Clear imported file
                    file_state["mpl_reimport_temp_df"] = None
                    file_state["mpl_show_excel_reimport"] = False
                    st.info("❌ Reimport cancelled.")
                    time.sleep(1)
                    st.rerun()

        # Flag for edit table UI
        if st.button("✏️ Edit Table", key="mpl_edit_button"):
            file_state["mpl_edit_mode"] = True

        # Edit table UI
        if file_state["mpl_edit_mode"]:
            # Made use of form to prevent whole code from rerunning each time a letter/number is entered
            with st.form("mpl_edit_form"):
                st.subheader("Edit Master Parts List Table")
                st.write("Edit the table directly below and click **Save MPL** to apply changes.")
                editable_mpl_df = file_state["mpl_df"]
                # Table editor
                edited_mpl_df = st.data_editor(editable_mpl_df, use_container_width=True)

                confirm_edit = st.form_submit_button("✅ Save MPL")
                cancel_edit = st.form_submit_button("❌ Cancel")

                if confirm_edit:
                    file_state["mpl_df"] = edited_mpl_df
                    file_state["mpl_edit_mode"] = False
                    st.success("✅ Master Parts List data updated.")
                    time.sleep(1)
                    st.rerun()

                elif cancel_edit:
                    file_state["mpl_edit_mode"] = False
                    st.info("❌ Edit cancelled.")
                    time.sleep(1)
                    st.rerun()

    # --- PDF SECTION preview + edits UI ---
    if file_state["pdf_section_df"] is not None:
        st.subheader("PDF Section Preview")
        st.dataframe(file_state["pdf_section_df"], use_container_width=True)

        # Download Table as excel file to make changes
        buffer = io.BytesIO()
        # Remove image column before export
        # When reimport with image column, column becomes text instead of bytea format
        export_section_df = file_state["pdf_section_df"].drop(columns=["section_image"], errors="ignore")
        export_section_df.to_excel(buffer, index=False)
        st.download_button(
            label="📥 Download as Excel",
            data=buffer.getvalue(),
            file_name=f"pdf_section_{file_state['mpl_df']['pdf_id'].iloc[0]}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pdf_section_download_button"
        )

        # Init flags
        file_state.setdefault("pdf_section_show_excel_reimport", False)
        file_state.setdefault("pdf_section_excel_uploaded", False)
        file_state.setdefault("pdf_section_edit_mode", False)

        # Flag to show reimport UI
        if st.button("📤 Reimport Excel File", key="pdf_section_reimport_button"):
            file_state["pdf_section_show_excel_reimport"] = True

        # Reimport UI
        if file_state["pdf_section_show_excel_reimport"]:
            # Made use of form to handle validation before applying changes to main file state
            with st.form("pdf_section_reimport_excel_form"):
                st.markdown("Upload an Excel file to replace the current PDF Section table.")
                pdf_section_excel_upload = st.file_uploader("Upload Edited Excel File (.xlsx)", type="xlsx")

                # Validate data
                if pdf_section_excel_upload:
                    try:
                        # Check if columns match before upload
                        new_df = pd.read_excel(pdf_section_excel_upload, engine="openpyxl")
                        original_cols = set(file_state["pdf_section_df"].drop(columns=["section_image"], errors="ignore").columns)
                        new_cols = set(new_df.columns)

                        if original_cols != new_cols:
                            st.error(f"❌ Column mismatch in uploaded file.\n\nExpected: {sorted(original_cols)}\nGot: {sorted(new_cols)}")
                        else:
                            uploaded_pdf_ids = new_df["pdf_id"].dropna().unique()
                            current_pdf_id = file_state["pdf_id"]

                            # Check if only there is only 1 PDF_id and it has not been changed
                            if len(uploaded_pdf_ids) != 1 or uploaded_pdf_ids[0] != current_pdf_id:
                                st.error(f"❌ PDF ID mismatch.\nExpected: '{current_pdf_id}'\nFound in file: {uploaded_pdf_ids}")
                            else:
                                # Join back image column using section_id
                                if "section_image" in file_state["pdf_section_df"].columns:
                                    images_df = file_state["pdf_section_df"][["section_id", "section_image"]]
                                    new_df = new_df.merge(images_df, on="section_id", how="left")
                                file_state["pdf_section_reimport_temp_df"] = new_df
                                st.success("✅ File uploaded. Please confirm import below.")
                    # Error handling
                    except Exception as e:
                        st.error(f"❌ Failed to read Excel file: {e}")

                # Form action buttons
                confirm_import = st.form_submit_button("✅ Confirm Import")
                cancel_import = st.form_submit_button("❌ Cancel")

                if confirm_import:
                    # Check if a valid file has been uploaded
                    if file_state.get("pdf_section_reimport_temp_df") is not None:
                        file_state["pdf_section_df"] = file_state["pdf_section_reimport_temp_df"]
                        file_state["pdf_section_reimport_temp_df"] = None
                        file_state["pdf_section_excel_uploaded"] = True
                        file_state["pdf_section_show_excel_reimport"] = False
                        st.success("✅ Excel file imported and table updated.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning("⚠️ Please upload a valid Excel file before confirming.")

                elif cancel_import:
                    # Clear imported file
                    file_state["pdf_section_reimport_temp_df"] = None
                    file_state["pdf_section_show_excel_reimport"] = False
                    st.info("❌ Reimport cancelled.")
                    time.sleep(1)
                    st.rerun()

        # Flag for edit table UI
        if st.button("✏️ Edit Table", key="pdf_section_edit_button"):
            file_state["pdf_section_edit_mode"] = True

        # Edit Table UI
        if file_state["pdf_section_edit_mode"]:
            # Made use of form to prevent whole code from rerunning each time a letter/number is entered
            with st.form("pdf_section_edit_form"):
                st.subheader("Edit PDF Section Table")
                st.write("Edit the table directly below and click **Save PDF Sections** to apply changes.")
                editable_pdf_section_df = file_state["pdf_section_df"]
                # Table editor
                edited_pdf_section_df = st.data_editor(editable_pdf_section_df, use_container_width=True)

                confirm_edit = st.form_submit_button("✅ Save PDF Sections")
                cancel_edit = st.form_submit_button("❌ Cancel")

                if confirm_edit:
                    file_state["pdf_section_df"] = edited_pdf_section_df
                    file_state["pdf_section_edit_mode"] = False
                    st.success("✅ PDF Section data updated.")
                    time.sleep(1)
                    st.rerun()

                elif cancel_edit:
                    file_state["pdf_section_edit_mode"] = False
                    st.info("❌ Edit cancelled.")
                    time.sleep(1)
                    st.rerun()

        # --- Image Preview ---
        st.subheader("Preview: Parts Images")

        # Initialize image preview flag
        if "show_image_previews" not in st.session_state:
            st.session_state["show_image_previews"] = False

        # Show/Hide image button
        if st.button("🔍 Display Image Previews" if not st.session_state["show_image_previews"] else "❌ Hide Image Previews", key="toggle_preview_btn"):
            st.session_state["show_image_previews"] = not st.session_state["show_image_previews"]
            st.rerun()  # Force rerun immediately after state change

        # Handle image previews
        if st.session_state["show_image_previews"]:
            st.divider()
            # Display images from imports.py
            display_image_previews(file_state["pdf_section_df"], "", file_state["brand"])
            st.divider()

    st.divider()
    checked_tables = st.checkbox("Confirm", key="confirm_tables")

    # --- Final Upload to DB Button ---
    # Check tables before upload as empty/blank values are still being inserted to non-null columns
    if st.button("Upload Data to Database", disabled=not checked_tables):
        # Define required fields per table
        required_fields = {
            "pdf_info": ["pdf_id", "year", "brand", "model", "batch_id", "cc", "is_active", "archived"],
            "pdf_section_df": ["section_id", "section_no", "section_name", "pdf_id"],
            "mpl_df": ["part_no", "description", "ref_no", "section_id", "pdf_id"],
            "pdf_log": ["pdf_id", "account_id", "timestamp", "description"]
        }
        
        # Check for missing/blank required fields and shows rows with missing fields
        for df_key, required_cols in required_fields.items():
            df = file_state.get(df_key)
            # Error handling
            if df is None:
                st.error(f"❌ Missing table: {df_key}")
                st.stop()
            # Extra check for columns
            for col in required_cols:
                if col not in df.columns:
                    st.error(f"❌ '{df_key}' is missing required column '{col}'")
                    st.stop()

                # Check for missing/empty/blank values
                invalid_rows = df[col].isna() | df[col].astype(str).str.strip().eq("")
                if invalid_rows.any():
                    # Keep tracks of rows and shows them
                    bad_indices = df[invalid_rows].index.tolist()
                    st.error(f"❌ {df_key} → Column '{col}' is empty/null in rows: {bad_indices}")
                    st.stop()
        
        # Convert data types
        try:
            file_state["pdf_info"] = file_state["pdf_info"].astype({
                "pdf_id": str,
                "year": int,
                "brand": str,
                "model": str,
                "batch_id": str,
                "cc": str,
                "is_active": int,
                "archived": int
            })

            file_state["pdf_section_df"] = file_state["pdf_section_df"].astype({
                "section_id": str,
                "section_no": str,
                "section_name": str,
                "pdf_id": str
            })

            file_state["mpl_df"] = file_state["mpl_df"].astype({
                "part_no": str,
                "description": str,
                "ref_no": str,
                "section_id": str,
                "pdf_id": str
            })

            file_state["pdf_log"] = file_state["pdf_log"].astype({
                "pdf_id": str,
                "account_id": str,
                "timestamp": str,
                "description": str
            })

        # Error handling
        except Exception as e:
            st.error(f"❌ Failed to convert column types: {e}")
            st.stop()

        # Check if pdf_id already exists
        pdf_id = file_state["pdf_info"]["pdf_id"].iloc[0]
        with engine.connect() as conn:
            existing = conn.execute(
                text("SELECT 1 FROM pdf_info WHERE pdf_id = :pdf_id LIMIT 1"),
                {"pdf_id": pdf_id}
            ).fetchone()

        # Block user from uploading if PDF already exist in the database
        if existing:
            st.error(f"❌ A PDF with ID '{pdf_id}' already exists in the database. Please Delete if first if you wish to reupload.")
            st.stop()

        # Upload into database
        try:
            Session = sessionmaker(bind=engine)
            session = Session()

            # Show upload status
            with st.status("📤 Uploading data to database...", expanded=True) as status:
                if "add_info" in file_state["mpl_df"].columns:
                    file_state["mpl_df"]["add_info"] = (
                        file_state["mpl_df"]["add_info"]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                        .replace("nan", "")
                    )

                # Upload using session to ensure everything is in one transaction
                with session.begin():
                    file_state["pdf_info"].to_sql("pdf_info", session.connection(), if_exists="append", index=False)
                    file_state["pdf_section_df"].to_sql("pdf_section", session.connection(), if_exists="append", index=False)
                    file_state["mpl_df"].to_sql("master_parts_list", session.connection(), if_exists="append", index=False)
                    file_state["pdf_log"].to_sql("pdf_log", session.connection(), if_exists="append", index=False)

                status.update(label="✅ Upload completed successfully.", state="complete")
                st.success("✅ Upload completed successfully.")
                # For manage database page to show changes
                st.cache_data.clear()

                # Clean up session after successful upload
                st.session_state["file_states"].pop(filename, None)
                st.session_state["uploaded_filename"] = ""
                st.session_state.pop("brand_select", None)
                st.session_state.pop("show_image_previews", None)
                st.session_state.pop("confirm_tables", None)
        
        # Error handling
        except Exception as e:
            status.update(label="❌ Upload failed.", state="error")
            st.error(f"❌ Upload failed: {e}")
            st.warning("⚠️ No changes were made to the database.")
            st.stop()

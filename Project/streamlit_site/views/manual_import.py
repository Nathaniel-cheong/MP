# if choose wrong brand to process pdf, pdf will be empty and pdf_section extraction will have error as missing data at 'section_id'
# add error handling and pdf_edit through csv import

# Fix xlsx import, image column become string instead of bytea
# Add error handling for db
from imports import *
import io

st.title("Manual Imports")

# --- Init ---
if "file_states" not in st.session_state:
    st.session_state["file_states"] = {}

if "uploaded_filename" not in st.session_state:
    st.session_state["uploaded_filename"] = ""

# --- UI Sidebar ---
st.sidebar.markdown("""
**For More Infomation**
-
""")

# --- File Upload ---
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

if uploaded_file is None:
    st.warning("Please upload a PDF file.")
    st.stop()

filename = uploaded_file.name
is_new_file = filename != st.session_state["uploaded_filename"]

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
        "pdf_log": None
    }

file_state = st.session_state["file_states"][filename]

# --- Brand Select ---
brand_options = ["Select a Brand", "Yamaha", "Honda"]

# Init previous brand if missing
if "previous_brand" not in file_state:
    file_state["previous_brand"] = "Select a Brand"

# Use session_state key to detect change 
if "brand_select" not in st.session_state:
    st.session_state.brand_select = file_state["brand"]

current_brand = st.selectbox("Brand:", brand_options, key="brand_select")

if current_brand == "Select a Brand":
    st.warning("Please select a brand.")
    st.stop()

# If brand changed → reset fields 
if st.session_state.brand_select != file_state["previous_brand"]:
    file_state["brand"] = st.session_state.brand_select
    file_state["batch_id"] = extract_batch_id(filename, file_state["brand"])
    file_state["year"] = extract_year(filename, file_state["brand"])
    file_state["model"] = extract_model(filename)
    file_state["previous_brand"] = st.session_state.brand_select
    file_state["preview_clicked"] = False
    
    file_state['mpl_df'] = None
    file_state['pdf_section_df'] = None
    file_state['pdf_log'] = None
    file_state['pdf_info'] = None

# --- FORM (page variables) ---
st.subheader("Data Preview")
st.info("Please review all form fields. All values were auto-filled from the file name or loaded from previous session and may require correction.")

form_model = st.text_input("Model:", value=file_state["model"])
form_batch_id = st.text_input("Batch ID:", value=file_state["batch_id"])
form_year = st.text_input("Year:", value=file_state["year"])
form_image = st.file_uploader("Upload the bike image", type=["jpg", "jpeg", "png"])

form_filled = all([
    str(form_model).strip(),
    str(form_batch_id).strip(),
    str(form_year).strip()
])

form_accepted = False
if not form_filled:
    st.warning("Please fill in all fields to enable 'Preview Data' button.")
elif not re.fullmatch(r"\d{4}", str(form_year).strip()):
    st.error("Please enter a valid Year (format: YYYY).")
else:
    form_accepted = True

checked_form = False
if form_accepted:
    checked_form = st.checkbox("Confirm")

preview_enabled = form_accepted and checked_form

if st.button("Preview Data", disabled=not preview_enabled):
    # Copy form to session state
    file_state["model"] = form_model
    file_state["batch_id"] = form_batch_id
    file_state["year"] = form_year
    file_state["preview_clicked"] = True

# --- MAIN PROCESSING ---
if file_state["preview_clicked"] and form_filled:
    file_state["pdf_id"] = file_state["model"] + "_" + file_state["batch_id"]

    parameters = [
            uploaded_file.read(),
            file_state["pdf_id"],
            file_state["brand"],
            file_state["year"],
            file_state["model"],
            file_state["batch_id"],
            form_image
    ]

    if file_state["brand"] == "Yamaha":
        processor = YamahaProcessor(*parameters)

    elif file_state["brand"] == "Honda":
        processor = HondaProcessor(*parameters)

    file_state["pdf_info"] = processor.get_pdf_info()

    if file_state["mpl_df"] is None or file_state["pdf_section_df"] is None:
        with st.status("Extracting Parts Data") as status:
            start_time = time.time()
            file_state["mpl_df"] = processor.extract_master_parts_list()
            file_state["pdf_log"] = processor.extract_pdf_log(st.session_state["user_name"]) # replace with user id in future
            total_time = time.time() - start_time
            status.update(label=f"Parts data extraction completed in {total_time:.2f} seconds.", state="complete")

        with st.status("Extracting Images") as status:
            start_time = time.time()
            file_state["pdf_section_df"] = processor.extract_pdf_section()
            total_time = time.time() - start_time
            status.update(label=f"Parts image extraction completed in {total_time:.2f} seconds.", state="complete")

    # --- DISPLAY ---
    if file_state["pdf_info"] is not None:
        st.subheader("PDF Information Preview")
        st.dataframe(file_state["pdf_info"], use_container_width=True)

    # MPL preview + edits UI
    if file_state["mpl_df"] is not None:
        st.subheader("Master Parts List Preview")
        st.dataframe(file_state["mpl_df"], use_container_width=True)

        # --- Download Button ---
        buffer = io.BytesIO()
        file_state["mpl_df"].to_excel(buffer, index=False)
        st.download_button(
            label="📥 Download as Excel",
            data=buffer.getvalue(),
            file_name="master_parts_list.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="mpl_download_button"
        )

        # --- Init internal flags ---
        file_state.setdefault("mpl_show_excel_reimport", False)
        file_state.setdefault("mpl_excel_uploaded", False)
        file_state.setdefault("mpl_edit_mode", False)

        # --- Toggle to show reimport section ---
        if st.button("📤 Reimport File", key="mpl_reimport_button"):
            file_state["mpl_show_excel_reimport"] = True

        # --- Reimport Excel UI ---
        if file_state["mpl_show_excel_reimport"]:
            with st.form("mpl_reimport_excel_form"):
                st.markdown("Upload an Excel file to replace the current Master Parts List.")
                uploaded_file = st.file_uploader("Upload Edited MPL Excel File (.xlsx)", type="xlsx")

                if uploaded_file:
                    try:
                        new_df = pd.read_excel(uploaded_file, engine="openpyxl")
                        file_state["mpl_reimport_temp_df"] = new_df
                        st.success("✅ File uploaded. Please confirm import below.")
                    except Exception as e:
                        st.error(f"❌ Failed to read Excel file: {e}")

                confirm_import = st.form_submit_button("✅ Confirm Import")
                cancel_import = st.form_submit_button("❌ Cancel")

                if confirm_import:
                    if file_state["mpl_reimport_temp_df"] is not None:
                        file_state["mpl_df"] = file_state["mpl_reimport_temp_df"]
                        file_state["mpl_reimport_temp_df"] = None
                        file_state["mpl_excel_uploaded"] = True
                        file_state["mpl_show_excel_reimport"] = False
                        st.success("✅ Excel file imported and table updated.")
                        st.rerun()
                    else:
                        st.warning("⚠️ Please upload a valid Excel file before confirming.")

                elif cancel_import:
                    file_state["mpl_reimport_temp_df"] = None
                    file_state["mpl_show_excel_reimport"] = False
                    st.info("❌ Reimport cancelled.")
                    st.rerun()

        # --- Edit Mode Toggle ---
        if st.button("✏️ Edit Table", key="mpl_edit_button"):
            file_state["mpl_edit_mode"] = True

        # --- Edit Form ---
        if file_state["mpl_edit_mode"]:
            with st.form("mpl_edit_form"):
                st.subheader("Edit Master Parts List Table")
                st.write("Edit the table directly below and click **Save MPL** to apply changes.")
                editable_mpl_df = file_state["mpl_df"]
                edited_mpl_df = st.data_editor(editable_mpl_df, use_container_width=True)

                confirm_edit = st.form_submit_button("✅ Save MPL")
                cancel_edit = st.form_submit_button("❌ Cancel")

                if confirm_edit:
                    file_state["mpl_df"] = edited_mpl_df
                    file_state["mpl_edit_mode"] = False
                    st.success("✅ Master Parts List data updated.")
                    st.rerun()

                elif cancel_edit:
                    file_state["mpl_edit_mode"] = False
                    st.info("❌ Edit cancelled.")
                    st.rerun()

    # PDF SECTION preview + edits UI
    if file_state["pdf_section_df"] is not None:
        # Original Table Preview + Changes applied
        st.subheader("PDF Section Preview")
        st.dataframe(file_state["pdf_section_df"], use_container_width=True)

        # Download Table as Xlsx Button
        buffer = io.BytesIO()
        file_state["pdf_section_df"].to_excel(buffer, index=False)
        st.download_button(
            label="📥 Download as Excel",
            data=buffer.getvalue(),
            file_name="pdf_section_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pdf_section_download_button"
        )

        # Init internal flags for UI
        file_state.setdefault("pdf_section_show_excel_reimport", False)
        file_state.setdefault("pdf_section_excel_uploaded", False)
        file_state.setdefault("pdf_section_edit_mode", False)

        # Button to toggle reimport section UI
        if st.button("📤 Reimport Excel File", key="pdf_section_reimport_button"):
            file_state["pdf_section_show_excel_reimport"] = True

        # Reimport section UI
        if file_state["pdf_section_show_excel_reimport"]:
            with st.form("pdf_section_reimport_excel_form"):
                st.markdown("Upload an Excel file to replace the current PDF Section table.")
                uploaded_file = st.file_uploader("Upload Edited Excel File (.xlsx)", type="xlsx")

                if uploaded_file:
                    try:
                        new_df = pd.read_excel(uploaded_file, engine="openpyxl")
                        file_state["pdf_section_reimport_temp_df"] = new_df
                        st.success("✅ File uploaded. Please confirm import below.")
                    except Exception as e:
                        st.error(f"❌ Failed to read Excel file: {e}")

                confirm_import = st.form_submit_button("✅ Confirm Import")
                cancel_import = st.form_submit_button("❌ Cancel")

                if confirm_import:
                    if file_state["pdf_section_reimport_temp_df"] is not None:
                        file_state["pdf_section_df"] = file_state["pdf_section_reimport_temp_df"]
                        file_state["pdf_section_reimport_temp_df"] = None
                        file_state["pdf_section_excel_uploaded"] = True
                        file_state["pdf_section_show_excel_reimport"] = False
                        st.success("✅ Excel file imported and table updated.")
                        st.rerun()
                    else:
                        st.warning("⚠️ Please upload a valid Excel file before confirming.")

                elif cancel_import:
                    file_state["pdf_section_reimport_temp_df"] = None
                    file_state["pdf_section_show_excel_reimport"] = False
                    st.info("❌ Reimport cancelled.")
                    st.rerun()

        # Button to toggle Edit Table UI
        if st.button("✏️ Edit Table", key="pdf_section_edit_button"):
            file_state["pdf_section_edit_mode"] = True

        # Edit Table UI
        if file_state["pdf_section_edit_mode"]:
            with st.form("pdf_section_edit_form"):
                st.subheader("Edit PDF Section Table")
                st.write("Edit the table directly below and click **Save PDF Sections** to apply changes.")
                editable_pdf_section_df = file_state["pdf_section_df"]
                edited_pdf_section_df = st.data_editor(editable_pdf_section_df, use_container_width=True)

                confirm_edit = st.form_submit_button("✅ Save PDF Sections")
                cancel_edit = st.form_submit_button("❌ Cancel")

                if confirm_edit:
                    file_state["pdf_section_df"] = edited_pdf_section_df
                    file_state["pdf_section_edit_mode"] = False
                    st.success("✅ PDF Section data updated.")
                    st.rerun()

                elif cancel_edit:
                    file_state["pdf_section_edit_mode"] = False
                    st.info("❌ Edit cancelled.")
                    st.rerun()

        # Image Preview UI
        st.subheader("Preview: Parts Images")
        if st.button("Display Image Previews"):
            display_image_previews(file_state["pdf_section_df"], "", file_state["brand"])

    # upload pdf_info, mpl_df, pdf_section_df, pdf_log
    if st.button("Upload Data to Database"):
        try:
            # Start a new SQLAlchemy session (transactional scope)
            Session = sessionmaker(bind=engine)
            session = Session()

            with session.begin():
                file_state["pdf_info"].to_sql("pdf_info", session.connection(), if_exists="append", index=False)
                file_state["pdf_section_df"].to_sql("pdf_section", session.connection(), if_exists="append", index=False)
                file_state["mpl_df"].to_sql("master_parts_list", session.connection(), if_exists="append", index=False)
                file_state["pdf_log"].to_sql("pdf_log", session.connection(), if_exists="append", index=False)

            st.success("Upload completed successfully.")

        except Exception as e:
            st.error(f"❌ Upload failed: {e}")
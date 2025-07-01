# Data editor not working, bugs site
# Cannot make changes to form then rerun, stays the same
# if form != stored form, changes_made = True then can rerun
from imports import *

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
        "image_df": None
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

# --- If brand changed → reset fields ---
if st.session_state.brand_select != file_state["previous_brand"]:
    file_state["brand"] = st.session_state.brand_select
    file_state["batch_id"] = extract_batch_id(filename, file_state["brand"])
    file_state["year"] = extract_year(filename, file_state["brand"])
    file_state["model"] = extract_model(filename)
    file_state["previous_brand"] = st.session_state.brand_select
    file_state["preview_clicked"] = False

if current_brand == "Select a Brand":
    st.warning("Please select a brand.")
    st.stop()

# --- FORM (page variables) ---
st.subheader("Data Preview")
st.info("Please review all form fields. All values were auto-filled from the file name or loaded from previous session and may require correction.")

form_model = st.text_input("Model:", value=file_state["model"])
form_batch_id = st.text_input("Batch ID:", value=file_state["batch_id"])
form_year = st.text_input("Year:", value=file_state["year"])

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
    checked_form = st.checkbox("Checked form fields?")

preview_enabled = form_accepted and checked_form

if st.button("Preview Data", disabled=not preview_enabled):
    st.session_state["Updated"] = True
    # Copy form to session state
    file_state["model"] = form_model
    file_state["batch_id"] = form_batch_id
    file_state["year"] = form_year
    file_state["preview_clicked"] = True

# --- MAIN PROCESSING ---
if file_state["preview_clicked"] and form_filled:
    file_state["pdf_id"] = file_state["model"] + "_" + file_state["batch_id"]

    if file_state["mpl_df"] is None or file_state["image_df"] is None:
        parameters = [
            uploaded_file.read(),
            file_state["pdf_id"],
            file_state["brand"],
            file_state["model"],
            file_state["batch_id"],
            file_state["year"]
        ]

        if file_state["brand"] == "Yamaha":
            processor = YamahaProcessor(*parameters)

        elif file_state["brand"] == "Honda":
            processor = HondaProcessor(*parameters)

        with st.status("Extracting Parts Data") as status:
            start_time = time.time()
            file_state["pdf_info"] = processor.get_pdf_info()
            file_state["mpl_df"] = processor.extract_text()
            total_time = time.time() - start_time
            status.update(label=f"Parts data extraction completed in {total_time:.2f} seconds.", state="complete")

        with st.status("Extracting Images") as status:
            start_time = time.time()
            file_state["image_df"] = processor.extract_images()
            total_time = time.time() - start_time
            status.update(label=f"Parts image extraction completed in {total_time:.2f} seconds.", state="complete")

    # --- DISPLAY ---
    if file_state["pdf_info"] is not None:
        st.subheader("PDF Information Preview")
        st.data_editor(file_state["pdf_info"], use_container_width=True)

    if file_state["mpl_df"] is not None:
        st.subheader("Master Parts List Preview")
        st.data_editor(file_state["mpl_df"], use_container_width=True)

    if file_state["image_df"] is not None:
        st.subheader("Parts Images Preview")
        st.dataframe(file_state["image_df"], use_container_width=True)
        display_image_previews(file_state["image_df"], "Preview: Parts Images", file_state["brand"])

    # import zipfile

    # if file_state["image_df"] is not None and not file_state["image_df"].empty:
    #     st.subheader("Download All Parts Images")

    #     # Create ZIP in memory
    #     zip_buffer = BytesIO()
    #     with zipfile.ZipFile(zip_buffer, "w") as zip_file:
    #         for idx, row in file_state["image_df"].iterrows():
    #             image_bytes = row["image"]  # Assuming this is already binary
    #             image_name = f"{row['pdf_id']}_{row['section']}.jpg"
    #             zip_file.writestr(image_name, image_bytes)

    #     zip_buffer.seek(0)

    #     st.download_button(
    #         label="📦 Download All Images as ZIP",
    #         data=zip_buffer,
    #         file_name=f"{file_state['pdf_id']}.zip",
    #         mime="application/zip"
    #     )


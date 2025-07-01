# Without session state, makes page reload and lose all data after changes
from imports import *

def advanced_display_image_previews(image_data, title, brand):
    st.subheader(title)

    if brand == "Honda": # Long Images
        num_cols = 5
    elif brand == "Yamaha": # Tall Images
        num_cols = 6

    # Pagination settings
    rows_per_page = 2  # show 2 rows at a time
    total_rows = (len(image_data) + num_cols - 1) // num_cols  # total rows of images
    total_pages = (total_rows + rows_per_page - 1) // rows_per_page

    # Init page number in session state
    if "image_page" not in st.session_state:
        st.session_state.image_page = 0

    # Calculate which rows to show
    start_row = st.session_state.image_page * rows_per_page
    end_row = start_row + rows_per_page

    # Slice image data
    rows = [image_data[i:i + num_cols] for i in range(0, len(image_data), num_cols)]
    rows_to_show = rows[start_row:end_row]

    # Display images
    for row in rows_to_show:
        cols = st.columns(num_cols)
        for i, item in enumerate(row):
            image = Image.open(BytesIO(item['image']))
            with cols[i]:
                st.image(
                    image,
                    caption=f"PDF ID: {item['pdf_id']}\nSection: {item['section']}",
                    use_container_width=True
                )

    # --- Navigation buttons at the bottom ---
    st.markdown("---")  # horizontal line

    # Show current page info
    st.write(f"Page {st.session_state.image_page + 1} of {total_pages}")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("⬅️ Back", key="image_back", disabled=(st.session_state.image_page == 0)):
            st.session_state.image_page -= 1

    with col3:
        if st.button("Next ➡️", key="image_next", disabled=(st.session_state.image_page >= total_pages - 1)):
            st.session_state.image_page += 1


st.title("Manual Imports")

# Sidebar info
st.sidebar.markdown("""
**For More Infomation**
-         
""")

mpl_df = image_df = image_preview = None

# File Upload
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf", key="file")
if uploaded_file is None:
    st.warning("Please upload a PDF file.")
    st.stop()

# Brand Dropdown Selection
brand_options = ["Select a Brand", "Yamaha", "Honda"]
brand = st.selectbox("Brand:", brand_options)

if brand == "Select a Brand":
    st.warning("Please select a brand.")
    st.stop()

# Extract filename-based defaults
filename = uploaded_file.name
model_default = extract_model(filename)
batch_id_default = extract_batch_id(filename, brand)
year_default = extract_year(filename, brand)

st.subheader("Data Preview")
st.info("Please review all form fields. All values were auto-filled from the file name and may require correction.")

# Form
model = st.text_input("Model:", value=model_default, key="model")
batch_id = st.text_input("Batch ID:", value=batch_id_default, key="batch_id")
year = st.text_input("Year:", value=year_default, key="year")

form_filled = all([str(model).strip(), str(batch_id).strip(), str(year).strip()])

form_accepted = False
if not form_filled:
    st.warning("Please fill in all fields to enable Preview.")
elif not re.fullmatch(r"\d{4}", str(year).strip()):
    st.error("Please enter a valid Year (format: YYYY).")
else:
    form_accepted = True

checked_form = False
if form_accepted:
    checked_form = st.checkbox("Checked form fields?")

preview_enabled = form_accepted and checked_form
preview_clicked = st.button("Preview Data", disabled=not preview_enabled)

if preview_clicked:
    pdf_id = model + '_' + batch_id

    if brand == "Yamaha":
        processor = YamahaProcessor(uploaded_file.read(), pdf_id, brand, model, batch_id, year)
    elif brand == "Honda":
        processor = HondaProcessor(uploaded_file.read(), pdf_id, brand, model, batch_id, year)

    with st.status("Extracting Parts Data") as status:
        start_time = time.time()
        mpl_df = processor.extract_text()
        total_time = time.time() - start_time
        status.update(label=f"Parts data extraction completed in {total_time:.2f} seconds. Click to Preview Table", state="complete")
    
        if mpl_df is not None:
            st.subheader("Master Parts List Preview")
            st.data_editor(mpl_df, use_container_width=True)
        
    with st.status("Extracting Images") as status:
        start_time = time.time()
        image_df = processor.extract_images()
        image_preview = []
        for _, row in image_df.iterrows():
            image_preview.append({
                'pdf_id': row['pdf_id'],
                'section': row['section'],
                'image': row['image']
            })
        total_time = time.time() - start_time
        status.update(label=f"Parts image extraction completed in {total_time:.2f} seconds. Click to Preview Table and Images", state="complete")

        if image_df is not None:
            st.subheader("Parts Images Preview")
            st.dataframe(image_df, use_container_width=True)

        if image_preview is not None:
            advanced_display_image_previews(image_preview, "Preview: Parts Images", brand)

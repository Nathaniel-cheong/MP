# Most update VER of manual_import.py for testing

# Add a check if data is already in database, Reject form > User to Delete > re-import
# Add pdf_id at the start to each pickle file, so that can restore multiple files instead of only recently uploaded
from imports import *

st.title("Testing - Manual Imports ")

# Sidebar info
st.sidebar.markdown("""
**For Your Infomation**
- a
- b
""")

# Select Brand
brand_options = ["Select a Brand", "Yamaha", "Honda"]
brand = st.selectbox("Brand:", brand_options)

if brand == "Select a Brand":
    st.warning("Please select a brand.")
    st.stop()

# File Upload
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf", key="file")
if uploaded_file is None:
    st.warning("Please upload a PDF file.")
    st.stop()

# Extract filename-based defaults
filename = uploaded_file.name
pdf_id_default = extract_pdf_id(filename, brand)
year_default = extract_year(filename, brand)
model_default = extract_model(filename, brand)

st.subheader("Data Preview")
st.info("Please review all form fields. \nAll values were auto-filled from the file name and may require correction.")

# --- Form ---
with st.form("pdf_metadata_form"):
    pdf_id = st.text_input("PDF ID:", value=pdf_id_default, key="pdf_id")
    year = st.text_input("Year:", value=year_default, key="year")
    model = st.text_input("Bike Models (Separate each model with a comma E.g. B65P, B65R, B65S):",
                          value=model_default, key="model")

    num_model_parts = len([m for m in model_default.split(",") if m.strip()])
    num_model = st.number_input("Number of Bike Model:", value=num_model_parts, step=1, key="num_model")

    preview_clicked = st.form_submit_button("Preview Data")

# --- Restore previously processed data (AFTER the form) ---
if not preview_clicked:
    cached_filename = load_from_cache(f"last_uploaded_filename.pkl")
    # Only restore if same file
    if cached_filename == uploaded_file.name:
        df_parts = load_from_cache("master_parts_list.pkl")
        df_images = load_from_cache("parts_images.pkl")
        render_blocks = load_from_cache("image_previews.pkl")

        if df_parts is not None:
            st.subheader("master_parts_list table (Restored):")
            st.dataframe(df_parts, use_container_width=True)

        if df_images is not None:
            st.subheader("parts_images table (Restored):")
            st.dataframe(df_images, use_container_width=True)

        if render_blocks is not None:
            st.subheader("📸 Preview: Parts Images (Restored)")
            rows = [render_blocks[i:i + 5] for i in range(0, len(render_blocks), 5)]
            for row in rows:
                cols = st.columns(5)
                for i, block in enumerate(row):
                    with cols[i]:
                        st.markdown(block, unsafe_allow_html=True)
    else:
        # Don't restore anything — different file
        df_parts = None
        df_images = None
        render_blocks = None

# --- On Submit ---
if preview_clicked:
    save_to_cache(uploaded_file.name, "last_uploaded_filename.pkl")
    if not re.fullmatch(r"\d{4}", year):
        st.error("Year must be a 4-digit number.")
        st.stop()

    file_bytes = uploaded_file.read()
    file_stream = BytesIO(file_bytes)

    with st.status("Structuring master_parts_list", expanded=True) as status:
        # ----------- master_parts_list -----------
        if brand == "Yamaha":
            raw_text_data = extract_text_from_pdf(file_stream)
            df_parts = yamaha_process_data(raw_text_data, pdf_id, year, model, num_model)

            if not df_parts.empty:
                st.write("master_parts_list table:")
                st.dataframe(df_parts, use_container_width=True)
                status.update(label="master_parts_list structured. Now structuring parts_images...", state="running")
                save_to_cache(df_parts, "master_parts_list.pkl")
            else:
                status.update(label="No parts data found in the PDF.", state="error")
                st.stop()

        elif brand == "Honda":
            st.info("Honda Structuring Logic (Parts List)")
            df_parts = pd.DataFrame()  # placeholder
            save_to_cache(df_parts, "master_parts_list.pkl")
            status.update(label="Honda master_parts_list processed.", state="running")

        # ----------- parts_images -----------
        if brand == "Yamaha":
            st.write("parts_images table:")
            file_stream.seek(0)
            df_images = extract_images_with_fig_labels(file_stream, pdf_id, engine)
            st.dataframe(df_images, use_container_width=True)
            save_to_cache(df_images, "parts_images.pkl")

            if not df_images.empty:
                st.subheader("📸 Preview: Parts Images")

                image_data = []
                for _, row in df_images.iterrows():
                    image_data.append({
                        'pdf_id': row['pdf_id'],
                        'section': row['section'],
                        'image': row['image']
                    })

                render_blocks = []
                for item in image_data:
                    image = Image.open(BytesIO(item['image']))
                    buf = BytesIO()
                    image.save(buf, format='PNG')
                    img_base64 = base64.b64encode(buf.getvalue()).decode()
                    html_block = f"""
                        <div style="text-align: center; margin: 0px;">
                            <img src="data:image/png;base64,{img_base64}" height="200"/>
                            <p style="font-size: small;">PDF ID: {item['pdf_id']}<br>Section: {item['section']}</p>
                        </div>
                    """
                    render_blocks.append(html_block)

                save_to_cache(render_blocks, "image_previews.pkl")

                rows = [render_blocks[i:i + 5] for i in range(0, len(render_blocks), 5)]
                for row in rows:
                    cols = st.columns(5)
                    for i, block in enumerate(row):
                        with cols[i]:
                            st.markdown(block, unsafe_allow_html=True)
            else:
                st.warning("No new parts images found.")

            status.update(label="Data structuring completed.", state="complete")

        elif brand == "Honda":
            st.info("Honda Structuring Logic (Parts Images)")
            df_images = pd.DataFrame()
            render_blocks = []
            save_to_cache(df_images, "parts_images.pkl")
            save_to_cache(render_blocks, "image_previews.pkl")
            status.update(label="Honda parts_images processed.", state="complete")

# --- Upload to DB and Clear Cache Button ---
if st.button("Upload to Database"):
    # Clear the cache and uploade to database
    for fname in ["master_parts_list.pkl", "parts_images.pkl", "image_previews.pkl", "last_uploaded_filename.pkl"]:
        path = os.path.join(CACHE_DIR, fname)
        if os.path.exists(path):
            os.remove(path)

    st.success("Data successfully uploaded.")
    
def original_homepage():
    st.title("Homepage")

    # Reflect existing tables
    metadata = MetaData()
    metadata.reflect(bind=engine)

    # Access tables
    master_parts_list = metadata.tables.get("master_parts_list")

    if master_parts_list is not None:
        # --- Fetch distinct filter options ---
        with engine.connect() as conn:
            # Fetch Brands
            brand_column = master_parts_list.c.brand
            brand_result = conn.execute(select(brand_column.distinct()).order_by(brand_column)).fetchall()
            brands = [row[0] for row in brand_result if row[0] is not None]

            # Fetch years
            year_column = master_parts_list.c.year
            year_result = conn.execute(select(year_column.distinct()).order_by(year_column)).fetchall()
            years = [row[0] for row in year_result if row[0] is not None]

        # --- Filter Widgets ---
        brands.insert(0, "All")
        selected_brand = st.selectbox("Filter by Brand", brands)

        years.insert(0, "All")
        selected_year = st.selectbox("Filter by Year", years)

        # --- Build query with filters ---
        stmt = select(master_parts_list)
        if selected_year != "All":
            stmt = stmt.where(master_parts_list.c.year == selected_year)

        if selected_brand != "All":
            stmt = stmt.where(master_parts_list.c.brand == selected_brand)

        # --- Execute and display results ---
        with engine.connect() as conn:
            result = conn.execute(stmt)
            rows = result.fetchall()

        if rows:
            df = pd.DataFrame(rows, columns=result.keys())
            st.subheader("master_parts_list Table")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No results found for the selected filters.")
    else:
        st.warning("master_parts_list table not found.")
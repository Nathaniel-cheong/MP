from imports import *

st.title("Manual Imports")

def display_image_previews(image_data, title="📸 Preview: Parts Images"):
    st.subheader(title)
    rows = [image_data[i:i + 6] for i in range(0, len(image_data), 6)]
    for row in rows:
        cols = st.columns(6)
        for i, item in enumerate(row):
            image = Image.open(BytesIO(item['image']))
            with cols[i]:
                st.image(
                    image,
                    caption=f"PDF ID: {item['pdf_id']}\nSection: {item['section']}",
                    use_container_width=True
                )

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

# --- Attempt to load cache for current file ---
df_parts = load_from_cache(f"{filename}_master_parts_list.pkl")
df_images = load_from_cache(f"{filename}_parts_images.pkl")
image_preview = load_from_cache(f"{filename}_image_previews.pkl")

if not preview_clicked and df_parts is not None and df_images is not None and image_preview is not None:
    st.success(f"✅ Session restored with data for `{filename}`.")

    st.subheader("master_parts_list table (Restored):")
    st.data_editor(df_parts, use_container_width=True)

    st.subheader("parts_images table (Restored):")
    st.dataframe(df_images, use_container_width=True)

    display_image_previews(image_preview, title="📸 Preview: Parts Images (Restored)")

# --- On Submit ---
if preview_clicked:
    if not re.fullmatch(r"\d{4}", year):
        st.error("Year must be a 4-digit number.")
        st.stop() # Remove this

    file_bytes = uploaded_file.read()
    file_stream = BytesIO(file_bytes)

    with st.status("Structuring master_parts_list", expanded=True) as status:
        # ----------- master_parts_list -----------
        if brand == "Yamaha":
            raw_text_data = extract_text_from_pdf(file_stream)
            df_parts = yamaha_process_data(raw_text_data, pdf_id, year, model, num_model)

            if not df_parts.empty:
                st.write("master_parts_list table:")
                st.data_editor(df_parts, use_container_width=True)
                save_to_cache(df_parts, f"{filename}_master_parts_list.pkl")
                status.update(label="master_parts_list structured. Now structuring parts_images...", state="running")
            else:
                status.update(label="No parts data found in the PDF.", state="error")

        elif brand == "Honda":
            st.info("Honda Structuring Logic (Parts List)")
            df_parts = pd.DataFrame()
            status.update(label="Honda master_parts_list processed.", state="complete")

        # ----------- parts_images -----------
        if brand == "Yamaha":
            st.write("parts_images table:")
            file_stream.seek(0)
            df_images = extract_images_with_fig_labels(file_stream, pdf_id, engine)
            st.dataframe(df_images, use_container_width=True)
            save_to_cache(df_images, f"{filename}_parts_images.pkl")

            if not df_images.empty:
                st.subheader("📸 Preview: Parts Images")

                image_preview = []
                for _, row in df_images.iterrows():
                    image_preview.append({
                        'pdf_id': row['pdf_id'],
                        'section': row['section'],
                        'image': row['image']
                    })

                display_image_previews(image_preview)
                save_to_cache(image_preview, f"{filename}_image_previews.pkl")

            else:
                st.warning("No new parts images found.")

            status.update(label="Data structuring completed.", state="complete")

        elif brand == "Honda":
            st.info("Honda Structuring Logic (Parts Images)")
            df_images = pd.DataFrame()
            image_preview = []
            status.update(label="Honda parts_images processed.", state="complete")
    
    st.subheader("Any Changes")
    updated_table = st.file_uploader("Upload Updated Table", type="csv", key="updated_table")

# --- Upload to DB and Clear Cache Button ---
if st.button("Upload to Database"):
    for fname in os.listdir(CACHE_DIR):
        if fname.startswith(f"{filename}_"):
            os.remove(os.path.join(CACHE_DIR, fname))
    
    st.success("Data successfully uploaded.")
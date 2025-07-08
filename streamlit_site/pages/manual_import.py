from imports import *

st.title("Manual Imports")

# ----------------- Session State Initialization -----------------
if 'pdf_id' not in st.session_state:
    st.session_state.pdf_id = ""
    st.session_state.year = ""
    st.session_state.model = ""
    st.session_state.num_model = 0
    st.session_state.file_bytes = None
    st.session_state.df_parts = None
    st.session_state.df_images = None
    st.session_state.image_data = []

# ----------------- Sidebar Info -----------------
st.sidebar.markdown("""
**For Your Information**
- a
- b
""")

# ----------------- Brand Selection -----------------
brand_options = ["Select a Brand", "Yamaha", "Honda"]
brand = st.selectbox("Brand:", brand_options)

if brand == "Select a Brand":
    st.warning("Please select a brand.")
    st.stop()

# ----------------- File Upload -----------------
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

if uploaded_file is not None:
    st.session_state.file_bytes = uploaded_file.read()
    filename = uploaded_file.name
    st.session_state.pdf_id = extract_pdf_id(filename, brand)
    st.session_state.year = extract_year(filename, brand)
    st.session_state.model = extract_model(filename, brand)

if st.session_state.file_bytes is None:
    st.warning("Please upload a PDF file.")
    st.stop()

# ----------------- Data Preview -----------------
st.subheader("Data Preview")

# PDF ID (readonly)
st.text_input("PDF ID:", value=st.session_state.pdf_id, disabled=True)

# Year Input with Validation
st.session_state.year = st.text_input("Year:", value=st.session_state.year)
if st.session_state.year and not re.fullmatch(r"\d{4}", st.session_state.year):
    st.error("Year must be a 4-digit number.")
    st.stop()

# Model Input
st.session_state.model = st.text_input("Bike Models (Separate each model with a comma E.g. B65P, B65R, B65S):", value=st.session_state.model)
st.session_state.num_model = st.number_input(
    "Number of Bike Model:",
    value=len([m for m in st.session_state.model.split(",") if m.strip()]),
    step=1
)

# ----------------- Preview Button -----------------
form_filled = all([
    st.session_state.pdf_id,
    st.session_state.year,
    st.session_state.model.strip(),
    st.session_state.num_model
])
if st.button("Preview Data", disabled=not form_filled):
    file_stream = BytesIO(st.session_state.file_bytes)

    with st.status("Structuring Data...", expanded=True) as status:
        # ----------- Process master_parts_list -----------
        if brand == "Yamaha":
            raw_text_data = extract_text_from_pdf(file_stream)
            st.session_state.df_parts = yamaha_process_data(
                raw_text_data,
                st.session_state.pdf_id,
                st.session_state.year,
                st.session_state.model,
                st.session_state.num_model
            )

            if st.session_state.df_parts is not None and not st.session_state.df_parts.empty:
                st.write("master_parts_list table:")
                st.dataframe(st.session_state.df_parts, use_container_width=True)
                status.update(label="master_parts_list structured, structuring parts_images.", state="running")
            else:
                status.update(label="No parts data found in the PDF.", state="error")
                st.stop()

        elif brand == "Honda":
            st.info("Honda Structuring Logic (Parts List)")
            status.update(label="Honda master_parts_list processed.", state="running")

        # ----------- Process parts_images -----------
        if brand == "Yamaha":
            st.write("parts_images table:")
            file_stream.seek(0)
            st.session_state.df_images = extract_images_with_fig_labels(file_stream, st.session_state.pdf_id, engine)

            if st.session_state.df_images is not None and not st.session_state.df_images.empty:
                st.dataframe(st.session_state.df_images, use_container_width=True)

                st.session_state.image_data = []
                for _, row in st.session_state.df_images.iterrows():
                    st.session_state.image_data.append({
                        'pdf_id': row['pdf_id'],
                        'section': row['section'],
                        'image': row['image']
                    })

                status.update(label="Data structuring completed.", state="complete")
            else:
                st.warning("No new parts images found.")
                status.update(label="No new parts images found.", state="error")

        elif brand == "Honda":
            st.info("Honda Structuring Logic (Parts Images)")
            status.update(label="Honda parts_images processed.", state="complete")

# ----------------- Display Image Previews -----------------
if st.session_state.image_data:
    st.subheader("📸 Preview: Parts Images")

    render_blocks = []
    for item in st.session_state.image_data:
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

    rows = [render_blocks[i:i + 5] for i in range(0, len(render_blocks), 5)]
    for row in rows:
        cols = st.columns(5)
        for i, block in enumerate(row):
            with cols[i]:
                st.markdown(block, unsafe_allow_html=True)
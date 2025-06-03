# Make form values persist
from imports import *

st.title("Manual Imports")

# Sidebar
st.sidebar.markdown("""
**For Your Infomation**
- a
- b
""")

# Set default value if session key doesn't exist
brand_options = ["Select a Brand", "Yamaha", "Honda"]
default_brand = st.session_state.get("brand", "Select a Brand")
brand = st.selectbox(
    "Brand:",
    brand_options, 
    index=brand_options.index(default_brand), 
    key="brand"
)

if brand == "Select a Brand":
    st.warning("Please select a brand.")
    st.stop()

else:
    # File Upload
    uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
    if uploaded_file is None:
        st.warning("Please upload a PDF file.")
        st.stop()

    else:
        # Process the file
        filename = uploaded_file.name

        # Extract values
        pdf_id = extract_pdf_id(filename, brand)
        year = extract_year(filename, brand)
        model = extract_model(filename, brand)

        st.subheader("Data Preview")

        # Form Fields
        pdf_id = st.text_input("PDF ID:", value=pdf_id, disabled=True)

        year = st.text_input("Year:", value=year)
        if year and not re.fullmatch(r"\d{4}", year):
            st.error("Year must be a 4-digit number.")

        else:
            model = st.text_input("Bike Models (Separate each model with a comma E.g. B65P, B65R, B65S):", value=model)

            # Validate model input
            num_model_parts = len([m for m in model.split(",") if m.strip()])
            num_model = st.number_input("Number of Bike Model:", value=num_model_parts, step=1)

            # Enable preview button only if form is filled
            form_filled = all([pdf_id, year, model.strip(), num_model])
            preview_clicked = st.button("Preview Data", disabled=not form_filled)

            if preview_clicked:
                file_bytes = uploaded_file.read()
                file_stream = BytesIO(file_bytes)

                with st.status("Structuring Data...", expanded=True) as status:
                    # ----------- Process master_parts_list -----------
                    if brand == "Yamaha":
                        raw_text_data = extract_text_from_pdf(file_stream)
                        df_parts = yamaha_process_data(raw_text_data, pdf_id, year, model, num_model)

                        if not df_parts.empty:
                            st.write("master_parts_list table:")
                            st.dataframe(df_parts, use_container_width=True)
                            status.update(label="master_parts_list structured, sturcturing parts_images.", state="running")
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
                        df_images = extract_images_with_fig_labels(file_stream, pdf_id, engine)
                        st.dataframe(df_images, use_container_width=True)

                        if not df_images.empty:
                            st.subheader("📸 Preview: Parts Images")

                            image_data = []
                            for _, row in df_images.iterrows():
                                image_data.append({
                                    'pdf_id': row['pdf_id'],
                                    'section': row['section'],
                                    'image': row['image']
                                })

                            # Convert images to base64 for fast HTML rendering
                            render_blocks = []
                            for item in image_data:
                                image = Image.open(BytesIO(item['image']))  # Convert bytes to PIL Image
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

                            # Display in rows of 5
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
                        status.update(label="Honda parts_images processed.", state="complete")

                upload_button = st.button("Upload to Database", help="Currently does nothing")
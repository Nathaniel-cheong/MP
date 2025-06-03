from imports import *

st.title("View Images")

metadata = MetaData()
parts_images = Table('parts_images', metadata, autoload_with=engine)

# --- Cache pdf_id list ---
@st.cache_data
def get_pdf_ids():
    Session = sessionmaker(bind=engine)
    session = Session()
    result = session.query(parts_images.c.pdf_id).distinct().order_by(parts_images.c.pdf_id).all()
    session.close()
    return [row[0] for row in result]

# --- Cache image results by pdf_id ---
@st.cache_data
def get_images_for_pdf_id(pdf_id):
    Session = sessionmaker(bind=engine)
    session = Session()
    results = session.execute(
        parts_images.select()
        .where(parts_images.c.pdf_id == pdf_id)
        .with_only_columns(
            parts_images.c.pdf_id,
            parts_images.c.section,
            parts_images.c.image
        )
    ).fetchall()
    session.close()

    image_data = []
    for row in results:
        pdf_id, section, image_binary = row
        image_data.append({'pdf_id': pdf_id, 'section': section, 'image_binary': image_binary})
    return image_data

# --- UI and rendering ---
pdf_ids = get_pdf_ids()
selected_pdf_id = st.selectbox("Select a PDF ID", pdf_ids)

if selected_pdf_id:
    image_data = get_images_for_pdf_id(selected_pdf_id)

    render_blocks = []
    for item in image_data:
        image = Image.open(BytesIO(item['image_binary']))
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

    # 5 per row
    rows = [render_blocks[i:i + 5] for i in range(0, len(render_blocks), 5)]
    for row in rows:
        cols = st.columns(5)
        for i, block in enumerate(row):
            with cols[i]:
                st.markdown(block, unsafe_allow_html=True)

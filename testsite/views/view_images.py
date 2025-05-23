import io
import base64
from PIL import Image
from imports import *  # Your custom import where `engine`, `st`, etc. are defined

st.title("View Images")

# Step 1: Setup session and table
Session = sessionmaker(bind=engine)
session = Session()

metadata = MetaData()
parts_images = Table('parts_images', metadata, autoload_with=engine)

# Step 2: Get unique PDF IDs for filtering
pdf_ids = session.query(parts_images.c.pdf_id).distinct().order_by(parts_images.c.pdf_id).all()
pdf_ids = [row[0] for row in pdf_ids]  # Flatten list of tuples

# Step 3: Show selectbox to filter by PDF ID
selected_pdf_id = st.selectbox("Select a PDF ID", pdf_ids)

# Step 4: Query and display images only for selected PDF ID
if selected_pdf_id:
    results = session.execute(
        parts_images.select()
        .where(parts_images.c.pdf_id == selected_pdf_id)
        .with_only_columns(
            parts_images.c.pdf_id,
            parts_images.c.section,
            parts_images.c.image
        )
    ).fetchall()

    image_data = []
    for row in results:
        pdf_id, section, image_binary = row
        image = Image.open(io.BytesIO(image_binary))
        image_data.append({'pdf_id': pdf_id, 'section': section, 'image': image})

    # Step 5: Display images in rows of 5 using base64 HTML for speed
    render_blocks = []
    for item in image_data:
        buf = io.BytesIO()
        item['image'].save(buf, format='PNG')
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
# views/view_images.py

from imports import *              # should bring in: engine, sessionmaker, etc.
import streamlit as st
from sqlalchemy import Table, MetaData
from sqlalchemy.orm import sessionmaker
from PIL import Image
from io import BytesIO
import base64

st.title("View Images")

# —– Create a session —–
Session = sessionmaker(bind=engine)
session = Session()

# —– Reflect just the parts_images table —–
metadata = MetaData()
parts_images = Table('parts_images', metadata, autoload_with=engine)

# —– Fetch distinct PDF IDs to populate the selectbox —–
pdf_ids = (
    session.query(parts_images.c.pdf_id)
    .distinct()
    .order_by(parts_images.c.pdf_id)
    .all()
)
pdf_ids = [row[0] for row in pdf_ids]

selected_pdf_id = st.selectbox("Select a PDF ID", pdf_ids)

if selected_pdf_id is not None:
    # Build a SELECT that only pulls the three columns we need
    stmt = (
        parts_images
        .select()  # SELECT * FROM parts_images
        .with_only_columns([
            parts_images.c.pdf_id,
            parts_images.c.section,
            parts_images.c.image
        ])
        .where(parts_images.c.pdf_id == selected_pdf_id)
    )

    results = session.execute(stmt).fetchall()

    render_blocks = []
    for pdf_id, section, image_binary in results:
        img = Image.open(BytesIO(image_binary))
        buf = BytesIO()
        img.save(buf, format='PNG')
        img_b64 = base64.b64encode(buf.getvalue()).decode()

        render_blocks.append(f"""
            <div style="text-align:center; margin:0;">
              <img src="data:image/png;base64,{img_b64}" height="200"/>
              <p style="font-size:small;">
                PDF ID: {pdf_id}<br/>Section: {section}
              </p>
            </div>
        """)

    # Layout the images in rows of 5 columns
    rows = [render_blocks[i:i + 5] for i in range(0, len(render_blocks), 5)]
    for row in rows:
        cols = st.columns(5)
        for col, block in zip(cols, row):
            with col:
                st.markdown(block, unsafe_allow_html=True)

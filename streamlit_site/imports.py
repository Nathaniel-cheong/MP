import os
import re
import base64
import streamlit as st
import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
import pickle

# For Image Display within the df
from IPython.display import Image
from PIL import Image, ImageOps
from io import BytesIO

# --- DATABASE SETUP ---
from sqlalchemy import (select, create_engine, text, Table, Column, Integer, String, MetaData, ForeignKey, LargeBinary)
from sqlalchemy.orm import sessionmaker

username = "tpmpams_user"
password = "X5Lx2fWLXQ18cxaEngOODl3gXtMq7H8f"
host = "dpg-d0r91k2dbo4c73a4kip0-a.singapore-postgres.render.com"
port = "5432"
database = "tpmpams"

# SQLAlchemy connection URL
DATABASE_URL = f"postgresql://{username}:{password}@{host}:{port}/{database}"

# Create engine
engine = create_engine(DATABASE_URL)

# --- YAMAHA DATA EXTRACTION ---
def extract_pdf_id(pdf_path, brand):
    base_filename = os.path.basename(pdf_path).split('.')[0]

    if brand == "Yamaha":
        match = re.match(r"([A-Za-z0-9 ]+)", base_filename)
        if match:
            return match.group(1).replace(" ", "")  # Remove all spaces
        return None

    elif brand == "Honda":
        # Look for '13' followed by 6 alphanumeric characters
        match = re.search(r"13[A-Z0-9]{6}", base_filename)
        if match:
            return match.group(0)
        return None

def extract_year(pdf_path, brand):
    if brand == "Yamaha":
        year_match = re.search(r"'(\d{2})", pdf_path)
        return f"20{year_match.group(1)}" if year_match else None

def extract_model(pdf_path, brand):
    base_filename = os.path.basename(pdf_path).split('.')[0]

    if brand == "Yamaha":
        # Extract model codes inside parentheses, e.g., "(B65P, B65R, B65S)"
        match = re.search(r"\((.*?)\)", base_filename)
        if match:
            return match.group(1).strip()  # return content inside parentheses
        return None

    elif brand == "Honda":
        # Extract bike model from start until the first non-alphanumeric character
        match = re.match(r"^([A-Z0-9]+)", base_filename)
        if match:
            return match.group(1)
        return None

# ---------- TEXT EXTRACTION ----------
def extract_text_from_pdf(pdf_path):
    all_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            lines = text.split('\n')
            first_line = lines[0].strip() if lines else ""
            if not any("FIG." in line for line in lines):
                continue
            if "NUMERICAL INDEX" in first_line:
                break
            all_text += f"\n--- Page {page_num + 1} ---\n{text}\n"
    return all_text

def yamaha_process_data(text, pdf_id, year, model, num_model):
    rows = []
    lines = text.strip().split('\n')
    section = c_name = prev_fig_no = prev_c_name = prev_ref_no = ""
    collect_data = False

    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith('FIG.'):
            tokens = line.split()
            if len(tokens) >= 3:
                section = tokens[1]
                c_name = " ".join(tokens[2:])
                prev_fig_no, prev_c_name = section, c_name
                collect_data = True
            continue
        if not collect_data: continue
        if not section:
            section, c_name = prev_fig_no, prev_c_name

        parts = line.split()
        is_valid_data_line = (
            len(parts) >= 2 and 
            (re.match(r'\w+[-–]\w+', parts[0]) or parts[0].isdigit())
        )
        if not is_valid_data_line:
            continue

        if parts[0].isdigit():
            ref_no = parts[0]
            part_no = parts[1]
            rest = parts[2:]
            prev_ref_no = ref_no
        else:
            ref_no = prev_ref_no
            part_no = parts[0]
            rest = parts[1:]

        rest = " ".join(rest).split()
        description = remarks = ""
        numbers = []
        found_numbers = False
        for item in rest:
            if item.isdigit():
                numbers.append(item)
                found_numbers = True
                continue
            if not found_numbers:
                description += item + " "
            else:
                remarks += item + " "
        if len(numbers) > num_model:
            description += numbers[0]

        image_id = "_".join([pdf_id, section])

        rows.append([pdf_id, year, "Yamaha", model, section, c_name, ref_no, part_no, description.strip(), remarks.strip(), image_id])

    return pd.DataFrame(rows, columns=[
        'pdf_id', 'year', 'brand', 'model', 'section', 'component_name',
        'ref_no', 'part_no', 'description', 'remarks', 'image_id'
    ])

# ---------- IMAGE EXTRACTION ----------
def normalize_image_background(image_bytes):
    img = Image.open(BytesIO(image_bytes)).convert("L")  # Grayscale
    mean_brightness = sum(img.getdata()) / (img.width * img.height)

    if mean_brightness < 128:  # Invert if it's a dark background
        img = ImageOps.invert(img)

    img = img.convert("RGB")  # Convert back to RGB

    output = BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()

def get_existing_fig_combos(engine, pdf_id):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT section FROM parts_images WHERE pdf_id = :pdf_id"),
            {"pdf_id": pdf_id}
        )
        return set(str(row[0]) for row in result.fetchall())  # Cast to str for consistent comparison

def extract_images_with_fig_labels(pdf_stream, pdf_id, engine):
    doc = fitz.open(stream=pdf_stream, filetype="pdf")
    data = []

    #existing_figs = get_existing_fig_combos(engine, pdf_id)
    seen_figs = set()

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text()

        matches = re.findall(r"FIG\.\s*([\w-]+)", text)
        if not matches:
            continue

        section = matches[0]
        #if section in seen_figs or section in existing_figs:
            #continue

        image_list = page.get_images(full=True)
        if not image_list:
            continue

        xref = image_list[0][0]
        base_image = doc.extract_image(xref)
        image = normalize_image_background(base_image["image"])

        image_id = f"{pdf_id}_{section}"

        data.append({
            "image_id": image_id,
            "pdf_id": pdf_id,
            "section": section,
            "image": image
        })
        seen_figs.add(section)

    return pd.DataFrame(data)

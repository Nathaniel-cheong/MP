import os
import re
import base64
from datetime import datetime, timedelta

import streamlit as st
from streamlit_cookies_controller import CookieController
cookies = CookieController()

import pandas as pd
import pdfplumber
import fitz
from IPython.display import Image
from PIL import Image, ImageOps
from io import BytesIO
from collections import defaultdict

# --- DATABASE SETUP ---
from sqlalchemy import (select, update, delete, distinct, create_engine, text, Table, Column, Integer, String, MetaData, ForeignKey, LargeBinary)
from sqlalchemy.orm import sessionmaker # currently only being used in view_images.py and MP jupyter files
username = "tpmpams_user"
password = "X5Lx2fWLXQ18cxaEngOODl3gXtMq7H8f"
host = "dpg-d0r91k2dbo4c73a4kip0-a.singapore-postgres.render.com"
port = "5432"
database = "tpmpams"
# SQLAlchemy connection URL
DATABASE_URL = f"postgresql://{username}:{password}@{host}:{port}/{database}"
# Create engine
engine = create_engine(DATABASE_URL)

# --- PDF EXTRACTION ---
# Yamaha + Honda
def extract_model(pdf_name):
    # Extract model: start of filename, letters/numbers/spaces until a special character (', _)
    match = re.match(r"([A-Za-z0-9 ]+)", pdf_name)
    if match:
        return match.group(1).replace(" ", "")  # Removes any spaces
def extract_batch_id(pdf_name, brand):
    if brand == "Yamaha":
        # Extract model codes inside parentheses
        match = re.search(r"\((.*?)\)", pdf_name)
        if match:
            parts = match.group(1).split(",")
            clean_parts = [part.strip() for part in parts]
            return "_".join(clean_parts)
    
    elif brand == "Honda":
        # Look for uppercase/digit code between underscores (6–10 characters)
        match = re.search(r"_([A-Z0-9]{6,10})_", pdf_name)
        if match:
            return match.group(1)

    return None
# Yamaha only
def extract_year(pdf_name, brand):
    if brand == "Yamaha":
        year_match = re.search(r"'(\d{2})", pdf_name)
        return f"20{year_match.group(1)}" if year_match else None

    # elif brand == "Honda":
    #     match = re.search(r"(20\d{2}_20\d{2})", pdf_name)
    #     return match.group(1) if match else None

    return None

# --- YAMAHA ---
# Text Extraction
def reconstruct_lines_from_chars(chars, y_tolerance=2.5):
    lines = defaultdict(list)

    for c in chars:
        # Use midpoint instead of top
        y_center = c["top"] + (c["height"] / 2)
        y_bucket = round(y_center / y_tolerance)
        lines[y_bucket].append(c)

    line_texts = []
    for y in sorted(lines.keys()):
        chars_in_line = sorted(lines[y], key=lambda c: c["x0"])
        line = ""
        prev_x = None

        for char in chars_in_line:
            x = char["x0"]
            text = char["text"]

            if prev_x is not None:
                gap = x - prev_x
                if gap > 1.5:
                    line += " " * int(gap / 2.5)

            line += text
            prev_x = char["x1"]

        line_texts.append((y, line.rstrip()))

    return line_texts
def extract_raw_text(pdf_path):
    output_lines = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            chars = page.chars
            raw_lines = reconstruct_lines_from_chars(chars, y_tolerance=5.5)

            # Skip non-parts pages
            if not raw_lines or not raw_lines[0][1].strip().startswith("FIG."):
                continue

            for _, line in raw_lines:
                stripped_line = line.strip()

                # ✅ Skip lines that are just a number (likely page numbers)
                if re.fullmatch(r"\d+", stripped_line):
                    continue

                if stripped_line:
                    output_lines.append(stripped_line)

    return output_lines
def structure_raw_text(raw_lines):
    structured_output = []
    skip_indices = set()

    for i in range(len(raw_lines)):
        if i in skip_indices:
            continue

        line = raw_lines[i].strip()
        parts = re.split(r"\s{2,}", line)

        # --- Normalize FIG. rows to always be ['FIG.', 'number', 'description']
        if parts and isinstance(parts[0], str) and parts[0].startswith("FIG."):
            if re.match(r"^FIG\.\s*\d+$", parts[0]):
                match = re.match(r"^(FIG\.)\s*(\d+)$", parts[0])
                if match:
                    parts = [match.group(1), match.group(2)] + parts[1:]

            elif re.match(r"^FIG\.\d+$", parts[0]):
                match = re.match(r"^(FIG\.)(\d+)$", parts[0])
                if match:
                    parts = [match.group(1), match.group(2)] + parts[1:]

        # --- Skip rows that are just floating descriptions
        if len(parts) == 1 and re.match(r"^[A-Z ,\-0-9]+$", parts[0]):
            continue

        # --- Heuristic: Missing description, try to find it nearby
        if len(parts) >= 2 and not re.search(r"[A-Za-z]", parts[1]):
            # Try backward merge
            if i > 0:
                prev_line = raw_lines[i - 1].strip()
                if len(re.split(r"\s{2,}", prev_line)) == 1:
                    parts.insert(1, prev_line)
                    skip_indices.add(i - 1)

            # Try forward merge
            elif i + 1 < len(raw_lines):
                next_line = raw_lines[i + 1].strip()
                if len(re.split(r"\s{2,}", next_line)) == 1:
                    parts.insert(1, next_line)
                    skip_indices.add(i + 1)

        # --- Extra fix: Split index + part number if mashed into one string
        if parts and re.match(r"^\d+\s+[A-Z0-9–\-]+$", parts[0]):
            split_part = re.split(r"\s+", parts[0], maxsplit=1)
            parts = split_part + parts[1:]

        structured_output.append(parts)

    # --- Final cleanup
    structured_output = [
        row for row in structured_output
        if not (
            (len(row) == 1 and re.match(r"^[A-Z ,\-0-9]+$", row[0])) or
            all(cell.isdigit() for cell in row)  # <-- remove purely numeric rows
        )
    ]

    return structured_output
def convert_to_table(pdf_id, year, brand, model, batch_id, structured_output):
    rows = []
    section = s_name = prev_section = prev_c_name = prev_ref_no = ""

    for line in structured_output:
        if not line or not line[0]:
            continue

        # FIG. section headers
        if line[0] == "FIG." and len(line) >= 3:
            section = line[1]

            raw_name = " ".join(line[2:])  # Full raw name with possible number
            # Remove trailing digits from component name
            s_name = re.sub(r"\s*\d+$", "", raw_name).strip()

            prev_section, prev_c_name = section, s_name
            continue

        # Fallback to previous if not set
        if not section:
            section, s_name = prev_section, prev_c_name

        # Determine if it's a valid data line
        if len(line) >= 2 and (re.match(r'\w+[-–]\w+', line[0]) or line[0].isdigit()):
            if line[0].isdigit():
                ref_no = line[0]
                part_no = line[1]
                rest = line[2:]
                prev_ref_no = ref_no
            else:
                ref_no = prev_ref_no
                part_no = line[0]
                rest = line[1:]
        else:
            continue

        # Extract description and additional info
        description = ""
        remarks = ""
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

        image_id = f"{pdf_id}_{section}"

        rows.append([
            pdf_id, year, brand, model, batch_id, section, s_name,
            ref_no, part_no, description.strip(), remarks.strip(), image_id
        ])

    return pd.DataFrame(rows, columns=[
        'pdf_id', 'year', 'brand', 'model', 'batch_id',
        'section', 'section_name', 'ref_no', 'part_no',
        'description', 'remarks', 'image_id'
    ])
# Image Extraction
def get_existing_fig_combos(engine, pdf_id):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT section FROM parts_images WHERE pdf_id = :pdf_id"),
            {"pdf_id": pdf_id}
        )
        return set(str(row[0]) for row in result.fetchall())  # Cast to str for consistent comparison
# Standardize image
def normalize_image_background(image_bytes):
    img = Image.open(BytesIO(image_bytes)).convert("L")  # Grayscale
    mean_brightness = sum(img.getdata()) / (img.width * img.height)

    if mean_brightness < 128:  # Invert if it's a dark background
        img = ImageOps.invert(img)

    img = img.convert("RGB")  # Convert back to RGB

    output = BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()
# Extract Images and structuring table
def yamaha_extract_images_with_fig_labels(pdf_stream, pdf_id, engine):
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
        if section in seen_figs:
            continue

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

# --- HONDA ---
# Text Extraction
def extract_section_with_layout(pdf_path: str, section_code: str, section_title: str) -> pd.DataFrame:
    """
    Finds a specified section, locates 'Reqd. QTY', extracts in layout mode,
    then parses each part and variant into ref_no, part_no, description, remarks.
    Stops collecting once it encounters any line containing 'PART', 'NO', and 'INDEX'.
    Returns a DataFrame with columns ref_no, part_no, description, remarks.
    """
    code = section_code.upper()
    title = section_title.upper()

    next_sec_re     = re.compile(r'^[A-Z]+-\d+', re.IGNORECASE)
    table_header_re = re.compile(r'\bReqd\.?\s*QTY\b', re.IGNORECASE)
    part_no_re      = re.compile(r'\b[0-9]{5,}(?:-[A-Z0-9-]+)+\b')
    end_re          = re.compile(r'.*PART\s*NO\.?\s*INDEX.*', re.IGNORECASE)

    # Phase 1: locate page range
    start_page = header_hit = None
    end_page = None
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            for ln in (page.extract_text() or "").splitlines():
                u = ln.strip().upper()
                if start_page is None:
                    if (("FRAMEGROUP" in u and u.startswith(code) and title in u)
                        or (u.startswith(code) and title in u)):
                        start_page = i
                        break
                elif not header_hit:
                    if table_header_re.search(u):
                        header_hit = True
                else:
                    if next_sec_re.match(u) and not u.startswith(code):
                        end_page = i
                        break
            if end_page is not None:
                break
        if start_page is None or not header_hit:
            raise ValueError(f"Section '{section_code} {section_title}' not found or missing table header.")
        if end_page is None:
            end_page = len(pdf.pages)

        # Phase 2: collect layout-preserved lines
        collected = []
        in_table = False
        stop_all = False
        for pi in range(start_page, end_page):
            for ln in (pdf.pages[pi].extract_text(layout=True) or "").splitlines():
                u = ln.strip().upper()
                if end_re.match(u):
                    stop_all = True
                    break
                if not in_table:
                    if table_header_re.search(u):
                        in_table = True
                    continue
                if next_sec_re.match(u) and not u.startswith(code):
                    break
                collected.append(ln)
            if stop_all:
                break

    # Phase 3: group into per-part buffers
    records = []
    last_ref = ""
    for ln in collected:
        m_pno = part_no_re.search(ln)
        if m_pno:
            m_ref = re.match(r'^\s*(?:\((\d+)\)|(\d+))\s+', ln)
            if m_ref:
                last_ref = m_ref.group(1) or m_ref.group(2)
            records.append({
                "ref":      last_ref,
                "part_no":  m_pno.group(0),
                "buf":      [ln[m_pno.end():].strip()]
            })
        else:
            if not records:
                continue
            txt = ln.strip()
            if re.fullmatch(r'\d+', txt) or re.fullmatch(r'\d{4}\.\d{2}\.\d{2}', txt):
                continue
            records[-1]["buf"].append(txt)

    # Phase 4: parse each buffer directly into column-lists
    ref_nos      = []
    part_nos     = []
    descriptions = []
    remarks_list = []

    for rec in records:
        raw = " ".join(rec["buf"])
        raw = raw.replace('∙','').replace('•','').replace('\uf020','')
        raw = re.sub(r'\s+', ' ', raw).strip()

        idx       = raw.find("--------")
        desc_part = raw[:idx].strip() if idx != -1 else raw
        cat_part  = raw[idx+8:].strip() if idx != -1 else ""

        # clean up description
        desc_part = re.sub(r'\.{2,}\s+\d.*$', '', desc_part).strip()
        desc_part = re.sub(r'\s+GK[A-Za-z0-9]+\s*$', '', desc_part)
        desc_part = re.sub(r'\s+(?:-+|\d+)+\s*$', '', desc_part)
        desc      = re.sub(r'\s+\d+\s+\d{4}\.\d{2}\.\d{2}.*$', "", desc_part).strip()
        desc      = re.sub(r'(?:\s+(?:\(\d+\)|-+|\d+))+$',     "", desc).strip()
        desc      = re.sub(r'\.{2,}$',                         "", desc).strip()
        desc      = re.sub(r'(?:\s+[A-Z])+$',                  "", desc).strip()
        desc      = "" if not re.search(r'[A-Za-z]', desc) else desc

        # clean up catalogue codes → remarks
        if cat_part.upper().startswith("GK") and len(cat_part) > 8:
            cat_clean = cat_part[8:].split()[0]
        else:
            m_codes   = re.match(r'[-\s]*([0-9A-Z,\s]+)', cat_part)
            raw_codes = m_codes.group(1) if m_codes else ""
            cat_clean = raw_codes.replace(" ", "")
            cat_clean = re.sub(r'([A-Z])(?=\d)', r'\1,', cat_clean)
            cat_clean = re.sub(r'(?<=[0-9A-Z]{2})(?=[A-Z]{2}(?:,|$))', ',', cat_clean)
        cat_clean    = re.sub(r'\d{4}$', '', cat_clean)
        tokens       = [t for t in cat_clean.split(',') if t]
        seen         = set()
        final_codes  = [c for c in tokens if c not in seen and not seen.add(c)]
        remarks      = ",".join(final_codes)

        # adjust part_no suffix logic
        m3 = re.match(r'^(.+?)([A-Z]{3,})$', rec["part_no"])
        if m3:
            core, suf = m3.group(1), m3.group(2)
            part_no    = core + suf[:2]
            desc       = f"{suf[2:]} {desc}".strip()
        else:
            part_no = rec["part_no"]

        ref_nos.append(rec["ref"])
        part_nos.append(part_no)
        descriptions.append(desc)
        remarks_list.append(remarks)

    df = pd.DataFrame({
        'ref_no':      ref_nos,
        'part_no':     part_nos,
        'description': descriptions,
        'remarks':     remarks_list
    })
    return df
def extract_all_sections_one_pass(pdf_id, year, brand, model, batch_id, pdf_path: str) -> pd.DataFrame:
    """
    Opens the PDF once, walks through it page by page, detects sections using
    next_sec_re, collects each section’s lines, inlines Phase 3+4 verbatim,
    stops entirely when end_re is first encountered, strips any leading
    "*GROUP" from titles, and writes a CSV with columns
    section_no, section_name, ref_no, part_no, description, remarks.
    """
    next_sec_re     = re.compile(r'^[A-Z]+-\d+', re.IGNORECASE)
    table_header_re = re.compile(r'\bReqd\.?\s*QTY\b', re.IGNORECASE)
    part_no_re      = re.compile(r'\b[0-9]{5,}(?:-[A-Z0-9-]+)+\b')
    end_re          = re.compile(r'.*PART\s*NO\.?\s*INDEX.*', re.IGNORECASE)

    section_nos   = []
    section_names = []
    ref_nos       = []
    part_nos      = []
    descriptions  = []
    remarks_list  = []

    current = None
    done    = False

    def _flush(cur):
        """Phase 3+4 logic verbatim, flushing cur['collected'] into our lists."""
        records = []; last_ref = ""
        for ln in cur['collected']:
            m_pno = part_no_re.search(ln)
            if m_pno:
                m_ref = re.match(r'^\s*(?:\((\d+)\)|(\d+))\s+', ln)
                if m_ref:
                    last_ref = m_ref.group(1) or m_ref.group(2)
                records.append({
                    'ref': last_ref,
                    'part_no': m_pno.group(0),
                    'buf': [ln[m_pno.end():].strip()]
                })
            else:
                if not records: continue
                txt = ln.strip()
                if re.fullmatch(r'\d+', txt) or re.fullmatch(r'\d{4}\.\d{2}\.\d{2}', txt):
                    continue
                records[-1]['buf'].append(txt)

        for rec in records:
            raw = " ".join(rec['buf']).replace('∙','').replace('•','').replace('\uf020','')
            raw = re.sub(r'\s+', ' ', raw).strip()
            idx = raw.find("--------")
            desc_part = raw[:idx].strip() if idx != -1 else raw
            cat_part  = raw[idx+8:].strip() if idx != -1 else ""

            # description cleanup
            desc_part = re.sub(r'\.{2,}\s+\d.*$', '', desc_part).strip()
            desc_part = re.sub(r'\s+GK[A-Za-z0-9]+\s*$', '', desc_part)
            desc_part = re.sub(r'\s+(?:-+|\d+)+\s*$', '', desc_part)
            desc = re.sub(r'\s+\d+\s+\d{4}\.\d{2}\.\d{2}.*$', "", desc_part).strip()
            desc = re.sub(r'(?:\s+(?:\(\d+\)|-+|\d+))+$', "", desc).strip()
            desc = re.sub(r'\.{2,}$', "", desc).strip()
            desc = re.sub(r'(?:\s+[A-Z])+$', "", desc).strip()
            desc = "" if not re.search(r'[A-Za-z]', desc) else desc

            # remarks cleanup
            if cat_part.upper().startswith("GK") and len(cat_part) > 8:
                cat_clean = cat_part[8:].split()[0]
            else:
                m_codes   = re.match(r'[-\s]*([0-9A-Z,\s]+)', cat_part)
                raw_codes = m_codes.group(1) if m_codes else ""
                cat_clean = raw_codes.replace(" ", "")
                cat_clean = re.sub(r'([A-Z])(?=\d)', r'\1,', cat_clean)
                cat_clean = re.sub(r'(?<=[0-9A-Z]{2})(?=[A-Z]{2}(?:,|$))', ',', cat_clean)
            cat_clean   = re.sub(r'\d{4}$', '', cat_clean)
            tokens      = [t for t in cat_clean.split(',') if t]
            seen        = set()
            final_codes = [c for c in tokens if c not in seen and not seen.add(c)]
            remarks     = ",".join(final_codes)

            m3 = re.match(r'^(.+?)([A-Z]{3,})$', rec['part_no'])
            if m3:
                core, suf = m3.group(1), m3.group(2)
                pno        = core + suf[:2]
                desc       = f"{suf[2:]} {desc}".strip()
            else:
                pno = rec['part_no']

            section_nos.append(cur['code'])
            section_names.append(cur['title'])
            ref_nos.append(rec['ref'])
            part_nos.append(pno)
            descriptions.append(desc)
            remarks_list.append(remarks)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            if done:
                break

            plain  = (page.extract_text() or "").splitlines()
            layout = (page.extract_text(layout=True) or "").splitlines()

            # detect new section headers
            for ln in plain:
                if done:
                    break
                u = ln.strip().upper()
                if next_sec_re.match(u):
                    if current:
                        _flush(current)
                    parts = ln.strip().split(None, 1)
                    raw_title = parts[1].strip() if len(parts) > 1 else ""
                    # strip any leading "*GROUP"
                    title = re.sub(r'\b[A-Z]+GROUP\b\s*', '', raw_title, flags=re.IGNORECASE)
                    current = {
                        'code':       parts[0].upper(),
                        'title':      title,
                        'header_hit': False,
                        'collected':  []
                    }

            # collect layout lines
            if current:
                for ln in layout:
                    u = ln.strip().upper()
                    if end_re.match(u):
                        _flush(current)
                        done = True
                        break
                    if not current['header_hit']:
                        if table_header_re.search(u):
                            current['header_hit'] = True
                        continue
                    if next_sec_re.match(u) and not u.startswith(current['code']):
                        _flush(current)
                        current = None
                        break
                    current['collected'].append(ln)

    if current and not done:
        _flush(current)

    final_df = pd.DataFrame({
        'pdf_id': pdf_id,       #added
        'year': year,           #added
        'brand': brand,         #added
        'model': model,         #added
        'batch_id': batch_id,   #added
        'section':   section_nos,
        'section_name': section_names,
        'ref_no':       ref_nos,
        'part_no':      part_nos,
        'description':  descriptions,
        'remarks':      remarks_list,
    })
    final_df["image_id"] = final_df["pdf_id"] + "_" + final_df["section"]
    return final_df
# Image Extraction
def honda_extract_images_with_fig_labels(pdf_stream, pdf_id, engine):
    doc = fitz.open(stream=pdf_stream, filetype="pdf")
    data = []

    MAIN_GROUPS = ["ENGINEGROUP", "FRAMEGROUP"]

    section_pattern = r"\b((?:E|F|EOP)-\d{1,3}(?:-\d+)?)\b"

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text()
        lines = text.splitlines()

        # --- Check if page is a MAIN GROUP page ---
        page_has_main_group = False

        text_no_spaces = re.sub(r"\s+", "", text).lower()

        for group in MAIN_GROUPS:
            if group.lower() in text_no_spaces:
                page_has_main_group = True
                break

        if not page_has_main_group:
            continue  # skip page

        # --- Check if page has images ---
        image_list = page.get_images()
        if not image_list:
            continue  # skip if no images

        # --- Extract section labels from page ---
        sections_found = []
        for line in lines:
            match = re.search(section_pattern, line)
            if match:
                section = match.group(1)
                sections_found.append(section)

        if not sections_found:
            # print(f"\n=== PAGE {page_num+1} ===")
            # print("[SKIP] No sections found")
            continue
        
        # For debugging
        # print(f"\n=== PAGE {page_num+1} ===")
        # print(f"[MAIN GROUP PAGE] → {len(image_list)} image(s) found")
        # print(f"Sections found: {sections_found}")

        # --- Map each section to corresponding image ---
        # NOTE: assumes order of section labels = order of images
        for idx, section in enumerate(sections_found):
            if idx >= len(image_list):
                #print(f"⚠️ Not enough images for sections — stopping at {idx}")
                break

            image_info = image_list[idx]
            xref = image_info[0]
            base_image = doc.extract_image(xref)
            image = normalize_image_background(base_image["image"])

            image_id = f"{pdf_id}_{section}"

            data.append({
                "image_id": image_id,
                "pdf_id": pdf_id,
                "section": section,
                "image": image
            })

            # # For debug: display the section + image
            # img = Image.open(BytesIO(image))
            # display(img)

            #print(f"[PAGE {page_num+1}] {section} → Image saved")

    return pd.DataFrame(data)

# --- CACHE ---
# import pickle
# import time    

# CACHE_DIR = "streamlit_site\cache"
# # Ensure the cache directory exists
# os.makedirs(CACHE_DIR, exist_ok=True)
# def save_to_cache(obj, filename):
#     with open(os.path.join(CACHE_DIR, filename), "wb") as f:
#         pickle.dump(obj, f)
# def load_from_cache(filename):
#     try:
#         with open(os.path.join(CACHE_DIR, filename), "rb") as f:
#             return pickle.load(f)
#     except (FileNotFoundError, EOFError):
#         return None
# def clear_old_cache_files(directory, max_age_seconds=86400):  # 1 Day = 86400
#     now = time.time()
#     for filename in os.listdir(directory):
#         file_path = os.path.join(directory, filename)
#         if os.path.isfile(file_path):
#             file_age = now - os.path.getmtime(file_path)
#             if file_age > max_age_seconds:
#                 os.remove(file_path)

# Importing relevant libraries
import os
import re
import time
import pandas as pd
import pdfplumber
import numpy as np
import ast
import base64
import fitz
from IPython.display import Image
from PIL import Image, ImageOps, UnidentifiedImageError
from PIL import Image as PILImage
from io import BytesIO
from collections import defaultdict
from datetime import datetime, timedelta
import time
import bcrypt
import calendar
import plotly.express as px
import streamlit as st
from streamlit_cookies_manager import EncryptedCookieManager

# Use the encrypted cookie manager for hiding cookie values
# Extent the EncryptedCookieManager to allow cookies to expire
class ExtendedEncryptedCookieManager(EncryptedCookieManager):
    def set_cookie_with_expiry(self, key, value, expires_at):
        self[key] = value
        # Ensure metadata storage exists
        if not hasattr(self, "_cookies_metadata") or self._cookies_metadata is None:
            self._cookies_metadata = {}
        self._cookies_metadata[key] = {"expires_at": expires_at.isoformat()}

# Configs for cookie manager
cookies = ExtendedEncryptedCookieManager(
    prefix="myapp_",
    password="mpams"
)

# Stop the app if cookies are not ready
if not cookies.ready():
    st.stop()

# For dashboard charts color scheme
custom_colors = ["#8E44AD", "#E74C3C", "#3498DB", "#F1C40F"]

# --- DATABASE SETUP ---
from sqlalchemy import (create_engine, select, update, delete, distinct, text, join, or_, func, and_, \
                        Table, Column, Integer, String, MetaData, ForeignKey, LargeBinary)

from sqlalchemy.orm import sessionmaker

# SQLAlchemy connection URL
# Local run: makes use of secrets.toml stored in user/username/secrets.toml in local files
# Deployed: makes use of streamlit secrets stored in manage app > 3 dots > Secrets
DATABASE_URL = f"postgresql://{st.secrets.username}:{st.secrets.password}@{st.secrets.host}:{st.secrets.port}/{st.secrets.database}"
# Configure SQLAlchemy engine to manage database connection
engine = create_engine(DATABASE_URL)

# --- PDF DATA EXTRACTION
# Extract models based of file name (Only Yamaha + Honda) for auto-filling of manual import form
def extract_model(pdf_name):
    # Format: AEROX from AEROX '... or NC750XAP from NC750XAP_...
    # start of filename, letters/numbers/spaces until a special character (', _)    
    match = re.match(r"([A-Za-z0-9 ]+)", pdf_name)
    if match:
        return match.group(1).replace(" ", "")  # Removes any spaces
    
# Extract batch id based of file name (Only Yamaha + Honda) for auto-filling of manual import form
def extract_batch_id(pdf_name, brand):
    if brand == "Yamaha":
        # Yamaha Format: (B65P, B65R, B56S) or (1MCH, !MCG)
        # Extract batch ids inside parentheses, ( )
        match = re.search(r"\((.*?)\)", pdf_name)
        if match:
            #Combine parts by underscore
            parts = match.group(1).split(",")
            clean_parts = [part.strip() for part in parts]
            return "_".join(clean_parts)
    
    elif brand == "Honda":
        # Honda Format: ..._13MJPG02_... or ..._13MKWM02_...
        # Look for uppercase/digit code between underscores (6–10 characters)
        match = re.search(r"_([A-Z0-9]{6,10})_", pdf_name)
        if match:
            return match.group(1)
        
    # If brand not supported return nothing
    return None

# Extract year based of file name (Only Yamaha) for auto-filling of manual import form
def extract_year(pdf_name, brand):
    # Format: AEROX '19 ... or FJR1300A '15
    # Get the 2 digit as year after the '
    if brand == "Yamaha":
        year_match = re.search(r"'(\d{2})", pdf_name)
        return f"20{year_match.group(1)}" if year_match else None
    return None

# Sub class for each PDF Processor to extract all data from PDF
class PDFProcessor:
    def __init__(self, pdf_bytes, pdf_id, brand, year, model, batch_id, cc, image=None):        
        self.pdf_stream = BytesIO(pdf_bytes)
        self.pdf_id = pdf_id
        self.brand = brand
        self.year = year
        self.model = model
        self.batch_id = batch_id
        self.image = image
        self.cc = cc
        self.pdf_section_df = None

    # Structure PDF info data for database upload
    def get_pdf_info(self):
        return pd.DataFrame([{
            "pdf_id": self.pdf_id,
            "brand": self.brand,
            "year": self.year,
            "model": self.model,
            "batch_id": self.batch_id,
            "bike_image": self.image,
            "cc": self.cc,
            "is_active": 0,
            "archived": 0
        }])
    
    # Structure PDF log data for database upload
    def extract_pdf_log(self, account_id, description):
        return pd.DataFrame([{
            "pdf_id": self.pdf_id,
            "account_id": account_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "description": description
        }])

    # Normalize image to ensure that all image extracted have the same format
    @staticmethod
    def normalize_image_background(image_bytes):
        img = Image.open(BytesIO(image_bytes)).convert("L")  # Grayscale
        mean_brightness = sum(img.getdata()) / (img.width * img.height)
        if mean_brightness < 128:
            img = ImageOps.invert(img)
        img = img.convert("RGB")
        output = BytesIO()
        img.save(output, format="PNG")
        return output.getvalue()

    # Intialize common text extraction function call (Different codes based of brand)
    def extract_text(self):
        raise NotImplementedError("Each brand must implement its own text extraction")

    # Intialize common image extraction function call extraction (Different codes based of brand)
    def extract_images(self):
        raise NotImplementedError("Each brand must implement its own image extraction")

# Yamaha PDF Processor
class YamahaProcessor(PDFProcessor):
    # Groups characters into lines based on Y position with a tolerance
    # Reconstructs text lines left-to-right with basic spacing using X gaps
    @staticmethod
    def reconstruct_lines_from_chars(chars, y_tolerance=2.5):
        lines = defaultdict(list)
        for c in chars:
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
    
    # Calls line reconstruction function to get visually ordered text layout from character positions
    def extract_raw_text(self):
        output_lines = []
        with pdfplumber.open(self.pdf_stream) as pdf:
            for page in pdf.pages:
                chars = page.chars
                raw_lines = self.reconstruct_lines_from_chars(chars, y_tolerance=5.5)
                if not raw_lines or not raw_lines[0][1].strip().startswith("FIG."):
                    continue
                for _, line in raw_lines:
                    stripped_line = line.strip()
                    if re.fullmatch(r"\d+", stripped_line):
                        continue
                    if stripped_line:
                        output_lines.append(stripped_line)
        return output_lines
    
    # Extracts data and splits the text into clean row parts
    @staticmethod
    def structure_raw_text(raw_lines):
        structured_output = []

        # Keep track of indices to skip (for merged lines)
        skip_indices = set()
        
        for i in range(len(raw_lines)):
            if i in skip_indices:
                continue

            line = raw_lines[i].strip()

            # Split line into parts using 2+ spaces as separator
            parts = re.split(r"\s{2,}", line)

            # --- Normalize FIG. format ---
            # Check if line is a FIG. line and Handle cases like "FIG. 1" or "FIG.1" by split into ["FIG.", "1", ...]
            if parts and isinstance(parts[0], str) and parts[0].startswith("FIG."):
                match = re.match(r"^(FIG\.)\s*(\d+)$", parts[0])
                if match:
                    parts = [match.group(1), match.group(2)] + parts[1:]

            # --- Skip pure descriptions (floating text without data) ---
            if len(parts) == 1 and re.match(r"^[A-Z ,\-0-9]+$", parts[0]):
                continue        

            # --- Try to fill in missing part name ---
            # If second part is not text, check previous/next lines for possible description
            if len(parts) >= 2 and not re.search(r"[A-Za-z]", parts[1]):
                # checks if its not the first line first (nothing to get from previous line)
                # Try merging with previous line if it's a lone description 
                if i > 0:
                    prev_line = raw_lines[i - 1].strip()
                    # check if line is a lone description (1 word/phrase even after 2 space split)
                    if len(re.split(r"\s{2,}", prev_line)) == 1:
                        parts.insert(1, prev_line)
                        skip_indices.add(i - 1)

                # checks if its not the last line first (nothing to get from next line)
                # Try merging with next line if it's a lone description
                if i + 1 < len(raw_lines):
                    next_line = raw_lines[i + 1].strip()
                    # check if line is a lone description 
                    if len(re.split(r"\s{2,}", next_line)) == 1:
                        parts.insert(1, next_line)
                        skip_indices.add(i + 1)

            # Checks if first item contains a number and part number
            # splits the first digit as fig number and second part as part number
            if parts and re.match(r"^\d+\s+[A-Z0-9–\-]+$", parts[0]):
                split_part = re.split(r"\s+", parts[0], maxsplit=1)
                parts = split_part + parts[1:]

            # Append cleaned row
            structured_output.append(parts)

        # --- Final cleanup: remove junk rows ---
        # Check if row has more than 1 parts and Keep only rows that have part number 
        structured_output = [
            row for row in structured_output
            if not (
                (len(row) == 1 and re.match(r"^[A-Z ,\-0-9]+$", row[0])) or
                all(cell.isdigit() for cell in row)
            )
        ]

        return structured_output
    
    # Converts the structured output into a clean and structured table
    @staticmethod
    def convert_to_table(pdf_id, structured_output):
        rows = []
        # intialize variables for keeping track of data
        section = s_name = prev_section = prev_c_name = prev_ref_no = ""

        for line in structured_output:
            if not line or not line[0]:
                continue

            # Checks if line is a FIG. line to get the section number (This line only contains section info)
            if line[0] == "FIG." and len(line) >= 3:
                section = line[1]

                # Get section name from after the section number by joining the rest
                raw_name = " ".join(line[2:])
                # Strip leading/trailing spaces
                s_name = raw_name.strip()
                
                # Skips to next line while keeping track of the current section for the parts data
                prev_section, prev_c_name = section, s_name
                continue

            # Fallback to previous and makes use of current section
            if not section:
                section, s_name = prev_section, prev_c_name

            # Determine if it's a valid parts data line
            if len(line) >= 2 and (re.match(r'\w+[-–]\w+', line[0]) or line[0].isdigit()):
                # Check if line contains a reference number
                if line[0].isdigit():
                    ref_no = line[0]
                    part_no = line[1]
                    rest = line[2:]
                    # Keep track of reference number for next few parts to use if they do not have a reference number
                    prev_ref_no = ref_no
                else:
                    # Makes use of previous one if there is no reference number
                    ref_no = prev_ref_no
                    part_no = line[0]
                    rest = line[1:]
            else:
                continue

            # Extract description(parts name) and additional info
            description = ""
            remarks = ""
            # Flag for if Part Quantities detected 
            # As it is not required and not part of the description or additional info
            # It is located between description and remarks as ['description1', 'description2', '1', '2', 'remarks1', 'remarks2']
            numbers = []
            found_numbers = False
            for item in rest:
                # Skip part if its part quantity seperate description and remarks
                if item.isdigit():
                    numbers.append(item)
                    found_numbers = True
                    continue
                
                # Combine all description until part quantity found
                if not found_numbers:
                    description += item + " "
                # Combine all remarks after all part quantity found and stored
                else:
                    remarks += item + " "

            # Creating section id for section table 
            section_id = f"{pdf_id}_{section}"

            rows.append([
                part_no, description.strip(), ref_no, remarks.strip(), section_id, section, s_name,  pdf_id
            ])
        
        # Structure the data into a DataFrame
        return pd.DataFrame(rows, columns=[
            'part_no', 'description', 'ref_no', 'add_info', 'section_id', 'section_no', 'section_name', 'pdf_id'
        ])

    # Extracts the images and assign the section to each imagefrom the pdf
    def yamaha_extract_images_with_fig_labels(self):
        # Gets the pdf file
        doc = fitz.open(stream=self.pdf_stream, filetype="pdf")
        data = []
        # Keep track of section numbers (Only 1 image per section)
        seen_figs = set()

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            # Check if page is a section page
            matches = re.findall(r"FIG\.\s*([\w-]+)", text)
            if not matches:
                continue

            # Get the section number
            section = matches[0]
            # Check if already stored image (Some sections have more than 1 page)
            if section in seen_figs:
                continue

            # Get image from the page
            image_list = page.get_images(full=True)
            if not image_list:
                continue
            xref = image_list[0][0]
            base_image = doc.extract_image(xref)
            # Normalize image to have a consistent format
            image = self.normalize_image_background(base_image["image"])
            # Create section id
            section_id = f"{self.pdf_id}_{section}"
            # Store the data
            data.append({
                "section_id": section_id,
                "pdf_id": self.pdf_id,
                "section_image": image
            })
            # Keep track of section numbers
            seen_figs.add(section)

        return pd.DataFrame(data)
    
    # Consistent master parts list extraction function naming
    def extract_master_parts_list(self):
        # Extract raw text in its exact layout from PDF
        raw_lines = self.extract_raw_text()
        # Extract relevant information into parts line by line
        structured_data = self.structure_raw_text(raw_lines)
        # Structure parts into a table
        df = self.convert_to_table(
            pdf_id=self.pdf_id,
            structured_output=structured_data
        )

        # Seperating columns into different tables
        mpl_df = df[['part_no', 'description', 'ref_no', 'add_info', 'section_id', 'pdf_id']]
        pdf_section_df = df[['section_id', 'section_no', 'section_name', 'pdf_id']].drop_duplicates().reset_index(drop=True)
        self.pdf_section_df = pdf_section_df

        # debugging purposes
        # print(mpl_df)
        # print(pdf_section_df)

        return mpl_df

    # Consistent PDF section and Image extraction function naming
    def extract_pdf_section(self):
        # Extract images and assign the section to each image
        image_df = self.yamaha_extract_images_with_fig_labels()

        # Merge PDF sections with extracted images
        merged_df = pd.merge(
            self.pdf_section_df,
            image_df,
            on=["section_id", "pdf_id"],
            how="inner"
        )

        # Re-order columns
        final_columns = ['section_id', 'section_no', 'section_name', 'section_image', 'pdf_id']
        merged_df = merged_df[final_columns]

        return merged_df

# Honda PDF Processor
class HondaProcessor(PDFProcessor):
    @staticmethod
    def extract_section_with_layout(pdf_stream: str, section_code: str, section_title: str):
        """
        Finds a specified section, locates 'Reqd. QTY', extracts in layout mode,
        then parses each part and variant into ref_no, part_no, description, remarks.
        Stops collecting once it encounters any line containing 'PART', 'NO', and 'INDEX'.
        Returns a DataFrame with columns ref_no, part_no, description, remarks.
        """
        code = section_code.upper()
        title = section_title.upper()

        next_sec_re     = re.compile(r'^[A-Z]+-\d+(?:-\d+)*', re.IGNORECASE)
        table_header_re = re.compile(r'\bReqd\.?\s*QTY\b', re.IGNORECASE)
        part_no_re      = re.compile(r'\b[0-9]{5,}(?:-[A-Z0-9-]+)+\b')
        end_re          = re.compile(r'.*PART\s*NO\.?\s*INDEX.*', re.IGNORECASE)

        # Phase 1: locate page range
        start_page = header_hit = None
        end_page = None
        with pdfplumber.open(pdf_stream) as pdf:
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
                        # skip blank lines to avoid u.split()[0] errors
                        if not u:
                            continue
                        first_token = u.split()[0]
                        if next_sec_re.match(u) and first_token != code:
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
                    # again guard against blank
                    if not u:
                        collected.append(ln)
                        continue
                    first_token = u.split()[0]
                    if next_sec_re.match(u) and first_token != code:
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
            cat_part  = re.sub(r'^[0-9]+\s*', '', cat_part)
            # strip quantity columns from description only
            desc_part = re.sub(r'\s\d+(?:\s+\d+)+.*$', '', desc_part).strip()

            # clean up description
            desc_part = re.sub(r'\.{2,}\s+\d.*$', '', desc_part).strip()
            desc_part = re.sub(r'\s+GK[A-Za-z0-9]+\s*$', '', desc_part)
            desc_part = re.sub(r'\s+(?:-+|\d+)+\s*$', '', desc_part)
            desc      = re.sub(r'\s+\d+\s+\d{4}\.\d{2}\.\d{2}.*$', "", desc_part).strip()
            desc      = re.sub(r'(?:\s+(?:\(\d+\)|-+|\d+))+$',     "", desc).strip()
            desc      = re.sub(r'\.{2,}$',                         "", desc).strip()
            desc      = re.sub(r'(?:\s+[A-Z])+$',                  "", desc).strip()
            desc      = re.sub(r'\s+[-\d ]+$',                     "", desc).strip()
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
            if len(tokens) > 1 and re.fullmatch(r'[A-Z]+', tokens[0]):
                m = re.match(r'^(\d+)', tokens[1])
                if m:
                    tokens[0] = m.group(1) + tokens[0]
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

        # build and return DataFrame
        df = pd.DataFrame({
            'ref_no':      ref_nos,
            'part_no':     part_nos,
            'description': descriptions,
            'remarks':     remarks_list
        })
        return df
    @staticmethod
    def extract_all_sections_one_pass(pdf_id, pdf_stream: str) -> pd.DataFrame:
        """
        Opens the PDF once, walks through it page by page, detects sections via next_sec_re,
        collects each section’s lines (with the shim‐prefix_re logic you added),
        and as soon as any end_re is hit, stops the entire extraction afterwards.
        Writes CSV with columns section_no, section_name, ref_no, part_no, description, remarks.
        """
        next_sec_re     = re.compile(r'^[A-Z]+-\d+(?:-\d+)*', re.IGNORECASE)
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
            """Phase 3+4 verbatim, with your prefix_re shim logic and all the desc/cat fixes."""
            records = []; last_ref = ""
            prefix_re = re.compile(r'^\s*\(?(\d+)\)?\s+(' + part_no_re.pattern + r')', re.IGNORECASE)

            # Phase 3: grouping
            for ln in cur['collected']:
                # same grouping logic
                m0 = prefix_re.match(ln)
                if m0:
                    last_ref, pno = m0.group(1), m0.group(2)
                    rest = ln[m0.end():].strip()
                    records.append({'ref': last_ref, 'part_no': pno, 'buf': [rest]})
                else:
                    m_pno = part_no_re.search(ln)
                    if m_pno:
                        pno  = m_pno.group(0)
                        rest = ln[m_pno.end():].strip()
                        records.append({'ref': last_ref, 'part_no': pno, 'buf': [rest]})
                    else:
                        if not records:
                            continue
                        txt = ln.strip()
                        if re.fullmatch(r'\d+', txt) or re.fullmatch(r'\d{4}\.\d{2}\.\d{2}', txt):
                            continue
                        records[-1]['buf'].append(txt)

            # Phase 4: parsing & cleanup
            for rec in records:
                raw = " ".join(rec['buf']).replace('∙','').replace('•','').replace('\uf020','')
                raw = re.sub(r'\s+', ' ', raw).strip()

                idx = raw.find("--------")
                desc_part = raw[:idx].strip() if idx != -1 else raw
                cat_part  = raw[idx+8:].strip() if idx != -1 else ""

                # — NEW: strip any stray leading serials from cat_part
                cat_part = re.sub(r'^[0-9]+\s*', '', cat_part)

                # — NEW: strip quantity columns from desc_part
                desc_part = re.sub(r'\s\d+(?:\s+\d+)+.*$', '', desc_part).strip()

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
                cat_clean = re.sub(r'\d{4}$', '', cat_clean)

                # — NEW: if first token is pure letters but second starts with a digit, prefix it
                tokens = [t for t in cat_clean.split(',') if t]
                if len(tokens) > 1 and re.fullmatch(r'[A-Z]+', tokens[0]):
                    m = re.match(r'^(\d+)', tokens[1])
                    if m:
                        tokens[0] = m.group(1) + tokens[0]

                # dedupe
                seen  = set()
                codes = [c for c in tokens if c not in seen and not seen.add(c)]
                remarks = ",".join(codes)

                # part_no suffix logic
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

        # --- the rest of extract_all_sections_one_pass is unchanged ---
        with pdfplumber.open(pdf_stream) as pdf:
            for page in pdf.pages:
                if done:
                    break

                plain  = (page.extract_text() or "").splitlines()
                layout = (page.extract_text(layout=True) or "").splitlines()

                for ln in plain:
                    u = ln.strip().upper()
                    if next_sec_re.match(u):
                        if current:
                            _flush(current)
                        parts = ln.strip().split(None, 1)
                        raw_title = parts[1].strip() if len(parts) > 1 else ""
                        title     = re.sub(r'\b[A-Z]+GROUP\b\s*', '', raw_title, re.IGNORECASE)
                        current = {
                            'code':       parts[0].upper(),
                            'title':      title,
                            'header_hit': False,
                            'collected':  []
                        }

                if current:
                    for ln in layout:
                        u = ln.strip().upper()
                        if end_re.match(u):
                            _flush(current)
                            done = True
                            current = None
                            break
                        if not current['header_hit']:
                            if table_header_re.search(u):
                                current['header_hit'] = True
                            continue
                        first_token = u.split()[0] if u else ""
                        if next_sec_re.match(u) and first_token != current['code']:
                            _flush(current)
                            current = None
                            break
                        collected = current['collected']
                        collected.append(ln)

        if current and not done:
            _flush(current)

        final_df = pd.DataFrame({
            'pdf_id': pdf_id,
            'part_no':      part_nos,
            'description':  descriptions,
            'section_no':   section_nos,
            'section_name': section_names,
            'ref_no':       ref_nos,
            'add_info':      remarks_list
        })
        final_df["section_id"] = final_df["pdf_id"] + "_" + final_df["section_no"]
        final_df[['part_no', 'description', 'ref_no', 'add_info', 'section_id', 'section_no', 'section_name', 'pdf_id']]
        return final_df
    
    # Extracts the images and assign the section to each imagefrom the pdf
    def honda_extract_images_with_fig_labels(self):
        doc = fitz.open(stream=self.pdf_stream, filetype="pdf")
        data = []

        MAIN_GROUPS = ["ENGINEGROUP", "FRAMEGROUP"]
        section_pattern = r"\b((?:E|F|EOP)-\d{1,3}(?:-\d+)?)\b"

        seen_section_ids = set()  # ✅ Track globally across pages

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            lines = text.splitlines()

            # --- Check if page is a MAIN GROUP page ---
            text_no_spaces = re.sub(r"\s+", "", text).lower()
            if not any(group.lower() in text_no_spaces for group in MAIN_GROUPS):
                continue

            # --- Check if page has images ---
            image_list = page.get_images()
            if not image_list:
                continue

            # --- Extract section labels ---
            sections_found = []
            for line in lines:
                match = re.search(section_pattern, line)
                if match:
                    sections_found.append(match.group(1))

            if not sections_found:
                print(f"\n=== PAGE {page_num+1} ===")
                print("[SKIP] No sections found")
                continue

            print(f"\n=== PAGE {page_num+1} ===")
            print(f"[MAIN GROUP PAGE] → {len(image_list)} image(s) found")
            print(f"Sections found: {sections_found}")

            # --- Map sections to images ---
            for idx, section in enumerate(sections_found):
                if idx >= len(image_list):
                    print(f"⚠️ Not enough images for sections — stopping at {idx}")
                    break

                section_id = f"{self.pdf_id}_{section}"
                if section_id in seen_section_ids:
                    print(f"⚠️ Duplicate section_id {section_id} — skipping")
                    continue
                seen_section_ids.add(section_id)

                image_info = image_list[idx]
                xref = image_info[0]
                base_image = doc.extract_image(xref)
                image = self.normalize_image_background(base_image["image"])

                data.append({
                    "section_id": section_id,
                    "pdf_id": self.pdf_id,
                    "section_image": image
                })

        return pd.DataFrame(data)
    
    # Consistent master parts list extraction function naming
    def extract_master_parts_list(self):
        # Extracting all data
        df = self.extract_all_sections_one_pass(
            pdf_id=self.pdf_id,
            pdf_stream=self.pdf_stream
        )

        # Seperating columns into different tables
        mpl_df = df[['part_no', 'description', 'ref_no', 'add_info', 'section_id', 'pdf_id']]
        pdf_section_df = df[['section_id', 'section_no', 'section_name', 'pdf_id']].drop_duplicates().reset_index(drop=True)
        self.pdf_section_df = pdf_section_df

        # Debugging purposes
        # print(mpl_df)
        # print(pdf_section_df)

        return mpl_df
    
    # Consistent PDF section and Image extraction function naming
    def extract_pdf_section(self):
        # Extract images and assign the section to each image
        image_df = self.honda_extract_images_with_fig_labels()

        # Merge PDF sections with extracted images
        merged_df = pd.merge(
            self.pdf_section_df,
            image_df,
            on=["section_id", "pdf_id"],
            how="inner" 
        )

        # Re-order columns
        final_columns = ['section_id', 'section_no', 'section_name', 'section_image', 'pdf_id']
        merged_df = merged_df[final_columns]

        return merged_df

# For manual imports page, to show image preview
def display_image_previews(df, title, brand):
    st.subheader(title)

    # honda and yamaha image has different resolutions
    # adjust the number of columns based on the brand
    num_cols = 5 if brand == "Honda" else 6
    rows = [df.iloc[i:i + num_cols] for i in range(0, len(df), num_cols)]

    for row in rows:
        cols = st.columns(num_cols)
        for i, (_, item) in enumerate(row.iterrows()):
            section_image = item.get('section_image', None)

            # Safe check before opening image
            if isinstance(section_image, bytes):
                try:
                    image = Image.open(BytesIO(section_image))
                    with cols[i]:
                        st.image(
                            image,
                            caption=f"Section: {item['section_no']}",
                            use_container_width=True
                        )
                except UnidentifiedImageError:
                    with cols[i]:
                        st.warning("⚠️ Unable to display image")
            else:
                with cols[i]:
                    st.warning("⚠️ No valid image data") 

# For manage database page, remove trailing spaces from strings in dataframe when comparing changes made from edits
def strip_whitespace(df):
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].astype(str).str.strip()
    return df

# For manage database page, properly sorting the sections for filter/section edit
def filter_sorting(s):
    """
    Sort key that handles:
    - Yamaha sections: '1', '10', '10-1'
    - Honda sections: 'E-1', 'E-1-1', 'F-2', 'EOP-2'
    """

    s = str(s).strip()

    # Case 1: Yamaha-style — all numeric, with optional hyphen
    if re.match(r'^\d+(-\d+)?$', s):
        parts = [int(p) for p in s.split('-')]
        return ('', *parts, 0) if len(parts) == 2 else ('', parts[0], 0, 0)

    # Case 2: Honda-style — alphabetic prefix, number, optional subnumber
    match = re.match(r'^([A-Z]+)-(\d+)(?:-(\d+))?$', s)
    if match:
        prefix = match.group(1)
        main = int(match.group(2))
        sub = int(match.group(3)) if match.group(3) else 0
        return (prefix, main, sub, 0)

    # Fallback: unrecognized — push to bottom
    return ('ZZZ', float('inf'), float('inf'), float('inf'))

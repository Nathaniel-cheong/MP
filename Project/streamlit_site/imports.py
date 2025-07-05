import os
import re
import time
import pandas as pd
import pdfplumber
import fitz
from IPython.display import Image
from PIL import Image, ImageOps, UnidentifiedImageError
from io import BytesIO
from collections import defaultdict
from datetime import datetime

import streamlit as st
from streamlit_cookies_controller import CookieController
cookies = CookieController()

# --- DATABASE SETUP ---
from sqlalchemy import (create_engine, select, update, delete, distinct, text, \
                        Table, Column, Integer, String, MetaData, ForeignKey, LargeBinary)
from sqlalchemy.orm import sessionmaker

# SQLAlchemy connection URL
DATABASE_URL = f"postgresql://{st.secrets.username}:{st.secrets.password}@{st.secrets.host}:{st.secrets.port}/{st.secrets.database}"
# Create engine
engine = create_engine(DATABASE_URL)

# --- PDF EXTRACTION ---
# Yamaha + Honda
def extract_model(pdf_name):
    # Extract model: start of filename, letters/numbers/spaces until a special character (', _)    
    match = re.match(r"([A-Za-z0-9 ]+)", pdf_name)
    if match:
        return match.group(1).replace(" ", "")  # Removes any spaces
# Yamaha + Honda
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

class PDFProcessor:
    def __init__(self, pdf_bytes, pdf_id, brand, year, model, batch_id, image=None):        
        self.pdf_stream = BytesIO(pdf_bytes)
        self.pdf_id = pdf_id
        self.brand = brand
        self.year = year
        self.model = model
        self.batch_id = batch_id
        self.image = image

        self.pdf_section_df = None

    def get_pdf_info(self):
        return pd.DataFrame([{
            "pdf_id": self.pdf_id,
            "brand": self.brand,
            "year": self.year,
            "model": self.model,
            "batch_id": self.batch_id,
            "bike_image": self.image
        }])
    
    #def bike_image_display(self):
        
    def extract_pdf_log(self, account_id):
        return pd.DataFrame([{
            "pdf_id": self.pdf_id,
            "account_id": account_id,
            "timestamp": datetime.now().isoformat(),
            "is_active": 0,
            "is_current": 1
        }])

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

    def extract_text(self):
        raise NotImplementedError("Each brand must implement its own text extraction")

    def extract_images(self):
        raise NotImplementedError("Each brand must implement its own image extraction")

class YamahaProcessor(PDFProcessor):
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
    @staticmethod
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
    @staticmethod
    def convert_to_table(pdf_id, structured_output):
        rows = []
        section = s_name = prev_section = prev_c_name = prev_ref_no = ""

        for line in structured_output:
            if not line or not line[0]:
                continue

            # FIG. section headers
            if line[0] == "FIG." and len(line) >= 3:
                section = line[1]
                print(line)

                raw_name = " ".join(line[2:])  # Full raw name with possible number
                s_name = raw_name.strip()  # Just strip leading/trailing spaces

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

            image_section_combination = f"{pdf_id}_{section}"

            rows.append([
                part_no, description.strip(), ref_no, remarks.strip(), image_section_combination, section, s_name,  pdf_id
            ])

        return pd.DataFrame(rows, columns=[
            'part_no', 'description', 'ref_no', 'add_info', 'section_id', 'section_no', 'section_name', 'pdf_id'
        ])

    def yamaha_extract_images_with_fig_labels(self):
        doc = fitz.open(stream=self.pdf_stream, filetype="pdf")
        data = []
        seen_figs = set()

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            matches = re.findall(r"FIG\.\s*([\w-]+)", text)
            if not matches:
                continue
            section = matches[0]
            if section in seen_figs:
                continue
            image_list = page.get_images(full=True)
            if not image_list:
                continue
            xref = image_list[0][0]
            base_image = doc.extract_image(xref)
            image = self.normalize_image_background(base_image["image"])

            section_id = f"{self.pdf_id}_{section}"

            data.append({
                "section_id": section_id,
                "pdf_id": self.pdf_id,
                "section_image": image
            })
            seen_figs.add(section)

        return pd.DataFrame(data)
    
    def extract_master_parts_list(self):
        raw_lines = self.extract_raw_text()
        structured_data = self.structure_raw_text(raw_lines)
        df = self.convert_to_table(
            pdf_id=self.pdf_id,
            structured_output=structured_data
        )

        mpl_df = df[['part_no', 'description', 'ref_no', 'add_info', 'section_id', 'pdf_id']]
        pdf_section_df = df[['section_id', 'section_no', 'section_name', 'pdf_id']].drop_duplicates().reset_index(drop=True)
        self.pdf_section_df = pdf_section_df

        print(mpl_df)
        print(pdf_section_df)

        return mpl_df

    def extract_pdf_section(self):
        image_df = self.yamaha_extract_images_with_fig_labels()

        merged_df = pd.merge(
            self.pdf_section_df,
            image_df,
            on=["section_id", "pdf_id"],
            how="inner"  # use "left" if you want to keep all rows from section_df
        )

        # Add 'cc' column as empty string
        merged_df["cc"] = ""

        # Optional: Reorder columns
        final_columns = ['section_id', 'section_no', 'section_name', 'cc', 'section_image', 'pdf_id']
        merged_df = merged_df[final_columns]

        return merged_df

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

    def extract_master_parts_list(self):
        df = self.extract_all_sections_one_pass(
            pdf_id=self.pdf_id,
            pdf_stream=self.pdf_stream
        )

        mpl_df = df[['part_no', 'description', 'ref_no', 'add_info', 'section_id', 'pdf_id']]
        pdf_section_df = df[['section_id', 'section_no', 'section_name', 'pdf_id']].drop_duplicates().reset_index(drop=True)
        self.pdf_section_df = pdf_section_df

        print(mpl_df)
        print(pdf_section_df)

        return mpl_df
    
    def extract_pdf_section(self):
        image_df = self.honda_extract_images_with_fig_labels()
        merged_df = pd.merge(
            self.pdf_section_df,
            image_df,
            on=["section_id", "pdf_id"],
            how="inner"  # use "left" if you want to keep all rows from section_df
        )

        # Add 'cc' column as empty string
        merged_df["cc"] = ""

        # Optional: Reorder columns
        final_columns = ['section_id', 'section_no', 'section_name', 'cc', 'section_image', 'pdf_id']
        merged_df = merged_df[final_columns]

        return merged_df

def display_image_previews(df, title, brand):
    st.subheader(title)

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
                    
def advanced_display_image_previews(image_data, title, brand):
    st.subheader(title)

    num_cols = 5 if brand == "Honda" else 6
    rows_per_page = 2
    total_rows = (len(image_data) + num_cols - 1) // num_cols
    total_pages = (total_rows + rows_per_page - 1) // rows_per_page

    if "image_page" not in st.session_state:
        st.session_state.image_page = 0

    start_row = st.session_state.image_page * rows_per_page
    end_row = start_row + rows_per_page

    rows = [image_data[i:i + num_cols] for i in range(0, len(image_data), num_cols)]
    rows_to_show = rows[start_row:end_row]

    for row in rows_to_show:
        cols = st.columns(num_cols)
        for i, item in enumerate(row):
            image = Image.open(BytesIO(item['image']))
            with cols[i]:
                st.image(image,
                         caption=f"PDF ID: {item['pdf_id']}\nSection: {item['section']}",
                         use_container_width=True)

    st.markdown("---")
    st.write(f"Page {st.session_state.image_page + 1} of {total_pages}")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("⬅️ Back", key="image_back", disabled=(st.session_state.image_page == 0)):
            st.session_state.image_page -= 1
    with col3:
        if st.button("Next ➡️", key="image_next", disabled=(st.session_state.image_page >= total_pages - 1)):
            st.session_state.image_page += 1

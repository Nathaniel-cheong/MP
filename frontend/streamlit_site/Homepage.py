from imports import *
import streamlit as st
from sqlalchemy import text
from io import BytesIO
from PIL import Image as PILImage
from PIL import UnidentifiedImageError
import os
from streamlit_app import gen_basket_id

# Page config & global CSS
st.set_page_config(layout="wide", initial_sidebar_state="expanded")
st.markdown("""
    <style>
      .stButton > button { width: 170px; height: 70px; font-size: 16px; }
      .zoom-container img { position: sticky; top: 0; z-index: 100; }
      .hide-sidebar [data-testid="stSidebar"] { display: none; }
    </style>
""", unsafe_allow_html=True)

# ─── Navigation state ─────────────────────────────────────────────────────
nav_defaults = {
    "page_num":        0,
    "current_brand":   None,
    "current_model":   None,
    "current_cc":      None,
    "current_section": None,
    "current_ref":     None,
    "zoom_image":      None,
}
for key, val in nav_defaults.items():
    st.session_state.setdefault(key, val)

# Clear search on page change
prev_page = st.session_state.get("prev_page")
curr_page = st.session_state.page_num
if prev_page is not None and prev_page != curr_page:
    st.session_state.search = ""
st.session_state.prev_page = curr_page

# ─── Cart state ────────────────────────────────────────────────────────────
if "cart_data" not in st.session_state:
    st.session_state.cart_data = {
        "basket_id":    [gen_basket_id()],
        "part_no":      [[]],
        "quantity":     [[]],
        "purchase_type": [],
        "customer_name": [],
        "contact":       [],
        "email":         [],
        "postal_code":   [],
        "address":       []
    }
cart = st.session_state.cart_data

def add_to_cart(part: str):
    qty = st.session_state.get(f"add_qty_{part}", 1)
    parts, qtys = cart["part_no"][0], cart["quantity"][0]
    if part in parts:
        qtys[parts.index(part)] += qty
    else:
        parts.append(part)
        qtys.append(qty)
    st.session_state.just_added = (part, qty)
    st.rerun()  # ← restore immediate rerun so you don't have to click twice

# ─── Brand-specific config + image cache ─────────────────────────────────
BRAND_CONFIG = {
    "Honda":  {"section_img_size": (350,200), "sections_per_row":3, "refs_per_row":5, "page4_layout":"top_image", "model_img_size":(300,200)},
    "Yamaha": {"section_img_size": (250,350), "sections_per_row":4, "refs_per_row":4, "page4_layout":"side_image", "model_img_size":(300,200)},
    "__default__": {"section_img_size": (250,350), "sections_per_row":4, "refs_per_row":4, "page4_layout":"side_image", "model_img_size":(300,200)},
}
@st.cache_data(show_spinner=False)
def process_image(img_bytes: bytes, size: tuple[int,int]):
    pil = PILImage.open(BytesIO(img_bytes)).convert("RGB")
    return pil.resize(size, resample=PILImage.BICUBIC)

for name in ("brands_list","models_dict","cc_dict","sections_dict"):
    st.session_state.setdefault(name, {} if name!="brands_list" else None)

def get_brands():
    if st.session_state.brands_list is None:
        with engine.connect() as conn:
            rs = conn.execute(text("SELECT DISTINCT brand FROM pdf_info")).fetchall()
        st.session_state.brands_list = [r[0] for r in rs]
    return st.session_state.brands_list

def get_years(brand):
    with engine.connect() as conn:
        rs = conn.execute(text(
            "SELECT DISTINCT year FROM pdf_info WHERE brand=:b ORDER BY year DESC"
        ),{"b":brand}).fetchall()
    return [r[0] for r in rs]

def get_models(brand):
    d = st.session_state.models_dict
    if brand not in d:
        with engine.connect() as conn:
            rs = conn.execute(text(
                "SELECT DISTINCT model FROM pdf_info WHERE brand=:b"
            ),{"b":brand}).fetchall()
        d[brand] = [r[0] for r in rs]
    return d[brand]

def get_cc_list(brand,model):
    key=(brand,model); d=st.session_state.cc_dict
    if key not in d:
        with engine.connect() as conn:
            rs = conn.execute(text("""
                SELECT DISTINCT ps.cc
                  FROM pdf_section ps
                  JOIN pdf_info pi ON ps.pdf_id=pi.pdf_id
                 WHERE pi.brand=:b AND pi.model=:m
            """),{"b":brand,"m":model}).fetchall()
        d[key] = [r[0] for r in rs]
    return d[key]

def get_sections(brand,model,cc):
    key=(brand,model,cc); d=st.session_state.sections_dict
    if key not in d:
        with engine.connect() as conn:
            rs = conn.execute(text("""
                SELECT ps.section_name, ps.section_image
                  FROM pdf_section ps
                  JOIN pdf_info pi ON ps.pdf_id=pi.pdf_id
                 WHERE pi.brand=:b AND pi.model=:m AND ps.cc=:c
            """),{"b":brand,"m":model,"c":cc}).fetchall()
        d[key] = [
            (r[0], bytes(r[1]) if isinstance(r[1],memoryview) else r[1])
            for r in rs
        ]
    return d[key]

search = st.text_input("🔍 Search", key="search")
if "page_num" in st.query_params:
    try:
        st.session_state.page_num = int(st.query_params["page_num"][0])
    except:
        pass

st.title("Homepage")

# Page 0: Brands
if st.session_state.page_num == 0:
    st.subheader("Please Choose a Brand")
    brands = get_brands()
    if search:
        filtered = [b for b in brands if b.lower()==search.lower()]
        if not filtered:
            st.info(f"Sorry, we don’t have a brand named “{search}.”")
            st.stop()
        brands = filtered

    cols = st.columns([1]*len(brands) + [len(brands)], gap="small")
    for col, b in zip(cols[:-1], brands):
        with col:
            url = {
                "Honda":"frontend/streamlit_site/images/honda.svg",
                "Yamaha":"frontend/streamlit_site/images/Yamaha_Logo.jpg"
            }.get(b)
            if url:
                st.image(url, width=250)
            else:
                st.write(b)
            if st.button(b):
                st.session_state.current_brand = b
                st.session_state.page_num     = 1
                st.rerun()

# Page 1: Models
elif st.session_state.page_num == 1:
    if st.button("« Back", key="b1"):
        st.session_state.page_num     = 0
        st.session_state.current_brand = None
        st.rerun()

    brand = st.session_state.current_brand
    st.subheader(f"{brand} Models")
    years = get_years(brand)
    col_year, _ = st.columns([1,4])
    with col_year:
        sel = st.selectbox("Filter by year", ["All"] + [str(y) for y in years])

    if sel == "All":
        models = get_models(brand)
    else:
        with engine.connect() as conn:
            rs = conn.execute(text(
                "SELECT DISTINCT model FROM pdf_info WHERE brand=:b AND year=:y"
            ),{"b":brand,"y":int(sel)}).fetchall()
        models = [r[0] for r in rs]

    if search:
        m2 = [m for m in models if m.lower()==search.lower()]
        if not m2:
            st.info(f"Sorry, we don’t have a {brand} model named “{search}.”")
            st.stop()
        models = m2

    DEFAULT_IMG = "frontend/streamlit_site/images/default_bike.jpg"
    cfg = BRAND_CONFIG.get(brand, BRAND_CONFIG["__default__"])
    size = cfg["model_img_size"]
    cols = st.columns([1]*len(models) + [len(models)], gap="small")
    for col, m in zip(cols[:-1], models):
        with col:
            row = engine.connect().execute(
                text("SELECT bike_image FROM pdf_info WHERE brand = :b AND model = :m LIMIT 1"),
                {"b": brand, "m": m}
            ).fetchone()
            blob = row[0] if row and row[0] is not None else None
            if blob:
                raw = bytes(blob) if isinstance(blob, memoryview) else blob
                try:
                    img = process_image(raw, size)
                except UnidentifiedImageError:
                    pil = PILImage.open(DEFAULT_IMG).convert("RGB")
                    img = pil.resize(size, PILImage.BICUBIC)
                st.image(img, width=size[0])
            else:
                pil = PILImage.open(DEFAULT_IMG).convert("RGB")
                img = pil.resize(size, PILImage.BICUBIC)
                st.image(img, width=size[0])    

            if st.button(m):
                st.session_state.current_model = m
                st.session_state.page_num      = 2
                st.rerun()

# Page 2: CC
elif st.session_state.page_num == 2:
    if st.button("« Back", key="b2"):
        st.session_state.page_num     = 1
        st.session_state.current_model = None
        st.rerun()

    brand, model = st.session_state.current_brand, st.session_state.current_model
    st.subheader(f"{brand} {model} — Select CC")
    cc_list = get_cc_list(brand, model)
    if search:
        cc_list = [c for c in cc_list if search.lower() in str(c).lower()]
    cols = st.columns([1]*len(cc_list) + [len(cc_list)], gap="small")
    for col, c in zip(cols[:-1], cc_list):
        with col:
            if st.button(str(c)):
                st.session_state.current_cc  = c
                st.session_state.page_num    = 3
                st.rerun()

# Page 3: Sections
elif st.session_state.page_num == 3:
    if st.button("« Back", key="b3"):
        st.session_state.page_num    = 2
        st.session_state.current_cc  = None
        st.rerun()

    b, m, cc = (
        st.session_state.current_brand,
        st.session_state.current_model,
        st.session_state.current_cc
    )
    st.subheader(f"{b} {m} — CC {cc} Sections")
    sections = get_sections(b, m, cc)
    if search:
        sections = [r for r in sections if search.lower() in r[0].lower()]
    cfg = BRAND_CONFIG.get(b, BRAND_CONFIG["__default__"])
    for i in range(0, len(sections), cfg["sections_per_row"]):
        chunk = sections[i : i + cfg["sections_per_row"]]
        cols  = st.columns(cfg["sections_per_row"], gap="small")
        for col, (name, raw) in zip(cols, chunk):
            with col:
                st.image(process_image(raw, cfg["section_img_size"]))
                if st.button(name, key=f"s_{name}"):
                    st.session_state.current_section = name
                    st.session_state.zoom_image       = raw
                    st.session_state.page_num         = 4
                    st.rerun()
        st.markdown("---")

# Page 4: Zoom & References
elif st.session_state.page_num == 4:
    back_label = "⟵ Back to References" if st.session_state.current_ref else "« Back"
    if st.button(back_label, key="b4"):
        if st.session_state.current_ref:
            st.session_state.current_ref = None
        else:
            st.session_state.page_num = 3
        st.rerun()

    b    = st.session_state.current_brand
    cfg  = BRAND_CONFIG.get(b, BRAND_CONFIG["__default__"])
    sect = st.session_state.current_section
    st.subheader(sect)

    with engine.connect() as conn:
        rs = conn.execute(text("""
            SELECT DISTINCT mpl.ref_no
            FROM master_parts_list mpl
            JOIN pdf_section ps ON mpl.section_id=ps.section_id
            WHERE ps.section_name = :sn
            ORDER BY mpl.ref_no
        """), {"sn": sect})
        ref_nos = [r[0] for r in rs]

    zoomed = PILImage.open(BytesIO(st.session_state.zoom_image)).convert("RGB")
    zoomed.thumbnail((500,750), PILImage.BICUBIC)

    if cfg["page4_layout"] == "top_image":
        st.image(zoomed, use_container_width=True)
        if st.session_state.current_ref is None:
            st.markdown("**Reference Numbers**")
            for i in range(0, len(ref_nos), cfg["refs_per_row"]):
                cols = st.columns(cfg["refs_per_row"], gap="small")
                for col, ref in zip(cols, ref_nos[i : i + cfg["refs_per_row"]]):
                    with col:
                        if st.button(str(ref), key=f"r_{ref}"):
                            st.session_state.current_ref = ref
                            st.rerun()
        else:
            sel = st.session_state.current_ref
            st.markdown(f"**Parts for Reference {sel}**")
            with engine.connect() as conn:
                pr = conn.execute(text("""
                    SELECT mpl.part_no, mpl.description
                    FROM master_parts_list mpl
                    JOIN pdf_section ps ON mpl.section_id=ps.section_id
                    WHERE ps.section_name = :sn AND mpl.ref_no = :rn
                    ORDER BY mpl.part_no
                """), {"sn": sect, "rn": sel})
            for part_no, desc in pr:
                c1, c2 = st.columns([3,5], gap="small")
                with c1:
                    st.markdown(f"**{part_no}**")
                with c2:
                    st.write(desc)
                if b == "Yamaha":
                    qcol, bcol = st.columns([1,1], gap="small")
                    with qcol:
                        st.number_input("Qty:", min_value=1, value=1, key=f"add_qty_{part_no}")
                    with bcol:
                        if st.button(f"Add to Cart", key=f"add_{part_no}"):
                            add_to_cart(part_no)
                            st.rerun()
                else:
                    c3, c4 = st.columns([2,2], gap="small")
                    with c3:
                        st.number_input("Qty:", min_value=1, value=1, key=f"add_qty_{part_no}")
                    with c4:
                        st.button(
                            "Add to Cart",
                            key=f"add_{part_no}",
                            on_click=add_to_cart,
                            args=(part_no,),
                        )
                if st.session_state.get("just_added", [None])[0] == part_no:
                    added_qty = st.session_state.pop("just_added")[1]
                    st.success(f"Added {added_qty} × {part_no} to cart")
                st.markdown("---")
    else:
        img_col, detail_col = st.columns([2,3], gap="medium")
        with img_col:
            st.markdown("<div class='zoom-container'>", unsafe_allow_html=True)
            st.image(zoomed)
            st.markdown("</div>", unsafe_allow_html=True)
        with detail_col:
            if st.session_state.current_ref is None:
                st.markdown("**Reference Numbers**")
                for i in range(0, len(ref_nos), cfg["refs_per_row"]):
                    cols = st.columns(cfg["refs_per_row"], gap="small")
                    for col, ref in zip(cols, ref_nos[i : i + cfg["refs_per_row"]]):
                        with col:
                            if st.button(str(ref), key=f"r2_{ref}"):
                                st.session_state.current_ref = ref
                                st.rerun()
            else:
                sel = st.session_state.current_ref
                st.markdown(f"**Parts for Reference {sel}**")
                with engine.connect() as conn:
                    pr = conn.execute(text("""
                        SELECT mpl.part_no, mpl.description
                        FROM master_parts_list mpl
                        JOIN pdf_section ps ON mpl.section_id=ps.section_id
                        WHERE ps.section_name = :sn AND mpl.ref_no = :rn
                    """), {"sn": sect, "rn": sel})
                for part_no, desc in pr:
                    c1, c2 = st.columns([3,5], gap="small")
                    with c1:
                        st.markdown(f"**{part_no}**")
                    with c2:
                        st.write(desc)
                    if b == "Yamaha":
                        qcol, bcol = st.columns([1,1], gap="small")
                        with qcol:
                            st.number_input("Qty:", min_value=1, value=1, key=f"add_qty_{part_no}")
                        with bcol:
                            if st.button(f"Add to Cart", key=f"add_{part_no}"):
                                add_to_cart(part_no)
                                st.rerun()
                    else:
                        c3, c4 = st.columns([2,2], gap="small")
                        with c3:
                            st.number_input("Qty:", min_value=1, value=1, key=f"add_qty_{part_no}")
                        with c4:
                            if st.button(f"Add to Cart", key=f"add_{part_no}"):
                                add_to_cart(part_no)
                                st.rerun()
                    if st.session_state.get("just_added", [None])[0] == part_no:
                        added_qty = st.session_state.pop("just_added")[1]
                        st.success(f"Added {added_qty} × {part_no} to cart")
                    st.markdown("---")
# Final toast
if "just_added" in st.session_state:
    part, qty = st.session_state.pop("just_added")
    st.success(f"Added {qty}×{part} to cart")

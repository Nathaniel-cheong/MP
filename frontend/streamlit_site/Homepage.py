from imports import engine
import streamlit as st
from sqlalchemy import text
from io import BytesIO
from PIL import Image as PILImage, UnidentifiedImageError
from streamlit_app import gen_basket_id

# ─── CACHING SETUP ─────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_engine():
    return engine

@st.cache_data(ttl=3600, show_spinner=False)
def get_brands():
    with get_engine().connect() as conn:
        rs = conn.execute(text("SELECT DISTINCT brand FROM pdf_info")).fetchall()
    return [r[0] for r in rs]

@st.cache_data(ttl=3600, show_spinner=False)
def get_years(brand: str):
    with get_engine().connect() as conn:
        rs = conn.execute(
            text("SELECT DISTINCT year FROM pdf_info WHERE brand=:b ORDER BY year DESC"),
            {"b": brand}
        ).fetchall()
    return [r[0] for r in rs]

@st.cache_data(ttl=3600, show_spinner=False)
def get_models(brand: str):
    with get_engine().connect() as conn:
        rs = conn.execute(
            text("SELECT DISTINCT model FROM pdf_info WHERE brand=:b"),
            {"b": brand}
        ).fetchall()
    return [r[0] for r in rs]

@st.cache_data(ttl=3600, show_spinner=False)
def get_cc_list(brand: str, model: str):
    with get_engine().connect() as conn:
        rs = conn.execute(text("""
            SELECT DISTINCT ps.cc
              FROM pdf_section ps
              JOIN pdf_info pi ON ps.pdf_id = pi.pdf_id
             WHERE pi.brand = :b AND pi.model = :m
        """), {"b": brand, "m": model}).fetchall()
    return [r[0] for r in rs]

@st.cache_data(ttl=3600, show_spinner=False)
def get_sections(brand: str, model: str, cc):
    with get_engine().connect() as conn:
        rs = conn.execute(text("""
            SELECT ps.section_name, ps.section_image
              FROM pdf_section ps
              JOIN pdf_info pi ON ps.pdf_id = pi.pdf_id
             WHERE pi.brand = :b AND pi.model = :m AND ps.cc = :c
        """), {"b": brand, "m": model, "c": cc}).fetchall()
    return [
        (r[0], bytes(r[1]) if isinstance(r[1], memoryview) else r[1])
        for r in rs
    ]

@st.cache_data(show_spinner=False)
def process_image(img_bytes: bytes, size: tuple[int, int]):
    pil = PILImage.open(BytesIO(img_bytes)).convert("RGB")
    return pil.resize(size, resample=PILImage.BICUBIC)


# ─── CALLBACKS ────────────────────────────────────────────────────────────
def go_to_brand(brand):
    st.session_state.current_brand = brand
    st.session_state.page_num = 1

def go_to_model(model):
    st.session_state.current_model = model
    st.session_state.page_num = 2

def go_to_cc(cc):
    st.session_state.current_cc = cc
    st.session_state.page_num = 3

def go_to_section(section, raw_image):
    st.session_state.current_section = section
    st.session_state.zoom_image = raw_image
    st.session_state.page_num = 4

def go_back():
    p = st.session_state.page_num
    if p == 4:
        st.session_state.current_ref = None
        st.session_state.page_num = 3
    elif p == 3:
        st.session_state.current_cc = None
        st.session_state.page_num = 2
    elif p == 2:
        st.session_state.current_model = None
        st.session_state.page_num = 1
    elif p == 1:
        st.session_state.current_brand = None
        st.session_state.page_num = 0

def add_to_cart(part: str):
    qty = st.session_state.get(f"add_qty_{part}", 1)
    cart = st.session_state.cart_data
    parts, qtys = cart["part_no"][0], cart["quantity"][0]
    if part in parts:
        qtys[parts.index(part)] += qty
    else:
        parts.append(part)
        qtys.append(qty)
    st.session_state.just_added = (part, qty)


# ─── PAGE CONFIG & GLOBAL CSS ─────────────────────────────────────────────
st.set_page_config(layout="wide", initial_sidebar_state="expanded")
st.markdown("""
    <style>
      .stButton > button { width: 150px; height: 70px; font-size: 16px; }
      .zoom-container img { position: sticky; top: 0; z-index: 100; }
      .hide-sidebar [data-testid="stSidebar"] { display: none; }
    </style>
""", unsafe_allow_html=True)


# ─── STATE INITIALIZATION ─────────────────────────────────────────────────
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

if "cart_data" not in st.session_state:
    st.session_state.cart_data = {
        "basket_id":     [gen_basket_id()],
        "part_no":       [[]],
        "quantity":      [[]],
        "purchase_type": [],
        "customer_name": [],
        "contact":       [],
        "email":         [],
        "postal_code":   [],
        "address":       []
    }


# ─── SEARCH BAR: clear on every page change ─────────────────────────────────
prev_page = st.session_state.get("prev_page")
curr_page = st.session_state.page_num
if prev_page is not None and prev_page != curr_page:
    st.session_state.search = ""
st.session_state.prev_page = curr_page

# render on pages 0, 1, and 3
search = ""
if curr_page in (0, 1, 3):
    search = st.text_input("🔍 Search", key="search")
else:
    st.session_state.search = ""


# ─── BRAND LAYOUT CONFIG ──────────────────────────────────────────────────
BRAND_CONFIG = {
    "Honda":  {"section_img_size": (350,200), "sections_per_row":3, "refs_per_row":5, "page4_layout":"top_image",  "model_img_size":(300,200)},
    "Yamaha": {"section_img_size": (250,350), "sections_per_row":4, "refs_per_row":4, "page4_layout":"side_image", "model_img_size":(300,200)},
    "__default__": {"section_img_size": (250,350), "sections_per_row":4, "refs_per_row":4, "page4_layout":"side_image", "model_img_size":(300,200)},
}


# ─── MAIN UI ───────────────────────────────────────────────────────────────
st.title("Homepage")

# Page 0: Brands
if curr_page == 0:
    st.subheader("Please Choose a Brand")
    brands = get_brands()
    if search:
        brands = [b for b in brands if b.lower() == search.lower()]
        if not brands:
            st.info(f"Sorry, we don’t have a brand named “{search}.”")
            st.stop()
    cols = st.columns([1]*len(brands) + [len(brands)], gap="small")
    for col, b in zip(cols[:-1], brands):
        with col:
            url = {
                "Honda":"frontend/streamlit_site/images/honda.svg",
                "Yamaha":"frontend/streamlit_site/images/Yamaha_Logo.jpg"
            }.get(b)
            if url: st.image(url, width=250)
            else:   st.write(b)
            st.button(b, on_click=go_to_brand, args=(b,), key=f"brand_{b}")

# Page 1: Models
elif curr_page == 1:
    st.button("« Back", on_click=go_back, key="back_brand")
    brand = st.session_state.current_brand
    st.subheader(f"{brand} Models")

    # ← narrow the year filter to just one column
    col_filter, _ = st.columns([1, 4], gap="small")
    with col_filter:
        sel = st.selectbox(
            "Filter by year", 
            ["All"] + [str(y) for y in get_years(brand)],
            key="year_filter"
        )
    if sel == "All":
        models = get_models(brand)
    else:
        with get_engine().connect() as conn:
            rs = conn.execute(
                text("SELECT DISTINCT model FROM pdf_info WHERE brand=:b AND year=:y"),
                {"b": brand, "y": int(sel)}
            ).fetchall()
        models = [r[0] for r in rs]

    if search:
        models = [m for m in models if m.lower() == search.lower()]
        if not models:
            st.info(f"Sorry, we don’t have a {brand} model named “{search}.”")
            st.stop()

    cfg = BRAND_CONFIG.get(brand, BRAND_CONFIG["__default__"])
    size = cfg["model_img_size"]
    DEFAULT_IMG = "frontend/streamlit_site/images/default_bike.jpg"

    cols = st.columns([1]*len(models) + [len(models)], gap="small")
    for col, m in zip(cols[:-1], models):
        with col:
            row = get_engine().connect().execute(
                text("SELECT bike_image FROM pdf_info WHERE brand=:b AND model=:m LIMIT 1"),
                {"b": brand, "m": m}
            ).fetchone()
            blob = row[0] if row and row[0] else None
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
            st.button(m, on_click=go_to_model, args=(m,), key=f"model_{m}")

# Page 2: CC
elif curr_page == 2:
    st.button("« Back", on_click=go_back, key="back_model")
    brand, model = st.session_state.current_brand, st.session_state.current_model
    st.subheader(f"{brand} {model} — Select CC")
    cc_list = get_cc_list(brand, model)
    cols = st.columns([1]*len(cc_list) + [len(cc_list)], gap="small")
    for col, c in zip(cols[:-1], cc_list):
        with col:
            st.button(str(c), on_click=go_to_cc, args=(c,), key=f"cc_{c}")

# Page 3: Sections
elif curr_page == 3:
    st.button("« Back", on_click=go_back, key="back_cc")
    b, m, cc = (
        st.session_state.current_brand,
        st.session_state.current_model,
        st.session_state.current_cc
    )
    st.subheader(f"{b} {m} — CC {cc} Sections")
    sections = get_sections(b, m, cc)
    if search:
        sections = [s for s in sections if search.lower() in s[0].lower()]
    cfg = BRAND_CONFIG.get(b, BRAND_CONFIG["__default__"])
    for i in range(0, len(sections), cfg["sections_per_row"]):
        chunk = sections[i : i + cfg["sections_per_row"]]
        cols  = st.columns(cfg["sections_per_row"], gap="small")
        for col, (name, raw) in zip(cols, chunk):
            with col:
                st.image(process_image(raw, cfg["section_img_size"]))
                st.button(name, on_click=go_to_section, args=(name, raw), key=f"sec_{name}")
        st.markdown("---")

# Page 4: Zoom & References
elif curr_page == 4:
    st.button("« Back", on_click=go_back, key="back_section")
    b = st.session_state.current_brand
    cfg = BRAND_CONFIG.get(b, BRAND_CONFIG["__default__"])
    sect = st.session_state.current_section
    st.subheader(sect)

    with get_engine().connect() as conn:
        rs = conn.execute(text("""
            SELECT DISTINCT mpl.ref_no
              FROM master_parts_list mpl
              JOIN pdf_section ps ON mpl.section_id=ps.section_id
             WHERE ps.section_name = :sn
             ORDER BY mpl.ref_no
        """), {"sn": sect}).fetchall()
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
                        st.button(
                            str(ref),
                            on_click=lambda r=ref: st.session_state.update({"current_ref": r}),
                            key=f"ref_{ref}"
                        )
        else:
            sel = st.session_state.current_ref
            st.markdown(f"**Parts for Reference {sel}**")
            with get_engine().connect() as conn:
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
                st.number_input("Qty:", min_value=1, value=1, key=f"add_qty_{part_no}")
                st.button(
                    "Add to Cart",
                    on_click=add_to_cart,
                    args=(part_no,),
                    key=f"add_{part_no}"
                )
                if st.session_state.get("just_added", [None])[0] == part_no:
                    added_qty = st.session_state.pop("just_added")[1]
                    st.success(f"Added {added_qty}×{part_no} to cart")
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
                            st.button(
                                str(ref),
                                on_click=lambda r=ref: st.session_state.update({"current_ref": r}),
                                key=f"ref2_{ref}"
                            )
            else:
                sel = st.session_state.current_ref
                st.markdown(f"**Parts for Reference {sel}**")
                with get_engine().connect() as conn:
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
                    st.number_input("Qty:", min_value=1, value=1, key=f"add_qty_{part_no}")
                    st.button(
                        "Add to Cart",
                        on_click=add_to_cart,
                        args=(part_no,),
                        key=f"add2_{part_no}"
                    )
                    if st.session_state.get("just_added", [None])[0] == part_no:
                        added_qty = st.session_state.pop("just_added")[1]
                        st.success(f"Added {added_qty}×{part_no} to cart")
                    st.markdown("---")

# Final toast
if "just_added" in st.session_state:
    part, qty = st.session_state.pop("just_added")
    st.success(f"Added {qty}×{part} to cart")

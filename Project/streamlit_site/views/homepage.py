from imports import *

# Persistence Helpers
from streamlit_app import (
    load_cart_from_disk,
    save_cart_to_disk,
    load_session_state,
    save_session_state,
    APP_STATE_PATH,
)

# Load or reset navigation state
if os.path.exists(APP_STATE_PATH):
    load_session_state()
else:
    st.session_state["page_num"]        = 0
    st.session_state["current_brand"]   = None
    st.session_state["current_model"]   = None
    st.session_state["current_cc"]      = None
    st.session_state["current_section"] = None
    st.session_state["current_ref"]     = None
    st.session_state["zoom_image"]      = None

# a Fix any None navigation keys
nav_keys = ["page_num","current_brand","current_model","current_cc",
            "current_section","current_ref","zoom_image"]
defaults = [0, None, None, None, None, None, None]
for key, default in zip(nav_keys, defaults):
    if key not in st.session_state or st.session_state[key] is None:
        st.session_state[key] = default

# Clear search on page change
prev_page = st.session_state.get("prev_page")
curr_page = st.session_state.page_num
if prev_page is not None and prev_page != curr_page:
    st.session_state.search = ""
st.session_state.prev_page = curr_page

# Load or initialize cart_data
if "cart_data" not in st.session_state:
    disk = load_cart_from_disk()
    if disk:
        st.session_state.cart_data = disk
    else:
        st.session_state.cart_data = {"part_no": [[]], "quantity": [[]]}
        save_cart_to_disk()
cart = st.session_state.cart_data

# Add-to-cart helper function
def add_to_cart(part: str):
    qty = st.session_state.get(f"add_qty_{part}", 1)
    parts, qtys = cart["part_no"][0], cart["quantity"][0]
    if part in parts:
        qtys[parts.index(part)] += qty
    else:
        parts.append(part); qtys.append(qty)
    st.session_state.just_added = (part, qty)
    save_session_state(); save_cart_to_disk()

# Brand-specific config + image cache
BRAND_CONFIG = {
    "Honda":  {"section_img_size": (350,200), "sections_per_row":3, "refs_per_row":5, "page4_layout":"top_image"},
    "Yamaha": {"section_img_size": (250,350), "sections_per_row":4, "refs_per_row":4, "page4_layout":"side_image"},
    "__default__": {"section_img_size": (250,350), "sections_per_row":4, "refs_per_row":4, "page4_layout":"side_image"},
}
@st.cache_data(show_spinner=False)
def process_image(img_bytes: bytes, size: tuple[int,int]):
    pil = PILImage.open(BytesIO(img_bytes)).convert("RGB")
    return pil.resize(size, resample=PILImage.BICUBIC)

# session_state defaults for caches
for name in ("brands_list","models_dict","cc_dict","sections_dict"):
    st.session_state.setdefault(name, {} if name!="brands_list" else None)

# Data-loading helpers
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
        d[key] = [(r[0], bytes(r[1]) if isinstance(r[1],memoryview) else r[1]) for r in rs]
    return d[key]

# Search bar & URL override
params = st.query_params
search = st.text_input("🔍 Search", key="search")
if "page_num" in params:
    try: st.session_state.page_num = int(params["page_num"][0])
    except: pass

# Multi-page UI
st.title("Homepage")

# Page 0: Brands Selection
if st.session_state.page_num == 0:
    st.subheader("Please Choose a Brand")
    brands = get_brands()
    if search:
        filtered = [b for b in brands if b.lower()==search.lower()]
        if not filtered:
            st.info(f"Sorry, we don’t have a brand named “{search}.”"); st.stop()
        brands = filtered
    weights = [1]*len(brands) + [len(brands)]
    cols = st.columns(weights, gap="small")
    for col, b in zip(cols[:-1], brands):
        with col:
            url = {"Honda":"images/honda.svg",
                   "Yamaha":"images/Yamaha_Logo.jpg"}.get(b)
            if url: st.image(url, width=250)
            else: st.write(b)
            if st.button(b):
                st.session_state.current_brand = b
                st.session_state.page_num     = 1
                save_session_state(); st.rerun()

# Page 1: Models Selection
elif st.session_state.page_num == 1:
    if st.button("« Back", key="b1"):
        st.session_state.page_num     = 0
        st.session_state.current_brand = None
        save_session_state(); st.rerun()

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
            st.info(f"Sorry, we don’t have a {brand} model named “{search}.”"); st.stop()
        models = m2

    # DEFAULT IMAGE PATH
    DEFAULT_BIKE_IMAGE_PATH = "images/default_bike.jpg"
    cols = st.columns([1]*len(models) + [len(models)], gap="small")
    for col, m in zip(cols[:-1], models):
        with col:
            #fetch one row; might be (None,) if bike_image IS NULL
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT bike_image
                      FROM pdf_info
                     WHERE brand = :b
                       AND model = :m
                     LIMIT 1
                """), {"b": brand, "m": m}).fetchone()

            # explicit check for None
            img_blob = row[0] if row and row[0] is not None else None

            if img_blob:
                st.image(BytesIO(img_blob), use_container_width=True)
            else:
                st.image(DEFAULT_BIKE_IMAGE_PATH, use_container_width=True)

            if st.button(m):
                st.session_state.current_model = m
                st.session_state.page_num      = 2
                save_session_state()
                st.rerun()

# Page 2: CC Selection
elif st.session_state.page_num == 2:
    if st.button("« Back", key="b2"):
        st.session_state.page_num     = 1
        st.session_state.current_model = None
        save_session_state(); st.rerun()
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
                save_session_state(); st.rerun()

# Page 3: Sections Picture + Name Display
elif st.session_state.page_num == 3:
    if st.button("« Back", key="b3"):
        st.session_state.page_num    = 2
        st.session_state.current_cc  = None
        save_session_state(); st.rerun()
    b,m,cc = (st.session_state.current_brand,
              st.session_state.current_model,
              st.session_state.current_cc)
    st.subheader(f"{b} {m} — CC {cc} Sections")
    sections = get_sections(b,m,cc)
    if search:
        sections = [r for r in sections if search.lower() in r[0].lower()]
    cfg = BRAND_CONFIG.get(b, BRAND_CONFIG["__default__"])
    for i in range(0, len(sections), cfg["sections_per_row"]):
        chunk = sections[i:i+cfg["sections_per_row"]]
        cols = st.columns(cfg["sections_per_row"], gap="small")
        for col, (name, raw) in zip(cols, chunk):
            with col:
                st.image(process_image(raw, cfg["section_img_size"]))
                if st.button(name, key=f"s_{name}"):
                    st.session_state.current_section = name
                    st.session_state.zoom_image       = raw
                    st.session_state.page_num         = 4
                    save_session_state(); st.rerun()
        st.markdown("---")

# Page 4: Zoomed Picture & Reference Numbers
elif st.session_state.page_num == 4:
    back_label = "⟵ Back to References" if st.session_state.current_ref else "« Back"
    if st.button(back_label, key="b4"):
        if st.session_state.current_ref:
            st.session_state.current_ref = None
        else:
            st.session_state.page_num = 3
        save_session_state(); st.rerun()

    b   = st.session_state.current_brand
    cfg = BRAND_CONFIG.get(b, BRAND_CONFIG["__default__"])
    sect= st.session_state.current_section
    st.subheader(sect)

    with engine.connect() as conn:
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
                for col, ref in zip(cols, ref_nos[i:i+cfg["refs_per_row"]]):
                    with col:
                        if st.button(str(ref), key=f"r_{ref}"):
                            st.session_state.current_ref = ref
                            save_session_state(); st.rerun()

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
                """), {"sn": sect, "rn": sel}).fetchall()

            for part_no, desc in pr:
                # part_no + description on first row
                c1, c2 = st.columns([3,5], gap="small")
                with c1:
                    st.markdown(f"**{part_no}**")
                with c2:
                    st.write(desc)

                if b == "Yamaha":
                    # second row for Yamaha
                    qcol, bcol = st.columns([1,1], gap="small")
                    with qcol:
                        st.number_input("Qty:", min_value=1, value=1, key=f"add_qty_{part_no}")
                    with bcol:
                        st.button("Add to Cart",
                                  key=f"add_{part_no}",
                                  on_click=add_to_cart,
                                  args=(part_no,))
                else:
                    # inline for others
                    c3, c4 = st.columns([2,2], gap="small")
                    with c3:
                        st.number_input("Qty:", min_value=1, value=1, key=f"add_qty_{part_no}")
                    with c4:
                        st.button("Add to Cart",
                                  key=f"add_{part_no}",
                                  on_click=add_to_cart,
                                  args=(part_no,))

                if st.session_state.get("just_added") and st.session_state["just_added"][0] == part_no:
                    added_qty = st.session_state["just_added"][1]
                    st.success(f"Added {added_qty} × {part_no} to cart")
                    st.session_state.pop("just_added")
                st.markdown("---")

    else:
        # side_image layout
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
                    for col, ref in zip(cols, ref_nos[i:i+cfg["refs_per_row"]]):
                        with col:
                            if st.button(str(ref), key=f"r2_{ref}"):
                                st.session_state.current_ref = ref
                                save_session_state(); st.rerun()
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
                    """), {"sn": sect, "rn": sel}).fetchall()
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
                            st.button("Add to Cart",
                                      key=f"add_{part_no}",
                                      on_click=add_to_cart,
                                      args=(part_no,))
                    else:
                        c3, c4 = st.columns([2,2], gap="small")
                        with c3:
                            st.number_input("Qty:", min_value=1, value=1, key=f"add_qty_{part_no}")
                        with c4:
                            st.button("Add to Cart",
                                      key=f"add_{part_no}",
                                      on_click=add_to_cart,
                                      args=(part_no,))
                    if st.session_state.get("just_added") and st.session_state["just_added"][0] == part_no:
                        added_qty = st.session_state["just_added"][1]
                        st.success(f"Added {added_qty} × {part_no} to cart")
                        st.session_state.pop("just_added")
                    st.markdown("---")

# Notify on add
if "just_added" in st.session_state:
    part, qty = st.session_state.pop("just_added")
    st.success(f"Added {qty}×{part} to cart")

save_session_state()
from imports import engine
import streamlit as st
from sqlalchemy import text
from io import BytesIO
from PIL import Image as PILImage, UnidentifiedImageError
from streamlit_app import gen_basket_id
import uuid, json
from streamlit_cookies_manager import EncryptedCookieManager
from pathlib import Path

# ─── PAGE CONFIG & GLOBAL CSS ─────────────────────────────────────────────
try:
    st.set_page_config(layout="wide", initial_sidebar_state="expanded")
except Exception:
    pass

HERE = Path(__file__).parent
IMAGE_DIR = HERE / "images"

st.markdown("""
    <style>
      .stButton > button { width: 150px; height: 70px; font-size: 16px; }
      .zoom-container img { position: sticky; top: 0; z-index: 100; }
      .hide-sidebar [data-testid="stSidebar"] { display: none; }
    </style>
""", unsafe_allow_html=True)

# ─── COOKIE SETUP ──────────────────────────────────────────────────────────
cookies = EncryptedCookieManager(
    prefix="my_app/",
    password="your-32-byte-long-secret-key-here"
)
if not cookies.ready():
    st.stop()

# Mint visitor_id once
visitor_id = cookies.get("visitor_id")
if visitor_id is None:
    visitor_id = str(uuid.uuid4())
    cookies["visitor_id"] = visitor_id
    cookies.save()             # ← push the new cookie to the browser
    st.rerun()    # ← reload so that the rest of your script sees it
st.session_state.setdefault("visitor_id", visitor_id)

# Restore page/view state cookie (only if fresh session)
view_json = cookies.get("view_state", None)
if view_json and st.session_state.get("page_num", 0) == 0:
    try:
        saved = json.loads(view_json)
        st.session_state.page_num        = saved.get("page_num", 0)
        st.session_state.current_brand   = saved.get("current_brand")
        st.session_state.current_model   = saved.get("current_model")
        st.session_state.current_cc      = saved.get("current_cc")
        st.session_state.current_section = saved.get("current_section")
        st.session_state.current_ref     = saved.get("current_ref")
    except:
        pass

# ─── CACHEABLE DATA LOADERS ────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_engine():
    return engine

@st.cache_data(ttl=3600, show_spinner=False)
def get_brands():
    with get_engine().connect() as conn:
        return [r[0] for r in conn.execute(text("SELECT DISTINCT brand FROM pdf_info")).fetchall()]

@st.cache_data(ttl=3600, show_spinner=False)
def get_years(brand: str):
    with get_engine().connect() as conn:
        return [r[0] for r in conn.execute(
            text("SELECT DISTINCT year FROM pdf_info WHERE brand=:b ORDER BY year DESC"),
            {"b": brand}
        ).fetchall()]

@st.cache_data(ttl=3600, show_spinner=False)
def get_models(brand: str):
    with get_engine().connect() as conn:
        return [r[0] for r in conn.execute(
            text("SELECT DISTINCT model FROM pdf_info WHERE brand=:b"),
            {"b": brand}
        ).fetchall()]

@st.cache_data(ttl=3600, show_spinner=False)
def get_cc_list(brand: str, model: str):
    with get_engine().connect() as conn:
        return [r[0] for r in conn.execute(text("""
            SELECT DISTINCT ps.cc
              FROM pdf_section ps
              JOIN pdf_info pi ON ps.pdf_id = pi.pdf_id
             WHERE pi.brand = :b AND pi.model = :m
        """), {"b": brand, "m": model}).fetchall()]

@st.cache_data(show_spinner=False)
def get_sections(brand: str, model: str, cc):
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT ps.section_name, ps.section_image
              FROM pdf_section ps
              JOIN pdf_info pi ON ps.pdf_id = pi.pdf_id
             WHERE pi.brand = :b AND pi.model = :m AND ps.cc = :c
        """), {"b": brand, "m": model, "c": cc}).fetchall()
    return [(r[0], bytes(r[1]) if isinstance(r[1], memoryview) else r[1]) for r in rows]

if "img_cache" not in st.session_state:
    # maps (id, size) → PIL.Image
    st.session_state.img_cache = {}

def process_image(img_bytes: bytes, size: tuple[int,int]):
    """
    Resize the raw JPEG/PNG bytes to `size`, but only once per unique image+size
    during this session.  Returns a PIL.Image.
    """
    # derive a key that’s cheap to compare
    key = (hash(img_bytes), size)
    cache = st.session_state.img_cache

    if key not in cache:
        pil = PILImage.open(BytesIO(img_bytes)).convert("RGB")
        cache[key] = pil.resize(size, resample=PILImage.BICUBIC)
    return cache[key]

# ─── COOKIE‐SAVE HELPERS (deferred) ────────────────────────────────────────
def _save_view_cookie():
    cookies["view_state"] = json.dumps({
        "page_num":        st.session_state.page_num,
        "current_brand":   st.session_state.current_brand,
        "current_model":   st.session_state.current_model,
        "current_cc":      st.session_state.current_cc,
        "current_section": st.session_state.current_section,
        "current_ref":     st.session_state.current_ref,
    })

def _save_cart_cookie():
    cookies["cart_state"] = json.dumps(st.session_state.cart_data)

# ─── NAVIGATION CALLBACKS ──────────────────────────────────────────────────
def go_to_brand(b):
    st.session_state.current_brand = b
    st.session_state.page_num       = 1
    _save_view_cookie()

def go_to_model(m):
    st.session_state.current_model = m
    st.session_state.page_num       = 2
    _save_view_cookie()

def go_to_cc(cc):
    st.session_state.current_cc = cc
    st.session_state.page_num   = 3
    _save_view_cookie()

def go_to_section(sec, raw):
    st.session_state.current_section = sec
    st.session_state.zoom_image      = raw
    st.session_state.page_num        = 4
    _save_view_cookie()

def set_ref(r):
    st.session_state.current_ref = r
    _save_view_cookie()

def go_back():
    p = st.session_state.page_num

    # if we're on page 4 with a ref selected, clear just the ref
    if p == 4 and st.session_state.current_ref is not None:
        st.session_state.current_ref = None
        st.session_state.page_num    = 4

    # if we're on page 4 with no ref, go back to the CC list
    elif p == 4:
        st.session_state.page_num = 3

    # leaving the CC list (page 3) → clear zoom/section and go to page 2
    elif p == 3:
        st.session_state.current_cc      = None
        st.session_state.current_section = None
        st.session_state.zoom_image      = None
        st.session_state.page_num        = 2

    # leaving the model list (page 2)
    elif p == 2:
        st.session_state.current_model = None
        st.session_state.page_num      = 1

    # leaving the brand list (page 1)
    elif p == 1:
        st.session_state.current_brand = None
        st.session_state.page_num      = 0

    _save_view_cookie()


def add_to_cart(part):
    qty    = st.session_state.get(f"add_qty_{part}", 1)
    cart   = st.session_state.cart_data
    parts  = cart["part_no"][0]
    qtys   = cart["quantity"][0]
    brands = cart["item_brand"][0]
    models = cart["item_model"][0]
    b, m   = st.session_state.current_brand, st.session_state.current_model

    if part in parts:
        i = parts.index(part)
        qtys[i] += qty
    else:
        parts .append(part)
        qtys  .append(qty)
        brands.append(b)
        models.append(m)

    st.session_state.just_added = (part, qty)
    _save_cart_cookie()

# ─── INITIALIZE SESSION STATE ──────────────────────────────────────────────
for k,v in {
    "page_num":0, "current_brand":None, "current_model":None,
    "current_cc":None, "current_section":None, "current_ref":None,
    "zoom_image":None
}.items():
    st.session_state.setdefault(k, v)

# restore cart_data from cookie
if "cart_state" in cookies:
    try:
        st.session_state.cart_data = json.loads(cookies.get("cart_state"))
    except:
        pass

if "cart_data" not in st.session_state:
    st.session_state.cart_data = {
        "basket_id":[gen_basket_id()],
        "part_no":[[]],
        "quantity":[[]],
        "item_brand":    [[]],
        "item_model":    [[]],
        "purchase_type":[], "customer_name":[], "contact":[],
        "email":[], "postal_code":[], "address":[]
    }

# ─── OPTIONAL COOKIE DEBUG ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔧 Cookie Debug")
    st.write("All cookies:", dict(cookies))

# Title of page
st.title("Homepage")

# ─── SEARCH BAR STATE ──────────────────────────────────────────────────────
prev, curr = st.session_state.get("prev_page"), st.session_state.page_num
if prev is not None and prev != curr:
    st.session_state.search = ""
st.session_state.prev_page = curr

search = ""
if curr in (0,1,3):
    search = st.text_input("🔍 Search", key="search")

# ─── LAYOUT CONFIG ────────────────────────────────────────────────────────
BRAND_CONFIG = {
    "Honda":  {"section_img_size":(350,200), "sections_per_row":3, "refs_per_row":5, "page4_layout":"top_image", "model_img_size":(300,200)},
    "Yamaha": {"section_img_size":(250,350), "sections_per_row":4, "refs_per_row":4, "page4_layout":"side_image", "model_img_size":(300,200)},
    "__default__": {"section_img_size":(250,350), "sections_per_row":4, "refs_per_row":4, "page4_layout":"side_image", "model_img_size":(300,200)},
}

# ─── MAIN UI ───────────────────────────────────────────────────────────────
# Page 0: Brands
if curr == 0:
    st.subheader("Please Choose a Brand")
    brands = get_brands()
    if search:
        brands = [b for b in brands if b.lower()==search.lower()]
        if not brands:
            st.info(f"No brand named “{search}.”"); st.stop()
    cols = st.columns([1]*len(brands)+[len(brands)], gap="small")
    for col,b in zip(cols[:-1], brands):
        with col:
            url = { "Honda":str(IMAGE_DIR / "honda.svg"), "Yamaha":str(IMAGE_DIR / "Yamaha_Logo.jpg") }.get(b)
            if url and Path(url).exists(): st.image(url, width=250)
            else:   st.write(b)
            st.button(b, on_click=go_to_brand, args=(b,), key=f"brand_{b}")

# Page 1: Models
elif curr == 1:
    st.button("« Back", on_click=go_back, key="back0")
    br = st.session_state.current_brand
    st.subheader(f"{br} Models")
    colf,_ = st.columns([1,4], gap="small")
    with colf:
        yrs = ["All"] + [str(y) for y in get_years(br)]
        sel = st.selectbox("Filter by year", yrs, key="yr")
    models = get_models(br) if sel=="All" else [
        r[0] for r in get_engine().connect()
                          .execute(text(
                              "SELECT model FROM pdf_info WHERE brand=:b AND year=:y"
                          ),{"b":br,"y":int(sel)}).fetchall()
    ]
    if search:
        models = [m for m in models if m.lower()==search.lower()]
        if not models:
            st.info(f"No {br} model “{search}.”"); st.stop()
    cfg = BRAND_CONFIG.get(br, BRAND_CONFIG["__default__"])
    size = cfg["model_img_size"]
    DEFAULT_IMG = "MP/frontend/streamlit_site/images/default_bike.jpg"
    cols = st.columns([1]*len(models)+[len(models)], gap="small")
    for col,m in zip(cols[:-1], models):
        with col:
            row = get_engine().connect().execute(
                text("SELECT bike_image FROM pdf_info WHERE brand=:b AND model=:m LIMIT 1"),
                {"b":br,"m":m}
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
            st.button(m, on_click=go_to_model, args=(m,), key=f"mdl_{m}")

# Page 2: CC
elif curr == 2:
    st.button("« Back", on_click=go_back, key="back1")
    br,md = st.session_state.current_brand, st.session_state.current_model
    st.subheader(f"{br} {md} — Select CC")
    ccs = get_cc_list(br,md)
    cols=st.columns([1]*len(ccs)+[len(ccs)], gap="small")
    for col,c in zip(cols[:-1],ccs):
        with col:
            st.button(str(c), on_click=go_to_cc, args=(c,), key=f"cc_{c}")

# Page 3: Sections
elif curr == 3:
    st.button("« Back", on_click=go_back, key="back2")
    b,m,cc= st.session_state.current_brand, st.session_state.current_model, st.session_state.current_cc
    st.subheader(f"{b} {m} — CC {cc} Sections")
    secs = get_sections(b,m,cc)
    if search:
        secs=[s for s in secs if search.lower() in s[0].lower()]
    cfg=BRAND_CONFIG.get(b,BRAND_CONFIG["__default__"])
    for i in range(0,len(secs),cfg["sections_per_row"]):
        chunk=secs[i:i+cfg["sections_per_row"]]
        cols=st.columns(cfg["sections_per_row"],gap="small")
        for col,(name,raw) in zip(cols,chunk):
            with col:
                st.image(process_image(raw,cfg["section_img_size"]))
                st.button(name,on_click=go_to_section,args=(name,raw),key=f"sec_{name}")
        st.markdown("---")

# Page 4: Zoom & References
elif curr == 4:
    st.button("« Back", on_click=go_back, key="back3")
    b=st.session_state.current_brand
    cfg=BRAND_CONFIG.get(b,BRAND_CONFIG["__default__"])
    sect=st.session_state.current_section
    st.subheader(sect)

    with get_engine().connect() as conn:
        rs=conn.execute(text("""
            SELECT DISTINCT mpl.ref_no
              FROM master_parts_list mpl
              JOIN pdf_section ps ON mpl.section_id=ps.section_id
             WHERE ps.section_name=:sn
             ORDER BY mpl.ref_no
        """),{"sn":sect}).fetchall()
    ref_nos=[r[0] for r in rs]

    if st.session_state.zoom_image is None:
        for name,raw in get_sections(
            st.session_state.current_brand,
            st.session_state.current_model,
            st.session_state.current_cc
        ):
            if name==sect:
                st.session_state.zoom_image=raw; break

    zoomed=PILImage.open(BytesIO(st.session_state.zoom_image)).convert("RGB")
    zoomed.thumbnail((500,750),PILImage.BICUBIC)

    if cfg["page4_layout"]=="top_image":
        st.image(zoomed,use_container_width=True)
        if st.session_state.current_ref is None:
            st.markdown("**Reference Numbers**")
            for i in range(0,len(ref_nos),cfg["refs_per_row"]):
                cols=st.columns(cfg["refs_per_row"],gap="small")
                for col,ref in zip(cols,ref_nos[i:i+cfg["refs_per_row"]]):
                    with col:
                        st.button(str(ref),on_click=set_ref,args=(ref,),key=f"ref_{ref}")
        else:
            sel=st.session_state.current_ref
            st.markdown(f"**Parts for Reference {sel}**")
            with get_engine().connect() as conn:
                pr=conn.execute(text("""
                    SELECT mpl.part_no,mpl.description
                      FROM master_parts_list mpl
                      JOIN pdf_section ps ON mpl.section_id=ps.section_id
                     WHERE ps.section_name=:sn AND mpl.ref_no=:rn
                     ORDER BY mpl.part_no
                """),{"sn":sect,"rn":sel})
            for part_no, desc in pr:
                if st.session_state.current_brand == "Honda":
                    # ─── Inline 4-column layout for Honda ────────────────────────
                    c1, c2, c3, c4 = st.columns([3, 5, 2, 2], gap="small")
                    with c1:
                        st.markdown(f"**{part_no}**")
                    with c2:
                        st.write(desc)
                    with c3:
                        st.number_input(
                            label="", 
                            min_value=1,
                            value=1,
                            key=f"add_qty_{part_no}"
                        )
                    with c4:
                        st.button(
                            "Add to Cart",
                            on_click=add_to_cart,
                            args=(part_no,),
                            key=f"add_{part_no}"
                        )
                else:
                    # ─── Stacked layout for everybody else (Yamaha, etc.) ───────
                    st.markdown(f"**{part_no}**")  
                    st.write(desc)
                    st.number_input(
                        "Qty:",  
                        min_value=1,
                        value=1,
                        key=f"add_qty_{part_no}"
                    )
                    st.button(
                        "Add to Cart",
                        on_click=add_to_cart,
                        args=(part_no,),
                        key=f"add_{part_no}"
                    )

                # common toast
                if st.session_state.get("just_added", [None])[0] == part_no:
                    added_qty = st.session_state.pop("just_added")[1]
                    st.success(f"Added {added_qty}×{part_no} to cart")
                st.markdown("---")
    else:
        img_col,detail_col=st.columns([2,3],gap="medium")
        with img_col:
            st.markdown("<div class='zoom-container'>",unsafe_allow_html=True)
            st.image(zoomed)
            st.markdown("</div>",unsafe_allow_html=True)
        with detail_col:
            if st.session_state.current_ref is None:
                st.markdown("**Reference Numbers**")
                for i in range(0,len(ref_nos),cfg["refs_per_row"]):
                    cols=st.columns(cfg["refs_per_row"],gap="small")
                    for col,ref in zip(cols,ref_nos[i:i+cfg["refs_per_row"]]):
                        with col:
                            st.button(str(ref),on_click=set_ref,args=(ref,),key=f"ref2_{ref}")
            else:
                sel=st.session_state.current_ref
                st.markdown(f"**Parts for Reference {sel}**")
                with get_engine().connect() as conn:
                    pr=conn.execute(text("""
                        SELECT mpl.part_no,mpl.description
                          FROM master_parts_list mpl
                          JOIN pdf_section ps ON mpl.section_id=ps.section_id
                         WHERE ps.section_name=:sn AND mpl.ref_no=:rn
                    """),{"sn":sect,"rn":sel})
                for part_no,desc in pr:
                    c1,c2=st.columns([3,5],gap="small")
                    with c1: st.markdown(f"**{part_no}**")
                    with c2: st.write(desc)
                    st.number_input("Qty:",min_value=1,value=1,key=f"add_qty_{part_no}")
                    st.button("Add to Cart",on_click=add_to_cart,args=(part_no,),key=f"add2_{part_no}")
                    if st.session_state.get("just_added",[None])[0]==part_no:
                        added=st.session_state.pop("just_added")[1]
                        st.success(f"Added {added}×{part_no} to cart")
                    st.markdown("---")

cookies.save()

if "just_added" in st.session_state:
    part,qty=st.session_state.pop("just_added")
    st.success(f"Added {qty}×{part} to cart")

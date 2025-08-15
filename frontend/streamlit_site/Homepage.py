from imports import engine
import streamlit as st
from sqlalchemy import text
from io import BytesIO
from PIL import Image as PILImage, UnidentifiedImageError
from streamlit_app import gen_basket_id
import uuid
import json
from streamlit_cookies_manager import EncryptedCookieManager
from pathlib import Path


# ─── PAGE CONFIG & GLOBAL CSS ─────────────────────────────────────────────
try:
    # Configure the Streamlit app layout and sidebar behavior
    st.set_page_config(layout="wide", initial_sidebar_state="expanded")
except Exception:
    # Some Streamlit runners restrict set_page_config after first run; ignore errors
    pass

# Paths to local assets (images)
HERE = Path(__file__).parent
IMAGE_DIR = HERE / "images"
DEFAULT_MODEL_IMG = IMAGE_DIR / "default_bike.jpg"

# Inject app-wide CSS for button sizing, sticky zoom image, optional hidden sidebar
st.markdown(
    """
    <style>
      .stButton > button { width: 150px; height: 70px; font-size: 16px; }
      .zoom-container img { position: sticky; top: 0; z-index: 100; }
      .hide-sidebar [data-testid="stSidebar"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── COOKIE SETUP ──────────────────────────────────────────────────────────
# Encrypted cookies handle lightweight persistence across sessions
cookies = EncryptedCookieManager(
    prefix="my_app/",                                  # namespace for this app's cookies
    password="your-32-byte-long-secret-key-here",     # encryption key (replace in production)
)

# Ensure cookie manager is initialized; otherwise stop and wait for reload
if not cookies.ready():
    st.stop()

# Create a unique visitor_id if not present (used to tie carts/sessions)
visitor_id = cookies.get("visitor_id")
if visitor_id is None:
    visitor_id = str(uuid.uuid4())           # generate a UUID
    cookies["visitor_id"] = visitor_id       # store in cookie
    cookies.save()                           # push to browser
    st.rerun()                               # reload so session_state picks it up
st.session_state.setdefault("visitor_id", visitor_id)

# Restore saved UI navigation state from cookie on a fresh session
view_json = cookies.get("view_state", None)
if view_json and st.session_state.get("page_num", 0) == 0:
    try:
        saved = json.loads(view_json)
        # Restore navigation + selection context
        st.session_state.page_num             = saved.get("page_num", 0)
        st.session_state.current_brand        = saved.get("current_brand")
        st.session_state.current_model        = saved.get("current_model")
        st.session_state.current_cc           = saved.get("current_cc")
        st.session_state.current_section      = saved.get("current_section")
        st.session_state.current_ref          = saved.get("current_ref")
        st.session_state.current_section_id   = saved.get("current_section_id")  # <-- restore id
    except:
        # Ignore corrupt/old cookie formats
        pass


# ─── CACHEABLE DATA LOADERS ────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_engine():
    # Return shared SQLAlchemy engine (cached as a resource)
    return engine


@st.cache_data(ttl=30, show_spinner=False)
def get_brands():
    # Fetch distinct active brands
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("""
            SELECT DISTINCT pi.brand
              FROM pdf_info pi
             WHERE pi.is_active = 1
            """)
        ).fetchall()
    # Flatten to a Python list
    return [r[0] for r in rows]


@st.cache_data(ttl=30, show_spinner=False)
def get_years(brand: str, cc: str):
    # Fetch available years for a given brand and CC (descending)
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("""
            SELECT DISTINCT pi.year
              FROM pdf_info pi
             WHERE pi.brand     = :b
               AND pi.cc        = :c
               AND pi.is_active = 1
             ORDER BY pi.year DESC
            """),
            {"b": brand, "c": cc}
        ).fetchall()
    return [r[0] for r in rows]


@st.cache_data(ttl=3600, show_spinner=False)
def get_cc_list(brand: str):
    # Fetch CC options for a brand
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("""
            SELECT DISTINCT pi.cc
              FROM pdf_info   pi
             WHERE pi.brand    = :b
               AND pi.is_active = 1
            """),
            {"b": brand}
        ).fetchall()
    return [r[0] for r in rows]


@st.cache_data(ttl=30, show_spinner=False)
def get_models(brand: str, cc: int):
    # Fetch models available for brand + CC
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("""
            SELECT DISTINCT pi.model
              FROM pdf_info   pi
             WHERE pi.brand    = :b
               AND pi.cc       = :c
               AND pi.is_active = 1
            """),
            {"b": brand, "c": cc}
        ).fetchall()
    return [r[0] for r in rows]


@st.cache_data(show_spinner=False)
def get_sections(brand: str, model: str, cc: str):
    # Fetch sections (id, name, image) for the selected brand/model/cc
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("""
            SELECT ps.section_id, ps.section_name, ps.section_image
              FROM pdf_section ps
              JOIN pdf_info    pi ON ps.pdf_id = pi.pdf_id
             WHERE pi.brand = :b
               AND pi.model = :m
               AND pi.cc    = :c
               AND pi.is_active = 1
            """),
            {"b": brand, "m": model, "c": cc}
        ).fetchall()

    # Ensure images are returned as raw bytes (memoryview→bytes)
    return [
        (r[0], r[1], bytes(r[2]) if isinstance(r[2], memoryview) else r[2])
        for r in rows
    ]


# Initialize per-session image cache for resized PIL images
if "img_cache" not in st.session_state:
    st.session_state.img_cache = {}  # (hash(img_bytes), size) → PIL.Image


def process_image(img_bytes: bytes, size: tuple[int,int]):
    """
    Resize raw image bytes to the desired size with caching to avoid
    re-decoding and re-resizing the same image multiple times.
    """
    key = (hash(img_bytes), size)
    cache = st.session_state.img_cache

    if key not in cache:
        pil = PILImage.open(BytesIO(img_bytes)).convert("RGB")
        cache[key] = pil.resize(size, resample=PILImage.BICUBIC)
    return cache[key]


# ─── COOKIE‐SAVE HELPERS (deferred) ────────────────────────────────────────
def _save_view_cookie():
    # Serialize current navigation and selection state to cookie
    cookies["view_state"] = json.dumps({
        "page_num":            st.session_state.get("page_num", 0),
        "current_brand":       st.session_state.get("current_brand", None),
        "current_cc":          st.session_state.get("current_cc", None),
        "current_model":       st.session_state.get("current_model", None),
        "current_section":     st.session_state.get("current_section", None),
        "current_ref":         st.session_state.get("current_ref", None),
        "current_section_id":  st.session_state.get("current_section_id", None),  # <-- save id
    })
    cookies.save()  # ensure it flushes immediately


def _save_cart_cookie():
    # Serialize entire cart to cookie for persistence
    cookies["cart_state"] = json.dumps(st.session_state.cart_data)
    cookies.save()


# ─── NAVIGATION CALLBACKS ──────────────────────────────────────────────────
def go_to_brand(b):
    # Set brand and advance to CC page
    st.session_state.current_brand = b
    st.session_state.page_num       = 1
    _save_view_cookie()


def go_to_cc(cc):
    # Set CC and advance to Models page
    st.session_state.current_cc = cc
    st.session_state.page_num   = 2
    _save_view_cookie()


def go_to_model(m):
    # Set model and advance to Sections page
    st.session_state.current_model = m
    st.session_state.page_num       = 3
    _save_view_cookie()


def go_to_section(sec_id, sec, raw):
    # Set current section and its preview image, then go to zoom/refs page
    st.session_state.current_section_id = sec_id
    st.session_state.current_section    = sec
    st.session_state.zoom_image         = raw
    st.session_state.page_num           = 4
    _save_view_cookie()


def set_ref(r):
    # Select a specific reference number to list its parts
    st.session_state.current_ref = r
    _save_view_cookie()


def go_back():
    # Back button handler: navigate up a level, clearing context appropriately
    p = st.session_state.page_num

    if p == 4 and st.session_state.current_ref is not None:
        # From part list → back to ref list (stay on page 4)
        st.session_state.current_ref = None
        st.session_state.page_num    = 4

    elif p == 4:
        # From section zoom → back to Sections page
        st.session_state.page_num = 3

    elif p == 3:
        # From Sections page → back to Models page
        st.session_state.current_section = None
        st.session_state.zoom_image      = None
        st.session_state.current_section_id = None
        st.session_state.page_num        = 2

    elif p == 2:
        # From Models page → back to CC page
        st.session_state.current_model = None
        st.session_state.page_num      = 1

    elif p == 1:
        # From CC page → back to Brands page
        st.session_state.current_brand = None
        st.session_state.page_num      = 0

    _save_view_cookie()


def add_to_cart(part, widget_key):
    # Append or increment a part in the cart, preserving brand/model for each line
    qty = st.session_state.get(f"add_qty_{widget_key}", 1)
    cart   = st.session_state.cart_data
    parts  = cart["part_no"][0]
    qtys   = cart["quantity"][0]
    brands = cart["item_brand"][0]
    models = cart["item_model"][0]
    b, m   = st.session_state.current_brand, st.session_state.current_model

    if part in parts:
        # If part is already present, just bump quantity
        i = parts.index(part)
        qtys[i] += qty
    else:
        # Else add a new line item
        parts.append(part)
        qtys.append(qty)
        brands.append(b)
        models.append(m)

    # Store a flag to show a success message after the button press
    st.session_state.just_added = (part, qty)
    _save_cart_cookie()                  # persist cart
    st.session_state.show_qr = False     # ensure cart view is shown, not QR
    st.session_state.view    = "cart"


# ─── INITIALIZE SESSION STATE ──────────────────────────────────────────────
# Provide defaults for navigation and selection state keys
for k, v in {
    "page_num": 0, "current_brand": None, "current_model": None,
    "current_cc":  None, "current_section": None, "current_ref":   None,
    "zoom_image": None,
    "current_section_id": None,   # <-- default added
}.items():
    st.session_state.setdefault(k, v)

# Initialize cart structure (with nested lists for line items) if missing
if "cart_data" not in st.session_state:
    st.session_state.cart_data = {
        "basket_id":    [gen_basket_id()],  # one basket id per cart
        "part_no":      [[]],               # list of part numbers
        "quantity":     [[]],               # list of quantities
        "item_brand":   [[]],               # brand per line item
        "item_model":   [[]],               # model per line item
        "purchase_type": [], "customer_name": [], "contact": [],
        "email":         [], "postal_code":  [], "address": []
    }

# Restore cart from cookie if available (backward-compatible)
if "cart_state" in cookies:
    try:
        st.session_state.cart_data = json.loads(cookies.get("cart_state"))
    except:
        # Ignore invalid cart cookie content
        pass

# Backfill missing keys for older cart_state structures
cart = st.session_state.cart_data
n    = len(cart["basket_id"])
if "item_brand" not in cart:
    cart["item_brand"] = [[] for _ in range(n)]
if "item_model" not in cart:
    cart["item_model"] = [[] for _ in range(n)]


# ─── SEARCH BAR STATE (only on Sections page) ─────────────────────────────
# Clear search box when navigating between pages so it doesn't leak across views
prev, curr = st.session_state.get("prev_page"), st.session_state.page_num
if prev is not None and prev != curr:
    st.session_state.pop("search", None)
st.session_state.prev_page = curr

# Only render search input on Sections (page 3)
search = ""
if curr == 3:
    search = st.text_input("🔍 Search Sections", key="search")


# ─── LAYOUT CONFIG ────────────────────────────────────────────────────────
# Per-brand UI config: section image sizes, grid layout, and page-4 layout mode
BRAND_CONFIG = {
    "Honda":  {"section_img_size": (350,200), "sections_per_row": 3, "refs_per_row": 5, "page4_layout": "top_image", "model_img_size": (300,200)},
    "Yamaha": {"section_img_size": (250,350), "sections_per_row": 4, "refs_per_row": 4, "page4_layout": "side_image","model_img_size": (300,200)},
    "__default__": {"section_img_size": (250,350), "sections_per_row": 4, "refs_per_row": 4, "page4_layout": "side_image","model_img_size": (300,200)},
}


# ─── MAIN UI ───────────────────────────────────────────────────────────────
# Page 0: Brand selection
if curr == 0:
    st.title("Our Brands")
    st.subheader("Please Choose a Brand")

    brands = get_brands()                                       # available brands
    cols   = st.columns([1] * len(brands) + [len(brands)], gap="small")  # simple grid

    for col, b in zip(cols[:-1], brands):
        with col:
            # Map brand → preview image path if available
            url = {
                "Honda": str(IMAGE_DIR / "honda.jpg"),
                "Yamaha": str(IMAGE_DIR / "Yamaha_Logo.jpg")
            }.get(b)

            # Show brand image if present; otherwise fallback to text label
            if url and Path(url).exists():
                pil = PILImage.open(url).convert("RGB")
                st.image(pil, width=250)
            else:
                st.write(b)

            # Brand selection button triggers navigation
            st.button(b, on_click=go_to_brand, args=(b,), key=f"brand_{b}")

# Page 1: CC selection for chosen brand
elif curr == 1:
    st.title("CC Selection")
    st.button("« Back", on_click=go_back, key="back0")  # back to brands
    br = st.session_state.current_brand
    st.subheader(f"{br} — Select CC")

    ccs  = get_cc_list(br)                                        # available CCs
    cols = st.columns([1] * len(ccs) + [len(ccs)], gap="small")

    for col, c in zip(cols[:-1], ccs):
        with col:
            st.button(str(c), on_click=go_to_cc, args=(c,), key=f"cc_{c}")

# Page 2: Model selection for brand + CC
elif curr == 2:
    st.title("Model Selection")
    st.button("« Back", on_click=go_back, key="back1")  # back to CCs
    br = st.session_state.current_brand
    cc = st.session_state.current_cc

    # Escape CC for safe HTML rendering
    raw_cc     = st.session_state.get("current_cc") or ""
    escaped_cc = raw_cc.replace(">", "&gt;").replace("<", "&lt;")

    # Header with brand and CC
    st.markdown(
        f"<h3 style='white-space: nowrap'>{br} CC {escaped_cc} — Models</h3>",
        unsafe_allow_html=True,
    )

    # Year filter (optional)
    colf, _ = st.columns([1, 4], gap="small")
    with colf:
        yrs = ["All"] + [str(y) for y in get_years(br, cc)]
        sel = st.selectbox("Filter by year", yrs, key="yr")

    # Filter models by year if selected
    if sel == "All":
        models = get_models(br, cc)
    else:
        with get_engine().connect() as conn:
            rows = conn.execute(
                text("""
                SELECT DISTINCT pi.model
                  FROM pdf_info pi
                 WHERE pi.brand     = :b
                   AND pi.cc        = :c
                   AND pi.year      = :y
                   AND pi.is_active = 1
                """),
                {"b": br, "c": cc, "y": int(sel)}
            ).fetchall()
        models = [r[0] for r in rows]

    # Brand-specific layout configuration
    cfg         = BRAND_CONFIG.get(br, BRAND_CONFIG["__default__"])
    size        = cfg["model_img_size"]
    DEFAULT_IMG = DEFAULT_MODEL_IMG

    # Grid for model cards
    cols = st.columns([1] * len(models) + [len(models)], gap="small")

    for col, m in zip(cols[:-1], models):
        with col:
            # Attempt to load a bike image from DB for this model
            row = get_engine().connect().execute(
                text("SELECT bike_image FROM pdf_info WHERE brand=:b AND model=:m LIMIT 1"),
                {"b": br, "m": m},
            ).fetchone()

            blob = row[0] if row and row[0] else None
            if blob:
                raw = bytes(blob) if isinstance(blob, memoryview) else blob
                try:
                    img = process_image(raw, size)  # resize and cache
                except UnidentifiedImageError:
                    # If corrupt/unknown format, fallback to default image
                    img = PILImage.open(str(DEFAULT_IMG)).convert("RGB").resize(size, PILImage.BICUBIC)
                st.image(img, width=size[0])
            else:
                # Missing image → show default placeholder
                img = PILImage.open(str(DEFAULT_IMG)).convert("RGB").resize(size, PILImage.BICUBIC)
                st.image(img, width=size[0])

            # Selecting a model advances to Sections page
            st.button(m, on_click=go_to_model, args=(m,), key=f"mdl_{m}")

# Page 3: Sections grid for the chosen model
elif curr == 3:
    st.button("« Back", on_click=go_back, key="back2")  # back to Models
    b, m, cc = st.session_state.current_brand, st.session_state.current_model, st.session_state.current_cc
    st.subheader(f"{b} {m} — Sections")
    secs = get_sections(b, m, cc)  # (section_id, section_name, section_image_bytes)

    # Apply client-side search filter by section name
    if search:
        secs = [s for s in secs if search.lower() in s[1].lower()]

    # Empty-result message when search misses
    if search and not secs:
        st.warning("There is no such section.")

    cfg = BRAND_CONFIG.get(b, BRAND_CONFIG["__default__"])
    # Render section cards in rows of N columns
    for i in range(0, len(secs), cfg["sections_per_row"]):
        chunk = secs[i : i + cfg["sections_per_row"]]
        cols  = st.columns(cfg["sections_per_row"], gap="small")
        for col, (sec_id, name, raw) in zip(cols, chunk):
            with col:
                img = process_image(raw, cfg["section_img_size"])
                st.image(img, width=cfg["section_img_size"][0])
                # Selecting a section goes to Page 4 with zoom + references
                st.button(name, on_click=go_to_section, args=(sec_id, name, raw), key=f"sec_{sec_id}")
        st.markdown("---")

# Page 4: Zoomed section image and reference numbers/parts
elif curr == 4:
    st.button("« Back", on_click=go_back, key="back3")  # back to Sections
    b    = st.session_state.current_brand
    m    = st.session_state.current_model
    cc   = st.session_state.current_cc
    cfg  = BRAND_CONFIG.get(b, BRAND_CONFIG["__default__"])
    sect = st.session_state.current_section
    st.subheader(sect)

    # If we lost the section_id on refresh but still know the section name, recover it
    if st.session_state.get("current_section_id") is None and all([b, m, cc, sect]):
        for sid, name, _img in get_sections(b, m, cc):
            if name == sect:
                st.session_state.current_section_id = sid
                break

    # Fetch all reference numbers for this section
    if st.session_state.get("current_section_id") is None:  # guard against direct landing
        st.warning("No section selected. Please choose a section again.")
        st.session_state.page_num = 3
        st.stop()

    sec_id = st.session_state.current_section_id
    with get_engine().connect() as conn:
        rs = conn.execute(
            text("""
            SELECT DISTINCT mpl.ref_no
              FROM master_parts_list mpl
             WHERE mpl.section_id = :sid
             ORDER BY mpl.ref_no
            """),
            {"sid": sec_id},
        ).fetchall()
    ref_nos = [r[0] for r in rs]

    # Ensure the zoom image is available in session
    if st.session_state.zoom_image is None and all([b, m, cc, sect]):
        for _sec_id, _name, raw in get_sections(b, m, cc):  # unpack all 3
            if _name == sect:
                st.session_state.zoom_image = raw
                break

    # Prepare a medium-sized zoom image preview
    if st.session_state.zoom_image:
        zoomed = PILImage.open(BytesIO(st.session_state.zoom_image)).convert("RGB")
        zoomed.thumbnail((500, 750), PILImage.BICUBIC)
    else:
        zoomed = None  # very unlikely if data exists; keeps code safe

    # Layout option 1: image on top, content below
    if cfg["page4_layout"] == "top_image":
        if zoomed is not None:
            st.image(zoomed, use_container_width=True)

        if st.session_state.current_ref is None:
            # No ref selected yet → render grid of reference buttons
            st.markdown("**Reference Numbers**")
            for i in range(0, len(ref_nos), cfg["refs_per_row"]):
                cols = st.columns(cfg["refs_per_row"], gap="small")
                for col, ref in zip(cols, ref_nos[i : i + cfg["refs_per_row"]]):
                    with col:
                        st.button(str(ref), on_click=set_ref, args=(ref,), key=f"ref_{ref}")

        else:
            # Ref selected → list unique parts for that ref (scoped to brand/model)
            sel = st.session_state.current_ref
            st.markdown(f"**Parts for Reference {sel}**")
            
            # Query and deduplicate part_no + description pairs
            with get_engine().connect() as conn2:
                raw_rows = conn2.execute(
                    text("""
                        SELECT mpl.part_no, mpl.description
                        FROM master_parts_list mpl
                        JOIN pdf_section ps ON mpl.section_id = ps.section_id
                        JOIN pdf_info    pi ON ps.pdf_id      = pi.pdf_id
                        WHERE mpl.section_id = :sid
                        AND mpl.ref_no     = :rn
                        AND pi.brand       = :b
                        AND pi.model       = :m
                        ORDER BY mpl.part_no
                    """),
                    {
                    "sid": st.session_state.current_section_id,
                    "rn":  sel,
                    "b":   st.session_state.current_brand,
                    "m":   st.session_state.current_model,
                    },
                ).fetchall()
                
            seen = set()
            unique_parts = []
            for part_no, desc in raw_rows:
                key = (part_no, desc)
                if key not in seen:
                    seen.add(key)
                    unique_parts.append((part_no, desc))

            # Render parts list with qty input + Add to Cart buttons
            for idx, (part_no, desc) in enumerate(unique_parts):
                widget_key = f"{sel}_{part_no}_{idx}"

                if b == "Honda":
                    # Honda layout with 4 columns
                    c1, c2, c3, c4 = st.columns([3, 5, 2, 2], gap="small")
                    with c1:
                        st.markdown(f"**{part_no}**")
                    with c2:
                        st.write(desc)
                    with c3:
                        st.number_input(
                            "Qty:",
                            min_value=1,
                            value=1,
                            key=f"add_qty_{widget_key}"
                        )
                    with c4:
                        st.button(
                            "Add to Cart",
                            on_click=add_to_cart,
                            args=(part_no, widget_key),
                            key=f"add_btn_{widget_key}"
                        )
                else:
                    # Default simpler layout
                    st.markdown(f"**{part_no}**")
                    st.write(desc)
                    st.number_input(
                        "Qty:",
                        min_value=1,
                        value=1,
                        key=f"add_qty_{widget_key}"
                    )
                    st.button(
                        "Add to Cart",
                        on_click=add_to_cart,
                        args=(part_no, widget_key),
                        key=f"add_btn_{widget_key}"
                    )

                # One-time success toast for the last added item
                if st.session_state.get("just_added", [None])[0] == part_no:
                    added_qty = st.session_state.pop("just_added")[1]
                    st.success(f"Added {added_qty}×{part_no} to cart")
                st.markdown("---")

    else:
        # Layout option 2: split columns (image left, details right)
        img_col, detail_col = st.columns([2, 3], gap="medium")

        with img_col:
            # Sticky image container to keep it in view while scrolling details
            st.markdown("<div class='zoom-container'>", unsafe_allow_html=True)
            if zoomed is not None:
                st.image(zoomed)
            st.markdown("</div>", unsafe_allow_html=True)

        with detail_col:
            if st.session_state.current_ref is None:
                # Show clickable reference numbers
                st.markdown("**Reference Numbers**")
                for i in range(0, len(ref_nos), cfg["refs_per_row"]):
                    cols = st.columns(cfg["refs_per_row"], gap="small")
                    for col, ref in zip(cols, ref_nos[i : i + cfg["refs_per_row"]]):
                        with col:
                            st.button(str(ref), on_click=set_ref, args=(ref,), key=f"ref2_{ref}")

            else:
                # Show parts for the selected reference
                sel = st.session_state.current_ref
                st.markdown(f"**Parts for Reference {sel}**")

                # Query and deduplicate scoped to brand/model
                with get_engine().connect() as conn2:
                    raw_rows = conn2.execute(
                        text("""
                            SELECT mpl.part_no, mpl.description
                            FROM master_parts_list mpl
                            JOIN pdf_section ps ON mpl.section_id = ps.section_id
                            JOIN pdf_info    pi ON ps.pdf_id      = pi.pdf_id
                            WHERE mpl.section_id = :sid
                            AND mpl.ref_no     = :rn
                            AND pi.brand       = :b
                            AND pi.model       = :m
                            ORDER BY mpl.part_no
                        """),
                        {
                        "sid": st.session_state.current_section_id,
                        "rn":  sel,
                        "b":   st.session_state.current_brand,
                        "m":   st.session_state.current_model,
                        },
                    ).fetchall()

                seen = set()
                unique_parts = []
                for part_no, desc in raw_rows:
                    key = (part_no, desc)
                    if key not in seen:
                        seen.add(key)
                        unique_parts.append((part_no, desc))

                # Render each unique part with controls
                for idx, (part_no, desc) in enumerate(unique_parts):
                    widget_key = f"{sel}_{part_no}_{idx}"

                    c1, c2 = st.columns([3, 5], gap="small")
                    with c1:
                        st.markdown(f"**{part_no}**")
                    with c2:
                        st.write(desc)
                    st.number_input(
                        "Qty:",
                        min_value=1,
                        value=1,
                        key=f"add_qty_{widget_key}"
                    )
                    st.button(
                        "Add to Cart",
                        on_click=add_to_cart,
                        args=(part_no, widget_key),
                        key=f"add_btn_{widget_key}"
                    )

                    # Success message only once per add
                    if st.session_state.get("just_added", [None])[0] == part_no:
                        added = st.session_state.pop("just_added")[1]
                        st.success(f"Added {added}×{part_no} to cart")
                    st.markdown("---")

    # Persist any view/cart updates made on this page
    cookies.save()

    # Global success alert at bottom (fallback if not shown above)
    if "just_added" in st.session_state:
        part, qty = st.session_state.pop("just_added")
        st.success(f"Added {qty}×{part} to cart")

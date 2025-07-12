from sqlalchemy import (
    Table, Column, Integer, String, MetaData,
    Date, UniqueConstraint, ForeignKey, select, text, join
)
from imports import engine, st, io, qrcode
from streamlit_app import gen_basket_id

# ─── CACHING SETUP FOR TABLE REFLECTION ────────────────────────────────────
@st.cache_resource(show_spinner=False)
def reflect_tables():
    meta = MetaData()
    eb = Table("ebasket", meta, autoload_with=engine)
    mpl = Table("master_parts_list", meta, autoload_with=engine)
    return eb, mpl

@st.cache_data(ttl=600, show_spinner=False)
def get_part_to_id_map():
    _, mpl = reflect_tables()
    with engine.connect() as conn:
        rows = conn.execute(select([mpl.c.part_no, mpl.c.mpl_id])).fetchall()
    return {r[0]: r[1] for r in rows}


# ─── Detect QR-link mode & set_page_config ────────────────────────────────
qp = st.query_params
is_qr_view = "id" in qp

st.set_page_config(
    layout="wide",
    initial_sidebar_state="collapsed" if is_qr_view else "expanded",
)

# ─── Initialize cart_data ─────────────────────────────────────────────────
if "cart_data" not in st.session_state:
    new_id = gen_basket_id()
    st.session_state.cart_data = {
        "basket_id":     [new_id],
        "part_no":       [[]],
        "quantity":      [[]],
        "purchase_type": [],
        "customer_name": [],
        "contact":       [],
        "email":         [],
        "postal_code":   [],
        "address":       []
    }
cart = st.session_state.cart_data


# ─── QR-only detail view ─────────────────────────────────────────────────
if is_qr_view:
    bid = qp["id"][0] if isinstance(qp["id"], list) else qp["id"]

    eb, mpl = reflect_tables()
    eb_mpl = join(eb, mpl, eb.c.mpl_id == mpl.c.mpl_id)

    with engine.connect() as conn:
        stmt = (
            select([
                eb.c.part_no,
                mpl.c.description,
                eb.c.quantity,
                eb.c.order_date
            ])
            .select_from(eb_mpl)
            .where(eb.c.basket_id == bid)
            .order_by(eb.c.item_id)
        )
        rows = conn.execute(stmt).fetchall()

    st.markdown(f"## Order Details for Basket {bid}")
    if rows:
        for part, desc, qty, od in rows:
            c1, c2 = st.columns([3,7])
            with c1: st.markdown(f"**{part}**")
            with c2: st.write(desc)
            st.write(f"Quantity: {qty}  •  Ordered on {od}")
            st.markdown("---")
    else:
        st.info("No items found for this basket.")
    st.stop()


# ─── QR confirmation block ────────────────────────────────────────────────
if st.session_state.get("show_qr", False):
    buf = io.BytesIO(st.session_state.qr_bytes)
    buf.seek(0)
    st.markdown("# 🎉 Order Confirmed!")
    st.markdown("### Please take a picture of this QR Code")
    st.image(buf, width=250)
    st.write(f"[Or click here to view your order details]({st.session_state.order_url})")
    st.markdown("### Once completed please refresh the page")
    st.stop()


# ─── View state defaults ─────────────────────────────────────────────────
st.session_state.setdefault("view", "cart")
st.session_state.setdefault("checkout_id", None)


# ─── Cart callbacks ──────────────────────────────────────────────────────
def update_quantity(idx: int):
    parts = cart["part_no"][0]
    qtys  = cart["quantity"][0]
    new_q = st.session_state[f"qty_input_{idx}"]
    i = idx - 1
    if new_q <= 0:
        parts.pop(i); qtys.pop(i)
    else:
        qtys[i] = new_q

def remove_entire(part: str):
    parts = cart["part_no"][0]; qtys = cart["quantity"][0]
    i = parts.index(part)
    parts.pop(i); qtys.pop(i)

def show_checkout():
    st.session_state.view = "checkout"


# ─── Cart & checkout UI ─────────────────────────────────────────────────
st.title("🛒 Your Shopping Cart")

if st.session_state.view == "cart":
    parts, qtys = cart["part_no"][0], cart["quantity"][0]
    st.markdown("### Basket Contents")
    if parts:
        for idx, (p, q) in enumerate(zip(parts, qtys), start=1):
            c0, c1, c2 = st.columns([4,2,1])
            with c0:
                eb, mpl = reflect_tables()
                desc = engine.connect().execute(
                    select([mpl.c.description]).where(mpl.c.part_no == p)
                ).scalar() or ""
                c_desc, _ = st.columns([7,3])
                with c_desc:
                    st.markdown(f"**{p}**")
                    st.write(desc)
            with c1:
                st.number_input(
                    f"Qty for {p}:", min_value=0, value=int(q),
                    key=f"qty_input_{idx}",
                    on_change=update_quantity,
                    args=(idx,)
                )
            with c2:
                st.button("x", key=f"x_{idx}",
                          on_click=remove_entire, args=(p,))
            st.markdown("---")
        st.button("Checkout", on_click=show_checkout)
    else:
        st.info("Your basket is currently empty.")


elif st.session_state.view == "checkout":
    if st.session_state.checkout_id is not None:
        bid = st.session_state.checkout_id

        eb, mpl = reflect_tables()
        eb_mpl = join(eb, mpl, eb.c.mpl_id == mpl.c.mpl_id)

        rows = engine.connect().execute(
            select([
                eb.c.part_no,
                mpl.c.description,
                eb.c.quantity,
                eb.c.order_date
            ])
            .select_from(eb_mpl)
            .where(eb.c.basket_id == bid)
            .order_by(eb.c.item_id)
        ).fetchall()

        st.markdown(f"## Order Details for Basket {bid}")
        for part, desc, qty, od in rows:
            c1, c2 = st.columns([3,7])
            with c1: st.markdown(f"**{part}**")
            with c2: st.write(desc)
            st.write(f"Quantity: {qty}  •  Ordered on {od}")
            st.markdown("---")
        st.markdown("[Back to Homepage](/)")
        st.stop()

    with st.form("checkout_form"):
        st.markdown("### Checkout Information")
        purchase_type = st.radio("Type of Purchase:", ["Personal","Business"])
        name          = st.text_input("Personal/Company Name:")
        phone         = st.text_input("Phone Number:")
        email         = st.text_input("Email Address:")
        pc_col, addr_col = st.columns(2)
        with pc_col:  postal_code = st.text_input("Postal Code:")
        with addr_col: address     = st.text_input("Address:")

        back_clicked   = st.form_submit_button("Back")
        submit_clicked = st.form_submit_button("Submit Order")

        if back_clicked:
            st.session_state.view = "cart"
            st.rerun()

        if submit_clicked:
            errors = []
            if not name.strip():        errors.append("Enter a Name.")
            if not phone.strip():       errors.append("Enter a Phone.")
            if not email.strip():       errors.append("Enter an Email.")
            if not postal_code.strip(): errors.append("Enter a Postal Code.")
            if not address.strip():     errors.append("Enter an Address.")
            if phone.strip() and not phone.isdigit():
                errors.append("Invalid Phone Number")
            if email.strip() and email.count("@")!=1:
                errors.append("Invalid Email")
            if postal_code.strip() and not postal_code.isdigit():
                errors.append("Invalid Postal Code")
            if errors:
                for e in errors: st.error(e)
                st.stop()

            _, mpl = reflect_tables()
            eb = Table(
                "ebasket", MetaData(),
                Column("item_id", Integer, primary_key=True, autoincrement=True),
                Column("basket_id", String, nullable=False),
                Column("mpl_id", Integer, ForeignKey("master_parts_list.mpl_id"), nullable=False),
                Column("part_no", String, nullable=False),
                Column("quantity", Integer),
                Column("order_date", Date, server_default=text("CURRENT_DATE"), nullable=False),
                Column("purchase_type", String),
                Column("customer_name", String),
                Column("contact", String),
                Column("email", String),
                Column("postal_code", String),
                Column("address", String),
                UniqueConstraint("basket_id","mpl_id",name="uix_basket_mpl")
            )
            eb.metadata.create_all(engine, tables=[eb])

            part_to_id = get_part_to_id_map()
            bid = cart["basket_id"][0]
            to_insert = []
            for p, q in zip(cart["part_no"][0], cart["quantity"][0]):
                pid = part_to_id.get(p)
                if pid is None:
                    st.error(f"Unknown part_no {p}—cannot insert.")
                    st.stop()
                to_insert.append({
                    "basket_id":     bid,
                    "mpl_id":        pid,
                    "part_no":       p,
                    "quantity":      q,
                    "purchase_type": purchase_type,
                    "customer_name": name,
                    "contact":       phone,
                    "email":         email,
                    "postal_code":   postal_code,
                    "address":       address
                })

            with engine.begin() as conn:
                conn.execute(eb.insert(), to_insert)

            new_bid = gen_basket_id()
            st.session_state.cart_data = {
                "basket_id":     [new_bid],
                "part_no":       [[]],
                "quantity":      [[]],
                "purchase_type": [],
                "customer_name": [],
                "contact":       [],
                "email":         [],
                "postal_code":   [],
                "address":       []
            }

            url = f"http://localhost:8501/Checkout🛒?id={bid}"
            qr_img = qrcode.make(url)
            buf = io.BytesIO(); qr_img.save(buf, format="PNG")
            st.session_state.qr_bytes  = buf.getvalue()
            st.session_state.order_url = url
            st.session_state.show_qr   = True

            st.rerun()

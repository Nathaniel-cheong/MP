import streamlit as st

# ─── 1. session_state setup ─────────────────────────────────────────────
# Assume cart_data is initialized and persisted in app.py
from streamlit_app import save_cart_to_disk  # Adjust import path if needed

# ─── 2. Callbacks ────────────────────────────────────────────────────────
def update_quantity(idx: int):
    """
    Called when the user edits the quantity for item at position idx.
    If new_qty <= 0, remove that item; otherwise, update to new_qty.
    Then save the cart.
    """
    cart = st.session_state.cart_data
    basket_parts = cart["part_no"][0]
    basket_qtys = cart["quantity"][0]

    new_qty = st.session_state.get(f"qty_input_{idx}", 0)
    list_index = idx - 1

    if new_qty <= 0:
        # Remove this item entirely
        basket_parts.pop(list_index)
        basket_qtys.pop(list_index)
        # No need to delete old qty_input key; it won't be used next rerun
    else:
        # Update to new quantity
        basket_qtys[list_index] = new_qty

    save_cart_to_disk()

def remove_entire(part: str):
    """
    Remove the entire row for 'part' regardless of quantity.
    Then save the cart.
    """
    cart = st.session_state.cart_data
    idx = cart["part_no"][0].index(part)
    cart["part_no"][0].pop(idx)
    cart["quantity"][0].pop(idx)
    save_cart_to_disk()

# ─── 3. Dummy parts catalog (for adding new items) ──────────────────────
parts_list = ["A123-XL", "B456-M", "C789-S", "D012-L", "E345-XXL"]

# ─── 4. UI: choose a part and quantity to add ───────────────────────────
st.title("🛒 Persistent Single-Row Basket Demo")

selected_part = st.selectbox("Choose a part to add:", parts_list, key="add_part")
add_quantity = st.number_input(
    "Quantity to add:",
    min_value=1,
    step=1,
    value=1,
    key="add_qty"
)

if st.button("Add to Cart", key="add_button"):
    cart = st.session_state.cart_data
    basket_parts = cart["part_no"][0]
    basket_qtys = cart["quantity"][0]

    if selected_part in basket_parts:
        idx0 = basket_parts.index(selected_part)
        basket_qtys[idx0] += add_quantity
    else:
        basket_parts.append(selected_part)
        basket_qtys.append(add_quantity)

    save_cart_to_disk()

st.markdown("---")

# ─── 5. Display items with editable quantities and an "X" button ────────
st.markdown("### Items in Your Basket")
basket_parts = st.session_state.cart_data["part_no"][0]
basket_qtys = st.session_state.cart_data["quantity"][0]

if basket_parts:
    for idx, (part, qty) in enumerate(zip(basket_parts, basket_qtys), start=1):
        cols = st.columns([4, 2, 1])
        with cols[0]:
            st.write(f"{idx}. Part: **{part}**")
        with cols[1]:
            st.number_input(
                f"Qty for {part}:",
                min_value=0,
                step=1,
                value=qty,
                key=f"qty_input_{idx}",
                on_change=update_quantity,
                args=(idx,)
            )
        with cols[2]:
            st.button(
                "x",
                key=f"remove_x_{idx}",
                on_click=remove_entire,
                args=(part,)
            )
        st.markdown("---")
else:
    st.info("Your basket is currently empty.")

# ─── 6. (Optional) Show raw cart_data dictionary for debugging ──────────
st.markdown("### Raw cart_data (for debugging)")
st.write(st.session_state.cart_data)
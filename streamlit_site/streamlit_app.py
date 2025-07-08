import os
import pickle
import streamlit as st
import random
import string
from imports import *

# ─── CART PICKLE ──────────────────────────────────────────────────────────
PICKLE_FILENAME = "cart_data.pkl"
PICKLE_PATH     = os.path.join(os.getcwd(), PICKLE_FILENAME)

def load_cart_from_disk():
    """Return cart_data dict from pickle file, or None if missing/invalid."""
    if os.path.exists(PICKLE_PATH):
        try:
            with open(PICKLE_PATH, "rb") as f:
                data = pickle.load(f)
            if (
                isinstance(data, dict)
                and "basket_id" in data
                and "part_no"   in data
                and "quantity"  in data
            ):
                return data
        except Exception:
            pass
    return None

def save_cart_to_disk():
    """Write current session_state.cart_data to pickle file."""
    try:
        with open(PICKLE_PATH, "wb") as f:
            pickle.dump(st.session_state.cart_data, f)
    except Exception as e:
        st.error(f"Couldn't save cart: {e}")

# ─── APP (PAGE & NAV) STATE PICKLE ────────────────────────────────────────
APP_STATE_FILENAME = "homepage_state.pkl"
APP_STATE_PATH     = os.path.join(os.getcwd(), APP_STATE_FILENAME)

# Keys we want to persist across refreshes
PERSIST_KEYS = [
    "page_num",
    "current_brand",
    "current_model",
    "current_cc",
    "current_section",
    "current_ref",
    "zoom_image",
]

def load_session_state():
    """Load persisted keys into st.session_state, overwriting any existing."""
    if os.path.exists(APP_STATE_PATH):
        try:
            with open(APP_STATE_PATH, "rb") as f:
                state = pickle.load(f)
            for k in PERSIST_KEYS:
                # if missing in file, default page_num to 0
                if k not in state and k == "page_num":
                    st.session_state[k] = 0
                else:
                    v = state.get(k)
                    # convert bytes back to memoryview if needed?
                    st.session_state[k] = v
        except Exception:
            # on error, at least ensure page_num starts at 0
            st.session_state["page_num"] = 0

def save_session_state():
    """Save select keys from session_state into the homepage pickle."""
    state_dict = {}
    for k in PERSIST_KEYS:
        v = st.session_state.get(k)
        # convert memoryview to bytes for pickling
        if isinstance(v, memoryview):
            v = bytes(v)
        state_dict[k] = v

    try:
        with open(APP_STATE_PATH, "wb") as f:
            pickle.dump(state_dict, f)
    except Exception as e:
        st.error(f"Couldn't save app state: {e}")

# ─── HELPER TO MAKE A RANDOM 8-CHAR CODE ──────────────────────────────────
def gen_basket_id() -> str:
    """
    Generate a unique ID in the format:
      3 digits, 2 letters, 3 digits, 1 letter
    Re-roll if it already exists in ebasket; if the table doesn't exist yet,
    we assume no collision.
    """
    def _make_candidate():
        d1 = random.choices(string.digits, k=3)
        l1 = random.choices(string.ascii_uppercase, k=2)
        d2 = random.choices(string.digits, k=3)
        l2 = random.choice(string.ascii_uppercase)
        return "".join(d1 + l1 + d2 + [l2])

    while True:
        candidate = _make_candidate()
        try:
            with engine.connect() as conn:
                found = conn.execute(
                    text("SELECT 1 FROM ebasket WHERE basket_id = :b LIMIT 1"),
                    {"b": candidate}
                ).fetchone()
        except ProgrammingError:
            # table doesn't exist yet → no collision
            return candidate

        if not found:
            return candidate
        # otherwise loop and try again


# ─── INITIAL LOAD ON IMPORT ──────────────────────────────────────────────

# 1. Load or initialize cart_data
if "cart_data" not in st.session_state:
    disk_data = load_cart_from_disk()
    if disk_data:
        st.session_state.cart_data = disk_data
    else:
        # Generate a fresh 8-char alphanumeric ID
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
        save_cart_to_disk()

# 2. Load preserved page/navigation state (always overwrites)
load_session_state()


# pages/rfq_dashboard.py
import streamlit as st
import json
from streamlit_cookies_manager import EncryptedCookieManager

st.set_page_config(page_title="RFQ Dashboard", layout="wide")

cookies = EncryptedCookieManager(prefix="my_app/", password="your-32-byte-long-secret-key-here")
if not cookies.ready():
    st.stop()

visitor_id = cookies.get("visitor_id")
if visitor_id is None:
    st.error("No visitor session found. Please start from the Homepage.")
    st.stop()

hist_json = cookies.get("purchase_history", "[]")
try:
    history = json.loads(hist_json)
except:
    history = []

st.title("📋 RFQ Dashboard")

if not history:
    st.info("You have no past requests yet.")
else:
    for entry in reversed(history):
        st.markdown(f"### Basket {entry['basket_id']} — {entry['order_date']}")

        # build our table rows
        data = {
            "Part No.":  [],
            "Quantity":  [],
            "Brand":     [],
            "Model":     []
        }
        for item in entry["items"]:
            data["Part No."].append(item["part_no"])
            data["Quantity"].append(item["quantity"])
            data["Brand"].append(item["brand"])
            data["Model"].append(item["model"])

        st.table(data)
        st.markdown("---")
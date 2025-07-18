# pages/rfq_dashboard.py
import streamlit as st
import json
import pandas as pd
import altair as alt
from streamlit_cookies_manager import EncryptedCookieManager

st.set_page_config(page_title="RFQ Dashboard", layout="wide")

# ─── COOKIE SETUP ──────────────────────────────────────────────────────────
cookies = EncryptedCookieManager(
    prefix="my_app/",
    password="your-32-byte-long-secret-key-here"
)
if not cookies.ready():
    st.stop()

visitor_id = cookies.get("visitor_id")
if visitor_id is None:
    st.error("No visitor session found. Please start from the Homepage.")
    st.stop()

# ─── LOAD & NORMALIZE HISTORY ───────────────────────────────────────────────
hist_json = cookies.get("purchase_history", "[]")
try:
    history = json.loads(hist_json)
except json.JSONDecodeError:
    history = []

records = []
for entry in history:
    bid  = entry["basket_id"]
    date = entry.get("order_date", "")
    for item in entry.get("items", []):
        records.append({
            "Basket ID":  bid,
            "Order Date": date,
            "Brand":      item.get("brand", ""),
            "Model":      item.get("model", ""),
            "Part No.":   item.get("part_no", ""),
            "Quantity":   item.get("quantity", 0),
        })

df = pd.DataFrame(records)
if df.empty:
    st.info("You have no past requests yet.")
    st.stop()

# ─── DATE PARSING ──────────────────────────────────────────────────────────
df["Order Date"]      = pd.to_datetime(df["Order Date"], errors="coerce")
df["Order Date Only"] = df["Order Date"].dt.date

# ─── SIDEBAR FILTERS ────────────────────────────────────────────────────────
st.sidebar.header("🔍 Filters")

# 1) Date range
date_min, date_max = df["Order Date Only"].min(), df["Order Date Only"].max()
date_range = st.sidebar.date_input(
    "Order date between",
    value=(date_min, date_max)
)

# 2) Brand multiselect
all_brands = sorted(df["Brand"].dropna().unique())
selected_brands = st.sidebar.multiselect(
    "Brand",
    options=all_brands,
    default=all_brands,
    key="brand_filter"
)

# 3) Model multiselect, dependent on selected_brands
#    Derive available models *after* brand selection
available_models = (
    df.loc[df["Brand"].isin(selected_brands), "Model"]
      .dropna()
      .unique()
      .tolist()
)
available_models.sort()

# Initialize or trim the session_state for models
if "model_filter" not in st.session_state:
    st.session_state.model_filter = available_models
else:
    # drop any models no longer available
    st.session_state.model_filter = [
        m for m in st.session_state.model_filter if m in available_models
    ]

selected_models = st.sidebar.multiselect(
    "Model",
    options=available_models,
    default=st.session_state.model_filter,
    key="model_filter"
)

# ─── APPLY FILTERS ─────────────────────────────────────────────────────────
mask = (
    df["Order Date Only"].between(date_range[0], date_range[1]) &
    df["Brand"].isin(selected_brands) &
    df["Model"].isin(selected_models)
)
filtered = df[mask]

# ─── TOP‐LINE METRICS ───────────────────────────────────────────────────────
st.title("📋 RFQ Dashboard")

qty_by_part  = filtered.groupby("Part No.")["Quantity"].sum()
qty_by_brand = filtered.groupby("Brand")   ["Quantity"].sum()

total_orders  = filtered["Basket ID"].nunique()
most_part     = qty_by_part.idxmax()  if not qty_by_part.empty  else ""
most_part_qty = qty_by_part.max()     if not qty_by_part.empty  else 0
top_brand     = qty_by_brand.idxmax() if not qty_by_brand.empty else ""
top_brand_qty = qty_by_brand.max()    if not qty_by_brand.empty else 0

# ─── METRICS CARDS ─────────────────────────────────────────────────────────
st.markdown(f"""
<style>
.metrics-container {{
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
}}
.metric-card {{
    flex: 1;
    background: #f8f9fa;
    border-radius: 8px;
    padding: 20px;
    text-align: center;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
}}
.metric-card h2 {{
    margin: 0;
    font-size: 2.5rem;
    color: #333;
}}
.metric-card p {{
    margin: 4px 0 0;
    color: #666;
    font-size: 1rem;
}}
</style>
<div class="metrics-container">
  <div class="metric-card">
    <h2>{total_orders}</h2>
    <p>Total Orders Made</p>
  </div>
  <div class="metric-card">
    <h2>{most_part}</h2>
    <p>Top Part</p>
  </div>
  <div class="metric-card">
    <h2>{top_brand}</h2>
    <p>Top Brand</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ─── GRAPHS ────────────────────────────────────────────────────────────────

# Part Popularity (horizontal, multi‑color)
st.subheader("🏆 Part Popularity (Top 10)")
chart_df = (
    qty_by_part
      .sort_values(ascending=False)
      .head(10)
      .rename_axis("part_no")
      .reset_index(name="total_qty")
)
bar = (
    alt.Chart(chart_df)
       .mark_bar()
       .encode(
           x=alt.X("total_qty:Q", title="Total Quantity", axis=alt.Axis(format="d", tickMinStep=1)),
           y=alt.Y("part_no:N", sort="-x", title="Part No."),
           color=alt.Color("part_no:N", legend=None, scale=alt.Scale(scheme="set3"))
       )
       .properties(height=300)
)
st.altair_chart(bar, use_container_width=True)

# Number of Orders by Brand
st.subheader("📊 Number of Orders by Brand")
orders_by_brand = (
    filtered
      .drop_duplicates(subset=["Basket ID", "Brand"])
      .groupby("Brand")["Basket ID"]
      .nunique()
      .reset_index(name="order_count")
)
bar3 = (
    alt.Chart(orders_by_brand)
       .mark_bar()
       .encode(
           x=alt.X("order_count:Q", title="Number of Orders", axis=alt.Axis(format="d", tickMinStep=1)),
           y=alt.Y("Brand:N", sort="-x", title="Brand"),
           color=alt.Color("Brand:N", legend=None, scale=alt.Scale(scheme="set3"))
       )
       .properties(height=300)
)
st.altair_chart(bar3, use_container_width=True)

# Orders Over Time (by Day)
st.subheader("🗓️ Orders Over Time")
orders_by_date = (
    filtered
      .drop_duplicates(subset=["Basket ID", "Order Date Only"])
      .groupby("Order Date Only")["Basket ID"]
      .nunique()
      .reset_index(name="orders")
)
line = (
    alt.Chart(orders_by_date)
       .mark_line(point=True)
       .encode(
           x=alt.X("Order Date Only:T", timeUnit="yearmonthdate", title="Date"),
           y=alt.Y("orders:Q", title="Number of Orders", axis=alt.Axis(format="d", tickMinStep=1))
       )
       .properties(height=300)
)
st.altair_chart(line, use_container_width=True)

st.markdown("---")

# ─── DETAILED TABLE ────────────────────────────────────────────────────────
st.subheader("Detailed Request Log")
st.dataframe(
    filtered.sort_values(["Order Date", "Basket ID"], ascending=False)
            .reset_index(drop=True),
    use_container_width=True
)

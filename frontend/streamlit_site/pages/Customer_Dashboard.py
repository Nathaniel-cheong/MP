# pages/rfq_dashboard.py
import streamlit as st
import json
import pandas as pd
import altair as alt
from streamlit_cookies_manager import EncryptedCookieManager
import random, datetime
import numpy as np

st.set_page_config(page_title="RFQ Dashboard", layout="wide")

# ─── DUMMY DATA FUNCTION ─────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_dummy_history(n_baskets=100, seed: int = 41):
    random.seed(seed)
    brands_models = {
        "Honda":  ["CRF1000A", "NC750XAP"],
        "Yamaha": ["AEROX155", "FJR1300A"],
    }
    start = datetime.date(2025, 1, 1)
    end   = datetime.date(2025, 7, 19)
    delta_days = (end - start).days

    history = []
    for i in range(1, n_baskets + 1):
        order_date = (start + datetime.timedelta(days=random.randint(0, delta_days))).isoformat()
        items = []
        for _ in range(random.randint(1, 4)):
            brand    = random.choice(list(brands_models.keys()))
            model    = random.choice(brands_models[brand])
            part_no  = f"P{random.randint(1000, 9999)}"
            quantity = random.randint(1, 100)
            items.append({
                "brand":    brand,
                "model":    model,
                "part_no":  part_no,
                "quantity": quantity
            })
        history.append({
            "basket_id": 1000 + i,
            "order_date": order_date,
            "items":      items
        })
    return history

# ─── CHOOSE DATA SOURCE ─────────────────────────────────────────────────────
USE_DUMMY = True

if USE_DUMMY:
    history = get_dummy_history()
else:
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

    # ─── LOAD REAL HISTORY ─────────────────────────────────────────────────────
    hist_json = cookies.get("purchase_history", "[]")
    try:
        history = json.loads(hist_json)
    except json.JSONDecodeError:
        history = []

# ─── BUILD RECORDS DATAFRAME ─────────────────────────────────────────────────
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

# Date range
date_min, date_max = df["Order Date Only"].min(), df["Order Date Only"].max()
date_range = st.sidebar.date_input(
    "Order date between",
    value=(date_min, date_max)
)

# Brand multiselect
all_brands = sorted(df["Brand"].dropna().unique())
selected_brands = st.sidebar.multiselect(
    "Brand",
    options=all_brands,
    default=all_brands,
    key="brand_filter"
)

# Model multiselect, dependent on selected_brands
available_models = (
    df.loc[df["Brand"].isin(selected_brands), "Model"]
      .dropna().unique().tolist()
)
available_models.sort()

if "model_filter" not in st.session_state:
    st.session_state.model_filter = available_models
else:
    st.session_state.model_filter = [
        m for m in st.session_state.model_filter if m in available_models
    ]

selected_models = st.sidebar.multiselect(
    "Model",
    options=available_models,
    default=st.session_state.model_filter,
    key="model_filter"
)

# ─── normalize date range input safely ───────────────────────────────────────
if isinstance(date_range, (list, tuple)):
    if len(date_range) == 2:
        start_date, end_date = date_range
    elif len(date_range) == 1:
        start_date = end_date = date_range[0]
    else:
        start_date = end_date = date_min
else:
    start_date = end_date = date_range

# swap if reversed
if start_date and end_date and start_date > end_date:
    start_date, end_date = end_date, start_date

# fallback to full span if invalid
if start_date is None or end_date is None:
    start_date, end_date = date_min, date_max

# ─── apply filters ─────────────────────────────────────────────────────────
mask = (
    df["Order Date Only"].between(start_date, end_date) &
    df["Brand"].isin(selected_brands) &
    df["Model"].isin(selected_models)
)
filtered = df[mask]

# ─── TOP‐LINE METRICS ───────────────────────────────────────────────────────
st.title("📋 RFQ Dashboard")

qty_by_part  = filtered.groupby("Part No.")["Quantity"].sum()
qty_by_brand = filtered.groupby("Brand")   ["Quantity"].sum()
qty_by_model = filtered.groupby("Model")["Quantity"].sum()

total_orders  = filtered["Basket ID"].nunique()
most_part     = qty_by_part.idxmax()  if not qty_by_part.empty  else ""
top_model     = qty_by_model.idxmax() if not qty_by_model.empty else ""
top_brand     = qty_by_brand.idxmax() if not qty_by_brand.empty else ""

# ─── GLOBAL STYLING (hide index, compact, flatten purchase history) ────────
st.markdown(
    """
    <style>
      /* hide any leftover index column in pandas-styled HTML tables */
      .no-index table thead th.row_heading,
      .no-index table tbody th.row_heading {
          display: none;
      }
      .no-index table thead th:first-child,
      .no-index table tbody th {
          display: none;
      }
      .no-index table {
          border-collapse: collapse;
          font-size: 13px;
      }
      .no-index table td, .no-index table th {
          padding: 6px 8px;
      }
      .purchase-history-wrapper table {
          background: none !important;
      }
      .purchase-history-wrapper th {
          background: transparent !important;
          border-bottom: 1px solid #ddd;
      }
      .purchase-history-wrapper td {
          background: transparent !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

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
    <h2>{top_model}</h2>
    <p>Top Model</p>
  </div>
  <div class="metric-card">
    <h2>{top_brand}</h2>
    <p>Top Brand</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ─── GRAPHS & TABLES ───────────────────────────────────────────────────────
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🗓️ Orders Over Time")
    agg_choice = st.selectbox("Aggregate by", ["Day", "Month"], index=0)
    if agg_choice == "Day":
        orders_by_time = (
            filtered
              .drop_duplicates(subset=["Basket ID", "Order Date Only"])
              .groupby("Order Date Only")["Basket ID"]
              .nunique()
              .reset_index(name="orders")
        )
        x_enc = alt.X("Order Date Only:T", timeUnit="yearmonthdate", title="Date")
    else:
        orders_by_time = (
            filtered
              .drop_duplicates(subset=["Basket ID", "Order Date Only"])
              .assign(order_month=filtered["Order Date"].dt.to_period("M").dt.to_timestamp())
              .groupby("order_month")["Basket ID"]
              .nunique()
              .reset_index(name="orders")
        )
        orders_by_time.rename(columns={"order_month": "Month"}, inplace=True)
        x_enc = alt.X("Month:T", timeUnit="yearmonth", title="Month")

    line = (
        alt.Chart(orders_by_time)
           .mark_line(point=True)
           .encode(
               x=x_enc,
               y=alt.Y("orders:Q", title="Number of Orders", axis=alt.Axis(format="d", tickMinStep=1))
           )
           .properties(height=300)
    )
    st.altair_chart(line, use_container_width=True)

    # ─── PURCHASE HISTORY UNDER THE CHART ────────────────────────────────────
    st.subheader("📜 Purchase History")
    filtered_display = (
        filtered
        .drop(columns=["Order Date Only"], errors="ignore")
        .assign(**{"Order Date": filtered["Order Date"].dt.strftime("%Y-%m-%d")})
        .sort_values(["Order Date", "Basket ID"], ascending=False)
        .reset_index(drop=True)
    )

    history_styler = (
        filtered_display.style
        .format({"Quantity": "{:d}"})
        .set_properties(**{
            "font-size": "14px",
            "padding": "8px",
        })
        .hide(axis="index")
        .set_table_styles([
            {"selector": "table", "props": [("background-color", "transparent"), ("border-collapse", "collapse")]},
            {"selector": "td", "props": [("padding", "8px"), ("vertical-align", "top")]},
        ])
    )

    history_html = history_styler.to_html(index=False)
    st.markdown(f'<div class="purchase-history-wrapper">{history_html}</div>', unsafe_allow_html=True)


def styled_top_series_html(series, name, top_n=10):
    df_top = (
        series
        .sort_values(ascending=False)
        .head(top_n)
        .rename_axis(name)
        .reset_index(name="Total Quantity")
        .reset_index(drop=True)
    )
    df_top.insert(0, "Rank", np.arange(1, len(df_top) + 1))
    styler = (
        df_top.style
        .format({"Total Quantity": "{:d}"})
        .set_properties(**{"text-align": "left"})
    )
    return styler.to_html(index=False)


with col2:
    st.subheader("🏆 Part Popularity (Top 10)")
    part_html = styled_top_series_html(qty_by_part, "Part No.")
    st.markdown(f'<div class="no-index">{part_html}</div>', unsafe_allow_html=True)

    st.subheader("📊 Number of Orders by Brand")
    orders_by_brand = (
        filtered
          .drop_duplicates(subset=["Basket ID", "Brand"])
          .groupby("Brand")["Basket ID"]
          .nunique()
          .reset_index(name="Number of Orders")
    )
    orders_by_brand.insert(0, "Rank", orders_by_brand["Number of Orders"].rank(
        method="dense", ascending=False
    ).astype(int))
    brand_df = orders_by_brand.sort_values("Number of Orders", ascending=False).reset_index(drop=True)
    brand_styler = (
        brand_df.style
        .format({"Number of Orders": "{:d}"})
        .set_properties(**{"text-align": "left"})
    )
    brand_html = brand_styler.to_html(index=False)
    st.markdown(f'<div class="no-index">{brand_html}</div>', unsafe_allow_html=True)

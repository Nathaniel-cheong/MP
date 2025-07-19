# pages/rfq_dashboard.py
import streamlit as st
import json
import pandas as pd
import altair as alt
from streamlit_cookies_manager import EncryptedCookieManager
import random, datetime

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

# apply filters
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
qty_by_model = filtered.groupby("Model")["Quantity"].sum()

total_orders  = filtered["Basket ID"].nunique()
most_part     = qty_by_part.idxmax()  if not qty_by_part.empty  else ""
top_model     = qty_by_model.idxmax() if not qty_by_model.empty else ""
top_brand     = qty_by_brand.idxmax() if not qty_by_brand.empty else ""



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

# ─── GRAPHS ────────────────────────────────────────────────────────────────

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


# ─── ORDERS OVER TIME WITH CHOICE ───────────────────────────────────────────
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
    # derive a period timestamp column for month
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

st.markdown("---")

st.subheader("Detailed Request Log")
st.dataframe(
    filtered.sort_values(["Order Date", "Basket ID"], ascending=False)
            .reset_index(drop=True),
    use_container_width=True
)

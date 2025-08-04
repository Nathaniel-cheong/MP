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

date_min, date_max = df["Order Date Only"].min(), df["Order Date Only"].max()
date_range = st.sidebar.date_input(
    "Choose a date range",
    value=(date_min, date_max),
    key="order_date_range"
)

all_brands = sorted(df["Brand"].dropna().unique())
selected_brands = st.sidebar.multiselect(
    "Brand",
    options=all_brands,
    default=all_brands,
    key="brand_filter"
)

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

if start_date and end_date and start_date > end_date:
    start_date, end_date = end_date, start_date

if start_date is None or end_date is None:
    start_date, end_date = date_min, date_max

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

# ─── GLOBAL STYLING (compact, purchase history flatten) ───────────────────
st.markdown(
    """
    <style>
      .metric-card { font-family: system-ui; }
      .metrics-container {
          display: flex;
          gap: 16px;
          margin-bottom: 24px;
      }
      .metric-card {
          flex: 1;
          background: #f8f9fa;
          border-radius: 8px;
          padding: 20px;
          text-align: center;
          box-shadow: 0 2px 6px rgba(0,0,0,0.1);
      }
      .metric-card h2 {
          margin: 0;
          font-size: 2.5rem;
          color: #333;
      }
      .metric-card p {
          margin: 4px 0 0;
          color: #666;
          font-size: 1rem;
      }
      .purchase-history-wrapper table {
          background: none !important;
          border-collapse: collapse;
          width: 100%;
          font-size: 14px;
      }
      .purchase-history-wrapper th {
          background: transparent !important;
          border-bottom: 1px solid #ddd;
          padding: 6px 8px;
          text-align: left;
      }
      .purchase-history-wrapper td {
          background: transparent !important;
          padding: 6px 8px;
          vertical-align: top;
          text-align: left;
      }
      .compact-html-table {
          border-collapse: collapse;
          width: 100%;
          font-size: 13px;
          margin-bottom: 8px;
      }
      .compact-html-table th, .compact-html-table td {
          padding: 6px 8px;
          text-align: left;
          border-bottom: 1px solid #eee;
      }
      .compact-html-wrapper { overflow:auto; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── METRICS CARDS ─────────────────────────────────────────────────────────
st.markdown(f"""
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

# ─── HELPER: render arbitrary df as HTML table without index ───────────────
def df_to_html_table_no_index(df: pd.DataFrame, caption: str | None = None) -> str:
    header_cells = "".join(f"<th>{col}</th>" for col in df.columns)
    body_rows = ""
    for _, row in df.iterrows():
        cells = "".join(f"<td>{row[col]}</td>" for col in df.columns)
        body_rows += f"<tr>{cells}</tr>"
    caption_html = (
        f"<div style='font-weight:600; margin-bottom:4px'>{caption}</div>" if caption else ""
    )
    return f"""
    <div class="compact-html-wrapper">
      {caption_html}
      <table class="compact-html-table">
        <thead>
          <tr>{header_cells}</tr>
        </thead>
        <tbody>
          {body_rows}
        </tbody>
      </table>
    </div>
    """

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

    st.subheader("📜 Purchase History")
    filtered_display = (
        filtered
        .drop(columns=["Order Date Only"], errors="ignore")
        .assign(**{"Order Date": filtered["Order Date"].dt.strftime("%Y-%m-%d")})
        .sort_values(["Order Date", "Basket ID"], ascending=False)
        .reset_index(drop=True)
    )
    filtered_display["Quantity"] = filtered_display["Quantity"].astype(int)

    def render_purchase_history_clean(df: pd.DataFrame) -> str:
        # Header row
        header_cells = "".join(
            f"<th style='position:sticky; top:0; background:#111; color:#fff; padding:10px; text-align:left; border-bottom:1px solid #444;'>"
            f"{col}</th>" for col in df.columns
        )
        # Body rows with zebra striping
        rows_html = ""
        for i, (_, row) in enumerate(df.iterrows()):
            bg = "#1e2330" if i % 2 == 0 else "#1b1f2a"  # subtle dark stripes
            cells = "".join(
                f"<td style='padding:10px; vertical-align:top; border-bottom:1px solid #2f3245; color:#e5e9f0;'>"
                f"{row[col]}</td>" for col in df.columns
            )
            rows_html += f"<tr style='background:{bg};'>{cells}</tr>"

        return f"""
        <div style="max-height:500px; overflow:auto; border:1px solid #2f3245; border-radius:8px;">
        <table style="border-collapse:collapse; width:100%; font-size:14px; background: none;">
            <thead>
            <tr>{header_cells}</tr>
            </thead>
            <tbody>
            {rows_html}
            </tbody>
        </table>
        </div>
        """

    st.markdown(render_purchase_history_clean(filtered_display), unsafe_allow_html=True)

with col2:
    st.subheader("🏆 Part Popularity (Top 10)")
    part_df = (
        qty_by_part
        .sort_values(ascending=False)
        .head(10)
        .rename_axis("Part No.")
        .reset_index(name="Total Quantity")
    )
    part_df.insert(0, "Rank", np.arange(1, len(part_df) + 1))
    part_df["Total Quantity"] = part_df["Total Quantity"].astype(int)
    part_html = df_to_html_table_no_index(part_df, caption="Top parts by total quantity requested.")
    st.markdown(part_html, unsafe_allow_html=True)

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
    orders_by_brand = orders_by_brand.sort_values("Number of Orders", ascending=False).reset_index(drop=True)
    orders_by_brand["Number of Orders"] = orders_by_brand["Number of Orders"].astype(int)
    brand_html = df_to_html_table_no_index(orders_by_brand, caption="Unique baskets per brand.")
    st.markdown(brand_html, unsafe_allow_html=True)

from imports import *
st.title("📦 Inventory Overview")

# Refresh button (Clears cached data)
if st.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.toast("Cache cleared. Refreshing data...")
    time.sleep(1)
    st.rerun()

# Load and merge pdf_info with pdf_log (to get pdf status)
@st.cache_data(ttl=600)
def load_inventory():
    with engine.connect() as conn:
        pdf_info = pd.read_sql_table("pdf_info", con=conn)
        logs = pd.read_sql_table("pdf_log", con=conn)

        # Merge logs info into pdf_info
        merged_df = pdf_info.merge(
            logs[["pdf_id", "is_current","is_active", "archived"]],
            on="pdf_id",
            how="left"
        )
        return merged_df

df = load_inventory()

# Error handling for empty df
if df.empty:
    st.warning("No inventory data available.")
    st.stop()

# Data preprocessing for charts
df["year"] = df["year"].astype(str)

# --- Metrics Row ---
with st.container():
    st.subheader("📊 PDF Status Summary")

    # Filtering to only main PDFs (Able to be editted)
    current_logs = df[df["is_current"] == 1]

    # Total unique PDFs in the data
    total_pdfs = df[df["is_active"].isin([1, 0])]["pdf_id"].nunique() + df[df["archived"] == 1]["pdf_id"].nunique()

    metric_cols = st.columns(4)
    # Total Bikes: Active + Inactive + Archived
    metric_cols[0].metric("📦 Total Bikes", total_pdfs)
    # Active: is_current = 1 and is_active = 1 and archived = 0
    metric_cols[1].metric("✅ Active Bikes", current_logs[current_logs["is_active"] == 1]["pdf_id"].nunique())
    # Inactive: is_current = 1 and is_active = 0 and archived = 0
    metric_cols[2].metric("❌ Inactive Bikes", current_logs[current_logs["is_active"] == 0]["pdf_id"].nunique())
    # Archived: is_current = 0 and Is_active = 0 but archived = 1
    metric_cols[3].metric("🗑️ Archived Bikes (In PDF Dustbin)", df[df["archived"] == 1]["pdf_id"].nunique())

# --- Pie Charts for Brand and CC Distribution ---
st.subheader("🥧 Distribution of Bike Models")

col1, col2 = st.columns(2)

# --- Brand Pie Chart ---
with col1:
    if "brand" in df.columns and not df["brand"].dropna().empty:
        # Get number of bikes for each brand using value count
        brand_counts = df["brand"].value_counts().reset_index()
        brand_counts.columns = ["brand", "count"]
        fig_brand = px.pie(
            brand_counts,
            names="brand",
            values="count",
            title="Bike Models by Brand",
            color_discrete_sequence=custom_colors # Color scheme from imports.py
        )
        st.plotly_chart(fig_brand, use_container_width=True)
    else:
        st.info("No brand data available.")

# --- CC Pie Chart ---
with col2:
    if "cc" in df.columns and not df["cc"].dropna().empty:
        cc_counts = df["cc"].value_counts().reset_index()
        cc_counts.columns = ["cc", "count"]
        fig_cc = px.pie(
            cc_counts,
            names="cc",
            values="count",
            title="Bike Models by CC",
            color_discrete_sequence=custom_colors # Color scheme from imports.py
        )
        st.plotly_chart(fig_cc, use_container_width=True)
    else:
        st.info("No engine CC data available.")
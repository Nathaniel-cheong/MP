from imports import *

st.title("📦 Inventory Overview")
# --- Refresh Button ---
if st.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.success("Cache cleared. Refreshing data...")
    time.sleep(1)
    st.rerun()

# --- Load Inventory Table ---
@st.cache_data(ttl=600)
def load_inventory():
    with engine.connect() as conn:
        return pd.read_sql_table("pdf_info", con=conn)

df = load_inventory()

if df.empty:
    st.warning("No inventory data available.")
    st.stop()

# --- Preprocessing ---
df["year"] = df["year"].astype(str)

# --- Layout ---
col1, col2 = st.columns(2)

# --- Chart 1: Count by Brand ---
with col1:
    st.subheader("🏷️ Count of Models by Brand")
    brand_counts = df["brand"].value_counts()
    st.bar_chart(brand_counts)

# --- Chart 2: Count by Year ---
with col2:
    st.subheader("📆 Count of Models by Year")
    year_counts = df["year"].value_counts().sort_index()
    st.line_chart(year_counts)

# --- Chart 3: Brand-Year Table ---
st.subheader("📊 Brand-Year Distribution")
brand_year_counts = df.groupby(["brand", "year"]).size().unstack(fill_value=0)
st.dataframe(brand_year_counts, use_container_width=True)
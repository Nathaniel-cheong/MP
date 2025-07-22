from imports import *

st.title("Manage Accounts")

# Reflect the metadata and get accounts table
metadata = MetaData()
metadata.reflect(bind=engine)
accounts = metadata.tables.get("accounts")

#@st.cache_data(ttl=300)
def load_accounts_table():
    with engine.connect() as conn:
        return pd.read_sql_table("accounts", con=conn)

# 🔁 Button to clear cache
# if st.button("🔄 Clear Table Cache"):
#     st.cache_data.clear()
#     st.success("✅ Cache cleared. Reloading fresh data...")
#     time.sleep(1)
#     st.rerun()

# Load data
accounts_df = load_accounts_table()

# Stop if no data
if accounts_df.empty:
    st.info("No accounts found.")
    st.stop()

# Search bar
search_query = st.text_input("🔍 Search by staff name only:")

# Apply search filter
if search_query:
    query = search_query.strip().lower()
    if "staff_name" in accounts_df.columns:
        mask = accounts_df["staff_name"].astype(str).str.lower().str.contains(query)
        accounts_df = accounts_df[mask]

# ✅ Sort by account_id
accounts_df = accounts_df.sort_values("account_id")

# Show table (excluding password)
st.dataframe(accounts_df.drop(columns=["password"]), use_container_width=True, hide_index=True)

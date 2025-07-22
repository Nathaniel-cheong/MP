from imports import *

st.title("Logs Dashboard")
st.markdown("To monitor bike edit/upload activity.")

# Reflect the metadata and get accounts table
metadata = MetaData()
metadata.reflect(bind=engine)
logs = metadata.tables.get("pdf_log")

#@st.cache_data(ttl=300)
def load_pdf_logs():
    with engine.connect() as conn:
        return pd.read_sql_table("pdf_log", con=conn)

# 🔁 Button to clear cache
# if st.button("🔄 Clear Table Cache"):
#     st.cache_data.clear()
#     st.success("✅ Cache cleared. Reloading fresh data...")
#     time.sleep(1)
#     st.rerun()

# Load data
logs_df = load_pdf_logs()

# Stop if no data
if logs_df.empty:
    st.info("No accounts found.")
    st.stop()

logs_df = logs_df.sort_values("log_id", ascending=True)

# Show table (excluding password)
st.dataframe(logs_df, use_container_width=True, hide_index=True)

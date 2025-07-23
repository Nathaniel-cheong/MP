from imports import *

st.title("📊 Logs Dashboard")

# --- Load Log + Account Data ---
@st.cache_data(ttl=600)
def load_log_data():
    with engine.connect() as conn:
        log_df = pd.read_sql_table("pdf_log", con=conn)
        acc_df = pd.read_sql_table("accounts", con=conn)[["account_id", "staff_name"]]
        return log_df.merge(acc_df, how="left", on="account_id")

# --- Load Data ---
df = load_log_data()
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp"])

# --- Preprocessing ---
df["date"] = df["timestamp"].dt.date
df["hour"] = df["timestamp"].dt.hour
df["day"] = df["timestamp"].dt.strftime("%A")

# --- Sidebar Filters ---
with st.sidebar:
    st.header("🔧 Filters")
    staff_options = ["All"] + sorted(df["staff_name"].dropna().unique().tolist())
    selected_staff = st.selectbox("Filter by Staff Name", staff_options)
    if selected_staff != "All":
        df = df[df["staff_name"] == selected_staff]

        # --- Refresh Cache ---
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.success("Cache cleared. Reloading...")
        time.sleep(1)
        st.rerun()

# --- Dashboard Columns ---
col1, col2, col3 = st.columns([1.5, 3, 2])

# --- Column 1: Metrics ---
with col1:
    st.subheader("📌 Quick Stats")
    st.metric("Total Logs", len(df))
    st.metric("Unique Staff", df["staff_name"].nunique())
    st.metric("Active Entries", df["is_current"].sum())

    st.subheader("🕒 Most Active Hour")
    if not df.empty:
        peak_hour = df["hour"].value_counts().idxmax()
        st.metric("Hour", f"{peak_hour}:00")
    else:
        st.write("No data available.")

# --- Column 2: Daily Activity ---
with col2:
    st.subheader("📅 Log Activity per Day")
    if not df.empty:
        daily_logs = df["date"].value_counts().sort_index()
        st.line_chart(daily_logs)
    else:
        st.write("No activity to show.")

# --- Column 3: Top PDFs and Recent ---
with col3:
    st.subheader("📄 Top 5 Most Edited PDF IDs")
    if not df.empty:
        top_pdfs = df["pdf_id"].value_counts().head(5).reset_index()
        top_pdfs.columns = ["PDF ID", "Log Count"]
        st.dataframe(top_pdfs, hide_index=True, use_container_width=True)
    else:
        st.write("No recent edits.")

    st.subheader("🧾 Recent Activity")
    recent = df.sort_values("timestamp", ascending=False).head(5)[["pdf_id", "staff_name", "timestamp"]]
    st.dataframe(recent, hide_index=True, use_container_width=True)

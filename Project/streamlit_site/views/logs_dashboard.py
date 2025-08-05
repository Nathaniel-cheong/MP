from imports import *
st.title("📊 Logs Dashboard")

# Load and merge pdf_log with accounts(For staff) and pdf_info (For brand)
@st.cache_data(ttl=600)
def load_log_data():
    with engine.connect() as conn:
        log_df = pd.read_sql_table("pdf_log", con=conn)
        acc_df = pd.read_sql_table("accounts", con=conn)[["account_id", "staff_name"]]
        info_df = pd.read_sql_table("pdf_info", con=conn)[["pdf_id", "brand"]]  # Add brand from pdf_info
        merged = log_df.merge(acc_df, on="account_id", how="left")
        merged = merged.merge(info_df, on="pdf_id", how="left")  # Merge brand into the logs
        return merged

df = load_log_data()

# Error handling for empty df
if df.empty:
    st.warning("⚠️ No log data found in the database.")
    st.stop()

# Loading accounts for account filter
with engine.connect() as conn:
    account_df = pd.read_sql_table("accounts", con=conn)[["staff_name"]]

# Data preprocessing for charts
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp"])
df["date"] = df["timestamp"].dt.date
df["year"] = df["timestamp"].dt.year
df["month"] = df["timestamp"].dt.month
df["time"] = df["timestamp"].dt.strftime("%H:%M:%S")

# --- Buttons Row ---
refresh_btn_col, reset_filter_btn_col, _ = st.columns([1, 1, 4.5]) 

# --- Reset Filters on Button Press ---
if "reset_triggered" not in st.session_state:
    st.session_state["reset_triggered"] = False

# Refresh button (Clears cached data + dropdown filters)
if refresh_btn_col.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.toast("Cache cleared. Refreshing data...")
    st.session_state["Logs_Year"] = "All"
    st.session_state["Logs_Month"] = "All"
    st.session_state["Logs_Brand"] = "All"
    st.session_state["Logs_Staff"] = "All"
    time.sleep(0.1)
    st.rerun()

# Reset Filters button (Clears dropdown filters only)
if reset_filter_btn_col.button("♻️ Reset Filters"):
    st.toast("Resetting filters...")
    st.session_state["Logs_Year"] = "All"
    st.session_state["Logs_Month"] = "All"
    st.session_state["Logs_Brand"] = "All"
    st.session_state["Logs_Staff"] = "All"
    time.sleep(0.1)
    st.rerun()

# --- Filters ---
filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1,1,1,2])

# Year Filter (Only show years available in data)
year_options = ["All"] + sorted(df["year"].dropna().astype(str).unique())
selected_year = filter_col1.selectbox("Year", year_options, key="Logs_Year")
if selected_year != "All":
    df = df[df["year"].astype(str) == selected_year]

# Month Filter (Only show months available in data)
available_months = sorted(df["month"].dropna().unique())
month_name_map = {i: calendar.month_name[i] for i in available_months}
month_options = ["All"] + [month_name_map[i] for i in available_months]
selected_month = filter_col2.selectbox("Month", month_options, key="Logs_Month")
if selected_month != "All":
    month_number = {v: k for k, v in month_name_map.items()}[selected_month]
    df = df[df["month"] == month_number]

# Brand Filter (Only show brands available)
brand_options = ["All"] + sorted(df["brand"].dropna().unique().tolist())
selected_brand = filter_col3.selectbox("Brand", brand_options, key="Logs_Brand")
if selected_brand != "All":
    df = df[df["brand"] == selected_brand]

# Accounts Filter (Shows all account from account table)
staff_options = ["All"] + sorted(account_df["staff_name"].dropna().unique().tolist())
selected_staff = filter_col4.selectbox("Staff", staff_options, key="Logs_Staff")
if selected_staff != "All":
    df = df[df["staff_name"] == selected_staff]

# --- Main Layout: Charts + Side Panel ---
chart_col, info_col = st.columns([3, 3])

# --- Column 1 (Left):
with chart_col:
    st.subheader("📅 Log Activity per Day")
    if not df.empty:
        # Get daily log counts using value count
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date
        daily_logs = df["date"].value_counts().sort_index()
        daily_logs_df = daily_logs.rename_axis("Date").reset_index(name="Log Count")
        daily_logs_df["Date"] = pd.to_datetime(daily_logs_df["Date"])

        # Fill missing dates with 0
        full_range = pd.date_range(start=daily_logs_df["Date"].min(), end=daily_logs_df["Date"].max())
        full_logs_df = (
            daily_logs_df.set_index("Date")
            .reindex(full_range, fill_value=0)
            .rename_axis("Date")
            .reset_index()
        )
        full_logs_df["Log Count"] = full_logs_df["Log Count"].astype(int)

        # Plot Table Chart
        fig = px.line(full_logs_df, x="Date", y="Log Count", title="📅 Log Activity per Day")
        fig.update_layout(
            height=350,
            yaxis=dict(tickmode='linear', dtick=1, title='Log Count'),
            xaxis_title="Date",
            margin=dict(t=50, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)

        # Plot Pie Chart
        if "description" in df.columns and not df["description"].isna().all():
            # Get description counts using value count
            action_counts = df["description"].value_counts().reset_index()
            action_counts.columns = ["Action", "Count"]
            fig = px.pie(
                action_counts, 
                names="Action", 
                values="Count", 
                title="Distribution of Log Actions", 
                color_discrete_sequence=custom_colors # Color scheme from imports.py
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No action descriptions available to display.")
    else:
        # Error handling for missing data (E.g. newly created staff)
        st.info("No activity to show.")

# --- Column 2 (Right):
with info_col:
    st.subheader("🕒 Most Active Hour")
    if not df.empty and "time" in df.columns:
        # Getting the hour with the most activity
        peak_hour = pd.to_datetime(df["time"], format="%H:%M:%S").dt.hour.value_counts().idxmax()
        st.metric(label="Most Active Hour", value=f"{peak_hour}:00")
    else:
        # Error handling for missing data (E.g. newly created staff)
        st.info("No data available.")

    st.subheader("📄 Top 5 Most Edited PDF IDs")
    # Getting the PDFs with the top 5 highest value counts
    if not df.empty:
        top_pdfs = (
            df["pdf_id"]
            .value_counts()
            .head(5)
            .reset_index()
            .rename(columns={"pdf_id": "PDF ID", "count": "Log Count"})
        )
        st.dataframe(top_pdfs, hide_index=True, use_container_width=True)
    else:
        # Error handling for missing data (E.g. newly created staff)
        st.info("No recent edits.")

    st.subheader("🧾 Recent Activity")
    if not df.empty:
        # Sorting logs data by timestamp descending and selecting the recent 10
        recent_display = (
            df.sort_values("timestamp", ascending=False)
            .loc[:, ["pdf_id", "staff_name", "date", "time", "description"]]
            .head(10)
            .rename(columns={
                "pdf_id": "PDF ID",
                "staff_name": "Staff",
                "date": "Date",
                "time": "Time",
                "description": "Change"
            })
        )

        st.dataframe(recent_display, hide_index=True, use_container_width=True)
    else:
        # Error handling for missing data (E.g. newly created staff)
        st.info("No recent activity.")
from imports import *
import streamlit as st
import pandas as pd
import time

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

    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.success("Cache cleared. Reloading...")
        time.sleep(1)
        st.rerun()

# --- Metrics Row ---
with st.container():
    metric_cols = st.columns(4)
    metric_cols[0].metric("📦 Total PDFs", df["pdf_id"].nunique())
    metric_cols[1].metric("✅ Active PDFs", df[df["is_active"] == 1]["pdf_id"].nunique())
    metric_cols[2].metric("👥 Unique Staff", df["staff_name"].nunique())
    if not df.empty:
        peak_hour = df["hour"].value_counts().idxmax()
        metric_cols[3].metric("🕒 Most Active Hour", f"{peak_hour}:00")
    else:
        metric_cols[3].write("No data")

# --- Main Charts and Tables ---
chart_col, side_col = st.columns([3, 2])

# --- Column 1: Chart ---
with chart_col:
    st.subheader("📅 Log Activity per Day")
    if not df.empty:
        daily_logs = df["date"].value_counts().sort_index()
        st.line_chart(daily_logs)
    else:
        st.write("No activity to show.")

# --- Column 2: Top PDFs and Recent Logs ---
with side_col:
    st.subheader("📄 Top 5 Most Edited PDF IDs")
    if not df.empty:
        top_pdfs = df["pdf_id"].value_counts().head(5).reset_index()
        top_pdfs.columns = ["PDF ID", "Log Count"]
        st.dataframe(top_pdfs, hide_index=True, use_container_width=True)
    else:
        st.write("No recent edits.")

    st.subheader("🧾 Recent Activity")
    recent = df.sort_values("timestamp", ascending=False).head(5)[["pdf_id", "staff_name"]]
    st.dataframe(recent, hide_index=True, use_container_width=True)

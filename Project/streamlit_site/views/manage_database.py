# Edit pdf
# Edit mpl list (those without pdf_info, logs, and sections due to cascade delete)

from imports import *
import io
cookies = CookieController()

# Rehydrate session state from cookies
if "user_type" not in st.session_state:
    st.session_state.user_type = cookies.get("user_type")
if "user_name" not in st.session_state:
    st.session_state.user_name = cookies.get("user_name")

st.title("Manage PDFs")

for key in ["edit_page", "edit_page_mpl_list", "edit_page_pdf_info", "edit_page_pdf_section"]:
    st.session_state.setdefault(key, False)

# Reflect the metadata
metadata = MetaData()
metadata.reflect(bind=engine)
mpl_table = metadata.tables.get("master_parts_list")
pdf_info_table = metadata.tables.get("pdf_info")
pdf_log_table = metadata.tables.get("pdf_log")
pdf_section_table = metadata.tables.get("pdf_section")

# --- Check if table was found ---
if None in (mpl_table, pdf_info_table, pdf_log_table, pdf_section_table):
    st.error("❌ Could not find one or more required tables.")
    st.stop()

if st.session_state.edit_page == False:
    pdf_details_table = join(pdf_log_table, pdf_info_table, pdf_log_table.c.pdf_id == pdf_info_table.c.pdf_id)
    query = select(pdf_log_table, pdf_info_table).select_from(pdf_details_table).where(pdf_log_table.c.is_current == 1)

    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()

    if rows:
        pdf_details_df = pd.DataFrame(rows, columns=result.keys())

        unique_brands = sorted(pdf_details_df["brand"].dropna().unique())
        unique_years = sorted(pdf_details_df["year"].dropna().unique())
        with st.container():
            col1, col2 = st.columns(2)
            with col1:
                selected_brand = st.selectbox("Filter by Brand", ["All"] + unique_brands)
            with col2:
                selected_year = st.selectbox("Filter by Year", ["All"] + [str(year) for year in unique_years])

        # Apply filters
        if selected_brand != "All":
            pdf_details_df = pdf_details_df[pdf_details_df["brand"] == selected_brand]
        if selected_year != "All":
            pdf_details_df = pdf_details_df[pdf_details_df["year"] == int(selected_year)]
        st.divider()

        for index, row in pdf_details_df.iterrows():
            with st.container():
                image_col, pdf_details_col, edit_button_col, delete_button_col = st.columns([1, 2, 1, 1])

                with image_col:
                    if row["bike_image"]:
                        try:
                            st.image(row["bike_image"], width=200)
                        except Exception:
                            st.write("⚠️ Image could not be displayed.")
                    else:
                        st.write("🚫 No image available")

                with pdf_details_col:
                    ts = datetime.fromisoformat(str(row['timestamp']))
                    date_str = ts.strftime("%Y-%m-%d")
                    time_str = ts.strftime("%H:%M")
                    status_str = (
                        '<span style="color:green; font-weight:bold;">Active</span>'
                        if row["is_active"] == 1
                        else '<span style="color:red; font-weight:bold;">Not Active</span>'
                    )

                    st.markdown(f"""
                        <u><b>PDF DETAILS:</b></u><br>
                        <b>Model:</b> {row['model']}<br>
                        <b>Batch ID:</b> {row['batch_id']}<br>
                        <b>Year:</b> {row['year']}<br>
                        <b>Brand:</b> {row['brand']}<br>
                        <u><b>UPLOAD DETAILS:</b></u><br>
                        <b>Date:</b> {date_str}<br>
                        <b>Time:</b> {time_str}<br>
                        Status: {status_str}
                    """, unsafe_allow_html=True)

                with edit_button_col:
                    if st.button("Edit Details", key=f"edit_{row['pdf_id']}"):
                        st.session_state.edit_page = True
                        st.session_state.selected_pdf_id = row['pdf_id']
                        st.rerun()

                    toggle_label = "🔄 Set Inactive" if row["is_active"] == 1 else "✅ Set Active"
                    toggle_key = f"toggle_status_{row['pdf_id']}"

                    if st.button(toggle_label, key=toggle_key):
                        new_status = 0 if row["is_active"] == 1 else 1
                        with engine.begin() as conn:
                            stmt = update(pdf_log_table).where(
                                pdf_log_table.c.pdf_id == row['pdf_id']
                            ).values(is_active=new_status)
                            conn.execute(stmt)
                        st.success(f"Status for PDF ID {row['pdf_id']} updated.")
                        st.rerun()

                with delete_button_col:
                    delete_key = f"delete_{row['pdf_id']}"
                    confirm_key = f"confirm_delete_{row['pdf_id']}"
                    confirm_button_key = f"confirm_button_{row['pdf_id']}"
                    cancel_button_key = f"cancel_button_{row['pdf_id']}"

                    if st.button("Delete", key=delete_key):
                        st.session_state[confirm_key] = True

                    if st.session_state.get(confirm_key, False):
                        st.warning(f"Are you sure you want to delete PDF ID {row['pdf_id']}?")

                        if st.button("✅ Confirm Delete", key=confirm_button_key):
                            with engine.begin() as conn:
                                stmt = delete(pdf_log_table).where(pdf_log_table.c.pdf_id == row['pdf_id'])
                                conn.execute(stmt)
                            st.success(f"Deleted PDF ID {row['pdf_id']}")
                            st.session_state[confirm_key] = False
                            st.rerun()

                        if st.button("❌ Cancel", key=cancel_button_key):
                            st.session_state[confirm_key] = False
                            st.rerun()

                st.divider()
    else:
        st.info("Unable to join tables. Please check your table.")

# --- Edit Mode ---
if st.session_state.edit_page:
    pdf_id = st.session_state.get("selected_pdf_id")
    if not pdf_id:
        st.warning("No PDF selected.")
        st.stop()

    if any([
        st.session_state.edit_page_mpl_list,
        st.session_state.edit_page_pdf_info,
        st.session_state.edit_page_pdf_section
    ]):
        if st.button("🔙 Back to Table Selection"):
            for key in ["edit_page_mpl_list", "edit_page_pdf_info", "edit_page_pdf_section"]:
                st.session_state[key] = False
            st.rerun()

    elif st.button("🔙 Back to All PDFs"):
        # Clear all editing page flags
        for key in [
            "edit_page", "edit_page_mpl_list", "edit_page_pdf_info", "edit_page_pdf_section",
            "mpl_df", "mpl_pdf_id", "mpl_edit_mode", "mpl_show_excel_reimport", "mpl_reimport_temp_df"
        ]:
            st.session_state.pop(key, None)
        st.session_state.pop("selected_pdf_id", None)
        st.rerun()

    if not any([
        st.session_state.edit_page_mpl_list,
        st.session_state.edit_page_pdf_info,
        st.session_state.edit_page_pdf_section
    ]):
        st.subheader(f"Choose table to edit for PDF ID: {pdf_id}")
        if st.button("Edit pdf_info"):
            st.session_state.edit_page_pdf_info = True
            st.rerun()
        if st.button("Edit master_parts_list"):
            st.session_state.edit_page_mpl_list = True
            st.rerun()
        if st.button("Edit pdf_section"):
            st.session_state.edit_page_pdf_section = True
            st.rerun()

    with engine.connect() as conn:
        if st.session_state.edit_page_pdf_info:
            st.subheader("Edit: pdf_info")
            df = pd.read_sql_table("pdf_info", con=conn)
            df = df[df["pdf_id"] == pdf_id]
            st.dataframe(df, use_container_width=True)
        
        elif st.session_state.edit_page_mpl_list:
            st.subheader("Edit: master_parts_list")
            st.warning("Please do not touch the **mpl_id** column when editing")
            mpl_df = pd.read_sql_table("master_parts_list", con=conn)
            edit_mpl_df = mpl_df[mpl_df["pdf_id"] == pdf_id]

            if edit_mpl_df.empty:
                st.warning("No entries found for this PDF ID.")
            else:
                # --- SESSION INITIALIZATION ---
                st.session_state.setdefault("mpl_pdf_id", pdf_id)
                st.session_state.setdefault("mpl_df", edit_mpl_df.copy())
                st.session_state.setdefault("mpl_show_excel_reimport", False)
                st.session_state.setdefault("mpl_edit_mode", False)
                st.session_state.setdefault("mpl_reimport_temp_df", None)

                st.dataframe(st.session_state["mpl_df"], use_container_width=True)

                # --- Download Excel ---
                buffer = io.BytesIO()
                st.session_state["mpl_df"].to_excel(buffer, index=False)
                st.download_button(
                    label="📥 Download master_parts_list Excel",
                    data=buffer.getvalue(),
                    file_name=f"master_parts_list_{pdf_id}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                # --- Reimport Excel Logic ---
                if st.button("📤 Reimport File", key="mpl_reimport_button"):
                    st.session_state["mpl_show_excel_reimport"] = True

                if st.session_state["mpl_show_excel_reimport"]:
                    with st.form("mpl_reimport_excel_form"):
                        st.markdown("Upload an Excel file to replace the current Master Parts List.")
                        mpl_excel_upload = st.file_uploader("Upload Edited MPL Excel File (.xlsx)", type="xlsx")

                        if mpl_excel_upload:
                            try:
                                new_df = pd.read_excel(mpl_excel_upload, engine="openpyxl")
                                original_cols = set(st.session_state["mpl_df"].columns)
                                new_cols = set(new_df.columns)

                                if original_cols != new_cols:
                                    st.error(f"❌ Column mismatch in uploaded file.\n\nExpected: {sorted(original_cols)}\nGot: {sorted(new_cols)}")
                                else:
                                    uploaded_pdf_ids = new_df["pdf_id"].dropna().unique()
                                    if len(uploaded_pdf_ids) != 1 or uploaded_pdf_ids[0] != pdf_id:
                                        st.error(f"❌ PDF ID mismatch.\nExpected: '{pdf_id}'\nFound in file: {uploaded_pdf_ids}")
                                    else:
                                        st.session_state["mpl_reimport_temp_df"] = new_df
                                        st.success("✅ File uploaded. Please confirm import below.")
                            except Exception as e:
                                st.error(f"❌ Failed to read Excel file: {e}")

                        confirm_import = st.form_submit_button("✅ Confirm Import")
                        cancel_import = st.form_submit_button("❌ Cancel")

                        if confirm_import and st.session_state.get("mpl_reimport_temp_df") is not None:
                            st.session_state["mpl_df"] = st.session_state["mpl_reimport_temp_df"]
                            st.session_state["mpl_reimport_temp_df"] = None
                            st.session_state["mpl_show_excel_reimport"] = False
                            st.success("✅ Data loaded. Press 'Save Changes' to apply.")
                            st.rerun()

                        elif cancel_import:
                            st.session_state["mpl_reimport_temp_df"] = None
                            st.session_state["mpl_show_excel_reimport"] = False
                            st.info("❌ Reimport cancelled.")
                            st.rerun()

                # --- Edit Table UI ---
                if not st.session_state["mpl_edit_mode"]:
                    if st.button("✏️ Edit Table"):
                        st.session_state["mpl_edit_mode"] = True
                        st.rerun()

                if st.session_state["mpl_edit_mode"]:
                    with st.form("mpl_edit_form"):
                        st.write("Edit the table and save changes.")
                        edited_df = st.data_editor(st.session_state["mpl_df"], use_container_width=True)

                        confirm_btn = st.form_submit_button("✅ Save Draft")
                        cancel_btn = st.form_submit_button("❌ Cancel")

                        if confirm_btn:
                            st.session_state["mpl_df"] = edited_df
                            st.session_state["mpl_edit_mode"] = False
                            st.success("✅ Changes saved locally. Press 'Save Changes' to apply to database.")
                            st.rerun()
                        elif cancel_btn:
                            st.session_state["mpl_edit_mode"] = False
                            st.info("❌ Edit cancelled.")
                            st.rerun()

                st.divider()
                # --- FINAL DB SAVE ---
                if st.button("🔄 Reset Changes"):
                    try:
                        with engine.connect() as conn_refresh:
                            refreshed_df = pd.read_sql_table("master_parts_list", con=conn_refresh)
                            refreshed_df = refreshed_df[refreshed_df["pdf_id"] == pdf_id]
                            st.session_state["mpl_df"] = refreshed_df
                            st.session_state["mpl_edit_mode"] = False
                            st.session_state["mpl_reimport_temp_df"] = None
                            st.session_state["mpl_show_excel_reimport"] = False
                        st.success("🔄 Changes reset to latest from database.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to reset changes: {e}")

                if st.button("✅ Save Changes"):
                    st.success("saved")
                    try:
                        with engine.begin() as conn2:
                            conn2.execute(delete(mpl_table).where(mpl_table.c.pdf_id == pdf_id))
                            st.session_state["mpl_df"].to_sql("master_parts_list", con=conn2, if_exists="append", index=False)
                        st.success("✅ master_parts_list updated in the database.")
                        # Clear out session state after save
                        for key in ["mpl_df", "mpl_pdf_id", "mpl_edit_mode", "mpl_show_excel_reimport", "mpl_reimport_temp_df"]:
                            st.session_state.pop(key, None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to save to database: {e}")

        elif st.session_state.edit_page_pdf_section:
            st.subheader("Edit: pdf_section")
            df = pd.read_sql_table("pdf_section", con=conn)
            df = df[df["pdf_id"] == pdf_id]
            st.dataframe(df, use_container_width=True)

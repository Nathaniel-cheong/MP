# Edit pdf
# Edit mpl list (those without pdf_info, logs, and sections due to cascade delete)

from imports import *
st.title("Manage Database")

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

    # Execute query
    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()

    # --- Convert to DataFrame for display ---
    if rows:
        pdf_details_df = pd.DataFrame(rows, columns=result.keys()) 
        #st.dataframe(pdf_details_df, use_container_width=True)  
        for index, row in pdf_details_df.iterrows():
            pdf_details_con, edit_button_con, delete_button_con = st.columns(3)

            with pdf_details_con: 
                # Parse and format timestamp
                ts = datetime.fromisoformat(str(row['timestamp']))
                date_str = ts.strftime("%Y-%m-%d")
                time_str = ts.strftime("%H:%M")
                st.markdown(f"""
                    **Model:** {row['model']}<br>
                    **Batch ID:** {row['batch_id']}<br>
                    **Year:** {row['year']}<br>
                    **Brand:** {row['brand']}<br>
                    **Date:** {date_str}<br>
                    **Time:** {time_str}
                """, unsafe_allow_html=True)
                
            with edit_button_con:       
                if st.button(f"Edit Details #{row['pdf_id']}", key=f"edit_{row['pdf_id']}"):
                    st.query_params.update({"pdf_id": row['pdf_id']})
                    st.session_state.edit_page = True
                    st.rerun()

            with delete_button_con:
                delete_key = f"delete_{row['pdf_id']}"
                confirm_key = f"confirm_delete_{row['pdf_id']}"
                confirm_button_key = f"confirm_button_{row['pdf_id']}"
                cancel_button_key = f"cancel_button_{row['pdf_id']}"

                if st.button(f"Delete #{row['pdf_id']}", key=delete_key):
                    st.session_state[confirm_key] = True

                if st.session_state.get(confirm_key, False):
                    st.warning(f"Are you sure you want to delete PDF ID {row['pdf_id']}?")
                    
                    if st.button(f"✅ Confirm Delete", key=confirm_button_key):
                        with engine.begin() as conn:
                            stmt = delete(pdf_log_table).where(pdf_log_table.c.pdf_id == row['pdf_id'])
                            conn.execute(stmt)
                        st.success(f"Deleted PDF ID {row['pdf_id']}")
                        st.session_state[confirm_key] = False
                        st.rerun()

                    if st.button(f"❌ Cancel", key=cancel_button_key):
                        st.session_state[confirm_key] = False
                        st.rerun()

            # Add a horizontal line to separate each pdf        
            st.divider()
    else:
        st.info("Unable to join tables. Please check your table.")      
         
if st.session_state.edit_page:
    pdf_id = st.query_params.get("pdf_id", "[Unknown]")

    # Back button when inside a specific table view
    if any([
        st.session_state.edit_page_mpl_list,
        st.session_state.edit_page_pdf_info,
        st.session_state.edit_page_pdf_section
    ]):
        if st.button("🔙 Back to Table Selection"):
            for key in ["edit_page_mpl_list", "edit_page_pdf_info", "edit_page_pdf_section"]:
                st.session_state[key] = False
            st.rerun()

    # Back button when selecting table (not inside one)
    elif st.button("🔙 Back to All PDFs"):
        for key in ["edit_page", "edit_page_mpl_list", "edit_page_pdf_info", "edit_page_pdf_section"]:
            st.session_state[key] = False
        st.query_params.clear()
        st.rerun()

    # If not in a specific table, show table options
    if not any([
        st.session_state.edit_page_mpl_list,
        st.session_state.edit_page_pdf_info,
        st.session_state.edit_page_pdf_section
    ]):
        st.subheader(f"Choose table to edit for PDF ID: {pdf_id}")
        if st.button("Edit master_parts_list"):
            st.session_state.edit_page_mpl_list = True
            st.rerun()
        if st.button("Edit pdf_info"):
            st.session_state.edit_page_pdf_info = True
            st.rerun()
        if st.button("Edit pdf_section"):
            st.session_state.edit_page_pdf_section = True
            st.rerun()

    # Show selected table
    with engine.connect() as conn:
        if st.session_state.edit_page_mpl_list:
            st.subheader("Edit: master_parts_list")
            df = pd.read_sql_table("master_parts_list", con=conn)
            df = df[df["pdf_id"] == pdf_id]
            df.set_index("mpl_id", inplace=True) 
            df.index.name = None
            st.dataframe(df, use_container_width=True)

        elif st.session_state.edit_page_pdf_info:
            st.subheader("Edit: pdf_info")
            df = pd.read_sql_table("pdf_info", con=conn)
            df = df[df["pdf_id"] == pdf_id]
            st.dataframe(df, use_container_width=True)

        elif st.session_state.edit_page_pdf_section:
            st.subheader("Edit: pdf_section")
            df = pd.read_sql_table("pdf_section", con=conn)
            df = df[df["pdf_id"] == pdf_id]
            st.dataframe(df, use_container_width=True)

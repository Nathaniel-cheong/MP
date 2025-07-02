# Have not tested, not sure if delete works
# Edit details code logic not done
from imports import *
st.title("Manage Database")

# Reflect the metadata
metadata = MetaData()
metadata.reflect(bind=engine)

# Access the pdf_log table
pdf_log_table = metadata.tables.get("pdf_log")

# Reflect metadata and get the pdf_log table
metadata = MetaData()
metadata.reflect(bind=engine)
pdf_log_table = metadata.tables.get("pdf_log")

if pdf_log_table is not None:
    with engine.connect() as connection:
        # Query the data
        query = select(pdf_log_table)
        result = connection.execute(query)
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    
    if not df.empty:
        # Only show selected columns
        for index, row in df.iterrows():
            pdf_details_con, edit_button_con, delete_button_con = st.columns(3)

            with pdf_details_con: 
                # Parse and format timestamp
                ts = datetime.fromisoformat(str(row['timestamp']))
                date_str = ts.strftime("%Y-%m-%d")
                time_str = ts.strftime("%H:%M")
                st.write(f"**PDF ID:** {row['pdf_id']}  \n**Date:** {date_str}  \n**Time:** {time_str}")
                
            with edit_button_con:       
                if st.button(f"Edit Details #{row['pdf_id']}", key=f"edit_{row['pdf_id']}"):
                    st.query_params.update({"pdf_id": row['pdf_id']})
                    st.switch_page("views/manual_import.py")

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
            st.markdown("---")
    else:
        st.info("No records found in 'pdf_log' table.")
else:
    st.error("Table 'pdf_log' not found in the database.")

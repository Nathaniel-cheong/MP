from imports import *

st.title("Homepage")

# Reflect existing tables
metadata = MetaData()
metadata.reflect(bind=engine)

# Access tables
master_parts_list = metadata.tables.get("master_parts_list")
parts_images = metadata.tables.get("parts_images")

# Use session or connection
with engine.connect() as conn:
    if master_parts_list is not None:
        st.subheader("master_parts_list Table")
        result = conn.execute(select(master_parts_list))
        st.dataframe(result.fetchall())
    else:
        st.warning("master_parts_list table not found.")

    if parts_images is not None:
        st.subheader("parts_images Table")
        result = conn.execute(select(parts_images))
        st.dataframe(result.fetchall())
    else:
        st.warning("parts_images table not found.")
# views/homepage.py

from imports import *            # this should already pull in: engine, MetaData, etc.
import streamlit as st
from sqlalchemy import MetaData

st.title("Homepage")

# Reflect existing tables
metadata = MetaData()
metadata.reflect(bind=engine)

# Grab the reflected Table objects
master_parts_list = metadata.tables.get("master_parts_list")
parts_images      = metadata.tables.get("parts_images")

with engine.connect() as conn:
    if master_parts_list is not None:
        st.subheader("master_parts_list Table")
        # ← Use Table.select() rather than select(master_parts_list)
        stmt   = master_parts_list.select()
        result = conn.execute(stmt)
        st.dataframe(result.fetchall())

    else:
        st.warning("master_parts_list table not found.")

    if parts_images is not None:
        st.subheader("parts_images Table")
        # ← Same here: use the Table.select() API
        stmt   = parts_images.select()
        result = conn.execute(stmt)
        st.dataframe(result.fetchall())

    else:
        st.warning("parts_images table not found.")

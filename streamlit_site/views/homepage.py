from imports import *
from sqlalchemy import select, distinct

st.title("Select a Model")

# Reflect table
metadata = MetaData()
metadata.reflect(bind=engine)
master_parts_list = metadata.tables.get("master_parts_list")

if master_parts_list is not None:
    with engine.connect() as conn:
        # Get all distinct model names
        query = select(distinct(master_parts_list.c.model))
        result = conn.execute(query)
        unique_models = [row[0] for row in result.fetchall() if row[0] is not None]

    if unique_models:
        st.subheader("Available Models:")

        for model in unique_models:
            # Create one button per model
            if st.button(f"{model}"):
                st.session_state["selected_model"] = model
                st.rerun()

        # Show selected model if one was clicked
        if "selected_model" in st.session_state:
            st.success(f"Selected model: {st.session_state['selected_model']}")

    else:
        st.info("No models found.")
else:
    st.error("Table 'master_parts_list' not found.")

st.write(st.session_state)
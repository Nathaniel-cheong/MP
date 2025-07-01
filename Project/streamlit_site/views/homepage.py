# Use session stage to track page type
from imports import *
from collections import defaultdict
from PIL import Image
from io import BytesIO
def old():
    st.title("Homepage")
    st.text("Welcome to the Homepage!")

    # Reflect tables
    metadata = MetaData()
    metadata.reflect(bind=engine)
    master_parts_list = metadata.tables.get("master_parts_list")
    parts_images = metadata.tables.get("parts_images")

    if master_parts_list is not None and parts_images is not None:
        with engine.connect() as conn:
            # Get distinct (model, brand, year)
            query = select(
                master_parts_list.c.model,
                master_parts_list.c.brand,
                master_parts_list.c.year
            ).distinct().order_by(master_parts_list.c.brand, master_parts_list.c.model)
            result = conn.execute(query)
            rows = result.fetchall()

        # Group by brand
        brand_groups = defaultdict(list)
        for model, brand, year in rows:
            if model:
                brand_groups[brand].append({"model": model, "year": year})

        if brand_groups:
            st.subheader("Available Models:")

            for brand, models in brand_groups.items():
                st.subheader(f"🏷 {brand}")

                model_chunks = [models[i:i + 4] for i in range(0, len(models), 4)]

                for chunk in model_chunks:
                    cols = st.columns(4)
                    for col, entry in zip(cols, chunk):
                        model = entry['model']
                        year = entry['year']
                        label = f"{model} ({year})"

                        with col:
                            if st.button(label, key=f"{brand}_{model}_{year}"):
                                if st.session_state.get("selected_model") == model:
                                    st.session_state.pop("selected_model", None)
                                    st.session_state.pop("selected_component", None)
                                else:
                                    st.session_state["selected_model"] = model
                                    st.session_state.pop("selected_component", None)
                                st.rerun()

            # Show components for selected model
            selected_model = st.session_state.get("selected_model")
            if selected_model:
                st.success(f"Selected model: {selected_model}")

                with engine.connect() as conn:
                    # Get components and their image_ids for the selected model
                    component_query = select(
                        distinct(master_parts_list.c.component_name),
                        master_parts_list.c.image_id
                    ).where(master_parts_list.c.model == selected_model)
                    component_result = conn.execute(component_query)
                    components = [(row[0], row[1]) for row in component_result.fetchall() if row[0] is not None]

                    # Get image_id list
                    image_ids = [img_id for _, img_id in components if img_id is not None]

                    # Fetch matching images from parts_images table
                    image_query = select(parts_images.c.image_id, parts_images.c.image).where(
                        parts_images.c.image_id.in_(image_ids)
                    )
                    image_map = {
                        row[0]: row[1] for row in conn.execute(image_query).fetchall()
                    }

                if components:
                    st.subheader("Components for this Model:")

                    comp_chunks = [components[i:i + 5] for i in range(0, len(components), 5)]
                    for chunk in comp_chunks:
                        cols = st.columns(5)
                        for col, (comp, image_id) in zip(cols, chunk):
                            with col:
                                matched_image = image_map.get(image_id)
                                if matched_image:
                                    image = Image.open(BytesIO(matched_image))
                                    st.image(image, use_container_width=True)

                                if st.button(f"{comp}", key=f"component_{comp}"):
                                    st.session_state["selected_component"] = comp
                                    st.rerun()

                    if "selected_component" in st.session_state:
                        st.info(f"Selected component: {st.session_state['selected_component']}")
                else:
                    st.info("No components found for this model.")
        else:
            st.info("No models found.")
    else:
        st.error("One or more required tables ('master_parts_list' or 'parts_images') were not found.")

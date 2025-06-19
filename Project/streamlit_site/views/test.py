from imports import *

st.title("Homepage")

# Reflect existing tables
metadata = MetaData()
metadata.reflect(bind=engine)

# Access tables
master_parts_list = metadata.tables.get("master_parts_list")

if master_parts_list is not None:
    # --- Fetch distinct filter options ---
    with engine.connect() as conn:
        # Fetch Brands
        brand_column = master_parts_list.c.brand
        brand_result = conn.execute(select(brand_column.distinct()).order_by(brand_column)).fetchall()
        brands = [row[0] for row in brand_result if row[0] is not None]

        # Fetch years
        year_column = master_parts_list.c.year
        year_result = conn.execute(select(year_column.distinct()).order_by(year_column)).fetchall()
        years = [row[0] for row in year_result if row[0] is not None]

    # --- Filter Widgets ---
    brands.insert(0, "All")
    selected_brand = st.selectbox("Filter by Brand", brands)

    years.insert(0, "All")
    selected_year = st.selectbox("Filter by Year", years)

    # --- Build query with filters ---
    stmt = select(master_parts_list)
    if selected_year != "All":
        stmt = stmt.where(master_parts_list.c.year == selected_year)

    if selected_brand != "All":
        stmt = stmt.where(master_parts_list.c.brand == selected_brand)

    # --- Execute and display results ---
    with engine.connect() as conn:
        result = conn.execute(stmt)
        rows = result.fetchall()

    if rows:
        df = pd.DataFrame(rows, columns=result.keys())
        st.subheader("master_parts_list Table")
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No results found for the selected filters.")
else:
    st.warning("master_parts_list table not found.")
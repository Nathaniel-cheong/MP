from imports import *
def render():
    st.title("Main Page")

    # Create a session
    Session = sessionmaker(bind=engine)
    session = Session()

    # Define the table and metadata
    metadata = MetaData()
    parts_images = Table('parts_images', metadata, autoload_with=engine)

    # Query the relevant columns (pdf_id, fig_no, image)
    results = session.execute(parts_images.select().with_only_columns([parts_images.c.pdf_id, parts_images.c.fig_no, parts_images.c.image])).fetchall()

    # Create a list to store data
    image_data = []

    # Loop through results to prepare data for display
    for row in results:
        pdf_id, fig_no, image_binary = row
        # Convert image binary to a PIL image
        image = Image.open(io.BytesIO(image_binary))
        
        # Store the data (pdf_id, fig_no, and image object)
        image_data.append({
            'pdf_id': pdf_id,
            'fig_no': fig_no,
            'image': image
        })

    # Display the images in rows with 5 images per row
    columns = st.columns(5)  # Create 5 columns for each row

    # Loop through the images and display them 5 per row
    for i, item in enumerate(image_data):
        # Get the corresponding column for each image
        col = columns[i % 5]  # Use modulus to cycle through columns
        with col:
            st.image(item['image'], caption=f"PDF ID: {item['pdf_id']} Fig No: {item['fig_no']}", use_container_width=True)

from imports import *

st.title("Manual Imports")

# Initialize default values
pdf_id = ""
year = ""
model = ""
brand = "Select a Brand"
accept_details = False
accept_form = False

brand_options = ["Select a Brand", "Yamaha", "Honda"]
brand = st.selectbox("Brand:", brand_options)

if brand == "Select a Brand":
    st.warning("Please select a brand.")
else:
    uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

    if uploaded_file is None:
        st.warning("Please upload a PDF file.")
    else:
        filename = uploaded_file.name
        file_bytes = uploaded_file.read()
        file_stream = BytesIO(file_bytes)  # Convert to file-like object

        # Extract values from filename
        pdf_id = extract_pdf_id(filename)
        year = extract_year(filename)
        model = extract_model(filename)

        st.subheader("Data Preview")
        st.info("Please check the extracted values before confirming the data.")

        # Display extracted values
        pdf_id = st.text_input("PDF ID:", value=pdf_id, disabled=True)
        st.text_input("Year:", key="year_input", value=year)
        year = st.session_state["year_input"]

        # Year validation
        if year and (not year.isdigit() or len(year) != 4):
            st.error("Please enter a valid 4-digit year.")
        else:
            accept_details = True

        model = st.text_input("Model:", value=model, disabled=True)

        st.subheader("Table Preview")

        #if accept_details:
            # Try to get the uploaded_file and print something before integrating extraction code
            
        st.button("Confirm Data", disabled=not accept_form)

# Sidebar
st.sidebar.text(""" 
Single (Fixed/Edit)
    pdf_id
    year
    brand
    model
Multiple (View a Table)
    section
    component_name
    ref_no
    part_no
    description
    remarks
    image_id
""")
import streamlit as st
import os
import time
import json
import tempfile
import shutil
import pandas as pd
from epubtranslator import EpubTranslator

# Set page config
st.set_page_config(
    page_title="EPUB Translator",
    page_icon="📚",
    layout="wide"
)

# Create necessary directories
os.makedirs("tmp", exist_ok=True)
os.makedirs("translated_files", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

def save_uploaded_file(uploaded_file, save_dir="uploads"):
    """Save an uploaded file to the specified directory"""
    file_path = os.path.join(save_dir, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def load_glossary_from_excel(file):
    """Load glossary data from Excel file"""
    try:
        df = pd.read_excel(file)
        # Check if dataframe has at least 2 columns
        if len(df.columns) < 2:
            st.error("Excel file must have at least 2 columns: Term and Translation")
            return None
            
        # Use the first two columns as term and translation
        term_col = df.columns[0]
        trans_col = df.columns[1]
        
        # Convert to dictionary
        glossary = {}
        for _, row in df.iterrows():
            if pd.notna(row[term_col]) and pd.notna(row[trans_col]):
                glossary[str(row[term_col])] = str(row[trans_col])
        
        return glossary
    except Exception as e:
        st.error(f"Error loading Excel glossary: {e}")
        return None

# Sidebar for configuration
st.sidebar.title("Configuration")

# API settings
with st.sidebar.expander("API Settings", expanded=True):
    api_key = st.text_input("OpenAI API Key", value="", type="password")
    api_base = st.text_input("API Base URL (Optional)", value="")
    model_name = st.text_input("Model Name", value="gpt-3.5-turbo")

# Translation settings
with st.sidebar.expander("Translation Settings", expanded=True):
    num_threads = st.slider("Number of Threads", min_value=1, max_value=10, value=5)
    resume_translation = st.checkbox("Resume from checkpoint if available", value=True)

# Main app area
st.title("EPUB Translator")
st.write("Translate EPUB files from English to Chinese using OpenAI API")

tab1, tab2, tab3 = st.tabs(["Translate", "Extract Terms", "Manage Glossary"])

# Translate tab
with tab1:
    st.header("Upload EPUB file")
    uploaded_file = st.file_uploader("Choose an EPUB file", type="epub", key="translate_file")
    
    # Glossary upload (optional)
    st.subheader("Glossary (Optional)")
    glossary_format = st.radio("Glossary format:", ["JSON", "Excel"], horizontal=True)
    
    user_glossary = None
    if glossary_format == "JSON":
        glossary_file = st.file_uploader("Upload glossary file (JSON format)", type="json", key="glossary_file_json")
        if glossary_file:
            try:
                user_glossary = json.loads(glossary_file.getvalue().decode("utf-8"))
                st.success(f"Glossary loaded with {len(user_glossary)} entries")
            except Exception as e:
                st.error(f"Error loading glossary: {e}")
    else:  # Excel format
        glossary_file = st.file_uploader("Upload glossary file (Excel format)", type=["xlsx", "xls"], key="glossary_file_excel")
        if glossary_file:
            user_glossary = load_glossary_from_excel(glossary_file)
            if user_glossary:
                st.success(f"Glossary loaded with {len(user_glossary)} entries")
    
    if uploaded_file and st.button("Start Translation"):
        if not api_key:
            st.error("Please provide an OpenAI API key")
        else:
            # Save uploaded file
            input_path = save_uploaded_file(uploaded_file)
            output_path = input_path.replace('.epub', '_cn.epub')
            
            # Create progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Initialize translator
            translator = EpubTranslator(api_key=api_key, api_base=api_base, model_name=model_name)
            
            # Start translation in a way that allows progress updates
            status_text.text("Translation in progress...")
            
            try:
                output_path, tmp_output_path, translated_file_path = translator.translate_epub(
                    input_path,
                    output_path,
                    num_threads=num_threads,
                    user_glossary=user_glossary,
                    resume=resume_translation
                )
                
                # When complete
                progress_bar.progress(100)
                status_text.text("Translation completed!")
                
                # Download options
                if os.path.exists(output_path):
                    with open(output_path, "rb") as f:
                        st.download_button(
                            label="Download Translated EPUB",
                            data=f,
                            file_name=os.path.basename(output_path),
                            mime="application/epub+zip"
                        )
            except Exception as e:
                st.error(f"Translation error: {e}")

# Extract Terms tab
with tab2:
    st.header("Extract Terms from EPUB")
    term_file = st.file_uploader("Choose an EPUB file", type="epub", key="term_file")
    
    export_excel = st.checkbox("Export terms to Excel", value=True)
    
    if term_file and st.button("Extract Terms"):
        # Save uploaded file
        input_path = save_uploaded_file(term_file)
        
        # Initialize translator
        translator = EpubTranslator(api_key=api_key, api_base=api_base, model_name=model_name)
        
        try:
            with st.spinner("Extracting terms..."):
                terms, excel_path = translator.extract_terms(input_path, export_excel=export_excel)
                
                # Display extracted terms
                st.success(f"Extracted {len(terms)} terms")
                st.json(terms)
                
                # Save terms to JSON
                base_name = os.path.splitext(os.path.basename(input_path))[0]
                terms_file = f"{base_name}_terms.json"
                terms_path = os.path.join("tmp", terms_file)
                
                with open(terms_path, 'w', encoding='utf-8') as f:
                    json.dump(terms, f, ensure_ascii=False, indent=2)
                
                # Download options
                with open(terms_path, "rb") as f:
                    st.download_button(
                        label="Download Terms (JSON)",
                        data=f,
                        file_name=terms_file,
                        mime="application/json"
                    )
                
                # Excel download if available
                if excel_path and os.path.exists(excel_path):
                    with open(excel_path, "rb") as f:
                        st.download_button(
                            label="Download Terms (Excel)",
                            data=f,
                            file_name=os.path.basename(excel_path),
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
        except Exception as e:
            st.error(f"Error extracting terms: {e}")

# Manage Glossary tab
with tab3:
    st.header("Manage Glossary")
    
    # Two columns for creating and viewing glossary
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Create/Edit Glossary")
        
        # Either upload existing glossary or create new
        glossary_import_format = st.radio("Import format:", ["JSON", "Excel"], horizontal=True)
        
        glossary_data = {}
        if glossary_import_format == "JSON":
            existing_glossary = st.file_uploader("Upload existing glossary", type="json", key="existing_glossary_json")
            if existing_glossary:
                try:
                    glossary_data = json.loads(existing_glossary.getvalue().decode("utf-8"))
                    st.success(f"Loaded glossary with {len(glossary_data)} entries")
                except Exception as e:
                    st.error(f"Error loading glossary: {e}")
        else:  # Excel format
            existing_glossary = st.file_uploader("Upload existing glossary", type=["xlsx", "xls"], key="existing_glossary_excel")
            if existing_glossary:
                glossary_data = load_glossary_from_excel(existing_glossary)
                if glossary_data:
                    st.success(f"Loaded glossary with {len(glossary_data)} entries")
        
        # Add new entries
        st.subheader("Add New Entry")
        term = st.text_input("English Term")
        translation = st.text_input("Chinese Translation")
        
        if st.button("Add Entry") and term and translation:
            glossary_data[term] = translation
            st.success(f"Added '{term}' to glossary")
        
        # Save glossary
        if glossary_data:
            export_format = st.radio("Export format:", ["JSON", "Excel"], horizontal=True)
            
            if st.button("Save Glossary"):
                timestamp = int(time.time())
                
                if export_format == "JSON":
                    glossary_file = f"glossary_{timestamp}.json"
                    glossary_path = os.path.join("tmp", glossary_file)
                    
                    with open(glossary_path, 'w', encoding='utf-8') as f:
                        json.dump(glossary_data, f, ensure_ascii=False, indent=2)
                    
                    # Download option
                    with open(glossary_path, "rb") as f:
                        st.download_button(
                            label="Download Glossary (JSON)",
                            data=f,
                            file_name=glossary_file,
                            mime="application/json"
                        )
                else:  # Excel format
                    translator = EpubTranslator()
                    excel_path = translator.export_glossary_to_excel(glossary_data)
                    
                    if excel_path and os.path.exists(excel_path):
                        with open(excel_path, "rb") as f:
                            st.download_button(
                                label="Download Glossary (Excel)",
                                data=f,
                                file_name=os.path.basename(excel_path),
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
    
    with col2:
        st.subheader("Current Glossary")
        if glossary_data:
            st.table({"Term": list(glossary_data.keys()), "Translation": list(glossary_data.values())})
        else:
            st.info("No glossary data loaded or created yet")

# Footer
st.markdown("---")
st.markdown("EPUB Translator - Powered by OpenAI API")

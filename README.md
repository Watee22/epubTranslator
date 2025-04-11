# EPUB Translator Web App

A Streamlit web application for translating EPUB files from English to Chinese using the OpenAI API.

## Features

- Upload and translate EPUB files
- Extract terms from EPUB files
- Manage custom glossaries
- Resume translations from checkpoints
- Export terms and glossaries to Excel

## Installation

1. Clone this repository
2. Install the required packages:

```bash
pip install -r requirements.txt
```

## Usage

1. Run the Streamlit app:

```bash
streamlit run app.py
```

2. The application will open in your default web browser at http://localhost:8501

3. Configure the API settings:
   - Enter your OpenAI API key
   - Optionally specify a custom API base URL
   - Select the model to use for translation

4. Upload your EPUB file and start translation

## Configuration Options

- **Number of Threads**: Control the number of concurrent translation threads
- **Resume Translation**: Enable/disable resuming from checkpoints
- **Export to Excel**: Export extracted terms or glossaries to Excel format

## Directory Structure

- `uploads/`: Stores uploaded EPUB files
- `tmp/`: Temporary storage for processed files
- `translated_files/`: Permanent storage for translated EPUB files

## Requirements

- Python 3.7+
- OpenAI API key
- Internet connection

## License

This project is for educational purposes.

## Credits

Uses the EpubTranslator module for EPUB file processing and translation.


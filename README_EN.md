# EPUB Translation Web App  

A Streamlit-based web application that uses the OpenAI API to translate EPUB files from English to Chinese.  

## Features  

- Upload and translate EPUB files  
- Extract terms from EPUB files  
- Manage custom glossaries  
- Resume translations from checkpoints  
- Export terms and glossaries to Excel  
- Provide background knowledge to the model to help it understand what it's translating  

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

2. The app will open in your default web browser at http://localhost:8501  

3. Configure API settings:  
   - Enter your OpenAI API key  
   - Optionally specify a custom API base URL  
   - Select the model to use for translation  

4. Upload your EPUB file and start translating  

## Configuration Options  

- **Number of Threads**: Control the number of concurrent translation threads  
- **Resume Translation**: Enable/disable resuming from checkpoints  
- **Export to Excel**: Export extracted terms or glossaries in Excel format  

## Directory Structure  

- `uploads/`: Stores uploaded EPUB files  
- `tmp/`: Temporary storage for processing files  
- `translated_files/`: Permanent storage for translated EPUB files  

## Requirements  

- Python 3.7+  
- DeepSeekAI API key or other API key  
- Internet connection  

## License  

MIT  

## Acknowledgements  

- Modified the EpubTranslator module for EPUB file processing and translation.  
- Used a list of common English words from `https://github.com/oprogramador/most-common-words-by-language`  

## Todo  
- 1. Support more languages  
- 2. Docker deployment
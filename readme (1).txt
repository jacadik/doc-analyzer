# Document Analyzer

An on-premise application for analyzing document templates in a migration project. The application helps business analysts understand how many master templates exist and assists developers in planning migrations.

## Features

- **Document Processing**: Upload and analyze PDF and Word (.docx) documents
- **Content Analysis**: Identify common paragraphs, similar content, and variables
- **Template Detection**: Group documents with similar layouts to identify master templates
- **Variable Extraction**: Find placeholders for dynamic content like `<<variable>>`
- **Paragraph Comparison**: Detect identical and similar paragraphs across documents
- **Rich Visualization**: Interactive interface for analyzing document structure
- **Export Functionality**: Export analysis results to Excel

## Installation

### Prerequisites

- Python 3.8 or higher
- Pip (Python package installer)
- Virtual environment (recommended)

### Setup

1. Clone this repository or download the source code:

```bash
git clone https://github.com/yourusername/document-analyzer.git
cd document-analyzer
```

2. Create and activate a virtual environment:

```bash
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Initialize the application:

```bash
python app.py
```

5. Open your browser and navigate to:

```
http://127.0.0.1:5000/
```

## Usage

### Uploading Documents

1. Click on the "Upload" button in the navigation bar
2. Select a PDF or Word document (.pdf or .docx)
3. Click "Upload" to start processing

### Analyzing Documents

After uploading documents, you can:

- **View Document Details**: See metadata, content, and structure
- **Analyze Paragraphs**: Find common paragraphs across documents
- **Identify Variables**: View placeholders for dynamic content
- **Compare Content**: Find similarities between documents
- **Detect Templates**: Group documents with similar layouts

### Exporting Data

You can export analysis results to Excel:

- Document summary
- Paragraph analysis
- Variable lists
- Template groupings

## Advanced Configuration

The application can be configured by editing the `config.py` file:

- `UPLOAD_FOLDER`: Directory for uploaded documents
- `MAX_CONTENT_LENGTH`: Maximum file size (default: 50MB)
- `SIMILARITY_THRESHOLD`: Threshold for paragraph similarity (default: 0.8)
- `VARIABLE_PATTERNS`: Regex patterns to detect variables

## Security

- All processing is done locally
- No data leaves your environment
- Uploaded documents are stored in the `uploads` folder
- Detailed logs are stored in the `logs` folder

## Troubleshooting

If you encounter issues:

1. Check the logs in the `logs` folder
2. Verify file formats (PDF, DOCX)
3. Check file permissions
4. Restart the application

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- PyMuPDF for PDF processing
- Python-docx for Word document processing
- Flask for the web framework
- Bootstrap for the UI

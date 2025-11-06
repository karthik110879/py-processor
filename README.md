# PDF Processor Bridge - Flask Microservice

A powerful Flask microservice that processes PDF and document files using the `docling` library with advanced features including OCR, table extraction, image extraction, and multiple output formats.

## Features

### Core Features
- **Multi-Format Support**: PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, HTML, TXT, and MD files
- **Multiple Output Formats**: Markdown, JSON, and HTML output formats
- **Metadata Extraction**: Extracts title, author, date, page count, language, subject, and keywords
- **Noise Removal**: Automatically removes headers, footers, and watermarks
- **RESTful API**: Clean JSON responses with consistent structure
- **Error Handling**: Comprehensive error handling with meaningful messages
- **Health Check**: `/health` endpoint for service monitoring

### Advanced Features
- **OCR Support**: Process scanned documents and images with OCR (configurable)
- **Table Extraction**: Extract tables with structured data (rows, columns, markdown)
- **Image Extraction**: Extract images with metadata and base64 encoding
- **Document Chunking**: Split large documents into manageable chunks with configurable overlap
- **Enhanced Metadata**: Language detection, document classification hints, and document properties
- **Pipeline Options**: Configurable OCR and cleanup settings

## Requirements

- Python 3.10+
- Flask 3.x
- docling 1.0+
- python-dotenv
- pytest (for testing)
- flask-cors
- opencv-python-headless (for OCR support)

## Installation

1. **Clone or navigate to the project directory:**
   ```bash
   cd py-processor
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv venv
   ```
   
   **Activate it:**
   - On Windows: `venv\Scripts\activate`
   - On macOS/Linux: `source venv/bin/activate`

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Copy `.env.example` to `.env` and modify as needed:

```env
HOST=0.0.0.0
PORT=5001
DEBUG=False
UPLOAD_FOLDER=/tmp
```

## Running the Service

Start the Flask server:

```bash
python app.py
```

The server will run at `http://localhost:5001` by default.

## API Endpoints

### POST /process-pdf

Process a document file and get parsed content with optional advanced features.

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`
- Body: Form data with field name `file` containing the document file
- Optional Query Parameters (or form fields):
  - `enable_ocr`: Enable OCR for scanned documents (`true`/`false`, default: `false`)
  - `output_format`: Output format - `markdown`, `json`, or `html` (default: `markdown`)
  - `extract_tables`: Extract tables (`true`/`false`, default: `true`)
  - `extract_images`: Extract images (`true`/`false`, default: `true`)
  - `chunk_size`: Chunk document into pieces of this size (integer, optional)
  - `chunk_overlap`: Overlap between chunks (integer, default: `200`)

**Response (Success):**
```json
{
  "status": "success",
  "data": {
    "metadata": {
      "filename": "document.pdf",
      "title": "Document Title",
      "author": "Author Name",
      "date": "2024-01-01",
      "pages": 10,
      "language": "en",
      "subject": "Document Subject",
      "keywords": ["keyword1", "keyword2"]
    },
    "content": "# Document Title\n\nContent in markdown format...",
    "sections": [
      {
        "title": "Section 1",
        "content": "Section content",
        "level": 1
      }
    ],
    "tables": [
      {
        "type": "table",
        "rows": [
          ["Header 1", "Header 2"],
          ["Data 1", "Data 2"]
        ],
        "markdown": "| Header 1 | Header 2 |\n|----------|----------|\n| Data 1   | Data 2   |"
      }
    ],
    "images": [
      {
        "type": "image",
        "description": "Image caption",
        "base64": "iVBORw0KGgoAAAANSUhEUgAA...",
        "format": "base64"
      }
    ],
    "chunks": [
      {
        "chunk_index": 0,
        "content": "First chunk of content...",
        "start": 0,
        "end": 1000
      }
    ]
  },
  "message": "Successfully processed document: document.pdf"
}
```

**Response (Error):**
```json
{
  "status": "error",
  "message": "Error message here"
}
```

**Example using curl (Basic):**
```bash
curl -X POST http://localhost:5001/process-pdf \
  -F "file=@path/to/your/document.pdf"
```

**Example using curl (With OCR and JSON output):**
```bash
curl -X POST "http://localhost:5001/process-pdf?enable_ocr=true&output_format=json" \
  -F "file=@path/to/scanned_document.pdf"
```

**Example using curl (With chunking):**
```bash
curl -X POST "http://localhost:5001/process-pdf?chunk_size=2000&chunk_overlap=300" \
  -F "file=@path/to/large_document.pdf"
```

**Example using Python requests (Basic):**
```python
import requests

url = "http://localhost:5001/process-pdf"
files = {"file": open("document.pdf", "rb")}
response = requests.post(url, files=files)
print(response.json())
```

**Example using Python requests (With all options):**
```python
import requests

url = "http://localhost:5001/process-pdf"
files = {"file": open("scanned_document.pdf", "rb")}
params = {
    "enable_ocr": "true",
    "output_format": "json",
    "extract_tables": "true",
    "extract_images": "true",
    "chunk_size": "2000",
    "chunk_overlap": "200"
}
response = requests.post(url, files=files, params=params)
result = response.json()
print(result)
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "success",
  "data": {
    "status": "ok"
  },
  "message": "Service is healthy"
}
```

## Feature Details

### OCR Support
Enable OCR to process scanned documents and image-based PDFs:
```bash
curl -X POST "http://localhost:5001/process-pdf?enable_ocr=true" \
  -F "file=@scanned_document.pdf"
```

### Table Extraction
Tables are automatically extracted with structured data:
- Row and column structure
- Markdown representation
- Preserved cell relationships

### Image Extraction
Images are extracted with:
- Descriptions/captions
- Base64 encoded image data
- Metadata

### Document Chunking
Split large documents into smaller chunks for processing:
- Configurable chunk size
- Overlap between chunks to maintain context
- Sentence boundary detection

### Output Formats
Choose your preferred output format:
- **Markdown**: Clean markdown text (default)
- **JSON**: Structured JSON format
- **HTML**: HTML formatted output

## Testing

Run the test suite:

```bash
pytest test_app.py -v
```

## Project Structure

```
py-processor/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── test_app.py           # Test suite
├── .env                  # Environment configuration
├── .env.example          # Example environment file
├── services/
│   ├── __init__.py
│   └── pdf_service.py    # PDF processing logic with advanced features
├── routes/
│   ├── __init__.py
│   └── pdf_routes.py     # API routes with parameter handling
└── utils/
    ├── __init__.py
    └── response_formatter.py  # Response formatting utilities
```

## Architecture

- **Flask Blueprints**: Routes organized in blueprints for modularity
- **Service Layer**: Business logic separated in `services/pdf_service.py`
- **Utility Layer**: Common utilities in `utils/`
- **Error Handling**: Centralized error handlers in `app.py`
- **Logging**: Structured logging with timestamps and log levels
- **Pipeline Options**: Configurable OCR and cleanup via docling pipeline

## Error Codes

- `200`: Success
- `400`: Bad Request (invalid input, missing file, invalid file type, invalid parameters)
- `413`: Request Entity Too Large (file exceeds size limit)
- `500`: Internal Server Error

## Integration with NestJS

This microservice is designed to be called from a NestJS backend. The service:

- Returns clean JSON responses
- Supports CORS (enabled via flask-cors)
- Uses consistent response format
- Handles errors gracefully
- Supports query parameters and form data for configuration

**Example NestJS integration:**
```typescript
async processDocument(file: Express.Multer.File, options?: {
  enableOcr?: boolean;
  outputFormat?: 'markdown' | 'json' | 'html';
  extractTables?: boolean;
  extractImages?: boolean;
  chunkSize?: number;
  chunkOverlap?: number;
}) {
  const formData = new FormData();
  formData.append('file', file.buffer, file.originalname);
  
  const params = new URLSearchParams();
  if (options?.enableOcr) params.append('enable_ocr', 'true');
  if (options?.outputFormat) params.append('output_format', options.outputFormat);
  if (options?.chunkSize) params.append('chunk_size', options.chunkSize.toString());
  
  const response = await axios.post(
    `http://localhost:5001/process-pdf?${params.toString()}`,
    formData,
    { headers: formData.getHeaders() }
  );
  
  return response.data;
}
```

## Development

### Code Standards

- Type hints in all function definitions
- Docstrings for all functions
- Code formatted with Black
- Logging instead of print statements

### Formatting Code

```bash
black .
```

## Performance Considerations

- **OCR**: Enabling OCR significantly increases processing time but enables scanned document support
- **Chunking**: Use chunking for large documents to improve processing and downstream analysis
- **Image Extraction**: Base64 encoding increases response size; consider extracting only when needed
- **Table Extraction**: Automatically enabled but can be disabled if not needed

## License

This project is part of a document processing system.

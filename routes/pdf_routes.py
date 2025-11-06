"""Routes for PDF processing endpoints."""

import logging
from flask import Blueprint, request, current_app
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

from services.pdf_service import PDFService
from utils.response_formatter import success_response, error_response

logger = logging.getLogger(__name__)

# Create blueprint
pdf_bp = Blueprint('pdf', __name__)

# Initialize PDF service
pdf_service = PDFService()


def allowed_file(filename: str) -> bool:
    """
    Check if the uploaded file has an allowed extension.

    Args:
        filename: Name of the file to check

    Returns:
        True if file extension is allowed, False otherwise
    """
    # Allow common document formats that docling supports
    allowed_extensions = {
        'pdf', 'docx', 'doc', 'pptx', 'ppt', 
        'xlsx', 'xls', 'html', 'htm', 'txt', 'md'
    }
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


@pdf_bp.route('/process-pdf', methods=['POST'])
def process_pdf() -> tuple:
    """
    Process an uploaded PDF or document file.

    Expects:
        - multipart/form-data with field name 'file'
        - File can be PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, HTML, TXT, or MD
        - Optional query parameters:
            - enable_ocr: Enable OCR for scanned documents (true/false, default: false)
            - output_format: Output format - "markdown", "json", or "html" (default: "markdown")
            - extract_tables: Extract tables (true/false, default: true)
            - extract_images: Extract images (true/false, default: true)
            - chunk_size: Chunk document into pieces of this size (integer, optional)
            - chunk_overlap: Overlap between chunks (integer, default: 200)

    Returns:
        JSON response with:
            - status: "success" | "error"
            - data: { metadata, content, sections, tables, images, chunks }
            - message: Optional message
    """
    try:
        # Check if file is present in request
        if 'file' not in request.files:
            return error_response(
                "No file provided. Please upload a file with field name 'file'",
                status_code=400
            )
        
        file = request.files['file']
        
        # Check if file was actually selected
        if file.filename == '':
            return error_response(
                "No file selected. Please select a file to upload",
                status_code=400
            )
        
        # Validate file extension
        if not allowed_file(file.filename):
            return error_response(
                "Invalid file type. Allowed types: PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, HTML, TXT, MD",
                status_code=400
            )
        
        # Secure the filename
        filename = secure_filename(file.filename)
        
        # Parse optional parameters from query string or form data
        enable_ocr = request.args.get('enable_ocr', 'false').lower() == 'true' or \
                     request.form.get('enable_ocr', 'false').lower() == 'true'
        
        output_format = request.args.get('output_format', request.form.get('output_format', 'markdown')).lower()
        if output_format not in ['markdown', 'json', 'html']:
            output_format = 'markdown'
        
        extract_tables = request.args.get('extract_tables', request.form.get('extract_tables', 'true')).lower() != 'false'
        extract_images = request.args.get('extract_images', request.form.get('extract_images', 'true')).lower() != 'false'
        
        chunk_size = None
        chunk_size_param = request.args.get('chunk_size', request.form.get('chunk_size'))
        if chunk_size_param:
            try:
                chunk_size = int(chunk_size_param)
                if chunk_size <= 0:
                    return error_response(
                        "chunk_size must be a positive integer",
                        status_code=400
                    )
            except ValueError:
                return error_response(
                    "chunk_size must be a valid integer",
                    status_code=400
                )
        
        chunk_overlap = 200
        chunk_overlap_param = request.args.get('chunk_overlap', request.form.get('chunk_overlap'))
        if chunk_overlap_param:
            try:
                chunk_overlap = int(chunk_overlap_param)
                if chunk_overlap < 0:
                    return error_response(
                        "chunk_overlap must be a non-negative integer",
                        status_code=400
                    )
            except ValueError:
                return error_response(
                    "chunk_overlap must be a valid integer",
                    status_code=400
                )
        
        logger.info(
            f"Processing file: {filename} "
            f"(OCR={enable_ocr}, format={output_format}, "
            f"tables={extract_tables}, images={extract_images}, "
            f"chunk_size={chunk_size})"
        )
        
        # Process the document
        try:
            result = pdf_service.process_file_upload(
                file,
                enable_ocr=enable_ocr,
                output_format=output_format,
                extract_tables=extract_tables,
                extract_images=extract_images,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            
            return success_response(
                data=result,
                message=f"Successfully processed document: {filename}"
            )
            
        except ValueError as e:
            logger.error(f"Validation error: {str(e)}")
            return error_response(
                str(e),
                status_code=400
            )
        
        except Exception as e:
            logger.error(f"Processing error: {str(e)}", exc_info=True)
            return error_response(
                f"Failed to process document: {str(e)}",
                status_code=500
            )
    
    except RequestEntityTooLarge:
        return error_response(
            "File size exceeds maximum allowed size",
            status_code=413
        )
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return error_response(
            "An unexpected error occurred while processing the request",
            status_code=500
        )


@pdf_bp.route('/health', methods=['GET'])
def health_check() -> tuple:
    """
    Health check endpoint.

    Returns:
        JSON response with status "ok"
    """
    return success_response(
        data={"status": "ok"},
        message="Service is healthy"
    )


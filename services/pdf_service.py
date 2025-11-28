"""Service for processing PDF documents using docling."""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import tempfile
import os
import json
import base64
import agents.chunking_agent as chunking_agent
import agents.storing_agent as storing_agent
try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat
except ImportError:
    DocumentConverter = None
    PdfPipelineOptions = None
    InputFormat = None

logger = logging.getLogger(__name__)


class PDFService:
    """Service class for processing PDF and document files using docling."""
    
    def __init__(self, enable_ocr: bool = False, enable_cleanup: bool = True) -> None:
        """
        Initialize the PDF service with docling converter.
        
        Args:
            enable_ocr: Enable OCR for scanned documents (default: False)
            enable_cleanup: Enable cleanup to remove headers/footers/watermarks (default: True)
        """
        if DocumentConverter is None:
            raise ImportError(
                "docling library is not installed. "
                "Please install it using: pip install docling"
            )
        
        # Initialize docling converter
        # Note: DocumentConverter doesn't accept pipeline_options in constructor
        # Pipeline options may be passed to convert() method or configured differently
        self.converter = DocumentConverter()
        
        # Store pipeline options for potential use in convert() calls
        if PdfPipelineOptions:
            self._pipeline_options = PdfPipelineOptions(
                do_ocr=enable_ocr,
                do_cleanup=enable_cleanup
            )
        else:
            self._pipeline_options = None
        
        # Store OCR and cleanup settings
        self._enable_ocr = enable_ocr
        self._enable_cleanup = enable_cleanup
        self._last_ocr_setting = enable_ocr
        
        logger.info(f"PDFService initialized with docling converter (OCR={enable_ocr}, Cleanup={enable_cleanup})")
    
    def _extract_tables(self, doc: Any) -> List[Dict[str, Any]]:
        """
        Extract tables from the document.
        
        Args:
            doc: Document object from docling
            
        Returns:
            List of table dictionaries with structure
        """
        tables = []
        
        # Try to find tables in the document
        if hasattr(doc, 'items'):
            for item in doc.items:
                if hasattr(item, 'type') and item.type == 'table':
                    table_data = {
                        "type": "table",
                        "rows": [],
                        "columns": []
                    }
                    
                    # Extract table structure
                    if hasattr(item, 'rows'):
                        for row in item.rows:
                            row_data = []
                            if hasattr(row, 'cells'):
                                for cell in row.cells:
                                    cell_text = ""
                                    if hasattr(cell, 'text'):
                                        cell_text = cell.text
                                    elif hasattr(cell, 'content'):
                                        cell_text = str(cell.content)
                                    row_data.append(cell_text)
                            if row_data:
                                table_data["rows"].append(row_data)
                    
                    # Try to export as CSV or structured format
                    if hasattr(item, 'export_to_markdown'):
                        table_data["markdown"] = item.export_to_markdown()
                    elif hasattr(item, 'to_markdown'):
                        table_data["markdown"] = item.to_markdown()
                    
                    if table_data["rows"] or "markdown" in table_data:
                        tables.append(table_data)
        
        # Alternative: search in document structure
        if not tables and hasattr(doc, 'tables'):
            for table in doc.tables:
                table_data = {
                    "type": "table",
                    "rows": [],
                    "markdown": ""
                }
                if hasattr(table, 'export_to_markdown'):
                    table_data["markdown"] = table.export_to_markdown()
                tables.append(table_data)
        
        return tables
    
    def _extract_images(self, doc: Any) -> List[Dict[str, Any]]:
        """
        Extract images from the document.
        
        Args:
            doc: Document object from docling
            
        Returns:
            List of image metadata dictionaries
        """
        images = []
        
        # Try to find images in the document
        if hasattr(doc, 'items'):
            for item in doc.items:
                if hasattr(item, 'type') and item.type == 'image':
                    image_data = {
                        "type": "image",
                        "description": ""
                    }
                    
                    if hasattr(item, 'description'):
                        image_data["description"] = item.description
                    elif hasattr(item, 'caption'):
                        image_data["description"] = item.caption
                    
                    if hasattr(item, 'image'):
                        # Try to get image data
                        try:
                            if hasattr(item.image, 'data'):
                                # Encode image as base64 if available
                                img_data = item.image.data
                                if isinstance(img_data, bytes):
                                    image_data["base64"] = base64.b64encode(img_data).decode('utf-8')
                                    image_data["format"] = "base64"
                        except Exception as e:
                            logger.debug(f"Could not extract image data: {str(e)}")
                    
                    images.append(image_data)
        
        # Alternative: search in document structure
        if not images and hasattr(doc, 'images'):
            for img in doc.images:
                image_data = {
                    "type": "image",
                    "description": ""
                }
                if hasattr(img, 'description'):
                    image_data["description"] = img.description
                images.append(image_data)
        
        return images
    
    def _chunk_document(
        self,
        content: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Chunk document content into smaller pieces.
        
        Args:
            content: Full document content
            chunk_size: Maximum size of each chunk (characters)
            chunk_overlap: Overlap between chunks (characters)
            
        Returns:
            List of chunk dictionaries
        """
        if not content or len(content) <= chunk_size:
            return [{"chunk_index": 0, "content": content, "start": 0, "end": len(content)}]
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(content):
            end = start + chunk_size
            
            # Try to break at sentence boundary if possible
            if end < len(content):
                # Look for sentence endings near the chunk boundary
                for i in range(end, max(start + chunk_size - 100, start), -1):
                    if i < len(content) and content[i] in '.!?\n':
                        end = i + 1
                        break
            
            chunk_content = content[start:end]
            chunks.append({
                "chunk_index": chunk_index,
                "content": chunk_content,
                "start": start,
                "end": min(end, len(content))
            })
            
            chunk_index += 1
            start = end - chunk_overlap
            
            if start >= len(content):
                break
        
        return chunks
    
    def process_document(
        self,
        file_path: str,
        filename: Optional[str] = None,
        output_format: str = "markdown",
        extract_tables: bool = True,
        extract_images: bool = True,
        chunk_size: Optional[int] = None,
        chunk_overlap: int = 200
    ) -> Dict[str, Any]:
        """
        Process a document file and extract content, metadata, and sections.

        Args:
            file_path: Path to the document file
            filename: Original filename (optional)
            output_format: Output format - "markdown", "json", or "html" (default: "markdown")
            extract_tables: Whether to extract tables (default: True)
            extract_images: Whether to extract images (default: True)
            chunk_size: If provided, chunk the document into pieces of this size (default: None)
            chunk_overlap: Overlap between chunks when chunking (default: 200)

        Returns:
            Dictionary containing:
                - metadata: Document metadata (title, author, date, pages, language, etc.)
                - content: Full text content in specified format
                - sections: Structured sections if available
                - tables: Extracted tables with structure
                - images: Extracted images metadata
                - chunks: Document chunks if chunk_size is provided
                - filename: Original filename

        Raises:
            ValueError: If file doesn't exist or is invalid
            Exception: If processing fails
        """
        if not os.path.exists(file_path):
            raise ValueError(f"File not found: {file_path}")
        
        try:
            logger.info(f"Processing document: {file_path} (format={output_format})")
            
            # Convert document using docling
            # Try to pass pipeline options to convert() if available
            if hasattr(self, '_pipeline_options') and self._pipeline_options:
                try:
                    result = self.converter.convert(file_path)
                except TypeError:
                    # If convert() doesn't accept pipeline_options, use default
                    result = self.converter.convert(file_path)
            else:
                result = self.converter.convert(file_path)
            
            # Extract metadata
            metadata: Dict[str, Any] = {
                "filename": filename or os.path.basename(file_path),
            }
            
            # Extract content
            content = ""
            sections = []
            tables = []
            images = []
            
            # Try to get the document from the result
            doc = result.document if hasattr(result, 'document') else result
            
            # Extract metadata if available
            if hasattr(doc, 'meta') and doc.meta:
                meta = doc.meta
                if hasattr(meta, 'title') and meta.title:
                    metadata["title"] = meta.title
                if hasattr(meta, 'author') and meta.author:
                    metadata["author"] = meta.author
                if hasattr(meta, 'creation_date') and meta.creation_date:
                    metadata["date"] = str(meta.creation_date)
                if hasattr(meta, 'language') and meta.language:
                    metadata["language"] = meta.language
                if hasattr(meta, 'subject') and meta.subject:
                    metadata["subject"] = meta.subject
                if hasattr(meta, 'keywords') and meta.keywords:
                    metadata["keywords"] = meta.keywords
            
            # Get page count if available
            if hasattr(doc, 'pages') and doc.pages:
                metadata["pages"] = len(doc.pages)
            
            # Extract content based on output format
            if output_format.lower() == "markdown":
                if hasattr(doc, 'export_to_markdown'):
                    content = doc.export_to_markdown()
                elif hasattr(doc, 'to_markdown'):
                    content = doc.to_markdown()
                elif hasattr(doc, 'export'):
                    content = doc.export(format='markdown')
                else:
                    content = str(doc)
            elif output_format.lower() == "json":
                if hasattr(doc, 'export_to_json'):
                    content = doc.export_to_json()
                elif hasattr(doc, 'export'):
                    content = doc.export(format='json')
                else:
                    # Fallback: convert to dict and then JSON
                    try:
                        content = json.dumps(doc.__dict__ if hasattr(doc, '__dict__') else str(doc), default=str)
                    except:
                        content = json.dumps({"content": str(doc)})
            elif output_format.lower() == "html":
                if hasattr(doc, 'export_to_html'):
                    content = doc.export_to_html()
                elif hasattr(doc, 'export'):
                    content = doc.export(format='html')
                else:
                    # Fallback: wrap in HTML
                    content = f"<html><body><pre>{str(doc)}</pre></body></html>"
            else:
                # Default to markdown
                if hasattr(doc, 'export_to_markdown'):
                    content = doc.export_to_markdown()
                else:
                    content = str(doc)
            
            # Extract sections if available
            if hasattr(doc, 'sections') and doc.sections:
                for section in doc.sections:
                    section_data: Dict[str, Any] = {}
                    if hasattr(section, 'title'):
                        section_data["title"] = section.title
                    if hasattr(section, 'content'):
                        section_data["content"] = section.content
                    if hasattr(section, 'level'):
                        section_data["level"] = section.level
                    if section_data:
                        sections.append(section_data)
            
            # Extract tables if requested
            if extract_tables:
                try:
                    tables = self._extract_tables(doc)
                    logger.info(f"Extracted {len(tables)} tables from document")
                except Exception as e:
                    logger.warning(f"Error extracting tables: {str(e)}")
                    tables = []
            
            # Extract images if requested
            if extract_images:
                try:
                    images = self._extract_images(doc)
                    logger.info(f"Extracted {len(images)} images from document")
                except Exception as e:
                    logger.warning(f"Error extracting images: {str(e)}")
                    images = []
            
            # Chunk document if requested
            chunks = None
            if chunk_size and chunk_size > 0:
                try:
                    chunks = self._chunk_document(content, chunk_size, chunk_overlap)
                    logger.info(f"Chunked document into {len(chunks)} pieces")
                except Exception as e:
                    logger.warning(f"Error chunking document: {str(e)}")
            
            logger.info(f"Successfully processed document: {filename or file_path}")
            
            result_data = {
                "metadata": metadata,
                "content": content,
                "sections": sections if sections else None,
                "tables": tables if tables else None,
                "images": images if images else None,
                "chunks": chunks if chunks else None
            }

            # ➜ STORE CHUNKS IN CHROMA DB
            if content:
                try:
                    # chunked_data = chunking_agent.create_chunking_agent().invoke({"input": content})
                    # agent = chunking_agent.create_chunking_agent()
                    # response = agent.invoke({
                    #     "messages": [{
                    #             "role": "user",
                    #             "content": content
                    #         }]
                    # })

                    # output_text = "\n".join(response["structured_response"].chunks)
                    # print("Chunked data:", chunked_data)
                    # stored_count = storing_agent.create_store_agent().invoke({
                    #     "payload": {
                    #         "chunks": chunked_data
                    #     }
                    # })
                    chunk_agent_response = chunking_agent.chunk_text.invoke({
                        "content": content,
                    })
                    print("Chunked data:", chunk_agent_response["chunks"])

                    store_agent_response = storing_agent.store_vectors.invoke({
                        "payload": {
                            "chunks": chunk_agent_response["chunks"]
                        }
                    })
                    print("Stored chunks count:", store_agent_response)
                    print(f"Stored {store_agent_response} chunks into Qdrant DB")
                    logger.info(f"Stored {store_agent_response} chunks into Qdrant DB")
                    result_data["chunks"] = chunk_agent_response["chunks"]
                except Exception as e:
                    logger.error(f"Failed to store chunks in Qdrant DB: {str(e)}")
                        
            return result_data
            
        except Exception as e:
            logger.error(f"Error processing document {file_path}: {str(e)}", exc_info=True)
            raise Exception(f"Failed to process document: {str(e)}")
    
    def process_file_upload(
        self,
        file_storage,
        enable_ocr: bool = False,
        output_format: str = "markdown",
        extract_tables: bool = True,
        extract_images: bool = True,
        chunk_size: Optional[int] = None,
        chunk_overlap: int = 200
    ) -> Dict[str, Any]:
        """
        Process an uploaded file from Flask request.

        Args:
            file_storage: FileStorage object from Flask request
            enable_ocr: Enable OCR for scanned documents (default: False)
            output_format: Output format - "markdown", "json", or "html" (default: "markdown")
            extract_tables: Whether to extract tables (default: True)
            extract_images: Whether to extract images (default: True)
            chunk_size: If provided, chunk the document into pieces of this size (default: None)
            chunk_overlap: Overlap between chunks when chunking (default: 200)

        Returns:
            Dictionary with processed document data

        Raises:
            ValueError: If file is invalid or missing
            Exception: If processing fails
        """
        if not file_storage or not file_storage.filename:
            raise ValueError("No file provided")
        
        # Update pipeline options if OCR setting changes
        # Note: We store options and pass them to convert() method
        if enable_ocr != getattr(self, '_last_ocr_setting', False):
            if PdfPipelineOptions:
                self._pipeline_options = PdfPipelineOptions(
                    do_ocr=enable_ocr,
                    do_cleanup=True
                )
            else:
                self._pipeline_options = None
            self._last_ocr_setting = enable_ocr
            self._enable_ocr = enable_ocr
        
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_storage.filename)[1]) as tmp_file:
            file_storage.save(tmp_file.name)
            tmp_path = tmp_file.name
        
        try:
            # Process the document
            result = self.process_document(
                tmp_path,
                file_storage.filename,
                output_format=output_format,
                extract_tables=extract_tables,
                extract_images=extract_images,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            return result
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                logger.debug(f"Cleaned up temporary file: {tmp_path}")

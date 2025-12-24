"""Document PKG integration service."""

import os
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from services.claude_document_analyzer import ClaudeDocumentAnalyzer
from services.pdf_service import PDFService
from utils.logging_config import get_logger, log_with_context

logger = get_logger(__name__)


class DocumentPKGIntegrator:
    """Integrates documents into PKG with Claude analysis."""
    
    def __init__(self):
        """Initialize document PKG integrator."""
        self.analyzer = ClaudeDocumentAnalyzer()
        self.pdf_service = PDFService()
    
    def find_documents_in_repo(self, repo_path: str) -> List[str]:
        """
        Find all documents in repository.
        
        Args:
            repo_path: Root path of the repository
            
        Returns:
            List of full file paths to documents
        """
        document_extensions = {'.pdf', '.docx', '.doc', '.md', '.txt'}
        skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'qdrant_local', '.pytest_cache', 'venv', 'env'}
        document_files = []
        
        try:
            for root, dirs, files in os.walk(repo_path):
                # Skip ignored directories
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    _, ext = os.path.splitext(file)
                    
                    if ext.lower() in document_extensions:
                        document_files.append(file_path)
            
            log_with_context(
                logger, logging.INFO, f"Found {len(document_files)} documents in repository",
                repo_path=repo_path,
                count=len(document_files)
            )
            
            return document_files
        except Exception as e:
            log_with_context(
                logger, logging.ERROR, f"Error discovering documents: {e}",
                repo_path=repo_path,
                exc_info=e
            )
            return []
    
    def _generate_document_id(self, file_path: str, repo_path: str) -> str:
        """
        Generate document ID from file path.
        
        Args:
            file_path: Full file path
            repo_path: Repository root path
            
        Returns:
            Document ID in format: "doc:{relative_path}"
        """
        try:
            rel_path = os.path.relpath(file_path, repo_path)
            # Normalize path separators to forward slashes
            rel_path = rel_path.replace("\\", "/")
            return f"doc:{rel_path}"
        except Exception:
            # Fallback to filename if relative path fails
            filename = os.path.basename(file_path)
            return f"doc:{filename}"
    
    def _extract_chunk_ids(self, chunks: Optional[List[Any]], doc_id: str) -> List[str]:
        """
        Extract chunk IDs from processed chunks.
        
        Args:
            chunks: List of chunk dictionaries or strings
            doc_id: Document ID
            
        Returns:
            List of chunk IDs in format: "chunk:{doc_id}:{index}"
        """
        if not chunks:
            return []
        
        chunk_ids = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"chunk:{doc_id}:{i}"
            chunk_ids.append(chunk_id)
        
        return chunk_ids
    
    def add_documents_to_pkg(
        self,
        pkg: Dict[str, Any],
        document_files: List[str],
        repo_path: str
    ) -> Dict[str, Any]:
        """
        Add documents to PKG with Claude analysis.
        
        Args:
            pkg: PKG dictionary to enhance
            document_files: List of document file paths
            repo_path: Repository root path
            
        Returns:
            Enhanced PKG dictionary with documents array
        """
        if not document_files:
            log_with_context(
                logger, logging.INFO, "No documents to add to PKG",
                repo_path=repo_path
            )
            return pkg
        
        documents = []
        pkg_modules = pkg.get("modules", [])
        
        for file_path in document_files:
            try:
                filename = os.path.basename(file_path)
                rel_path = os.path.relpath(file_path, repo_path).replace("\\", "/")
                
                log_with_context(
                    logger, logging.INFO, f"Processing document: {filename}",
                    repo_path=repo_path,
                    file_path=rel_path
                )
                
                # Process document with PDFService
                try:
                    result_data = self.pdf_service.process_document(
                        file_path=file_path,
                        filename=filename,
                        output_format="markdown",
                        extract_tables=True,
                        extract_images=True
                    )
                except Exception as e:
                    log_with_context(
                        logger, logging.WARNING, f"Failed to process document: {e}",
                        repo_path=repo_path,
                        file_path=rel_path,
                        exc_info=e
                    )
                    continue
                
                # Get content from result
                content = result_data.get("content", "")
                if not content:
                    log_with_context(
                        logger, logging.WARNING, f"Document has no extractable content: {filename}",
                        repo_path=repo_path,
                        file_path=rel_path
                    )
                    continue
                
                # Analyze document with Claude
                document_type = self.analyzer._detect_document_type(filename)
                analysis = self.analyzer.analyze_document(
                    document_content=content,
                    filename=filename,
                    document_type=document_type
                )
                
                # Generate document ID
                doc_id = self._generate_document_id(file_path, repo_path)
                
                # Link to modules
                linked_module_ids = self.analyzer.link_document_to_modules(
                    analysis=analysis,
                    pkg_modules=pkg_modules
                )
                
                # Extract chunk IDs
                chunks = result_data.get("chunks")
                chunk_ids = self._extract_chunk_ids(chunks, doc_id)
                
                # Build document entry
                document_entry = {
                    "id": doc_id,
                    "filename": filename,
                    "path": rel_path,
                    "type": analysis.get("category", document_type),
                    "summary": analysis.get("summary", ""),
                    "key_points": analysis.get("key_points", []),
                    "linkedModuleIds": linked_module_ids,
                    "metadata": {
                        **result_data.get("metadata", {}),
                        **analysis.get("metadata", {})
                    },
                    "chunkIds": chunk_ids
                }
                
                documents.append(document_entry)
                
                log_with_context(
                    logger, logging.INFO, f"Added document to PKG: {filename} | Linked to {len(linked_module_ids)} modules",
                    repo_path=repo_path,
                    file_path=rel_path,
                    count=len(linked_module_ids)
                )
                
            except Exception as e:
                log_with_context(
                    logger, logging.ERROR, f"Error processing document {file_path}: {e}",
                    repo_path=repo_path,
                    file_path=file_path,
                    exc_info=e
                )
                continue
        
        # Add documents array to PKG
        pkg["documents"] = documents
        
        log_with_context(
            logger, logging.INFO, f"Added {len(documents)} documents to PKG",
            repo_path=repo_path,
            count=len(documents)
        )
        
        return pkg


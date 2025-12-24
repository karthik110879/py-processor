"""Claude-powered document analysis service."""

import json
import logging
import re
from typing import Dict, Any, List, Optional
from anthropic import Anthropic
from utils.config import Config
from utils.logging_config import get_logger, log_with_context

logger = get_logger(__name__)


class ClaudeDocumentAnalyzer:
    """Analyzes documents using Claude API to extract key information."""
    
    def __init__(self):
        """Initialize Claude document analyzer."""
        config = Config()
        self._anthropic_api_key = config.anthropic_api_key
        self._claude_model = config.claude_model
        self._claude_temperature = 0.3
        self._claude_max_tokens = config.claude_max_tokens
        
        # Initialize Anthropic client
        self._claude_client = None
        if self._anthropic_api_key:
            try:
                self._claude_client = Anthropic(api_key=self._anthropic_api_key)
                log_with_context(
                    logger, logging.INFO, "Claude document analyzer initialized",
                    repo_path=None
                )
            except Exception as e:
                log_with_context(
                    logger, logging.WARNING, f"Failed to initialize Claude client: {e}",
                    repo_path=None
                )
                self._claude_client = None
        else:
            log_with_context(
                logger, logging.WARNING, "ANTHROPIC_API_KEY not set, document analysis disabled",
                repo_path=None
            )
    
    def _detect_document_type(self, filename: str) -> str:
        """
        Auto-detect document type from filename patterns.
        
        Args:
            filename: Document filename
            
        Returns:
            Document type: "requirements", "cost", "enhancement", "design", "test", or "other"
        """
        filename_lower = filename.lower()
        
        # Check for requirements documents
        if any(keyword in filename_lower for keyword in ['requirement', 'req', 'spec', 'specification']):
            return "requirements"
        
        # Check for cost/budget documents
        if any(keyword in filename_lower for keyword in ['cost', 'budget', 'price', 'estimate', 'quote']):
            return "cost"
        
        # Check for enhancement/improvement documents
        if any(keyword in filename_lower for keyword in ['enhancement', 'improvement', 'upgrade', 'feature']):
            return "enhancement"
        
        # Check for design documents
        if any(keyword in filename_lower for keyword in ['design', 'architecture', 'diagram', 'mockup', 'wireframe']):
            return "design"
        
        # Check for test documents
        if any(keyword in filename_lower for keyword in ['test', 'testing', 'qa', 'quality']):
            return "test"
        
        # Default to "other"
        return "other"
    
    def analyze_document(
        self,
        document_content: str,
        filename: str,
        document_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze document using Claude API to extract key information.
        
        Args:
            document_content: Full document content (text/markdown)
            filename: Original filename
            document_type: Optional document type (auto-detected if not provided)
            
        Returns:
            Dictionary with:
                - summary: Comprehensive summary (3-5 sentences)
                - key_points: List of key points/requirements
                - referenced_modules: List of referenced code modules/features
                - category: Document category
                - metadata: Additional metadata
        """
        if not self._claude_client:
            log_with_context(
                logger, logging.DEBUG, "Claude client not available, returning empty analysis",
                file_path=filename
            )
            return {
                "summary": "",
                "key_points": [],
                "referenced_modules": [],
                "category": document_type or self._detect_document_type(filename),
                "metadata": {}
            }
        
        # Auto-detect document type if not provided
        if not document_type:
            document_type = self._detect_document_type(filename)
        
        # Limit content to 100,000 characters to avoid token limits
        content_preview = document_content[:100000] if len(document_content) > 100000 else document_content
        if len(document_content) > 100000:
            content_preview += "\n\n[Content truncated...]"
        
        # Construct prompt
        prompt = f"""Analyze this document and extract key information. Return a JSON object with the following structure:

{{
  "summary": "A comprehensive 3-5 sentence summary of the document's purpose and main content",
  "key_points": ["Key point 1", "Key point 2", "..."],
  "referenced_modules": ["module_name_1", "module_name_2", "..."],
  "technical_specs": "Technical specifications, costs, timelines, constraints mentioned",
  "category": "{document_type}"
}}

Guidelines:
- Extract all key points, requirements, or important information as a bullet list
- Identify any code modules, features, or components mentioned in the document
- Note any technical specifications, costs, timelines, or constraints
- The category should be one of: requirements, cost, enhancement, design, test, or other
- Be concise but comprehensive

Document filename: {filename}
Document type: {document_type}

Document content:
{content_preview}

Return only valid JSON, no additional text or markdown formatting."""

        try:
            message = self._claude_client.messages.create(
                model=self._claude_model,
                max_tokens=self._claude_max_tokens,
                temperature=self._claude_temperature,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            if message.content and len(message.content) > 0:
                response_text = message.content[0].text.strip()
                
                # Try to extract JSON from response (handle markdown code blocks)
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(0)
                
                try:
                    analysis = json.loads(response_text)
                    
                    # Ensure all required fields exist
                    result = {
                        "summary": analysis.get("summary", ""),
                        "key_points": analysis.get("key_points", []),
                        "referenced_modules": analysis.get("referenced_modules", []),
                        "category": analysis.get("category", document_type),
                        "metadata": {
                            "technical_specs": analysis.get("technical_specs", ""),
                            "filename": filename,
                            "document_type": document_type
                        }
                    }
                    
                    log_with_context(
                        logger, logging.DEBUG, f"Successfully analyzed document: {filename}",
                        file_path=filename
                    )
                    return result
                except json.JSONDecodeError as e:
                    log_with_context(
                        logger, logging.WARNING, f"Failed to parse Claude response as JSON: {e}",
                        file_path=filename
                    )
                    # Fallback: extract summary from text
                    return {
                        "summary": response_text[:500] if len(response_text) > 500 else response_text,
                        "key_points": [],
                        "referenced_modules": [],
                        "category": document_type,
                        "metadata": {"raw_response": response_text}
                    }
            else:
                log_with_context(
                    logger, logging.WARNING, "Empty response from Claude API",
                    file_path=filename
                )
                return {
                    "summary": "",
                    "key_points": [],
                    "referenced_modules": [],
                    "category": document_type,
                    "metadata": {}
                }
                
        except Exception as e:
            log_with_context(
                logger, logging.ERROR, f"Failed to analyze document with Claude: {e}",
                file_path=filename,
                exc_info=e
            )
            return {
                "summary": "",
                "key_points": [],
                "referenced_modules": [],
                "category": document_type,
                "metadata": {"error": str(e)}
            }
    
    def link_document_to_modules(
        self,
        analysis: Dict[str, Any],
        pkg_modules: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Match referenced modules from analysis to PKG module IDs.
        
        Args:
            analysis: Document analysis result from analyze_document()
            pkg_modules: List of module dictionaries from PKG
            
        Returns:
            List of linked module IDs (format: "mod:path/to/file.py")
        """
        linked_module_ids = []
        referenced_modules = analysis.get("referenced_modules", [])
        key_points_text = " ".join(analysis.get("key_points", []))
        summary_text = analysis.get("summary", "")
        
        # Combine all text for keyword matching
        search_text = " ".join([summary_text, key_points_text] + referenced_modules).lower()
        
        # Build module lookup by path and name
        module_by_path = {}
        module_by_name = {}
        for module in pkg_modules:
            module_id = module.get("id", "")
            path = module.get("path", "")
            filename = path.split("/")[-1] if "/" in path else path.split("\\")[-1]
            module_name = filename.split(".")[0] if "." in filename else filename
            
            module_by_path[path.lower()] = module_id
            module_by_name[module_name.lower()] = module_id
            
            # Also index by directory name
            if "/" in path:
                dir_name = path.split("/")[-2] if len(path.split("/")) > 1 else ""
            elif "\\" in path:
                dir_name = path.split("\\")[-2] if len(path.split("\\")) > 1 else ""
            else:
                dir_name = ""
            
            if dir_name:
                module_by_name[dir_name.lower()] = module_id
        
        # Match on referenced module names
        for ref_module in referenced_modules:
            ref_lower = ref_module.lower().strip()
            
            # Try exact name match
            if ref_lower in module_by_name:
                module_id = module_by_name[ref_lower]
                if module_id not in linked_module_ids:
                    linked_module_ids.append(module_id)
                    continue
            
            # Try partial path match
            for path, module_id in module_by_path.items():
                if ref_lower in path or path in ref_lower:
                    if module_id not in linked_module_ids:
                        linked_module_ids.append(module_id)
                        break
        
        # Match on keywords in module paths
        keywords = set()
        for ref_module in referenced_modules:
            # Extract keywords from referenced module names
            words = re.findall(r'\b\w+\b', ref_module.lower())
            keywords.update(words)
        
        # Also extract keywords from summary and key points
        summary_words = re.findall(r'\b\w+\b', summary_text.lower())
        key_points_words = re.findall(r'\b\w+\b', key_points_text.lower())
        keywords.update(summary_words)
        keywords.update(key_points_words)
        
        # Match modules that contain keywords
        for keyword in keywords:
            if len(keyword) < 3:  # Skip very short keywords
                continue
            
            for path, module_id in module_by_path.items():
                if keyword in path and module_id not in linked_module_ids:
                    linked_module_ids.append(module_id)
        
        log_with_context(
            logger, logging.DEBUG, f"Linked {len(linked_module_ids)} modules to document",
            count=len(linked_module_ids)
        )
        
        return linked_module_ids


"""Claude API integration for PKG generation with semantic enhancements."""

import os
import logging
import json
from typing import Dict, Any, Optional
from anthropic import Anthropic
from utils.config import Config
from utils.logging_config import get_logger, log_with_context
from services.pkg_generator import PKGGenerator
from code_parser.multi_parser import detect_language
import db.neo4j_db as neo4j_database

logger = get_logger(__name__)


class ClaudePKGGenerator(PKGGenerator):
    """PKG Generator with Claude API enhancements for semantic summaries."""
    
    def __init__(self, repo_path: str, fan_threshold: Optional[int] = None, include_features: Optional[bool] = None):
        """
        Initialize Claude-enhanced PKG generator.
        
        Args:
            repo_path: Root path of the repository
            fan_threshold: Fan-in threshold for filtering detailed symbol info (defaults to config)
            include_features: Whether to include feature groupings (defaults to config)
        """
        super().__init__(repo_path, fan_threshold, include_features)
        
        config = Config()
        self._anthropic_api_key = config.anthropic_api_key
        self._claude_model = config.claude_model
        self._claude_temperature = 0.3  # Use 0.3 for consistency, override config default
        self._claude_max_tokens = config.claude_max_tokens
        
        # Initialize Anthropic client
        self._claude_client = None
        if self._anthropic_api_key:
            try:
                self._claude_client = Anthropic(api_key=self._anthropic_api_key)
                log_with_context(
                    logger, logging.INFO, "Claude client initialized",
                    repo_path=self.repo_path
                )
            except Exception as e:
                log_with_context(
                    logger, logging.WARNING, f"Failed to initialize Claude client: {e}",
                    repo_path=self.repo_path
                )
                self._claude_client = None
        else:
            log_with_context(
                logger, logging.WARNING, "ANTHROPIC_API_KEY not set, Claude enhancements disabled",
                repo_path=self.repo_path
            )
    
    def _detect_language_from_path(self, file_path: str) -> Optional[str]:
        """
        Detect programming language from file path.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Language string or None
        """
        try:
            return detect_language(file_path)
        except Exception:
            return None
    
    def _extract_symbol_context(self, symbol: Dict[str, Any], module_source: str) -> str:
        """
        Extract code context around a symbol definition.
        
        Args:
            symbol: Symbol dictionary
            module_source: Full module source code
            
        Returns:
            Context string (max 10,000 chars)
        """
        if not module_source:
            return ""
        
        # Try to find the symbol in the source code
        symbol_name = symbol.get("name", "")
        if not symbol_name:
            return ""
        
        # For class methods, extract just the method name
        if "." in symbol_name:
            symbol_name = symbol_name.split(".")[-1]
        
        # Find the symbol definition in source
        lines = module_source.split('\n')
        context_lines = []
        found_symbol = False
        
        # Search for symbol definition
        for i, line in enumerate(lines):
            # Look for function/class/method definitions
            if symbol_name in line and (
                f"def {symbol_name}" in line or
                f"class {symbol_name}" in line or
                f"function {symbol_name}" in line or
                f"{symbol_name}(" in line
            ):
                found_symbol = True
                # Include some lines before (up to 10)
                start = max(0, i - 10)
                # Include definition and body (up to 50 lines after)
                end = min(len(lines), i + 50)
                context_lines = lines[start:end]
                break
        
        if not found_symbol:
            # Fallback: return first 200 lines
            context_lines = lines[:200]
        
        context = '\n'.join(context_lines)
        
        # Limit to 10,000 characters
        if len(context) > 10000:
            context = context[:10000]
        
        return context
    
    def _generate_module_summary_with_claude(self, module: Dict[str, Any], source_code: str) -> Optional[str]:
        """
        Generate module summary using Claude API.
        
        Args:
            module: Module dictionary
            source_code: Source code of the module
            
        Returns:
            Summary string or None on failure
        """
        if not self._claude_client:
            return None
        
        # Limit source code to 10,000 characters
        if len(source_code) > 10000:
            source_code = source_code[:10000]
        
        path = module.get("path", "")
        kinds = module.get("kind", [])
        exports_count = len(module.get("exports", []))
        
        # Construct prompt
        prompt = f"""Analyze this code module and provide a concise 2-3 sentence summary describing its purpose and main functionality.

Module path: {path}
Module types: {', '.join(kinds) if kinds else 'generic'}
Exports: {exports_count} symbols

Source code:
```{self._detect_language_from_path(os.path.join(self.repo_path, path)) or 'text'}
{source_code}
```

Provide a 2-3 sentence summary of what this module does:"""
        
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
                summary = message.content[0].text.strip()
                log_with_context(
                    logger, logging.DEBUG, f"Generated module summary for {path}",
                    repo_path=self.repo_path, file_path=path
                )
                return summary
            else:
                return None
                
        except Exception as e:
            log_with_context(
                logger, logging.ERROR, f"Failed to generate module summary with Claude: {e}",
                repo_path=self.repo_path, file_path=path
            )
            return None
    
    def _generate_symbol_summary_with_claude(self, symbol: Dict[str, Any], module_source: str) -> Optional[str]:
        """
        Generate symbol summary using Claude API.
        
        Args:
            symbol: Symbol dictionary
            module_source: Source code of the module containing the symbol
            
        Returns:
            Summary string or None on failure
        """
        if not self._claude_client:
            return None
        
        # Extract context around symbol
        context = self._extract_symbol_context(symbol, module_source)
        
        if not context:
            return None
        
        # Limit context to 10,000 characters
        if len(context) > 10000:
            context = context[:10000]
        
        symbol_name = symbol.get("name", "")
        symbol_kind = symbol.get("kind", "")
        signature = symbol.get("signature", "")
        module_id = symbol.get("moduleId", "")
        
        # Get module path from module_id
        module_path = module_id.replace("mod:", "") if module_id.startswith("mod:") else ""
        language = self._detect_language_from_path(os.path.join(self.repo_path, module_path)) if module_path else None
        
        # Construct prompt
        prompt = f"""Analyze this code symbol and provide a concise 1-2 sentence description of what it does.

Symbol name: {symbol_name}
Symbol kind: {symbol_kind}
Signature: {signature}

Code context:
```{language or 'text'}
{context}
```

Provide a 1-2 sentence description of what this symbol does:"""
        
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
                summary = message.content[0].text.strip()
                log_with_context(
                    logger, logging.DEBUG, f"Generated symbol summary for {symbol_name}",
                    repo_path=self.repo_path
                )
                return summary
            else:
                return None
                
        except Exception as e:
            log_with_context(
                logger, logging.ERROR, f"Failed to generate symbol summary with Claude: {e}",
                repo_path=self.repo_path
            )
            return None
    
    def generate_pkg(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate complete PKG JSON with Claude enhancements.
        
        First generates base PKG using static analysis, then enhances
        modules and symbols with Claude-generated summaries.
        
        Args:
            output_path: Optional path to save JSON file
            
        Returns:
            Complete PKG dictionary with Claude enhancements
        """
        # Generate base PKG using parent class
        log_with_context(
            logger, logging.INFO, "Generating base PKG with static analysis",
            repo_path=self.repo_path
        )
        pkg = super().generate_pkg(output_path=None)  # Don't save yet, we'll save after enhancements
        
        # Enhance with Claude if available
        if self._claude_client:
            log_with_context(
                logger, logging.INFO, "Enhancing PKG with Claude summaries",
                repo_path=self.repo_path
            )
            
            # Enhance modules
            modules = pkg.get("modules", [])
            for module in modules:
                # Only generate summary if it doesn't already exist
                if not module.get("moduleSummary"):
                    module_path = module.get("path", "")
                    if module_path:
                        # Reconstruct full file path
                        full_path = os.path.join(self.repo_path, module_path)
                        if os.path.exists(full_path):
                            try:
                                source_code = self._read_file_with_retry(full_path)
                                summary = self._generate_module_summary_with_claude(module, source_code)
                                if summary:
                                    module["moduleSummary"] = summary
                            except Exception as e:
                                log_with_context(
                                    logger, logging.DEBUG, f"Could not read source for module {module_path}: {e}",
                                    repo_path=self.repo_path, file_path=module_path
                                )
            
            # Enhance symbols
            symbols = pkg.get("symbols", [])
            # Build a map of module_id -> module for quick lookup
            module_map = {m["id"]: m for m in modules}
            
            for symbol in symbols:
                # Only generate summary if it doesn't already exist
                if not symbol.get("summary"):
                    module_id = symbol.get("moduleId", "")
                    module = module_map.get(module_id)
                    if module:
                        module_path = module.get("path", "")
                        if module_path:
                            # Reconstruct full file path
                            full_path = os.path.join(self.repo_path, module_path)
                            if os.path.exists(full_path):
                                try:
                                    module_source = self._read_file_with_retry(full_path)
                                    summary = self._generate_symbol_summary_with_claude(symbol, module_source)
                                    if summary:
                                        symbol["summary"] = summary
                                except Exception as e:
                                    log_with_context(
                                        logger, logging.DEBUG, f"Could not read source for symbol {symbol.get('name')}: {e}",
                                        repo_path=self.repo_path
                                    )
            
            log_with_context(
                logger, logging.INFO, "Claude enhancements complete",
                repo_path=self.repo_path
            )
        else:
            log_with_context(
                logger, logging.INFO, "Skipping Claude enhancements (client not available)",
                repo_path=self.repo_path
            )
        
        # ➜ DOCUMENT DISCOVERY AND INTEGRATION
        try:
            from services.document_pkg_integrator import DocumentPKGIntegrator
            integrator = DocumentPKGIntegrator()
            document_files = integrator.find_documents_in_repo(self.repo_path)
            
            if document_files:
                log_with_context(
                    logger, logging.INFO, f"Found {len(document_files)} documents, integrating into PKG",
                    repo_path=self.repo_path,
                    count=len(document_files)
                )
                pkg = integrator.add_documents_to_pkg(pkg, document_files, self.repo_path)
                doc_count = len(pkg.get("documents", []))
                log_with_context(
                    logger, logging.INFO, f"Added {doc_count} documents to PKG",
                    repo_path=self.repo_path,
                    count=doc_count
                )
            else:
                log_with_context(
                    logger, logging.INFO, "No documents found in repository",
                    repo_path=self.repo_path
                )
        except ImportError as e:
            log_with_context(
                logger, logging.WARNING, f"DocumentPKGIntegrator not available: {e}",
                repo_path=self.repo_path
            )
        except Exception as e:
            log_with_context(
                logger, logging.WARNING, f"Error integrating documents into PKG: {e}",
                repo_path=self.repo_path,
                exc_info=e
            )
        
        # Store enhanced PKG to Neo4j
        project_id = pkg.get("project", {}).get("id", "unknown")
        log_with_context(
            logger, logging.INFO, f"Storing enhanced PKG to Neo4j | Project ID: {project_id}",
            repo_path=self.repo_path
        )
        neo4j_database.store_pkg(pkg)
        log_with_context(
            logger, logging.INFO, f"Enhanced PKG stored to Neo4j | Project ID: {project_id}",
            repo_path=self.repo_path
        )
        
        # Save to output_path if provided
        if output_path:
            log_with_context(
                logger, logging.INFO, f"Saving enhanced PKG to file | Path: {output_path}",
                repo_path=self.repo_path
            )
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(pkg, f, indent=2)
            log_with_context(
                logger, logging.INFO, f"Enhanced PKG saved to file | Path: {output_path}",
                repo_path=self.repo_path
            )
        
        return pkg


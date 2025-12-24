"""Generate Project Knowledge Graph (PKG) JSON following project-schema.json."""

import os
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
import logging
from pathlib import Path

from code_parser.project_metadata import extract_project_metadata
from code_parser.framework_detector import detect_frameworks
from code_parser.multi_parser import detect_language, parse_file
from code_parser.multi_normalizer import extract_definitions
from code_parser.endpoint_extractors import extract_endpoints
from code_parser.relationship_extractor import extract_relationships, calculate_fan_in_fan_out
from code_parser.exceptions import ParseError, ImportResolutionError
from utils.file_utils import collect_files
from utils.config import Config
from utils.logging_config import get_logger, log_with_context
import db.neo4j_db as neo4j_database  # Import to ensure connection is established
import functools
import time
import traceback

logger = get_logger(__name__)


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """
    Retry decorator for transient failures.
    
    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between attempts in seconds
        backoff: Backoff multiplier for delay
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}. Retrying in {current_delay}s...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"All {max_attempts} attempts failed for {func.__name__}: {e}")
            
            raise last_exception
        return wrapper
    return decorator


class PKGGenerator:
    """Generate Project Knowledge Graph JSON."""
    
    def __init__(self, repo_path: str, fan_threshold: Optional[int] = None, include_features: Optional[bool] = None):
        """
        Initialize PKG generator.
        
        Args:
            repo_path: Root path of the repository
            fan_threshold: Fan-in threshold for filtering detailed symbol info (defaults to config)
            include_features: Whether to include feature groupings (defaults to config)
        """
        self.repo_path = os.path.abspath(repo_path)
        config = Config()
        self.fan_threshold = fan_threshold if fan_threshold is not None else config.fan_threshold
        self.include_features = include_features if include_features is not None else config.include_features
        self.modules = []
        self.symbols = []
        self.endpoints = []
        self.edges = []
        self.features = []
        self.frameworks = []
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
    
    def _collect_error(self, error_type: str, file_path: str, message: str, stack_trace: Optional[str] = None) -> None:
        """
        Collect error information.
        
        Args:
            error_type: Type of error (file_not_found, parse_error, etc.)
            file_path: Path where error occurred
            message: Error message
            stack_trace: Optional stack trace
        """
        error = {
            "type": error_type,
            "file_path": file_path,
            "message": message,
            "stack_trace": stack_trace
        }
        self.errors.append(error)
        log_with_context(
            logger, logging.ERROR, f"Error collected: {message}",
            repo_path=self.repo_path, file_path=file_path, error_type=error_type
        )
    
    def _collect_warning(self, warning_type: str, file_path: str, message: str) -> None:
        """
        Collect warning information.
        
        Args:
            warning_type: Type of warning
            file_path: Path where warning occurred
            message: Warning message
        """
        warning = {
            "type": warning_type,
            "file_path": file_path,
            "message": message
        }
        self.warnings.append(warning)
        log_with_context(
            logger, logging.WARNING, f"Warning: {message}",
            repo_path=self.repo_path, file_path=file_path
        )
    
    @retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(IOError, OSError))
    def _read_file_with_retry(self, file_path: str) -> str:
        """
        Read file with retry logic for transient I/O failures.
        
        Args:
            file_path: Path to file
            
        Returns:
            File contents as string
            
        Raises:
            FileNotFoundError: If file doesn't exist
            IOError: If file can't be read after retries
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except FileNotFoundError:
            raise  # Don't retry file not found
        except (IOError, OSError) as e:
            raise IOError(f"Failed to read file {file_path}: {e}") from e
        
    def _generate_module_id(self, file_path: str) -> str:
        """Generate stable module ID from file path."""
        rel_path = os.path.relpath(file_path, self.repo_path)
        # Normalize path separators
        rel_path = rel_path.replace(os.sep, '/')
        return f"mod:{rel_path}"
    
    def _generate_symbol_id(self, module_id: str, symbol_name: str) -> str:
        """Generate stable symbol ID."""
        return f"sym:{module_id}:{symbol_name}"
    
    def _generate_feature_id(self, folder_path: str) -> str:
        """Generate stable feature ID from folder path."""
        rel_path = os.path.relpath(folder_path, self.repo_path)
        rel_path = rel_path.replace(os.sep, '/')
        return f"feat:{rel_path}"
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file content."""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                return hashlib.sha256(content).hexdigest()
        except FileNotFoundError as e:
            self._collect_error("file_not_found", file_path, str(e))
            return ""
        except (IOError, OSError) as e:
            self._collect_error("io_error", file_path, f"Failed to read file for hash: {e}")
            return ""
    
    def _count_lines_of_code(self, file_path: str) -> int:
        """Count lines of code in a file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return len([line for line in f if line.strip()])
        except FileNotFoundError as e:
            self._collect_error("file_not_found", file_path, str(e))
            return 0
        except (IOError, OSError) as e:
            self._collect_error("io_error", file_path, f"Failed to read file for LOC: {e}")
            return 0
    
    def _extract_decorators_from_ast(self, file_path: str) -> List[str]:
        """
        Extract decorators/annotations from file using AST analysis.
        
        Args:
            file_path: Path to file
            
        Returns:
            List of decorator names
        """
        decorators = []
        try:
            from code_parser.multi_parser import detect_language, parse_file
            from code_parser.normalizer import get_text
            
            language = detect_language(file_path)
            if not language:
                return decorators
            
            root = parse_file(file_path)
            if not root:
                return decorators
            
            def walk(node):
                yield node
                for child in node.children:
                    yield from walk(child)
            
            for node in walk(root):
                # Python decorators
                if node.type == "decorator":
                    decorator_text = get_text(node, "").strip()
                    if decorator_text.startswith("@"):
                        decorators.append(decorator_text[1:].split("(")[0].strip())
                
                # TypeScript/JavaScript decorators
                elif node.type == "decorator":
                    decorator_text = get_text(node, "").strip()
                    if decorator_text.startswith("@"):
                        decorators.append(decorator_text[1:].split("(")[0].strip())
                
                # Java annotations
                elif node.type == "annotation":
                    annotation_text = get_text(node, "").strip()
                    if annotation_text.startswith("@"):
                        decorators.append(annotation_text[1:].split("(")[0].strip())
                
                # C# attributes
                elif node.type == "attribute":
                    attr_text = get_text(node, "").strip()
                    if attr_text.startswith("[") and attr_text.endswith("]"):
                        decorators.append(attr_text[1:-1].split("(")[0].strip())
        
        except Exception as e:
            # Fallback to empty list on error
            log_with_context(logger, logging.DEBUG, f"Failed to extract decorators from AST: {e}", file_path=file_path)
            pass
        
        return decorators
    
    def _detect_module_kind(self, file_path: str, definitions: Dict[str, Any], frameworks: List[str]) -> List[str]:
        """
        Detect module kind/tags using AST analysis and framework patterns.
        
        Args:
            file_path: Path to file
            definitions: Extracted definitions
            frameworks: Detected frameworks
            
        Returns:
            List of module kinds
        """
        kinds = []
        file_name = os.path.basename(file_path).lower()
        path_lower = file_path.lower()
        
        # Extract decorators from AST
        decorators = self._extract_decorators_from_ast(file_path)
        decorator_names = [d.lower() for d in decorators]
        decorators_str = " ".join(decorator_names)
        
        # Framework-specific detection using AST decorators
        if "nestjs" in frameworks:
            if "controller" in file_name or "@controller" in decorators_str or "controller" in decorators_str:
                kinds.append("controller")
            if "service" in file_name or "@injectable" in decorators_str or "injectable" in decorators_str:
                kinds.append("service")
            if "module" in file_name or "@module" in decorators_str or "module" in decorators_str:
                kinds.append("module")
        
        if "spring-boot" in frameworks:
            if "controller" in file_name or "restcontroller" in decorators_str or "@restcontroller" in decorators_str:
                kinds.append("controller")
            if "service" in file_name or "@service" in decorators_str or "service" in decorators_str:
                kinds.append("service")
            if "repository" in file_name or "@repository" in decorators_str or "repository" in decorators_str:
                kinds.append("repository")
        
        if any(f.startswith("aspnet") for f in frameworks):
            if "controller" in file_name or "controller" in decorators_str:
                kinds.append("controller")
        
        # Django detection
        if "django" in frameworks:
            if "views" in path_lower or "view" in file_name:
                kinds.append("controller")
            if "models" in path_lower or "model" in file_name:
                kinds.append("entity")
            if "urls" in file_name:
                kinds.append("route")
        
        # Flask detection
        if "flask" in frameworks:
            if "@app.route" in str(definitions) or "blueprint" in decorators_str:
                kinds.append("controller")
        
        # Rails detection
        if "rails" in frameworks:
            if "controller" in file_name:
                kinds.append("controller")
            if "model" in file_name:
                kinds.append("entity")
            if "helper" in file_name:
                kinds.append("util")
        
        # React detection
        if "react" in frameworks:
            if "component" in file_name or "jsx" in file_path.lower():
                kinds.append("component")
        
        # Vue detection
        if "vue" in frameworks:
            if "component" in file_name or "vue" in file_path.lower():
                kinds.append("component")
        
        # Generic patterns
        if "test" in file_name or "spec" in file_name:
            kinds.append("test")
        
        if "util" in file_name or "helper" in file_name:
            kinds.append("util")
        
        if "entity" in file_name or "model" in file_name:
            kinds.append("entity")
        
        if "component" in file_name:
            kinds.append("component")
        
        return kinds if kinds else []
    
    def _extract_code_snippets(self, file_path: str, source: str) -> Dict[str, Any]:
        """
        Extract code snippets for LLM context from a file.
        
        Extracts:
        - Imports (first 20 lines)
        - Component decorator if present
        - Class/function signature
        - Common methods (first 5)
        
        Each snippet is limited to 200 characters.
        
        Args:
            file_path: Path to the file
            source: Source code string
            
        Returns:
            Dictionary with code snippets
        """
        snippets: Dict[str, Any] = {
            "imports": "",
            "componentDecorator": "",
            "classSignature": "",
            "commonMethods": []
        }
        
        if not source:
            return snippets
        
        lines = source.split('\n')
        
        # Extract imports (first 20 lines)
        import_lines = []
        for i, line in enumerate(lines[:20]):
            line_stripped = line.strip()
            if line_stripped.startswith('import ') or line_stripped.startswith('from '):
                import_lines.append(line)
        
        imports_text = '\n'.join(import_lines)
        if len(imports_text) > 200:
            snippets["imports"] = imports_text[:197] + "..."
        else:
            snippets["imports"] = imports_text
        
        # Parse AST to extract decorator and class signature
        from code_parser.multi_parser import parse_source, detect_language
        from code_parser.normalizer import get_text
        
        language = detect_language(file_path)
        if language:
            root = parse_source(source, language)
            if root:
                def walk(node):
                    yield node
                    for child in node.children:
                        yield from walk(child)
                
                # Extract component decorator
                for node in walk(root):
                    if node.type == "decorator":
                        decorator_text = get_text(node, source)
                        if decorator_text:
                            decorator_lower = decorator_text.lower()
                            if '@component' in decorator_lower or '@ngmodule' in decorator_lower:
                                if len(decorator_text) > 200:
                                    snippets["componentDecorator"] = decorator_text[:197] + "..."
                                else:
                                    snippets["componentDecorator"] = decorator_text
                                break
                
                # Extract class/function signature
                for node in walk(root):
                    if node.type == "class_declaration":
                        class_name_node = node.child_by_field_name("name")
                        if class_name_node:
                            class_name = get_text(class_name_node, source)
                            # Get modifiers (export, etc.)
                            modifiers = []
                            for child in node.children:
                                if child.type in ("export", "abstract", "public", "private", "protected"):
                                    modifiers.append(get_text(child, source))
                            
                            # Get implements/extends
                            implements_node = node.child_by_field_name("superclass")
                            extends_text = ""
                            if implements_node:
                                extends_text = f" extends {get_text(implements_node, source)}"
                            
                            signature = f"{' '.join(modifiers)} class {class_name}{extends_text}"
                            if len(signature) > 200:
                                snippets["classSignature"] = signature[:197] + "..."
                            else:
                                snippets["classSignature"] = signature
                            break
                    
                    elif node.type == "function_declaration":
                        func_name_node = node.child_by_field_name("name")
                        if func_name_node:
                            func_name = get_text(func_name_node, source)
                            params_node = node.child_by_field_name("parameters")
                            params = get_text(params_node, source) if params_node else "()"
                            
                            # Check for export
                            is_exported = any(child.type == "export" for child in node.children)
                            signature = f"{'export ' if is_exported else ''}function {func_name}{params}"
                            if len(signature) > 200:
                                snippets["classSignature"] = signature[:197] + "..."
                            else:
                                snippets["classSignature"] = signature
                            break
                
                # Extract first 5 method signatures
                method_count = 0
                for node in walk(root):
                    if method_count >= 5:
                        break
                    
                    if node.type == "method_definition":
                        method_name_node = node.child_by_field_name("name")
                        if method_name_node:
                            method_name = get_text(method_name_node, source)
                            params_node = node.child_by_field_name("parameters")
                            params = get_text(params_node, source) if params_node else "()"
                            
                            # Try to get return type
                            return_type = ""
                            for child in node.children:
                                if child.type in ("type_annotation", "return_type"):
                                    return_type_text = get_text(child, source)
                                    if return_type_text:
                                        return_type = f": {return_type_text}"
                                        break
                            
                            method_sig = f"{method_name}{params}{return_type}"
                            if len(method_sig) > 200:
                                method_sig = method_sig[:197] + "..."
                            snippets["commonMethods"].append(method_sig)
                            method_count += 1
                    
                    elif node.type == "function_declaration" and method_count < 5:
                        # Include standalone functions as methods
                        func_name_node = node.child_by_field_name("name")
                        if func_name_node:
                            func_name = get_text(func_name_node, source)
                            params_node = node.child_by_field_name("parameters")
                            params = get_text(params_node, source) if params_node else "()"
                            
                            method_sig = f"{func_name}{params}"
                            if len(method_sig) > 200:
                                method_sig = method_sig[:197] + "..."
                            snippets["commonMethods"].append(method_sig)
                            method_count += 1
        
        return snippets
    
    def _build_modules(self) -> List[Dict[str, Any]]:
        """Build modules array from parsed files."""
        modules = []
        files = collect_files(self.repo_path)
        self.frameworks = detect_frameworks(self.repo_path)
        
        for file_path in files:
            try:
                language = detect_language(file_path)
                if not language:
                    continue
                
                module_id = self._generate_module_id(file_path)
                rel_path = os.path.relpath(file_path, self.repo_path).replace(os.sep, '/')
                
                # Parse file
                try:
                    definitions = extract_definitions(file_path)
                    if not definitions:
                        self._collect_warning("no_definitions", file_path, "No definitions extracted from file")
                        continue
                except ParseError as e:
                    self._collect_error("parse_error", file_path, str(e), traceback.format_exc())
                    continue
                except Exception as e:
                    self._collect_error("parse_error", file_path, f"Unexpected error during parsing: {e}", traceback.format_exc())
                    continue
                
                # Calculate hash and LOC
                file_hash = self._calculate_file_hash(file_path)
                loc = self._count_lines_of_code(file_path)
                
                # Detect module kind
                kinds = self._detect_module_kind(file_path, definitions, self.frameworks)
                
                # Extract imports (store raw for now, will be resolved later)
                raw_imports = []
                if "imports" in definitions:
                    raw_imports = definitions["imports"]
                
                # Read source for framework detection and other extractions
                try:
                    source = self._read_file_with_retry(file_path)
                except Exception:
                    source = ""
                
                # Detect module-level framework
                from code_parser.multi_parser import detect_module_framework
                framework, framework_confidence = detect_module_framework(file_path, source)
                
                # Extract code snippets
                code_snippets = self._extract_code_snippets(file_path, source)
                
                # Extract UI patterns (for template files)
                from code_parser.multi_parser import extract_ui_patterns
                ext = os.path.splitext(file_path)[1].lower()
                ui_elements = {}
                if ext in ('.html', '.tsx', '.jsx', '.vue'):
                    ui_elements = extract_ui_patterns(file_path, source)
                else:
                    # Check for associated template file
                    file_dir = os.path.dirname(file_path)
                    file_base = os.path.splitext(os.path.basename(file_path))[0]
                    template_extensions = ['.html', '.tsx', '.jsx']
                    for template_ext in template_extensions:
                        template_path = os.path.join(file_dir, f"{file_base}{template_ext}")
                        if os.path.exists(template_path):
                            try:
                                template_source = self._read_file_with_retry(template_path)
                                ui_elements = extract_ui_patterns(template_path, template_source)
                            except Exception:
                                pass
                            break
                
                # Analyze file structure
                from code_parser.multi_parser import analyze_file_structure
                file_structure = analyze_file_structure(file_path, source)
                
                # Get code patterns from definitions (already extracted)
                code_patterns = definitions.get("codePatterns", {})
                
                # Build module object
                module = {
                    "id": module_id,
                    "path": rel_path,
                    "kind": kinds,
                    "loc": loc,
                    "hash": file_hash,
                    "exports": [],  # Will be populated with symbol IDs
                    "imports": [],  # Will be resolved to module IDs in relationship extraction
                    "definitions": definitions,  # Store for later processing
                    "file_path": file_path,  # Store for endpoint extraction
                    "raw_imports": raw_imports,  # Store raw imports for resolution
                    "framework": framework,
                    "frameworkConfidence": framework_confidence,
                    "codePatterns": code_patterns,
                    "codeSnippets": code_snippets,
                    "uiElements": ui_elements,
                    "fileStructure": file_structure
                }
                
                modules.append(module)
            except Exception as e:
                self._collect_error("module_build_error", file_path, f"Unexpected error building module: {e}", traceback.format_exc())
                continue
        
        return modules
    
    def _build_symbols(self, modules: List[Dict[str, Any]], fan_stats: Dict[str, tuple]) -> List[Dict[str, Any]]:
        """Build symbols array from module definitions."""
        symbols = []
        
        for module in modules:
            module_id = module["id"]
            definitions = module.get("definitions", {})
            file_path = module.get("file_path", "")
            
            # Check fan-in threshold
            fan_in, _ = fan_stats.get(module_id, (0, 0))
            include_details = fan_in >= self.fan_threshold
            
            # Extract functions
            functions = definitions.get("functions", [])
            for func in functions:
                func_name = func.get("name")
                if not func_name:
                    continue
                
                symbol_id = self._generate_symbol_id(module_id, func_name)
                
                # Build signature
                params = func.get("parameters", "")
                signature = f"{func_name}({params})"
                
                # Extract enhanced information
                return_type = func.get("return_type", "")
                is_async = func.get("is_async", False)
                decorators = func.get("decorators", [])
                visibility = func.get("visibility", "public")
                parameters = func.get("parameters_list", [])  # Enhanced parameter list
                
                # Build full signature
                if return_type:
                    signature = f"{func_name}({params}) -> {return_type}"
                else:
                    signature = f"{func_name}({params})"
                
                symbol = {
                    "id": symbol_id,
                    "moduleId": module_id,
                    "name": func_name,
                    "kind": "function",
                    "isExported": func.get("is_exported", True),
                    "signature": signature,
                    "visibility": visibility,
                }
                
                # Add enhanced fields
                if is_async:
                    symbol["isAsync"] = True
                if decorators:
                    symbol["decorators"] = decorators
                if parameters:
                    symbol["parameters"] = parameters
                if return_type:
                    symbol["returnType"] = return_type
                if func.get("generic_params"):
                    symbol["genericParams"] = func.get("generic_params")
                
                # Always include summary if available (not just for high fan-in)
                docstring = func.get("docstring", "")
                if docstring:
                    symbol["summary"] = docstring
                
                symbols.append(symbol)
                # Add to module exports
                module["exports"].append(symbol_id)
            
            # Extract classes
            classes = definitions.get("classes", [])
            for cls in classes:
                cls_name = cls.get("name")
                if not cls_name:
                    continue
                
                symbol_id = self._generate_symbol_id(module_id, cls_name)
                
                symbol = {
                    "id": symbol_id,
                    "moduleId": module_id,
                    "name": cls_name,
                    "kind": "class",
                    "isExported": True,
                    "signature": cls_name,
                    "visibility": "public",
                }
                
                if include_details:
                    symbol["summary"] = cls.get("docstring", "")
                
                symbols.append(symbol)
                module["exports"].append(symbol_id)
                
                # Extract methods
                methods = cls.get("methods", [])
                for method in methods:
                    # Handle both string and dict formats
                    if isinstance(method, dict):
                        method_name = method.get("name")
                    else:
                        method_name = method
                    
                    if isinstance(method_name, str):
                        method_symbol_id = self._generate_symbol_id(module_id, f"{cls_name}.{method_name}")
                        
                        # Extract enhanced method information
                        method_params = method.get("parameters", "") if isinstance(method, dict) else ""
                        method_return_type = method.get("return_type", "") if isinstance(method, dict) else ""
                        method_is_async = method.get("is_async", False) if isinstance(method, dict) else False
                        method_decorators = method.get("decorators", []) if isinstance(method, dict) else []
                        method_visibility = method.get("visibility", "public") if isinstance(method, dict) else "public"
                        
                        # Build signature
                        if method_return_type:
                            method_signature = f"{method_name}({method_params}) -> {method_return_type}"
                        else:
                            method_signature = f"{method_name}({method_params})"
                        
                        method_symbol = {
                            "id": method_symbol_id,
                            "moduleId": module_id,
                            "name": f"{cls_name}.{method_name}",
                            "kind": "method",
                            "isExported": method.get("is_exported", False) if isinstance(method, dict) else False,
                            "signature": method_signature,
                            "visibility": method_visibility,
                        }
                        
                        # Add enhanced fields
                        if method_is_async:
                            method_symbol["isAsync"] = True
                        if method_decorators:
                            method_symbol["decorators"] = method_decorators
                        if isinstance(method, dict) and method.get("parameters_list"):
                            method_symbol["parameters"] = method.get("parameters_list")
                        if method_return_type:
                            method_symbol["returnType"] = method_return_type
                        if isinstance(method, dict) and method.get("docstring"):
                            method_symbol["summary"] = method.get("docstring")
                        
                        symbols.append(method_symbol)
            
            # Extract interfaces (Java, C#, TypeScript)
            interfaces = definitions.get("interfaces", [])
            for interface in interfaces:
                interface_name = interface.get("name")
                if not interface_name:
                    continue
                
                symbol_id = self._generate_symbol_id(module_id, interface_name)
                
                symbol = {
                    "id": symbol_id,
                    "moduleId": module_id,
                    "name": interface_name,
                    "kind": "interface",
                    "isExported": True,
                    "signature": interface_name,
                    "visibility": "public",
                }
                
                symbols.append(symbol)
                module["exports"].append(symbol_id)
        
        return symbols
    
    def _build_endpoints(self, modules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build endpoints array from modules."""
        endpoints = []
        
        for module in modules:
            module_id = module["id"]
            file_path = module.get("file_path")
            
            if not file_path:
                continue
            
            try:
                source = self._read_file_with_retry(file_path)
                module_endpoints = extract_endpoints(file_path, source, module_id, self.frameworks)
                endpoints.extend(module_endpoints)
            except FileNotFoundError as e:
                self._collect_error("file_not_found", file_path, str(e))
                continue
            except (IOError, OSError) as e:
                self._collect_error("io_error", file_path, f"Failed to read file: {e}")
                continue
            except Exception as e:
                self._collect_error("endpoint_extraction_error", file_path, f"Unexpected error: {e}", traceback.format_exc())
                continue
        
        return endpoints
    
    def _build_framework_patterns_library(self, modules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build framework patterns library by extracting templates from actual codebase files.
        
        Analyzes actual files in the codebase to extract component templates, service templates,
        routing patterns, and button patterns for each detected framework.
        
        Args:
            modules: List of module dictionaries
            
        Returns:
            Dictionary with framework patterns organized by framework name
        """
        framework_patterns: Dict[str, Any] = {}
        
        if not self.frameworks:
            return framework_patterns
        
        # Group modules by framework
        modules_by_framework: Dict[str, List[Dict[str, Any]]] = {}
        for module in modules:
            framework = module.get("framework")
            if framework:
                if framework not in modules_by_framework:
                    modules_by_framework[framework] = []
                modules_by_framework[framework].append(module)
        
        # Extract patterns for each framework
        for framework in self.frameworks:
            framework_modules = modules_by_framework.get(framework, [])
            if not framework_modules:
                continue
            
            patterns: Dict[str, str] = {}
            
            # Find component files
            component_files = [m for m in framework_modules if "component" in m.get("kind", [])]
            if component_files:
                # Extract component template from first component
                component_file = component_files[0]
                file_path = component_file.get("file_path")
                if file_path and os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            # Extract class/component definition (first 50 lines or until closing brace)
                            lines = content.split('\n')
                            component_lines = []
                            brace_count = 0
                            in_component = False
                            
                            for line in lines[:100]:  # Limit to first 100 lines
                                if '@component' in line.lower() or '@component' in line.lower():
                                    in_component = True
                                if in_component:
                                    component_lines.append(line)
                                    brace_count += line.count('{') - line.count('}')
                                    if brace_count <= 0 and len(component_lines) > 5:
                                        break
                            
                            if component_lines:
                                component_template = '\n'.join(component_lines)
                                if len(component_template) > 500:
                                    component_template = component_template[:497] + "..."
                                patterns["componentTemplate"] = component_template
                    except Exception:
                        pass
            
            # Find service files
            service_files = [m for m in framework_modules if "service" in m.get("kind", [])]
            if service_files:
                service_file = service_files[0]
                file_path = service_file.get("file_path")
                if file_path and os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            # Extract service class definition
                            lines = content.split('\n')
                            service_lines = []
                            brace_count = 0
                            in_service = False
                            
                            for line in lines[:80]:
                                if '@injectable' in line.lower() or 'service' in line.lower():
                                    in_service = True
                                if in_service:
                                    service_lines.append(line)
                                    brace_count += line.count('{') - line.count('}')
                                    if brace_count <= 0 and len(service_lines) > 3:
                                        break
                            
                            if service_lines:
                                service_template = '\n'.join(service_lines)
                                if len(service_template) > 500:
                                    service_template = service_template[:497] + "..."
                                patterns["serviceTemplate"] = service_template
                    except Exception:
                        pass
            
            # Find routing files
            routing_files = [
                f for f in collect_files(self.repo_path)
                if 'routing' in f.lower() or 'router' in f.lower() or 'route' in f.lower()
            ]
            if routing_files:
                routing_file = routing_files[0]
                try:
                    with open(routing_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        # Extract routing pattern (routes array or Route components)
                        if framework == 'angular':
                            routes_match = re.search(r'const\s+routes:\s*Routes\s*=\s*\[[^\]]+\]', content, re.DOTALL)
                            if routes_match:
                                routes_text = routes_match.group(0)
                                if len(routes_text) > 500:
                                    routes_text = routes_text[:497] + "..."
                                patterns["routingPattern"] = routes_text
                        elif framework == 'react':
                            route_match = re.search(r'<Route[^>]*path[^>]*>', content)
                            if route_match:
                                route_text = route_match.group(0)
                                patterns["routingPattern"] = route_text
                except Exception:
                    pass
            
            # Extract button pattern from UI elements
            for module in framework_modules[:5]:  # Check first 5 modules
                ui_elements = module.get("uiElements", {})
                buttons = ui_elements.get("buttons", [])
                if buttons:
                    button = buttons[0]
                    patterns["buttonPattern"] = button.get("pattern", "")
                    break
            
            if patterns:
                framework_patterns[framework] = patterns
        
        return framework_patterns
    
    def _build_features(self, modules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build features array from folder hierarchy."""
        if not self.include_features:
            return []
        
        features = []
        feature_map = {}
        
        for module in modules:
            path = module.get("path", "")
            path_parts = path.split('/')[:-1]  # Exclude filename
            
            # Build feature hierarchy
            current_path = ""
            for part in path_parts:
                if not part:
                    continue
                
                current_path = os.path.join(current_path, part) if current_path else part
                feature_id = self._generate_feature_id(
                    os.path.join(self.repo_path, current_path)
                )
                
                if feature_id not in feature_map:
                    feature = {
                        "id": feature_id,
                        "name": part,
                        "path": current_path.replace(os.sep, '/'),
                        "moduleIds": []
                    }
                    feature_map[feature_id] = feature
                    features.append(feature)
                
                feature_map[feature_id]["moduleIds"].append(module["id"])
        
        return features
    
    def generate_pkg(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate complete PKG JSON.
        
        Args:
            output_path: Optional path to save JSON file
            
        Returns:
            Complete PKG dictionary
        """
        logger = get_logger(__name__)
        
        log_with_context(logger, logging.INFO, "Starting PKG generation", repo_path=self.repo_path)
        
        # Extract project metadata
        log_with_context(logger, logging.INFO, "Extracting project metadata", repo_path=self.repo_path)
        project_meta = extract_project_metadata(self.repo_path)
        project_id = project_meta.get("id", "unknown")
        log_with_context(logger, logging.INFO, f"Project metadata extracted | Project ID: {project_id} | Name: {project_meta.get('name', 'N/A')} | Languages: {project_meta.get('languages', [])}", repo_path=self.repo_path)
        
        # Build modules
        log_with_context(logger, logging.INFO, "Building modules", repo_path=self.repo_path)
        self.modules = self._build_modules()
        log_with_context(logger, logging.INFO, "Modules built", repo_path=self.repo_path, count=len(self.modules))
        
        # Build symbols (need fan stats, so do a first pass)
        # For now, build symbols without fan filtering, then recalculate
        log_with_context(logger, logging.INFO, "Building symbols (first pass)", repo_path=self.repo_path)
        temp_symbols = self._build_symbols(self.modules, {})
        self.symbols = temp_symbols
        log_with_context(logger, logging.INFO, "Symbols built (first pass)", repo_path=self.repo_path, count=len(self.symbols))
        
        # Build endpoints
        log_with_context(logger, logging.INFO, "Building endpoints", repo_path=self.repo_path)
        self.endpoints = self._build_endpoints(self.modules)
        log_with_context(logger, logging.INFO, "Endpoints built", repo_path=self.repo_path, count=len(self.endpoints))
        
        # Extract relationships
        log_with_context(logger, logging.INFO, "Extracting relationships", repo_path=self.repo_path)
        self.edges, fan_stats = extract_relationships(
            self.modules, self.symbols, self.endpoints, self.repo_path
        )
        log_with_context(logger, logging.INFO, "Relationships extracted", repo_path=self.repo_path, count=len(self.edges))
        
        # Populate module imports from edges
        log_with_context(logger, logging.DEBUG, "Populating module imports", repo_path=self.repo_path)
        for edge in self.edges:
            if edge.get("type") == "imports":
                from_id = edge.get("from")
                to_id = edge.get("to")
                for module in self.modules:
                    if module["id"] == from_id:
                        if to_id not in module["imports"]:
                            module["imports"].append(to_id)
        
        # Rebuild symbols with fan filtering
        log_with_context(logger, logging.INFO, f"Rebuilding symbols (with fan filtering) | Fan threshold: {self.fan_threshold}", repo_path=self.repo_path)
        self.symbols = self._build_symbols(self.modules, fan_stats)
        log_with_context(logger, logging.INFO, "Symbols rebuilt", repo_path=self.repo_path, count=len(self.symbols))
        
        # Build features
        if self.include_features:
            log_with_context(logger, logging.INFO, "Building features", repo_path=self.repo_path)
            self.features = self._build_features(self.modules)
            log_with_context(logger, logging.INFO, "Features built", repo_path=self.repo_path, count=len(self.features))
        else:
            self.features = []
            log_with_context(logger, logging.INFO, "Skipping features | include_features=False", repo_path=self.repo_path)
        
        # Build framework patterns library
        log_with_context(logger, logging.INFO, "Building framework patterns library", repo_path=self.repo_path)
        framework_patterns = self._build_framework_patterns_library(self.modules)
        log_with_context(logger, logging.INFO, "Framework patterns built", repo_path=self.repo_path, count=len(framework_patterns))
        
        # Extract project-level UI patterns and code style
        log_with_context(logger, logging.INFO, "Extracting project-level UI patterns and code style", repo_path=self.repo_path)
        from code_parser.project_metadata import extract_project_ui_patterns, extract_code_style
        
        project_ui_patterns = extract_project_ui_patterns(self.modules, self.repo_path)
        code_style = extract_code_style(self.repo_path)
        
        # Clean up module definitions (remove file_path, keep only needed fields)
        log_with_context(logger, logging.DEBUG, "Cleaning up module data", repo_path=self.repo_path)
        for module in self.modules:
            module.pop("definitions", None)
            module.pop("file_path", None)
            # Add moduleSummary if available
            if "moduleSummary" not in module:
                module["moduleSummary"] = None
        
        # Build final PKG
        log_with_context(logger, logging.INFO, "Building final PKG structure", repo_path=self.repo_path)
        
        # Merge project metadata with new fields
        project_data = {
            "id": project_meta.get("id", ""),
            "name": project_meta.get("name", ""),
            "rootPath": project_meta.get("rootPath", ""),
            "languages": project_meta.get("languages", []),
            "frameworks": project_meta.get("frameworks", []),
            "metadata": project_meta.get("metadata", {}),
            "codeStyle": code_style
        }
        
        # Add UI patterns if available
        if project_ui_patterns:
            project_data.update(project_ui_patterns)
        
        pkg = {
            "version": "1.0.0",
            "generatedAt": datetime.utcnow().isoformat() + "Z",
            "gitSha": project_meta.get("gitSha"),
            "project": project_data,
            "modules": self.modules,
            "symbols": self.symbols,
            "endpoints": self.endpoints,
            "edges": self.edges,
        }
        
        # Add framework patterns if available
        if framework_patterns:
            pkg["frameworkPatterns"] = framework_patterns
        
        if self.features:
            pkg["features"] = self.features
        
        # Add error and warning metadata
        if self.errors or self.warnings:
            if "metadata" not in pkg["project"]:
                pkg["project"]["metadata"] = {}
            pkg["project"]["metadata"]["errors"] = self.errors
            pkg["project"]["metadata"]["error_count"] = len(self.errors)
            pkg["project"]["metadata"]["warnings"] = self.warnings
            pkg["project"]["metadata"]["warning_count"] = len(self.warnings)
        
        # Validate PKG before returning
        from utils.schema_validator import validate_pkg
        is_valid, validation_errors = validate_pkg(pkg)
        
        if not is_valid:
            error_msg = f"PKG validation failed: {'; '.join(validation_errors)}"
            log_with_context(logger, logging.ERROR, error_msg, repo_path=self.repo_path)
            from code_parser.exceptions import ValidationError
            raise ValidationError(error_msg, errors=validation_errors)
        
        if validation_errors:
            log_with_context(logger, logging.WARNING, f"PKG validation warnings: {'; '.join(validation_errors)}", repo_path=self.repo_path)
        
        # Save if output path provided
        if output_path:
            log_with_context(logger, logging.INFO, f"Saving PKG to file | Path: {output_path}", repo_path=self.repo_path)
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(pkg, f, indent=2)
            log_with_context(logger, logging.INFO, f"PKG saved to file | Path: {output_path}", repo_path=self.repo_path)
        
        log_with_context(logger, logging.INFO, f"Storing PKG to Neo4j | Project ID: {project_id}", repo_path=self.repo_path)
        neo4j_database.store_pkg(pkg)
        log_with_context(logger, logging.INFO, f"PKG stored to Neo4j | Project ID: {project_id}", repo_path=self.repo_path)

        log_with_context(logger, logging.INFO, f"PKG generation complete | Project ID: {project_id} | Modules: {len(self.modules)} | Symbols: {len(self.symbols)} | Edges: {len(self.edges)} | Endpoints: {len(self.endpoints)}", repo_path=self.repo_path)
        return pkg
    
    def _identify_affected_modules(self, changed_files: List[str], edges: List[Dict[str, Any]]) -> Set[str]:
        """
        Identify modules affected by changes (modules that import changed modules or are imported by changed modules).
        
        Args:
            changed_files: List of changed file paths (relative to repo root)
            edges: List of edge dictionaries
            
        Returns:
            Set of affected module IDs
        """
        # Convert changed files to module IDs
        changed_module_ids = set()
        for file_path in changed_files:
            abs_path = os.path.join(self.repo_path, file_path)
            module_id = self._generate_module_id(abs_path)
            changed_module_ids.add(module_id)
        
        affected_module_ids = set(changed_module_ids)
        
        # Find modules that import changed modules
        for edge in edges:
            if edge.get("type") == "imports":
                from_id = edge.get("from")
                to_id = edge.get("to")
                if to_id in changed_module_ids:
                    affected_module_ids.add(from_id)
                if from_id in changed_module_ids:
                    affected_module_ids.add(to_id)
        
        return affected_module_ids
    
    def generate_pkg_incremental(
        self,
        changed_files: List[str],
        base_pkg: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate PKG incrementally by re-parsing only changed files.
        
        Args:
            changed_files: List of changed file paths (relative to repo root)
            base_pkg: Previous PKG version
            output_path: Optional path to save JSON file
            
        Returns:
            Updated PKG dictionary
        """
        logger = get_logger(__name__)
        import logging
        
        log_with_context(logger, logging.INFO, f"Starting incremental PKG generation | Changed files: {len(changed_files)}", repo_path=self.repo_path)
        
        # Extract project metadata
        project_meta = extract_project_metadata(self.repo_path)
        project_id = project_meta.get("id", "unknown")
        
        # Identify changed module IDs
        changed_module_ids = set()
        for file_path in changed_files:
            abs_path = os.path.join(self.repo_path, file_path)
            module_id = self._generate_module_id(abs_path)
            changed_module_ids.add(module_id)
        
        # Identify affected modules
        base_edges = base_pkg.get("edges", [])
        affected_module_ids = self._identify_affected_modules(changed_files, base_edges)
        log_with_context(logger, logging.INFO, f"Affected modules: {len(affected_module_ids)}", repo_path=self.repo_path, count=len(affected_module_ids))
        
        # Preserve unchanged modules
        base_modules = {m["id"]: m for m in base_pkg.get("modules", [])}
        base_symbols = {s["id"]: s for s in base_pkg.get("symbols", [])}
        base_endpoints = {e["id"]: e for e in base_pkg.get("endpoints", [])}
        
        # Re-parse changed files
        updated_modules = []
        for file_path in changed_files:
            abs_path = os.path.join(self.repo_path, file_path)
            if not os.path.exists(abs_path):
                # File was deleted, skip
                continue
            
            try:
                language = detect_language(abs_path)
                if not language:
                    continue
                
                module_id = self._generate_module_id(abs_path)
                rel_path = os.path.relpath(abs_path, self.repo_path).replace(os.sep, '/')
                
                # Parse file
                try:
                    definitions = extract_definitions(abs_path)
                    if not definitions:
                        continue
                except ParseError as e:
                    self._collect_error("parse_error", abs_path, str(e), traceback.format_exc())
                    continue
                
                # Calculate hash and LOC
                file_hash = self._calculate_file_hash(abs_path)
                loc = self._count_lines_of_code(abs_path)
                
                # Detect module kind
                kinds = self._detect_module_kind(abs_path, definitions, self.frameworks)
                
                # Extract imports
                raw_imports = []
                if "imports" in definitions:
                    raw_imports = definitions["imports"]
                
                # Build module object
                module = {
                    "id": module_id,
                    "path": rel_path,
                    "kind": kinds,
                    "loc": loc,
                    "hash": file_hash,
                    "exports": [],
                    "imports": [],
                    "definitions": definitions,
                    "file_path": abs_path,
                    "raw_imports": raw_imports
                }
                
                updated_modules.append(module)
            
            except Exception as e:
                self._collect_error("incremental_parse_error", abs_path, f"Unexpected error: {e}", traceback.format_exc())
                continue
        
        # Update modules list (replace changed, keep unchanged)
        final_modules = []
        for module_id, module in base_modules.items():
            if module_id not in changed_module_ids:
                final_modules.append(module)
        
        final_modules.extend(updated_modules)
        self.modules = final_modules
        
        # Re-extract symbols for changed modules
        updated_symbols = []
        for module in updated_modules:
            module_id = module["id"]
            definitions = module.get("definitions", {})
            
            # Extract symbols (simplified - full extraction would use _build_symbols)
            functions = definitions.get("functions", [])
            for func in functions:
                func_name = func.get("name")
                if func_name:
                    symbol_id = self._generate_symbol_id(module_id, func_name)
                    if symbol_id in base_symbols:
                        # Update existing symbol
                        symbol = base_symbols[symbol_id].copy()
                        # Update fields as needed
                        updated_symbols.append(symbol)
                    else:
                        # New symbol
                        symbol = {
                            "id": symbol_id,
                            "moduleId": module_id,
                            "name": func_name,
                            "kind": "function",
                            "isExported": True,
                            "signature": f"{func_name}({func.get('parameters', '')})",
                            "visibility": "public"
                        }
                        updated_symbols.append(symbol)
        
        # Remove symbols from changed modules, add updated ones
        final_symbols = []
        for symbol_id, symbol in base_symbols.items():
            module_id = symbol.get("moduleId")
            if module_id not in changed_module_ids:
                final_symbols.append(symbol)
        
        final_symbols.extend(updated_symbols)
        self.symbols = final_symbols
        
        # Re-extract relationships for affected modules
        affected_modules_list = [m for m in self.modules if m["id"] in affected_module_ids]
        self.edges, fan_stats = extract_relationships(
            self.modules, self.symbols, self.endpoints, self.repo_path
        )
        
        # Recalculate fan-in/fan-out for affected modules
        # (fan_stats already calculated above)
        
        # Update git SHA and timestamp
        updated_pkg = base_pkg.copy()
        updated_pkg["generatedAt"] = datetime.utcnow().isoformat() + "Z"
        updated_pkg["gitSha"] = project_meta.get("gitSha")
        updated_pkg["modules"] = self.modules
        updated_pkg["symbols"] = self.symbols
        updated_pkg["edges"] = self.edges
        
        # Validate updated PKG
        from utils.schema_validator import validate_pkg
        is_valid, validation_errors = validate_pkg(updated_pkg)
        
        if not is_valid:
            error_msg = f"Incremental PKG validation failed: {'; '.join(validation_errors)}"
            log_with_context(logger, logging.ERROR, error_msg, repo_path=self.repo_path)
            from code_parser.exceptions import ValidationError
            raise ValidationError(error_msg, errors=validation_errors)
        
        # Save if output path provided
        if output_path:
            log_with_context(logger, logging.INFO, f"Saving incremental PKG to file | Path: {output_path}", repo_path=self.repo_path)
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(updated_pkg, f, indent=2)
        
        log_with_context(logger, logging.INFO, f"Incremental PKG generation complete | Modules: {len(self.modules)} | Symbols: {len(self.symbols)} | Edges: {len(self.edges)}", repo_path=self.repo_path)
        return updated_pkg        


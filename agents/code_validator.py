"""Code Validator - Validates generated code before applying."""

import ast
import logging
import os
import subprocess
import re
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


class CodeValidator:
    """Validates code changes before applying."""
    
    def __init__(self, repo_path: str):
        """
        Initialize code validator.
        
        Args:
            repo_path: Path to repository
        """
        self.repo_path = repo_path
    
    def validate_syntax(self, file_path: str, content: str) -> Tuple[bool, str]:
        """
        Validate syntax for Python/TypeScript/JavaScript.
        
        Args:
            file_path: Path to file
            content: File content to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.py':
            return self._validate_python_syntax(content)
        elif file_ext in ['.ts', '.tsx']:
            return self._validate_typescript_syntax(file_path, content)
        elif file_ext in ['.js', '.jsx']:
            return self._validate_javascript_syntax(file_path, content)
        else:
            # Unknown file type, skip validation
            logger.debug(f"Unknown file type for validation: {file_ext}")
            return True, ""
    
    def _validate_python_syntax(self, content: str) -> Tuple[bool, str]:
        """Validate Python syntax using ast.parse()."""
        try:
            ast.parse(content)
            return True, ""
        except SyntaxError as e:
            error_msg = f"Syntax error at line {e.lineno}: {e.msg}"
            if e.text:
                error_msg += f" - {e.text.strip()}"
            return False, error_msg
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def _validate_typescript_syntax(self, file_path: str, content: str) -> Tuple[bool, str]:
        """Validate TypeScript syntax using tsc if available."""
        try:
            # Check if tsc is available
            result = subprocess.run(
                ['tsc', '--version'],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                # tsc not available, skip validation
                logger.debug("TypeScript compiler not available, skipping validation")
                return True, ""
            
            # Write content to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', delete=False) as f:
                f.write(content)
                temp_path = f.name
            
            try:
                # Run tsc --noEmit
                result = subprocess.run(
                    ['tsc', '--noEmit', temp_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=self.repo_path
                )
                
                if result.returncode == 0:
                    return True, ""
                else:
                    # Extract error message
                    error_lines = result.stderr.split('\n')[:5]  # Limit to first 5 lines
                    error_msg = '\n'.join(error_lines)
                    return False, error_msg
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
                    
        except FileNotFoundError:
            logger.debug("TypeScript compiler not found, skipping validation")
            return True, ""
        except subprocess.TimeoutExpired:
            logger.warning("TypeScript validation timed out")
            return True, ""  # Don't block on timeout
        except Exception as e:
            logger.warning(f"TypeScript validation error: {e}")
            return True, ""  # Don't block on errors
    
    def _validate_javascript_syntax(self, file_path: str, content: str) -> Tuple[bool, str]:
        """Validate JavaScript syntax using node --check."""
        try:
            # Check if node is available
            result = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                # node not available, skip validation
                logger.debug("Node.js not available, skipping validation")
                return True, ""
            
            # Write content to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(content)
                temp_path = f.name
            
            try:
                # Run node --check
                result = subprocess.run(
                    ['node', '--check', temp_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    return True, ""
                else:
                    error_msg = result.stderr.strip() if result.stderr else "Syntax error"
                    return False, error_msg
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
                    
        except FileNotFoundError:
            logger.debug("Node.js not found, skipping validation")
            return True, ""
        except subprocess.TimeoutExpired:
            logger.warning("JavaScript validation timed out")
            return True, ""  # Don't block on timeout
        except Exception as e:
            logger.warning(f"JavaScript validation error: {e}")
            return True, ""  # Don't block on errors
    
    def validate_imports(self, file_path: str, content: str, pkg_data: Dict) -> Tuple[bool, List[str]]:
        """
        Validate that imports exist in PKG.
        
        Args:
            file_path: Path to file
            content: File content
            pkg_data: PKG data dictionary
            
        Returns:
            Tuple of (is_valid, missing_imports)
        """
        if not pkg_data:
            return True, []
        
        file_ext = os.path.splitext(file_path)[1].lower()
        missing_imports = []
        
        # Extract imports based on file type
        imports = self._extract_imports(content, file_ext)
        
        if not imports:
            return True, []
        
        # Get all module paths from PKG
        pkg_modules = pkg_data.get('modules', [])
        module_paths = {mod.get('path', '') for mod in pkg_modules}
        
        # Check each import
        for imp in imports:
            # Try to match import to module path
            # This is a simple check - could be enhanced
            matched = False
            
            # Direct path match
            if imp in module_paths:
                matched = True
            else:
                # Try relative path matching
                rel_path = os.path.relpath(file_path, self.repo_path) if os.path.isabs(file_path) else file_path
                base_dir = os.path.dirname(rel_path)
                
                # Try various path combinations
                possible_paths = [
                    imp,
                    os.path.join(base_dir, imp),
                    imp.replace('.', '/'),
                    imp.replace('.', '/') + '.py',
                    imp.replace('.', '/') + '.ts',
                    imp.replace('.', '/') + '.js',
                ]
                
                for possible_path in possible_paths:
                    if possible_path in module_paths:
                        matched = True
                        break
            
            if not matched:
                missing_imports.append(imp)
        
        # Don't fail validation for missing imports - just warn
        # Some imports might be external packages
        return True, missing_imports
    
    def _extract_imports(self, content: str, file_ext: str) -> List[str]:
        """Extract import statements from code."""
        imports = []
        
        if file_ext == '.py':
            # Python imports
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imports.append(node.module)
            except SyntaxError:
                # If we can't parse, try regex fallback
                import_pattern = r'^(?:from\s+(\S+)\s+)?import\s+'
                for line in content.split('\n'):
                    match = re.match(import_pattern, line.strip())
                    if match:
                        module = match.group(1) or line.split('import')[1].split()[0]
                        imports.append(module)
        
        elif file_ext in ['.ts', '.tsx', '.js', '.jsx']:
            # JavaScript/TypeScript imports
            # Match: import ... from 'module'
            import_pattern = r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]"
            matches = re.findall(import_pattern, content)
            imports.extend(matches)
            
            # Match: require('module')
            require_pattern = r"require\(['\"]([^'\"]+)['\"]\)"
            matches = re.findall(require_pattern, content)
            imports.extend(matches)
        
        return imports
    
    def validate_types(self, file_path: str, content: str) -> Tuple[bool, str]:
        """
        Validate types (if TypeScript or Python with type hints).
        
        Args:
            file_path: Path to file
            content: File content
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext in ['.ts', '.tsx']:
            # TypeScript type checking is handled in validate_syntax
            return True, ""
        elif file_ext == '.py':
            # Python type checking would require mypy or similar
            # For now, just check syntax
            return True, ""
        else:
            return True, ""
    
    def validate_all(self, file_path: str, content: str, pkg_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Run all validations.
        
        Args:
            file_path: Path to file
            content: File content
            pkg_data: Optional PKG data dictionary
            
        Returns:
            Validation result with errors/warnings
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Syntax validation
        syntax_valid, syntax_error = self.validate_syntax(file_path, content)
        if not syntax_valid:
            result["valid"] = False
            result["errors"].append(f"Syntax error: {syntax_error}")
        
        # Import validation (if PKG data available)
        if pkg_data:
            imports_valid, missing_imports = self.validate_imports(file_path, content, pkg_data)
            if missing_imports:
                result["warnings"].append(f"Potentially missing imports: {', '.join(missing_imports[:5])}")
        
        # Type validation
        types_valid, type_error = self.validate_types(file_path, content)
        if not types_valid:
            result["warnings"].append(f"Type warning: {type_error}")
        
        return result

"""AST Transformers for code editing with language-specific implementations."""

import logging
import os
import json
import subprocess
from abc import ABC, abstractmethod
from typing import Any, List, Optional, Dict

logger = logging.getLogger(__name__)


class ASTTransformer(ABC):
    """Abstract base class for AST transformers."""
    
    @abstractmethod
    def parse(self, content: str) -> Any:
        """
        Parse code content to AST.
        
        Args:
            content: Source code string
            
        Returns:
            AST representation (language-specific)
        """
        pass
    
    @abstractmethod
    def apply_edit(self, tree: Any, edit_instructions: List[str]) -> Any:
        """
        Apply edit instructions to AST.
        
        Args:
            tree: AST representation
            edit_instructions: List of change descriptions
            
        Returns:
            Modified AST
        """
        pass
    
    @abstractmethod
    def generate_code(self, tree: Any) -> str:
        """
        Generate code from AST.
        
        Args:
            tree: AST representation
            
        Returns:
            Generated source code string
        """
        pass


class PythonASTTransformer(ASTTransformer):
    """AST transformer for Python using libCST."""
    
    def __init__(self):
        """Initialize Python AST transformer."""
        try:
            import libcst as cst
            self.cst = cst
            self._available = True
        except ImportError:
            logger.warning("libcst not available, Python AST editing disabled")
            self._available = False
    
    def parse(self, content: str) -> Any:
        """Parse Python code using libCST."""
        if not self._available:
            raise RuntimeError("libcst not available")
        
        try:
            return self.cst.parse_module(content)
        except Exception as e:
            logger.error(f"Failed to parse Python code: {e}")
            raise
    
    def apply_edit(self, tree: Any, edit_instructions: List[str]) -> Any:
        """Apply edit instructions to Python AST."""
        if not self._available:
            raise RuntimeError("libcst not available")
        
        try:
            # Create a transformer visitor
            transformer = _PythonEditTransformer(edit_instructions, self.cst)
            # Use libCST's transformer pattern
            modified_tree = tree.visit(transformer)
            return modified_tree
        except Exception as e:
            logger.error(f"Failed to apply Python AST edits: {e}")
            raise
    
    def generate_code(self, tree: Any) -> str:
        """Generate Python code from AST, preserving formatting."""
        if not self._available:
            raise RuntimeError("libcst not available")
        
        try:
            # libCST preserves formatting automatically
            return tree.code
        except Exception as e:
            logger.error(f"Failed to generate Python code from AST: {e}")
            raise


class _PythonEditTransformer:
    """Internal transformer visitor for Python AST edits."""
    
    def __init__(self, edit_instructions: List[str], cst_module: Any):
        """Initialize with edit instructions and libCST module."""
        self.edit_instructions = edit_instructions
        self.cst = cst_module
        self.imports_to_add = []
        self.methods_to_add = []
        self.functions_to_modify = []
        
        # Parse edit instructions
        for instruction in edit_instructions:
            instruction_lower = instruction.lower()
            if 'add import' in instruction_lower or 'import' in instruction_lower:
                # Extract import statement
                if 'from' in instruction_lower:
                    # from X import Y
                    parts = instruction.split('from')
                    if len(parts) > 1:
                        import_part = parts[1].strip()
                        if 'import' in import_part:
                            self.imports_to_add.append(('from', import_part))
                else:
                    # import X
                    if 'import' in instruction:
                        import_name = instruction.split('import')[-1].strip()
                        if import_name:
                            self.imports_to_add.append(('import', import_name))
            elif 'add method' in instruction_lower or 'add function' in instruction_lower:
                # Extract method/function name
                parts = instruction.split()
                for i, part in enumerate(parts):
                    if part.lower() in ['method', 'function'] and i + 1 < len(parts):
                        method_name = parts[i + 1]
                        self.methods_to_add.append(method_name)
                        break
    
    def transform_Module(self, node: Any) -> Any:
        """Transform module node, adding imports if needed."""
        if not self.imports_to_add:
            return node
        
        # Get existing imports
        existing_imports = []
        new_body = []
        
        for item in node.body:
            if isinstance(item, (self.cst.Import, self.cst.ImportFrom)):
                existing_imports.append(item)
            else:
                new_body.append(item)
        
        # Add new imports
        new_imports = []
        for import_type, import_spec in self.imports_to_add:
            try:
                if import_type == 'from':
                    # Parse "from X import Y"
                    if ' import ' in import_spec:
                        module_part, names_part = import_spec.split(' import ', 1)
                        module_name = module_part.strip()
                        import_names = [name.strip() for name in names_part.split(',')]
                        
                        # Create ImportFrom node
                        import_aliases = []
                        for name in import_names:
                            import_aliases.append(
                                self.cst.ImportAlias(name=self.cst.Name(name))
                            )
                        
                        new_imports.append(
                            self.cst.ImportFrom(
                                module=self.cst.Name(module_name),
                                names=self.cst.ImportStar() if '*' in names_part else self.cst.ImportFromTargets(import_aliases)
                            )
                        )
                else:
                    # Parse "import X"
                    module_name = import_spec.split('.')[0]
                    new_imports.append(
                        self.cst.Import(
                            names=[self.cst.ImportAlias(name=self.cst.Name(module_name))]
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to parse import instruction '{import_spec}': {e}")
        
        # Combine imports and body
        all_imports = existing_imports + new_imports
        new_body = all_imports + new_body
        
        return node.with_changes(body=new_body)


class TypeScriptASTTransformer(ASTTransformer):
    """AST transformer for TypeScript/JavaScript using ts-morph or tree-sitter."""
    
    def __init__(self, file_path: str):
        """
        Initialize TypeScript AST transformer.
        
        Args:
            file_path: Path to the file being edited (for detecting ts-morph)
        """
        self.file_path = file_path
        self.repo_path = os.path.dirname(file_path) if os.path.isfile(file_path) else file_path
        self._ts_morph_path = None  # Path to ts-morph node_modules directory
        self._use_npx = False  # Whether to use npx for ts-morph
        self._ts_morph_available = self._check_ts_morph_availability()
        self._tree_sitter_available = self._check_tree_sitter_availability()
        
        if not self._ts_morph_available and not self._tree_sitter_available:
            logger.warning("Neither ts-morph nor tree-sitter available for TypeScript editing")
    
    def _find_py_processor_root(self) -> Optional[str]:
        """Find py-processor project root by locating scripts/ts_morph_editor.js."""
        # Start from this file's location
        current = os.path.dirname(os.path.abspath(__file__))
        
        # Walk up directory tree looking for scripts/ts_morph_editor.js
        for _ in range(10):  # Limit search depth
            scripts_dir = os.path.join(current, 'scripts')
            script_path = os.path.join(scripts_dir, 'ts_morph_editor.js')
            if os.path.exists(script_path):
                return current
            parent = os.path.dirname(current)
            if parent == current:  # Reached root
                break
            current = parent
        
        return None
    
    def _check_ts_morph_availability(self) -> bool:
        """Check if ts-morph is available via Node.js.
        
        Checks in priority order:
        0. NODE_PATH from environment (.env file)
        1. py-processor project's node_modules
        2. Cloned repo's node_modules
        3. Global installation via npx
        
        Returns:
            True if ts-morph is available, False otherwise
        """
        try:
            # Check if Node.js is available
            result = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                return False
            
            # Priority 0: Check NODE_PATH from environment (highest priority)
            node_path_env = os.environ.get('NODE_PATH', '')
            if node_path_env:
                # NODE_PATH can contain multiple paths separated by : (Unix) or ; (Windows)
                node_path_separator = ';' if os.name == 'nt' else ':'
                paths = [p.strip() for p in node_path_env.split(node_path_separator) if p.strip()]
                
                for path in paths:
                    ts_morph_path = os.path.join(path, 'ts-morph')
                    if os.path.exists(ts_morph_path):
                        self._ts_morph_path = path
                        logger.info(f"Found ts-morph via NODE_PATH: {path}")
                        logger.info("ts-morph availability check complete: available=True, method=node-path-env")
                        return True
            
            # Priority 1: Check py-processor project's node_modules
            py_processor_root = self._find_py_processor_root()
            if py_processor_root:
                py_processor_node_modules = os.path.join(py_processor_root, 'node_modules', 'ts-morph')
                if os.path.exists(py_processor_node_modules):
                    # Store the parent node_modules directory for NODE_PATH
                    self._ts_morph_path = os.path.join(py_processor_root, 'node_modules')
                    logger.info(f"Found ts-morph in py-processor project: {self._ts_morph_path}")
                    logger.info("ts-morph availability check complete: available=True, method=py-processor")
                    return True
                
                # Also check package.json in py-processor root
                py_processor_package_json = os.path.join(py_processor_root, 'package.json')
                if os.path.exists(py_processor_package_json):
                    try:
                        with open(py_processor_package_json, 'r', encoding='utf-8') as f:
                            package_data = json.load(f)
                            deps = package_data.get('dependencies', {})
                            dev_deps = package_data.get('devDependencies', {})
                            if 'ts-morph' in deps or 'ts-morph' in dev_deps:
                                # If in package.json, node_modules should exist or be installable
                                if os.path.exists(py_processor_node_modules):
                                    self._ts_morph_path = os.path.join(py_processor_root, 'node_modules')
                                    logger.info(f"Found ts-morph in py-processor package.json: {self._ts_morph_path}")
                                    logger.info("ts-morph availability check complete: available=True, method=py-processor")
                                    return True
                    except Exception:
                        pass
            
            # Priority 2: Check cloned repo's node_modules
            repo_root = self._find_repo_root()
            if repo_root:
                repo_node_modules = os.path.join(repo_root, 'node_modules', 'ts-morph')
                if os.path.exists(repo_node_modules):
                    self._ts_morph_path = os.path.join(repo_root, 'node_modules')
                    logger.info(f"Found ts-morph in cloned repo: {self._ts_morph_path}")
                    logger.info("ts-morph availability check complete: available=True, method=cloned-repo")
                    return True
                
                # Check package.json
                package_json_path = os.path.join(repo_root, 'package.json')
                if os.path.exists(package_json_path):
                    try:
                        with open(package_json_path, 'r', encoding='utf-8') as f:
                            package_data = json.load(f)
                            deps = package_data.get('dependencies', {})
                            dev_deps = package_data.get('devDependencies', {})
                            if 'ts-morph' in deps or 'ts-morph' in dev_deps:
                                if os.path.exists(repo_node_modules):
                                    self._ts_morph_path = os.path.join(repo_root, 'node_modules')
                                    logger.info(f"Found ts-morph in repo package.json: {self._ts_morph_path}")
                                    logger.info("ts-morph availability check complete: available=True, method=cloned-repo")
                                    return True
                    except Exception:
                        pass
            
            # Priority 3: Check if npx is available as fallback
            try:
                npx_result = subprocess.run(
                    ['npx', '--version'],
                    capture_output=True,
                    timeout=5
                )
                if npx_result.returncode == 0:
                    # Actually test if ts-morph can be required
                    # Try to require ts-morph using node
                    test_result = subprocess.run(
                        ['node', '-e', "require('ts-morph')"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if test_result.returncode == 0:
                        self._use_npx = True
                        logger.info("Using npx as fallback for ts-morph")
                        logger.info("ts-morph availability check complete: available=True, method=npx")
                        return True
                    else:
                        logger.warning("npx available but ts-morph cannot be required. Install ts-morph: npm install ts-morph")
                        logger.info("ts-morph availability check complete: available=False, method=npx-test-failed")
            except Exception as e:
                logger.debug(f"Error checking npx/ts-morph: {e}")
            
            # ts-morph not found in any location
            checked_locations = []
            if node_path_env:
                checked_locations.append("node-path-env")
            if py_processor_root:
                checked_locations.append(f"py-processor ({py_processor_root})")
            if repo_root:
                checked_locations.append(f"cloned-repo ({repo_root})")
            checked_locations.append("npx/global")
            logger.info(f"ts-morph not available. Checked locations: {', '.join(checked_locations)}")
            logger.info("ts-morph availability check complete: available=False, method=not-found")
            return False
        except Exception as e:
            logger.info(f"Error checking ts-morph availability: {e}")
            logger.info("ts-morph availability check complete: available=False, method=error")
            return False
    
    def _check_tree_sitter_availability(self) -> bool:
        """Check if tree-sitter-typescript is available."""
        try:
            from code_parser.multi_parser import parser_ts, parser_js
            return parser_ts is not None or parser_js is not None
        except Exception:
            return False
    
    def _find_repo_root(self) -> Optional[str]:
        """Find repository root by looking for package.json or node_modules."""
        current = os.path.dirname(self.file_path) if os.path.isfile(self.file_path) else self.file_path
        
        # Walk up directory tree
        for _ in range(10):  # Limit search depth
            if os.path.exists(os.path.join(current, 'package.json')):
                return current
            if os.path.exists(os.path.join(current, 'node_modules')):
                return current
            parent = os.path.dirname(current)
            if parent == current:  # Reached root
                break
            current = parent
        
        return None
    
    def parse(self, content: str) -> Any:
        """Parse TypeScript/JavaScript code."""
        if self._ts_morph_available:
            # For ts-morph, we'll handle parsing in apply_edit via subprocess
            return content  # Return content as-is, will be parsed by Node.js script
        elif self._tree_sitter_available:
            # Tree-sitter is available but code generation is not implemented
            # Return None to indicate AST editing should be skipped
            logger.debug("Tree-sitter available but code generation not implemented, skipping AST edit")
            return None
        else:
            raise RuntimeError("No TypeScript parser available")
    
    def apply_edit(self, tree: Any, edit_instructions: List[str]) -> Any:
        """Apply edit instructions to TypeScript/JavaScript AST."""
        if self._ts_morph_available:
            # Use ts-morph via Node.js subprocess
            # tree is actually the content string when ts-morph is used
            return self._apply_edit_with_ts_morph(tree, edit_instructions)
        elif tree is None:
            # Tree-sitter parsing returned None (not supported)
            return None
        else:
            # Tree-sitter tree available but transformations not implemented
            return None
    
    def _apply_edit_with_ts_morph(self, content: str, edit_instructions: List[str]) -> str:
        """Apply edits using ts-morph via Node.js subprocess."""
        try:
            # Find the Node.js script
            script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
            script_path = os.path.join(script_dir, 'ts_morph_editor.js')
            
            if not os.path.exists(script_path):
                logger.warning(f"ts-morph script not found at {script_path}")
                raise RuntimeError("ts-morph script not found")
            
            # Prepare input
            input_data = {
                'content': content,
                'changes': edit_instructions,
                'filePath': self.file_path
            }
            
            # Prepare environment variables
            env = os.environ.copy()
            
            # Always check for NODE_PATH from environment first
            env_node_path = env.get('NODE_PATH', '')
            if env_node_path:
                logger.info(f"Using NODE_PATH from environment: {env_node_path}")
            
            # Set NODE_PATH if using local ts-morph path (merge with env NODE_PATH if both exist)
            if self._ts_morph_path:
                # Add the node_modules directory to NODE_PATH
                # NODE_PATH is a colon-separated (Unix) or semicolon-separated (Windows) list
                node_path_separator = ';' if os.name == 'nt' else ':'
                if env_node_path:
                    # Merge: environment NODE_PATH takes precedence, add detected path if not already present
                    if self._ts_morph_path not in env_node_path:
                        env['NODE_PATH'] = f"{env_node_path}{node_path_separator}{self._ts_morph_path}"
                    else:
                        env['NODE_PATH'] = env_node_path
                else:
                    env['NODE_PATH'] = self._ts_morph_path
                logger.info(f"Set NODE_PATH to: {env['NODE_PATH']}")
            
            # Prepare command
            if self._use_npx:
                # Use npx to run the script (npx will handle module resolution)
                # Note: We still need to run our script, so we use node with NODE_PATH
                # or we could use npx with ts-morph directly, but our script is custom
                # For now, use node with NODE_PATH including global node_modules
                cmd = ['node', script_path]
                # Try to add global node_modules to NODE_PATH if not already set
                if not self._ts_morph_path and not env_node_path:
                    # Get npm global prefix
                    try:
                        npm_result = subprocess.run(
                            ['npm', 'config', 'get', 'prefix'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if npm_result.returncode == 0:
                            npm_prefix = npm_result.stdout.strip()
                            global_node_modules = os.path.join(npm_prefix, 'node_modules')
                            if os.path.exists(global_node_modules):
                                node_path_separator = ';' if os.name == 'nt' else ':'
                                # env_node_path already checked above, use it if set
                                if env_node_path:
                                    env['NODE_PATH'] = f"{global_node_modules}{node_path_separator}{env_node_path}"
                                else:
                                    env['NODE_PATH'] = global_node_modules
                    except Exception:
                        pass
            else:
                cmd = ['node', script_path]
            
            # Call Node.js script
            result = subprocess.run(
                cmd,
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
                cwd=os.path.dirname(self.file_path) if os.path.isfile(self.file_path) else self.file_path
            )
            
            if result.returncode != 0:
                logger.info(f"ts-morph script execution failed. Falling back to LLM editing.")
                logger.error(f"ts-morph script failed: {result.stderr}")
                raise RuntimeError(f"ts-morph script failed: {result.stderr}")
            
            # Parse output
            try:
                output_data = json.loads(result.stdout)
                if output_data.get('success'):
                    return output_data.get('content', content)
                else:
                    error = output_data.get('error', 'Unknown error')
                    logger.info(f"AST editing failed: {error}. Falling back to LLM editing.")
                    logger.error(f"ts-morph edit failed: {error}")
                    raise RuntimeError(f"ts-morph edit failed: {error}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse ts-morph output: {e}")
                raise RuntimeError(f"Invalid ts-morph output: {result.stdout}")
        
        except subprocess.TimeoutExpired:
            logger.info("ts-morph script execution timed out. Falling back to LLM editing.")
            logger.error("ts-morph script timed out")
            raise RuntimeError("ts-morph script timed out")
        except Exception as e:
            logger.info(f"ts-morph subprocess error occurred. Falling back to LLM editing.")
            logger.error(f"ts-morph subprocess error: {e}")
            raise
    
    def generate_code(self, tree: Any) -> str:
        """Generate TypeScript/JavaScript code from AST."""
        if self._ts_morph_available:
            # When ts-morph is used, tree is already the modified content string
            return tree
        elif tree is None:
            # Tree-sitter not supported, return empty to trigger LLM fallback
            return ""
        else:
            # Should not reach here, but handle gracefully
            return ""

"""Extract relationships and edges between modules and symbols."""

import os
import re
import json
from typing import List, Dict, Any, Set, Tuple, Optional
from pathlib import Path

from code_parser.multi_parser import detect_language, parse_file
from code_parser.multi_normalizer import extract_definitions
from code_parser.normalizer import get_text
from code_parser.exceptions import ImportResolutionError


def _load_tsconfig_paths(repo_path: str) -> Dict[str, List[str]]:
    """
    Load and parse tsconfig.json or jsconfig.json path mappings.
    
    Args:
        repo_path: Repository root path
        
    Returns:
        Dictionary mapping path patterns to replacement paths
    """
    path_mappings = {}
    config_files = [
        Path(repo_path) / "tsconfig.json",
        Path(repo_path) / "jsconfig.json"
    ]
    
    for config_file in config_files:
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                compiler_options = config.get("compilerOptions", {})
                paths = compiler_options.get("paths", {})
                base_url = compiler_options.get("baseUrl", ".")
                
                for pattern, replacements in paths.items():
                    # Normalize pattern (remove trailing /*)
                    pattern_key = pattern.rstrip('/*')
                    # Convert replacements to absolute paths
                    resolved_replacements = []
                    for replacement in replacements:
                        if isinstance(replacement, str):
                            # Remove leading ./ and trailing /*
                            replacement = replacement.lstrip('./').rstrip('/*')
                            resolved_path = os.path.join(repo_path, base_url, replacement)
                            resolved_replacements.append(resolved_path)
                    path_mappings[pattern_key] = resolved_replacements
                
                break  # Use first found config file
            except (json.JSONDecodeError, KeyError, IOError):
                continue
    
    return path_mappings


def _find_index_file(directory: Path, extensions: List[str]) -> Optional[Path]:
    """
    Find index file in directory (index.ts, index.js, __init__.py, etc.).
    
    Args:
        directory: Directory to search
        extensions: List of extensions to try (e.g., ['.ts', '.js', '.tsx'])
        
    Returns:
        Path to index file or None if not found
    """
    index_names = ["index", "__init__"]
    
    for index_name in index_names:
        for ext in extensions:
            index_path = directory / f"{index_name}{ext}"
            if index_path.exists():
                return index_path
    
    return None


def _load_package_json_exports(repo_path: str) -> Dict[str, Any]:
    """
    Load package.json exports field.
    
    Args:
        repo_path: Repository root path
        
    Returns:
        Dictionary with exports configuration
    """
    package_json = Path(repo_path) / "package.json"
    
    if package_json.exists():
        try:
            with open(package_json, 'r', encoding='utf-8') as f:
                package_data = json.load(f)
            return package_data.get("exports", {})
        except (json.JSONDecodeError, IOError):
            pass
    
    return {}


def _resolve_with_path_mappings(import_path: str, current_file: str, repo_path: str, path_mappings: Dict[str, List[str]]) -> Optional[str]:
    """
    Resolve import using tsconfig/jsconfig path mappings.
    
    Args:
        import_path: Import path to resolve
        current_file: Current file path
        repo_path: Repository root path
        path_mappings: Path mappings from tsconfig
        
    Returns:
        Resolved module ID or None
    """
    # Try exact match first
    if import_path in path_mappings:
        for replacement in path_mappings[import_path]:
            resolved_path = Path(replacement)
            if resolved_path.exists() and resolved_path.is_file():
                rel_path = os.path.relpath(resolved_path, repo_path)
                return f"mod:{rel_path}"
            elif resolved_path.exists() and resolved_path.is_dir():
                # Try to find index file
                index_file = _find_index_file(resolved_path, ['.ts', '.tsx', '.js', '.jsx'])
                if index_file:
                    rel_path = os.path.relpath(index_file, repo_path)
                    return f"mod:{rel_path}"
    
    # Try pattern matching (e.g., @app/* -> src/app/*)
    for pattern, replacements in path_mappings.items():
        if '*' in pattern:
            pattern_prefix = pattern.replace('*', '')
            if import_path.startswith(pattern_prefix):
                suffix = import_path[len(pattern_prefix):]
                for replacement in replacements:
                    if '*' in replacement:
                        resolved = replacement.replace('*', suffix)
                        resolved_path = Path(resolved)
                        if resolved_path.exists() and resolved_path.is_file():
                            rel_path = os.path.relpath(resolved_path, repo_path)
                            return f"mod:{rel_path}"
                        elif resolved_path.exists() and resolved_path.is_dir():
                            index_file = _find_index_file(resolved_path, ['.ts', '.tsx', '.js', '.jsx'])
                            if index_file:
                                rel_path = os.path.relpath(index_file, repo_path)
                                return f"mod:{rel_path}"
    
    return None


def resolve_import_path(import_stmt: str, current_file: str, repo_path: str) -> Optional[str]:
    """
    Resolve an import statement to a module ID with enhanced resolution strategies.
    
    Args:
        import_stmt: Import statement text
        current_file: Current file path
        repo_path: Repository root path
        
    Returns:
        Module ID or None if cannot resolve
    """
    repo_path_obj = Path(repo_path)
    current_file_obj = Path(current_file)
    current_dir = current_file_obj.parent
    
    # Load path mappings and package.json exports (cached per call for now)
    path_mappings = _load_tsconfig_paths(repo_path)
    package_exports = _load_package_json_exports(repo_path)
    
    # Strategy 1: Python imports
    if "from" in import_stmt and "import" in import_stmt:
        match = re.search(r'from\s+([\w.]+)\s+import', import_stmt)
        if match:
            module_path = match.group(1)
            # Try relative path first
            module_path_parts = module_path.split('.')
            possible_dir = current_dir
            for part in module_path_parts:
                possible_dir = possible_dir / part
            
            # Try __init__.py
            init_file = possible_dir / "__init__.py"
            if init_file.exists():
                rel_path = os.path.relpath(init_file, repo_path)
                return f"mod:{rel_path}"
            
            # Try .py file
            py_file = possible_dir.with_suffix('.py')
            if py_file.exists():
                rel_path = os.path.relpath(py_file, repo_path)
                return f"mod:{rel_path}"
            
            # Try absolute from repo root
            abs_path = repo_path_obj
            for part in module_path_parts:
                abs_path = abs_path / part
            py_file = abs_path.with_suffix('.py')
            if py_file.exists():
                rel_path = os.path.relpath(py_file, repo_path)
                return f"mod:{rel_path}"
            
            # Try directory with __init__.py
            if abs_path.exists() and abs_path.is_dir():
                init_file = abs_path / "__init__.py"
                if init_file.exists():
                    rel_path = os.path.relpath(init_file, repo_path)
                    return f"mod:{rel_path}"
    
    # Strategy 2: TypeScript/JavaScript imports
    match = re.search(r"from\s+['\"]([^'\"]+)['\"]|import\s+.*from\s+['\"]([^'\"]+)['\"]", import_stmt)
    if match:
        import_path = match.group(1) or match.group(2)
        
        # Strategy 2a: Path mappings (tsconfig/jsconfig)
        if path_mappings:
            resolved = _resolve_with_path_mappings(import_path, current_file, repo_path, path_mappings)
            if resolved:
                return resolved
        
        # Strategy 2b: Relative imports
        if import_path.startswith('.'):
            # Normalize relative path
            if import_path.startswith('./'):
                import_path = import_path[2:]
            elif import_path.startswith('../'):
                # Count ../ to go up directories
                up_count = len(import_path) - len(import_path.lstrip('../'))
                up_count = up_count // 3  # '../' is 3 chars
                target_dir = current_dir
                for _ in range(up_count):
                    target_dir = target_dir.parent
                import_path = import_path.lstrip('../')
            else:
                import_path = import_path.lstrip('.')
            
            # Try direct file match
            for ext in ['.ts', '.tsx', '.js', '.jsx', '.mjs']:
                file_path = (current_dir / import_path).with_suffix(ext) if not import_path.endswith(ext) else (current_dir / import_path)
                if file_path.exists() and file_path.is_file():
                    rel_path = os.path.relpath(file_path, repo_path)
                    return f"mod:{rel_path}"
            
            # Try directory with index file
            dir_path = current_dir / import_path
            if dir_path.exists() and dir_path.is_dir():
                index_file = _find_index_file(dir_path, ['.ts', '.tsx', '.js', '.jsx', '.mjs'])
                if index_file:
                    rel_path = os.path.relpath(index_file, repo_path)
                    return f"mod:{rel_path}"
        
        # Strategy 2c: Absolute imports (from repo root)
        else:
            # Try direct file
            for ext in ['.ts', '.tsx', '.js', '.jsx', '.mjs']:
                file_path = (repo_path_obj / import_path).with_suffix(ext) if not import_path.endswith(ext) else (repo_path_obj / import_path)
                if file_path.exists() and file_path.is_file():
                    rel_path = os.path.relpath(file_path, repo_path)
                    return f"mod:{rel_path}"
            
            # Try directory with index
            dir_path = repo_path_obj / import_path
            if dir_path.exists() and dir_path.is_dir():
                index_file = _find_index_file(dir_path, ['.ts', '.tsx', '.js', '.jsx', '.mjs'])
                if index_file:
                    rel_path = os.path.relpath(index_file, repo_path)
                    return f"mod:{rel_path}"
        
        # Strategy 2d: package.json exports (for external packages, we skip for now)
        # This would require node_modules resolution which is complex
    
    return None


def extract_import_edges(
    modules: List[Dict[str, Any]],
    repo_path: str
) -> List[Dict[str, Any]]:
    """
    Extract import edges between modules.
    
    Args:
        modules: List of module dictionaries
        repo_path: Repository root path
        
    Returns:
        List of edge dictionaries with type "imports"
    """
    edges = []
    module_map = {m["id"]: m for m in modules}
    
    for module in modules:
        module_id = module["id"]
        file_path = module.get("file_path")
        
        if not file_path:
            continue
        
        # Try to get imports from raw_imports first, then from definitions
        imports = module.get("raw_imports", [])
        if not imports and "definitions" in module:
            imports = module["definitions"].get("imports", [])
        
        for import_stmt in imports:
            target_module_id = resolve_import_path(import_stmt, file_path, repo_path)
            if target_module_id and target_module_id in module_map:
                edges.append({
                    "from": module_id,
                    "to": target_module_id,
                    "type": "imports",
                    "weight": 1
                })
    
    return edges


def extract_call_edges(
    modules: List[Dict[str, Any]],
    symbols: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Extract call edges between symbols.
    
    Args:
        modules: List of module dictionaries
        symbols: List of symbol dictionaries
        
    Returns:
        List of edge dictionaries with type "calls"
    """
    edges = []
    symbol_map = {}
    
    # Build symbol map by name
    for symbol in symbols:
        symbol_name = symbol.get("name")
        if symbol_name:
            if symbol_name not in symbol_map:
                symbol_map[symbol_name] = []
            symbol_map[symbol_name].append(symbol["id"])
    
    # Find calls in modules
    for module in modules:
        module_id = module["id"]
        definitions = module.get("definitions", {})
        calls = definitions.get("calls", [])
        
        for call in calls:
            func_name = call.get("function", "")
            # Try to find matching symbol
            if func_name in symbol_map:
                for target_symbol_id in symbol_map[func_name]:
                    edges.append({
                        "from": module_id,
                        "to": target_symbol_id,
                        "type": "calls",
                        "weight": 1
                    })
    
    return edges


def extract_inheritance_edges(
    symbols: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Extract extends and implements edges.
    
    Args:
        symbols: List of symbol dictionaries
        
    Returns:
        List of edge dictionaries with types "extends" or "implements"
    """
    edges = []
    symbol_map = {s["id"]: s for s in symbols}
    
    for symbol in symbols:
        symbol_id = symbol["id"]
        
        # Check for extends (inheritance)
        extends = symbol.get("extends")
        if extends:
            # Try to find parent symbol
            for other_symbol in symbols:
                if other_symbol.get("name") == extends:
                    edges.append({
                        "from": symbol_id,
                        "to": other_symbol["id"],
                        "type": "extends",
                        "weight": 1
                    })
                    break
        
        # Check for implements (interface implementation)
        implements = symbol.get("implements", [])
        for interface_name in implements:
            for other_symbol in symbols:
                if other_symbol.get("name") == interface_name and other_symbol.get("kind") == "interface":
                    edges.append({
                        "from": symbol_id,
                        "to": other_symbol["id"],
                        "type": "implements",
                        "weight": 1
                    })
                    break
    
    return edges


def extract_contains_edges(
    modules: List[Dict[str, Any]],
    symbols: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Extract contains edges (module contains symbol).
    
    Args:
        modules: List of module dictionaries
        symbols: List of symbol dictionaries
        
    Returns:
        List of edge dictionaries with type "contains"
    """
    edges = []
    module_map = {m["id"]: m for m in modules}
    
    for symbol in symbols:
        module_id = symbol.get("moduleId")
        if module_id and module_id in module_map:
            edges.append({
                "from": module_id,
                "to": symbol["id"],
                "type": "contains",
                "weight": 1
            })
    
    return edges


def extract_routes_to_edges(
    endpoints: List[Dict[str, Any]],
    symbols: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Extract routes-to edges (endpoint to handler symbol).
    
    Args:
        endpoints: List of endpoint dictionaries
        symbols: List of symbol dictionaries
        
    Returns:
        List of edge dictionaries with type "routes-to"
    """
    edges = []
    symbol_map = {s["id"]: s for s in symbols}
    
    for endpoint in endpoints:
        handler_symbol_id = endpoint.get("handlerSymbolId")
        if handler_symbol_id and handler_symbol_id in symbol_map:
            edges.append({
                "from": endpoint["id"],
                "to": handler_symbol_id,
                "type": "routes-to",
                "weight": 1
            })
    
    return edges


def calculate_fan_in_fan_out(
    modules: List[Dict[str, Any]],
    edges: List[Dict[str, Any]]
) -> Dict[str, Tuple[int, int]]:
    """
    Calculate fan-in and fan-out for each module.
    
    Args:
        modules: List of module dictionaries
        edges: List of edge dictionaries
        
    Returns:
        Dictionary mapping module_id to (fan_in, fan_out) tuple
    """
    fan_stats = {m["id"]: [0, 0] for m in modules}  # [fan_in, fan_out]
    
    for edge in edges:
        edge_type = edge.get("type")
        if edge_type == "imports":
            from_id = edge.get("from")
            to_id = edge.get("to")
            if from_id in fan_stats:
                fan_stats[from_id][1] += 1  # fan_out
            if to_id in fan_stats:
                fan_stats[to_id][0] += 1  # fan_in
    
    return {module_id: (stats[0], stats[1]) for module_id, stats in fan_stats.items()}


def extract_relationships(
    modules: List[Dict[str, Any]],
    symbols: List[Dict[str, Any]],
    endpoints: List[Dict[str, Any]],
    repo_path: str
) -> Tuple[List[Dict[str, Any]], Dict[str, Tuple[int, int]]]:
    """
    Extract all relationships and edges.
    
    Args:
        modules: List of module dictionaries
        symbols: List of symbol dictionaries
        endpoints: List of endpoint dictionaries
        repo_path: Repository root path
        
    Returns:
        Tuple of (edges list, fan statistics dictionary)
    """
    edges = []
    
    # Extract different types of edges
    edges.extend(extract_import_edges(modules, repo_path))
    edges.extend(extract_call_edges(modules, symbols))
    edges.extend(extract_inheritance_edges(symbols))
    edges.extend(extract_contains_edges(modules, symbols))
    edges.extend(extract_routes_to_edges(endpoints, symbols))
    
    # Calculate fan-in/fan-out
    fan_stats = calculate_fan_in_fan_out(modules, edges)
    
    return edges, fan_stats


"""Extract relationships and edges between modules and symbols."""

import os
import re
from typing import List, Dict, Any, Set, Tuple, Optional
from pathlib import Path

from code_parser.multi_parser import detect_language, parse_file
from code_parser.multi_normalizer import extract_definitions
from code_parser.normalizer import get_text


def resolve_import_path(import_stmt: str, current_file: str, repo_path: str) -> Optional[str]:
    """
    Resolve an import statement to a module ID.
    
    Args:
        import_stmt: Import statement text
        current_file: Current file path
        repo_path: Repository root path
        
    Returns:
        Module ID or None if cannot resolve
    """
    # This is a simplified resolver - can be enhanced
    # For now, try to match common patterns
    
    # Python: from module import X or import module
    if "from" in import_stmt and "import" in import_stmt:
        match = re.search(r'from\s+([\w.]+)\s+import', import_stmt)
        if match:
            module_path = match.group(1).replace('.', os.sep)
            # Try to find the file
            current_dir = os.path.dirname(current_file)
            possible_paths = [
                os.path.join(current_dir, module_path + '.py'),
                os.path.join(repo_path, module_path.replace('.', os.sep) + '.py'),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    rel_path = os.path.relpath(path, repo_path)
                    return f"mod:{rel_path}"
    
    # TypeScript/JavaScript: import X from 'path'
    match = re.search(r"from\s+['\"]([^'\"]+)['\"]", import_stmt)
    if match:
        import_path = match.group(1)
        # Resolve relative imports
        if import_path.startswith('.'):
            current_dir = os.path.dirname(current_file)
            resolved = os.path.normpath(os.path.join(current_dir, import_path))
            if os.path.exists(resolved + '.ts'):
                rel_path = os.path.relpath(resolved + '.ts', repo_path)
                return f"mod:{rel_path}"
            elif os.path.exists(resolved + '.tsx'):
                rel_path = os.path.relpath(resolved + '.tsx', repo_path)
                return f"mod:{rel_path}"
            elif os.path.exists(resolved + '.js'):
                rel_path = os.path.relpath(resolved + '.js', repo_path)
                return f"mod:{rel_path}"
    
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


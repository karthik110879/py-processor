"""Multi-language normalizer to extract definitions from various programming languages."""

import re
from typing import Any, Dict, Optional, List
from tree_sitter import Node

from code_parser.normalizer import get_text, extract_docstring
from code_parser.multi_parser import parse_source, detect_language


def extract_python_definitions(root: Node, source: str) -> Dict[str, Any]:
    """Extract Python definitions (reuse existing implementation)."""
    from code_parser.normalizer import extract_python_definitions as py_extract
    return py_extract(root, source)


def extract_ts_definitions(root: Node, source: str) -> Dict[str, Any]:
    """Extract TypeScript definitions (reuse existing implementation)."""
    from code_parser.normalizer import extract_ts_definitions as ts_extract
    return ts_extract(root, source)


def extract_js_definitions(root: Node, source: str) -> Dict[str, Any]:
    """Extract JavaScript definitions (similar to TypeScript)."""
    results: Dict[str, Any] = {
        "functions": [],
        "classes": [],
        "imports": [],
        "variables": [],
        "calls": []
    }
    
    def walk(node: Node):
        yield node
        for child in node.children:
            yield from walk(child)
    
    for node in walk(root):
        if node.type == "import_statement":
            results["imports"].append(get_text(node, source))
        
        elif node.type == "function_declaration":
            name = get_text(node.child_by_field_name("name"), source)
            params = get_text(node.child_by_field_name("parameters"), source)
            results["functions"].append({"name": name, "parameters": params})
        
        elif node.type == "arrow_function":
            # Handle arrow functions assigned to variables
            parent = node.parent
            if parent and parent.type == "variable_declarator":
                name_node = parent.child_by_field_name("name")
                name = get_text(name_node, source) if name_node else None
                params = get_text(node.child_by_field_name("parameters"), source)
                if name:
                    results["functions"].append({"name": name, "parameters": params})
        
        elif node.type == "class_declaration":
            name = get_text(node.child_by_field_name("name"), source)
            methods = []
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type == "method_definition":
                        method_name = get_text(child.child_by_field_name("name"), source)
                        methods.append({"name": method_name})
            results["classes"].append({"name": name, "methods": methods})
        
        elif node.type == "variable_declaration":
            results["variables"].append(get_text(node, source))
        
        elif node.type == "call_expression":
            func = get_text(node.child_by_field_name("function"), source)
            args_node = node.child_by_field_name("arguments")
            args = [get_text(arg, source) for arg in args_node.children if arg.type not in (",", "(", ")")]
            results["calls"].append({"function": func, "arguments": args})
    
    return results


def extract_java_definitions(root: Node, source: str) -> Dict[str, Any]:
    """Extract Java definitions including classes, methods, interfaces, and annotations."""
    results: Dict[str, Any] = {
        "classes": [],
        "interfaces": [],
        "methods": [],
        "imports": [],
        "annotations": [],
        "fields": []
    }
    
    def walk(node: Node):
        yield node
        for child in node.children:
            yield from walk(child)
    
    for node in walk(root):
        if node.type == "import_declaration":
            results["imports"].append(get_text(node, source))
        
        elif node.type == "class_declaration":
            name = get_text(node.child_by_field_name("name"), source)
            methods = []
            fields = []
            annotations = []
            
            # Extract annotations
            for child in node.children:
                if child.type == "modifiers":
                    for mod in child.children:
                        if mod.type == "annotation":
                            annotations.append(get_text(mod, source))
            
            # Extract methods and fields
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type == "method_declaration":
                        method_name = get_text(child.child_by_field_name("name"), source)
                        params = get_text(child.child_by_field_name("parameters"), source)
                        return_type = None
                        for c in child.children:
                            if c.type == "type_identifier" or c.type == "void_type":
                                return_type = get_text(c, source)
                                break
                        methods.append({
                            "name": method_name,
                            "parameters": params,
                            "return_type": return_type
                        })
                    elif child.type == "field_declaration":
                        field_text = get_text(child, source)
                        fields.append(field_text)
            
            results["classes"].append({
                "name": name,
                "methods": methods,
                "fields": fields,
                "annotations": annotations
            })
        
        elif node.type == "interface_declaration":
            name = get_text(node.child_by_field_name("name"), source)
            methods = []
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type == "method_declaration":
                        method_name = get_text(child.child_by_field_name("name"), source)
                        params = get_text(child.child_by_field_name("parameters"), source)
                        methods.append({"name": method_name, "parameters": params})
            results["interfaces"].append({"name": name, "methods": methods})
    
    return results


def extract_c_definitions(root: Node, source: str) -> Dict[str, Any]:
    """Extract C definitions including functions, structs, and includes."""
    results: Dict[str, Any] = {
        "functions": [],
        "structs": [],
        "includes": [],
        "typedefs": []
    }
    
    def walk(node: Node):
        yield node
        for child in node.children:
            yield from walk(child)
    
    for node in walk(root):
        if node.type == "preproc_include":
            results["includes"].append(get_text(node, source))
        
        elif node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            if declarator:
                name_node = declarator.child_by_field_name("declarator")
                if name_node:
                    name = get_text(name_node, source)
                    params = get_text(declarator.child_by_field_name("parameters"), source)
                    results["functions"].append({"name": name, "parameters": params})
        
        elif node.type == "struct_specifier":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = get_text(name_node, source)
                results["structs"].append({"name": name})
        
        elif node.type == "type_definition":
            name = get_text(node.child_by_field_name("name"), source)
            results["typedefs"].append({"name": name})
    
    return results


def extract_cpp_definitions(root: Node, source: str) -> Dict[str, Any]:
    """Extract C++ definitions including classes, functions, and includes."""
    results: Dict[str, Any] = {
        "classes": [],
        "functions": [],
        "includes": [],
        "namespaces": []
    }
    
    def walk(node: Node):
        yield node
        for child in node.children:
            yield from walk(child)
    
    for node in walk(root):
        if node.type == "preproc_include":
            results["includes"].append(get_text(node, source))
        
        elif node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            if declarator:
                name_node = declarator.child_by_field_name("declarator")
                if name_node:
                    name = get_text(name_node, source)
                    params = get_text(declarator.child_by_field_name("parameters"), source)
                    results["functions"].append({"name": name, "parameters": params})
        
        elif node.type == "class_specifier":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = get_text(name_node, source)
                methods = []
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        if child.type == "function_definition":
                            declarator = child.child_by_field_name("declarator")
                            if declarator:
                                method_name_node = declarator.child_by_field_name("declarator")
                                if method_name_node:
                                    method_name = get_text(method_name_node, source)
                                    params = get_text(declarator.child_by_field_name("parameters"), source)
                                    methods.append({"name": method_name, "parameters": params})
                results["classes"].append({"name": name, "methods": methods})
        
        elif node.type == "namespace_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = get_text(name_node, source)
                results["namespaces"].append({"name": name})
    
    return results


def extract_csharp_definitions(root: Node, source: str) -> Dict[str, Any]:
    """Extract C# definitions including classes, methods, interfaces, and attributes."""
    results: Dict[str, Any] = {
        "classes": [],
        "interfaces": [],
        "methods": [],
        "imports": [],
        "attributes": [],
        "properties": []
    }
    
    def walk(node: Node):
        yield node
        for child in node.children:
            yield from walk(child)
    
    for node in walk(root):
        if node.type == "using_directive":
            results["imports"].append(get_text(node, source))
        
        elif node.type == "class_declaration":
            name = get_text(node.child_by_field_name("name"), source)
            methods = []
            properties = []
            attributes = []
            
            # Extract attributes
            for child in node.children:
                if child.type == "attribute_list":
                    attributes.append(get_text(child, source))
            
            # Extract methods and properties
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type == "method_declaration":
                        method_name = get_text(child.child_by_field_name("name"), source)
                        params = get_text(child.child_by_field_name("parameter_list"), source)
                        return_type = None
                        for c in child.children:
                            if c.type == "predefined_type" or c.type == "identifier":
                                return_type = get_text(c, source)
                                break
                        methods.append({
                            "name": method_name,
                            "parameters": params,
                            "return_type": return_type
                        })
                    elif child.type == "property_declaration":
                        prop_name = get_text(child.child_by_field_name("name"), source)
                        properties.append({"name": prop_name})
            
            results["classes"].append({
                "name": name,
                "methods": methods,
                "properties": properties,
                "attributes": attributes
            })
        
        elif node.type == "interface_declaration":
            name = get_text(node.child_by_field_name("name"), source)
            methods = []
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type == "method_declaration":
                        method_name = get_text(child.child_by_field_name("name"), source)
                        params = get_text(child.child_by_field_name("parameter_list"), source)
                        methods.append({"name": method_name, "parameters": params})
            results["interfaces"].append({"name": name, "methods": methods})
    
    return results


def extract_asp_definitions(source: str) -> Dict[str, Any]:
    """Extract Classic ASP definitions using regex (no tree-sitter support)."""
    results: Dict[str, Any] = {
        "functions": [],
        "subroutines": [],
        "includes": []
    }
    
    # Extract function definitions
    function_pattern = r'Function\s+(\w+)\s*\([^)]*\)'
    for match in re.finditer(function_pattern, source, re.IGNORECASE):
        results["functions"].append({"name": match.group(1)})
    
    # Extract subroutine definitions
    sub_pattern = r'Sub\s+(\w+)\s*\([^)]*\)'
    for match in re.finditer(sub_pattern, source, re.IGNORECASE):
        results["subroutines"].append({"name": match.group(1)})
    
    # Extract includes
    include_pattern = r'<!--\s*#include\s+(?:file|virtual)=["\']([^"\']+)["\']\s*-->'
    for match in re.finditer(include_pattern, source, re.IGNORECASE):
        results["includes"].append(match.group(1))
    
    return results


def extract_definitions(file_path: str, source: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Extract definitions from a file based on its language.
    
    Args:
        file_path: Path to the file
        source: Optional source code string (if None, will read from file)
        
    Returns:
        Dictionary with extracted definitions or None if not supported
    """
    language = detect_language(file_path)
    
    if not language:
        return None
    
    if source is None:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                source = f.read()
        except Exception:
            return None
    
    # Handle languages without tree-sitter support
    if language in ('asp', 'aspx'):
        return extract_asp_definitions(source)
    
    # Parse using tree-sitter
    root = parse_source(source, language)
    if not root:
        return None
    
    # Extract based on language
    if language == 'python':
        return extract_python_definitions(root, source)
    elif language == 'typescript':
        return extract_ts_definitions(root, source)
    elif language == 'javascript':
        return extract_js_definitions(root, source)
    elif language == 'java':
        return extract_java_definitions(root, source)
    elif language == 'c':
        return extract_c_definitions(root, source)
    elif language == 'cpp':
        return extract_cpp_definitions(root, source)
    elif language == 'csharp':
        return extract_csharp_definitions(root, source)
    
    return None


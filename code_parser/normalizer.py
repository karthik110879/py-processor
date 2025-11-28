from typing import Any, Dict, Optional
from tree_sitter import Node

# def get_text(node: Node, source: str) -> str:
#     return source[node.start_byte:node.end_byte]

def get_text(node: Optional[Node], source: str) -> Optional[str]:
    """Safely extract text for a node, return None if node is missing."""
    if node is None:
        return None
    return source[node.start_byte:node.end_byte]


def extract_docstring(node: Node, source: str) -> Optional[str]:
    """Extract Python docstring if present as first statement in body."""
    body = node.child_by_field_name("body")
    if body and body.children:
        first_stmt = body.children[0]
        expr = first_stmt.child_by_field_name("expression")
        if expr and expr.type == "string":
            return get_text(expr, source).strip('"').strip("'")
    return None

def extract_python_definitions(root: Node, source: str) -> Dict[str, Any]:
    results: Dict[str, Any] = {"functions": [], "classes": [], "imports": [], "assignments": [], "calls": []}

    def walk(node: Node):
        yield node
        for child in node.children:
            yield from walk(child)

    for node in walk(root):
        if node.type in ("import_statement", "import_from_statement"):
            results["imports"].append(get_text(node, source))

        elif node.type == "function_definition":
            name = get_text(node.child_by_field_name("name"), source)
            params = get_text(node.child_by_field_name("parameters"), source)
            docstring = extract_docstring(node, source)
            results["functions"].append({"name": name, "parameters": params, "docstring": docstring})

        elif node.type == "class_definition":
            name = get_text(node.child_by_field_name("name"), source)
            docstring = extract_docstring(node, source)
            methods = []
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type == "function_definition":
                        methods.append(get_text(child.child_by_field_name("name"), source))
            results["classes"].append({"name": name, "docstring": docstring, "methods": methods})

        elif node.type == "assignment":
            left = get_text(node.child_by_field_name("left"), source)
            right = get_text(node.child_by_field_name("right"), source)
            results["assignments"].append({"target": left, "value": right})

        elif node.type == "call":
            func = get_text(node.child_by_field_name("function"), source)
            args_node = node.child_by_field_name("arguments")
            args = [get_text(arg, source) for arg in args_node.children if arg.type not in (",", "(", ")")]
            results["calls"].append({"function": func, "arguments": args})

    return results

def extract_ts_definitions(root: Node, source: str) -> Dict[str, Any]:
    results: Dict[str, Any] = {"functions": [], "classes": [], "imports": [], "variables": [], "calls": []}

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
            docstring = None
            prev_sibling = node.prev_sibling
            if prev_sibling and prev_sibling.type == "comment" and get_text(prev_sibling, source).startswith("/**"):
                docstring = get_text(prev_sibling, source)
            results["functions"].append({"name": name, "parameters": params, "docstring": docstring})

        elif node.type == "class_declaration":
            name = get_text(node.child_by_field_name("name"), source)
            methods = []
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type == "method_definition":
                        method_name = get_text(child.child_by_field_name("name"), source)
                        docstring = None
                        prev_sibling = child.prev_sibling
                        if prev_sibling and prev_sibling.type == "comment" and get_text(prev_sibling, source).startswith("/**"):
                            docstring = get_text(prev_sibling, source)
                        methods.append({"name": method_name, "docstring": docstring})
            results["classes"].append({"name": name, "methods": methods})

        elif node.type == "variable_statement":
            results["variables"].append(get_text(node, source))

        elif node.type == "call_expression":
            func = get_text(node.child_by_field_name("function"), source)
            args_node = node.child_by_field_name("arguments")
            args = [get_text(arg, source) for arg in args_node.children if arg.type not in (",", "(", ")")]
            results["calls"].append({"function": func, "arguments": args})

    return results


def safe_get_text(node: Optional[Node], source: str) -> Optional[str]:
    if node is None:
        return None
    return source[node.start_byte:node.end_byte]
"""Extract HTTP/RPC endpoints from various frameworks."""

import re
from typing import List, Dict, Any, Optional
from pathlib import Path

from code_parser.multi_parser import parse_file, detect_language
from code_parser.normalizer import get_text


def extract_nestjs_endpoints(file_path: str, source: str, module_id: str) -> List[Dict[str, Any]]:
    """
    Extract NestJS endpoints from decorators.
    
    Args:
        file_path: Path to the file
        source: Source code content
        module_id: Module ID for the file
        
    Returns:
        List of endpoint dictionaries
    """
    endpoints = []
    root = parse_file(file_path)
    
    if not root:
        return endpoints
    
    # Find @Controller decorator
    controller_path = None
    controller_pattern = r'@Controller\(["\']([^"\']+)["\']\)'
    controller_match = re.search(controller_pattern, source)
    if controller_match:
        controller_path = controller_match.group(1)
    
    # Find all method decorators (@Get, @Post, etc.)
    method_patterns = {
        'GET': r'@Get\(["\']([^"\']*)["\']\)',
        'POST': r'@Post\(["\']([^"\']*)["\']\)',
        'PUT': r'@Put\(["\']([^"\']*)["\']\)',
        'DELETE': r'@Delete\(["\']([^"\']*)["\']\)',
        'PATCH': r'@Patch\(["\']([^"\']*)["\']\)',
    }
    
    # Find method definitions with decorators
    def walk(node):
        yield node
        for child in node.children:
            yield from walk(child)
    
    for node in walk(root):
        if node.type == "method_definition" or node.type == "method_declaration":
            # Get method name
            method_name_node = node.child_by_field_name("name")
            if not method_name_node:
                continue
            
            method_name = get_text(method_name_node, source)
            if not method_name:
                continue
            
            # Check for decorators before the method
            method_start = node.start_byte
            method_decorators = source[max(0, method_start - 500):method_start]
            
            # Find HTTP method decorator
            http_method = None
            path_suffix = ""
            
            for method, pattern in method_patterns.items():
                match = re.search(pattern, method_decorators)
                if match:
                    http_method = method
                    path_suffix = match.group(1) if match.group(1) else ""
                    break
            
            if http_method and controller_path is not None:
                # Build full path
                full_path = controller_path.rstrip('/') + '/' + path_suffix.lstrip('/')
                full_path = '/' + full_path.lstrip('/')
                
                # Generate endpoint ID
                endpoint_id = f"ep:{http_method}:{full_path}"
                
                endpoints.append({
                    "id": endpoint_id,
                    "method": http_method,
                    "path": full_path,
                    "handlerModuleId": module_id,
                    "handlerSymbolId": f"{module_id}:{method_name}",
                    "summary": f"{http_method} {full_path}"
                })
    
    return endpoints


def extract_express_endpoints(file_path: str, source: str, module_id: str) -> List[Dict[str, Any]]:
    """
    Extract Express.js endpoints from app.get(), router.post(), etc.
    
    Args:
        file_path: Path to the file
        source: Source code content
        module_id: Module ID for the file
        
    Returns:
        List of endpoint dictionaries
    """
    endpoints = []
    
    # Pattern for Express routes: app.get('/path', handler) or router.post('/path', handler)
    route_pattern = r'(?:app|router|express\(\))\.(get|post|put|delete|patch|all)\s*\(\s*["\']([^"\']+)["\']'
    
    for match in re.finditer(route_pattern, source):
        http_method = match.group(1).upper()
        path = match.group(2)
        
        # Find the handler function name (if it's a named function)
        handler_start = match.end()
        handler_snippet = source[handler_start:handler_start + 200]
        
        handler_name = None
        # Try to find function name: function handlerName or const handlerName = ...
        func_match = re.search(r'(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\(|(\w+)\s*:\s*(?:async\s*)?\()', handler_snippet)
        if func_match:
            handler_name = func_match.group(1) or func_match.group(2) or func_match.group(3)
        
        endpoint_id = f"ep:{http_method}:{path}"
        
        endpoints.append({
            "id": endpoint_id,
            "method": http_method,
            "path": path,
            "handlerModuleId": module_id,
            "handlerSymbolId": f"{module_id}:{handler_name}" if handler_name else None,
            "summary": f"{http_method} {path}"
        })
    
    return endpoints


def extract_spring_endpoints(file_path: str, source: str, module_id: str) -> List[Dict[str, Any]]:
    """
    Extract Spring Boot endpoints from annotations.
    
    Args:
        file_path: Path to the file
        source: Source code content
        module_id: Module ID for the file
        
    Returns:
        List of endpoint dictionaries
    """
    endpoints = []
    
    # Find @RequestMapping or @RestController base path
    base_path = ""
    request_mapping_match = re.search(r'@RequestMapping\(["\']([^"\']+)["\']\)', source)
    if request_mapping_match:
        base_path = request_mapping_match.group(1)
    
    # Find method-level annotations
    method_patterns = {
        'GET': r'@GetMapping\(["\']([^"\']*)["\']\)',
        'POST': r'@PostMapping\(["\']([^"\']*)["\']\)',
        'PUT': r'@PutMapping\(["\']([^"\']*)["\']\)',
        'DELETE': r'@DeleteMapping\(["\']([^"\']*)["\']\)',
        'PATCH': r'@PatchMapping\(["\']([^"\']*)["\']\)',
    }
    
    # Find method definitions
    method_def_pattern = r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\('
    
    for method_match in re.finditer(method_def_pattern, source):
        method_name = method_match.group(1)
        method_start = method_match.start()
        
        # Look for annotations before the method
        method_context = source[max(0, method_start - 300):method_start]
        
        # Check for HTTP method annotations
        http_method = None
        path_suffix = ""
        
        for method, pattern in method_patterns.items():
            annotation_match = re.search(pattern, method_context)
            if annotation_match:
                http_method = method
                path_suffix = annotation_match.group(1) if annotation_match.group(1) else ""
                break
        
        if http_method:
            # Build full path
            full_path = base_path.rstrip('/') + '/' + path_suffix.lstrip('/')
            full_path = '/' + full_path.lstrip('/')
            
            endpoint_id = f"ep:{http_method}:{full_path}"
            
            endpoints.append({
                "id": endpoint_id,
                "method": http_method,
                "path": full_path,
                "handlerModuleId": module_id,
                "handlerSymbolId": f"{module_id}:{method_name}",
                "summary": f"{http_method} {full_path}"
            })
    
    return endpoints


def extract_aspnet_endpoints(file_path: str, source: str, module_id: str) -> List[Dict[str, Any]]:
    """
    Extract ASP.NET endpoints from attributes.
    
    Args:
        file_path: Path to the file
        source: Source code content
        module_id: Module ID for the file
        
    Returns:
        List of endpoint dictionaries
    """
    endpoints = []
    
    # Find [Route] base path
    base_path = ""
    route_match = re.search(r'\[Route\(["\']([^"\']+)["\']\)\]', source)
    if route_match:
        base_path = route_match.group(1)
    
    # Find method-level HTTP attributes
    method_patterns = {
        'GET': r'\[HttpGet(?:\(["\']([^"\']*)["\']\))?\]',
        'POST': r'\[HttpPost(?:\(["\']([^"\']*)["\']\))?\]',
        'PUT': r'\[HttpPut(?:\(["\']([^"\']*)["\']\))?\]',
        'DELETE': r'\[HttpDelete(?:\(["\']([^"\']*)["\']\))?\]',
        'PATCH': r'\[HttpPatch(?:\(["\']([^"\']*)["\']\))?\]',
    }
    
    # Find method definitions
    method_def_pattern = r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\('
    
    for method_match in re.finditer(method_def_pattern, source):
        method_name = method_match.group(1)
        method_start = method_match.start()
        
        # Look for attributes before the method
        method_context = source[max(0, method_start - 300):method_start]
        
        # Check for HTTP method attributes
        http_method = None
        path_suffix = ""
        
        for method, pattern in method_patterns.items():
            attr_match = re.search(pattern, method_context)
            if attr_match:
                http_method = method
                path_suffix = attr_match.group(1) if attr_match.group(1) else ""
                break
        
        if http_method:
            # Build full path
            full_path = base_path.rstrip('/') + '/' + path_suffix.lstrip('/')
            full_path = '/' + full_path.lstrip('/')
            
            endpoint_id = f"ep:{http_method}:{full_path}"
            
            endpoints.append({
                "id": endpoint_id,
                "method": http_method,
                "path": full_path,
                "handlerModuleId": module_id,
                "handlerSymbolId": f"{module_id}:{method_name}",
                "summary": f"{http_method} {full_path}"
            })
    
    return endpoints


def extract_fastapi_endpoints(file_path: str, source: str, module_id: str) -> List[Dict[str, Any]]:
    """
    Extract FastAPI endpoints from decorators.
    
    Args:
        file_path: Path to the file
        source: Source code content
        module_id: Module ID for the file
        
    Returns:
        List of endpoint dictionaries
    """
    endpoints = []
    
    # Find @app or @router base path
    base_path = ""
    router_match = re.search(r'@(?:app|router)\.(?:get|post|put|delete|patch)', source)
    if router_match:
        # Try to find APIRouter with prefix
        prefix_match = re.search(r'APIRouter\(prefix=["\']([^"\']+)["\']', source)
        if prefix_match:
            base_path = prefix_match.group(1)
    
    # Find route decorators
    route_pattern = r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'
    
    for match in re.finditer(route_pattern, source):
        http_method = match.group(1).upper()
        path_suffix = match.group(2)
        
        # Find the handler function name
        handler_start = match.end()
        handler_snippet = source[handler_start:handler_start + 200]
        
        handler_name = None
        func_match = re.search(r'def\s+(\w+)\s*\(', handler_snippet)
        if func_match:
            handler_name = func_match.group(1)
        
        # Build full path
        full_path = base_path.rstrip('/') + '/' + path_suffix.lstrip('/')
        full_path = '/' + full_path.lstrip('/')
        
        endpoint_id = f"ep:{http_method}:{full_path}"
        
        endpoints.append({
            "id": endpoint_id,
            "method": http_method,
            "path": full_path,
            "handlerModuleId": module_id,
            "handlerSymbolId": f"{module_id}:{handler_name}" if handler_name else None,
            "summary": f"{http_method} {full_path}"
        })
    
    return endpoints


def extract_endpoints(
    file_path: str,
    source: str,
    module_id: str,
    frameworks: List[str]
) -> List[Dict[str, Any]]:
    """
    Extract endpoints based on detected frameworks.
    
    Args:
        file_path: Path to the file
        source: Source code content
        module_id: Module ID for the file
        frameworks: List of detected frameworks
        
    Returns:
        List of endpoint dictionaries
    """
    endpoints = []
    language = detect_language(file_path)
    
    if not language:
        return endpoints
    
    # Try framework-specific extractors
    if "nestjs" in frameworks and language in ("typescript", "javascript"):
        endpoints.extend(extract_nestjs_endpoints(file_path, source, module_id))
    
    if "express" in frameworks and language in ("typescript", "javascript"):
        endpoints.extend(extract_express_endpoints(file_path, source, module_id))
    
    if "spring-boot" in frameworks and language == "java":
        endpoints.extend(extract_spring_endpoints(file_path, source, module_id))
    
    if any(f.startswith("aspnet") for f in frameworks) and language == "csharp":
        endpoints.extend(extract_aspnet_endpoints(file_path, source, module_id))
    
    if "fastapi" in frameworks and language == "python":
        endpoints.extend(extract_fastapi_endpoints(file_path, source, module_id))
    
    return endpoints


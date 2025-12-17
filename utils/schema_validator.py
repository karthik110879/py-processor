"""Validate PKG JSON against project-schema.json."""

import json
import os
from typing import Dict, Any, Tuple, Optional, List
import jsonschema
from jsonschema import validate, ValidationError


def load_schema(schema_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load the PKG schema from project-schema.json.
    
    Args:
        schema_path: Optional path to schema file. If None, looks for project-schema.json in project root.
        
    Returns:
        Schema dictionary
    """
    if schema_path is None:
        # Try to find project-schema.json in project root
        # #region agent log
        import json
        log_data = {
            "sessionId": "debug-session",
            "runId": "post-fix",
            "hypothesisId": "A",
            "location": "utils/schema_validator.py:22",
            "message": "load_schema path calculation (post-fix)",
            "data": {
                "__file__": __file__,
                "abspath": os.path.abspath(__file__),
                "current_dir": os.path.dirname(os.path.abspath(__file__)),
                "project_root_calculated": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            },
            "timestamp": int(__import__("time").time() * 1000)
        }
        with open(r"d:\Projects\Dev_Projects\2.0_Doc_processor\py-processor\.cursor\debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_data) + "\n")
        # #endregion
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        schema_path = os.path.join(project_root, "project-schema.json")
        # #region agent log
        log_data2 = {
            "sessionId": "debug-session",
            "runId": "post-fix",
            "hypothesisId": "A",
            "location": "utils/schema_validator.py:24",
            "message": "calculated schema_path (post-fix)",
            "data": {
                "project_root": project_root,
                "schema_path": schema_path,
                "exists": os.path.exists(schema_path)
            },
            "timestamp": int(__import__("time").time() * 1000)
        }
        with open(r"d:\Projects\Dev_Projects\2.0_Doc_processor\py-processor\.cursor\debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_data2) + "\n")
        # #endregion
    
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_pkg(pkg_data: Dict[str, Any], schema_path: Optional[str] = None) -> Tuple[bool, List[str]]:
    """
    Validate PKG data against the schema with detailed error reporting.
    
    Args:
        pkg_data: PKG dictionary to validate
        schema_path: Optional path to schema file
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors: List[str] = []
    
    try:
        schema = load_schema(schema_path)
        
        # Basic schema validation
        try:
            validate(instance=pkg_data, schema=schema)
        except ValidationError as e:
            error_msg = f"Schema validation error at {'.'.join(str(p) for p in e.path)}: {e.message}"
            errors.append(error_msg)
        
        # Additional custom validations
        errors.extend(_validate_module_ids(pkg_data))
        errors.extend(_validate_symbol_ids(pkg_data))
        errors.extend(_validate_edges(pkg_data))
        errors.extend(_validate_required_fields(pkg_data))
        errors.extend(_validate_framework_metadata(pkg_data))
        
        return len(errors) == 0, errors
        
    except Exception as e:
        errors.append(f"Validation failed: {str(e)}")
        return False, errors


def _validate_module_ids(pkg_data: Dict[str, Any]) -> List[str]:
    """Validate module ID format (mod:path)."""
    errors = []
    modules = pkg_data.get("modules", [])
    
    for i, module in enumerate(modules):
        module_id = module.get("id")
        if not module_id:
            errors.append(f"Module[{i}]: Missing 'id' field")
        elif not module_id.startswith("mod:"):
            errors.append(f"Module[{i}]: Invalid ID format '{module_id}' (must start with 'mod:')")
        else:
            # Check that path matches ID
            path = module.get("path", "")
            expected_id = f"mod:{path}"
            if module_id != expected_id:
                errors.append(f"Module[{i}]: ID '{module_id}' doesn't match path '{path}'")
    
    return errors


def _validate_symbol_ids(pkg_data: Dict[str, Any]) -> List[str]:
    """Validate symbol ID format (sym:mod:path:name)."""
    errors = []
    symbols = pkg_data.get("symbols", [])
    module_ids = {m.get("id") for m in pkg_data.get("modules", [])}
    
    for i, symbol in enumerate(symbols):
        symbol_id = symbol.get("id")
        if not symbol_id:
            errors.append(f"Symbol[{i}]: Missing 'id' field")
        elif not symbol_id.startswith("sym:"):
            errors.append(f"Symbol[{i}]: Invalid ID format '{symbol_id}' (must start with 'sym:')")
        else:
            # Check that moduleId exists
            module_id = symbol.get("moduleId")
            if not module_id:
                errors.append(f"Symbol[{i}]: Missing 'moduleId' field")
            elif module_id not in module_ids:
                errors.append(f"Symbol[{i}]: moduleId '{module_id}' not found in modules")
    
    return errors


def _validate_edges(pkg_data: Dict[str, Any]) -> List[str]:
    """Validate edge references (from/to must exist)."""
    errors = []
    edges = pkg_data.get("edges", [])
    
    # Build sets of valid IDs
    module_ids = {m.get("id") for m in pkg_data.get("modules", [])}
    symbol_ids = {s.get("id") for s in pkg_data.get("symbols", [])}
    endpoint_ids = {e.get("id") for e in pkg_data.get("endpoints", [])}
    valid_ids = module_ids | symbol_ids | endpoint_ids
    
    for i, edge in enumerate(edges):
        from_id = edge.get("from")
        to_id = edge.get("to")
        edge_type = edge.get("type")
        
        if not from_id:
            errors.append(f"Edge[{i}]: Missing 'from' field")
        elif from_id not in valid_ids:
            errors.append(f"Edge[{i}]: 'from' ID '{from_id}' not found in modules/symbols/endpoints")
        
        if not to_id:
            errors.append(f"Edge[{i}]: Missing 'to' field")
        elif to_id not in valid_ids:
            errors.append(f"Edge[{i}]: 'to' ID '{to_id}' not found in modules/symbols/endpoints")
        
        if not edge_type:
            errors.append(f"Edge[{i}]: Missing 'type' field")
        else:
            valid_types = ["imports", "calls", "implements", "extends", "routes-to", "uses-db", "tests", "contains"]
            if edge_type not in valid_types:
                errors.append(f"Edge[{i}]: Invalid type '{edge_type}' (must be one of {valid_types})")
    
    return errors


def _validate_required_fields(pkg_data: Dict[str, Any]) -> List[str]:
    """Validate required fields per entity type."""
    errors = []
    
    # Validate project
    project = pkg_data.get("project", {})
    if not project.get("id"):
        errors.append("Project: Missing required field 'id'")
    if not project.get("name"):
        errors.append("Project: Missing required field 'name'")
    
    # Validate modules
    modules = pkg_data.get("modules", [])
    for i, module in enumerate(modules):
        if not module.get("id"):
            errors.append(f"Module[{i}]: Missing required field 'id'")
        if not module.get("path"):
            errors.append(f"Module[{i}]: Missing required field 'path'")
    
    # Validate symbols
    symbols = pkg_data.get("symbols", [])
    for i, symbol in enumerate(symbols):
        if not symbol.get("id"):
            errors.append(f"Symbol[{i}]: Missing required field 'id'")
        if not symbol.get("moduleId"):
            errors.append(f"Symbol[{i}]: Missing required field 'moduleId'")
        if not symbol.get("name"):
            errors.append(f"Symbol[{i}]: Missing required field 'name'")
        if not symbol.get("kind"):
            errors.append(f"Symbol[{i}]: Missing required field 'kind'")
    
    # Validate endpoints
    endpoints = pkg_data.get("endpoints", [])
    for i, endpoint in enumerate(endpoints):
        if not endpoint.get("id"):
            errors.append(f"Endpoint[{i}]: Missing required field 'id'")
        if not endpoint.get("method"):
            errors.append(f"Endpoint[{i}]: Missing required field 'method'")
        if not endpoint.get("path"):
            errors.append(f"Endpoint[{i}]: Missing required field 'path'")
        if not endpoint.get("handlerModuleId"):
            errors.append(f"Endpoint[{i}]: Missing required field 'handlerModuleId'")
    
    return errors


def _validate_framework_metadata(pkg_data: Dict[str, Any]) -> List[str]:
    """Validate framework-aware metadata fields."""
    errors = []
    modules = pkg_data.get("modules", [])
    
    # Valid framework names
    valid_frameworks = [
        "angular", "react", "vue", "nestjs", "nextjs", "flask", "fastapi",
        "spring-boot", "aspnet-core", "django", "express"
    ]
    
    for i, module in enumerate(modules):
        # Validate frameworkConfidence
        framework_confidence = module.get("frameworkConfidence")
        if framework_confidence is not None:
            if not isinstance(framework_confidence, (int, float)):
                errors.append(f"Module[{i}]: frameworkConfidence must be a number")
            elif framework_confidence < 0.0 or framework_confidence > 1.0:
                errors.append(f"Module[{i}]: frameworkConfidence must be between 0.0 and 1.0, got {framework_confidence}")
        
        # Validate framework field
        framework = module.get("framework")
        if framework is not None and framework not in valid_frameworks:
            errors.append(f"Module[{i}]: Invalid framework '{framework}' (must be one of {valid_frameworks})")
        
        # Validate code snippets
        code_snippets = module.get("codeSnippets")
        if code_snippets:
            if isinstance(code_snippets, dict):
                for snippet_key, snippet_value in code_snippets.items():
                    if isinstance(snippet_value, str) and len(snippet_value) > 500:
                        errors.append(f"Module[{i}]: codeSnippets.{snippet_key} exceeds 500 characters")
                    elif isinstance(snippet_value, list):
                        for j, item in enumerate(snippet_value):
                            if isinstance(item, str) and len(item) > 200:
                                errors.append(f"Module[{i}]: codeSnippets.{snippet_key}[{j}] exceeds 200 characters")
    
    return errors


def validate_pkg_file(pkg_file_path: str, schema_path: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Validate PKG JSON file against the schema.
    
    Args:
        pkg_file_path: Path to PKG JSON file
        schema_path: Optional path to schema file
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        with open(pkg_file_path, 'r', encoding='utf-8') as f:
            pkg_data = json.load(f)
        return validate_pkg(pkg_data, schema_path)
    except FileNotFoundError:
        return False, f"PKG file not found: {pkg_file_path}"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {str(e)}"
    except Exception as e:
        return False, f"Validation failed: {str(e)}"


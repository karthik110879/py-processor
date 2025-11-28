"""Validate PKG JSON against project-schema.json."""

import json
import os
from typing import Dict, Any, Tuple, Optional
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
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        schema_path = os.path.join(project_root, "project-schema.json")
    
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_pkg(pkg_data: Dict[str, Any], schema_path: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Validate PKG data against the schema.
    
    Args:
        pkg_data: PKG dictionary to validate
        schema_path: Optional path to schema file
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        schema = load_schema(schema_path)
        validate(instance=pkg_data, schema=schema)
        return True, None
    except ValidationError as e:
        error_msg = f"Validation error at {'.'.join(str(p) for p in e.path)}: {e.message}"
        return False, error_msg
    except Exception as e:
        return False, f"Validation failed: {str(e)}"


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


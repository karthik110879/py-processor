import json, os
from typing import Dict, Any, Optional
from code_parser.parser import parse_python
from code_parser.parser import parse_typescript
from code_parser.normalizer import extract_python_definitions, extract_ts_definitions
from utils.file_utils import collect_files



def file_to_json(file_path: str) -> Optional[Dict[str, Any]]:
    """Parse a single file and return its normalized JSON representation."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        source: str = f.read()

    ext: str = os.path.splitext(file_path)[1].lower()
    if ext == ".py":
        root = parse_python(source)
        extracted: Dict[str, Any] = extract_python_definitions(root, source)
        language: str = "python"
    elif ext == ".ts":
        root = parse_typescript(source)
        extracted: Dict[str, Any] = extract_ts_definitions(root, source)
        language: str = "typescript"
    else:
        return None

    return {"language": language, **extracted}



def insert_nested(result_dict: Dict[str, Any], file_path: str, file_json: Dict[str, Any], repo_path: str) -> None:
    """Insert file JSON into nested dict structure based on repo folder hierarchy."""
    rel_path = os.path.relpath(file_path, repo_path)   # e.g. "examples/utils/helper.py"
    parts = rel_path.split(os.sep)                     # ["examples","utils","helper.py"]
    current = result_dict
    for p in parts[:-1]:                               # walk directories
        current = current.setdefault(p, {})
    current[parts[-1]] = file_json                     # assign file JSON at leaf



def repo_to_json(repo_path: str, output_path: str = "output/repo_parsed.json") -> Dict[str, Any]:
    """Parse all files in a repo and save structured JSON output that mirrors folder hierarchy."""
    files = collect_files(repo_path)
    result_dict: Dict[str, Any] = {}

    for f in files:
        parsed = file_to_json(f)
        if parsed:
            insert_nested(result_dict, f, parsed, repo_path)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out:
        json.dump(result_dict, out, indent=2)

    print(f"✅ Parsed {len(files)} files. Results saved to {output_path}")

    return result_dict

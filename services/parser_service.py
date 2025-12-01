import json
import os
import logging
from typing import Dict, Any, Optional
from code_parser.parser import parse_python
from code_parser.parser import parse_typescript
from code_parser.normalizer import extract_python_definitions, extract_ts_definitions
from code_parser.project_metadata import get_git_sha
from utils.file_utils import collect_files
from services.pkg_generator import PKGGenerator

logger = logging.getLogger(__name__)


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
    """
    Parse all files in a repo and save structured JSON output that mirrors folder hierarchy.
    
    This is the legacy function maintained for backward compatibility.
    For new PKG format, use generate_pkg() instead.
    """
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


def generate_pkg(
    repo_path: str,
    output_path: Optional[str] = None,
    fan_threshold: int = 3,
    include_features: bool = True,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Generate Project Knowledge Graph (PKG) JSON following project-schema.json.
    
    Automatically saves PKG to {repo_path}/pkg.json and implements caching
    based on git SHA to avoid expensive regeneration.
    
    Args:
        repo_path: Root path of the repository
        output_path: Optional path to save JSON file (defaults to {repo_path}/pkg.json)
        fan_threshold: Fan-in threshold for filtering detailed symbol info (default: 3)
        include_features: Whether to include feature groupings (default: True)
        use_cache: Whether to use cached PKG if available and valid (default: True)
        
    Returns:
        Complete PKG dictionary
    """
    # Determine output path - default to repo_path/pkg.json if not specified
    if output_path is None:
        output_path = os.path.join(repo_path, 'pkg.json')
    
    # Check cache if enabled
    if use_cache and os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                cached_pkg = json.load(f)
            
            # Validate cache by comparing git SHA
            current_sha = get_git_sha(repo_path)
            cached_sha = cached_pkg.get('gitSha')
            
            if cached_sha is not None and current_sha is not None:
                if cached_sha == current_sha:
                    logger.info(f"Using cached PKG for {repo_path} (git SHA: {current_sha[:8]}...)")
                    return cached_pkg
                else:
                    logger.info(f"Cache invalidated: git SHA changed ({cached_sha[:8]}... -> {current_sha[:8]}...)")
            elif cached_sha is None and current_sha is None:
                # Both are None (not a git repo), check if file is recent enough
                # For now, we'll regenerate if SHA is None to be safe
                logger.info("No git SHA available, regenerating PKG")
            else:
                logger.info("Git SHA mismatch, regenerating PKG")
        except Exception as e:
            logger.warning(f"Error reading cached PKG: {e}, regenerating...")
    
    # Generate new PKG
    logger.info(f"Generating PKG for {repo_path}")
    generator = PKGGenerator(
        repo_path=repo_path,
        fan_threshold=fan_threshold,
        include_features=include_features
    )
    
    pkg = generator.generate_pkg(output_path=output_path)
    logger.info(f"PKG generated and saved to {output_path}")
    
    return pkg

import os
from typing import List, Tuple, Optional

# Supported file extensions for all target languages
SUPPORTED_EXTENSIONS = (
    # Python
    ".py",
    # JavaScript/TypeScript
    ".js", ".jsx", ".ts", ".tsx",
    # Java
    ".java",
    # C/C++
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx",
    # C#
    ".cs",
    # Classic ASP
    ".asp", ".aspx",
)

def collect_files(
    repo_path: str,
    extensions: Optional[Tuple[str, ...]] = None,
    exclude_dirs: Optional[Tuple[str, ...]] = None
) -> List[str]:
    """
    Recursively collect files with given extensions from a repository path.

    Args:
        repo_path (str): Root directory to search.
        extensions (Tuple[str, ...], optional): File extensions to include.
            If None, uses all supported extensions.
        exclude_dirs (Tuple[str, ...], optional): Directory names to exclude
            (e.g., node_modules, .git, __pycache__).

    Returns:
        List[str]: List of full file paths.
    """
    if extensions is None:
        extensions = SUPPORTED_EXTENSIONS
    
    if exclude_dirs is None:
        exclude_dirs = (
            "node_modules", ".git", "__pycache__", ".venv", "venv",
            "target", "build", "dist", ".next", ".nuxt", "bin", "obj"
        )
    
    files = []
    for root, dirs, filenames in os.walk(repo_path):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for f in filenames:
            if f.lower().endswith(extensions):  # case-insensitive match
                files.append(os.path.join(root, f))
    
    return files


def collect_files_by_language(repo_path: str, languages: List[str]) -> List[str]:
    """
    Collect files filtered by programming languages.

    Args:
        repo_path (str): Root directory to search.
        languages (List[str]): List of language names to include
            (e.g., ['python', 'typescript', 'java']).

    Returns:
        List[str]: List of full file paths.
    """
    language_extensions = {
        "python": (".py",),
        "javascript": (".js", ".jsx"),
        "typescript": (".ts", ".tsx"),
        "java": (".java",),
        "c": (".c", ".h"),
        "cpp": (".cpp", ".cc", ".cxx", ".hpp", ".hxx"),
        "csharp": (".cs",),
        "asp": (".asp",),
        "aspx": (".aspx",),
    }
    
    extensions = []
    for lang in languages:
        if lang in language_extensions:
            extensions.extend(language_extensions[lang])
    
    if not extensions:
        return []
    
    return collect_files(repo_path, tuple(extensions))

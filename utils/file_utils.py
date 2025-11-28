import os
from typing import List, Tuple

def collect_files(repo_path: str, extensions: Tuple[str, ...] = (".py", ".ts")) -> List[str]:
    """
    Recursively collect files with given extensions from a repository path.

    Args:
        repo_path (str): Root directory to search.
        extensions (Tuple[str, ...]): File extensions to include.

    Returns:
        List[str]: List of full file paths.
    """
    files = []
    for root, _, filenames in os.walk(repo_path):
        for f in filenames:
            if f.lower().endswith(extensions):  # case-insensitive match
                files.append(os.path.join(root, f))
    return files

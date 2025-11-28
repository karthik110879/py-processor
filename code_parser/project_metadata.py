"""Extract project-level metadata including languages, build tools, and package managers."""

import os
import json
import re
import subprocess
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

from code_parser.framework_detector import detect_frameworks
from code_parser.multi_parser import detect_language
from utils.file_utils import collect_files


def detect_languages(repo_path: str) -> List[str]:
    """
    Detect all languages used in the repository.
    
    Args:
        repo_path: Root path of the repository
        
    Returns:
        List of unique language names
    """
    languages = set()
    
    # Collect all files
    files = collect_files(repo_path)
    
    for file_path in files:
        lang = detect_language(file_path)
        if lang:
            languages.add(lang)
    
    return sorted(list(languages))


def detect_build_tools(repo_path: str) -> List[str]:
    """
    Detect build tools from configuration files.
    
    Args:
        repo_path: Root path of the repository
        
    Returns:
        List of build tool names
    """
    build_tools = []
    repo_path_obj = Path(repo_path)
    
    # npm/yarn/pnpm
    if (repo_path_obj / "package.json").exists():
        build_tools.append("npm")
        if (repo_path_obj / "yarn.lock").exists():
            build_tools.append("yarn")
        if (repo_path_obj / "pnpm-lock.yaml").exists():
            build_tools.append("pnpm")
    
    # Maven
    if (repo_path_obj / "pom.xml").exists():
        build_tools.append("maven")
    
    # Gradle
    if (repo_path_obj / "build.gradle").exists() or (repo_path_obj / "build.gradle.kts").exists():
        build_tools.append("gradle")
    
    # .NET
    if list(repo_path_obj.rglob("*.csproj")):
        build_tools.append("dotnet")
    
    # CMake
    if (repo_path_obj / "CMakeLists.txt").exists():
        build_tools.append("cmake")
    
    # Make
    if (repo_path_obj / "Makefile").exists():
        build_tools.append("make")
    
    return build_tools


def get_git_sha(repo_path: str) -> Optional[str]:
    """
    Get the current git commit SHA if the repository is a git repo.
    
    Args:
        repo_path: Root path of the repository
        
    Returns:
        Git commit SHA or None
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    
    return None


def extract_project_metadata(repo_path: str) -> Dict[str, Any]:
    """
    Extract comprehensive project metadata.
    
    Args:
        repo_path: Root path of the repository
        
    Returns:
        Dictionary with project metadata
    """
    repo_path_obj = Path(repo_path)
    repo_name = repo_path_obj.name
    
    # Detect languages
    languages = detect_languages(repo_path)
    
    # Detect frameworks
    frameworks = detect_frameworks(repo_path)
    
    # Detect build tools
    build_tools = detect_build_tools(repo_path)
    
    # Get git SHA
    git_sha = get_git_sha(repo_path)
    
    # Extract package manager metadata
    metadata = {}
    
    # Node.js metadata
    package_json = repo_path_obj / "package.json"
    if package_json.exists():
        try:
            with open(package_json, 'r', encoding='utf-8') as f:
                pkg_data = json.load(f)
                metadata["packageManager"] = "npm"
                if "name" in pkg_data:
                    metadata["packageName"] = pkg_data["name"]
                if "version" in pkg_data:
                    metadata["packageVersion"] = pkg_data["version"]
        except Exception:
            pass
    
    # Java metadata
    pom_xml = repo_path_obj / "pom.xml"
    if pom_xml.exists():
        try:
            with open(pom_xml, 'r', encoding='utf-8') as f:
                content = f.read()
                # Simple extraction of groupId and artifactId
                group_match = re.search(r'<groupId>([^<]+)</groupId>', content)
                artifact_match = re.search(r'<artifactId>([^<]+)</artifactId>', content)
                if group_match and artifact_match:
                    metadata["mavenGroupId"] = group_match.group(1)
                    metadata["mavenArtifactId"] = artifact_match.group(1)
        except Exception:
            pass
    
    # .NET metadata
    csproj_files = list(repo_path_obj.rglob("*.csproj"))
    if csproj_files:
        try:
            with open(csproj_files[0], 'r', encoding='utf-8') as f:
                content = f.read()
                # Extract project name
                name_match = re.search(r'<PropertyGroup>.*?<AssemblyName>([^<]+)</AssemblyName>', content, re.DOTALL)
                if name_match:
                    metadata["dotnetAssemblyName"] = name_match.group(1)
        except Exception:
            pass
    
    return {
        "id": repo_name,
        "name": repo_name,
        "rootPath": repo_path,
        "languages": languages,
        "frameworks": frameworks,
        "buildTools": build_tools,
        "gitSha": git_sha,
        "metadata": metadata
    }


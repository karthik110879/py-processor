"""Framework detection from package files and static analysis."""

import os
import json
import re
from typing import List, Set, Dict, Any
from pathlib import Path


def _should_exclude_path(file_path: Path, repo_path: Path) -> bool:
    """
    Check if path should be excluded from framework detection.
    
    Args:
        file_path: Path to check
        repo_path: Root path of the repository
        
    Returns:
        True if path should be excluded (contains cloned_repos), False otherwise
    """
    try:
        relative_path = file_path.relative_to(repo_path)
        return "cloned_repos" in relative_path.parts
    except ValueError:
        return False


def detect_frameworks_from_package_files(repo_path: str) -> Set[str]:
    """
    Detect frameworks from package manager files.
    
    Args:
        repo_path: Root path of the repository
        
    Returns:
        Set of detected framework names
    """
    frameworks = set()
    repo_path_obj = Path(repo_path)
    
    # Node.js / JavaScript frameworks
    package_json = repo_path_obj / "package.json"
    if package_json.exists():
        try:
            with open(package_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                
                # NestJS
                if "@nestjs/core" in deps or "@nestjs/common" in deps:
                    frameworks.add("nestjs")
                
                # Express
                if "express" in deps:
                    frameworks.add("express")
                
                # Fastify
                if "fastify" in deps:
                    frameworks.add("fastify")
                
                # Koa
                if "koa" in deps:
                    frameworks.add("koa")
                
                # React
                if "react" in deps:
                    frameworks.add("react")
                
                # Angular
                if "@angular/core" in deps:
                    frameworks.add("angular")
                
                # Vue
                if "vue" in deps or "@vue/core" in deps:
                    frameworks.add("vue")
                
                # Next.js
                if "next" in deps:
                    frameworks.add("nextjs")
        except Exception:
            pass
    
    # Python frameworks
    requirements_txt = repo_path_obj / "requirements.txt"
    if requirements_txt.exists():
        try:
            with open(requirements_txt, 'r', encoding='utf-8') as f:
                content = f.read().lower()
                if "fastapi" in content:
                    frameworks.add("fastapi")
                if "flask" in content:
                    frameworks.add("flask")
                if "django" in content:
                    frameworks.add("django")
        except Exception:
            pass
    
    # Java frameworks
    pom_xml = repo_path_obj / "pom.xml"
    if pom_xml.exists():
        try:
            with open(pom_xml, 'r', encoding='utf-8') as f:
                content = f.read()
                if "spring-boot" in content or "springframework" in content:
                    frameworks.add("spring-boot")
                if "spring-web" in content:
                    frameworks.add("spring-mvc")
        except Exception:
            pass
    
    build_gradle = repo_path_obj / "build.gradle"
    if build_gradle.exists():
        try:
            with open(build_gradle, 'r', encoding='utf-8') as f:
                content = f.read()
                if "spring-boot" in content or "org.springframework" in content:
                    frameworks.add("spring-boot")
        except Exception:
            pass
    
    # .NET frameworks
    for csproj_file in repo_path_obj.rglob("*.csproj"):
        # Skip files in cloned_repos directory
        if _should_exclude_path(csproj_file, repo_path_obj):
            continue
        try:
            with open(csproj_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if "Microsoft.AspNetCore" in content:
                    frameworks.add("aspnet-core")
                if "Microsoft.AspNetCore.Mvc" in content:
                    frameworks.add("aspnet-mvc")
                if "Microsoft.AspNetCore.WebApi" in content:
                    frameworks.add("aspnet-webapi")
        except Exception:
            pass
    
    web_config = repo_path_obj / "web.config"
    if web_config.exists():
        frameworks.add("aspnet-classic")
    
    return frameworks


def detect_frameworks_from_static_analysis(repo_path: str) -> Set[str]:
    """
    Detect frameworks from static code analysis (imports, decorators, annotations).
    
    Args:
        repo_path: Root path of the repository
        
    Returns:
        Set of detected framework names
    """
    frameworks = set()
    repo_path_obj = Path(repo_path)
    
    # Patterns for framework detection
    patterns = {
        "nestjs": [
            r"@nestjs/",
            r"@Controller\(",
            r"@Injectable\(",
            r"@Module\(",
        ],
        "express": [
            r"require\(['\"]express['\"]\)",
            r"from ['\"]express['\"]",
            r"app\.(get|post|put|delete|use)\(",
            r"router\.(get|post|put|delete)\(",
        ],
        "fastapi": [
            r"from fastapi import",
            r"@app\.(get|post|put|delete)\(",
            r"@router\.(get|post|put|delete)\(",
        ],
        "flask": [
            r"from flask import",
            r"@app\.route\(",
            r"Flask\(",
            r"flask\.",
        ],
        "spring-boot": [
            r"@RestController",
            r"@Controller",
            r"@Service",
            r"@Repository",
            r"@SpringBootApplication",
            r"import org\.springframework",
        ],
        "aspnet-core": [
            r"\[Route\(",
            r"\[HttpGet\]",
            r"\[HttpPost\]",
            r"using Microsoft\.AspNetCore",
        ],
        "react": [
            r"import.*from ['\"]react['\"]",
            r"React\.(createElement|Component)",
        ],
        "angular": [
            r"@Component\(",
            r"@Injectable\(",
            r"import.*@angular/",
        ],
        "vue": [
            r"import.*from ['\"]vue['\"]",
            r"Vue\.(component|directive)",
        ],
    }
    
    # Search in common source directories
    source_dirs = ["src", "lib", "app", "server", "client", "backend", "frontend"]
    
    for source_dir in source_dirs:
        src_path = repo_path_obj / source_dir
        if not src_path.exists():
            continue
        
        # Skip source directories inside cloned_repos
        if _should_exclude_path(src_path, repo_path_obj):
            continue
        
        # Search in TypeScript/JavaScript files
        for ext in ["*.ts", "*.js", "*.tsx", "*.jsx"]:
            for file_path in src_path.rglob(ext):
                # Skip files in cloned_repos directory
                if _should_exclude_path(file_path, repo_path_obj):
                    continue
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        for framework, pattern_list in patterns.items():
                            for pattern in pattern_list:
                                if re.search(pattern, content, re.IGNORECASE):
                                    frameworks.add(framework)
                                    break
                except Exception:
                    continue
        
        # Search in Python files
        for file_path in src_path.rglob("*.py"):
            # Skip files in cloned_repos directory
            if _should_exclude_path(file_path, repo_path_obj):
                continue
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    for framework, pattern_list in patterns.items():
                        if framework in ("fastapi", "flask"):
                            for pattern in pattern_list:
                                if re.search(pattern, content, re.IGNORECASE):
                                    frameworks.add(framework)
                                    break
            except Exception:
                continue
        
        # Search in Java files
        for file_path in src_path.rglob("*.java"):
            # Skip files in cloned_repos directory
            if _should_exclude_path(file_path, repo_path_obj):
                continue
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    for framework, pattern_list in patterns.items():
                        if framework in ("spring-boot", "spring-mvc"):
                            for pattern in pattern_list:
                                if re.search(pattern, content, re.IGNORECASE):
                                    frameworks.add(framework)
                                    break
            except Exception:
                continue
        
        # Search in C# files
        for file_path in src_path.rglob("*.cs"):
            # Skip files in cloned_repos directory
            if _should_exclude_path(file_path, repo_path_obj):
                continue
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    for framework, pattern_list in patterns.items():
                        if framework.startswith("aspnet"):
                            for pattern in pattern_list:
                                if re.search(pattern, content, re.IGNORECASE):
                                    frameworks.add(framework)
                                    break
            except Exception:
                continue
    
    return frameworks


def detect_frameworks(repo_path: str) -> List[str]:
    """
    Detect frameworks from both package files and static analysis.
    
    Args:
        repo_path: Root path of the repository
        
    Returns:
        List of detected framework names (sorted, with root-level Python frameworks prioritized)
    """
    frameworks = set()
    repo_path_obj = Path(repo_path)
    
    # Prioritize root-level requirements.txt - check it first
    root_requirements = repo_path_obj / "requirements.txt"
    root_python_frameworks = set()
    if root_requirements.exists():
        try:
            with open(root_requirements, 'r', encoding='utf-8') as f:
                content = f.read().lower()
                if "flask" in content:
                    root_python_frameworks.add("flask")
                if "fastapi" in content:
                    root_python_frameworks.add("fastapi")
                if "django" in content:
                    root_python_frameworks.add("django")
        except Exception:
            pass
    
    # Detect from package files
    frameworks.update(detect_frameworks_from_package_files(repo_path))
    
    # Detect from static analysis
    frameworks.update(detect_frameworks_from_static_analysis(repo_path))
    
    # If root-level Python frameworks were found, prioritize them
    # by moving them to the front of the sorted list
    if root_python_frameworks:
        all_frameworks = sorted(list(frameworks))
        prioritized = []
        # Add root Python frameworks first
        for fw in sorted(root_python_frameworks):
            if fw in all_frameworks:
                prioritized.append(fw)
        # Add remaining frameworks
        for fw in all_frameworks:
            if fw not in prioritized:
                prioritized.append(fw)
        return prioritized
    
    return sorted(list(frameworks))


"""Planner - Generates step-by-step code change plans using LLM."""

import logging
import os
import uuid
from typing import Dict, Any, List, Optional
from langchain_openai import ChatOpenAI
from utils.config import Config

logger = logging.getLogger(__name__)


class Planner:
    """Generates structured code change plans using LLM."""
    
    def __init__(self):
        """Initialize the planner."""
        self.llm = None
        self._init_llm()
    
    def _init_llm(self) -> None:
        """Initialize LLM for planning."""
        try:
            config = Config()
            api_key = config.openai_api_key
            if not api_key:
                logger.warning("OPENAI_API_KEY not set, planning will be limited")
                return
            
            self.llm = ChatOpenAI(
                model=config.llm_model,
                temperature=config.llm_temperature,
                max_tokens=config.llm_max_tokens,
                openai_api_key=api_key
            )
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}", exc_info=True)
            self.llm = None
    
    def generate_plan(
        self,
        intent: Dict[str, Any],
        impact_result: Dict[str, Any],
        constraints: List[str],
        pkg_data: Optional[Dict[str, Any]] = None,
        repo_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a step-by-step code change plan.
        
        Args:
            intent: Intent dictionary
            impact_result: Impact analysis result
            constraints: List of constraints
            pkg_data: Optional PKG data dictionary for context-aware planning
            repo_path: Optional repository path for file validation
            
        Returns:
            Plan dictionary with tasks
        """
        if not self.llm:
            return self._fallback_plan(intent, impact_result, constraints)
        
        try:
            plan = self._call_llm(intent, impact_result, constraints, pkg_data)
            # Validate files if repo_path provided
            if repo_path:
                validation_result = self._validate_files_exist(plan, repo_path, pkg_data)
                plan['validation'] = validation_result
            return plan
        except Exception as e:
            logger.error(f"LLM planning failed: {e}", exc_info=True)
            return self._fallback_plan(intent, impact_result, constraints)
    
    def _should_exclude_path(self, file_path: str) -> bool:
        """Check if path should be excluded from framework detection."""
        return "cloned_repos" in file_path.replace("\\", "/")
    
    def _find_file_by_name(self, filename: str, repo_path: str) -> Optional[Dict[str, Any]]:
        """
        Find file by name using fuzzy matching (reused from code_editor logic).
        
        Args:
            filename: Filename to search for
            repo_path: Repository root path
            
        Returns:
            Dictionary with 'path' (relative path), 'confidence' (0.0-1.0), 'method' (str)
            or None if no match found
        """
        config = Config()
        if not config.fuzzy_file_matching_enabled:
            return None
        
        filename_lower = filename.lower()
        filename_no_ext = os.path.splitext(filename_lower)[0]
        
        best_match = None
        best_confidence = 0.0
        
        # Recursively search all files in repo
        for root, dirs, files in os.walk(repo_path):
            # Skip hidden directories and common ignore patterns
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', '.git']]
            
            for file in files:
                file_lower = file.lower()
                file_no_ext = os.path.splitext(file_lower)[0]
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, repo_path)
                
                confidence = 0.0
                method = None
                
                # Exact filename match (case-insensitive)
                if file_lower == filename_lower:
                    confidence = 1.0
                    method = "exact_filename"
                # Exact filename without extension match
                elif file_no_ext == filename_no_ext:
                    confidence = 0.95
                    method = "exact_no_ext"
                # Partial substring match in filename
                elif filename_lower in file_lower or file_lower in filename_lower:
                    # Calculate match ratio
                    longer = max(len(filename_lower), len(file_lower))
                    shorter = min(len(filename_lower), len(file_lower))
                    match_ratio = shorter / longer if longer > 0 else 0.0
                    confidence = 0.7 + (match_ratio * 0.2)  # 0.7-0.9 range
                    method = "partial_match"
                # Partial match in filename without extension
                elif filename_no_ext in file_no_ext or file_no_ext in filename_no_ext:
                    longer = max(len(filename_no_ext), len(file_no_ext))
                    shorter = min(len(filename_no_ext), len(file_no_ext))
                    match_ratio = shorter / longer if longer > 0 else 0.0
                    confidence = 0.65 + (match_ratio * 0.15)  # 0.65-0.8 range
                    method = "partial_no_ext"
                
                # Update best match if this is better
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = {
                        "path": rel_path.replace('\\', '/'),  # Normalize path separators
                        "full_path": full_path,
                        "confidence": confidence,
                        "method": method
                    }
        
        if best_match and best_confidence >= config.fuzzy_match_confidence_threshold:
            logger.debug(f"Fuzzy file match found: {filename} -> {best_match['path']} (confidence: {best_confidence:.2f})")
            return best_match
        
        return None
    
    def _validate_files_exist(
        self,
        plan: Dict[str, Any],
        repo_path: Optional[str],
        pkg_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate that all files in the plan exist, using fuzzy matching if needed.
        Also validates framework consistency.
        
        Args:
            plan: Plan dictionary with tasks
            repo_path: Repository root path
            pkg_data: Optional PKG data for querying file paths
            
        Returns:
            Validation results dictionary
        """
        config = Config()
        if not config.enable_file_validation:
            return {"valid": True, "missing_files": [], "found_files": [], "framework_warnings": []}
        
        if not repo_path or not os.path.exists(repo_path):
            logger.warning("Cannot validate files: repo_path not provided or does not exist")
            return {"valid": False, "missing_files": [], "found_files": [], "framework_warnings": [], "error": "repo_path invalid"}
        
        missing_files = []
        found_files = []
        framework_warnings = []
        all_valid = True
        
        tasks = plan.get('tasks', [])
        for task in tasks:
            files = task.get('files', [])
            for file_path in files:
                # Resolve full path
                full_path = os.path.join(repo_path, file_path)
                
                if os.path.exists(full_path):
                    found_files.append({
                        "original": file_path,
                        "resolved": file_path,
                        "method": "exact"
                    })
                    
                    # Validate framework consistency for existing files
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        framework_validation = self._validate_framework_consistency(
                            file_path, content, pkg_data
                        )
                        
                        if framework_validation.get('warnings'):
                            framework_warnings.extend([
                                {
                                    "file": file_path,
                                    "warning": w
                                }
                                for w in framework_validation.get('warnings', [])
                            ])
                    except Exception as e:
                        logger.debug(f"Failed to validate framework for {file_path}: {e}")
                else:
                    # Try fuzzy matching
                    filename = os.path.basename(file_path)
                    fuzzy_match = self._find_file_by_name(filename, repo_path)
                    
                    if fuzzy_match:
                        found_files.append({
                            "original": file_path,
                            "resolved": fuzzy_match['path'],
                            "method": "fuzzy",
                            "confidence": fuzzy_match['confidence']
                        })
                        # Update the file path in the task
                        file_index = files.index(file_path)
                        files[file_index] = fuzzy_match['path']
                        logger.info(f"Updated file path in plan: {file_path} -> {fuzzy_match['path']}")
                    else:
                        # Try PKG query if available
                        suggestions = []
                        if pkg_data:
                            try:
                                from services.pkg_query_engine import PKGQueryEngine
                                query_engine = PKGQueryEngine(pkg_data)
                                pkg_modules = query_engine.get_modules_by_filename(filename)
                                if pkg_modules:
                                    suggestions = [m.get('path', '') for m in pkg_modules[:3]]
                            except Exception as e:
                                logger.debug(f"PKG query for file validation failed: {e}")
                        
                        missing_files.append({
                            "file": file_path,
                            "suggestions": suggestions
                        })
                        all_valid = False
        
        return {
            "valid": all_valid,
            "missing_files": missing_files,
            "found_files": found_files,
            "framework_warnings": framework_warnings
        }
    
    def _validate_framework_consistency(
        self,
        file_path: str,
        content: str,
        pkg_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate framework consistency between file content, extension, and PKG data.
        
        Args:
            file_path: Path to the file
            content: File content string
            pkg_data: Optional PKG data dictionary
            
        Returns:
            Dictionary with validation results
        """
        warnings = []
        detected_framework = self._detect_framework_from_content(content, file_path)
        pkg_framework = None
        
        # Get PKG framework if available
        if pkg_data:
            frameworks = pkg_data.get('project', {}).get('frameworks', [])
            if frameworks:
                pkg_framework = frameworks[0].lower()
        
        # Validate file extension matches detected framework
        ext = os.path.splitext(file_path)[1].lower()
        if detected_framework == 'react' and ext != '.tsx' and ext != '.jsx':
            if ext == '.ts' or ext == '.js':
                warnings.append(f"React framework detected but file extension is {ext} (expected .tsx or .jsx)")
        elif detected_framework == 'angular' and ext == '.tsx':
            warnings.append(f"Angular framework detected but file extension is .tsx (Angular uses .ts for components)")
        elif detected_framework == 'vue' and ext != '.vue':
            warnings.append(f"Vue framework detected but file extension is {ext} (expected .vue)")
        
        # Validate imports match framework patterns
        content_lower = content.lower()
        if detected_framework == 'angular':
            if 'from \'react\'' in content_lower or 'from "react"' in content_lower:
                warnings.append("Angular file contains React imports - framework mismatch")
        elif detected_framework == 'react':
            if '@component' in content_lower or '@ngmodule' in content_lower:
                warnings.append("React file contains Angular decorators - framework mismatch")
        
        # Compare PKG framework with detected framework
        if pkg_framework and detected_framework:
            if pkg_framework != detected_framework:
                warnings.append(
                    f"Framework mismatch: PKG indicates '{pkg_framework}' but file content indicates '{detected_framework}'"
                )
        
        return {
            "valid": len(warnings) == 0,
            "detected_framework": detected_framework,
            "pkg_framework": pkg_framework,
            "warnings": warnings
        }
    
    def _detect_framework_from_content(self, content: str, file_path: str) -> Optional[str]:
        """
        Detect framework from file content (imports, decorators, syntax).
        
        Args:
            content: File content string
            file_path: Path to the file
            
        Returns:
            Framework name or None
        """
        content_lower = content.lower()
        ext = os.path.splitext(file_path)[1].lower()
        
        # Check for Angular patterns
        if ('@component' in content_lower or 
            '@ngmodule' in content_lower or 
            '@angular/core' in content_lower):
            return 'angular'
        
        # Check for React patterns
        if ('import react' in content_lower or 
            "from 'react'" in content_lower or
            'usestate' in content_lower or
            (ext == '.tsx' and 'return (' in content_lower)):
            return 'react'
        
        # Check for Vue patterns
        if (ext == '.vue' or
            'definecomponent' in content_lower or
            "from 'vue'" in content_lower):
            return 'vue'
        
        # Check for Next.js patterns
        if ('next/router' in content_lower or
            'next/link' in content_lower):
            return 'nextjs'
        
        # Check for NestJS patterns
        if ('@controller' in content_lower or
            '@injectable' in content_lower or
            '@nestjs/common' in content_lower):
            return 'nestjs'
        
        # Check for Flask patterns
        if ('from flask import' in content_lower or
            '@app.route' in content_lower):
            return 'flask'
        
        # Default based on extension
        if ext == '.tsx':
            return 'react'
        
        return None
    
    def _analyze_project_structure(self, repo_path: Optional[str], pkg_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze actual project structure to infer framework and file patterns.
        
        Args:
            repo_path: Path to repository root
            pkg_data: Optional PKG data dictionary
            
        Returns:
            Dictionary with 'framework', 'file_patterns', 'examples', 'hints'
        """
        import os
        import glob
        
        if not repo_path or not os.path.exists(repo_path):
            return {'framework': None, 'file_patterns': [], 'examples': [], 'hints': {}}
        
        framework_hints = {}
        file_patterns = []
        examples = []
        
        # Prioritize root-level Python/Flask detection
        root_requirements = os.path.join(repo_path, 'requirements.txt')
        root_app_py = os.path.join(repo_path, 'app.py')
        flask_detected = False
        
        if os.path.exists(root_requirements):
            try:
                with open(root_requirements, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                    if "flask" in content:
                        flask_detected = True
                        framework_hints['flask'] = 100  # High priority
                        examples.append('requirements.txt')
            except Exception:
                pass
        
        if os.path.exists(root_app_py):
            flask_detected = True
            if 'flask' not in framework_hints:
                framework_hints['flask'] = 100
            examples.append('app.py')
        
        # Check for Flask imports in root-level Python files (excluding cloned_repos)
        if not flask_detected:
            root_py_files = glob.glob(os.path.join(repo_path, '*.py'), recursive=False)
            for py_file in root_py_files:
                if self._should_exclude_path(py_file):
                    continue
                try:
                    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if 'from flask import' in content or 'import flask' in content or 'Flask(' in content:
                            flask_detected = True
                            framework_hints['flask'] = 50
                            examples.append(os.path.relpath(py_file, repo_path))
                            break
                except Exception:
                    continue
        
        # Check for Angular patterns (filter out cloned_repos)
        angular_components = [f for f in glob.glob(os.path.join(repo_path, '**/*.component.ts'), recursive=True) 
                             if not self._should_exclude_path(f)]
        angular_modules = [f for f in glob.glob(os.path.join(repo_path, '**/*.module.ts'), recursive=True) 
                          if not self._should_exclude_path(f)]
        angular_app_dir = os.path.exists(os.path.join(repo_path, 'src', 'app'))
        
        if angular_components or angular_modules or angular_app_dir:
            framework_hints['angular'] = len(angular_components) + len(angular_modules)
            if angular_components:
                examples.extend([os.path.relpath(f, repo_path) for f in angular_components[:3]])
        
        # Check for React patterns (filter out cloned_repos)
        react_components = [f for f in glob.glob(os.path.join(repo_path, '**/*.tsx'), recursive=True) 
                           if not self._should_exclude_path(f)]
        react_jsx = [f for f in glob.glob(os.path.join(repo_path, '**/*.jsx'), recursive=True) 
                    if not self._should_exclude_path(f)]
        react_components_dir = os.path.exists(os.path.join(repo_path, 'src', 'components'))
        
        if react_components or react_jsx or react_components_dir:
            framework_hints['react'] = len(react_components) + len(react_jsx)
            if react_components:
                examples.extend([os.path.relpath(f, repo_path) for f in react_components[:3]])
        
        # Determine primary framework from hints (prioritize Flask if detected)
        detected_framework = None
        if framework_hints:
            # Flask gets highest priority if detected
            if 'flask' in framework_hints:
                detected_framework = 'flask'
            else:
                detected_framework = max(framework_hints.items(), key=lambda x: x[1])[0]
        
        return {
            'framework': detected_framework,
            'file_patterns': file_patterns,
            'examples': examples,
            'hints': framework_hints
        }
    
    def _call_llm(
        self,
        intent: Dict[str, Any],
        impact_result: Dict[str, Any],
        constraints: List[str],
        pkg_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call LLM to generate plan.
        
        Args:
            intent: Intent dictionary
            impact_result: Impact analysis result
            constraints: List of constraints
            pkg_data: Optional PKG data dictionary for context-aware planning
            
        Returns:
            Plan dictionary
        """
        # Prepare module summaries for context
        impacted_modules = impact_result.get('impacted_modules', [])
        module_summaries = []
        
        for module in impacted_modules[:10]:  # Limit to first 10 for context
            module_info = {
                "id": module.get('id'),
                "path": module.get('path'),
                "summary": module.get('moduleSummary', ''),
                "kind": module.get('kind', [])
            }
            module_summaries.append(module_info)
        
        # Extract PKG context if available
        pkg_context = ""
        framework_type = 'unknown'  # Initialize framework_type
        
        # Analyze actual project structure as fallback
        repo_path = None
        if pkg_data and pkg_data.get('project', {}).get('rootPath'):
            repo_path = pkg_data['project']['rootPath']
        
        structure_analysis = self._analyze_project_structure(repo_path, pkg_data)
        structure_framework = structure_analysis.get('framework')
        structure_examples = structure_analysis.get('examples', [])
        
        logger.info(f"📁 PROJECT STRUCTURE ANALYSIS | Framework: {structure_framework} | Examples: {len(structure_examples)} files")
        
        if pkg_data:
            try:
                from services.pkg_query_engine import PKGQueryEngine
                from agents.code_context_analyzer import CodeContextAnalyzer
                
                query_engine = PKGQueryEngine(pkg_data)
                context_analyzer = CodeContextAnalyzer(pkg_data, query_engine)
                
                # Extract framework patterns from project
                project = pkg_data.get('project', {})
                frameworks = project.get('frameworks', [])
                primary_framework = frameworks[0] if frameworks else None
                framework_type = primary_framework if primary_framework else 'unknown'
                logger.info(f"🔍 FRAMEWORK DETECTION | Detected frameworks: {frameworks} | Primary: {framework_type}")
                
                # Use structure analysis if PKG frameworks are empty or unknown
                if (not frameworks or framework_type == 'unknown') and structure_framework:
                    framework_type = structure_framework
                    logger.info(f"🔍 FRAMEWORK FROM STRUCTURE | Detected: {framework_type} | Examples: {structure_examples[:2]}")
                
                languages = project.get('languages', [])
                
                # Get framework patterns from impacted modules
                framework_patterns = []
                import_patterns = []
                code_conventions = []
                
                for module in impacted_modules[:5]:  # Limit to first 5 for context
                    module_id = module.get('id')
                    if module_id:
                        try:
                            patterns = context_analyzer.extract_code_patterns(module_id)
                            # Only override framework_type if it's still unknown
                            if framework_type == 'unknown' and patterns.get('framework_type'):
                                framework_type = patterns.get('framework_type')
                            if patterns.get('patterns'):
                                framework_patterns.extend(patterns.get('patterns', [])[:3])
                            if patterns.get('style', {}).get('import_style'):
                                import_patterns.append(patterns['style']['import_style'])
                            if patterns.get('style', {}).get('naming_convention'):
                                code_conventions.append(patterns['style']['naming_convention'])
                        except Exception as e:
                            logger.debug(f"Failed to extract patterns for module {module_id}: {e}")
                
                # Build PKG context string
                pkg_context_parts = []
                # Don't repeat framework here since it's at the top of the prompt
                if languages:
                    pkg_context_parts.append(f"Languages: {', '.join(languages)}")
                if framework_patterns:
                    unique_patterns = list(set(framework_patterns))[:5]
                    pkg_context_parts.append(f"Code Patterns: {', '.join(unique_patterns)}")
                if import_patterns:
                    unique_imports = list(set(import_patterns))[:3]
                    pkg_context_parts.append(f"Import Style: {', '.join(unique_imports)}")
                if code_conventions:
                    unique_conventions = list(set(code_conventions))[:3]
                    pkg_context_parts.append(f"Naming Conventions: {', '.join(unique_conventions)}")
                
                if pkg_context_parts:
                    pkg_context = "\n\nProject Context (from knowledge graph):\n" + "\n".join(f"- {part}" for part in pkg_context_parts) + "\n"
                    pkg_context += "\nIMPORTANT: Follow the project's framework patterns, import styles, and naming conventions shown above when planning changes.\n"
                
            except Exception as e:
                logger.warning(f"Failed to extract PKG context for planning: {e}", exc_info=True)
                # Continue without PKG context if extraction fails
        
        # Add structure examples to context
        if structure_examples:
            pkg_context += f"\n\nExisting Project Files (follow these patterns):\n"
            for example in structure_examples[:5]:
                pkg_context += f"- {example}\n"
        
        # Build framework-specific instruction
        framework_instruction = ""
        if framework_type and framework_type != 'unknown':
            framework_instruction = self._build_framework_instruction(framework_type)
        
        prompt = f"""{framework_instruction}You are a code-change planner. Given the following information, produce a detailed, step-by-step plan for implementing the requested changes.

Intent: {intent.get('description', '')}
Intent Type: {intent.get('intent', 'unknown')}
Risk Level: {impact_result.get('risk_score', 'medium')}

Impacted Modules ({len(impacted_modules)} total):
{self._format_modules_for_prompt(module_summaries)}

Impacted Files: {len(impact_result.get('impacted_files', []))} files
Affected Tests: {len(impact_result.get('affected_tests', []))} test files

Constraints:
{chr(10).join(f"- {c}" for c in constraints) if constraints else "- None specified"}
{pkg_context}

Produce a numbered plan of code edits with:
1. Files to modify (relative path from repo root)
2. Specific changes (add field, update method signature, call new function, etc.)
3. Tests to add/change (file path + test name/description)
4. Migration steps if database changes are required
5. CI changes if needed

For each task, provide:
- task: Clear description of what to do
- files: Array of file paths to modify
- changes: Array of specific change descriptions
- tests: Array of test files and test descriptions
- notes: Any important notes (migrations, breaking changes, etc.)
- estimated_time: Rough time estimate (e.g., "15min", "1h")

Return a JSON object with this structure:
{self._get_example_json(framework_type)}

IMPORTANT: Follow the framework-specific file naming and extensions shown in the example above.

Be specific, actionable, and consider the constraints. Order tasks logically (dependencies first)."""

        try:
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Parse JSON from response
            import json
            import re
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                plan_dict = json.loads(json_str)
            else:
                # Fallback parsing
                plan_dict = self._parse_plan_from_text(content)
            
            # Normalize plan
            plan_dict = self._normalize_plan(plan_dict, intent, impact_result)
            
            # Validate and correct file extensions based on framework
            # Use structure_framework as fallback for validation
            validation_framework = framework_type if framework_type != 'unknown' else structure_framework
            if validation_framework and validation_framework.lower() == 'angular':
                for task in plan_dict.get('tasks', []):
                    corrected_files = []
                    for file_path in task.get('files', []):
                        # Replace .tsx with .ts for Angular
                        if file_path.endswith('.tsx'):
                            corrected = file_path.replace('.tsx', '.ts')
                            logger.warning(f"⚠️  CORRECTED FILE EXTENSION | {file_path} -> {corrected} (Angular requires .ts, not .tsx)")
                            corrected_files.append(corrected)
                        else:
                            corrected_files.append(file_path)
                    task['files'] = corrected_files
            elif validation_framework and validation_framework.lower() == 'react':
                # For React, we could validate .tsx usage, but React can also use .ts for non-component files
                # So we'll just log if we see .ts files that might be components
                for task in plan_dict.get('tasks', []):
                    for file_path in task.get('files', []):
                        # Warn if React component might be using .ts instead of .tsx
                        if file_path.endswith('.ts') and any(keyword in file_path.lower() for keyword in ['component', 'page', 'view']):
                            logger.debug(f"React component using .ts extension: {file_path} (consider .tsx for components)")
            
            return plan_dict
        
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}", exc_info=True)
            return self._fallback_plan(intent, impact_result, constraints)
    
    def _format_modules_for_prompt(self, modules: List[Dict[str, Any]]) -> str:
        """Format modules for prompt."""
        lines = []
        for i, module in enumerate(modules, 1):
            path = module.get('path', 'unknown')
            summary = module.get('summary', 'No summary')
            kind = ', '.join(module.get('kind', []))
            lines.append(f"{i}. {path} ({kind})")
            if summary:
                lines.append(f"   Summary: {summary[:100]}")
        return '\n'.join(lines) if lines else "No modules found"
    
    def _build_framework_instruction(self, framework_type: str) -> str:
        """
        Build framework-specific instruction string with file naming rules.
        
        Args:
            framework_type: Framework name (e.g., 'angular', 'react')
            
        Returns:
            Framework instruction string
        """
        framework_lower = framework_type.lower()
        
        if framework_lower == 'angular':
            return """
CRITICAL FRAMEWORK REQUIREMENT: This is an ANGULAR project. You MUST:
- Use .ts file extensions for components (NOT .tsx)
- Use Angular component syntax: @Component decorator
- Use Angular imports: @angular/core, @angular/common, etc.
- Follow Angular file structure: component.ts, component.html, component.css
- Use Angular naming: login.component.ts (NOT Login.tsx)
- File paths should be: src/components/login/login.component.ts
- Separate files for template (.html) and styles (.css)

REMEMBER: Use .ts for Angular components, NOT .tsx. Example: login.component.ts is correct, Login.tsx is WRONG for Angular.

"""
        elif framework_lower == 'react':
            return """
CRITICAL FRAMEWORK REQUIREMENT: This is a REACT project. You MUST:
- Use .tsx file extensions for components (NOT .ts)
- Use React component syntax: function components or class components
- Use React imports: import React from 'react'
- File paths should be: src/components/Login.tsx
- Use PascalCase for component file names: Login.tsx, UserProfile.tsx

"""
        elif framework_lower == 'vue':
            return """
CRITICAL FRAMEWORK REQUIREMENT: This is a VUE project. You MUST:
- Use .vue file extensions for components
- Use Vue component syntax: <template>, <script>, <style>
- Use Vue imports: import { defineComponent } from 'vue'
- File paths should be: src/components/Login.vue

"""
        elif framework_lower == 'nestjs':
            return """
CRITICAL FRAMEWORK REQUIREMENT: This is a NESTJS project. You MUST:
- Use .ts file extensions (NOT .tsx)
- Use NestJS decorators: @Controller, @Injectable, @Module
- Use NestJS imports: @nestjs/common, @nestjs/core
- Follow NestJS file structure: *.controller.ts, *.service.ts, *.module.ts

"""
        elif framework_lower == 'flask':
            return """
CRITICAL FRAMEWORK REQUIREMENT: This is a FLASK project. You MUST:
- Use .py file extensions
- Use Flask route decorators: @app.route()
- Use Flask imports: from flask import Flask, request, jsonify
- Follow Flask file structure: routes/, services/, models/
- Use Flask Blueprint for route organization: from flask import Blueprint
- Use Flask request/response patterns: request.json, jsonify()

REMEMBER: Use Python/Flask syntax, NOT Angular/React. Example: routes/auth.py is correct, not auth.component.ts.

"""
        else:
            # Generic framework instruction
            return f"""
CRITICAL FRAMEWORK REQUIREMENT: This is a {framework_type.upper()} project.
You MUST use {framework_type} syntax, patterns, and conventions.
Follow the framework's standard file structure and naming conventions.

"""
    
    def _get_example_json(self, framework_type: str) -> str:
        """
        Get framework-specific JSON example for prompt.
        
        Args:
            framework_type: Framework name (e.g., 'angular', 'react')
            
        Returns:
            JSON example string with framework-appropriate file paths
        """
        framework_lower = framework_type.lower() if framework_type else 'unknown'
        
        if framework_lower == 'angular':
            example_files = '["src/components/login/login.component.ts", "src/components/login/login.component.html"]'
        elif framework_lower == 'react':
            example_files = '["src/components/Login.tsx", "src/components/UserProfile.tsx"]'
        elif framework_lower == 'vue':
            example_files = '["src/components/Login.vue", "src/components/UserProfile.vue"]'
        elif framework_lower == 'nestjs':
            example_files = '["src/auth/auth.controller.ts", "src/auth/auth.service.ts"]'
        elif framework_lower == 'flask':
            example_files = '["routes/auth.py", "services/auth_service.py", "app.py"]'
        else:
            # Generic example
            example_files = '["path/to/file1.py", "path/to/file2.ts"]'
        
        return f"""{{
  "tasks": [
    {{
      "task": "Description of task",
      "files": {example_files},
      "changes": ["Add field X to class Y", "Update method Z to handle new case"],
      "tests": ["tests/test_file1.py - test_new_functionality"],
      "notes": "Migration required: add column to database",
      "estimated_time": "30min"
    }}
  ],
  "total_estimated_time": "2h",
  "migration_required": false
}}"""
    
    def _parse_plan_from_text(self, text: str) -> Dict[str, Any]:
        """Fallback parser for plan text."""
        tasks = []
        lines = text.split('\n')
        current_task = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detect task start
            if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                if current_task:
                    tasks.append(current_task)
                current_task = {
                    "task": line[2:].strip(),
                    "files": [],
                    "changes": [],
                    "tests": [],
                    "notes": "",
                    "estimated_time": "30min"
                }
            elif current_task:
                if 'file' in line.lower() or '.py' in line or '.ts' in line:
                    # Extract file path
                    import re
                    file_match = re.search(r'[\w/]+\.(py|ts|js|java|cs)', line)
                    if file_match:
                        current_task["files"].append(file_match.group(0))
                elif 'change' in line.lower() or 'add' in line.lower() or 'update' in line.lower():
                    current_task["changes"].append(line)
                elif 'test' in line.lower():
                    current_task["tests"].append(line)
        
        if current_task:
            tasks.append(current_task)
        
        return {
            "tasks": tasks,
            "total_estimated_time": f"{len(tasks) * 30}min",
            "migration_required": False
        }
    
    def _normalize_plan(
        self,
        plan_dict: Dict[str, Any],
        intent: Dict[str, Any],
        impact_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize plan dictionary."""
        # Ensure tasks is a list
        tasks = plan_dict.get('tasks', [])
        if not isinstance(tasks, list):
            tasks = []
        
        # Normalize each task
        normalized_tasks = []
        for i, task in enumerate(tasks, 1):
            if not isinstance(task, dict):
                continue
            
            normalized_task = {
                "task_id": i,
                "task": task.get('task', f'Task {i}'),
                "files": task.get('files', []) if isinstance(task.get('files'), list) else [],
                "changes": task.get('changes', []) if isinstance(task.get('changes'), list) else [],
                "tests": task.get('tests', []) if isinstance(task.get('tests'), list) else [],
                "notes": task.get('notes', ''),
                "estimated_time": task.get('estimated_time', '30min')
            }
            normalized_tasks.append(normalized_task)
        
        # Check for migration requirement
        migration_required = plan_dict.get('migration_required', False)
        if not migration_required:
            # Check tasks for migration hints
            for task in normalized_tasks:
                notes = task.get('notes', '').lower()
                if 'migration' in notes or 'database' in notes or 'schema' in notes:
                    migration_required = True
                    break
        
        return {
            "plan_id": str(uuid.uuid4()),
            "tasks": normalized_tasks,
            "total_estimated_time": plan_dict.get('total_estimated_time', f"{len(normalized_tasks) * 30}min"),
            "migration_required": migration_required,
            "intent": intent,
            "impact_summary": {
                "file_count": impact_result.get('file_count', 0),
                "module_count": impact_result.get('module_count', 0),
                "risk_score": impact_result.get('risk_score', 'medium')
            }
        }
    
    def _fallback_plan(
        self,
        intent: Dict[str, Any],
        impact_result: Dict[str, Any],
        constraints: List[str]
    ) -> Dict[str, Any]:
        """Generate a basic fallback plan."""
        impacted_files = impact_result.get('impacted_files', [])[:5]  # Limit to 5 files
        
        tasks = []
        for i, file_path in enumerate(impacted_files, 1):
            tasks.append({
                "task_id": i,
                "task": f"Modify {file_path.split('/')[-1]}",
                "files": [file_path],
                "changes": [f"Apply changes as per intent: {intent.get('description', '')}"],
                "tests": [],
                "notes": "",
                "estimated_time": "30min"
            })
        
        return {
            "plan_id": str(uuid.uuid4()),
            "tasks": tasks,
            "total_estimated_time": f"{len(tasks) * 30}min",
            "migration_required": False,
            "intent": intent,
            "impact_summary": {
                "file_count": len(impacted_files),
                "module_count": len(impact_result.get('impacted_modules', [])),
                "risk_score": impact_result.get('risk_score', 'medium')
            }
        }

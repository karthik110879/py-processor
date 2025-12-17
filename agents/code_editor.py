"""Code Edit Executor - Applies code changes to repository."""

import logging
import os
import subprocess
from typing import Dict, Any, List, Optional
from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError
from utils.config import Config

logger = logging.getLogger(__name__)


class CodeEditExecutor:
    """Executes code edits on a repository."""
    
    def __init__(self, repo_path: str):
        """
        Initialize code editor.
        
        Args:
            repo_path: Path to repository
        """
        self.repo_path = os.path.abspath(repo_path)
        self.repo = None
        self.current_branch = None
        
        try:
            self.repo = Repo(self.repo_path)
        except InvalidGitRepositoryError:
            logger.warning(f"Not a git repository: {repo_path}")
            self.repo = None
    
    def create_branch(self, branch_name: str) -> str:
        """
        Create a new git branch.
        
        Args:
            branch_name: Name of branch to create
            
        Returns:
            Branch name
        """
        if not self.repo:
            logger.warning("Not a git repository, skipping branch creation")
            return branch_name
        
        try:
            # Check if branch already exists
            if branch_name in [ref.name.split('/')[-1] for ref in self.repo.heads]:
                logger.info(f"Branch {branch_name} already exists, checking it out")
                self.repo.git.checkout(branch_name)
            else:
                # Create and checkout new branch
                self.repo.git.checkout('-b', branch_name)
                logger.info(f"Created and checked out branch: {branch_name}")
            
            self.current_branch = branch_name
            return branch_name
        
        except GitCommandError as e:
            logger.error(f"Error creating branch: {e}", exc_info=True)
            raise
    
    def _find_file_by_name(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        Find file by name using fuzzy matching across the repository.
        
        Args:
            filename: Filename to search for (e.g., "BookDetail.tsx", "bookdetail")
            
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
        for root, dirs, files in os.walk(self.repo_path):
            # Skip hidden directories and common ignore patterns
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', '.git']]
            
            for file in files:
                file_lower = file.lower()
                file_no_ext = os.path.splitext(file_lower)[0]
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.repo_path)
                
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
            logger.debug(f"Fuzzy file match found: {filename} -> {best_match['path']} (confidence: {best_confidence:.2f}, method: {best_match['method']})")
            return best_match
        
        logger.debug(f"No fuzzy match found for filename: {filename} (best confidence: {best_confidence:.2f})")
        return None
    
    def _log_editing_step(
        self,
        step_name: str,
        file_path: str,
        status: str,
        search_method: Optional[str] = None,
        validation_status: Optional[Dict[str, Any]] = None,
        additional_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log editing step with comprehensive information.
        
        Args:
            step_name: Name of the step (e.g., "file_resolution", "llm_edit", "validation")
            file_path: File path being processed
            status: Status ("found", "not_found", "created", "modified", "error")
            search_method: Search method used ("exact", "fuzzy", "pkg", "created")
            validation_status: Validation results dictionary
            additional_info: Additional information dictionary
        """
        log_data = {
            "step": step_name,
            "file": file_path,
            "status": status
        }
        
        if search_method:
            log_data["search_method"] = search_method
        
        if validation_status:
            log_data["validation"] = {
                "valid": validation_status.get("valid", False),
                "errors_count": len(validation_status.get("errors", [])),
                "warnings_count": len(validation_status.get("warnings", []))
            }
        
        if additional_info:
            log_data.update(additional_info)
        
        # Use appropriate log level based on status
        if status == "error" or status == "not_found":
            logger.warning(f"EDITING STEP | {step_name} | File: {file_path} | Status: {status} | Data: {log_data}")
        elif status == "found" or status == "created" or status == "modified":
            logger.info(f"EDITING STEP | {step_name} | File: {file_path} | Status: {status} | Method: {search_method or 'N/A'}")
        else:
            logger.debug(f"EDITING STEP | {step_name} | File: {file_path} | Status: {status} | Data: {log_data}")
    
    def apply_edits(self, plan: Dict[str, Any], pkg_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Apply code edits from plan.
        
        Args:
            plan: Plan dictionary with tasks
            pkg_data: Optional PKG data dictionary for context-aware editing
            
        Returns:
            Dictionary with edit results
        """
        tasks = plan.get('tasks', [])
        changes = []
        errors = []
        validation_results = []
        
        for task in tasks:
            task_id = task.get('task_id', 0)
            files = task.get('files', [])
            change_descriptions = task.get('changes', [])
            
            for file_path in files:
                try:
                    # Resolve full file path
                    full_path = os.path.join(self.repo_path, file_path)
                    search_method = "exact"
                    original_file_path = file_path
                    
                    if not os.path.exists(full_path):
                        # Try fuzzy matching if exact path fails
                        config = Config()
                        fuzzy_match = None
                        if config.fuzzy_file_matching_enabled:
                            filename = os.path.basename(file_path)
                            fuzzy_match = self._find_file_by_name(filename)
                            
                            if fuzzy_match and fuzzy_match['confidence'] >= config.fuzzy_match_confidence_threshold:
                                # Use fuzzy match
                                file_path = fuzzy_match['path']
                                full_path = fuzzy_match['full_path']
                                search_method = "fuzzy"
                                logger.warning(
                                    f"File not found at exact path '{original_file_path}', "
                                    f"using fuzzy match: '{file_path}' "
                                    f"(confidence: {fuzzy_match['confidence']:.2f}, method: {fuzzy_match['method']})"
                                )
                            else:
                                # Fuzzy match failed or below threshold
                                search_method = "exact_failed"
                                if fuzzy_match:
                                    logger.warning(
                                        f"File not found at exact path '{original_file_path}', "
                                        f"fuzzy match found but below threshold: '{fuzzy_match['path']}' "
                                        f"(confidence: {fuzzy_match['confidence']:.2f}, threshold: {config.fuzzy_match_confidence_threshold})"
                                    )
                        else:
                            search_method = "exact_failed"
                        
                        # If still not found after fuzzy matching, check if file should be created
                        if not os.path.exists(full_path):
                            if self._should_create_file(change_descriptions, task):
                                logger.info(f"File not found, creating new file: {full_path}")
                                # Create new file
                                edit_result = self._create_file(full_path, change_descriptions, task, pkg_data)
                                
                                if edit_result['success']:
                                    changes.append({
                                        "file": file_path,
                                        "status": "created",
                                        "diff": edit_result.get('diff', ''),
                                        "task_id": task_id,
                                        "search_method": "created"
                                    })
                                    
                                    # Collect validation result
                                    if edit_result.get('validation'):
                                        validation_results.append({
                                            "file": file_path,
                                            "validation": edit_result['validation'],
                                            "task_id": task_id
                                        })
                                else:
                                    errors.append({
                                        "file": file_path,
                                        "error": edit_result.get('error', 'Failed to create file'),
                                        "task_id": task_id,
                                        "validation": edit_result.get('validation'),
                                        "search_method": "created",
                                        "original_path": original_file_path if original_file_path != file_path else None
                                    })
                                continue
                            else:
                                # File should exist but doesn't - log error with search results
                                error_msg = f"File not found: {original_file_path}"
                                if search_method == "fuzzy":
                                    error_msg += f" (fuzzy match attempted but file still not found)"
                                elif fuzzy_match:
                                    error_msg += f" (fuzzy match found but below threshold: {fuzzy_match['path']})"
                                
                                logger.warning(error_msg)
                                error_entry = {
                                    "file": original_file_path,
                                    "error": "File not found",
                                    "task_id": task_id,
                                    "search_method": search_method
                                }
                                if fuzzy_match:
                                    error_entry["suggestions"] = [fuzzy_match['path']]
                                    error_entry["fuzzy_match"] = {
                                        "path": fuzzy_match['path'],
                                        "confidence": fuzzy_match['confidence'],
                                        "method": fuzzy_match['method']
                                    }
                                errors.append(error_entry)
                                continue
                    
                    # Log file resolution
                    self._log_editing_step(
                        "file_resolution",
                        file_path,
                        "found",
                        search_method=search_method,
                        additional_info={"original_path": original_file_path} if original_file_path != file_path else None
                    )
                    
                    # Apply edits with PKG context
                    edit_result = self._edit_file(full_path, change_descriptions, task, pkg_data)
                    
                    if edit_result['success']:
                        changes.append({
                            "file": file_path,
                            "status": "modified",
                            "diff": edit_result.get('diff', ''),
                            "task_id": task_id,
                            "search_method": search_method,
                            "original_path": original_file_path if original_file_path != file_path else None
                        })
                        
                        # Collect validation result
                        if edit_result.get('validation'):
                            validation_results.append({
                                "file": file_path,
                                "validation": edit_result['validation'],
                                "task_id": task_id
                            })
                    else:
                        errors.append({
                            "file": file_path,
                            "error": edit_result.get('error', 'Unknown error'),
                            "task_id": task_id,
                            "validation": edit_result.get('validation'),
                            "search_method": search_method,
                            "original_path": original_file_path if original_file_path != file_path else None
                        })
                
                except Exception as e:
                    logger.error(f"Error editing file {file_path}: {e}", exc_info=True)
                    errors.append({
                        "file": file_path,
                        "error": str(e),
                        "task_id": task_id
                    })
        
        return {
            "changes": changes,
            "errors": errors,
            "validation_results": validation_results,
            "total_files": len(changes),
            "success": len(errors) == 0
        }
    
    def _should_create_file(
        self,
        change_descriptions: List[str],
        task: Dict[str, Any]
    ) -> bool:
        """
        Determine if a file should be created based on change descriptions and task context.
        
        Args:
            change_descriptions: List of change descriptions
            task: Task dictionary
            
        Returns:
            True if file should be created, False otherwise
        """
        # Check change descriptions for creation keywords
        creation_keywords = ['create', 'new', 'add new file', 'generate', 'implement new', 
                            'add new', 'new file', 'create new', 'implement']
        
        changes_text = ' '.join(change_descriptions).lower()
        for keyword in creation_keywords:
            if keyword in changes_text:
                return True
        
        # Check task description for creation keywords
        task_text = task.get('task', '').lower()
        for keyword in creation_keywords:
            if keyword in task_text:
                return True
        
        # Check notes field
        notes = task.get('notes', '').lower()
        for keyword in creation_keywords:
            if keyword in notes:
                return True
        
        return False
    
    def _create_file(
        self,
        file_path: str,
        change_descriptions: List[str],
        task: Dict[str, Any],
        pkg_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new file with generated content.
        
        Args:
            file_path: Full path to file
            change_descriptions: List of change descriptions
            task: Task dictionary
            pkg_data: Optional PKG data dictionary for context-aware generation
            
        Returns:
            Dictionary with success status, diff, and validation results
        """
        try:
            # Create parent directories if needed
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
                logger.info(f"Created parent directory: {parent_dir}")
            
            # Generate file content using LLM
            generated_content = self._generate_file_content(
                file_path,
                change_descriptions,
                task,
                pkg_data
            )
            
            if not generated_content:
                return {
                    "success": False,
                    "error": "Failed to generate file content",
                    "diff": "",
                    "status": "created"
                }
            
            # Write the file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(generated_content)
            
            logger.info(f"Created new file: {file_path}")
            
            # Generate diff (treat empty string as original)
            diff = self._generate_file_diff("", generated_content, file_path)
            
            # Log diff generation for created file
            generated_lines = len(generated_content.splitlines())
            diff_size = len(diff)
            logger.info(
                f"DIFF GENERATED (NEW FILE) | File: {file_path} | "
                f"Lines: 0 -> {generated_lines} (added: {generated_lines}) | "
                f"Diff size: {diff_size} chars"
            )
            
            # Validate the created file
            validation_result = None
            try:
                from agents.code_validator import CodeValidator
                validator = CodeValidator(self.repo_path)
                validation_result = validator.validate_all(file_path, generated_content, pkg_data)
                
                # Log validation results
                self._log_editing_step(
                    "validation",
                    file_path,
                    "valid" if validation_result.get('valid') else "error",
                    validation_status=validation_result
                )
                
                if not validation_result['valid']:
                    logger.warning(f"VALIDATION FAILED (NEW FILE) | File: {file_path} | Errors: {validation_result.get('errors', [])}")
                    # Don't fail on validation errors for new files, but log them
                else:
                    logger.info(f"VALIDATION PASSED (NEW FILE) | File: {file_path}")
                
                # Log warnings if any
                if validation_result.get('warnings'):
                    logger.warning(f"VALIDATION WARNINGS (NEW FILE) | File: {file_path} | Warnings: {validation_result['warnings']}")
            except Exception as e:
                logger.warning(f"Code validation error for created file: {e}", exc_info=True)
                # Continue even if validation fails (non-blocking)
                validation_result = {
                    "valid": True,  # Don't block on validation errors
                    "errors": [],
                    "warnings": [f"Validation check failed: {str(e)}"]
                }
            
            return {
                "success": True,
                "diff": diff,
                "status": "created",
                "validation": validation_result or {
                    "valid": True,
                    "errors": [],
                    "warnings": []
                }
            }
        
        except Exception as e:
            logger.error(f"Error creating file: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "diff": "",
                "status": "created"
            }
    
    def _detect_file_language(self, file_path: str, pkg_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Detect programming language from file path and PKG data.
        
        Args:
            file_path: Path to the file
            pkg_data: Optional PKG data dictionary
            
        Returns:
            Language string: 'python', 'typescript', 'javascript', or 'unknown'
        """
        # Check file extension first
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.py':
            return 'python'
        elif ext in ['.ts', '.tsx']:
            return 'typescript'
        elif ext in ['.js', '.jsx']:
            return 'javascript'
        
        # Fallback to PKG project.languages if available
        if pkg_data:
            project_languages = pkg_data.get('project', {}).get('languages', [])
            if project_languages:
                # Use first language from PKG
                primary_lang = project_languages[0].lower()
                if primary_lang in ['python', 'typescript', 'javascript']:
                    return primary_lang
        
        # Final fallback: use code_parser.multi_parser.detect_language()
        try:
            from code_parser.multi_parser import detect_language
            detected = detect_language(file_path)
            if detected in ['python', 'typescript', 'javascript']:
                return detected
        except Exception as e:
            logger.debug(f"Failed to detect language using code_parser: {e}")
        
        return 'unknown'
    
    def _detect_framework_from_content(self, content: str, file_path: str) -> Optional[str]:
        """
        Detect framework from file content (imports, decorators, syntax).
        
        Args:
            content: File content string
            file_path: Path to the file
            
        Returns:
            Framework name ('react', 'angular', 'vue', 'nextjs', 'nestjs', 'flask') or None
        """
        content_lower = content.lower()
        ext = os.path.splitext(file_path)[1].lower()
        
        # Check for Angular patterns
        if ('@component' in content_lower or 
            '@ngmodule' in content_lower or 
            '@angular/core' in content_lower or
            '@angular/common' in content_lower or
            '@angular/router' in content_lower):
            return 'angular'
        
        # Check for React patterns
        if ('import react' in content_lower or 
            "from 'react'" in content_lower or
            'from "react"' in content_lower or
            'usestate' in content_lower or
            'useeffect' in content_lower or
            'usenavigate' in content_lower or
            (ext == '.tsx' and 'return (' in content_lower)):
            return 'react'
        
        # Check for Vue patterns
        if (ext == '.vue' or
            'definecomponent' in content_lower or
            "from 'vue'" in content_lower or
            'from "vue"' in content_lower or
            '<template>' in content_lower):
            return 'vue'
        
        # Check for Next.js patterns
        if ('next/router' in content_lower or
            'next/link' in content_lower or
            'next/navigation' in content_lower or
            ('userouter' in content_lower and 'next' in content_lower)):
            return 'nextjs'
        
        # Check for NestJS patterns
        if ('@controller' in content_lower or
            '@injectable' in content_lower or
            '@module' in content_lower or
            '@nestjs/common' in content_lower or
            '@nestjs/core' in content_lower):
            return 'nestjs'
        
        # Check for Flask patterns
        if ('from flask import' in content_lower or
            'import flask' in content_lower or
            '@app.route' in content_lower or
            'flask(' in content_lower):
            return 'flask'
        
        # Default based on extension
        if ext == '.tsx':
            return 'react'  # Most likely React if .tsx
        
        return None
    
    def _detect_framework_from_file(self, file_path: str, content: str, pkg_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Detect framework from file with priority order:
        1. File content analysis (imports, decorators, syntax)
        2. File extension patterns
        3. PKG data (if available)
        4. Directory structure hints
        
        Args:
            file_path: Path to the file
            content: File content string
            pkg_data: Optional PKG data dictionary
            
        Returns:
            Framework name or None
        """
        # Priority 1: File content analysis
        framework = self._detect_framework_from_content(content, file_path)
        if framework:
            return framework
        
        # Priority 2: File extension patterns
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.tsx':
            return 'react'
        elif ext == '.vue':
            return 'vue'
        elif ext == '.ts' and 'component' in file_path.lower():
            # Could be Angular or React, check directory structure
            if 'angular' in file_path.lower() or 'ng-' in file_path.lower():
                return 'angular'
        
        # Priority 3: PKG data
        if pkg_data:
            frameworks = pkg_data.get('project', {}).get('frameworks', [])
            if frameworks:
                return frameworks[0].lower()
        
        # Priority 4: Directory structure hints
        file_path_lower = file_path.lower()
        if 'angular' in file_path_lower or 'ng-' in file_path_lower:
            return 'angular'
        elif 'react' in file_path_lower or 'components' in file_path_lower:
            return 'react'
        elif 'vue' in file_path_lower:
            return 'vue'
        elif 'next' in file_path_lower:
            return 'nextjs'
        
        return None
    
    def _get_ast_transformer(self, language: str, file_path: str) -> Optional[Any]:
        """
        Get appropriate AST transformer for the language.
        
        Args:
            language: Language string ('python', 'typescript', 'javascript')
            file_path: Path to the file
            
        Returns:
            ASTTransformer instance or None if not supported
        """
        try:
            from agents.ast_transformers import PythonASTTransformer, TypeScriptASTTransformer
            
            if language == 'python':
                return PythonASTTransformer()
            elif language in ['typescript', 'javascript']:
                return TypeScriptASTTransformer(file_path)
            else:
                return None
        except Exception as e:
            logger.warning(f"Failed to get AST transformer for {language}: {e}")
            return None
    
    def _apply_ast_edit(
        self,
        file_path: str,
        original_content: str,
        change_descriptions: List[str],
        language: str
    ) -> Optional[str]:
        """
        Apply edits using AST transformation.
        
        Args:
            file_path: Path to the file
            original_content: Original file content
            change_descriptions: List of change descriptions
            language: Detected language
            
        Returns:
            Modified content string or None if AST edit failed
        """
        try:
            logger.info(f"AST edit attempted for {file_path} using {language}")
            
            # Get transformer
            transformer = self._get_ast_transformer(language, file_path)
            if not transformer:
                logger.debug(f"No AST transformer available for {language}")
                return None
            
            # Log transformer creation with availability status
            transformer_type = type(transformer).__name__
            if transformer_type == 'TypeScriptASTTransformer':
                ts_morph_available = getattr(transformer, '_ts_morph_available', 'N/A')
                logger.info(f"AST transformer created: {transformer_type}, ts-morph available: {ts_morph_available}")
            elif transformer_type == 'PythonASTTransformer':
                available = getattr(transformer, '_available', 'N/A')
                logger.info(f"AST transformer created: {transformer_type}, libcst available: {available}")
            else:
                logger.info(f"AST transformer created: {transformer_type}")
            
            # Parse content
            tree = transformer.parse(original_content)
            
            # If parsing returns None, AST editing is not supported for this case
            if tree is None:
                logger.info(f"AST parsing not supported for {file_path}, falling back to LLM")
                return None
            
            # Apply edits
            modified_tree = transformer.apply_edit(tree, change_descriptions)
            
            # If apply_edit returns None, AST editing is not supported
            if modified_tree is None:
                logger.info(f"AST editing not supported for {file_path}, falling back to LLM")
                return None
            
            # Generate code
            modified_content = transformer.generate_code(modified_tree)
            
            if modified_content and modified_content != original_content:
                logger.info(f"AST edit successful for {file_path} using {language} transformer")
                return modified_content
            else:
                logger.info(f"AST edit produced no changes for {file_path}")
                return None
        
        except Exception as e:
            logger.info(f"AST edit failed for {file_path}, falling back to LLM editing")
            logger.warning(f"AST edit failed for {file_path}: {e}, using LLM fallback", exc_info=True)
            return None
    
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
            Dictionary with validation results:
            {
                "valid": bool,
                "detected_framework": str,
                "pkg_framework": Optional[str],
                "warnings": List[str]
            }
        """
        warnings = []
        detected_framework = self._detect_framework_from_file(file_path, content, pkg_data)
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
            # Check for React imports in Angular file
            if 'from \'react\'' in content_lower or 'from "react"' in content_lower:
                warnings.append("Angular file contains React imports - framework mismatch")
        elif detected_framework == 'react':
            # Check for Angular decorators in React file
            if '@component' in content_lower or '@ngmodule' in content_lower:
                warnings.append("React file contains Angular decorators - framework mismatch")
        
        # Compare PKG framework with detected framework
        if pkg_framework and detected_framework:
            if pkg_framework != detected_framework:
                warnings.append(
                    f"Framework mismatch: PKG indicates '{pkg_framework}' but file content indicates '{detected_framework}'. "
                    f"Using file's actual framework: '{detected_framework}'"
                )
                logger.warning(
                    f"Framework mismatch for {file_path}: PKG={pkg_framework}, File={detected_framework}. "
                    f"Using file's actual framework."
                )
        
        # Validate file structure matches framework conventions
        if detected_framework == 'angular':
            # Angular components should have @Component decorator
            if '@component' not in content_lower and 'component' in file_path.lower():
                warnings.append("Angular component file missing @Component decorator")
        elif detected_framework == 'react':
            # React components should export a component
            if 'export' not in content_lower and 'function' not in content_lower and 'const' not in content_lower:
                warnings.append("React component file may be missing component export")
        
        return {
            "valid": len(warnings) == 0,
            "detected_framework": detected_framework,
            "pkg_framework": pkg_framework,
            "warnings": warnings
        }
    
    def _validate_before_edit(
        self,
        file_path: str,
        content: str,
        pkg_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate file before editing: detect framework, check consistency, validate structure.
        
        Args:
            file_path: Path to the file
            content: File content string
            pkg_data: Optional PKG data dictionary
            
        Returns:
            Dictionary with validation results:
            {
                "valid": bool,
                "detected_framework": Optional[str],
                "pkg_framework": Optional[str],
                "warnings": List[str],
                "should_use_file_framework": bool
            }
        """
        # Run framework consistency validation
        consistency_result = self._validate_framework_consistency(file_path, content, pkg_data)
        
        detected_framework = consistency_result.get('detected_framework')
        pkg_framework = consistency_result.get('pkg_framework')
        warnings = consistency_result.get('warnings', [])
        
        # Determine which framework to use
        # Priority: file's actual framework > PKG framework
        should_use_file_framework = True
        if detected_framework:
            framework_to_use = detected_framework
        elif pkg_framework:
            framework_to_use = pkg_framework
            should_use_file_framework = False
            warnings.append("Using PKG-detected framework (file framework not detected)")
        else:
            framework_to_use = None
            warnings.append("No framework detected from file content or PKG data")
        
        # Validate import patterns are framework-appropriate
        if framework_to_use and content:
            content_lower = content.lower()
            if framework_to_use == 'angular':
                # Angular should use @angular imports
                if 'from \'react\'' in content_lower or 'from "react"' in content_lower:
                    warnings.append("Angular file should not import React - use @angular/core instead")
            elif framework_to_use == 'react':
                # React should use react imports, not Angular decorators
                if '@component' in content_lower or '@ngmodule' in content_lower:
                    warnings.append("React file should not use Angular decorators - use React component syntax")
        
        return {
            "valid": len([w for w in warnings if 'mismatch' in w.lower() or 'should not' in w.lower()]) == 0,
            "detected_framework": detected_framework,
            "pkg_framework": pkg_framework,
            "framework_to_use": framework_to_use,
            "warnings": warnings,
            "should_use_file_framework": should_use_file_framework
        }
    
    def _edit_file(
        self,
        file_path: str,
        change_descriptions: List[str],
        task: Dict[str, Any],
        pkg_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Edit a file based on change descriptions.
        
        Args:
            file_path: Full path to file
            change_descriptions: List of change descriptions
            task: Task dictionary
            pkg_data: Optional PKG data dictionary for context-aware editing
            
        Returns:
            Dictionary with success status and diff
        """
        try:
            # Read original file
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                original_content = f.read()
            
            # Pre-edit validation: detect framework and validate consistency
            validation_result = self._validate_before_edit(file_path, original_content, pkg_data)
            detected_framework = validation_result.get('framework_to_use')
            validation_warnings = validation_result.get('warnings', [])
            
            # Log validation warnings
            if validation_warnings:
                for warning in validation_warnings:
                    logger.warning(f"PRE-EDIT VALIDATION | {file_path} | {warning}")
            
            # Use detected framework for editing (override PKG if file framework is detected)
            if detected_framework and validation_result.get('should_use_file_framework'):
                # Update pkg_data to use file's actual framework
                if pkg_data:
                    if 'project' not in pkg_data:
                        pkg_data['project'] = {}
                    if 'frameworks' not in pkg_data['project']:
                        pkg_data['project']['frameworks'] = []
                    if not pkg_data['project']['frameworks'] or pkg_data['project']['frameworks'][0] != detected_framework:
                        logger.info(f"Using file's detected framework '{detected_framework}' instead of PKG framework")
                        pkg_data['project']['frameworks'] = [detected_framework]
            
            # Try AST-aware editing first
            config = Config()
            modified_content = None
            
            if config.use_ast_editing:
                language = self._detect_file_language(file_path, pkg_data)
                ast_modified = self._apply_ast_edit(file_path, original_content, change_descriptions, language)
                
                if ast_modified and ast_modified != original_content:
                    # Validate AST result
                    try:
                        from agents.code_validator import CodeValidator
                        validator = CodeValidator(self.repo_path)
                        validation_result = validator.validate_all(file_path, ast_modified, pkg_data)
                        
                        if validation_result.get('valid'):
                            modified_content = ast_modified
                            logger.info(f"AST edit successful for {file_path} using {language}")
                        else:
                            logger.warning(f"AST edit validation failed for {file_path}, falling back to LLM")
                            modified_content = None  # Will fall through to LLM edit
                    except Exception as e:
                        logger.warning(f"AST edit validation error: {e}, falling back to LLM")
                        modified_content = None
                else:
                    # AST edit failed or no changes
                    logger.debug(f"AST edit not applicable or failed for {file_path}, using LLM")
                    modified_content = None
            
            # Fallback to LLM editing if AST editing disabled, failed, or validation failed
            if not modified_content:
                modified_content = self._apply_llm_edit(
                    file_path,
                    original_content,
                    change_descriptions,
                    task,
                    pkg_data
                )
            
            if modified_content == original_content:
                # No changes made
                return {
                    "success": False,
                    "error": "No changes applied",
                    "diff": ""
                }
            
            # Validation loop: validate → fix iteratively → re-validate until clean or max retries
            config = Config()
            validation_result = None
            max_validation_retries = config.max_fix_retries
            
            for validation_attempt in range(1, max_validation_retries + 1):
                try:
                    from agents.code_validator import CodeValidator
                    validator = CodeValidator(self.repo_path)
                    validation_result = validator.validate_all(file_path, modified_content, pkg_data)
                    
                    # Log validation results
                    self._log_editing_step(
                        "validation",
                        file_path,
                        "valid" if validation_result.get('valid') else "error",
                        validation_status=validation_result
                    )
                    
                    if validation_result.get('valid'):
                        # Validation passed
                        if validation_result.get('warnings'):
                            logger.warning(f"VALIDATION WARNINGS | File: {file_path} | Warnings: {validation_result['warnings']}")
                        else:
                            logger.info(f"VALIDATION PASSED | File: {file_path} (attempt {validation_attempt})")
                        break  # Exit validation loop
                    else:
                        # Validation failed - try to fix
                        validation_errors = validation_result.get('errors', [])
                        logger.warning(f"VALIDATION FAILED (attempt {validation_attempt}/{max_validation_retries}) | File: {file_path} | Errors: {validation_errors}")
                        
                        if validation_attempt < max_validation_retries:
                            logger.info(f"Fixing validation errors... (attempt {validation_attempt}/{max_validation_retries})")
                            
                            # Try to fix iteratively
                            errors_dict = {
                                'validation_errors': validation_errors,
                                'lint_errors': [],
                                'test_failures': []
                            }
                            
                            fixed_content = self._fix_code_iteratively(
                                file_path,
                                modified_content,
                                errors_dict,
                                change_descriptions,
                                task,
                                pkg_data,
                                max_retries=1  # Single fix attempt per validation iteration
                            )
                            
                            if fixed_content and fixed_content != modified_content:
                                modified_content = fixed_content
                                logger.info(f"Applied fix for validation errors, re-validating...")
                            else:
                                logger.warning(f"Fix attempt did not produce changes, stopping validation loop")
                                break
                        else:
                            # Max retries reached
                            error_msg = f"Validation failed after {max_validation_retries} attempts: {'; '.join(validation_errors)}"
                            logger.error(f"VALIDATION FAILED (max retries) | File: {file_path} | Errors: {validation_errors}")
                            return {
                                "success": False,
                                "error": error_msg,
                                "diff": "",
                                "validation": validation_result
                            }
                
                except Exception as e:
                    logger.warning(f"Code validation error: {e}", exc_info=True)
                    # Continue even if validation fails (non-blocking)
                    # Create a default validation result for error case
                    validation_result = {
                        "valid": True,  # Don't block on validation errors
                        "errors": [],
                        "warnings": [f"Validation check failed: {str(e)}"]
                    }
                    break
            
            # Linting loop: run linter → auto-fix if available → fix iteratively if needed → re-lint until clean
            lint_result = None
            max_lint_retries = config.max_fix_retries
            
            for lint_attempt in range(1, max_lint_retries + 1):
                try:
                    from agents.test_runner import TestRunner
                    test_runner = TestRunner(self.repo_path)
                    
                    # Run linter for the specific file
                    # Note: TestRunner.run_linter() runs on entire repo, we'll filter results
                    lint_result = test_runner.run_linter()
                    
                    # Filter lint errors for this specific file
                    file_lint_errors = []
                    rel_file_path = os.path.relpath(file_path, self.repo_path).replace('\\', '/')
                    
                    if lint_result.get('errors'):
                        for error in lint_result.get('errors', []):
                            if rel_file_path in error or os.path.basename(file_path) in error:
                                file_lint_errors.append(error)
                    
                    if not file_lint_errors:
                        # No lint errors for this file
                        logger.info(f"LINTING PASSED | File: {file_path} (attempt {lint_attempt})")
                        break  # Exit linting loop
                    
                    # Lint errors found
                    logger.warning(f"LINT ERRORS FOUND (attempt {lint_attempt}/{max_lint_retries}) | File: {file_path} | Errors: {len(file_lint_errors)}")
                    
                    # Try auto-fix if enabled
                    auto_fixed = False
                    if config.auto_fix_lint and lint_attempt == 1:
                        auto_fixed = self._try_auto_fix_lint(file_path)
                        if auto_fixed:
                            # Re-read file after auto-fix
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                modified_content = f.read()
                            logger.info(f"Auto-fix applied, re-linting...")
                            continue  # Re-lint after auto-fix
                    
                    # If auto-fix not available or failed, try iterative fix
                    if lint_attempt < max_lint_retries:
                        logger.info(f"Fixing lint errors... (attempt {lint_attempt}/{max_lint_retries})")
                        
                        errors_dict = {
                            'validation_errors': [],
                            'lint_errors': file_lint_errors[:10],  # Limit to first 10 errors
                            'test_failures': []
                        }
                        
                        fixed_content = self._fix_code_iteratively(
                            file_path,
                            modified_content,
                            errors_dict,
                            change_descriptions,
                            task,
                            pkg_data,
                            max_retries=1  # Single fix attempt per lint iteration
                        )
                        
                        if fixed_content and fixed_content != modified_content:
                            modified_content = fixed_content
                            logger.info(f"Applied fix for lint errors, re-linting...")
                        else:
                            logger.warning(f"Fix attempt did not produce changes, stopping lint loop")
                            break
                    else:
                        # Max retries reached - log but don't fail
                        logger.warning(f"LINT ERRORS REMAIN after {max_lint_retries} attempts | File: {file_path} | Errors: {len(file_lint_errors)}")
                        break
                
                except Exception as e:
                    logger.warning(f"Linting error: {e}", exc_info=True)
                    # Continue even if linting fails (non-blocking)
                    break
            
            # Write modified content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            # Generate diff
            diff = self._generate_file_diff(original_content, modified_content, file_path)
            
            # Log diff generation
            original_lines = len(original_content.splitlines())
            modified_lines = len(modified_content.splitlines())
            lines_added = modified_lines - original_lines
            diff_size = len(diff)
            
            logger.info(
                f"DIFF GENERATED | File: {file_path} | "
                f"Lines: {original_lines} -> {modified_lines} (change: {lines_added:+d}) | "
                f"Diff size: {diff_size} chars"
            )
            
            # Log summary of fix attempts
            validation_status = "passed" if (validation_result and validation_result.get('valid')) else "failed"
            lint_status = "passed" if (lint_result and not lint_result.get('errors')) else ("warnings" if lint_result else "skipped")
            logger.info(
                f"FILE EDIT COMPLETE | File: {file_path} | "
                f"Validation: {validation_status} | Linting: {lint_status} | "
                f"Max validation retries: {max_validation_retries} | Max lint retries: {max_lint_retries}"
            )
            
            self._log_editing_step(
                "diff_generation",
                file_path,
                "modified",
                additional_info={
                    "original_lines": original_lines,
                    "modified_lines": modified_lines,
                    "lines_added": lines_added,
                    "diff_size": diff_size,
                    "validation_status": validation_status,
                    "lint_status": lint_status
                }
            )
            
            return {
                "success": True,
                "diff": diff,
                "modified": True,
                "validation": validation_result or {
                    "valid": True,
                    "errors": [],
                    "warnings": []
                }
            }
        
        except Exception as e:
            logger.error(f"Error editing file: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "diff": ""
            }
    
    def _apply_llm_edit(
        self,
        file_path: str,
        original_content: str,
        change_descriptions: List[str],
        task: Dict[str, Any],
        pkg_data: Optional[Dict[str, Any]] = None,
        error_context: Optional[str] = None
    ) -> str:
        """
        Apply edits using LLM with rich PKG context.
        
        Args:
            file_path: File path
            original_content: Original file content
            change_descriptions: List of change descriptions
            task: Task dictionary
            pkg_data: Optional PKG data dictionary for context-aware editing
            
        Returns:
            Modified file content
        """
        try:
            from langchain_openai import ChatOpenAI
            
            config = Config()
            api_key = config.openai_api_key
            if not api_key:
                logger.warning("OPENAI_API_KEY not set, skipping LLM edit")
                return original_content
            
            llm = ChatOpenAI(
                model=config.llm_model,
                temperature=0.1,
                openai_api_key=api_key
            )
            
            # Build rich context from PKG if available
            context_info = ""
            if pkg_data:
                try:
                    from agents.code_context_analyzer import CodeContextAnalyzer
                    from services.pkg_query_engine import PKGQueryEngine
                    
                    query_engine = PKGQueryEngine(pkg_data)
                    context_analyzer = CodeContextAnalyzer(pkg_data, query_engine)
                    
                    # Find module in PKG by file path
                    # Convert file_path to relative path from repo root
                    rel_path = os.path.relpath(file_path, self.repo_path) if os.path.isabs(file_path) else file_path
                    # Normalize path separators (handle both Windows and Unix)
                    rel_path_normalized = rel_path.replace('\\', '/')
                    
                    # Try to find module by path with multiple matching strategies
                    module = None
                    module_id = None
                    
                    # Strategy 1: Exact match with normalized path
                    for mod in pkg_data.get('modules', []):
                        mod_path = mod.get('path', '')
                        mod_path_normalized = mod_path.replace('\\', '/')
                        if mod_path_normalized == rel_path_normalized or mod_path == rel_path:
                            module = mod
                            break
                    
                    # Strategy 2: Match by filename if exact path not found
                    if not module:
                        filename = os.path.basename(rel_path)
                        for mod in pkg_data.get('modules', []):
                            mod_path = mod.get('path', '')
                            if os.path.basename(mod_path) == filename:
                                module = mod
                                logger.debug(f"Found module by filename match: {mod_path} for {rel_path}")
                                break
                    
                    if module:
                        module_id = module.get('id')
                        if not module_id:
                            logger.warning(f"Module found but missing ID for path: {rel_path}")
                            context = {}
                        else:
                            intent = task.get('intent', {})
                            try:
                                context = context_analyzer.build_code_generation_context(module_id, intent)
                            except Exception as e:
                                logger.warning(f"Failed to build code generation context for module {module_id}: {e}", exc_info=True)
                                context = {}
                        
                        # Build enhanced context string for prompt
                        context_sections = []
                        
                        # 1. Related Components/Imports
                        related_components = []
                        if context.get('import_patterns', {}).get('direct_imports'):
                            import_graph = context_analyzer.get_import_graph(module_id)
                            direct_imports = import_graph.get('direct_imports', [])[:5]
                            
                            for imp_module in direct_imports:
                                imp_path = imp_module.get('path', '')
                                imp_imports = imp_module.get('imports', [])
                                imports_list = ', '.join(imp_imports[:3]) if imp_imports else 'no imports'
                                related_components.append(f"- {imp_path} (imports: {imports_list})")
                        
                        if related_components:
                            context_sections.append("Related Components:")
                            context_sections.extend(related_components)
                            context_sections.append("")
                        
                        # 2. Framework-Specific Examples
                        framework_examples = []
                        if context.get('framework'):
                            # Find similar modules from same framework
                            similar_modules = context.get('similar_modules', [])[:2]
                            for sim_mod in similar_modules:
                                sim_path = sim_mod.get('path', '')
                                sim_kinds = sim_mod.get('kind', [])
                                kind_desc = ', '.join(sim_kinds[:2]) if sim_kinds else 'component'
                                framework_examples.append(f"- {sim_path} ({kind_desc})")
                        
                        if framework_examples:
                            context_sections.append("Framework Examples:")
                            context_sections.extend(framework_examples)
                            context_sections.append("")
                        
                        # 3. File Structure Context
                        file_structure = []
                        if context.get('symbols'):
                            exports = []
                            main_items = []
                            for symbol in context['symbols'][:5]:
                                name = symbol.get('name', '')
                                kind = symbol.get('kind', '')
                                is_exported = symbol.get('isExported', False)
                                
                                if is_exported:
                                    exports.append(name)
                                if kind in ['function', 'class', 'component']:
                                    main_items.append(f"{name} ({kind})")
                            
                            if exports:
                                file_structure.append(f"- Exports: {', '.join(exports[:5])}")
                            if main_items:
                                file_structure.append(f"- Main: {', '.join(main_items[:3])}")
                        
                        if file_structure:
                            context_sections.append("File Structure:")
                            context_sections.extend(file_structure)
                            context_sections.append("")
                        
                        # 4. Import Patterns
                        import_patterns_section = []
                        if context.get('import_patterns'):
                            direct_imports = context['import_patterns'].get('direct_imports', [])
                            import_style = context.get('patterns', {}).get('style', {}).get('import_style', {})
                            
                            if direct_imports:
                                # Analyze import patterns
                                relative_imports = [imp for imp in direct_imports if imp.startswith('./') or imp.startswith('../')]
                                absolute_imports = [imp for imp in direct_imports if not (imp.startswith('./') or imp.startswith('../'))]
                                
                                if relative_imports:
                                    import_patterns_section.append(f"- Relative imports for local files: {', '.join(relative_imports[:3])}")
                                if absolute_imports:
                                    import_patterns_section.append(f"- Absolute imports: {', '.join(absolute_imports[:3])}")
                            
                            if import_style:
                                if isinstance(import_style, dict):
                                    style_desc = ', '.join([f"{k}: {v}" for k, v in list(import_style.items())[:2]])
                                    if style_desc:
                                        import_patterns_section.append(f"- Import style: {style_desc}")
                            
                            # Check for named vs default exports
                            if context.get('code_style', {}).get('export_style'):
                                export_style = context['code_style']['export_style']
                                import_patterns_section.append(f"- {export_style.capitalize()} exports preferred")
                        
                        if import_patterns_section:
                            context_sections.append("Import Patterns:")
                            context_sections.extend(import_patterns_section)
                            context_sections.append("")
                        
                        # 5. Similar Components (with actual code examples if enabled)
                        similar_components = []
                        code_examples = []
                        
                        config = Config()
                        if config.include_code_examples and context.get('similar_modules'):
                            # Find similar modules and read their actual code
                            # Prioritize: same directory first, same framework second, same file type third
                            similar_modules = context.get('similar_modules', [])
                            
                            # Sort by directory proximity
                            target_dir = os.path.dirname(rel_path_normalized)
                            similar_modules_sorted = sorted(
                                similar_modules,
                                key=lambda m: (
                                    # Same directory gets highest priority
                                    0 if os.path.dirname(m.get('path', '').replace('\\', '/')) == target_dir else 1,
                                    # Then by framework match
                                    0 if m.get('kind', []) and any(k in str(context.get('framework', '')).lower() for k in m.get('kind', [])) else 1,
                                    # Then by file extension match
                                    0 if os.path.splitext(m.get('path', ''))[1] == os.path.splitext(rel_path)[1] else 1
                                )
                            )[:3]  # Limit to top 3
                            
                            for sim_mod in similar_modules_sorted:
                                sim_path = sim_mod.get('path', '')
                                sim_summary = sim_mod.get('moduleSummary', '')
                                
                                # Build relative path for similar component
                                if sim_summary:
                                    summary_short = sim_summary[:50] + '...' if len(sim_summary) > 50 else sim_summary
                                    similar_components.append(f"- {sim_path}: {summary_short}")
                                else:
                                    similar_components.append(f"- {sim_path}: Similar structure, uses same patterns")
                                
                                # Try to read actual file content
                                try:
                                    # Convert relative path to absolute
                                    if os.path.isabs(sim_path):
                                        full_sim_path = sim_path
                                    else:
                                        full_sim_path = os.path.join(self.repo_path, sim_path)
                                    
                                    if os.path.exists(full_sim_path):
                                        with open(full_sim_path, 'r', encoding='utf-8', errors='ignore') as f:
                                            sim_content = f.read()
                                        
                                        # Limit to 50-100 lines per example (prefer 50-100 lines as specified)
                                        sim_lines = sim_content.split('\n')
                                        if len(sim_lines) > 100:
                                            # Take first 100 lines
                                            sim_content = '\n'.join(sim_lines[:100]) + '\n... (truncated)'
                                        elif len(sim_lines) > 50:
                                            # Take first 50-100 lines (prefer around 75)
                                            take_lines = min(100, len(sim_lines))
                                            sim_content = '\n'.join(sim_lines[:take_lines])
                                        
                                        code_examples.append(f"Example from {sim_path}:\n```\n{sim_content}\n```")
                                        
                                        # Limit to 3 examples
                                        if len(code_examples) >= 3:
                                            break
                                except Exception as e:
                                    logger.debug(f"Failed to read code example from {sim_path}: {e}")
                                    # Continue without this example
                        
                        if similar_components:
                            context_sections.append("Similar Components:")
                            context_sections.extend(similar_components)
                            context_sections.append("")
                        
                        # Add actual code examples if available
                        if code_examples:
                            context_sections.append("Similar components in codebase (use these as reference for patterns and style):")
                            context_sections.extend(code_examples)
                            context_sections.append("")
                        
                        # 6. Include actual code snippets from target file itself (50-100 lines)
                        target_file_snippet = None
                        try:
                            target_lines = original_content.split('\n')
                            if len(target_lines) > 100:
                                # Take a representative 50-100 line snippet (prefer middle section)
                                start_line = max(0, len(target_lines) // 4)
                                end_line = min(len(target_lines), start_line + 100)
                                target_file_snippet = '\n'.join(target_lines[start_line:end_line])
                            elif len(target_lines) > 50:
                                # Take first 50-100 lines
                                take_lines = min(100, len(target_lines))
                                target_file_snippet = '\n'.join(target_lines[:take_lines])
                            else:
                                # File is small, use all of it
                                target_file_snippet = original_content
                        except Exception as e:
                            logger.debug(f"Failed to extract snippet from target file: {e}")
                        
                        if target_file_snippet:
                            context_sections.append("Current file code snippet (preserve this style and patterns):")
                            context_sections.append(f"```\n{target_file_snippet}\n```")
                            context_sections.append("")
                        
                        # Add framework and patterns info
                        if context.get('framework'):
                            context_sections.insert(0, f"Framework: {context['framework']}")
                            context_sections.insert(1, "")
                        
                        if context.get('patterns', {}).get('patterns'):
                            patterns_str = ', '.join(context['patterns']['patterns'][:5])
                            context_sections.append(f"Code Patterns: {patterns_str}")
                            context_sections.append("")
                        
                        if context.get('code_style', {}).get('naming_convention'):
                            context_sections.append(f"Naming Convention: {context['code_style']['naming_convention']}")
                            context_sections.append("")
                        
                        if context_sections:
                            context_info = "\n".join(context_sections) + "\n"
                    else:
                        logger.debug(f"Module not found in PKG for file: {rel_path} (tried normalized: {rel_path_normalized})")
                        
                except Exception as e:
                    logger.warning(f"Failed to build PKG context: {e}", exc_info=True)
                    # Continue without context if there's an error
            
            # Extract frameworks from pkg_data
            frameworks = pkg_data.get('project', {}).get('frameworks', []) if pkg_data else []
            primary_framework = frameworks[0] if frameworks else None
            
            # Log framework detection for debugging
            if primary_framework:
                logger.info(f"🔍 CODE EDITOR | Detected framework: {primary_framework} | All frameworks: {frameworks}")
            
            # Build framework instruction string
            framework_instruction = ""
            if primary_framework:
                framework_lower = primary_framework.lower()
                if framework_lower == 'flask':
                    framework_instruction = """
CRITICAL FRAMEWORK REQUIREMENT: This is a FLASK project. You MUST:
- Use .py file extensions
- Use Flask route decorators: @app.route()
- Use Flask imports: from flask import Flask, request, jsonify
- Follow Flask file structure: routes/, services/, models/
- Use Flask Blueprint for route organization: from flask import Blueprint
- Use Flask request/response patterns: request.json, jsonify()

REMEMBER: Use Python/Flask syntax, NOT Angular/React. Example: routes/auth.py is correct, not auth.component.ts.

"""
                elif framework_lower == 'angular':
                    framework_instruction = """
CRITICAL FRAMEWORK REQUIREMENT: This is an ANGULAR project. You MUST:
- Use .ts file extensions for components (NOT .tsx)
- Use Angular component syntax: @Component decorator
- Use Angular imports: @angular/core, @angular/common, etc.
- Follow Angular file structure: component.ts, component.html, component.css

"""
                else:
                    framework_instruction = f"""
CRITICAL FRAMEWORK REQUIREMENT: This is a {primary_framework.upper()} project.
You MUST use {primary_framework} syntax, patterns, and conventions.
- Use {primary_framework} component syntax (e.g., @Component for Angular, not React JSX)
- Use {primary_framework} imports (e.g., @angular/core for Angular, not react)
- Follow {primary_framework} file structure and naming conventions

"""
            
            changes_text = '\n'.join(f"- {desc}" for desc in change_descriptions)
            
            # Include actual code snippet from target file (50-100 lines) in prompt
            target_file_snippet_for_prompt = None
            try:
                target_lines = original_content.split('\n')
                if len(target_lines) > 100:
                    # Take a representative 50-100 line snippet
                    start_line = max(0, len(target_lines) // 4)
                    end_line = min(len(target_lines), start_line + 100)
                    target_file_snippet_for_prompt = '\n'.join(target_lines[start_line:end_line])
                elif len(target_lines) > 50:
                    take_lines = min(100, len(target_lines))
                    target_file_snippet_for_prompt = '\n'.join(target_lines[:take_lines])
                else:
                    target_file_snippet_for_prompt = original_content
            except Exception as e:
                logger.debug(f"Failed to extract snippet for prompt: {e}")
                target_file_snippet_for_prompt = original_content[:2000]  # Fallback to first 2000 chars
            
            # Build prompt with enhanced context
            prompt = f"""You are a code-edit assistant. Given:
- File path: {file_path}
- Current file content (full):
<<<
{original_content}
>>>
- Current file code snippet (preserve this style and patterns):
<<<
{target_file_snippet_for_prompt}
>>>
- Edit instructions:
{changes_text}
{framework_instruction}"""
            
            # Add error context if provided
            if error_context:
                prompt += f"""

Previous attempt had issues:
{error_context}

Fix these issues while maintaining the original requirements."""
            
            if context_info:
                prompt += f"""
Codebase Context:
{context_info}
"""
            
            prompt += """Apply the edits precisely. Return ONLY the modified file content (no prose, no explanations).

CRITICAL REQUIREMENTS:
1. Preserve the exact code style and formatting from the current file snippet above
2. Match the import patterns and code structure from similar components shown in context
3. Follow the framework-specific DO/DON'T rules above
4. Make minimal, targeted changes - only modify what's necessary
5. Use the same patterns, naming conventions, and structure as the existing code
6. If this is an Angular project, use @Component decorator, NOT React JSX
7. If this is a React project, use JSX syntax, NOT Angular decorators
8. Include file's existing import patterns and code style in your changes"""

            # Log prompt structure if enabled
            config = Config()
            if config.log_llm_prompts:
                prompt_preview = prompt[:2000] + "..." if len(prompt) > 2000 else prompt
                prompt_structure = {
                    "file_path": file_path,
                    "prompt_length": len(prompt),
                    "has_context": bool(context_info),
                    "has_framework_instruction": bool(framework_instruction),
                    "context_sections": len(context_info.split("\n\n")) if context_info else 0,
                    "preview": prompt_preview
                }
                logger.debug(f"LLM PROMPT STRUCTURE | {prompt_structure}")
            
            response = llm.invoke(prompt)
            modified_content = response.content if hasattr(response, 'content') else str(response)
            
            # Clean up response (remove markdown code blocks if present)
            if modified_content.startswith('```'):
                # Remove code block markers
                lines = modified_content.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines[-1].strip() == '```':
                    lines = lines[:-1]
                modified_content = '\n'.join(lines)
            
            return modified_content
        
        except Exception as e:
            logger.error(f"LLM edit failed: {e}", exc_info=True)
            return original_content
    
    def _try_auto_fix_lint(self, file_path: str) -> bool:
        """
        Try to auto-fix lint errors using eslint --fix or prettier --write.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if auto-fix was attempted and succeeded, False otherwise
        """
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            # Try eslint --fix for TypeScript/JavaScript files
            if file_ext in ['.ts', '.tsx', '.js', '.jsx']:
                try:
                    from agents.test_runner import TestRunner
                    test_runner = TestRunner(self.repo_path)
                    
                    # Use npx eslint --fix
                    import subprocess
                    import platform
                    
                    if platform.system() == 'Windows':
                        npx_cmd = 'npx.cmd'
                    else:
                        npx_cmd = 'npx'
                    
                    rel_path = os.path.relpath(file_path, self.repo_path)
                    result = subprocess.run(
                        [npx_cmd, 'eslint', '--fix', rel_path],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=self.repo_path
                    )
                    
                    if result.returncode == 0:
                        logger.info(f"Auto-fixed lint errors using eslint --fix for {file_path}")
                        return True
                    else:
                        logger.debug(f"eslint --fix failed for {file_path}: {result.stderr}")
                except FileNotFoundError:
                    logger.debug("eslint not found, skipping auto-fix")
                except Exception as e:
                    logger.debug(f"eslint --fix error: {e}")
                
                # Try prettier --write as fallback
                try:
                    import subprocess
                    import platform
                    
                    if platform.system() == 'Windows':
                        npx_cmd = 'npx.cmd'
                    else:
                        npx_cmd = 'npx'
                    
                    rel_path = os.path.relpath(file_path, self.repo_path)
                    result = subprocess.run(
                        [npx_cmd, 'prettier', '--write', rel_path],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=self.repo_path
                    )
                    
                    if result.returncode == 0:
                        logger.info(f"Auto-fixed formatting using prettier --write for {file_path}")
                        return True
                except FileNotFoundError:
                    logger.debug("prettier not found, skipping auto-fix")
                except Exception as e:
                    logger.debug(f"prettier --write error: {e}")
            
            return False
        
        except Exception as e:
            logger.debug(f"Auto-fix lint error: {e}")
            return False
    
    def _fix_code_iteratively(
        self,
        file_path: str,
        content: str,
        errors: Dict[str, Any],
        change_descriptions: List[str],
        task: Dict[str, Any],
        pkg_data: Optional[Dict[str, Any]] = None,
        max_retries: Optional[int] = None
    ) -> Optional[str]:
        """
        Iteratively fix code using LLM with error context.
        
        Args:
            file_path: Path to file
            content: Current code content
            errors: Dictionary with validation_errors, lint_errors, test_failures
            change_descriptions: Original change descriptions
            task: Task dictionary
            pkg_data: Optional PKG data
            max_retries: Maximum fix attempts (defaults to config.max_fix_retries)
            
        Returns:
            Fixed code or None if max retries reached
        """
        config = Config()
        max_retries = max_retries or config.max_fix_retries
        
        # Build error context string
        error_context_parts = []
        
        validation_errors = errors.get('validation_errors', [])
        lint_errors = errors.get('lint_errors', [])
        test_failures = errors.get('test_failures', [])
        
        if validation_errors:
            error_context_parts.append("- Validation errors:")
            for err in validation_errors[:5]:  # Limit to first 5 errors
                error_context_parts.append(f"  {err}")
        
        if lint_errors:
            error_context_parts.append("- Lint errors:")
            for err in lint_errors[:5]:  # Limit to first 5 errors
                error_context_parts.append(f"  {err}")
        
        if test_failures:
            error_context_parts.append("- Test failures:")
            # Test failures might be a string or list
            if isinstance(test_failures, str):
                # Extract first few lines if it's a long string
                failure_lines = test_failures.split('\n')[:10]
                error_context_parts.append(f"  {chr(10).join(failure_lines)}")
            elif isinstance(test_failures, list):
                for failure in test_failures[:5]:
                    error_context_parts.append(f"  {failure}")
        
        error_context = "\n".join(error_context_parts) if error_context_parts else ""
        
        # Count total errors
        total_errors = len(validation_errors) + len(lint_errors) + (len(test_failures) if isinstance(test_failures, list) else (1 if test_failures else 0))
        
        # Try fixing iteratively
        current_content = content
        for attempt in range(1, max_retries + 1):
            logger.info(f"Fix attempt {attempt}/{max_retries}: {total_errors} errors for {file_path}")
            
            # Build enhanced change descriptions with error context
            enhanced_changes = list(change_descriptions)
            if error_context:
                enhanced_changes.insert(0, f"Previous attempt had issues:\n{error_context}\n\nFix these issues while maintaining the original requirements.")
            
            # Call LLM edit with error context
            fixed_content = self._apply_llm_edit(
                file_path,
                current_content,
                enhanced_changes,
                task,
                pkg_data,
                error_context=error_context
            )
            
            if fixed_content == current_content:
                logger.warning(f"Fix attempt {attempt}: No changes made, stopping")
                break
            
            current_content = fixed_content
            
            # Re-validate to check if errors are fixed
            # This will be done by the caller, but we can do a quick syntax check here
            try:
                from agents.code_validator import CodeValidator
                validator = CodeValidator(self.repo_path)
                validation_result = validator.validate_all(file_path, current_content, pkg_data)
                
                if validation_result.get('valid'):
                    logger.info(f"Fix attempt {attempt}: Validation passed")
                    return current_content
                else:
                    # Update errors for next iteration
                    validation_errors = validation_result.get('errors', [])
                    errors['validation_errors'] = validation_errors
                    total_errors = len(validation_errors)
                    logger.info(f"Fix attempt {attempt}: Still {total_errors} validation errors, continuing...")
            except Exception as e:
                logger.warning(f"Fix attempt {attempt}: Validation check failed: {e}, returning fixed content")
                return current_content
        
        logger.warning(f"Max retries ({max_retries}) reached for {file_path}, returning last attempt")
        return current_content
    
    def _generate_file_content(
        self,
        file_path: str,
        change_descriptions: List[str],
        task: Dict[str, Any],
        pkg_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate complete file content using LLM with rich PKG context.
        
        Args:
            file_path: File path
            change_descriptions: List of change descriptions
            task: Task dictionary
            pkg_data: Optional PKG data dictionary for context-aware generation
            
        Returns:
            Generated file content
        """
        try:
            from langchain_openai import ChatOpenAI
            
            config = Config()
            api_key = config.openai_api_key
            if not api_key:
                logger.warning("OPENAI_API_KEY not set, cannot generate file content")
                return ""
            
            llm = ChatOpenAI(
                model=config.llm_model,
                temperature=0.1,
                openai_api_key=api_key
            )
            
            # Build rich context from PKG if available
            context_info = ""
            if pkg_data:
                try:
                    from agents.code_context_analyzer import CodeContextAnalyzer
                    from services.pkg_query_engine import PKGQueryEngine
                    
                    query_engine = PKGQueryEngine(pkg_data)
                    context_analyzer = CodeContextAnalyzer(pkg_data, query_engine)
                    
                    # Convert file_path to relative path from repo root
                    rel_path = os.path.relpath(file_path, self.repo_path) if os.path.isabs(file_path) else file_path
                    rel_path_normalized = rel_path.replace('\\', '/')
                    
                    # Try to find related modules by directory or similar patterns
                    # For new files, we look for modules in the same directory or similar patterns
                    parent_dir = os.path.dirname(rel_path_normalized)
                    related_modules = []
                    
                    # Find modules in the same directory or parent directories
                    for mod in pkg_data.get('modules', []):
                        mod_path = mod.get('path', '').replace('\\', '/')
                        mod_parent = os.path.dirname(mod_path)
                        if parent_dir in mod_parent or mod_parent in parent_dir:
                            related_modules.append(mod)
                            if len(related_modules) >= 3:
                                break
                    
                    # If no related modules found by path, try to find by framework patterns
                    if not related_modules:
                        # Look for modules with similar file extensions or naming patterns
                        file_ext = os.path.splitext(rel_path)[1]
                        for mod in pkg_data.get('modules', []):
                            mod_path = mod.get('path', '')
                            if os.path.splitext(mod_path)[1] == file_ext:
                                related_modules.append(mod)
                                if len(related_modules) >= 3:
                                    break
                    
                    # Build context from related modules
                    if related_modules:
                        # Use the first related module to build context
                        module = related_modules[0]
                        module_id = module.get('id')
                        if module_id:
                            intent = task.get('intent', {})
                            try:
                                context = context_analyzer.build_code_generation_context(module_id, intent)
                            except Exception as e:
                                logger.warning(f"Failed to build code generation context: {e}", exc_info=True)
                                context = {}
                            
                            # Build context string for prompt
                            context_parts = []
                            
                            if context.get('framework'):
                                context_parts.append(f"- Framework: {context['framework']}")
                            
                            if context.get('patterns', {}).get('patterns'):
                                patterns_str = ', '.join(context['patterns']['patterns'][:5])
                                context_parts.append(f"- Code patterns: {patterns_str}")
                            
                            if related_modules:
                                related_paths = [m.get('path', '') for m in related_modules[:3]]
                                if related_paths:
                                    context_parts.append(f"- Related modules: {', '.join(related_paths)}")
                            
                            if context.get('import_patterns', {}).get('direct_imports'):
                                imports_str = ', '.join(context['import_patterns']['direct_imports'][:5])
                                context_parts.append(f"- Import patterns: {imports_str}")
                            
                            if context.get('code_style', {}).get('naming_convention'):
                                context_parts.append(f"- Naming convention: {context['code_style']['naming_convention']}")
                            
                            if context.get('type_information'):
                                type_info_str = ', '.join([
                                    f"{name}: {info.get('signature', '')}" 
                                    for name, info in list(context['type_information'].items())[:3]
                                ])
                                if type_info_str:
                                    context_parts.append(f"- Type information: {type_info_str}")
                            
                            if context_parts:
                                context_info = "\n".join(context_parts) + "\n"
                    
                except Exception as e:
                    logger.warning(f"Failed to build PKG context for file creation: {e}", exc_info=True)
                    # Continue without context if there's an error
            
            # Extract frameworks from pkg_data
            frameworks = pkg_data.get('project', {}).get('frameworks', []) if pkg_data else []
            primary_framework = frameworks[0] if frameworks else None
            
            # Log framework detection for debugging
            if primary_framework:
                logger.info(f"🔍 CODE EDITOR FILE GENERATION | Detected framework: {primary_framework} | All frameworks: {frameworks}")
            
            # Build framework instruction string
            framework_instruction = ""
            if primary_framework:
                framework_lower = primary_framework.lower()
                if framework_lower == 'flask':
                    framework_instruction = """
CRITICAL FRAMEWORK REQUIREMENT: This is a FLASK project. You MUST:
- Use .py file extensions
- Use Flask route decorators: @app.route()
- Use Flask imports: from flask import Flask, request, jsonify
- Follow Flask file structure: routes/, services/, models/
- Use Flask Blueprint for route organization: from flask import Blueprint
- Use Flask request/response patterns: request.json, jsonify()

REMEMBER: Use Python/Flask syntax, NOT Angular/React. Example: routes/auth.py is correct, not auth.component.ts.

"""
                elif framework_lower == 'angular':
                    framework_instruction = """
CRITICAL FRAMEWORK REQUIREMENT: This is an ANGULAR project. You MUST:
- Use .ts file extensions for components (NOT .tsx)
- Use Angular component syntax: @Component decorator
- Use Angular imports: @angular/core, @angular/common, etc.
- Follow Angular file structure: component.ts, component.html, component.css

"""
                else:
                    framework_instruction = f"""
CRITICAL FRAMEWORK REQUIREMENT: This is a {primary_framework.upper()} project.
You MUST use {primary_framework} syntax, patterns, and conventions.
- Use {primary_framework} component syntax (e.g., @Component for Angular, not React JSX)
- Use {primary_framework} imports (e.g., @angular/core for Angular, not react)
- Follow {primary_framework} file structure and naming conventions

"""
            
            changes_text = '\n'.join(f"- {desc}" for desc in change_descriptions)
            task_description = task.get('task', '')
            
            prompt = f"""You are a code generation assistant. Generate a complete, production-ready file.

File path: {file_path}
Task: {task_description}
Requirements:
{changes_text}

{framework_instruction}{context_info}
Generate the complete file content following:
- Framework patterns and conventions from related modules
- Import patterns and code style from the codebase
- Best practices for the file type
- All necessary imports, exports, and structure

Return ONLY the complete file content (no prose, no explanations, no markdown code blocks).
The file should be ready to use and follow the same patterns as related modules in the codebase."""

            response = llm.invoke(prompt)
            generated_content = response.content if hasattr(response, 'content') else str(response)
            
            # Clean up response (remove markdown code blocks if present)
            if generated_content.startswith('```'):
                # Remove code block markers
                lines = generated_content.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                generated_content = '\n'.join(lines)
            
            return generated_content.strip()
        
        except Exception as e:
            logger.error(f"LLM file generation failed: {e}", exc_info=True)
            return ""
    
    def _generate_file_diff(
        self,
        original: str,
        modified: str,
        file_path: str
    ) -> str:
        """
        Generate unified diff for file changes.
        
        Args:
            original: Original content
            modified: Modified content
            file_path: File path
            
        Returns:
            Unified diff string
        """
        try:
            import difflib
            
            original_lines = original.splitlines(keepends=True)
            modified_lines = modified.splitlines(keepends=True)
            
            diff = difflib.unified_diff(
                original_lines,
                modified_lines,
                fromfile=file_path,
                tofile=file_path,
                lineterm=''
            )
            
            return ''.join(diff)
        
        except Exception as e:
            logger.error(f"Error generating diff: {e}", exc_info=True)
            return ""
    
    def generate_diff(self) -> str:
        """
        Generate unified diff for all changes.
        
        Returns:
            Unified diff string
        """
        if not self.repo:
            return ""
        
        try:
            # Get diff of working directory
            diff = self.repo.git.diff()
            return diff
        except Exception as e:
            logger.error(f"Error generating diff: {e}", exc_info=True)
            return ""
    
    def commit_changes(self, message: str) -> str:
        """
        Commit changes with message.
        
        Args:
            message: Commit message
            
        Returns:
            Commit SHA
        """
        if not self.repo:
            logger.warning("Not a git repository, skipping commit")
            return ""
        
        try:
            # Configure git user if not set
            config = Config()
            git_user_name = config.git_user_name or 'Agent'
            git_user_email = config.git_user_email or 'agent@example.com'
            
            self.repo.config_writer().set_value("user", "name", git_user_name).release()
            self.repo.config_writer().set_value("user", "email", git_user_email).release()
            
            # Stage all changes
            self.repo.git.add(A=True)
            
            # Commit
            commit = self.repo.index.commit(message)
            logger.info(f"Committed changes: {commit.hexsha}")
            
            return commit.hexsha
        
        except GitCommandError as e:
            logger.error(f"Error committing changes: {e}", exc_info=True)
            raise

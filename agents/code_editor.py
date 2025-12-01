"""Code Edit Executor - Applies code changes to repository."""

import logging
import os
import subprocess
from typing import Dict, Any, List
from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError

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
    
    def apply_edits(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply code edits from plan.
        
        Args:
            plan: Plan dictionary with tasks
            
        Returns:
            Dictionary with edit results
        """
        tasks = plan.get('tasks', [])
        changes = []
        errors = []
        
        for task in tasks:
            task_id = task.get('task_id', 0)
            files = task.get('files', [])
            change_descriptions = task.get('changes', [])
            
            for file_path in files:
                try:
                    # Resolve full file path
                    full_path = os.path.join(self.repo_path, file_path)
                    
                    if not os.path.exists(full_path):
                        logger.warning(f"File not found: {full_path}")
                        errors.append({
                            "file": file_path,
                            "error": "File not found",
                            "task_id": task_id
                        })
                        continue
                    
                    # Apply edits (simple approach for now)
                    # In Phase 2, this can be enhanced with AST-aware editing
                    edit_result = self._edit_file(full_path, change_descriptions, task)
                    
                    if edit_result['success']:
                        changes.append({
                            "file": file_path,
                            "status": "modified",
                            "diff": edit_result.get('diff', ''),
                            "task_id": task_id
                        })
                    else:
                        errors.append({
                            "file": file_path,
                            "error": edit_result.get('error', 'Unknown error'),
                            "task_id": task_id
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
            "total_files": len(changes),
            "success": len(errors) == 0
        }
    
    def _edit_file(
        self,
        file_path: str,
        change_descriptions: List[str],
        task: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Edit a file based on change descriptions.
        
        Args:
            file_path: Full path to file
            change_descriptions: List of change descriptions
            task: Task dictionary
            
        Returns:
            Dictionary with success status and diff
        """
        try:
            # Read original file
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                original_content = f.read()
            
            # For now, use simple LLM-based editing
            # In Phase 2, this can be enhanced with AST-aware tools
            modified_content = self._apply_llm_edit(
                file_path,
                original_content,
                change_descriptions,
                task
            )
            
            if modified_content == original_content:
                # No changes made
                return {
                    "success": False,
                    "error": "No changes applied",
                    "diff": ""
                }
            
            # Write modified content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            # Generate diff
            diff = self._generate_file_diff(original_content, modified_content, file_path)
            
            return {
                "success": True,
                "diff": diff,
                "modified": True
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
        task: Dict[str, Any]
    ) -> str:
        """
        Apply edits using LLM (simple approach).
        
        Args:
            file_path: File path
            original_content: Original file content
            change_descriptions: List of change descriptions
            task: Task dictionary
            
        Returns:
            Modified file content
        """
        try:
            from langchain_openai import ChatOpenAI
            import os
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not set, skipping LLM edit")
                return original_content
            
            llm = ChatOpenAI(
                model=os.getenv("LLM_MODEL", "gpt-4"),
                temperature=0.1,
                openai_api_key=api_key
            )
            
            changes_text = '\n'.join(f"- {desc}" for desc in change_descriptions)
            
            prompt = f"""You are a code-edit assistant. Given:
- File path: {file_path}
- Current file content:
<<<
{original_content}
>>>
- Edit instructions:
{changes_text}

Apply the edits precisely. Return ONLY the modified file content (no prose, no explanations).
Preserve code style and formatting. Make minimal, targeted changes."""

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
            git_user_name = os.getenv('GIT_USER_NAME', 'Agent')
            git_user_email = os.getenv('GIT_USER_EMAIL', 'agent@example.com')
            
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

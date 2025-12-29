"""Job processing routes for asynchronous repository analysis."""

import logging
import os
import subprocess
import threading
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Blueprint, request

from services.parser_service import generate_pkg
from services.agent_orchestrator import AgentOrchestrator
from utils.response_formatter import success_response, error_response
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Create blueprint
job_bp = Blueprint('jobs', __name__)

# In-memory job storage (thread-safe with lock)
_job_store: Dict[str, Dict[str, Any]] = {}
_job_store_lock = threading.Lock()

# Job status constants
STATUS_PENDING = "PENDING"
STATUS_PROCESSING = "PROCESSING"
STATUS_READY = "READY"
STATUS_ERROR = "ERROR"


def _get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job from store (thread-safe)."""
    with _job_store_lock:
        return _job_store.get(job_id)


def _create_job(job_id: str, epic_id: str, epic_details: Dict[str, Any], repository_url: str) -> Dict[str, Any]:
    """Create new job entry (thread-safe)."""
    job = {
        "jobId": job_id,
        "epicId": epic_id,
        "epicDetails": epic_details,
        "repositoryUrl": repository_url,
        "status": STATUS_PENDING,
        "created_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "completed_at": None,
        "error": None,
        "pkg_data": None
    }
    with _job_store_lock:
        _job_store[job_id] = job
    return job


def _update_job_status(job_id: str, status: str, **kwargs) -> None:
    """Update job status and optional fields (thread-safe)."""
    with _job_store_lock:
        if job_id in _job_store:
            _job_store[job_id]["status"] = status
            for key, value in kwargs.items():
                _job_store[job_id][key] = value


def _send_portfolio_callback(job_id: str, epic_id: str, status: str, pkg_data: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
    """Send callback to portfolio service."""
    try:
        from utils.config import Config
        config = Config()
        callback_url = os.getenv("PORTFOLIO_SERVICE_CALLBACK_URL") or config.portfolio_service_callback_url
        
        if not callback_url:
            logger.warning(f"⚠️  PORTFOLIO CALLBACK URL NOT CONFIGURED | Job ID: {job_id} | Skipping callback")
            return
        
        import requests
        
        payload = {
            "jobId": job_id,
            "epicId": epic_id,
            "status": status,
            "pkg_data": pkg_data,
            "error": error
        }
        
        logger.info(f"📞 SENDING PORTFOLIO CALLBACK | Job ID: {job_id} | URL: {callback_url} | Status: {status}")
        
        response = requests.post(
            callback_url,
            json=payload,
            timeout=30,
            headers={"Content-Type": "application/json"}
        )
        
        response.raise_for_status()
        logger.info(f"✅ PORTFOLIO CALLBACK SUCCESS | Job ID: {job_id} | Status: {response.status_code}")
        
    except ImportError:
        logger.warning(f"⚠️  REQUESTS LIBRARY NOT AVAILABLE | Job ID: {job_id} | Cannot send callback")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ PORTFOLIO CALLBACK FAILED | Job ID: {job_id} | Error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"❌ PORTFOLIO CALLBACK ERROR | Job ID: {job_id} | Error: {e}", exc_info=True)


def _process_repository(job_id: str, epic_id: str, epic_details: Dict[str, Any], repository_url: str) -> None:
    """
    Background processing function for repository analysis.
    
    This function runs in a separate thread and:
    1. Clones the repository (or skips if exists)
    2. Auto-forks if needed
    3. Generates PKG
    4. Updates job status
    5. Sends callback to portfolio service
    """
    try:
        logger.info(f"🚀 STARTING JOB PROCESSING | Job ID: {job_id} | Repo: {repository_url}")
        
        # Update status to PROCESSING
        _update_job_status(job_id, STATUS_PROCESSING, started_at=datetime.utcnow().isoformat())
        
        # Store original URL before potential fork
        original_repo_url = repository_url
        fork_info = None
        
        # Check if auto-forking is needed (BEFORE clone operation)
        logger.info(f"🔍 CHECKING FORK STATUS | Job ID: {job_id} | URL: {repository_url}")
        orchestrator = AgentOrchestrator()
        owner, repo_name_parsed = orchestrator._parse_repo_url(repository_url)
        
        if owner and repo_name_parsed:
            try:
                # Initialize PRCreator to access GitHub API
                temp_repo_path = os.path.join(os.getcwd(), "cloned_repos", ".temp")
                os.makedirs(temp_repo_path, exist_ok=True)
                
                from agents.pr_creator import PRCreator
                pr_creator = PRCreator(temp_repo_path)
                
                if pr_creator.github:
                    logger.info(f"🔐 AUTHENTICATED GITHUB USER AVAILABLE | Job ID: {job_id} | Checking ownership...")
                    
                    # Fork repository if needed
                    fork_info = pr_creator.fork_repository(owner, repo_name_parsed)
                    
                    if fork_info.get('success'):
                        if fork_info.get('already_owned'):
                            logger.info(f"✅ REPO OWNED BY USER | Job ID: {job_id} | No fork needed")
                        else:
                            logger.info(f"🍴 FORK OPERATION SUCCESSFUL | Job ID: {job_id} | Fork URL: {fork_info.get('fork_url')}")
                            repository_url = fork_info.get('fork_url')
                    else:
                        logger.warning(f"⚠️  FORK OPERATION FAILED | Job ID: {job_id} | Error: {fork_info.get('error')} | Falling back to original URL")
                else:
                    logger.warning(f"⚠️  GITHUB TOKEN NOT AVAILABLE | Job ID: {job_id} | Skipping fork, using original URL")
            except Exception as e:
                logger.error(f"❌ ERROR DURING FORK CHECK | Job ID: {job_id} | Error: {e}", exc_info=True)
                # Continue with original URL
        else:
            logger.warning(f"⚠️  COULD NOT PARSE REPO URL | Job ID: {job_id} | URL: {repository_url} | Skipping fork check")
        
        # Ensure cloned_repos folder exists
        base_dir = os.path.join(os.getcwd(), "cloned_repos")
        os.makedirs(base_dir, exist_ok=True)
        
        # Extract repo name from URL (strip .git if present)
        repo_name = os.path.splitext(os.path.basename(repository_url))[0]
        folder_path = os.path.join(base_dir, repo_name)
        
        # Check if repo already exists
        if os.path.exists(folder_path):
            logger.info(f"📁 REPOSITORY ALREADY EXISTS | Job ID: {job_id} | Path: {folder_path} | Skipping clone")
        else:
            # Clone repo
            logger.info(f"📥 CLONING REPOSITORY | Job ID: {job_id} | URL: {repository_url} | Path: {folder_path}")
            try:
                # Try to use git from PATH first, then fallback to Windows path
                git_cmd = "git"
                try:
                    subprocess.run([git_cmd, "--version"], check=True, capture_output=True)
                except (FileNotFoundError, subprocess.CalledProcessError):
                    git_cmd = r"C:\Program Files\Git\cmd\git.exe"
                
                subprocess.run([git_cmd, "clone", repository_url, folder_path], check=True)
                logger.info(f"✅ REPOSITORY CLONED | Job ID: {job_id} | Path: {folder_path}")
            except FileNotFoundError:
                error_msg = "Git is not installed or not found in PATH"
                logger.error(f"❌ GIT NOT FOUND | Job ID: {job_id} | {error_msg}")
                _update_job_status(
                    job_id,
                    STATUS_ERROR,
                    completed_at=datetime.utcnow().isoformat(),
                    error=error_msg
                )
                _send_portfolio_callback(job_id, epic_id, STATUS_ERROR, error=error_msg)
                return
            except subprocess.CalledProcessError as e:
                error_msg = f"Failed to clone repo: {str(e)}"
                logger.error(f"❌ CLONE FAILED | Job ID: {job_id} | {error_msg}", exc_info=True)
                _update_job_status(
                    job_id,
                    STATUS_ERROR,
                    completed_at=datetime.utcnow().isoformat(),
                    error=error_msg
                )
                _send_portfolio_callback(job_id, epic_id, STATUS_ERROR, error=error_msg)
                return
        
        # Generate PKG from cloned repo
        logger.info(f"🏗️  GENERATING PKG | Job ID: {job_id} | Repo: {repo_name}")
        try:
            from utils.config import Config
            config = Config()
            
            pkg_output = generate_pkg(
                repo_path=folder_path,
                fan_threshold=config.fan_threshold,
                include_features=config.include_features
            )
            
            # Extract PKG summary (module/symbol/endpoint counts)
            pkg_data = {
                "module_count": len(pkg_output.get("modules", [])),
                "symbol_count": len(pkg_output.get("symbols", [])),
                "endpoint_count": len(pkg_output.get("endpoints", [])),
                "edge_count": len(pkg_output.get("edges", [])),
                "feature_count": len(pkg_output.get("features", [])),
                "project_id": pkg_output.get("project", {}).get("id", "unknown")
            }
            
            logger.info(f"✅ PKG GENERATED | Job ID: {job_id} | Modules: {pkg_data['module_count']} | Symbols: {pkg_data['symbol_count']} | Endpoints: {pkg_data['endpoint_count']}")
            
            # Update job status to READY
            _update_job_status(
                job_id,
                STATUS_READY,
                completed_at=datetime.utcnow().isoformat(),
                pkg_data=pkg_data
            )
            
            # Send callback to portfolio service
            _send_portfolio_callback(job_id, epic_id, STATUS_READY, pkg_data=pkg_data)
            
            logger.info(f"✅ JOB COMPLETED | Job ID: {job_id} | Status: READY")
            
        except Exception as e:
            error_msg = f"Failed to generate PKG: {str(e)}"
            logger.error(f"❌ PKG GENERATION FAILED | Job ID: {job_id} | {error_msg}", exc_info=True)
            _update_job_status(
                job_id,
                STATUS_ERROR,
                completed_at=datetime.utcnow().isoformat(),
                error=error_msg
            )
            _send_portfolio_callback(job_id, epic_id, STATUS_ERROR, error=error_msg)
            
    except Exception as e:
        error_msg = f"Unexpected error during job processing: {str(e)}"
        logger.error(f"❌ JOB PROCESSING ERROR | Job ID: {job_id} | {error_msg}", exc_info=True)
        _update_job_status(
            job_id,
            STATUS_ERROR,
            completed_at=datetime.utcnow().isoformat(),
            error=error_msg
        )
        _send_portfolio_callback(job_id, epic_id, STATUS_ERROR, error=error_msg)


@job_bp.route('/process', methods=['POST'])
def process_job():
    """
    Create a new job for repository analysis.
    
    Accepts JSON payload:
    {
        "jobId": "job-123",
        "epicId": "epic-123",
        "epicDetails": { /* full epic details object */ },
        "repositoryUrl": "https://github.com/user/repo.git"
    }
    
    Returns:
        { "jobId": "...", "status": "PENDING", "message": "Job processing started" }
    """
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        job_id = data.get('jobId')
        repository_url = data.get('repositoryUrl')
        epic_id = data.get('epicId', '')
        epic_details = data.get('epicDetails', {})
        
        # Validate required fields
        if not job_id:
            logger.error("Missing jobId in request body")
            return error_response("jobId is required", 400)
        
        if not repository_url:
            logger.error("Missing repositoryUrl in request body")
            return error_response("repositoryUrl is required", 400)
        
        # Check if jobId already exists
        existing_job = _get_job(job_id)
        if existing_job:
            existing_status = existing_job.get('status')
            # Return 409 if job is in progress
            if existing_status in [STATUS_PENDING, STATUS_PROCESSING]:
                logger.warning(f"Job ID already exists and in progress | Job ID: {job_id} | Status: {existing_status}")
                return error_response(
                    f"Job with jobId '{job_id}' already exists and is {existing_status.lower()}",
                    409
                )
            # If job is completed (READY or ERROR), allow creating new job with same ID
            logger.info(f"Job ID exists but completed | Job ID: {job_id} | Status: {existing_status} | Creating new job")
        
        # Create job entry
        job = _create_job(job_id, epic_id, epic_details, repository_url)
        logger.info(f"📝 JOB CREATED | Job ID: {job_id} | Repo: {repository_url}")
        
        # Start background thread for processing
        thread = threading.Thread(
            target=_process_repository,
            args=(job_id, epic_id, epic_details, repository_url),
            daemon=True
        )
        thread.start()
        logger.info(f"🚀 BACKGROUND THREAD STARTED | Job ID: {job_id}")
        
        return success_response(
            data={
                "jobId": job_id,
                "status": STATUS_PENDING,
                "message": "Job processing started"
            },
            message="Job created successfully"
        )
        
    except Exception as e:
        logger.error(f"Error creating job: {e}", exc_info=True)
        return error_response(f"Failed to create job: {str(e)}", 500)


@job_bp.route('/<job_id>/status', methods=['GET'])
def get_job_status(job_id: str):
    """
    Get the current status of a job.
    
    Returns:
        Full job status object with:
        - jobId, epicId, epicDetails, repositoryUrl
        - status (PENDING, PROCESSING, READY, ERROR)
        - timestamps (created_at, started_at, completed_at)
        - error (if any)
        - pkg_data (when READY)
    
    Returns 404 if job not found.
    """
    try:
        job = _get_job(job_id)
        
        if not job:
            logger.warning(f"Job not found | Job ID: {job_id}")
            return error_response(f"Job with jobId '{job_id}' not found", 404)
        
        return success_response(
            data=job,
            message="Job status retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error retrieving job status: {e}", exc_info=True)
        return error_response(f"Failed to retrieve job status: {str(e)}", 500)


"""Routes for project cleanup endpoints."""

import logging
from flask import Blueprint, request
from typing import Dict, Any, Optional

from utils.cleanup_utils import cleanup_project
from utils.response_formatter import success_response, error_response
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Create blueprint
cleanup_bp = Blueprint('cleanup', __name__)


@cleanup_bp.route('/project', methods=['DELETE', 'POST'])
def cleanup_project_api():
    """
    Cleanup project data.
    
    Accepts JSON body:
    {
        "project_id": "optional",
        "project_name": "optional",
        "repo_url": "optional",
        "repo_path": "optional",
        "delete_neo4j": true,
        "delete_local": true,
        "dry_run": false,
        "confirm": false
    }
    
    At least one identifier must be provided.
    
    Returns:
        JSON response with deletion summary
    """
    try:
        # Get request data
        if not request.is_json:
            return error_response("Request must be JSON", 400)
        
        data = request.get_json() or {}
        
        # Extract identifiers
        project_id = data.get('project_id')
        project_name = data.get('project_name')
        repo_url = data.get('repo_url')
        repo_path = data.get('repo_path')
        
        # Validate: at least one identifier must be provided
        identifiers = [project_id, project_name, repo_url, repo_path]
        if not any(identifiers):
            return error_response(
                "At least one identifier must be provided: project_id, project_name, repo_url, or repo_path",
                400
            )
        
        # Determine which identifier to use (priority: project_id > project_name > repo_url > repo_path)
        identifier = None
        identifier_type = None
        
        if project_id:
            identifier = project_id
            identifier_type = 'project_id'
        elif project_name:
            identifier = project_name
            identifier_type = 'project_name'
        elif repo_url:
            identifier = repo_url
            identifier_type = 'repo_url'
        elif repo_path:
            identifier = repo_path
            identifier_type = 'repo_path'
        
        # Extract options
        delete_neo4j = data.get('delete_neo4j', True)
        delete_local = data.get('delete_local', True)
        dry_run = data.get('dry_run', False)
        confirm = data.get('confirm', False)
        
        # Validate options
        if not isinstance(delete_neo4j, bool):
            return error_response("delete_neo4j must be a boolean", 400)
        if not isinstance(delete_local, bool):
            return error_response("delete_local must be a boolean", 400)
        if not isinstance(dry_run, bool):
            return error_response("dry_run must be a boolean", 400)
        if not isinstance(confirm, bool):
            return error_response("confirm must be a boolean", 400)
        
        # Safety check: require confirmation for actual deletion (not dry-run)
        if not dry_run and not confirm:
            return error_response(
                "Confirmation required. Set 'confirm': true to proceed with deletion.",
                400
            )
        
        # Validate that at least one deletion target is specified
        if not delete_neo4j and not delete_local:
            return error_response(
                "At least one deletion target must be specified: delete_neo4j or delete_local",
                400
            )
        
        logger.info(f"🗑️  CLEANUP API REQUEST | Identifier: {identifier} | Type: {identifier_type} | Delete Neo4j: {delete_neo4j} | Delete Local: {delete_local} | Dry Run: {dry_run}")
        
        # Call cleanup function
        try:
            result = cleanup_project(
                identifier=identifier,
                identifier_type=identifier_type,
                delete_neo4j=delete_neo4j,
                delete_local=delete_local,
                dry_run=dry_run
            )
            
            # Check if cleanup was successful
            if not result.get("success"):
                error = result.get("error", "Unknown error")
                
                # Handle specific error cases
                if "not found" in error.lower() or "could not resolve" in error.lower():
                    return error_response(
                        f"Project not found: {error}",
                        404
                    )
                elif "permission" in error.lower() or "Permission denied" in error:
                    return error_response(
                        f"Permission denied: {error}",
                        403
                    )
                elif "connection" in error.lower() or "Neo4j" in error:
                    return error_response(
                        f"Database connection error: {error}",
                        500
                    )
                else:
                    return error_response(
                        f"Cleanup failed: {error}",
                        500
                    )
            
            # Success response
            return success_response(
                data=result,
                message=result.get("message", "Project cleanup completed successfully")
            )
            
        except ValueError as e:
            # Invalid identifier format
            logger.warning(f"⚠️  INVALID IDENTIFIER FORMAT | Identifier: {identifier} | Error: {e}")
            return error_response(
                f"Invalid identifier format: {str(e)}",
                400
            )
        except PermissionError as e:
            # Permission error
            logger.error(f"❌ PERMISSION ERROR | Identifier: {identifier} | Error: {e}")
            return error_response(
                f"Permission denied: {str(e)}",
                403
            )
        except ConnectionError as e:
            # Neo4j connection error
            logger.error(f"❌ NEO4J CONNECTION ERROR | Identifier: {identifier} | Error: {e}")
            return error_response(
                f"Database connection error: {str(e)}",
                500
            )
        except Exception as e:
            # Other errors
            logger.error(f"❌ CLEANUP API ERROR | Identifier: {identifier} | Error: {e}", exc_info=True)
            return error_response(
                f"Internal server error: {str(e)}",
                500
            )
            
    except Exception as e:
        logger.error(f"❌ UNEXPECTED ERROR IN CLEANUP API | Error: {e}", exc_info=True)
        return error_response(
            "An unexpected error occurred",
            500
        )

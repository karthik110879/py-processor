"""Utility functions for project cleanup operations."""

import os
import shutil
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from db.neo4j_db import get_session, verify_connection
from utils.logging_config import get_logger

logger = get_logger(__name__)


def resolve_project_identifier(
    identifier: str,
    identifier_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Resolve project identifier to get all project information.
    
    Accepts: project_id, project_name, repo_url, or repo_path
    If repo_url: Extract project name from URL (e.g., github.com/owner/repo.git → repo)
    If project_name: Use as-is
    If project_id: Use as-is
    Query Neo4j to get project metadata (name, rootPath) if needed
    
    Args:
        identifier: Project identifier (project_id, project_name, repo_url, or repo_path)
        identifier_type: Optional explicit type hint ('project_id', 'project_name', 'repo_url', 'repo_path')
        
    Returns:
        Dictionary with: {"project_id": "...", "project_name": "...", "repo_path": "...", "repo_url": "..."}
    """
    logger.debug(f"🔍 RESOLVING PROJECT IDENTIFIER | Identifier: {identifier} | Type: {identifier_type}")
    
    # Auto-detect type if not provided
    if not identifier_type:
        if identifier.startswith(('http://', 'https://', 'git@')):
            identifier_type = 'repo_url'
        elif os.path.sep in identifier or (os.path.altsep and os.path.altsep in identifier):
            # Check if it's a valid path
            if os.path.exists(identifier) or identifier.startswith('cloned_repos'):
                identifier_type = 'repo_path'
            else:
                # Could be project_id or project_name, try Neo4j first
                identifier_type = None  # Will be determined by Neo4j query
        else:
            # Could be project_id or project_name
            identifier_type = None
    
    project_id = None
    project_name = None
    repo_path = None
    repo_url = None
    
    # Handle repo_url
    if identifier_type == 'repo_url':
        # Extract repo name from URL
        repo_url = identifier
        # Remove .git suffix if present
        repo_name = os.path.splitext(os.path.basename(repo_url.replace('.git', '')))[0]
        project_id = repo_name
        project_name = repo_name
        
        # Try to get additional info from Neo4j
        if verify_connection():
            try:
                with get_session() as session:
                    result = session.run("""
                        MATCH (proj:Project {id: $project_id})
                        RETURN proj.name AS name, proj.rootPath AS rootPath
                        LIMIT 1
                    """, {"project_id": project_id})
                    record = result.single()
                    if record:
                        if record["name"]:
                            project_name = record["name"]
                        if record["rootPath"]:
                            repo_path = record["rootPath"]
            except Exception as e:
                logger.debug(f"Could not query Neo4j for repo_url: {e}")
        
        # If repo_path not found in Neo4j, construct it
        if not repo_path:
            base_dir = os.path.join(os.getcwd(), "cloned_repos")
            repo_path = os.path.join(base_dir, repo_name)
    
    # Handle repo_path
    elif identifier_type == 'repo_path':
        repo_path = identifier
        # Extract repo name from path
        repo_name = os.path.basename(repo_path.rstrip(os.path.sep))
        project_id = repo_name
        project_name = repo_name
        
        # Try to get additional info from Neo4j
        if verify_connection():
            try:
                with get_session() as session:
                    result = session.run("""
                        MATCH (proj:Project {id: $project_id})
                        RETURN proj.name AS name, proj.rootPath AS rootPath
                        LIMIT 1
                    """, {"project_id": project_id})
                    record = result.single()
                    if record:
                        if record["name"]:
                            project_name = record["name"]
                        if record["rootPath"]:
                            repo_path = record["rootPath"]  # Use Neo4j path if available
            except Exception as e:
                logger.debug(f"Could not query Neo4j for repo_path: {e}")
    
    # Handle project_id or project_name (query Neo4j)
    else:
        # Try as project_id first
        project_id = identifier
        project_name = identifier
        
        if verify_connection():
            try:
                with get_session() as session:
                    # Try by project_id
                    result = session.run("""
                        MATCH (proj:Project {id: $project_id})
                        RETURN proj.name AS name, proj.rootPath AS rootPath
                        LIMIT 1
                    """, {"project_id": project_id})
                    record = result.single()
                    
                    if not record:
                        # Try by project_name
                        result = session.run("""
                            MATCH (proj:Project {name: $project_name})
                            RETURN proj.id AS id, proj.rootPath AS rootPath
                            LIMIT 1
                        """, {"project_name": identifier})
                        record = result.single()
                        if record:
                            project_id = record["id"] or project_id
                    
                    if record:
                        if record.get("name"):
                            project_name = record["name"]
                        elif record.get("id"):
                            project_id = record["id"]
                        if record.get("rootPath"):
                            repo_path = record["rootPath"]
            except Exception as e:
                logger.debug(f"Could not query Neo4j: {e}")
        
        # If repo_path not found in Neo4j, try to construct it
        if not repo_path:
            base_dir = os.path.join(os.getcwd(), "cloned_repos")
            repo_path = os.path.join(base_dir, project_id)
    
    result = {
        "project_id": project_id,
        "project_name": project_name,
        "repo_path": repo_path,
        "repo_url": repo_url
    }
    
    logger.debug(f"✅ IDENTIFIER RESOLVED | Project ID: {project_id} | Project Name: {project_name} | Repo Path: {repo_path}")
    
    return result


def delete_local_project(project_identifier: str) -> Dict[str, Any]:
    """
    Delete local project files (cloned repo directory and PKG cache file).
    
    Accepts: project_id, project_name, or repo_path
    Finds cloned repo in cloned_repos/{repo_name} directory
    Deletes entire directory recursively using shutil.rmtree()
    Deletes PKG cache file: {repo_path}/pkg.json
    
    Args:
        project_identifier: Project identifier (project_id, project_name, or repo_path)
        
    Returns:
        Dictionary with deletion summary: {"deleted": {"repo_path": "...", "pkg_file": "..."}, "success": true}
    """
    logger.info(f"🗑️  DELETING LOCAL PROJECT | Identifier: {project_identifier}")
    
    # Resolve identifier to get repo_path
    resolved = resolve_project_identifier(project_identifier)
    repo_path = resolved.get("repo_path")
    
    if not repo_path:
        logger.warning(f"⚠️  COULD NOT RESOLVE REPO PATH | Identifier: {project_identifier}")
        return {
            "deleted": {},
            "success": False,
            "error": "Could not resolve repository path"
        }
    
    # Security: Ensure path is within cloned_repos directory
    base_dir = os.path.join(os.getcwd(), "cloned_repos")
    base_dir_abs = os.path.abspath(base_dir)
    repo_path_abs = os.path.abspath(repo_path)
    
    if not repo_path_abs.startswith(base_dir_abs):
        logger.error(f"❌ INVALID REPO PATH | Path: {repo_path} | Must be within {base_dir}")
        return {
            "deleted": {},
            "success": False,
            "error": f"Invalid repository path: must be within {base_dir}"
        }
    
    deleted_items = {}
    success = True
    errors = []
    
    # Delete pkg.json file if it exists
    pkg_file = os.path.join(repo_path, "pkg.json")
    if os.path.exists(pkg_file):
        try:
            os.remove(pkg_file)
            deleted_items["pkg_file"] = pkg_file
            logger.info(f"✅ DELETED PKG FILE | Path: {pkg_file}")
        except Exception as e:
            error_msg = f"Failed to delete pkg.json: {str(e)}"
            logger.warning(f"⚠️  {error_msg}")
            errors.append(error_msg)
            success = False
    else:
        logger.debug(f"ℹ️  PKG FILE NOT FOUND | Path: {pkg_file} | Skipping")
    
    # Delete repository directory if it exists
    if os.path.exists(repo_path) and os.path.isdir(repo_path):
        try:
            shutil.rmtree(repo_path)
            deleted_items["repo_path"] = repo_path
            logger.info(f"✅ DELETED REPO DIRECTORY | Path: {repo_path}")
        except PermissionError as e:
            error_msg = f"Permission denied deleting directory: {str(e)}"
            logger.error(f"❌ {error_msg}")
            errors.append(error_msg)
            success = False
        except Exception as e:
            error_msg = f"Failed to delete directory: {str(e)}"
            logger.error(f"❌ {error_msg}")
            errors.append(error_msg)
            success = False
    else:
        logger.warning(f"⚠️  REPO DIRECTORY NOT FOUND | Path: {repo_path} | Skipping")
        # This is not a fatal error, just log a warning
    
    result = {
        "deleted": deleted_items,
        "success": success
    }
    
    if errors:
        result["errors"] = errors
    
    if success:
        logger.info(f"✅ LOCAL PROJECT DELETED | Repo Path: {repo_path}")
    else:
        logger.warning(f"⚠️  LOCAL PROJECT DELETION PARTIAL | Repo Path: {repo_path} | Errors: {errors}")
    
    return result


def cleanup_project(
    identifier: str,
    identifier_type: Optional[str] = None,
    delete_neo4j: bool = True,
    delete_local: bool = True,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Main cleanup function that orchestrates Neo4j and local file cleanup.
    
    Resolves project identifier
    Deletes from Neo4j if delete_neo4j=True
    Deletes local files if delete_local=True
    Returns comprehensive summary with all deletions
    
    Args:
        identifier: Project identifier (project_id, project_name, repo_url, or repo_path)
        identifier_type: Optional explicit type hint
        delete_neo4j: Whether to delete from Neo4j (default: True)
        delete_local: Whether to delete local files (default: True)
        dry_run: If True, return what would be deleted without actually deleting (default: False)
        
    Returns:
        Comprehensive deletion summary
    """
    logger.info(f"🗑️  CLEANUP STARTED | Identifier: {identifier} | Delete Neo4j: {delete_neo4j} | Delete Local: {delete_local} | Dry Run: {dry_run}")
    
    # Resolve project identifier
    try:
        resolved = resolve_project_identifier(identifier, identifier_type)
        project_id = resolved.get("project_id")
        
        if not project_id:
            return {
                "success": False,
                "error": "Could not resolve project identifier",
                "message": "Project identifier could not be resolved to a valid project"
            }
    except Exception as e:
        logger.error(f"❌ ERROR RESOLVING IDENTIFIER | Identifier: {identifier} | Error: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Error resolving identifier: {str(e)}",
            "message": "Failed to resolve project identifier"
        }
    
    result = {
        "success": True,
        "project_id": project_id,
        "project_name": resolved.get("project_name"),
        "dry_run": dry_run,
        "deleted": {
            "neo4j": {},
            "local": {}
        },
        "message": "Project cleanup completed successfully"
    }
    
    # Dry run: query what would be deleted without actually deleting
    if dry_run:
        logger.info(f"🔍 DRY RUN MODE | Project ID: {project_id}")
        
        # Query Neo4j for counts
        if delete_neo4j and verify_connection():
            try:
                from db.neo4j_db import get_session
                with get_session() as session:
                    # Count packages
                    pkg_result = session.run("""
                        MATCH (pkg:Package {projectId: $project_id})
                        RETURN count(pkg) AS count
                    """, {"project_id": project_id})
                    pkg_count = pkg_result.single()["count"] or 0
                    
                    # Count modules
                    mod_result = session.run("""
                        MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(m:Module)
                        RETURN count(m) AS count
                    """, {"project_id": project_id})
                    mod_count = mod_result.single()["count"] or 0
                    
                    # Count symbols
                    sym_result = session.run("""
                        MATCH (proj:Project {id: $project_id})-[:HAS_SYMBOL]->(s:Symbol)
                        RETURN count(s) AS count
                    """, {"project_id": project_id})
                    sym_count = sym_result.single()["count"] or 0
                    
                    # Count endpoints
                    end_result = session.run("""
                        MATCH (proj:Project {id: $project_id})-[:HAS_ENDPOINT]->(e:Endpoint)
                        RETURN count(e) AS count
                    """, {"project_id": project_id})
                    end_count = end_result.single()["count"] or 0
                    
                    # Count features
                    feat_result = session.run("""
                        MATCH (proj:Project {id: $project_id})-[:HAS_FEATURE]->(f:Feature)
                        RETURN count(f) AS count
                    """, {"project_id": project_id})
                    feat_count = feat_result.single()["count"] or 0
                    
                    # Count metadata
                    meta_result = session.run("""
                        MATCH (m:Metadata {projectId: $project_id})
                        RETURN count(m) AS count
                    """, {"project_id": project_id})
                    meta_count = meta_result.single()["count"] or 0
                    
                    # Count relationships (sum of all relationship types)
                    rel_result1 = session.run("""
                        MATCH (proj:Project {id: $project_id})-[r:HAS_MODULE|HAS_SYMBOL|HAS_ENDPOINT|HAS_FEATURE|HAS_METADATA]->()
                        RETURN count(r) AS count
                    """, {"project_id": project_id})
                    count1 = rel_result1.single()["count"] or 0
                    
                    rel_result2 = session.run("""
                        MATCH (proj:Project {id: $project_id})
                        MATCH (proj)-[:HAS_MODULE|HAS_SYMBOL]->(a)
                        MATCH (a)-[r]->(b)
                        WHERE (b:Module OR b:Symbol)
                        RETURN count(r) AS count
                    """, {"project_id": project_id})
                    count2 = rel_result2.single()["count"] or 0
                    
                    rel_result3 = session.run("""
                        MATCH (proj:Project {id: $project_id})-[:HAS_FEATURE]->(f:Feature)
                        MATCH (f)-[r:CONTAINS]->()
                        RETURN count(r) AS count
                    """, {"project_id": project_id})
                    count3 = rel_result3.single()["count"] or 0
                    
                    rel_result4 = session.run("""
                        MATCH (pkg:Package {projectId: $project_id})-[r:VERSION_OF]->()
                        RETURN count(r) AS count
                    """, {"project_id": project_id})
                    count4 = rel_result4.single()["count"] or 0
                    
                    rel_count = count1 + count2 + count3 + count4
                    
                    result["deleted"]["neo4j"] = {
                        "packages": pkg_count,
                        "modules": mod_count,
                        "symbols": sym_count,
                        "endpoints": end_count,
                        "features": feat_count,
                        "metadata": meta_count,
                        "relationships": rel_count
                    }
            except Exception as e:
                logger.warning(f"⚠️  ERROR QUERYING NEO4J FOR DRY RUN | Project ID: {project_id} | Error: {e}")
        
        # Check local files
        if delete_local:
            repo_path = resolved.get("repo_path")
            if repo_path:
                base_dir = os.path.join(os.getcwd(), "cloned_repos")
                base_dir_abs = os.path.abspath(base_dir)
                repo_path_abs = os.path.abspath(repo_path)
                
                if repo_path_abs.startswith(base_dir_abs):
                    local_items = {}
                    if os.path.exists(repo_path):
                        local_items["repo_path"] = repo_path
                    pkg_file = os.path.join(repo_path, "pkg.json")
                    if os.path.exists(pkg_file):
                        local_items["pkg_file"] = pkg_file
                    result["deleted"]["local"] = local_items
        
        result["message"] = "Dry run completed - no data was deleted"
        logger.info(f"✅ DRY RUN COMPLETED | Project ID: {project_id} | Would delete: {result['deleted']}")
        return result
    
    # Actual deletion
    # Delete from Neo4j
    if delete_neo4j:
        try:
            from db.neo4j_db import delete_project
            neo4j_result = delete_project(project_id)
            if neo4j_result.get("success"):
                result["deleted"]["neo4j"] = neo4j_result.get("deleted", {})
            else:
                error = neo4j_result.get("error", "Unknown error")
                if "not found" in error.lower():
                    result["deleted"]["neo4j"] = {}
                    logger.warning(f"⚠️  PROJECT NOT FOUND IN NEO4J | Project ID: {project_id} | Skipping Neo4j cleanup")
                else:
                    result["success"] = False
                    result["error"] = f"Neo4j deletion failed: {error}"
                    result["message"] = f"Project cleanup partially failed: {error}"
        except Exception as e:
            logger.error(f"❌ ERROR DELETING FROM NEO4J | Project ID: {project_id} | Error: {e}", exc_info=True)
            result["success"] = False
            result["error"] = f"Error deleting from Neo4j: {str(e)}"
            result["message"] = f"Project cleanup failed: {str(e)}"
    
    # Delete local files
    if delete_local:
        try:
            local_result = delete_local_project(identifier)
            if local_result.get("success"):
                result["deleted"]["local"] = local_result.get("deleted", {})
            else:
                # Local deletion errors are non-fatal (repo might not exist)
                result["deleted"]["local"] = local_result.get("deleted", {})
                if local_result.get("errors"):
                    logger.warning(f"⚠️  LOCAL DELETION WARNINGS | Project ID: {project_id} | Errors: {local_result.get('errors')}")
        except Exception as e:
            logger.error(f"❌ ERROR DELETING LOCAL FILES | Project ID: {project_id} | Error: {e}", exc_info=True)
            # Local deletion errors are non-fatal
            result["deleted"]["local"] = {}
    
    if result["success"]:
        logger.info(f"✅ CLEANUP COMPLETED | Project ID: {project_id} | Summary: {result['deleted']}")
    else:
        logger.warning(f"⚠️  CLEANUP PARTIAL | Project ID: {project_id} | Error: {result.get('error')}")
    
    return result

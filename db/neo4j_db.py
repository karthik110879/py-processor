"""Neo4j database operations for storing and querying PKG data."""

import json
import logging
import time
from contextlib import contextmanager
from typing import Dict, Any, List, Optional
from neo4j import GraphDatabase, Session, Transaction

from utils.config import Config
from utils.logging_config import get_logger

# Configure logging
logger = get_logger(__name__)

# Get configuration
config = Config()
uri = config.neo4j_uri
user = config.neo4j_user
password = config.neo4j_password
database = config.neo4j_database
max_retries = config.neo4j_max_retries
retry_delay = config.neo4j_retry_delay
batch_size = config.neo4j_batch_size

# Global driver instance
driver: Optional[GraphDatabase.driver] = None


def _initialize_driver() -> Optional[GraphDatabase.driver]:
    """
    Initialize Neo4j driver with retry logic.
    
    Returns:
        Driver instance or None if connection fails
    """
    global driver
    
    if not uri or not user or not password:
        logger.warning("Neo4j credentials not configured. Skipping Neo4j initialization.")
        return None
    
    for attempt in range(max_retries):
        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            driver.verify_connectivity()
            logger.info(f"Neo4j connection established to {uri}")
            
            # Create indexes for better query performance
            _create_indexes(driver)
            
            return driver
        except Exception as e:
            logger.warning(f"Neo4j connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
            else:
                logger.error(f"Failed to connect to Neo4j after {max_retries} attempts")
                return None
    
    return None


def _create_indexes(driver_instance: GraphDatabase.driver) -> None:
    """Create indexes on frequently queried properties."""
    try:
        with driver_instance.session() as session:
            # Indexes for nodes
            session.run("CREATE INDEX IF NOT EXISTS FOR (p:Project) ON (p.id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (m:Module) ON (m.id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (s:Symbol) ON (s.id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (e:Endpoint) ON (e.id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (f:Feature) ON (f.id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (pkg:Package) ON (pkg.id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (pkg:Package) ON (pkg.projectId)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.url)")
            
            # Module metrics indexes
            session.run("CREATE INDEX IF NOT EXISTS FOR (m:Module) ON (m.centrality)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (m:Module) ON (m.complexity)")
            
            # Fulltext indexes for summaries
            try:
                session.run("""
                    CREATE FULLTEXT INDEX module_summary_ft IF NOT EXISTS
                    FOR (m:Module) ON EACH [m.moduleSummary]
                """)
                session.run("""
                    CREATE FULLTEXT INDEX symbol_summary_ft IF NOT EXISTS
                    FOR (s:Symbol) ON EACH [s.summary]
                """)
                logger.info("Fulltext indexes created/verified")
            except Exception as e:
                logger.warning(f"Fulltext indexes not supported or failed: {e}")
            
            # Vector index for embeddings (Neo4j 5.x+)
            try:
                embedding_dim = config.embedding_dimension
                session.run(f"""
                    CREATE VECTOR INDEX symbol_embedding_index IF NOT EXISTS
                    FOR (s:Symbol) ON s.embedding
                    OPTIONS {{indexConfig: {{`vector.dimensions`: {embedding_dim}, `vector.similarity_function`: 'cosine'}}}}
                """)
                logger.info(f"Vector index created/verified (dimension: {embedding_dim})")
            except Exception as e:
                logger.warning(f"Vector index not supported or failed (Neo4j 5.x+ required): {e}")
            
            logger.info("Neo4j indexes created/verified")
    except Exception as e:
        logger.warning(f"Failed to create indexes: {e}")


def verify_connection() -> bool:
    """
    Verify Neo4j connection is healthy.
    
    Returns:
        True if connection is healthy, False otherwise
    """
    global driver
    
    if driver is None:
        logger.debug("Neo4j driver not initialized, attempting initialization...")
        driver = _initialize_driver()
    
    if driver is None:
        logger.warning("Neo4j driver initialization failed. Check NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD environment variables.")
        return False
    
    try:
        driver.verify_connectivity()
        logger.debug("Neo4j connection verified successfully")
        return True
    except Exception as e:
        logger.error(f"Neo4j connection verification failed: {e}")
        driver = None  # Reset driver to force re-initialization
        return False


@contextmanager
def get_session():
    """
    Context manager for Neo4j sessions with automatic error handling.
    
    Yields:
        Session instance
    """
    global driver
    
    if driver is None:
        driver = _initialize_driver()
    
    if driver is None:
        raise ConnectionError("Neo4j driver not initialized. Check connection settings.")
    session = driver.session(database=database)
    try:
        yield session
    except Exception as e:
        logger.error(f"Neo4j session error: {e}", exc_info=True)
        raise
    finally:
        session.close()


def _store_package_tx(tx: Transaction, pkg: Dict[str, Any]) -> str:
    """
    Transaction function to store Package node with versioning.
    
    Returns:
        Package ID (versioned)
    """
    from datetime import datetime
    
    project_id = pkg["project"]["id"]
    version_str = pkg.get("version", "1.0.0")
    
    # Auto-detect version strategy
    if version_str and version_str != "1.0.0" and not version_str.startswith(project_id):
        # Semantic versioning: use version as-is, create ID as {project_id}_v{version}
        pkg_id = f"{project_id}_v{version_str}"
    else:
        # Timestamp-based versioning
        timestamp = datetime.utcnow().isoformat()
        pkg_id = f"{project_id}_{timestamp}"
        version_str = timestamp
    
    tx.run("""
        MERGE (p:Package {id: $pkg_id})
        SET p.projectId = $project_id,
            p.version = $version,
            p.generatedAt = $generatedAt,
            p.gitSha = $gitSha,
            p.timestamp = datetime()
    """, {
        "pkg_id": pkg_id,
        "project_id": project_id,
        "version": version_str,
        "generatedAt": pkg.get("generatedAt"),
        "gitSha": pkg.get("gitSha")
    })
    
    return pkg_id


def _link_package_versions_tx(tx: Transaction, pkg_id: str, project_id: str) -> None:
    """Transaction function to link Package versions with VERSION_OF relationship."""
    # Find previous version (latest by timestamp)
    result = tx.run("""
        MATCH (prev:Package {projectId: $project_id})
        WHERE prev.id <> $pkg_id
        RETURN prev
        ORDER BY prev.timestamp DESC
        LIMIT 1
    """, {"pkg_id": pkg_id, "project_id": project_id})
    
    prev_record = result.single()
    if prev_record:
        prev_pkg = prev_record["prev"]
        prev_id = prev_pkg.get("id")
        # Create VERSION_OF relationship
        tx.run("""
            MATCH (new:Package {id: $new_id})
            MATCH (prev:Package {id: $prev_id})
            MERGE (new)-[:VERSION_OF]->(prev)
        """, {"new_id": pkg_id, "prev_id": prev_id})


def _store_project_tx(tx: Transaction, pkg: Dict[str, Any]) -> None:
    """Transaction function to store Project node and metadata."""
    project = pkg["project"]
    project_id = project["id"]
    
    # Create Project node
    tx.run("""
        MERGE (proj:Project {id: $project_id})
        SET proj.name = $name,
            proj.rootPath = $rootPath,
            proj.languages = $languages,
            proj.frameworks = $frameworks,
            proj.buildTools = $buildTools
    """, {
        "project_id": project_id,
        "name": project.get("name", ""),
        "rootPath": project.get("rootPath", ""),
        "languages": project.get("languages", []),
        "frameworks": project.get("frameworks", []),
        "buildTools": project.get("buildTools", [])
    })
    
    # Create Metadata node
    tx.run("""
        MERGE (m:Metadata {projectId: $project_id})
        SET m += $metadata
    """, {
        "project_id": project_id,
        "metadata": project.get("metadata", {})
    })
    
    # Connect Project -> Metadata
    tx.run("""
        MATCH (proj:Project {id: $project_id})
        MATCH (m:Metadata {projectId: $project_id})
        MERGE (proj)-[:HAS_METADATA]->(m)
    """, {"project_id": project_id})


def _store_modules_tx(tx: Transaction, modules: List[Dict[str, Any]], project_id: str, edges: Optional[List[Dict[str, Any]]] = None) -> None:
    """
    Transaction function to store modules using UNWIND batch operation with precomputed metrics.
    
    Args:
        tx: Neo4j transaction
        modules: List of module dictionaries
        project_id: Project ID
        edges: Optional list of edges for calculating fan_in metrics
    """
    if not modules:
        return
    
    # Build edge lookup for fan_in calculation
    fan_in_map = {}
    if edges:
        for edge in edges:
            if edge.get("type") == "imports":
                to_id = edge.get("to")
                if to_id:
                    fan_in_map[to_id] = fan_in_map.get(to_id, 0) + 1
    
    # Prepare module data for batch insert with metrics
    module_data = []
    for m in modules:
        module_id = m.get("id")
        if not module_id:
            logger.warning(f"Skipping module - missing id: {m}")
            continue
        
        # Calculate metrics
        fan_in = fan_in_map.get(module_id, 0)
        imports_list = m.get("imports", [])
        exports_list = m.get("exports", [])
        fan_out = len(imports_list) if isinstance(imports_list, list) else 0
        centrality = fan_in + fan_out
        complexity = len(exports_list) if isinstance(exports_list, list) else 0
        complexity += fan_out
        
        # Filter out None values
        module_props = {k: v for k, v in m.items() if v is not None and k != "id"}
        module_data.append({
            "id": module_id,
            "data": module_props,
            "projectId": project_id,
            "fan_in": fan_in,
            "fan_out": fan_out,
            "centrality": centrality,
            "complexity": complexity
        })
    
    if not module_data:
        return
    
    # Batch insert using UNWIND with metrics
    tx.run("""
        UNWIND $modules AS module
        MERGE (mod:Module {id: module.id})
        SET mod += module.data,
            mod.fan_in = module.fan_in,
            mod.fan_out = module.fan_out,
            mod.centrality = module.centrality,
            mod.complexity = module.complexity
        WITH mod, module.projectId AS projectId
        MATCH (proj:Project {id: projectId})
        MERGE (proj)-[:HAS_MODULE]->(mod)
    """, {"modules": module_data})


def _store_symbols_tx(tx: Transaction, symbols: List[Dict[str, Any]], project_id: str) -> None:
    """Transaction function to store symbols using UNWIND batch operation with embedding support."""
    if not symbols:
        return
    
    # Prepare symbol data for batch insert
    symbol_data = []
    for s in symbols:
        symbol_id = s.get("id")
        if not symbol_id:
            # Fallback to name if id not available (for backward compatibility)
            symbol_id = s.get("name")
            if not symbol_id:
                logger.warning(f"Skipping symbol - missing id and name: {s}")
                continue
        
        # Extract embedding if present and valid
        embedding = s.get("embedding")
        if embedding is not None:
            # Validate embedding is a list of numbers
            if not isinstance(embedding, list) or not all(isinstance(x, (int, float)) for x in embedding):
                logger.warning(f"Invalid embedding format for symbol {symbol_id}, skipping embedding")
                embedding = None
        
        # Filter out None values (but keep embedding if it's an empty list)
        symbol_props = {k: v for k, v in s.items() if v is not None and k not in ["id", "name", "embedding"]}
        symbol_data.append({
            "id": symbol_id,
            "name": s.get("name", ""),
            "data": symbol_props,
            "projectId": project_id,
            "embedding": embedding  # Can be None or list of floats
        })
    
    if not symbol_data:
        return
    
    # Batch insert using UNWIND - using id as identifier
    tx.run("""
        UNWIND $symbols AS symbol
        MERGE (sym:Symbol {id: symbol.id})
        SET sym.name = symbol.name,
            sym += symbol.data
        WITH sym, symbol.projectId AS projectId, symbol.embedding AS embedding
        SET sym.embedding = CASE WHEN embedding IS NOT NULL THEN embedding ELSE sym.embedding END
        WITH sym, projectId
        MATCH (proj:Project {id: projectId})
        MERGE (proj)-[:HAS_SYMBOL]->(sym)
    """, {"symbols": symbol_data})

def _store_endpoints_tx(tx: Transaction, endpoints: List[Dict[str, Any]], project_id: str) -> None:
    """Transaction function to store endpoints using UNWIND batch operation."""
    if not endpoints:
        return
    
    # Prepare endpoint data for batch insert
    endpoint_data = []
    for e in endpoints:
        endpoint_id = e.get("id")
        path = e.get("path")
        if not endpoint_id and not path:
            logger.warning(f"Skipping endpoint - missing id and path: {e}")
            continue
        
        # Use id if available, otherwise use path
        identifier = endpoint_id if endpoint_id else path
        
        # Filter out None values
        endpoint_props = {k: v for k, v in e.items() if v is not None and k not in ["id", "path"]}
        endpoint_data.append({
            "id": identifier,
            "path": path or identifier,
            "data": endpoint_props,
            "projectId": project_id
        })
    
    if not endpoint_data:
        return
    
    # Batch insert using UNWIND
    tx.run("""
        UNWIND $endpoints AS endpoint
        MERGE (end:Endpoint {id: endpoint.id})
        SET end.path = endpoint.path,
            end += endpoint.data
        WITH end, endpoint.projectId AS projectId
        MATCH (proj:Project {id: projectId})
        MERGE (proj)-[:HAS_ENDPOINT]->(end)
    """, {"endpoints": endpoint_data})


def _store_edges_tx(tx: Transaction, edges: List[Dict[str, Any]]) -> None:
    """Transaction function to store edges using UNWIND batch operation with type-specific matching."""
    if not edges:
        return
    
    # Group edges by relationship type for efficient batch processing
    rel_types = {}
    for edge in edges:
        from_id = edge.get("from")
        to_id = edge.get("to")
        if not from_id or not to_id:
            logger.warning(f"Skipping edge due to missing IDs: {edge}")
            continue
        
        rel_type = edge.get("type", "DEPENDS_ON").upper()
        if rel_type not in rel_types:
            rel_types[rel_type] = []
        
        rel_types[rel_type].append({
            "from": from_id,
            "to": to_id,
            "weight": edge.get("weight", 1)
        })
    
    if not rel_types:
        return
    
    # Process each relationship type separately (required for dynamic relationship types)
    for rel_type, typed_edges in rel_types.items():
        # Use type-specific matching to avoid wrong matches
        # Match nodes that could be Module or Symbol based on ID prefix
        tx.run(f"""
            UNWIND $edges AS edge
            MATCH (a)
            WHERE (a:Module OR a:Symbol) AND a.id = edge.from
            MATCH (b)
            WHERE (b:Module OR b:Symbol) AND b.id = edge.to
            MERGE (a)-[r:{rel_type}]->(b)
            ON CREATE SET r.weight = edge.weight
            ON MATCH SET r.weight = edge.weight
        """, {"edges": typed_edges})


def _store_features_tx(tx: Transaction, features: List[Dict[str, Any]], project_id: str) -> None:
    """Transaction function to store features using UNWIND batch operation."""
    if not features:
        return
    
    # Prepare feature data for batch insert
    feature_data = []
    for feature in features:
        feature_id = feature.get("id")
        if not feature_id:
            logger.warning(f"Skipping feature - missing id: {feature}")
            continue
        
        module_ids = feature.get("moduleIds", [])
        feature_data.append({
            "feature_id": feature_id,
            "name": feature.get("name", ""),
            "path": feature.get("path", ""),
            "projectId": project_id,
            "moduleIds": module_ids
        })
    
    if not feature_data:
        return
    
    # Batch insert features
    tx.run("""
        UNWIND $features AS feature
        MERGE (f:Feature {id: feature.feature_id})
        SET f.name = feature.name,
            f.path = feature.path
        WITH f, feature.projectId AS projectId
        MATCH (proj:Project {id: projectId})
        MERGE (proj)-[:HAS_FEATURE]->(f)
    """, {"features": feature_data})
    
    # Batch connect features to modules
    feature_module_data = []
    for feature in features:
        feature_id = feature.get("id")
        if not feature_id:
            continue
        for module_id in feature.get("moduleIds", []):
            feature_module_data.append({
                "feature_id": feature_id,
                "module_id": module_id
            })
    
    if feature_module_data:
        tx.run("""
            UNWIND $feature_modules AS fm
            MATCH (f:Feature {id: fm.feature_id})
            MATCH (m:Module {id: fm.module_id})
            MERGE (f)-[:CONTAINS]->(m)
        """, {"feature_modules": feature_module_data})


def store_pkg(pkg: Dict[str, Any]) -> bool:
    """
    Store PKG data to Neo4j with transaction management and batch optimizations.
    
    Args:
        pkg: PKG dictionary containing project, modules, symbols, endpoints, edges, features
        
    Returns:
        True if successful, False otherwise
    """
    project_id = pkg.get('project', {}).get('id', 'unknown')
    
    logger.info(f"💾 STORING PKG TO NEO4J | Project ID: {project_id}")
    
    if not verify_connection():
        logger.error(f"❌ NEO4J CONNECTION UNAVAILABLE | Project ID: {project_id} | Cannot store PKG")
        return False
    
    try:
        with get_session() as session:
            try:
                # Store Package node (with versioning)
                logger.debug(f"📦 STORING PACKAGE NODE | Project ID: {project_id}")
                pkg_id = session.execute_write(_store_package_tx, pkg)
                logger.debug(f"✅ PACKAGE NODE STORED | Project ID: {project_id} | Package ID: {pkg_id}")
                
                # Link package versions
                session.execute_write(_link_package_versions_tx, pkg_id, project_id)
                
                # Store Project node
                logger.debug(f"📋 STORING PROJECT NODE | Project ID: {project_id}")
                session.execute_write(_store_project_tx, pkg)
                logger.debug(f"✅ PROJECT NODE STORED | Project ID: {project_id}")
                
                # Batch store modules (with edges for metrics calculation)
                modules = pkg.get("modules", [])
                edges = pkg.get("edges", [])
                if modules:
                    logger.info(f"📦 STORING MODULES | Project ID: {project_id} | Count: {len(modules)} | Batch size: {batch_size}")
                    for i in range(0, len(modules), batch_size):
                        batch = modules[i:i + batch_size]
                        session.execute_write(_store_modules_tx, batch, project_id, edges)
                    logger.info(f"✅ MODULES STORED | Project ID: {project_id} | Count: {len(modules)}")
                
                # Batch store symbols
                symbols = pkg.get("symbols", [])
                if symbols:
                    logger.info(f"🔤 STORING SYMBOLS | Project ID: {project_id} | Count: {len(symbols)} | Batch size: {batch_size}")
                    for i in range(0, len(symbols), batch_size):
                        batch = symbols[i:i + batch_size]
                        session.execute_write(_store_symbols_tx, batch, project_id)
                    logger.info(f"✅ SYMBOLS STORED | Project ID: {project_id} | Count: {len(symbols)}")
                
                # Batch store endpoints
                endpoints = pkg.get("endpoints", [])
                if endpoints:
                    logger.info(f"🌐 STORING ENDPOINTS | Project ID: {project_id} | Count: {len(endpoints)} | Batch size: {batch_size}")
                    for i in range(0, len(endpoints), batch_size):
                        batch = endpoints[i:i + batch_size]
                        session.execute_write(_store_endpoints_tx, batch, project_id)
                    logger.info(f"✅ ENDPOINTS STORED | Project ID: {project_id} | Count: {len(endpoints)}")
                
                # Batch store edges
                edges = pkg.get("edges", [])
                if edges:
                    logger.info(f"🔗 STORING EDGES | Project ID: {project_id} | Count: {len(edges)} | Batch size: {batch_size}")
                    for i in range(0, len(edges), batch_size):
                        batch = edges[i:i + batch_size]
                        session.execute_write(_store_edges_tx, batch)
                    logger.info(f"✅ EDGES STORED | Project ID: {project_id} | Count: {len(edges)}")
                
                # Store features
                features = pkg.get("features", [])
                if features:
                    logger.info(f"📁 STORING FEATURES | Project ID: {project_id} | Count: {len(features)}")
                    session.execute_write(_store_features_tx, features, project_id)
                    logger.info(f"✅ FEATURES STORED | Project ID: {project_id} | Count: {len(features)}")
                
                logger.info(f"✅ PKG STORED TO NEO4J | Project ID: {project_id} | Modules: {len(modules)} | Symbols: {len(symbols)} | Endpoints: {len(endpoints)} | Edges: {len(edges)} | Features: {len(features)}")
                return True
                
            except Exception as tx_error:
                logger.error(
                    f"❌ TRANSACTION ERROR | Project ID: {project_id} | Error: {tx_error}",
                    exc_info=True
                )
                raise  # Re-raise to be caught by outer try-except
                
    except ConnectionError as e:
        logger.error(f"❌ NEO4J CONNECTION ERROR | Project ID: {project_id} | Error: {e}")
        return False
    except Exception as e:
        logger.error(
            f"❌ STORE PKG ERROR | Project ID: {project_id} | Error: {e}",
            exc_info=True
        )
        return False


def store_pkg_version(pkg: Dict[str, Any], version: Optional[str] = None) -> bool:
    """
    Store PKG with version information for version tracking.
    
    Args:
        pkg: PKG dictionary
        version: Optional version string (defaults to timestamp-based version)
        
    Returns:
        True if successful, False otherwise
    """
    if version is None:
        from datetime import datetime
        version = datetime.utcnow().isoformat()
    
    # Add version to pkg
    pkg_with_version = pkg.copy()
    pkg_with_version["version"] = version
    
    return store_pkg(pkg_with_version)


def close_driver() -> None:
    """Close Neo4j driver connection."""
    global driver
    if driver:
        try:
            driver.close()
            logger.info("Neo4j driver closed.")
        except Exception as e:
            logger.error(f"Error closing Neo4j driver: {e}")
        finally:
            driver = None


def get_version_history(project_id: str) -> List[Dict[str, Any]]:
    """
    Get version history for a project.
    
    Args:
        project_id: Project ID to get version history for
        
    Returns:
        List of version dictionaries with version, timestamp, and generatedAt
    """
    logger.debug(f"📜 GETTING VERSION HISTORY | Project ID: {project_id}")
    if not verify_connection():
        logger.warning(f"⚠️  NEO4J NOT CONNECTED | Project ID: {project_id} | Cannot get version history")
        return []
    
    try:
        with get_session() as session:
            result = session.run("""
                MATCH (pkg:Package)
                WHERE pkg.projectId = $project_id
                RETURN pkg.id as id, pkg.version as version, pkg.timestamp as timestamp, pkg.generatedAt as generatedAt
                ORDER BY pkg.timestamp DESC
            """, {"project_id": project_id})
            
            versions = []
            for record in result:
                versions.append({
                    "id": record["id"],
                    "version": record["version"],
                    "timestamp": record["timestamp"],
                    "generatedAt": record["generatedAt"]
                })
            
            logger.info(f"✅ VERSION HISTORY RETRIEVED | Project ID: {project_id} | Versions: {len(versions)}")
            return versions
    except Exception as e:
        logger.error(f"❌ ERROR GETTING VERSION HISTORY | Project ID: {project_id} | Error: {e}")
        return []


def check_pkg_stored(project_id: str) -> bool:
    """
    Check if PKG for a project is already stored in Neo4j.
    
    Args:
        project_id: Project ID to check
        
    Returns:
        True if project exists in Neo4j, False otherwise
    """
    logger.debug(f"🔍 CHECKING PKG IN NEO4J | Project ID: {project_id}")
    if not verify_connection():
        logger.warning(f"⚠️  NEO4J NOT CONNECTED | Project ID: {project_id} | Cannot check PKG")
        return False
    
    try:
        with get_session() as session:
            # Check by projectId property (for versioned packages) or by Package/Project node
            result = session.run("""
                MATCH (p:Package {projectId: $project_id})
                RETURN p
                LIMIT 1
            """, {"project_id": project_id})
            record = result.single()
            exists = record is not None
            
            # Fallback: check Project node if no Package found (backward compatibility)
            if not exists:
                result = session.run(
                    "MATCH (p:Project {id: $project_id}) RETURN p",
                    {"project_id": project_id}
                )
                record = result.single()
                exists = record is not None
            
            if exists:
                logger.info(f"✅ PKG FOUND IN NEO4J | Project ID: {project_id}")
            else:
                logger.info(f"ℹ️  PKG NOT IN NEO4J | Project ID: {project_id}")
            return exists
    except Exception as e:
        logger.error(f"❌ ERROR CHECKING PKG | Project ID: {project_id} | Error: {e}")
        return False


def load_pkg_from_neo4j(project_id: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Load PKG data from Neo4j and reconstruct the full PKG JSON structure.
    
    Args:
        project_id: Project ID to load
        version: Optional version string to load specific version. If None, loads latest.
        
    Returns:
        Complete PKG dictionary matching the schema from pkg_generator.py,
        or None if project not found or on error
    """
    logger.info(f"📥 LOADING PKG FROM NEO4J | Project ID: {project_id} | Version: {version or 'latest'}")
    if not verify_connection():
        logger.warning(f"⚠️  NEO4J NOT CONNECTED | Project ID: {project_id} | Cannot load PKG")
        return None
    
    # Check if project exists first
    if not check_pkg_stored(project_id):
        logger.warning(f"⚠️  PROJECT NOT FOUND | Project ID: {project_id} | Not in Neo4j")
        return None
    
    try:
        with get_session() as session:
            # 1. Load Package node (version, generatedAt, gitSha)
            package_data = {}
            if version:
                # Load specific version
                pkg_id = f"{project_id}_v{version}" if not version.startswith(project_id) else version
                result = session.run(
                    "MATCH (pkg:Package {id: $pkg_id}) RETURN pkg",
                    {"pkg_id": pkg_id}
                )
            else:
                # Load latest version (highest timestamp)
                result = session.run("""
                    MATCH (pkg:Package {projectId: $project_id})
                    RETURN pkg
                    ORDER BY pkg.timestamp DESC
                    LIMIT 1
                """, {"project_id": project_id})
            
            record = result.single()
            if record:
                pkg_node = record["pkg"]
                package_data = {
                    "version": pkg_node.get("version", "1.0.0"),
                    "generatedAt": pkg_node.get("generatedAt"),
                    "gitSha": pkg_node.get("gitSha")
                }
            else:
                # Fallback: try old format (backward compatibility)
                result = session.run(
                    "MATCH (pkg:Package {id: $project_id}) RETURN pkg",
                    {"project_id": project_id}
                )
                record = result.single()
                if record:
                    pkg_node = record["pkg"]
                    package_data = {
                        "version": pkg_node.get("version", "1.0.0"),
                        "generatedAt": pkg_node.get("generatedAt"),
                        "gitSha": pkg_node.get("gitSha")
                    }
            
            # 2. Load Project node and Metadata
            project_data = {}
            metadata_data = {}
            result = session.run("""
                MATCH (proj:Project {id: $project_id})
                OPTIONAL MATCH (proj)-[:HAS_METADATA]->(m:Metadata {projectId: $project_id})
                RETURN proj, m
            """, {"project_id": project_id})
            record = result.single()
            if record:
                proj_node = record["proj"]
                project_data = {
                    "id": proj_node.get("id", project_id),
                    "name": proj_node.get("name", ""),
                    "rootPath": proj_node.get("rootPath", ""),
                    "languages": proj_node.get("languages", []),
                    "frameworks": proj_node.get("frameworks", []),
                    "buildTools": proj_node.get("buildTools", [])
                }
                if record["m"]:
                    meta_node = record["m"]
                    # Extract all metadata properties except projectId
                    metadata_data = {k: v for k, v in meta_node.items() if k != "projectId"}
            
            if not project_data:
                logger.warning(f"Project node not found for {project_id}")
                return None
            
            project_data["metadata"] = metadata_data
            
            # 3. Load Modules
            modules = []
            result = session.run("""
                MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(mod:Module)
                RETURN mod
                ORDER BY mod.id
            """, {"project_id": project_id})
            for record in result:
                mod_node = record["mod"]
                module_dict = {"id": mod_node.get("id")}
                # Add all other properties
                for key, value in mod_node.items():
                    if key != "id" and value is not None:
                        module_dict[key] = value
                modules.append(module_dict)
            
            # 4. Load Symbols
            symbols = []
            result = session.run("""
                MATCH (proj:Project {id: $project_id})-[:HAS_SYMBOL]->(sym:Symbol)
                RETURN sym
                ORDER BY sym.id
            """, {"project_id": project_id})
            for record in result:
                sym_node = record["sym"]
                symbol_dict = {
                    "id": sym_node.get("id"),
                    "name": sym_node.get("name", "")
                }
                # Add all other properties except id and name
                for key, value in sym_node.items():
                    if key not in ["id", "name"] and value is not None:
                        symbol_dict[key] = value
                symbols.append(symbol_dict)
            
            # 5. Load Endpoints
            endpoints = []
            result = session.run("""
                MATCH (proj:Project {id: $project_id})-[:HAS_ENDPOINT]->(end:Endpoint)
                RETURN end
                ORDER BY end.id
            """, {"project_id": project_id})
            for record in result:
                end_node = record["end"]
                endpoint_dict = {
                    "id": end_node.get("id"),
                    "path": end_node.get("path", "")
                }
                # Add all other properties except id and path
                for key, value in end_node.items():
                    if key not in ["id", "path"] and value is not None:
                        endpoint_dict[key] = value
                endpoints.append(endpoint_dict)
            
            # 6. Load Features
            features = []
            feature_module_map = {}  # feature_id -> [module_ids]
            result = session.run("""
                MATCH (proj:Project {id: $project_id})-[:HAS_FEATURE]->(f:Feature)
                RETURN f
                ORDER BY f.id
            """, {"project_id": project_id})
            for record in result:
                feat_node = record["f"]
                feature_id = feat_node.get("id")
                feature_dict = {
                    "id": feature_id,
                    "name": feat_node.get("name", ""),
                    "path": feat_node.get("path", ""),
                    "moduleIds": []
                }
                features.append(feature_dict)
                feature_module_map[feature_id] = []
            
            # 7. Load Feature-Module links
            if feature_module_map:
                feature_ids = list(feature_module_map.keys())
                result = session.run("""
                    MATCH (f:Feature)-[:CONTAINS]->(m:Module)
                    WHERE f.id IN $feature_ids
                    RETURN f.id AS feature_id, m.id AS module_id
                """, {"feature_ids": feature_ids})
                for record in result:
                    feat_id = record["feature_id"]
                    mod_id = record["module_id"]
                    if feat_id in feature_module_map:
                        feature_module_map[feat_id].append(mod_id)
                
                # Update features with module IDs
                for feature in features:
                    feature_id = feature["id"]
                    if feature_id in feature_module_map:
                        feature["moduleIds"] = feature_module_map[feature_id]
            
            # 8. Load Edges (relationships between Modules/Symbols)
            edges = []
            # Query all relationship types between Module and Symbol nodes that belong to this project
            result = session.run("""
                MATCH (proj:Project {id: $project_id})
                MATCH (proj)-[:HAS_MODULE|HAS_SYMBOL]->(a)
                MATCH (a)-[r]->(b)
                WHERE (b:Module OR b:Symbol)
                AND (
                    EXISTS { MATCH (proj)-[:HAS_MODULE]->(b) } OR
                    EXISTS { MATCH (proj)-[:HAS_SYMBOL]->(b) }
                )
                RETURN type(r) AS rel_type, a.id AS from_id, b.id AS to_id, r.weight AS weight
            """, {"project_id": project_id})
            for record in result:
                edge_dict = {
                    "from": record["from_id"],
                    "to": record["to_id"],
                    "type": record["rel_type"]
                }
                if record["weight"] is not None:
                    edge_dict["weight"] = record["weight"]
                edges.append(edge_dict)
            
            # Reconstruct PKG dict matching the schema
            pkg = {
                "version": package_data.get("version", "1.0.0"),
                "generatedAt": package_data.get("generatedAt"),
                "gitSha": package_data.get("gitSha"),
                "project": project_data,
                "modules": modules,
                "symbols": symbols,
                "endpoints": endpoints,
                "edges": edges
            }
            
            # Add features if they exist
            if features:
                pkg["features"] = features
            
            logger.info(f"✅ PKG LOADED FROM NEO4J | Project ID: {project_id} | Modules: {len(modules)} | Symbols: {len(symbols)} | Endpoints: {len(endpoints)} | Edges: {len(edges)} | Features: {len(features)}")
            
            return pkg
            
    except ConnectionError as e:
        logger.error(f"❌ NEO4J CONNECTION ERROR | Project ID: {project_id} | Error: {e}")
        return None
    except Exception as e:
        logger.error(
            f"❌ LOAD PKG ERROR | Project ID: {project_id} | Error: {e}",
            exc_info=True
        )
        return None


def migrate_existing_pkgs() -> int:
    """
    Migrate existing PKG data to compute metrics for modules that don't have them.
    
    Returns:
        Number of modules updated
    """
    logger.info("🔄 MIGRATING EXISTING PKGS | Computing metrics for existing modules")
    if not verify_connection():
        logger.warning("⚠️  NEO4J NOT CONNECTED | Cannot migrate existing PKGs")
        return 0
    
    try:
        with get_session() as session:
            # Find modules without metrics
            result = session.run("""
                MATCH (mod:Module)
                WHERE mod.fan_in IS NULL OR mod.fan_out IS NULL OR mod.centrality IS NULL OR mod.complexity IS NULL
                RETURN mod.id AS module_id
                LIMIT 1000
            """)
            
            module_ids = [record["module_id"] for record in result]
            
            if not module_ids:
                logger.info("✅ NO MIGRATION NEEDED | All modules already have metrics")
                return 0
            
            logger.info(f"📊 MIGRATING MODULES | Found {len(module_ids)} modules without metrics")
            
            # Calculate and update metrics in batches
            updated_count = 0
            for i in range(0, len(module_ids), batch_size):
                batch_ids = module_ids[i:i + batch_size]
                
                # Calculate metrics for batch
                session.run("""
                    UNWIND $module_ids AS module_id
                    MATCH (mod:Module {id: module_id})
                    
                    // Calculate fan_in (modules that import this module)
                    OPTIONAL MATCH (caller:Module)-[r:IMPORTS]->(mod)
                    WITH mod, module_id, count(DISTINCT caller) AS fan_in
                    
                    // Calculate fan_out (modules this module imports)
                    OPTIONAL MATCH (mod)-[r:IMPORTS]->(callee:Module)
                    WITH mod, module_id, fan_in, count(DISTINCT callee) AS fan_out
                    
                    // Calculate complexity from exports and imports arrays
                    WITH mod, module_id, fan_in, fan_out,
                         CASE WHEN mod.exports IS NOT NULL THEN size(mod.exports) ELSE 0 END AS exports_count,
                         CASE WHEN mod.imports IS NOT NULL THEN size(mod.imports) ELSE 0 END AS imports_count
                    
                    SET mod.fan_in = fan_in,
                        mod.fan_out = fan_out,
                        mod.centrality = fan_in + fan_out,
                        mod.complexity = exports_count + imports_count
                """, {"module_ids": batch_ids})
                
                updated_count += len(batch_ids)
                logger.debug(f"✅ MIGRATED BATCH | Updated {len(batch_ids)} modules")
            
            logger.info(f"✅ MIGRATION COMPLETE | Updated {updated_count} modules with metrics")
            return updated_count
            
    except Exception as e:
        logger.error(f"❌ MIGRATION ERROR | Error: {e}", exc_info=True)
        return 0


# Initialize driver on module import
if uri and user and password:
    driver = _initialize_driver()
else:
    logger.warning("Neo4j not configured. Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD environment variables.")

"""Neo4j Query Engine - Queries Neo4j database for PKG data."""

import logging
from typing import Dict, Any, List, Optional
from db.neo4j_db import get_session, verify_connection

logger = logging.getLogger(__name__)


class Neo4jQueryEngine:
    """Query engine for Neo4j database that complements PKGQueryEngine."""
    
    def __init__(self, database: Optional[str] = None):
        """
        Initialize Neo4j query engine.
        
        Args:
            database: Optional database name (defaults to env config)
        """
        self.database = database
        if not verify_connection():
            logger.warning("Neo4j connection not available. Some queries may fail.")
    
    def _execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            
        Returns:
            List of result dictionaries
        """
        if not verify_connection():
            logger.error("Cannot execute query: Neo4j connection not available")
            return []
        
        try:
            with get_session() as session:
                result = session.run(query, parameters or {})
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error executing Neo4j query: {e}", exc_info=True)
            return []
    
    # ==================== Phase 2.2: Basic Module Queries ====================
    
    def get_modules_by_tag(self, project_id: str, tag: str) -> List[Dict[str, Any]]:
        """Find modules with matching tag/kind."""
        query = """
        MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(mod:Module)
        WHERE $tag IN mod.kind
        RETURN mod
        ORDER BY mod.path
        """
        results = self._execute_query(query, {"project_id": project_id, "tag": tag})
        return [record["mod"] for record in results]
    
    def get_modules_by_path_pattern(self, project_id: str, pattern: str) -> List[Dict[str, Any]]:
        """Find modules matching path pattern."""
        regex_pattern = pattern.replace('*', '.*')
        query = """
        MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(mod:Module)
        WHERE mod.path =~ $pattern
        RETURN mod
        ORDER BY mod.path
        """
        results = self._execute_query(query, {
            "project_id": project_id,
            "pattern": f"(?i){regex_pattern}"
        })
        return [record["mod"] for record in results]
    
    def get_modules_by_project(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all modules for a project."""
        query = """
        MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(mod:Module)
        RETURN mod
        ORDER BY mod.path
        """
        results = self._execute_query(query, {"project_id": project_id})
        return [record["mod"] for record in results]
    
    def get_module_by_id(self, module_id: str) -> Optional[Dict[str, Any]]:
        """Get module by ID."""
        query = """
        MATCH (mod:Module {id: $module_id})
        RETURN mod
        LIMIT 1
        """
        results = self._execute_query(query, {"module_id": module_id})
        return results[0]["mod"] if results else None
    
    # ==================== Phase 2.3: Dependency Path Queries ====================
    
    def get_dependencies(self, module_id: str) -> Dict[str, Any]:
        """Get callers (fan-in) and callees (fan-out) for a module."""
        callers_query = """
        MATCH (caller:Module)-[r]->(mod:Module {id: $module_id})
        RETURN caller, r
        """
        callers_results = self._execute_query(callers_query, {"module_id": module_id})
        callers = [record["caller"] for record in callers_results]
        
        callees_query = """
        MATCH (mod:Module {id: $module_id})-[r]->(callee:Module)
        RETURN callee, r
        """
        callees_results = self._execute_query(callees_query, {"module_id": module_id})
        callees = [record["callee"] for record in callees_results]
        
        return {
            "callers": callers,
            "callees": callees,
            "fan_in_count": len(callers),
            "fan_out_count": len(callees)
        }
    
    def get_shortest_path(self, from_module_id: str, to_module_id: str) -> Optional[List[Dict[str, Any]]]:
        """Find shortest path between two modules."""
        query = """
        MATCH path = shortestPath((from:Module {id: $from_id})-[*..10]->(to:Module {id: $to_id}))
        RETURN [node in nodes(path) | node] as modules
        LIMIT 1
        """
        results = self._execute_query(query, {"from_id": from_module_id, "to_id": to_module_id})
        if results and results[0].get("modules"):
            return results[0]["modules"]
        return None
    
    def get_all_paths(self, from_module_id: str, to_module_id: str, max_depth: int = 5) -> List[List[Dict[str, Any]]]:
        """Find all paths between two modules."""
        query = f"""
        MATCH path = (from:Module {{id: $from_id}})-[*1..{max_depth}]->(to:Module {{id: $to_id}})
        RETURN [node in nodes(path) | node] as modules
        LIMIT 50
        """
        results = self._execute_query(query, {"from_id": from_module_id, "to_id": to_module_id})
        return [record["modules"] for record in results]
    
    def detect_circular_dependencies(self, project_id: str) -> List[List[Dict[str, Any]]]:
        """Detect circular dependencies in a project."""
        query = """
        MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(mod:Module)
        MATCH path = (mod)-[*2..10]->(mod)
        WHERE ALL(n in nodes(path) WHERE (proj)-[:HAS_MODULE]->(n))
        RETURN [node in nodes(path) | node] as cycle
        LIMIT 20
        """
        results = self._execute_query(query, {"project_id": project_id})
        return [record["cycle"] for record in results]
    
    # ==================== Phase 2.4: Impact Analysis Queries ====================
    
    def get_impacted_modules(self, module_ids: List[str], depth: int = 2) -> Dict[str, Any]:
        """Build transitive closure of dependencies for given modules."""
        if not module_ids:
            return {"impacted_modules": [], "impacted_module_ids": [], "impacted_files": []}
        
        query = f"""
        MATCH path = (start:Module)-[*0..{depth}]->(affected:Module)
        WHERE start.id IN $module_ids
        RETURN DISTINCT affected
        """
        results = self._execute_query(query, {"module_ids": module_ids})
        impacted_modules = [record["affected"] for record in results]
        impacted_module_ids = [mod["id"] for mod in impacted_modules]
        impacted_files = [mod.get("path", "") for mod in impacted_modules if mod.get("path")]
        
        return {
            "impacted_modules": impacted_modules,
            "impacted_module_ids": impacted_module_ids,
            "impacted_files": impacted_files,
            "depth_reached": depth
        }
    
    def get_feature_impact(self, feature_id: str, depth: int = 2) -> Dict[str, Any]:
        """Find all modules affected by a feature change."""
        query = f"""
        MATCH (f:Feature {{id: $feature_id}})-[:CONTAINS]->(m:Module)
        MATCH path = (m)-[*0..{depth}]->(affected:Module)
        RETURN DISTINCT affected
        """
        results = self._execute_query(query, {"feature_id": feature_id})
        impacted_modules = [record["affected"] for record in results]
        impacted_module_ids = [mod["id"] for mod in impacted_modules]
        impacted_files = [mod.get("path", "") for mod in impacted_modules if mod.get("path")]
        
        return {
            "impacted_modules": impacted_modules,
            "impacted_module_ids": impacted_module_ids,
            "impacted_files": impacted_files,
            "feature_id": feature_id,
            "depth": depth
        }
    
    def get_endpoints_by_path(self, project_id: str, path_pattern: str) -> List[Dict[str, Any]]:
        """Find endpoints matching path pattern."""
        regex_pattern = path_pattern.replace('*', '.*')
        query = """
        MATCH (proj:Project {id: $project_id})-[:HAS_ENDPOINT]->(end:Endpoint)
        WHERE end.path =~ $pattern
        RETURN end
        ORDER BY end.path
        """
        results = self._execute_query(query, {
            "project_id": project_id,
            "pattern": f"(?i){regex_pattern}"
        })
        return [record["end"] for record in results]
    
    def get_symbols_by_name(self, project_id: str, name_pattern: str) -> List[Dict[str, Any]]:
        """Find symbols matching name pattern."""
        regex_pattern = name_pattern.replace('*', '.*')
        query = """
        MATCH (proj:Project {id: $project_id})-[:HAS_SYMBOL]->(sym:Symbol)
        WHERE sym.name =~ $pattern
        RETURN sym
        ORDER BY sym.name
        """
        results = self._execute_query(query, {
            "project_id": project_id,
            "pattern": f"(?i){regex_pattern}"
        })
        return [record["sym"] for record in results]
    
    # ==================== Phase 4.1: Multi-Repository Support ====================
    
    def compare_projects(self, project_id1: str, project_id2: str) -> Dict[str, Any]:
        """Compare two projects."""
        query1 = """
        MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(mod:Module)
        RETURN count(mod) as module_count
        """
        count1 = self._execute_query(query1, {"project_id": project_id1})
        count2 = self._execute_query(query1, {"project_id": project_id2})
        
        query2 = """
        MATCH (proj1:Project {id: $project_id1})-[:HAS_MODULE]->(mod1:Module)
        MATCH (proj2:Project {id: $project_id2})-[:HAS_MODULE]->(mod2:Module)
        WHERE mod1.kind = mod2.kind
        RETURN DISTINCT mod1.kind as shared_kind
        """
        shared_kinds = self._execute_query(query2, {
            "project_id1": project_id1,
            "project_id2": project_id2
        })
        
        return {
            "project1": {"id": project_id1, "module_count": count1[0]["module_count"] if count1 else 0},
            "project2": {"id": project_id2, "module_count": count2[0]["module_count"] if count2 else 0},
            "shared_kinds": [r["shared_kind"] for r in shared_kinds]
        }
    
    def find_shared_patterns(self, project_ids: List[str]) -> List[Dict[str, Any]]:
        """Find shared patterns across multiple projects."""
        query = """
        MATCH (proj:Project)-[:HAS_MODULE]->(mod:Module)
        WHERE proj.id IN $project_ids
        WITH mod.kind as kind, count(DISTINCT proj.id) as project_count
        WHERE project_count = $total_projects
        RETURN kind, project_count
        """
        results = self._execute_query(query, {
            "project_ids": project_ids,
            "total_projects": len(project_ids)
        })
        return [dict(record) for record in results]
    
    def get_cross_project_dependencies(self, project_id: str) -> List[Dict[str, Any]]:
        """Get dependencies that cross project boundaries."""
        query = """
        MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(mod1:Module)
        MATCH (mod1)-[r]->(mod2:Module)
        WHERE NOT (proj)-[:HAS_MODULE]->(mod2)
        RETURN mod1, mod2, r
        """
        results = self._execute_query(query, {"project_id": project_id})
        return [dict(record) for record in results]
    
    # ==================== Phase 4.2: Graph Algorithms ====================
    
    def get_critical_modules(self, project_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get modules with high importance (high fan-in)."""
        query = """
        MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(mod:Module)
        OPTIONAL MATCH (caller:Module)-[r]->(mod)
        WHERE (proj)-[:HAS_MODULE]->(caller)
        WITH mod, count(DISTINCT caller) as fan_in
        ORDER BY fan_in DESC
        LIMIT $limit
        RETURN mod, fan_in
        """
        results = self._execute_query(query, {"project_id": project_id, "limit": limit})
        return [{"module": record["mod"], "fan_in": record["fan_in"]} for record in results]
    
    def get_module_centrality(self, module_id: str) -> Dict[str, Any]:
        """Calculate centrality metrics for a module."""
        fan_in_query = """
        MATCH (caller:Module)-[r]->(mod:Module {id: $module_id})
        RETURN count(DISTINCT caller) as fan_in
        """
        fan_in_result = self._execute_query(fan_in_query, {"module_id": module_id})
        fan_in = fan_in_result[0]["fan_in"] if fan_in_result else 0
        
        fan_out_query = """
        MATCH (mod:Module {id: $module_id})-[r]->(callee:Module)
        RETURN count(DISTINCT callee) as fan_out
        """
        fan_out_result = self._execute_query(fan_out_query, {"module_id": module_id})
        fan_out = fan_out_result[0]["fan_out"] if fan_out_result else 0
        
        return {
            "module_id": module_id,
            "fan_in": fan_in,
            "fan_out": fan_out,
            "total_degree": fan_in + fan_out
        }
    
    # ==================== Phase 4.3: Code Smell Detection ====================
    
    def detect_god_objects(self, project_id: str, threshold: int = 10) -> List[Dict[str, Any]]:
        """Detect modules with too many dependencies (god objects)."""
        query = """
        MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(mod:Module)
        OPTIONAL MATCH (mod)-[r]->(dep:Module)
        WHERE (proj)-[:HAS_MODULE]->(dep)
        WITH mod, count(DISTINCT dep) as dep_count
        WHERE dep_count > $threshold
        RETURN mod, dep_count
        ORDER BY dep_count DESC
        """
        results = self._execute_query(query, {"project_id": project_id, "threshold": threshold})
        return [{"module": record["mod"], "dependency_count": record["dep_count"]} for record in results]
    
    def detect_high_coupling(self, project_id: str, threshold: int = 15) -> List[Dict[str, Any]]:
        """Detect modules with high coupling."""
        query = """
        MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(mod:Module)
        OPTIONAL MATCH (caller:Module)-[r1]->(mod)
        WHERE (proj)-[:HAS_MODULE]->(caller)
        OPTIONAL MATCH (mod)-[r2]->(callee:Module)
        WHERE (proj)-[:HAS_MODULE]->(callee)
        WITH mod, count(DISTINCT caller) as fan_in, count(DISTINCT callee) as fan_out
        WHERE (fan_in + fan_out) > $threshold
        RETURN mod, fan_in, fan_out, (fan_in + fan_out) as total_coupling
        ORDER BY total_coupling DESC
        """
        results = self._execute_query(query, {"project_id": project_id, "threshold": threshold})
        return [dict(record) for record in results]
    
    def get_code_smells(self, project_id: str) -> Dict[str, Any]:
        """Get comprehensive code smell report for a project."""
        god_objects = self.detect_god_objects(project_id)
        circular_deps = self.detect_circular_dependencies(project_id)
        high_coupling = self.detect_high_coupling(project_id)
        
        return {
            "god_objects": god_objects,
            "circular_dependencies": circular_deps,
            "high_coupling": high_coupling,
            "summary": {
                "god_object_count": len(god_objects),
                "circular_dependency_count": len(circular_deps),
                "high_coupling_count": len(high_coupling)
            }
        }
    
    # ==================== Phase 4.4: Feature Impact Analysis ====================
    
    def get_feature_dependencies(self, feature_id: str) -> Dict[str, Any]:
        """Get dependency graph for a feature."""
        query = """
        MATCH (f:Feature {id: $feature_id})-[:CONTAINS]->(mod:Module)
        OPTIONAL MATCH (mod)-[r]->(dep:Module)
        RETURN mod, collect(DISTINCT dep) as dependencies
        """
        results = self._execute_query(query, {"feature_id": feature_id})
        
        return {
            "feature_id": feature_id,
            "modules": [record["mod"] for record in results],
            "dependencies": [dep for record in results for dep in record["dependencies"]]
        }
    
    # ==================== Phase 4.5: Version Comparison ====================
    
    def get_version_history(self, project_id: str) -> List[Dict[str, Any]]:
        """Get version history for a project."""
        query = """
        MATCH (pkg:Package {id: $project_id})
        RETURN pkg.version as version, pkg.generatedAt as generatedAt, pkg.timestamp as timestamp
        ORDER BY pkg.timestamp DESC
        """
        results = self._execute_query(query, {"project_id": project_id})
        return [dict(record) for record in results]
    
    def compare_versions(self, project_id: str, version1: str, version2: str) -> Dict[str, Any]:
        """Compare two versions of a project."""
        return {
            "project_id": project_id,
            "version1": version1,
            "version2": version2,
            "note": "Version comparison requires versioned storage implementation"
        }
    
    # ==================== Phase 4.6: Similar Project Discovery ====================
    
    def find_similar_projects(self, project_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Find projects with similar structure."""
        query = """
        MATCH (proj1:Project {id: $project_id})-[:HAS_MODULE]->(mod1:Module)
        WITH collect(DISTINCT mod1.kind) as kinds1
        
        MATCH (proj2:Project)-[:HAS_MODULE]->(mod2:Module)
        WHERE proj2.id <> $project_id
        WITH kinds1, proj2, collect(DISTINCT mod2.kind) as kinds2
        
        WITH proj2, 
             size([k in kinds1 WHERE k IN kinds2]) as shared_kinds,
             size(kinds1) as total_kinds1,
             size(kinds2) as total_kinds2
        
        WHERE shared_kinds > 0
        RETURN proj2, 
               shared_kinds,
               toFloat(shared_kinds) / (total_kinds1 + total_kinds2 - shared_kinds) as similarity
        ORDER BY similarity DESC
        LIMIT $limit
        """
        results = self._execute_query(query, {"project_id": project_id, "limit": limit})
        return [dict(record) for record in results]
    
    def compare_architectures(self, project_id1: str, project_id2: str) -> Dict[str, Any]:
        """Compare architectures of two projects."""
        comparison = self.compare_projects(project_id1, project_id2)
        
        query = """
        MATCH (proj:Project {id: $project_id})-[:HAS_MODULE]->(mod:Module)
        WITH mod.kind as kind, count(*) as count
        RETURN kind, count
        ORDER BY count DESC
        """
        
        arch1 = self._execute_query(query, {"project_id": project_id1})
        arch2 = self._execute_query(query, {"project_id": project_id2})
        
        comparison["architecture1"] = {r["kind"]: r["count"] for r in arch1}
        comparison["architecture2"] = {r["kind"]: r["count"] for r in arch2}
        
        return comparison

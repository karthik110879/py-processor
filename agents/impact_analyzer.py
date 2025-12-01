"""Impact Analyzer - Analyzes the impact of proposed changes."""

import logging
import os
from typing import Dict, Any, List, Set
from services.pkg_query_engine import PKGQueryEngine

logger = logging.getLogger(__name__)


class ImpactAnalyzer:
    """Analyzes impact of proposed code changes using PKG data."""
    
    def __init__(self, pkg_data: Dict[str, Any]):
        """
        Initialize impact analyzer.
        
        Args:
            pkg_data: PKG data dictionary
        """
        self.pkg_data = pkg_data
        self.query_engine = PKGQueryEngine(pkg_data)
    
    def analyze_impact(
        self,
        intent: Dict[str, Any],
        target_module_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Analyze impact of proposed changes.
        
        Args:
            intent: Intent dictionary
            target_module_ids: List of target module IDs
            
        Returns:
            Impact analysis result dictionary
        """
        try:
            # Build dependency graph
            impact_result = self.query_engine.get_impacted_modules(
                target_module_ids,
                depth=2
            )
            
            impacted_modules = impact_result.get('impacted_modules', [])
            impacted_files = impact_result.get('impacted_files', [])
            
            # Calculate risk score
            risk_score = self.calculate_risk_score(impacted_files, impacted_modules)
            
            # Find affected tests
            affected_tests = self.find_affected_tests(impacted_modules)
            
            # Calculate fan-in/fan-out metrics
            total_fan_in = 0
            total_fan_out = 0
            
            for module_id in target_module_ids:
                deps = self.query_engine.get_dependencies(module_id)
                total_fan_in += deps.get('fan_in_count', 0)
                total_fan_out += deps.get('fan_out_count', 0)
            
            # Determine if approval is required
            requires_approval = self._requires_approval(
                risk_score,
                len(impacted_files),
                total_fan_in,
                intent
            )
            
            # Estimate complexity
            estimated_complexity = self._estimate_complexity(
                len(impacted_files),
                total_fan_in,
                total_fan_out
            )
            
            return {
                "impacted_modules": impacted_modules,
                "impacted_module_ids": impact_result.get('impacted_module_ids', []),
                "impacted_files": impacted_files,
                "affected_tests": affected_tests,
                "risk_score": risk_score,
                "fan_in_count": total_fan_in,
                "fan_out_count": total_fan_out,
                "requires_approval": requires_approval,
                "estimated_complexity": estimated_complexity,
                "file_count": len(impacted_files),
                "module_count": len(impacted_modules)
            }
        
        except Exception as e:
            logger.error(f"Error analyzing impact: {e}", exc_info=True)
            return {
                "impacted_modules": [],
                "impacted_files": [],
                "affected_tests": [],
                "risk_score": "high",
                "fan_in_count": 0,
                "fan_out_count": 0,
                "requires_approval": True,
                "estimated_complexity": "unknown",
                "error": str(e)
            }
    
    def calculate_risk_score(
        self,
        impacted_files: List[str],
        impacted_modules: List[Dict[str, Any]]
    ) -> str:
        """
        Calculate risk score based on impact.
        
        Args:
            impacted_files: List of impacted file paths
            impacted_modules: List of impacted module dictionaries
            
        Returns:
            Risk score: "low", "medium", or "high"
        """
        file_count = len(impacted_files)
        
        # Calculate average fan-in for impacted modules
        total_fan_in = 0
        for module in impacted_modules:
            module_id = module.get('id')
            if module_id:
                deps = self.query_engine.get_dependencies(module_id)
                total_fan_in += deps.get('fan_in_count', 0)
        
        avg_fan_in = total_fan_in / len(impacted_modules) if impacted_modules else 0
        
        # Risk calculation logic
        if file_count < 3 and avg_fan_in < 5:
            return "low"
        elif file_count < 10 and avg_fan_in < 15:
            return "medium"
        else:
            return "high"
    
    def find_affected_tests(self, modules: List[Dict[str, Any]]) -> List[str]:
        """
        Find test files affected by module changes.
        
        Args:
            modules: List of module dictionaries
            
        Returns:
            List of test file paths
        """
        test_files: Set[str] = set()
        
        for module in modules:
            module_path = module.get('path', '')
            if not module_path:
                continue
            
            # Look for test files using common patterns
            # Pattern 1: test_*.py, *_test.py (Python)
            # Pattern 2: *.spec.ts, *.test.ts (TypeScript)
            # Pattern 3: *Test.java (Java)
            # Pattern 4: *Tests.cs (C#)
            
            base_path = module_path.rsplit('.', 1)[0] if '.' in module_path else module_path
            dir_path = '/'.join(module_path.split('/')[:-1]) if '/' in module_path else ''
            
            # Check for test files in same directory
            test_patterns = [
                f"test_{base_path.split('/')[-1]}.py",
                f"{base_path.split('/')[-1]}_test.py",
                f"{base_path}.spec.ts",
                f"{base_path}.test.ts",
                f"{base_path}Test.java",
                f"{base_path}Tests.cs"
            ]
            
            # Also check in tests/ directory
            if dir_path:
                test_dir_patterns = [
                    f"tests/{base_path.split('/')[-1]}.py",
                    f"tests/test_{base_path.split('/')[-1]}.py",
                    f"test/{base_path.split('/')[-1]}.py",
                    f"__tests__/{base_path.split('/')[-1]}.test.ts",
                    f"src/test/java/{dir_path}/{base_path.split('/')[-1]}Test.java"
                ]
                test_patterns.extend(test_dir_patterns)
            
            # Search for test files in PKG
            for test_pattern in test_patterns:
                matching_modules = self.query_engine.get_modules_by_path_pattern(test_pattern)
                for test_module in matching_modules:
                    test_path = test_module.get('path')
                    if test_path:
                        test_files.add(test_path)
            
            # Also check edges for test relationships
            module_id = module.get('id')
            if module_id:
                # Look for edges with type "tests"
                for edge in self.query_engine.edges:
                    if (edge.get('type') == 'tests' and 
                        edge.get('to') == module_id):
                        from_id = edge.get('from')
                        if from_id:
                            from_module = self.query_engine.get_module_by_id(from_id)
                            if from_module:
                                test_path = from_module.get('path')
                                if test_path:
                                    test_files.add(test_path)
        
        return sorted(list(test_files))
    
    def _requires_approval(
        self,
        risk_score: str,
        file_count: int,
        fan_in_count: int,
        intent: Dict[str, Any]
    ) -> bool:
        """
        Determine if human approval is required.
        
        Args:
            risk_score: Calculated risk score
            file_count: Number of impacted files
            fan_in_count: Total fan-in count
            intent: Intent dictionary
            
        Returns:
            True if approval is required
        """
        # Check environment variable
        approval_required = os.getenv('AGENT_APPROVAL_REQUIRED', 'true').lower() == 'true'
        auto_apply_low_risk = os.getenv('AGENT_AUTO_APPLY_LOW_RISK', 'false').lower() == 'true'
        max_files_auto = int(os.getenv('MAX_IMPACTED_FILES_FOR_AUTO_APPROVAL', '5'))
        
        # Intent explicitly requires approval
        if intent.get('human_approval', False):
            return True
        
        # High risk always requires approval
        if risk_score == "high":
            return True
        
        # Check for migrations (high risk)
        constraints = intent.get('constraints', [])
        if any('migration' in c.lower() for c in constraints):
            require_migration_approval = os.getenv(
                'REQUIRE_HUMAN_APPROVAL_FOR_MIGRATIONS',
                'true'
            ).lower() == 'true'
            if require_migration_approval:
                return True
        
        # Auto-apply low risk if configured
        if auto_apply_low_risk and risk_score == "low" and file_count <= max_files_auto:
            return False
        
        # Default: require approval
        return approval_required
    
    def _estimate_complexity(
        self,
        file_count: int,
        fan_in_count: int,
        fan_out_count: int
    ) -> str:
        """
        Estimate complexity of changes.
        
        Args:
            file_count: Number of files
            fan_in_count: Total fan-in
            fan_out_count: Total fan-out
            
        Returns:
            Complexity estimate: "low", "medium", or "high"
        """
        complexity_score = 0
        
        # File count contribution
        if file_count > 10:
            complexity_score += 3
        elif file_count > 5:
            complexity_score += 2
        elif file_count > 2:
            complexity_score += 1
        
        # Fan-in contribution
        if fan_in_count > 20:
            complexity_score += 2
        elif fan_in_count > 10:
            complexity_score += 1
        
        # Fan-out contribution
        if fan_out_count > 15:
            complexity_score += 2
        elif fan_out_count > 8:
            complexity_score += 1
        
        if complexity_score >= 5:
            return "high"
        elif complexity_score >= 3:
            return "medium"
        else:
            return "low"

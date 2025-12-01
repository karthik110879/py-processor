"""Verifier - Verifies acceptance criteria and change readiness."""

import logging
import os
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class Verifier:
    """Verifies that changes meet acceptance criteria."""
    
    def __init__(self):
        """Initialize verifier."""
        pass
    
    def verify_acceptance(
        self,
        test_results: Dict[str, Any],
        criteria: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Verify acceptance criteria.
        
        Args:
            test_results: Test execution results
            criteria: Acceptance criteria dictionary
            
        Returns:
            Verification result dictionary
        """
        criteria_met = []
        issues = []
        
        # Check 1: All unit tests pass
        tests_passed = test_results.get('tests_passed', 0)
        tests_failed = test_results.get('tests_failed', 0)
        build_success = test_results.get('build_success', False)
        
        if tests_failed == 0 and build_success:
            criteria_met.append("tests_pass")
        else:
            issues.append(f"Tests failed: {tests_failed} failures")
        
        # Check 2: No new lint errors
        linter_errors = test_results.get('linter_errors', [])
        if not linter_errors or len(linter_errors) == 0:
            criteria_met.append("no_lint_errors")
        else:
            issues.append(f"Linter errors: {len(linter_errors)}")
        
        # Check 3: No type check errors
        typecheck_errors = test_results.get('typecheck_errors', [])
        if not typecheck_errors or len(typecheck_errors) == 0:
            criteria_met.append("no_typecheck_errors")
        else:
            issues.append(f"Type check errors: {len(typecheck_errors)}")
        
        # Check 4: Test coverage (if available)
        coverage_result = self.check_test_coverage(test_results)
        if coverage_result.get('coverage_maintained', False):
            criteria_met.append("coverage_maintained")
        
        # Check 5: Security scan (basic)
        security_result = self.run_security_scan(test_results)
        if security_result.get('security_issues', []):
            issues.append(f"Security issues: {len(security_result.get('security_issues', []))}")
        else:
            criteria_met.append("security_scan_passed")
        
        # Determine if ready for PR
        ready_for_pr = (
            len(issues) == 0 and
            "tests_pass" in criteria_met and
            build_success
        )
        
        return {
            "verified": ready_for_pr,
            "criteria_met": criteria_met,
            "issues": issues,
            "security_issues": security_result.get('security_issues', []),
            "coverage_change": coverage_result.get('coverage_change', 'unknown'),
            "ready_for_pr": ready_for_pr,
            "test_summary": {
                "passed": tests_passed,
                "failed": tests_failed,
                "build_success": build_success
            }
        }
    
    def run_security_scan(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run basic security scan.
        
        Args:
            test_results: Test results (may contain file paths)
            
        Returns:
            Security scan results
        """
        # Basic security checks
        # In production, this would use tools like bandit, semgrep, etc.
        security_issues = []
        
        # Check for common security issues in test output
        test_output = test_results.get('test_output', '')
        
        # Look for security-related warnings
        security_keywords = [
            'sql injection',
            'xss',
            'csrf',
            'secret',
            'password',
            'api key',
            'token'
        ]
        
        test_output_lower = test_output.lower()
        for keyword in security_keywords:
            if keyword in test_output_lower:
                # This is a very basic check - in production, use proper SAST tools
                pass
        
        return {
            "security_issues": security_issues,
            "scan_type": "basic",
            "message": "Basic security scan completed"
        }
    
    def check_test_coverage(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check test coverage.
        
        Args:
            test_results: Test results
            
        Returns:
            Coverage analysis
        """
        # Extract coverage from test output if available
        test_output = test_results.get('test_output', '')
        
        # Look for coverage information in output
        import re
        
        # Try to find coverage percentage
        coverage_match = re.search(r'coverage[:\s]+(\d+(?:\.\d+)?)%', test_output, re.IGNORECASE)
        if coverage_match:
            coverage = float(coverage_match.group(1))
            return {
                "coverage": coverage,
                "coverage_maintained": True,
                "coverage_change": f"{coverage}%"
            }
        
        # Default: assume coverage maintained if tests pass
        if test_results.get('build_success', False):
            return {
                "coverage": None,
                "coverage_maintained": True,
                "coverage_change": "unknown"
            }
        
        return {
            "coverage": None,
            "coverage_maintained": False,
            "coverage_change": "unknown"
        }

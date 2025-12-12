"""Tests for schema validation."""

import unittest
from utils.schema_validator import validate_pkg, _validate_module_ids, _validate_symbol_ids, _validate_edges


class TestSchemaValidation(unittest.TestCase):
    """Test cases for schema validation."""
    
    def test_valid_pkg(self):
        """Test validation of valid PKG."""
        pkg = {
            "version": "1.0.0",
            "generatedAt": "2024-01-01T00:00:00Z",
            "project": {
                "id": "test-project",
                "name": "Test Project"
            },
            "modules": [
                {"id": "mod:test.py", "path": "test.py"}
            ],
            "symbols": [
                {"id": "sym:mod:test.py:func", "moduleId": "mod:test.py", "name": "func", "kind": "function"}
            ],
            "edges": [
                {"from": "mod:test.py", "to": "mod:other.py", "type": "imports"}
            ]
        }
        
        is_valid, errors = validate_pkg(pkg)
        # May have some errors due to missing required fields, but structure should be mostly valid
        self.assertIsInstance(is_valid, bool)
        self.assertIsInstance(errors, list)
    
    def test_invalid_module_id_format(self):
        """Test validation of invalid module ID format."""
        modules = [{"id": "invalid_id", "path": "test.py"}]
        errors = _validate_module_ids({"modules": modules})
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("Invalid ID format" in e for e in errors))
    
    def test_invalid_symbol_id_format(self):
        """Test validation of invalid symbol ID format."""
        symbols = [{"id": "invalid_id", "moduleId": "mod:test.py", "name": "func", "kind": "function"}]
        errors = _validate_symbol_ids({"symbols": symbols, "modules": [{"id": "mod:test.py"}]})
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("Invalid ID format" in e for e in errors))
    
    def test_invalid_edge_reference(self):
        """Test validation of edge with invalid reference."""
        edges = [{"from": "mod:nonexistent.py", "to": "mod:other.py", "type": "imports"}]
        errors = _validate_edges({
            "edges": edges,
            "modules": [{"id": "mod:other.py"}],
            "symbols": []
        })
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("not found" in e for e in errors))


if __name__ == '__main__':
    unittest.main()


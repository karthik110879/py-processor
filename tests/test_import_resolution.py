"""Tests for import resolution."""

import os
import tempfile
import unittest
from pathlib import Path
from code_parser.relationship_extractor import resolve_import_path, _load_tsconfig_paths, _find_index_file


class TestImportResolution(unittest.TestCase):
    """Test cases for import resolution."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_path = self.temp_dir
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_relative_import_python(self):
        """Test relative Python import resolution."""
        # Create test files
        main_file = os.path.join(self.temp_dir, "main.py")
        utils_file = os.path.join(self.temp_dir, "utils.py")
        
        with open(main_file, 'w') as f:
            f.write("from utils import func")
        with open(utils_file, 'w') as f:
            f.write("def func(): pass")
        
        result = resolve_import_path("from utils import func", main_file, self.repo_path)
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("mod:"))
    
    def test_tsconfig_path_mappings(self):
        """Test TypeScript path mappings."""
        # Create tsconfig.json
        tsconfig = {
            "compilerOptions": {
                "baseUrl": ".",
                "paths": {
                    "@app/*": ["src/app/*"]
                }
            }
        }
        
        import json
        tsconfig_path = os.path.join(self.temp_dir, "tsconfig.json")
        with open(tsconfig_path, 'w') as f:
            json.dump(tsconfig, f)
        
        mappings = _load_tsconfig_paths(self.temp_dir)
        self.assertIn("@app", mappings)
    
    def test_find_index_file(self):
        """Test finding index files."""
        # Create directory with index file
        test_dir = Path(self.temp_dir) / "test"
        test_dir.mkdir()
        index_file = test_dir / "index.ts"
        index_file.write_text("export * from './module'")
        
        found = _find_index_file(test_dir, ['.ts', '.js'])
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "index.ts")


if __name__ == '__main__':
    unittest.main()


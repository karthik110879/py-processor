"""Tests for centralized configuration."""

import os
import unittest
from unittest.mock import patch
from utils.config import Config


class TestConfig(unittest.TestCase):
    """Test cases for Config class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Reset singleton instance
        Config._instance = None
        Config._initialized = False
    
    def test_config_singleton(self):
        """Test that Config is a singleton."""
        config1 = Config()
        config2 = Config()
        self.assertIs(config1, config2)
    
    def test_neo4j_config_defaults(self):
        """Test Neo4j configuration defaults."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            self.assertEqual(config.neo4j_uri, "neo4j://127.0.0.1:7687")
            self.assertEqual(config.neo4j_user, "neo4j")
            self.assertEqual(config.neo4j_database, "neo4j")
            self.assertEqual(config.neo4j_batch_size, 1000)
    
    def test_pkg_config_defaults(self):
        """Test PKG generation configuration defaults."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            self.assertEqual(config.fan_threshold, 3)
            self.assertTrue(config.include_features)
            self.assertTrue(config.cache_enabled)
    
    def test_logging_config_defaults(self):
        """Test logging configuration defaults."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            self.assertEqual(config.log_level, "INFO")
            self.assertEqual(config.log_format, "standard")
            self.assertFalse(config.log_structured)
    
    def test_config_from_env(self):
        """Test configuration from environment variables."""
        with patch.dict(os.environ, {
            "NEO4J_URI": "neo4j://test:7687",
            "NEO4J_USER": "testuser",
            "PKG_FAN_THRESHOLD": "5",
            "LOG_LEVEL": "DEBUG"
        }, clear=False):
            config = Config()
            self.assertEqual(config.neo4j_uri, "neo4j://test:7687")
            self.assertEqual(config.neo4j_user, "testuser")
            self.assertEqual(config.fan_threshold, 5)
            self.assertEqual(config.log_level, "DEBUG")
    
    def test_config_validation(self):
        """Test configuration validation."""
        with patch.dict(os.environ, {
            "NEO4J_BATCH_SIZE": "-1"
        }, clear=False):
            with self.assertRaises(ValueError):
                Config()


if __name__ == '__main__':
    unittest.main()


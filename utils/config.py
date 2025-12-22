"""Centralized configuration management with validation and type safety."""

import os
import json
from typing import Any, Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class Config:
    """Centralized configuration with validation and type safety."""
    
    _instance: Optional['Config'] = None
    
    def __new__(cls):
        """Singleton pattern to ensure single config instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize configuration from environment variables and config files."""
        if self._initialized:
            return
        
        # Load .env file if it exists
        env_file = Path(__file__).parent.parent / '.env'
        if env_file.exists():
            load_dotenv(dotenv_path=env_file)
        else:
            # Also try loading from current directory
            load_dotenv()
        
        self._load_from_env()
        self._load_from_file()  # Fallback to YAML/JSON
        self._validate()
        self._initialized = True
    
    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        # Neo4j Configuration
        self._neo4j_uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
        self._neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self._neo4j_password = os.getenv("NEO4J_PASSWORD", "")
        self._neo4j_database = os.getenv("NEO4J_DATABASE", "neo4j")
        self._neo4j_batch_size = int(os.getenv("NEO4J_BATCH_SIZE", "1000"))
        self._neo4j_max_retries = int(os.getenv("NEO4J_MAX_RETRIES", "3"))
        self._neo4j_retry_delay = float(os.getenv("NEO4J_RETRY_DELAY", "1.0"))
        
        # PKG Generation Configuration
        self._fan_threshold = int(os.getenv("PKG_FAN_THRESHOLD", "3"))
        self._include_features = os.getenv("PKG_INCLUDE_FEATURES", "true").lower() == "true"
        self._cache_enabled = os.getenv("PKG_CACHE_ENABLED", "true").lower() == "true"
        
        # Logging Configuration
        self._log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self._log_format = os.getenv("LOG_FORMAT", "standard")  # "standard" or "json"
        self._log_structured = os.getenv("LOG_STRUCTURED", "false").lower() == "true"
        
        # File Processing Configuration
        self._max_file_size = int(os.getenv("MAX_FILE_SIZE", str(16 * 1024 * 1024)))  # 16MB default
        self._supported_languages = os.getenv("SUPPORTED_LANGUAGES", "python,typescript,javascript,java,c,cpp,csharp").split(",")
        
        # Agent Configuration
        self._approval_required = os.getenv("AGENT_APPROVAL_REQUIRED", "true").lower() == "true"
        self._auto_apply_low_risk = os.getenv("AGENT_AUTO_APPLY_LOW_RISK", "false").lower() == "true"
        self._agent_max_retries = int(os.getenv("AGENT_MAX_RETRIES", "2"))
        self._agent_timeout = int(os.getenv("AGENT_TIMEOUT", "3600"))
        
        # Flask Configuration
        self._host = os.getenv("HOST", "0.0.0.0")
        self._port = int(os.getenv("PORT", "5001"))
        self._debug = os.getenv("DEBUG", "false").lower() == "true"
        self._upload_folder = os.getenv("UPLOAD_FOLDER", "/tmp")
        
        # WebSocket Configuration
        self._websocket_cors_origins = os.getenv("WEBSOCKET_CORS_ORIGINS", "*")
        self._websocket_async_mode = os.getenv("WEBSOCKET_ASYNC_MODE", "eventlet")
        self._websocket_ping_timeout = int(os.getenv("WEBSOCKET_PING_TIMEOUT", "60"))
        self._websocket_ping_interval = int(os.getenv("WEBSOCKET_PING_INTERVAL", "25"))
        
        # Embedding Configuration
        self._embedding_dimension = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
        
        # LLM Configuration
        self._openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self._llm_model = os.getenv("LLM_MODEL", "gpt-4")
        self._llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        self._llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2000"))
        
        # Git/GitHub Configuration
        self._git_user_name = os.getenv("GIT_USER_NAME", "")
        self._git_user_email = os.getenv("GIT_USER_EMAIL", "")
        self._github_token = os.getenv("GITHUB_TOKEN", "")
        self._github_api_url = os.getenv("GITHUB_API_URL", "https://api.github.com")
        
        # Test Runner Configuration
        self._test_runner_timeout = int(os.getenv("TEST_RUNNER_TIMEOUT", "300"))
        self._use_docker_for_tests = os.getenv("USE_DOCKER_FOR_TESTS", "false").lower() == "true"
        self._docker_image_prefix = os.getenv("DOCKER_IMAGE_PREFIX", "test-runner")
        
        # Security Configuration
        self._max_impacted_files_auto_approval = int(os.getenv("MAX_IMPACTED_FILES_FOR_AUTO_APPROVAL", "5"))
        self._require_migration_approval = os.getenv("REQUIRE_HUMAN_APPROVAL_FOR_MIGRATIONS", "true").lower() == "true"
        
        # File Matching Configuration
        self._fuzzy_file_matching_enabled = os.getenv("FUZZY_FILE_MATCHING_ENABLED", "true").lower() == "true"
        self._fuzzy_match_confidence_threshold = float(os.getenv("FUZZY_MATCH_CONFIDENCE_THRESHOLD", "0.8"))
        self._enable_file_validation = os.getenv("ENABLE_FILE_VALIDATION", "true").lower() == "true"
        self._log_llm_prompts = os.getenv("LOG_LLM_PROMPTS", "false").lower() == "true"
        
        # AST Editing Configuration
        self._use_ast_editing = os.getenv("USE_AST_EDITING", "true").lower() == "true"
        
        # Iterative Fix Configuration
        self._max_fix_retries = int(os.getenv("MAX_FIX_RETRIES", "3"))
        self._auto_fix_lint = os.getenv("AUTO_FIX_LINT", "true").lower() == "true"
        self._include_code_examples = os.getenv("INCLUDE_CODE_EXAMPLES", "true").lower() == "true"
        self._fix_on_test_failure = os.getenv("FIX_ON_TEST_FAILURE", "true").lower() == "true"
        
        # Code Edits Configuration
        self._code_edits_enabled = os.getenv("CODE_EDITS_ENABLED", "false").lower() == "true"
    
    def _load_from_file(self) -> None:
        """Load configuration from config.yaml or config.json as fallback."""
        # Try to find config file in project root
        current_dir = Path(__file__).parent.parent
        config_files = [
            current_dir / "config.yaml",
            current_dir / "config.json",
            current_dir / ".config.yaml",
            current_dir / ".config.json"
        ]
        
        config_data: Optional[Dict[str, Any]] = None
        
        for config_file in config_files:
            if config_file.exists():
                try:
                    if config_file.suffix == ".yaml":
                        if YAML_AVAILABLE:
                            with open(config_file, 'r', encoding='utf-8') as f:
                                config_data = yaml.safe_load(f)
                        else:
                            continue  # Skip YAML files if yaml not available
                    elif config_file.suffix == ".json":
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                    
                    if config_data:
                        self._apply_config_data(config_data)
                        break
                except Exception:
                    # Silently fail if config file can't be read
                    continue
    
    def _apply_config_data(self, config_data: Dict[str, Any]) -> None:
        """Apply configuration data from file, only if env var not set."""
        # Neo4j
        if "neo4j" in config_data:
            neo4j = config_data["neo4j"]
            if not os.getenv("NEO4J_URI"):
                self._neo4j_uri = neo4j.get("uri", self._neo4j_uri)
            if not os.getenv("NEO4J_USER"):
                self._neo4j_user = neo4j.get("user", self._neo4j_user)
            if not os.getenv("NEO4J_PASSWORD"):
                self._neo4j_password = neo4j.get("password", self._neo4j_password)
            if not os.getenv("NEO4J_DATABASE"):
                self._neo4j_database = neo4j.get("database", self._neo4j_database)
            if not os.getenv("NEO4J_BATCH_SIZE"):
                self._neo4j_batch_size = neo4j.get("batch_size", self._neo4j_batch_size)
        
        # PKG Generation
        if "pkg" in config_data:
            pkg = config_data["pkg"]
            if not os.getenv("PKG_FAN_THRESHOLD"):
                self._fan_threshold = pkg.get("fan_threshold", self._fan_threshold)
            if not os.getenv("PKG_INCLUDE_FEATURES"):
                self._include_features = pkg.get("include_features", self._include_features)
            if not os.getenv("PKG_CACHE_ENABLED"):
                self._cache_enabled = pkg.get("cache_enabled", self._cache_enabled)
        
        # Logging
        if "logging" in config_data:
            logging = config_data["logging"]
            if not os.getenv("LOG_LEVEL"):
                self._log_level = logging.get("level", self._log_level)
            if not os.getenv("LOG_FORMAT"):
                self._log_format = logging.get("format", self._log_format)
            if not os.getenv("LOG_STRUCTURED"):
                self._log_structured = logging.get("structured", self._log_structured)
        
        # LLM
        if "llm" in config_data:
            llm = config_data["llm"]
            if not os.getenv("OPENAI_API_KEY"):
                self._openai_api_key = llm.get("api_key", self._openai_api_key)
            if not os.getenv("LLM_MODEL"):
                self._llm_model = llm.get("model", self._llm_model)
            if not os.getenv("LLM_TEMPERATURE"):
                self._llm_temperature = llm.get("temperature", self._llm_temperature)
            if not os.getenv("LLM_MAX_TOKENS"):
                self._llm_max_tokens = llm.get("max_tokens", self._llm_max_tokens)
        
        # Git/GitHub
        if "git" in config_data:
            git = config_data["git"]
            if not os.getenv("GIT_USER_NAME"):
                self._git_user_name = git.get("user_name", self._git_user_name)
            if not os.getenv("GIT_USER_EMAIL"):
                self._git_user_email = git.get("user_email", self._git_user_email)
            if not os.getenv("GITHUB_TOKEN"):
                self._github_token = git.get("github_token", self._github_token)
            if not os.getenv("GITHUB_API_URL"):
                self._github_api_url = git.get("github_api_url", self._github_api_url)
        
        # Test Runner
        if "test_runner" in config_data:
            test_runner = config_data["test_runner"]
            if not os.getenv("TEST_RUNNER_TIMEOUT"):
                self._test_runner_timeout = test_runner.get("timeout", self._test_runner_timeout)
            if not os.getenv("USE_DOCKER_FOR_TESTS"):
                self._use_docker_for_tests = test_runner.get("use_docker", self._use_docker_for_tests)
            if not os.getenv("DOCKER_IMAGE_PREFIX"):
                self._docker_image_prefix = test_runner.get("docker_image_prefix", self._docker_image_prefix)
        
        # Security
        if "security" in config_data:
            security = config_data["security"]
            if not os.getenv("MAX_IMPACTED_FILES_FOR_AUTO_APPROVAL"):
                self._max_impacted_files_auto_approval = security.get("max_impacted_files", self._max_impacted_files_auto_approval)
            if not os.getenv("REQUIRE_HUMAN_APPROVAL_FOR_MIGRATIONS"):
                self._require_migration_approval = security.get("require_migration_approval", self._require_migration_approval)
        
        # Iterative Fix
        if "iterative_fix" in config_data:
            iterative_fix = config_data["iterative_fix"]
            if not os.getenv("MAX_FIX_RETRIES"):
                self._max_fix_retries = iterative_fix.get("max_retries", self._max_fix_retries)
            if not os.getenv("AUTO_FIX_LINT"):
                self._auto_fix_lint = iterative_fix.get("auto_fix_lint", self._auto_fix_lint)
            if not os.getenv("INCLUDE_CODE_EXAMPLES"):
                self._include_code_examples = iterative_fix.get("include_code_examples", self._include_code_examples)
            if not os.getenv("FIX_ON_TEST_FAILURE"):
                self._fix_on_test_failure = iterative_fix.get("fix_on_test_failure", self._fix_on_test_failure)
    
    def _validate(self) -> None:
        """Validate configuration values."""
        errors: List[str] = []
        
        # Validate Neo4j configuration
        if not self._neo4j_uri:
            errors.append("NEO4J_URI is required")
        if not self._neo4j_user:
            errors.append("NEO4J_USER is required")
        # Note: password can be empty for some setups
        
        # Validate numeric values
        if self._neo4j_batch_size <= 0:
            errors.append("NEO4J_BATCH_SIZE must be positive")
        if self._neo4j_max_retries < 0:
            errors.append("NEO4J_MAX_RETRIES must be non-negative")
        if self._neo4j_retry_delay < 0:
            errors.append("NEO4J_RETRY_DELAY must be non-negative")
        
        if self._fan_threshold < 0:
            errors.append("PKG_FAN_THRESHOLD must be non-negative")
        
        if self._max_file_size <= 0:
            errors.append("MAX_FILE_SIZE must be positive")
        
        if self._port <= 0 or self._port > 65535:
            errors.append("PORT must be between 1 and 65535")
        
        if self._max_fix_retries < 0:
            errors.append("MAX_FIX_RETRIES must be non-negative")
        
        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self._log_level not in valid_log_levels:
            errors.append(f"LOG_LEVEL must be one of {valid_log_levels}")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
    
    # Neo4j Properties
    @property
    def neo4j_uri(self) -> str:
        """Neo4j connection URI."""
        return self._neo4j_uri
    
    @property
    def neo4j_user(self) -> str:
        """Neo4j username."""
        return self._neo4j_user
    
    @property
    def neo4j_password(self) -> str:
        """Neo4j password."""
        return self._neo4j_password
    
    @property
    def neo4j_database(self) -> str:
        """Neo4j database name."""
        return self._neo4j_database
    
    @property
    def neo4j_batch_size(self) -> int:
        """Neo4j batch size for operations."""
        return self._neo4j_batch_size
    
    @property
    def neo4j_max_retries(self) -> int:
        """Maximum retries for Neo4j operations."""
        return self._neo4j_max_retries
    
    @property
    def neo4j_retry_delay(self) -> float:
        """Delay between Neo4j retries in seconds."""
        return self._neo4j_retry_delay
    
    # PKG Generation Properties
    @property
    def fan_threshold(self) -> int:
        """Fan-in threshold for filtering detailed symbol info."""
        return self._fan_threshold
    
    @property
    def include_features(self) -> bool:
        """Whether to include feature groupings in PKG."""
        return self._include_features
    
    @property
    def cache_enabled(self) -> bool:
        """Whether PKG caching is enabled."""
        return self._cache_enabled
    
    # Logging Properties
    @property
    def log_level(self) -> str:
        """Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)."""
        return self._log_level
    
    @property
    def log_format(self) -> str:
        """Logging format (standard or json)."""
        return self._log_format
    
    @property
    def log_structured(self) -> bool:
        """Whether to use structured JSON logging."""
        return self._log_structured
    
    # File Processing Properties
    @property
    def max_file_size(self) -> int:
        """Maximum file size in bytes."""
        return self._max_file_size
    
    @property
    def supported_languages(self) -> List[str]:
        """List of supported programming languages."""
        return self._supported_languages.copy()
    
    # Agent Properties
    @property
    def approval_required(self) -> bool:
        """Whether agent requires approval before applying changes."""
        return self._approval_required
    
    @property
    def auto_apply_low_risk(self) -> bool:
        """Whether to auto-apply low-risk changes."""
        return self._auto_apply_low_risk
    
    @property
    def agent_max_retries(self) -> int:
        """Maximum retries for agent operations."""
        return self._agent_max_retries
    
    @property
    def agent_timeout(self) -> int:
        """Timeout for agent operations in seconds."""
        return self._agent_timeout
    
    # Flask Properties
    @property
    def host(self) -> str:
        """Flask host address."""
        return self._host
    
    @property
    def port(self) -> int:
        """Flask port number."""
        return self._port
    
    @property
    def debug(self) -> bool:
        """Flask debug mode."""
        return self._debug
    
    @property
    def upload_folder(self) -> str:
        """Upload folder path."""
        return self._upload_folder
    
    # WebSocket Properties
    @property
    def websocket_cors_origins(self) -> str:
        """WebSocket CORS origins."""
        return self._websocket_cors_origins
    
    @property
    def websocket_async_mode(self) -> str:
        """WebSocket async mode."""
        return self._websocket_async_mode
    
    @property
    def websocket_ping_timeout(self) -> int:
        """WebSocket ping timeout in seconds."""
        return self._websocket_ping_timeout
    
    @property
    def websocket_ping_interval(self) -> int:
        """WebSocket ping interval in seconds."""
        return self._websocket_ping_interval
    
    # Embedding Properties
    @property
    def embedding_dimension(self) -> int:
        """Embedding dimension for vector indexes."""
        return self._embedding_dimension
    
    # LLM Properties
    @property
    def openai_api_key(self) -> str:
        """OpenAI API key for LLM operations."""
        return self._openai_api_key
    
    @property
    def llm_model(self) -> str:
        """LLM model name (default: gpt-4)."""
        return self._llm_model
    
    @property
    def llm_temperature(self) -> float:
        """LLM temperature (default: 0.7)."""
        return self._llm_temperature
    
    @property
    def llm_max_tokens(self) -> int:
        """Maximum tokens for LLM responses (default: 2000)."""
        return self._llm_max_tokens
    
    # Git/GitHub Properties
    @property
    def git_user_name(self) -> str:
        """Git user name for commits."""
        return self._git_user_name
    
    @property
    def git_user_email(self) -> str:
        """Git user email for commits."""
        return self._git_user_email
    
    @property
    def github_token(self) -> str:
        """GitHub API token for PR creation."""
        return self._github_token
    
    @property
    def github_api_url(self) -> str:
        """GitHub API base URL."""
        return self._github_api_url
    
    # Test Runner Properties
    @property
    def test_runner_timeout(self) -> int:
        """Test runner timeout in seconds."""
        return self._test_runner_timeout
    
    @property
    def use_docker_for_tests(self) -> bool:
        """Whether to use Docker for test execution."""
        return self._use_docker_for_tests
    
    @property
    def docker_image_prefix(self) -> str:
        """Docker image prefix for test runners."""
        return self._docker_image_prefix
    
    # Security Properties
    @property
    def max_impacted_files_auto_approval(self) -> int:
        """Maximum impacted files for auto-approval."""
        return self._max_impacted_files_auto_approval
    
    @property
    def require_migration_approval(self) -> bool:
        """Whether to require approval for migrations."""
        return self._require_migration_approval
    
    # File Matching Properties
    @property
    def fuzzy_file_matching_enabled(self) -> bool:
        """Whether fuzzy file matching is enabled."""
        return self._fuzzy_file_matching_enabled
    
    @property
    def fuzzy_match_confidence_threshold(self) -> float:
        """Confidence threshold for fuzzy file matching (0.0-1.0)."""
        return self._fuzzy_match_confidence_threshold
    
    @property
    def enable_file_validation(self) -> bool:
        """Whether file validation is enabled."""
        return self._enable_file_validation
    
    @property
    def log_llm_prompts(self) -> bool:
        """Whether to log LLM prompts (for debugging)."""
        return self._log_llm_prompts
    
    @property
    def use_ast_editing(self) -> bool:
        """Whether AST-aware editing is enabled (default: True)."""
        return self._use_ast_editing
    
    # Iterative Fix Properties
    @property
    def max_fix_retries(self) -> int:
        """Maximum retries for iterative code fixing (default: 3)."""
        return self._max_fix_retries
    
    @property
    def auto_fix_lint(self) -> bool:
        """Whether to use auto-fix tools (eslint --fix, prettier) when available (default: True)."""
        return self._auto_fix_lint
    
    @property
    def include_code_examples(self) -> bool:
        """Whether to include actual code examples from PKG in LLM prompts (default: True)."""
        return self._include_code_examples
    
    @property
    def fix_on_test_failure(self) -> bool:
        """Whether to automatically fix code when tests fail (default: True)."""
        return self._fix_on_test_failure
    
    @property
    def code_edits_enabled(self) -> bool:
        """Whether code edits are enabled (default: False). When False, generates spec files instead."""
        return self._code_edits_enabled


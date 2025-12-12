"""Standardized logging configuration with context support."""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional


class StandardFormatter(logging.Formatter):
    """Standard formatter with context support."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with context."""
        # Base format: TIMESTAMP | LEVEL | MODULE_NAME | MESSAGE
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        level = record.levelname.ljust(8)
        module = record.name.ljust(30)
        message = record.getMessage()
        
        # Add context if available
        context_parts = []
        if hasattr(record, 'repo_path'):
            context_parts.append(f"repo_path={record.repo_path}")
        if hasattr(record, 'file_path'):
            context_parts.append(f"file_path={record.file_path}")
        if hasattr(record, 'module_id'):
            context_parts.append(f"module_id={record.module_id}")
        if hasattr(record, 'count'):
            context_parts.append(f"count={record.count}")
        if hasattr(record, 'error_type'):
            context_parts.append(f"error_type={record.error_type}")
        
        if context_parts:
            context_str = " [" + ", ".join(context_parts) + "]"
        else:
            context_str = ""
        
        formatted = f"{timestamp} | {level} | {module} | {message}{context_str}"
        
        # Add exception info if present
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        
        return formatted


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        
        # Add context fields
        if hasattr(record, 'repo_path'):
            log_data["repo_path"] = record.repo_path
        if hasattr(record, 'file_path'):
            log_data["file_path"] = record.file_path
        if hasattr(record, 'module_id'):
            log_data["module_id"] = record.module_id
        if hasattr(record, 'count'):
            log_data["count"] = record.count
        if hasattr(record, 'error_type'):
            log_data["error_type"] = record.error_type
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add function name and line number
        log_data["function"] = record.funcName
        log_data["line"] = record.lineno
        
        return json.dumps(log_data)


def setup_logging(level: str = "INFO", structured: bool = False) -> None:
    """
    Setup standardized logging format.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        structured: Whether to use JSON structured logging
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Set formatter
    if structured:
        formatter = JSONFormatter()
    else:
        formatter = StandardFormatter()
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get logger with standardized configuration.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    repo_path: Optional[str] = None,
    file_path: Optional[str] = None,
    module_id: Optional[str] = None,
    count: Optional[int] = None,
    error_type: Optional[str] = None,
    exc_info: Optional[Exception] = None
) -> None:
    """
    Log message with context fields.
    
    Args:
        logger: Logger instance
        level: Log level (logging.DEBUG, logging.INFO, etc.)
        message: Log message
        repo_path: Repository path (optional)
        file_path: File path (optional)
        module_id: Module ID (optional)
        count: Count value (optional)
        error_type: Error type (optional)
        exc_info: Exception info (optional)
    """
    extra = {}
    if repo_path:
        extra['repo_path'] = repo_path
    if file_path:
        extra['file_path'] = file_path
    if module_id:
        extra['module_id'] = module_id
    if count is not None:
        extra['count'] = count
    if error_type:
        extra['error_type'] = error_type
    
    logger.log(level, message, extra=extra, exc_info=exc_info)


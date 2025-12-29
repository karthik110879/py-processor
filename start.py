"""Eventlet WSGI server entry point for Railway deployment."""

import os
import eventlet
from app import create_app
from utils.logging_config import setup_logging, get_logger
from utils.config import Config

# Get configuration
config = Config()

# Setup standardized logging
setup_logging(level=config.log_level, structured=config.log_structured)

logger = get_logger(__name__)

# Initialize eventlet (monkey patches standard library for async support)
eventlet.monkey_patch()

# Read PORT from environment (default to 5001)
port = int(os.getenv("PORT", "5001"))

# Create Flask app
logger.info(f"Creating Flask application...")
app = create_app()

# Start eventlet WSGI server
if __name__ == '__main__':
    logger.info(f"Starting eventlet WSGI server on 0.0.0.0:{port}")
    try:
        eventlet.wsgi.server(eventlet.listen(('0.0.0.0', port)), app)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


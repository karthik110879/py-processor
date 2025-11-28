"""Agent modules for document processing."""

try:
    from . import storing_agent
except ImportError:
    storing_agent = None

try:
    from . import chunking_agent
except ImportError:
    chunking_agent = None

try:
    from . import extraction_agent
except ImportError:
    extraction_agent = None

__all__ = ['storing_agent', 'chunking_agent', 'extraction_agent']

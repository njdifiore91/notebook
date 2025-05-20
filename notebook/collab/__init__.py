"""Real-time collaborative editing functionality for Jupyter Notebook.

This package provides the server-side components for enabling real-time
collaborative editing in Jupyter Notebook using the Yjs CRDT framework.
It includes WebSocket handlers for document synchronization, user presence
awareness, cell locking, and comment system.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

# Set up logging
logger = logging.getLogger('notebook.collab')

# Version info
__version__ = '0.1.0'  # Initial version of the collaboration extension

# Import and re-export key classes and functions
from .handlers import CollaborationWebSocketHandler, setup_handlers
from .store import CollaborationStore, MemoryCollaborationStore
from .auth import CollaborationAuthorizer

# Check for required dependencies
try:
    import pycrdt
    import pycrdt_websocket
    HAS_COLLABORATION_DEPS = True
except ImportError:
    HAS_COLLABORATION_DEPS = False
    logger.warning(
        "Collaboration features require pycrdt and pycrdt-websocket. "
        "Please install with: pip install pycrdt pycrdt-websocket"
    )


def _jupyter_server_extension_paths() -> List[Dict[str, str]]:
    """Return a list of dictionaries with metadata about the server extension.
    
    This function is called by Jupyter Server to discover server extensions.
    
    Returns:
        List[Dict[str, str]]: A list of dictionaries with extension metadata
    """
    return [{
        "module": "notebook.collab",
        "description": "Real-time collaborative editing for Jupyter Notebook"
    }]


def _load_jupyter_server_extension(server_app: Any) -> None:
    """Load the server extension.
    
    This function is called by Jupyter Server when the extension is loaded.
    It sets up the WebSocket handlers for collaboration.
    
    Args:
        server_app: The Jupyter server application instance
    """
    if not HAS_COLLABORATION_DEPS:
        logger.warning(
            "Collaboration extension is disabled because required dependencies "
            "are not available. Please install pycrdt and pycrdt-websocket."
        )
        return
    
    # Initialize the collaboration store if not already present
    if 'collaboration_store' not in server_app.web_app.settings:
        server_app.web_app.settings['collaboration_store'] = MemoryCollaborationStore()
    
    # Initialize the collaboration authorizer if not already present
    if 'collaboration_authorizer' not in server_app.web_app.settings:
        server_app.web_app.settings['collaboration_authorizer'] = CollaborationAuthorizer()
    
    # Set up the WebSocket handlers
    setup_handlers(server_app.web_app, server_app.web_app.settings['base_url'])
    
    logger.info("Jupyter Notebook collaboration extension loaded")


# For backwards compatibility with notebook server
load_jupyter_server_extension = _load_jupyter_server_extension
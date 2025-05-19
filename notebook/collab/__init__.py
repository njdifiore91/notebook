"""Real-time collaborative editing functionality for Jupyter Notebook.

This package provides real-time collaborative editing capabilities for Jupyter Notebook v7,
enabling multiple users to simultaneously edit the same notebook with live updates,
presence awareness, and conflict resolution.

The implementation leverages the Yjs Conflict-free Replicated Data Type (CRDT) framework
for real-time synchronization of notebook content, and includes features such as:

- Real-time synchronization for notebook content (code cells, markdown cells, outputs)
- User presence awareness showing which users are currently viewing/editing the notebook
- Cursor/selection synchronization to display other users' active locations
- Cell-level locking mechanism to prevent simultaneous editing conflicts
- Change history and versioning system for tracking individual contributions
- Permissions system with fine-grained access control (view-only, edit, admin)
- Comment and review system for discussing specific cells
- Integration with JupyterHub for user authentication in collaborative sessions

This module serves as the entry point for the collaboration functionality, registering
the collaboration extension with Jupyter Server and exposing the necessary classes and
functions for WebSocket handlers, document synchronization, user presence awareness,
and other collaborative features.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

# Import version information
from notebook._version import __version__, version_info

# Import and re-export key classes from handlers, store, and auth modules
from .handlers import (
    CollaborationWebSocketHandler,
    setup_handlers,
)
from .store import (
    CollaborationStore,
    MemoryCollaborationStore,
    FileCollaborationStore,
    CollaborationStoreFactory,
    CollaborationContentManager,
    StorageBackend,
)
from .auth import (
    CollaborationAuthorizer,
    CollaborationRole,
    CollaborationAction,
    CollaborationPermission,
    authorized_for_collaboration,
    CollaborationAuthConfig,
)

# Configure logger
logger = logging.getLogger(__name__)

# Define metadata for the collaboration extension
__collab_version__ = '0.1.0'  # Initial version of the collaboration extension

# Export key components
__all__ = [
    'CollaborationWebSocketHandler',
    'setup_handlers',
    'CollaborationStore',
    'MemoryCollaborationStore',
    'FileCollaborationStore',
    'CollaborationStoreFactory',
    'CollaborationContentManager',
    'StorageBackend',
    'CollaborationAuthorizer',
    'CollaborationRole',
    'CollaborationAction',
    'CollaborationPermission',
    'authorized_for_collaboration',
    'CollaborationAuthConfig',
]


def _jupyter_server_extension_points() -> List[Dict[str, Any]]:
    """Return a list of dictionaries with metadata about the extension."""
    return [{
        "module": "notebook.collab",
        "app": None,  # No custom app class
    }]


def _jupyter_server_extension_paths() -> List[Dict[str, str]]:
    """Return a list of dictionaries with metadata about the extension."""
    return [{
        "module": "notebook.collab",
    }]


def _load_jupyter_server_extension(server_app):
    """Load the collaboration extension for Jupyter Server.
    
    Args:
        server_app: Jupyter server application instance
    """
    # Import here to avoid circular imports
    from notebook.collab.handlers import setup_handlers
    
    # Set up WebSocket handlers for collaboration
    setup_handlers(server_app.web_app, server_app.base_url)
    
    # Initialize collaboration store if needed
    if not hasattr(server_app, 'collaboration_store'):
        from notebook.collab.store import CollaborationStoreFactory, StorageBackend
        
        # Get configuration
        config = server_app.config.get('CollaborationStore', {})
        backend_name = config.get('backend', 'file')
        backend = StorageBackend(backend_name)
        
        # Create store asynchronously
        import asyncio
        store_future = asyncio.ensure_future(
            CollaborationStoreFactory.create_store(backend, config)
        )
        
        # Store the future for later access
        server_app.collaboration_store_future = store_future
    
    # Initialize collaboration authorizer if needed
    if not hasattr(server_app, 'collaboration_authorizer'):
        from notebook.collab.auth import CollaborationAuthorizer
        
        # Get configuration
        config = server_app.config.get('CollaborationAuth', {})
        
        # Create authorizer
        authorizer = CollaborationAuthorizer(config=config)
        server_app.collaboration_authorizer = authorizer
    
    logger.info("Jupyter Notebook Collaboration extension loaded")


# For backward compatibility with notebook server
load_jupyter_server_extension = _load_jupyter_server_extension
"
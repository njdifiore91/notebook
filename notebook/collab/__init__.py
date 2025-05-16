"""Jupyter Notebook Collaboration Extension.

This module provides real-time collaborative editing capabilities for Jupyter Notebook v7
using the Yjs CRDT (Conflict-free Replicated Data Type) framework.

The collaboration extension enables:
- Real-time synchronization of notebook content (code cells, markdown cells, outputs)
- User presence awareness showing who is viewing/editing the notebook
- Cursor/selection synchronization to visualize other users' work areas
- Cell-level locking mechanism to prevent editing conflicts
- Change history and versioning system for tracking individual contributions
- Permissions system with fine-grained access control
- Comment and review system for discussing specific cells

This package initializer registers the collaboration server extension with Jupyter Server
and exports the necessary entry points for the collaboration extension.
"""

from __future__ import annotations

from typing import Any, Dict, List
import os
import json
from pathlib import Path

from traitlets import Bool, Dict as DictTrait, Integer, Unicode, default
from traitlets.config import Configurable

# Version information
__version__ = "0.1.0"  # Initial version of the collaboration module
version_info = (0, 1, 0)

# Default configuration
DEFAULT_CONFIG = {
    "enabled": True,
    "websocket_path": "/collaboration",
    "awareness_path": "/awareness",
    "persistence": {
        "enabled": True,
        "backend": "sqlite",
        "path": "",  # Empty string means use default location
    },
    "user_presence": {
        "enabled": True,
        "timeout": 30,  # Seconds of inactivity before user is considered idle
        "cleanup": 300,  # Seconds before removing disconnected users
    },
    "cell_locking": {
        "enabled": True,
        "timeout": 120,  # Seconds before automatically releasing a lock
    },
    "permissions": {
        "enabled": True,
        "default_role": "viewer",  # Default role for users without explicit permissions
    },
    "comments": {
        "enabled": True,
        "notifications": True,
    },
    "history": {
        "enabled": True,
        "max_snapshots": 100,  # Maximum number of version snapshots to keep
        "snapshot_interval": 300,  # Seconds between automatic snapshots
    },
}


def _jupyter_server_extension_paths() -> List[Dict[str, str]]:
    """Return a list of dictionaries with metadata about the server extension.
    
    This function is called by Jupyter Server to discover server extensions.
    
    Returns:
        List of dictionaries with module paths for server extensions.
    """
    return [{"module": "notebook.collab"}]


def _jupyter_server_extension_points() -> List[Dict[str, Any]]:
    """Return a list of dictionaries with metadata about server extensions.
    
    This function is called by Jupyter Server to discover extension applications.
    
    Returns:
        List of dictionaries with module and application class information.
    """

    return [{"module": "notebook.collab", "app": CollaborationExtensionApp}]


def _load_jupyter_server_extension(server_app):
    """Load the collaboration extension.
    
    This function is called by Jupyter Server when the extension is loaded.
    It sets up the WebSocket handlers and initializes the collaboration components.
    
    Args:
        server_app: The Jupyter Server application instance.
    """
    from .handlers import setup_handlers
    from .persistence import setup_persistence
    from .awareness import setup_awareness
    from .permissions import setup_permissions
    from .comments import setup_comments
    from .history import setup_history
    from .locks import setup_locks
    
    # Load configuration
    config = _load_config(server_app)
    
    # Skip setup if collaboration is disabled
    if not config.get("enabled", True):
        server_app.log.info("Jupyter Notebook collaboration extension is disabled")
        return
    
    # Initialize collaboration components
    persistence_manager = setup_persistence(server_app, config)
    awareness_manager = setup_awareness(server_app, config)
    permissions_manager = setup_permissions(server_app, config)
    comments_manager = setup_comments(server_app, config)
    history_manager = setup_history(server_app, config)
    locks_manager = setup_locks(server_app, config)
    
    # Setup WebSocket handlers
    setup_handlers(
        server_app,
        config,
        persistence_manager=persistence_manager,
        awareness_manager=awareness_manager,
        permissions_manager=permissions_manager,
        comments_manager=comments_manager,
        history_manager=history_manager,
        locks_manager=locks_manager,
    )
    
    server_app.log.info(f"Loaded Jupyter Notebook collaboration extension v{__version__}")


def _load_config(server_app) -> Dict[str, Any]:
    """Load and merge configuration for the collaboration extension.
    
    This function loads configuration from the server app's config object
    and converts it to the dictionary format expected by the collaboration components.
    
    Args:
        server_app: The Jupyter Server application instance.
        
    Returns:
        Dictionary containing the configuration.
    """
    # Create a NotebookCollabConfig instance with server app's config
    collab_config = NotebookCollabConfig(config=server_app.config)
    
    # Convert the traitlets config to a dictionary format for the components
    config = {
        "enabled": collab_config.enabled,
        "websocket_path": collab_config.websocket_path,
        "awareness_path": collab_config.awareness_path,
        "persistence": {
            "enabled": collab_config.persistence_enabled,
            "backend": collab_config.persistence_backend,
            "path": collab_config.persistence_path,
        },
        "user_presence": {
            "enabled": collab_config.user_presence_enabled,
            "timeout": collab_config.user_presence_timeout,
            "cleanup": collab_config.user_presence_cleanup,
        },
        "cell_locking": {
            "enabled": collab_config.cell_locking_enabled,
            "timeout": collab_config.cell_locking_timeout,
        },
        "permissions": {
            "enabled": collab_config.permissions_enabled,
            "default_role": collab_config.permissions_default_role,
        },
        "comments": {
            "enabled": collab_config.comments_enabled,
            "notifications": collab_config.comments_notifications,
        },
        "history": {
            "enabled": collab_config.history_enabled,
            "max_snapshots": collab_config.history_max_snapshots,
            "snapshot_interval": collab_config.history_snapshot_interval,
        },
    }
    
    return config


class NotebookCollabConfig(Configurable):
    """Configuration options for Jupyter Notebook collaboration extension."""
    
    enabled = Bool(True, help="Enable or disable the collaboration extension").tag(config=True)
    
    websocket_path = Unicode(
        "/collaboration", help="WebSocket endpoint path for Yjs CRDT synchronization"
    ).tag(config=True)
    
    awareness_path = Unicode(
        "/awareness", help="WebSocket endpoint path for user presence awareness"
    ).tag(config=True)
    
    persistence_enabled = Bool(
        True, help="Enable or disable persistence of collaboration data"
    ).tag(config=True)
    
    persistence_backend = Unicode(
        "sqlite", help="Backend storage type for collaboration data (sqlite, postgresql, etc.)"
    ).tag(config=True)
    
    persistence_path = Unicode(
        "", help="Path to the persistence database (empty for default location)"
    ).tag(config=True)
    
    user_presence_enabled = Bool(
        True, help="Enable or disable user presence awareness features"
    ).tag(config=True)
    
    user_presence_timeout = Integer(
        30, help="Seconds of inactivity before user is considered idle"
    ).tag(config=True)
    
    user_presence_cleanup = Integer(
        300, help="Seconds before removing disconnected users"
    ).tag(config=True)
    
    cell_locking_enabled = Bool(
        True, help="Enable or disable cell-level locking mechanism"
    ).tag(config=True)
    
    cell_locking_timeout = Integer(
        120, help="Seconds before automatically releasing a lock"
    ).tag(config=True)
    
    permissions_enabled = Bool(
        True, help="Enable or disable permission-based access control"
    ).tag(config=True)
    
    permissions_default_role = Unicode(
        "viewer", help="Default role for users without explicit permissions"
    ).tag(config=True)
    
    comments_enabled = Bool(
        True, help="Enable or disable comment and review system"
    ).tag(config=True)
    
    comments_notifications = Bool(
        True, help="Enable or disable notifications for new comments"
    ).tag(config=True)
    
    history_enabled = Bool(
        True, help="Enable or disable version history tracking"
    ).tag(config=True)
    
    history_max_snapshots = Integer(
        100, help="Maximum number of version snapshots to keep"
    ).tag(config=True)
    
    history_snapshot_interval = Integer(
        300, help="Seconds between automatic snapshots"
    ).tag(config=True)
    
    @default("persistence_path")
    def _default_persistence_path(self):
        """Default path for the persistence database."""
        from jupyter_core.paths import jupyter_data_dir
        return os.path.join(jupyter_data_dir(), "notebook_collaboration.db")


# Define the collaboration extension app class
class CollaborationExtensionApp:
    """Jupyter Server Extension Application for Collaboration.
    
    This class is used by Jupyter Server to initialize the collaboration extension.
    It provides a name and a load_jupyter_server_extension method that is called
    when the extension is loaded.
    """
    
    name = "notebook-collaboration"
    
    def load_jupyter_server_extension(self, server_app):
        """Load the collaboration extension.
        
        This method is called by Jupyter Server when the extension is loaded.
        It delegates to the _load_jupyter_server_extension function.
        
        Args:
            server_app: The Jupyter Server application instance.
        """
        _load_jupyter_server_extension(server_app)


# Import and initialize core collaboration components
from .handlers import CollaborationHandler, AwarenessHandler
from .persistence import CollaborationPersistenceManager
from .awareness import AwarenessManager
from .permissions import PermissionsManager
from .comments import CommentManager
from .history import HistoryManager
from .locks import LockManager

__all__ = [
    "__version__",
    "version_info",
    "NotebookCollabConfig",
    "CollaborationHandler",
    "AwarenessHandler",
    "CollaborationPersistenceManager",
    "AwarenessManager",
    "PermissionsManager",
    "CommentManager",
    "HistoryManager",
    "LockManager",
]
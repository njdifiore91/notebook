from __future__ import annotations

from typing import Any

from ._version import __version__, version_info  # noqa: F401

# Import and expose collaboration modules
from notebook.collab import (
    CollaborationWebSocketHandler,
    setup_handlers,
    CollaborationStore,
    MemoryCollaborationStore,
    FileCollaborationStore,
    CollaborationStoreFactory,
    CollaborationContentManager,
    StorageBackend,
    CollaborationAuthorizer,
    CollaborationRole,
    CollaborationAction,
    CollaborationPermission,
    authorized_for_collaboration,
    CollaborationAuthConfig,
)


def _jupyter_server_extension_paths() -> list[dict[str, str]]:
    return [
        {"module": "notebook"},
        {"module": "notebook.collab"}  # Register collaboration extension
    ]


def _jupyter_server_extension_points() -> list[dict[str, Any]]:
    from .app import JupyterNotebookApp

    return [
        {"module": "notebook", "app": JupyterNotebookApp},
        {"module": "notebook.collab", "app": None}  # Register collaboration extension
    ]


def _jupyter_labextension_paths() -> list[dict[str, str]]:
    return [{"src": "labextension", "dest": "@jupyter-notebook/lab-extension"}]
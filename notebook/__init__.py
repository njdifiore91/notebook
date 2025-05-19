from __future__ import annotations

from typing import Any, Dict, List

from ._version import __version__, version_info  # noqa: F401

# Import and expose collaboration modules
from .collab import auth, handlers, store  # noqa: F401


def _jupyter_server_extension_paths() -> list[dict[str, str]]:
    return [{"module": "notebook"}, {"module": "notebook.collab"}]


def _jupyter_server_extension_points() -> list[dict[str, Any]]:
    from .app import JupyterNotebookApp

    return [{"module": "notebook", "app": JupyterNotebookApp}]


def _jupyter_labextension_paths() -> list[dict[str, str]]:
    return [{"src": "labextension", "dest": "@jupyter-notebook/lab-extension"}]


# Add collaboration-specific entry points for discovery
def _jupyter_collaboration_extension_points() -> list[dict[str, Any]]:
    from .collab.handlers import CollaborationWebSocketHandler
    
    return [
        {
            "module": "notebook.collab",
            "handlers": [CollaborationWebSocketHandler],
            "auth_provider": "notebook.collab.auth",
            "store_provider": "notebook.collab.store"
        }
    ]
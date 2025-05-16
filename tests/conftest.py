import glob
import json
import os
import os.path as osp
import pathlib
import shutil
import sys
import asyncio
import uuid
from typing import Dict, List, Optional, Any, Callable, Awaitable

if sys.version_info < (3, 10):
    from importlib_resources import files
else:
    from importlib.resources import files

import pytest
import websockets

try:
    import y_py as Y
    from pycrdt import Doc as YDoc
    from pycrdt import Text as YText
    from pycrdt import Map as YMap
    from pycrdt import Array as YArray
    from pycrdt_websocket import WebsocketProvider
    HAS_COLLABORATION_DEPS = True
except ImportError:
    HAS_COLLABORATION_DEPS = False

from notebook.app import JupyterNotebookApp

pytest_plugins = ["jupyter_server.pytest_plugin"]


def mkdir(tmp_path, *parts):
    path = tmp_path.joinpath(*parts)
    if not path.exists():
        path.mkdir(parents=True)
    return path


app_settings_dir = pytest.fixture(lambda tmp_path: mkdir(tmp_path, "app_settings"))
user_settings_dir = pytest.fixture(lambda tmp_path: mkdir(tmp_path, "user_settings"))
schemas_dir = pytest.fixture(lambda tmp_path: mkdir(tmp_path, "schemas"))
workspaces_dir = pytest.fixture(lambda tmp_path: mkdir(tmp_path, "workspaces"))
labextensions_dir = pytest.fixture(lambda tmp_path: mkdir(tmp_path, "labextensions_dir"))


@pytest.fixture
def make_notebook_app(  # PLR0913
    jp_root_dir,
    jp_template_dir,
    app_settings_dir,
    user_settings_dir,
    schemas_dir,
    workspaces_dir,
    labextensions_dir,
):
    def _make_notebook_app(**kwargs):
        return JupyterNotebookApp(
            static_dir=str(jp_root_dir),
            templates_dir=str(jp_template_dir),
            app_url="/",
            app_settings_dir=str(app_settings_dir),
            user_settings_dir=str(user_settings_dir),
            schemas_dir=str(schemas_dir),
            workspaces_dir=str(workspaces_dir),
            extra_labextensions_path=[str(labextensions_dir)],
        )

    # Copy the template files.
    for html_path in glob.glob(str(files("notebook.templates").joinpath("*.html"))):
        shutil.copy(html_path, jp_template_dir)

    # Create the index file.
    index = jp_template_dir.joinpath("index.html")
    index.write_text(
        """
<!DOCTYPE html>
<html>
<head>
  <title>{{page_config['appName'] | e}}</title>
</head>
<body>
    {# Copy so we do not modify the page_config with updates. #}
    {% set page_config_full = page_config.copy() %}
    {# Set a dummy variable - we just want the side effect of the update. #}
    {% set _ = page_config_full.update(baseUrl=base_url, wsUrl=ws_url) %}
      <script id="jupyter-config-data" type="application/json">
        {{ page_config_full | tojson }}
      </script>
  <script src="{{page_config['fullStaticUrl'] | e}}/bundle.js" main="index"></script>
  <script type="text/javascript">
    /* Remove token from URL. */
    (function () {
      var parsedUrl = new URL(window.location.href);
      if (parsedUrl.searchParams.get('token')) {
        parsedUrl.searchParams.delete('token');
        window.history.replaceState({ }, '', parsedUrl.href);
      }
    })();
  </script>
</body>
</html>
"""
    )

    # Copy the schema files.
    test_data = str(files("jupyterlab_server.test_data")._paths[0])
    src = pathlib.PurePath(test_data, "schemas", "@jupyterlab")
    dst = pathlib.PurePath(str(schemas_dir), "@jupyterlab")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    # Create the federated extensions
    for name in ["apputils-extension", "codemirror-extension"]:
        target_name = name + "-federated"
        target = pathlib.PurePath(str(labextensions_dir), "@jupyterlab", target_name)
        src = pathlib.PurePath(test_data, "schemas", "@jupyterlab", name)
        dst = target / "schemas" / "@jupyterlab" / target_name
        if osp.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        with open(target / "package.orig.json", "w") as fid:
            data = dict(name=target_name, jupyterlab=dict(extension=True))
            json.dump(data, fid)

    # Copy the overrides file.
    src = pathlib.PurePath(test_data, "app-settings", "overrides.json")
    dst = pathlib.PurePath(str(app_settings_dir), "overrides.json")
    if os.path.exists(dst):
        os.remove(dst)
    shutil.copyfile(src, dst)

    # Copy workspaces.
    ws_path = pathlib.PurePath(test_data, "workspaces")
    for item in os.listdir(ws_path):
        src = ws_path / item
        dst = pathlib.PurePath(str(workspaces_dir), item)
        if os.path.exists(dst):
            os.remove(dst)
        shutil.copy(src, str(workspaces_dir))

    return _make_notebook_app


@pytest.fixture
def notebookapp(jp_serverapp, make_notebook_app):
    app = make_notebook_app()
    app._link_jupyter_server_extension(jp_serverapp)
    app.initialize()
    return app


# Collaboration testing fixtures

@pytest.fixture
def yjs_doc_provider():
    """Fixture for creating and managing Yjs documents for collaboration testing.
    
    Returns a function that creates a new Yjs document with the given ID.
    """
    if not HAS_COLLABORATION_DEPS:
        pytest.skip("Collaboration dependencies not installed")
    
    docs = {}
    
    def create_doc(doc_id=None):
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        
        if doc_id not in docs:
            doc = YDoc()
            docs[doc_id] = doc
        
        return docs[doc_id]
    
    yield create_doc
    
    # Clean up documents
    docs.clear()


@pytest.fixture
def awareness_state():
    """Fixture for testing user presence functionality.
    
    Returns a dictionary to track user awareness states.
    """
    if not HAS_COLLABORATION_DEPS:
        pytest.skip("Collaboration dependencies not installed")
    
    awareness_states = {}
    
    def get_awareness(doc_id=None):
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        
        if doc_id not in awareness_states:
            awareness_states[doc_id] = {}
        
        return awareness_states[doc_id]
    
    yield get_awareness
    
    # Clean up awareness states
    awareness_states.clear()


class CollabWebSocketClient:
    """WebSocket client for testing collaboration functionality."""
    
    def __init__(self, server_app, user_id=None, roles=None):
        """Initialize a WebSocket client for collaboration testing.
        
        Args:
            server_app: The Jupyter server application
            user_id: Optional user ID for the client
            roles: Optional list of roles for the client
        """
        if not HAS_COLLABORATION_DEPS:
            pytest.skip("Collaboration dependencies not installed")
        
        self.server_app = server_app
        self.user_id = user_id or str(uuid.uuid4())
        self.roles = roles or ["user"]
        self.websocket = None
        self.doc = None
        self.provider = None
        self.connected = False
        self.messages = []
    
    async def connect(self, doc_id=None, endpoint="/api/collaboration/room"):
        """Connect to the collaboration WebSocket endpoint.
        
        Args:
            doc_id: Optional document ID to connect to
            endpoint: The WebSocket endpoint to connect to
        """
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        
        self.doc_id = doc_id
        server_url = self.server_app.connection_url
        ws_url = f"ws://{server_url.host}:{server_url.port}{endpoint}/{doc_id}"
        
        # Create a new Yjs document
        self.doc = YDoc()
        
        # Connect to the WebSocket server
        self.websocket = await websockets.connect(ws_url)
        
        # Create a WebSocket provider for the document
        self.provider = WebsocketProvider(self.doc, self.websocket)
        
        # Set up awareness state
        self.provider.awareness.set_local_state({
            "user": {
                "id": self.user_id,
                "name": f"User {self.user_id}",
                "roles": self.roles
            }
        })
        
        self.connected = True
        return self
    
    async def disconnect(self):
        """Disconnect from the WebSocket server."""
        if self.provider:
            await self.provider.disconnect()
            self.provider = None
        
        if self.websocket and self.websocket.open:
            await self.websocket.close()
            self.websocket = None
        
        self.connected = False
    
    async def update_document(self, updates):
        """Apply updates to the Yjs document.
        
        Args:
            updates: Dictionary of updates to apply to the document
        """
        if not self.connected or not self.doc:
            raise RuntimeError("Client not connected")
        
        # Apply updates to the document
        with self.doc.begin_transaction() as txn:
            for key, value in updates.items():
                if isinstance(value, str):
                    # Create or update a text shared type
                    text = self.doc.get_text(key)
                    text.extend(txn, value)
                elif isinstance(value, dict):
                    # Create or update a map shared type
                    map_obj = self.doc.get_map(key)
                    for k, v in value.items():
                        map_obj.set(txn, k, v)
                elif isinstance(value, list):
                    # Create or update an array shared type
                    array = self.doc.get_array(key)
                    for item in value:
                        array.append(txn, item)
    
    async def get_document_state(self):
        """Get the current state of the Yjs document.
        
        Returns:
            Dictionary representing the document state
        """
        if not self.connected or not self.doc:
            raise RuntimeError("Client not connected")
        
        # Extract the document state
        state = {}
        for key in self.doc.share.keys():
            shared_type = self.doc.get(key)
            if isinstance(shared_type, YText):
                state[key] = str(shared_type)
            elif isinstance(shared_type, YMap):
                state[key] = {k: shared_type.get(k) for k in shared_type.keys()}
            elif isinstance(shared_type, YArray):
                state[key] = [shared_type.get(i) for i in range(len(shared_type))]
        
        return state
    
    async def update_awareness(self, state):
        """Update the client's awareness state.
        
        Args:
            state: Dictionary of awareness state to set
        """
        if not self.connected or not self.provider:
            raise RuntimeError("Client not connected")
        
        # Update the local awareness state
        current_state = self.provider.awareness.get_local_state() or {}
        current_state.update(state)
        self.provider.awareness.set_local_state(current_state)
    
    async def get_awareness_states(self):
        """Get the awareness states of all connected clients.
        
        Returns:
            Dictionary of client IDs to their awareness states
        """
        if not self.connected or not self.provider:
            raise RuntimeError("Client not connected")
        
        # Get all awareness states
        states = {}
        for client_id in self.provider.awareness.get_states().keys():
            states[client_id] = self.provider.awareness.get_state(client_id)
        
        return states


@pytest.fixture
async def multi_client_websocket_simulation(jp_serverapp):
    """Fixture for simulating multiple clients in collaboration tests.
    
    Returns a function that creates a new CollabWebSocketClient.
    """
    if not HAS_COLLABORATION_DEPS:
        pytest.skip("Collaboration dependencies not installed")
    
    clients = []
    
    async def create_client(user_id=None, roles=None):
        client = CollabWebSocketClient(jp_serverapp, user_id=user_id, roles=roles)
        clients.append(client)
        return client
    
    yield create_client
    
    # Clean up clients
    for client in clients:
        if client.connected:
            await client.disconnect()
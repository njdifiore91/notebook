import glob
import json
import os
import os.path as osp
import pathlib
import shutil
import sys
import asyncio
from typing import Dict, List, Optional, Any, Callable, Awaitable

if sys.version_info < (3, 10):
    from importlib_resources import files
else:
    from importlib.resources import files

import pytest
import y_py as ypy
from tornado.websocket import WebSocketClientConnection
from tornado.httpclient import AsyncHTTPClient

from notebook.app import JupyterNotebookApp
from notebook.collab.handlers import YjsDocumentProvider

pytest_plugins = ["jupyter_server.pytest_plugin", "pytest_asyncio"]


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


class CollabWebSocketClient:
    """A WebSocket client for testing collaboration features."""

    def __init__(self, serverapp, user_id="test-user", roles=None):
        """Initialize the WebSocket client.
        
        Parameters
        ----------
        serverapp : JupyterServerApp
            The Jupyter server application instance
        user_id : str, optional
            The user ID to use for this client, by default "test-user"
        roles : list, optional
            The roles to assign to this user, by default None
        """
        self.serverapp = serverapp
        self.user_id = user_id
        self.roles = roles or ["editor"]
        self.connection = None
        self.messages = []
        self.connected = False
        self.http_client = AsyncHTTPClient()
        self.base_url = self.serverapp.web_app.settings["base_url"]
        self.token = self.serverapp.web_app.settings["token"]

    async def connect(self, doc_id="test-doc"):
        """Connect to the WebSocket server.
        
        Parameters
        ----------
        doc_id : str, optional
            The document ID to connect to, by default "test-doc"
            
        Returns
        -------
        bool
            True if connection was successful, False otherwise
        """
        url = f"ws://localhost:{self.serverapp.port}{self.base_url}collab/api/yjs/{doc_id}?token={self.token}&user_id={self.user_id}"
        self.connection = await self.serverapp.http_server.websocket_connect(url)
        self.connected = True
        
        # Start message listener
        asyncio.create_task(self._listen_for_messages())
        return True

    async def disconnect(self):
        """Disconnect from the WebSocket server."""
        if self.connection:
            self.connection.close()
            self.connected = False
            self.connection = None

    async def send_message(self, message):
        """Send a message to the WebSocket server.
        
        Parameters
        ----------
        message : bytes or str
            The message to send
        """
        if not self.connected:
            raise RuntimeError("Not connected to WebSocket server")
        
        if isinstance(message, str):
            message = message.encode("utf-8")
            
        await self.connection.write_message(message, binary=True)

    async def _listen_for_messages(self):
        """Listen for messages from the WebSocket server."""
        while self.connected:
            try:
                msg = await self.connection.read_message()
                if msg is None:
                    # Connection closed
                    self.connected = False
                    break
                self.messages.append(msg)
            except Exception as e:
                print(f"Error reading message: {e}")
                self.connected = False
                break

    def get_messages(self):
        """Get all received messages.
        
        Returns
        -------
        list
            List of received messages
        """
        return self.messages

    def clear_messages(self):
        """Clear the message buffer."""
        self.messages = []


@pytest.fixture
async def yjs_doc_provider(jp_serverapp):
    """Create a Yjs document provider for testing.
    
    Returns
    -------
    YjsDocumentProvider
        A Yjs document provider instance
    """
    provider = YjsDocumentProvider(doc_id="test-doc")
    provider.initialize(jp_serverapp)
    try:
        yield provider
    finally:
        await provider.destroy()


@pytest.fixture
def awareness_state():
    """Create an awareness state for testing user presence functionality.
    
    Returns
    -------
    dict
        A dictionary representing the awareness state
    """
    # Create a Y.Doc to hold the awareness state
    ydoc = ypy.YDoc()
    
    # Create an awareness map
    awareness = {
        "clients": {},
        "user_ids": {}
    }
    
    # Add some test users
    awareness["clients"]["client1"] = {
        "user": {
            "id": "user1",
            "name": "Test User 1",
            "color": "#ff0000"
        },
        "cursor": {
            "cellId": "cell1",
            "position": 10
        },
        "selection": {
            "cellId": "cell1",
            "start": 5,
            "end": 15
        },
        "status": "active"
    }
    
    awareness["clients"]["client2"] = {
        "user": {
            "id": "user2",
            "name": "Test User 2",
            "color": "#00ff00"
        },
        "cursor": {
            "cellId": "cell2",
            "position": 5
        },
        "selection": None,
        "status": "idle"
    }
    
    awareness["user_ids"]["user1"] = "client1"
    awareness["user_ids"]["user2"] = "client2"
    
    return awareness


@pytest.fixture
async def multi_client_websocket_simulation(jp_serverapp):
    """Create a simulation of multiple clients for collaboration testing.
    
    Returns
    -------
    callable
        A function that creates a new client with the given user ID
    """
    clients = []
    
    async def create_client(user_id="test-user", roles=None):
        """Create a new client with the given user ID.
        
        Parameters
        ----------
        user_id : str, optional
            The user ID to use for this client, by default "test-user"
        roles : list, optional
            The roles to assign to this user, by default None
            
        Returns
        -------
        CollabWebSocketClient
            A WebSocket client instance
        """
        client = CollabWebSocketClient(jp_serverapp, user_id=user_id, roles=roles)
        await client.connect()
        clients.append(client)
        return client
    
    yield create_client
    
    # Clean up all clients after the test
    for client in clients:
        await client.disconnect()
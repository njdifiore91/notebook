import asyncio
import json
import os
import pathlib
import pytest
import uuid
from urllib.parse import urlparse, parse_qs

from tornado.httpclient import AsyncHTTPClient
from tornado.websocket import websocket_connect

from jupyter_server.serverapp import ServerApp
from jupyter_server.utils import url_path_join


class WebSocketTestClient:
    """A WebSocket client for testing collaborative features.
    
    This client simulates a user connecting to the Jupyter Server's WebSocket
    endpoints for real-time collaboration testing.
    """
    
    def __init__(self, serverapp, user_id=None, roles=None):
        """Initialize the WebSocket test client.
        
        Parameters
        ----------
        serverapp : ServerApp
            The Jupyter server application instance
        user_id : str, optional
            The user ID to use for this client, by default a random UUID
        roles : list, optional
            The roles to assign to this user, by default None
        """
        self.serverapp = serverapp
        self.user_id = user_id or f"test-user-{uuid.uuid4().hex[:8]}"
        self.roles = roles or ["editor"]
        self.base_url = self.serverapp.connection_url
        self.ws_url = self._get_ws_url()
        self.ws_connection = None
        self.received_messages = []
        self._message_future = None
    
    def _get_ws_url(self):
        """Convert the server's HTTP URL to a WebSocket URL."""
        parsed = urlparse(self.base_url)
        protocol = "ws" if parsed.scheme == "http" else "wss"
        return f"{protocol}://{parsed.netloc}"
    
    async def connect(self, path="/collaboration"):
        """Connect to the WebSocket server.
        
        Parameters
        ----------
        path : str, optional
            The WebSocket endpoint path, by default "/collaboration"
            
        Returns
        -------
        WebSocketClientConnection
            The WebSocket connection object
        """
        # Add authentication token if available
        token = getattr(self.serverapp, 'token', '')
        if token:
            path = f"{path}?token={token}"
            
        # Add user identity information
        headers = {
            "X-User-ID": self.user_id,
            "X-User-Roles": ",".join(self.roles)
        }
        
        # Connect to the WebSocket server
        url = url_path_join(self.ws_url, path)
        self.ws_connection = await websocket_connect(
            url, 
            headers=headers,
            on_message_callback=self._on_message
        )
        return self.ws_connection
    
    async def disconnect(self):
        """Disconnect from the WebSocket server."""
        if self.ws_connection:
            self.ws_connection.close()
            self.ws_connection = None
    
    def _on_message(self, message):
        """Handle incoming WebSocket messages.
        
        Parameters
        ----------
        message : str or None
            The message received from the WebSocket server, or None if the connection was closed
        """
        if message is None:
            # Connection closed
            return
            
        # Parse and store the message
        try:
            parsed_message = json.loads(message)
            self.received_messages.append(parsed_message)
            
            # If there's a waiting future, set its result
            if self._message_future and not self._message_future.done():
                self._message_future.set_result(parsed_message)
        except json.JSONDecodeError:
            # Handle binary messages (like Yjs updates)
            self.received_messages.append({"type": "binary", "data": message})
            
            # If there's a waiting future, set its result
            if self._message_future and not self._message_future.done():
                self._message_future.set_result({"type": "binary", "data": message})
    
    async def send_message(self, message):
        """Send a message to the WebSocket server.
        
        Parameters
        ----------
        message : dict or str
            The message to send. If a dict, it will be JSON-encoded.
        """
        if not self.ws_connection:
            raise RuntimeError("WebSocket connection not established")
            
        if isinstance(message, dict):
            message = json.dumps(message)
            
        await self.ws_connection.write_message(message)
    
    async def wait_for_message(self, timeout=5.0):
        """Wait for the next message from the WebSocket server.
        
        Parameters
        ----------
        timeout : float, optional
            The maximum time to wait in seconds, by default 5.0
            
        Returns
        -------
        dict
            The received message
            
        Raises
        ------
        asyncio.TimeoutError
            If no message is received within the timeout period
        """
        self._message_future = asyncio.Future()
        try:
            return await asyncio.wait_for(self._message_future, timeout)
        finally:
            self._message_future = None
    
    async def wait_for_message_type(self, message_type, timeout=5.0):
        """Wait for a message of a specific type.
        
        Parameters
        ----------
        message_type : str
            The type of message to wait for
        timeout : float, optional
            The maximum time to wait in seconds, by default 5.0
            
        Returns
        -------
        dict
            The received message
            
        Raises
        ------
        asyncio.TimeoutError
            If no matching message is received within the timeout period
        """
        start_time = asyncio.get_event_loop().time()
        while True:
            remaining_time = timeout - (asyncio.get_event_loop().time() - start_time)
            if remaining_time <= 0:
                raise asyncio.TimeoutError(f"Timeout waiting for message type: {message_type}")
                
            message = await self.wait_for_message(timeout=remaining_time)
            if message.get("type") == message_type:
                return message


@pytest.fixture
async def jp_ws_client(jp_serverapp):
    """Fixture to create WebSocket clients for testing collaborative features.
    
    This fixture provides a factory function that creates WebSocket clients
    connected to the test server. Each client simulates a different user for
    testing multi-user collaboration scenarios.
    
    Parameters
    ----------
    jp_serverapp : ServerApp
        The Jupyter server application fixture
        
    Returns
    -------
    callable
        A factory function that creates WebSocketTestClient instances
    """
    clients = []
    
    async def create_client(user_id=None, roles=None):
        """Create a WebSocket client connected to the test server.
        
        Parameters
        ----------
        user_id : str, optional
            The user ID to use for this client, by default a random UUID
        roles : list, optional
            The roles to assign to this user, by default ["editor"]
            
        Returns
        -------
        WebSocketTestClient
            A connected WebSocket client
        """
        client = WebSocketTestClient(jp_serverapp, user_id=user_id, roles=roles)
        await client.connect()
        clients.append(client)
        return client
    
    yield create_client
    
    # Disconnect all clients after the test
    for client in clients:
        await client.disconnect()


@pytest.fixture
def collab_db_path(tmp_path):
    """Fixture providing an isolated path for the collaboration database.
    
    This fixture creates a unique temporary path for each test to ensure
    that collaboration database state is isolated between tests.
    
    Parameters
    ----------
    tmp_path : pathlib.Path
        The pytest temporary directory fixture
        
    Returns
    -------
    str
        The path to use for the collaboration database
    """
    db_path = tmp_path.joinpath("collab.db")
    return str(db_path)


@pytest.fixture
def comments_db_path(tmp_path):
    """Fixture providing an isolated path for the comments database.
    
    This fixture creates a unique temporary path for each test to ensure
    that comments database state is isolated between tests.
    
    Parameters
    ----------
    tmp_path : pathlib.Path
        The pytest temporary directory fixture
        
    Returns
    -------
    str
        The path to use for the comments database
    """
    db_path = tmp_path.joinpath("comments.db")
    return str(db_path)


@pytest.fixture
def test_notebook_content():
    """Fixture providing a sample notebook content for testing.
    
    Returns
    -------
    dict
        A dictionary representing a simple notebook with code and markdown cells
    """
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Test Notebook for Collaboration\n", "This is a test notebook for collaboration features."]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["# This is a code cell\n", "print('Hello, world!')"]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["# Another code cell\n", "import numpy as np\n", "np.random.rand(10)"]
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "codemirror_mode": {
                    "name": "ipython",
                    "version": 3
                },
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.9.0"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }


@pytest.fixture
async def create_test_notebook(jp_root_dir, jp_fetch, test_notebook_content):
    """Fixture providing a function to create test notebooks.
    
    This fixture returns a function that creates a notebook file with the
    specified content in the server's root directory.
    
    Parameters
    ----------
    jp_root_dir : pathlib.Path
        The Jupyter server root directory fixture
    jp_fetch : callable
        The Jupyter server fetch fixture
    test_notebook_content : dict
        The default notebook content fixture
        
    Returns
    -------
    callable
        A function that creates test notebooks
    """
    async def _create_notebook(name="test_notebook.ipynb", content=None):
        """Create a test notebook file.
        
        Parameters
        ----------
        name : str, optional
            The name of the notebook file, by default "test_notebook.ipynb"
        content : dict, optional
            The notebook content, by default uses test_notebook_content
            
        Returns
        -------
        str
            The path to the created notebook file
        """
        if content is None:
            content = test_notebook_content
            
        # Create the notebook file
        notebook_path = jp_root_dir / name
        with open(notebook_path, 'w', encoding='utf-8') as f:
            json.dump(content, f)
            
        # Verify the file was created
        response = await jp_fetch("api", "contents", name)
        assert response.code == 200
        
        return str(notebook_path)
    
    return _create_notebook


@pytest.fixture
def configure_collaboration(monkeypatch, collab_db_path, comments_db_path):
    """Fixture to configure collaboration settings for testing.
    
    This fixture sets environment variables to configure the collaboration
    features for testing, using isolated database paths.
    
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture
    collab_db_path : str
        The collaboration database path fixture
    comments_db_path : str
        The comments database path fixture
        
    Returns
    -------
    dict
        A dictionary of the configured collaboration settings
    """
    # Configure collaboration settings via environment variables
    monkeypatch.setenv("JUPYTER_COLLABORATION_ENABLED", "true")
    monkeypatch.setenv("JUPYTER_COLLABORATION_DB_PATH", collab_db_path)
    monkeypatch.setenv("JUPYTER_COMMENTS_DB_PATH", comments_db_path)
    monkeypatch.setenv("JUPYTER_COLLABORATION_DOCUMENT_STORAGE_CLASS", "jupyter_ydoc.SQLiteYDocStorage")
    monkeypatch.setenv("JUPYTER_COLLABORATION_AWARENESS_STORAGE_CLASS", "jupyter_ydoc.InMemoryAwarenessStorage")
    monkeypatch.setenv("JUPYTER_COMMENTS_STORAGE_CLASS", "jupyter_comments.SQLiteCommentStorage")
    monkeypatch.setenv("JUPYTER_PERMISSIONS_STORAGE_CLASS", "jupyter_permissions.SQLitePermissionStorage")
    
    # Return the configuration for reference
    return {
        "enabled": True,
        "collab_db_path": collab_db_path,
        "comments_db_path": comments_db_path,
        "document_storage_class": "jupyter_ydoc.SQLiteYDocStorage",
        "awareness_storage_class": "jupyter_ydoc.InMemoryAwarenessStorage",
        "comments_storage_class": "jupyter_comments.SQLiteCommentStorage",
        "permissions_storage_class": "jupyter_permissions.SQLitePermissionStorage"
    }


@pytest.fixture
async def setup_collaboration_test(configure_collaboration, create_test_notebook, jp_ws_client):
    """Fixture to set up a complete collaboration test environment.
    
    This fixture combines multiple fixtures to create a fully configured
    collaboration test environment with a test notebook and connected clients.
    
    Parameters
    ----------
    configure_collaboration : dict
        The collaboration configuration fixture
    create_test_notebook : callable
        The notebook creation fixture
    jp_ws_client : callable
        The WebSocket client factory fixture
        
    Returns
    -------
    dict
        A dictionary containing the test environment setup
    """
    # Create a test notebook
    notebook_path = await create_test_notebook()
    notebook_name = os.path.basename(notebook_path)
    
    # Create two test clients
    client1 = await jp_ws_client(user_id="user1", roles=["editor"])
    client2 = await jp_ws_client(user_id="user2", roles=["editor"])
    
    # Subscribe both clients to the test document
    await client1.send_message({
        "type": "subscribe",
        "document_id": notebook_name
    })
    await client2.send_message({
        "type": "subscribe",
        "document_id": notebook_name
    })
    
    # Wait for subscription confirmations
    await client1.wait_for_message_type("subscribed")
    await client2.wait_for_message_type("subscribed")
    
    # Return the test environment
    return {
        "notebook_path": notebook_path,
        "notebook_name": notebook_name,
        "client1": client1,
        "client2": client2,
        "config": configure_collaboration
    }


@pytest.fixture
def mock_collaboration_provider():
    """Fixture providing a mock collaboration provider for unit testing.
    
    This fixture creates a mock implementation of the ICollaborationProvider
    interface for unit testing collaboration components without requiring
    a full server setup.
    
    Returns
    -------
    object
        A mock collaboration provider object
    """
    class MockCollaborationProvider:
        """Mock implementation of ICollaborationProvider for testing."""
        
        def __init__(self):
            self.documents = {}
            self.subscribers = {}
            self.awareness = {}
            self.connected = True
        
        async def connect_document(self, doc_id):
            """Mock connecting to a collaborative document."""
            if doc_id not in self.documents:
                self.documents[doc_id] = {"cells": [], "metadata": {}}
                self.subscribers[doc_id] = set()
            
            self.subscribers[doc_id].add("test-user")
            return self.documents[doc_id]
        
        async def disconnect_document(self, doc_id):
            """Mock disconnecting from a collaborative document."""
            if doc_id in self.subscribers:
                self.subscribers[doc_id].discard("test-user")
        
        def get_connected_users(self, doc_id):
            """Mock getting connected users for a document."""
            return ["test-user"] if doc_id in self.subscribers else []
        
        def update_awareness(self, doc_id, state):
            """Mock updating awareness state."""
            if doc_id not in self.awareness:
                self.awareness[doc_id] = {}
            
            self.awareness[doc_id]["test-user"] = state
        
        def get_awareness_states(self, doc_id):
            """Mock getting awareness states for a document."""
            return self.awareness.get(doc_id, {})
        
        def is_connected(self):
            """Mock checking if connected to collaboration server."""
            return self.connected
    
    return MockCollaborationProvider()
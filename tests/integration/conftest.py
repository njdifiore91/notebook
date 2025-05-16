import asyncio
import json
import os
import pathlib
import pytest
import uuid
from urllib.parse import urlparse
from tornado.httpclient import AsyncHTTPClient
from tornado.websocket import websocket_connect

# Import fixtures from the main conftest.py
from tests.conftest import (
    app_settings_dir,
    user_settings_dir,
    schemas_dir,
    workspaces_dir,
    labextensions_dir,
    make_notebook_app,
    notebookapp,
    mkdir,
)


class WebSocketTestClient:
    """A WebSocket client for testing collaborative editing features.
    
    This client simulates a user connecting to the Jupyter server's WebSocket
    endpoint for real-time collaboration. It handles authentication, message
    exchange, and maintains connection state.
    """
    
    def __init__(self, serverapp, user_id="test-user", roles=None):
        """Initialize a WebSocket test client.
        
        Parameters
        ----------
        serverapp : JupyterServerApp
            The server application instance to connect to
        user_id : str, optional
            The user identifier for this client, by default "test-user"
        roles : list, optional
            List of roles for this user, by default None
        """
        self.serverapp = serverapp
        self.user_id = user_id
        self.roles = roles or ["editor"]
        self.ws_connection = None
        self.messages = []
        self.connected = False
        self.auth_token = None
        self._message_callback = None
        
        # Parse the server URL to construct WebSocket URL
        server_url = self.serverapp.connection_url
        parsed = urlparse(server_url)
        protocol = "ws" if parsed.scheme == "http" else "wss"
        self.base_url = f"{protocol}://{parsed.netloc}"
    
    async def connect(self, path="/api/collaboration/ws"):
        """Connect to the WebSocket server.
        
        Parameters
        ----------
        path : str, optional
            The WebSocket endpoint path, by default "/api/collaboration/ws"
        
        Returns
        -------
        bool
            True if connection was successful, False otherwise
        """
        # First, get an authentication token
        await self._authenticate()
        
        # Construct the WebSocket URL with authentication token
        ws_url = f"{self.base_url}{path}?token={self.auth_token}"
        
        try:
            self.ws_connection = await websocket_connect(
                ws_url,
                on_message_callback=self._on_message
            )
            self.connected = True
            return True
        except Exception as e:
            print(f"WebSocket connection failed: {e}")
            self.connected = False
            return False
    
    async def _authenticate(self):
        """Authenticate with the server and get a token."""
        # In a test environment, we can use the server's token directly
        # In a real implementation, this would involve a proper authentication flow
        self.auth_token = self.serverapp.token
        
        # For testing purposes, we can also set user identity via HTTP headers
        # This simulates the authentication that would happen in a real deployment
        headers = {
            "X-Test-User-Id": self.user_id,
            "X-Test-User-Roles": ",".join(self.roles)
        }
        
        # Make a request to an endpoint that will recognize these test headers
        # This is a simplified approach for testing purposes
        http_client = AsyncHTTPClient()
        await http_client.fetch(
            f"{self.serverapp.connection_url}api/collaboration/auth/test",
            headers=headers,
            raise_error=False  # Don't raise on 404 if endpoint doesn't exist yet
        )
    
    async def disconnect(self):
        """Disconnect from the WebSocket server."""
        if self.ws_connection:
            self.ws_connection.close()
            self.ws_connection = None
            self.connected = False
    
    async def send_message(self, message):
        """Send a message to the WebSocket server.
        
        Parameters
        ----------
        message : dict or str
            The message to send. If a dict, it will be JSON-encoded.
        
        Returns
        -------
        bool
            True if the message was sent successfully, False otherwise
        """
        if not self.connected or not self.ws_connection:
            return False
        
        if isinstance(message, dict):
            message = json.dumps(message)
        
        await self.ws_connection.write_message(message)
        return True
    
    def _on_message(self, message):
        """Handle incoming WebSocket messages.
        
        Parameters
        ----------
        message : str
            The received message
        """
        if message is None:
            # Connection closed
            self.connected = False
            return
        
        # Store the message
        try:
            parsed_message = json.loads(message)
            self.messages.append(parsed_message)
        except json.JSONDecodeError:
            # Handle binary messages or non-JSON text
            self.messages.append(message)
        
        # Call the message callback if set
        if self._message_callback:
            asyncio.create_task(self._message_callback(message))
    
    def set_message_callback(self, callback):
        """Set a callback function for incoming messages.
        
        Parameters
        ----------
        callback : callable
            A function that takes a message as its argument
        """
        self._message_callback = callback
    
    def get_messages(self, clear=False):
        """Get all received messages.
        
        Parameters
        ----------
        clear : bool, optional
            Whether to clear the message queue after retrieval, by default False
        
        Returns
        -------
        list
            List of received messages
        """
        messages = list(self.messages)
        if clear:
            self.messages = []
        return messages
    
    async def wait_for_message(self, predicate, timeout=5.0):
        """Wait for a message that satisfies the given predicate.
        
        Parameters
        ----------
        predicate : callable
            A function that takes a message and returns True if it matches
        timeout : float, optional
            Maximum time to wait in seconds, by default 5.0
        
        Returns
        -------
        dict or None
            The matching message or None if timeout occurs
        """
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            for i, msg in enumerate(self.messages):
                if predicate(msg):
                    # Remove this message and all earlier ones
                    matching_msg = self.messages.pop(i)
                    self.messages = self.messages[i:]
                    return matching_msg
            await asyncio.sleep(0.1)
        return None


@pytest.fixture
def collab_db_path(tmp_path):
    """Creates an isolated database path for collaboration state.
    
    This fixture provides a unique path for each test to store collaboration
    data, ensuring test isolation.
    
    Parameters
    ----------
    tmp_path : pathlib.Path
        Pytest fixture providing a temporary directory
    
    Returns
    -------
    str
        Path to the collaboration database file
    """
    db_path = tmp_path.joinpath(f"collab_{uuid.uuid4().hex}.db")
    return str(db_path)


@pytest.fixture
def comments_db_path(tmp_path):
    """Creates an isolated database path for comments.
    
    This fixture provides a unique path for each test to store comment
    data, ensuring test isolation.
    
    Parameters
    ----------
    tmp_path : pathlib.Path
        Pytest fixture providing a temporary directory
    
    Returns
    -------
    str
        Path to the comments database file
    """
    db_path = tmp_path.joinpath(f"comments_{uuid.uuid4().hex}.db")
    return str(db_path)


@pytest.fixture
async def jp_ws_client(jp_serverapp):
    """Fixture to create WebSocket clients for testing collaboration.
    
    This fixture returns a factory function that creates WebSocket clients
    connected to the test server. Each client simulates a different user
    for testing multi-user collaboration scenarios.
    
    Parameters
    ----------
    jp_serverapp : JupyterServerApp
        The server application fixture from jupyter_server.pytest_plugin
    
    Returns
    -------
    callable
        A factory function that creates WebSocket clients
    """
    clients = []
    
    async def create_client(user_id="test-user", roles=None):
        """Create a WebSocket client with the specified user identity.
        
        Parameters
        ----------
        user_id : str, optional
            The user identifier, by default "test-user"
        roles : list, optional
            List of roles for this user, by default None
        
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
def network_condition_simulator():
    """Fixture to simulate various network conditions.
    
    This fixture provides functions to simulate network latency, packet loss,
    and other conditions that might affect collaboration performance.
    
    Returns
    -------
    dict
        Dictionary of network simulation functions
    """
    async def add_latency(delay_ms):
        """Simulate network latency by adding a delay.
        
        Parameters
        ----------
        delay_ms : int
            Delay in milliseconds
        """
        await asyncio.sleep(delay_ms / 1000.0)
    
    async def simulate_packet_loss(probability=0.1):
        """Simulate packet loss by randomly failing operations.
        
        Parameters
        ----------
        probability : float, optional
            Probability of packet loss (0.0 to 1.0), by default 0.1
        
        Returns
        -------
        bool
            True if the packet should be delivered, False if it should be dropped
        """
        import random
        return random.random() >= probability
    
    return {
        "add_latency": add_latency,
        "simulate_packet_loss": simulate_packet_loss
    }


@pytest.fixture
def collaborative_document_factory(jp_serverapp, collab_db_path):
    """Fixture to create test documents with predefined collaborative states.
    
    This fixture provides functions to create and manage test documents
    with specific collaborative editing scenarios.
    
    Parameters
    ----------
    jp_serverapp : JupyterServerApp
        The server application fixture
    collab_db_path : str
        Path to the collaboration database
    
    Returns
    -------
    dict
        Dictionary of document creation and management functions
    """
    async def create_document(doc_id=None, content=None, users=None):
        """Create a test document with the specified content and users.
        
        Parameters
        ----------
        doc_id : str, optional
            Document identifier, by default None (auto-generated)
        content : dict, optional
            Initial document content, by default None
        users : list, optional
            List of users with access to the document, by default None
        
        Returns
        -------
        str
            The document identifier
        """
        doc_id = doc_id or f"test-doc-{uuid.uuid4().hex}"
        content = content or {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": "# Test Document\n\nThis is a test document for collaboration.",
                    "metadata": {}
                },
                {
                    "cell_type": "code",
                    "source": "print('Hello, world!')",
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None
                }
            ],
            "metadata": {
                "kernelspec": {
                    "name": "python3",
                    "display_name": "Python 3"
                }
            },
            "nbformat": 4,
            "nbformat_minor": 5
        }
        
        # In a real implementation, this would create the document in the database
        # For testing purposes, we'll just return the document ID
        # The actual implementation would depend on the collaboration backend
        
        return doc_id
    
    async def get_document_state(doc_id):
        """Get the current state of a document.
        
        Parameters
        ----------
        doc_id : str
            Document identifier
        
        Returns
        -------
        dict
            The document state
        """
        # In a real implementation, this would retrieve the document from the database
        # For testing purposes, we'll return a placeholder
        return {
            "doc_id": doc_id,
            "state": "placeholder"
        }
    
    return {
        "create_document": create_document,
        "get_document_state": get_document_state
    }


@pytest.fixture
def configure_collaboration(jp_serverapp, collab_db_path, comments_db_path):
    """Configure the server for collaboration testing.
    
    This fixture sets up the necessary configuration for testing
    collaborative editing features.
    
    Parameters
    ----------
    jp_serverapp : JupyterServerApp
        The server application fixture
    collab_db_path : str
        Path to the collaboration database
    comments_db_path : str
        Path to the comments database
    
    Returns
    -------
    None
    """
    # Set configuration for collaboration testing
    jp_serverapp.config.JupyterCollaboration = {
        "enabled": True,
        "document_storage_class": "jupyter_ydoc.SQLiteYDocStorage",
        "document_storage_kwargs": {
            "db_path": collab_db_path,
            "auto_create_tables": True
        },
        "awareness_storage_class": "jupyter_ydoc.InMemoryAwarenessStorage"
    }
    
    # Set configuration for comments
    jp_serverapp.config.JupyterComments = {
        "comment_storage_class": "jupyter_comments.SQLiteCommentStorage",
        "comment_storage_kwargs": {
            "db_path": comments_db_path,
            "auto_create_tables": True
        }
    }
    
    # Set configuration for permissions
    jp_serverapp.config.JupyterPermissions = {
        "permission_storage_class": "jupyter_permissions.InMemoryPermissionStorage"
    }
    
    # Enable version history
    jp_serverapp.config.JupyterCollaboration.version_history_enabled = True
    jp_serverapp.config.JupyterCollaboration.version_history_class = "jupyter_ydoc.SQLiteVersionHistory"
    jp_serverapp.config.JupyterCollaboration.version_history_kwargs = {
        "db_path": collab_db_path,
        "auto_create_tables": True
    }
import asyncio
import json
import os
import pathlib
import pytest
import uuid
import time
import socket
import signal
import subprocess
from unittest.mock import MagicMock, patch

# Import Jupyter components
from jupyter_server.serverapp import ServerApp
from notebook.app import JupyterNotebookApp

# Import Yjs and collaboration components
try:
    import y_py as Y
except ImportError:
    # Mock Y if not available
    Y = MagicMock()

try:
    from jupyter_ydoc import YNotebook
except ImportError:
    # Mock YNotebook if not available
    YNotebook = MagicMock()

# Import WebSocket testing utilities
try:
    from websockets.client import connect as ws_connect
    from websockets.server import serve as ws_serve
    from websockets.exceptions import ConnectionClosed
except ImportError:
    # Mock WebSocket components if not available
    ws_connect = MagicMock()
    ws_serve = MagicMock()
    ConnectionClosed = Exception

# Reuse fixtures from main conftest.py if needed
pytest_plugins = ["jupyter_server.pytest_plugin"]


@pytest.fixture
async def jp_server_with_collab(jp_root_dir, jp_template_dir):
    """
    Creates a Jupyter server with collaboration enabled for integration testing.
    
    Args:
        jp_root_dir: Jupyter root directory fixture from jupyter_server.pytest_plugin
        jp_template_dir: Jupyter template directory fixture from jupyter_server.pytest_plugin
        
    Returns:
        A configured and running ServerApp instance with collaboration enabled.
    """
    # Create a temporary directory for collaboration test data
    collab_data_dir = jp_root_dir / "collab_data"
    collab_data_dir.mkdir(exist_ok=True)
    
    # Configure the server app with collaboration enabled
    app = ServerApp()
    app.root_dir = str(jp_root_dir)
    app.notebook_dir = str(jp_root_dir)
    app.config.JupyterCollaboration = {
        "enabled": True,
        "document_storage_class": "jupyter_ydoc.InMemoryYDocStorage",
        "awareness_storage_class": "jupyter_ydoc.InMemoryAwarenessStorage"
    }
    
    # Initialize and start the app
    await app.initialize(argv=[])
    await app.start()
    
    try:
        yield app
    finally:
        # Clean up
        await app.cleanup_kernels()
        await app.stop()
        app.clear_instance()


@pytest.fixture
async def jp_notebook_with_collab(jp_server_with_collab, jp_root_dir, jp_template_dir):
    """
    Creates a Jupyter notebook app with collaboration enabled for integration testing.
    
    Args:
        jp_server_with_collab: The server app fixture with collaboration enabled
        jp_root_dir: Jupyter root directory fixture from jupyter_server.pytest_plugin
        jp_template_dir: Jupyter template directory fixture from jupyter_server.pytest_plugin
        
    Returns:
        A configured and running JupyterNotebookApp instance with collaboration enabled.
    """
    # Create a notebook app linked to the server app
    app = JupyterNotebookApp(serverapp=jp_server_with_collab)
    app.static_dir = str(jp_root_dir)
    app.templates_dir = str(jp_template_dir)
    app.app_url = "/"
    
    # Initialize and start the app
    await app.initialize(argv=[])
    await app.start()
    
    try:
        yield app
    finally:
        # Clean up
        await app.stop()
        app.clear_instance()


class WebSocketTestClient:
    """
    A WebSocket client for testing collaborative editing features.
    
    This client can connect to a Jupyter server's WebSocket endpoint for
    collaboration testing, send and receive messages, and simulate network
    conditions like disconnections and latency.
    """
    
    def __init__(self, server_app, user_id=None, roles=None):
        """
        Initialize a WebSocket test client.
        
        Args:
            server_app: The Jupyter server app to connect to
            user_id: The user ID to use for this client
            roles: The roles to assign to this user
        """
        self.server_app = server_app
        self.user_id = user_id or f"test-user-{uuid.uuid4().hex[:8]}"
        self.roles = roles or ["editor"]
        self.websocket = None
        self.connected = False
        self.doc_id = None
        self.ydoc = Y.YDoc()
        self.received_messages = []
        self.connection_interrupted = False
        self.offline_updates = []
        
    async def connect(self, doc_id=None):
        """
        Connect to the collaboration WebSocket endpoint.
        
        Args:
            doc_id: The document ID to collaborate on
            
        Returns:
            True if connection was successful, False otherwise
        """
        if doc_id:
            self.doc_id = doc_id
        else:
            self.doc_id = f"test-doc-{uuid.uuid4().hex[:8]}"
            
        # Construct the WebSocket URL
        server_url = f"ws://localhost:{self.server_app.port}"
        ws_url = f"{server_url}/api/collaboration/{self.doc_id}/ws"
        
        try:
            # Connect to the WebSocket endpoint
            self.websocket = await ws_connect(
                ws_url,
                extra_headers={
                    "X-Jupyter-User-Id": self.user_id,
                    "X-Jupyter-User-Roles": ",".join(self.roles)
                }
            )
            self.connected = True
            
            # Start a background task to receive messages
            asyncio.create_task(self._receive_messages())
            
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    async def disconnect(self):
        """
        Disconnect from the WebSocket endpoint.
        
        Returns:
            True if disconnection was successful, False otherwise
        """
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
            self.connected = False
            return True
        return False
    
    async def send(self, message):
        """
        Send a message to the WebSocket endpoint.
        
        Args:
            message: The message to send (will be JSON-encoded)
            
        Returns:
            True if the message was sent, False otherwise
        """
        if not self.connected or self.connection_interrupted:
            # Store updates for later if we're offline
            self.offline_updates.append(message)
            return False
            
        try:
            if isinstance(message, dict):
                message = json.dumps(message)
                
            await self.websocket.send(message)
            return True
        except Exception as e:
            print(f"Send failed: {e}")
            return False
    
    async def _receive_messages(self):
        """
        Background task to receive messages from the WebSocket endpoint.
        """
        try:
            while self.connected and not self.websocket.closed:
                try:
                    message = await self.websocket.recv()
                    self.received_messages.append(message)
                except ConnectionClosed:
                    self.connected = False
                    break
        except Exception as e:
            print(f"Receive error: {e}")
            self.connected = False
    
    async def simulate_network_interruption(self, duration=2.0):
        """
        Simulate a network interruption by temporarily closing the WebSocket connection.
        
        Args:
            duration: The duration of the interruption in seconds
            
        Returns:
            True if the interruption was simulated, False otherwise
        """
        if not self.connected:
            return False
            
        # Mark as interrupted to prevent sending messages
        self.connection_interrupted = True
        
        # Close the current connection
        old_websocket = self.websocket
        await old_websocket.close()
        
        # Wait for the specified duration
        await asyncio.sleep(duration)
        
        # Reconnect
        await self.connect(self.doc_id)
        self.connection_interrupted = False
        
        # Send any offline updates
        for update in self.offline_updates:
            await self.send(update)
        self.offline_updates = []
        
        return True
    
    async def simulate_high_latency(self, latency=0.5, duration=5.0):
        """
        Simulate high network latency by delaying message sending and receiving.
        
        Args:
            latency: The latency to simulate in seconds
            duration: How long to simulate high latency in seconds
            
        Returns:
            True if high latency was simulated, False otherwise
        """
        if not self.connected:
            return False
            
        # Patch the send and receive methods to add delay
        original_send = self.websocket.send
        original_recv = self.websocket.recv
        
        async def delayed_send(message):
            await asyncio.sleep(latency)
            return await original_send(message)
            
        async def delayed_recv():
            await asyncio.sleep(latency)
            return await original_recv()
            
        self.websocket.send = delayed_send
        self.websocket.recv = delayed_recv
        
        # Wait for the specified duration
        await asyncio.sleep(duration)
        
        # Restore original methods
        self.websocket.send = original_send
        self.websocket.recv = original_recv
        
        return True
    
    async def update_cell(self, cell_id, content):
        """
        Update a cell in the collaborative document.
        
        Args:
            cell_id: The ID of the cell to update
            content: The new content for the cell
            
        Returns:
            True if the update was sent, False otherwise
        """
        # Create a simple update message
        # In a real implementation, this would be a proper Yjs update
        update = {
            "type": "update",
            "cell_id": cell_id,
            "content": content,
            "user_id": self.user_id,
            "timestamp": int(time.time() * 1000)
        }
        
        return await self.send(update)
    
    async def get_document_state(self):
        """
        Get the current state of the document.
        
        Returns:
            The document state as reported by the server
        """
        # Request the current document state
        await self.send({"type": "get_document"})
        
        # Wait for the response
        for _ in range(10):  # Try up to 10 times
            for message in reversed(self.received_messages):
                try:
                    data = json.loads(message)
                    if data.get("type") == "document_state":
                        return data.get("state")
                except (json.JSONDecodeError, AttributeError):
                    pass
            await asyncio.sleep(0.1)
            
        return None
    
    def clear_received_messages(self):
        """
        Clear the list of received messages.
        """
        self.received_messages = []
    
    async def wait_for_message_containing(self, content, timeout=5.0):
        """
        Wait for a message containing the specified content.
        
        Args:
            content: The content to look for in messages
            timeout: How long to wait in seconds
            
        Returns:
            The message if found, None otherwise
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            for message in self.received_messages:
                if content in str(message):
                    return message
            await asyncio.sleep(0.1)
        return None


@pytest.fixture
async def jp_ws_client(jp_server_with_collab):
    """
    Creates a WebSocket client connected to the test server.
    
    Args:
        jp_server_with_collab: The Jupyter server app with collaboration enabled
        
    Returns:
        A function that creates WebSocket test clients.
    """
    clients = []
    
    async def create_client(user_id=None, roles=None):
        """
        Creates a WebSocket client with specified user identity.
        
        Args:
            user_id: The user ID to use for this client
            roles: The roles to assign to this user
            
        Returns:
            A WebSocketTestClient instance.
        """
        client = WebSocketTestClient(jp_server_with_collab, user_id=user_id, roles=roles)
        clients.append(client)
        return client
    
    yield create_client
    
    # Disconnect all clients after the test
    for client in clients:
        await client.disconnect()


@pytest.fixture
async def create_test_document(jp_server_with_collab, jp_root_dir):
    """
    Creates a test notebook document for collaboration testing.
    
    Args:
        jp_server_with_collab: The Jupyter server app with collaboration enabled
        jp_root_dir: Jupyter root directory fixture
        
    Returns:
        A function that creates test documents with specified content.
    """
    created_files = []
    
    async def _create_document(name=None, cells=None):
        """
        Create a test notebook document.
        
        Args:
            name: The name of the document (default: a random name)
            cells: The cells to include in the document
            
        Returns:
            The path to the created document.
        """
        if name is None:
            name = f"test-notebook-{uuid.uuid4().hex[:8]}.ipynb"
            
        if not name.endswith(".ipynb"):
            name += ".ipynb"
            
        if cells is None:
            cells = [
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": ["# Test Notebook\n", "This is a test notebook for collaboration testing."]
                },
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": ["# Test code cell\n", "print('Hello, collaborative world!')"],
                }
            ]
            
        # Create notebook content
        content = {
            "cells": cells,
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
                    "version": "3.8.0"
                },
                "collaboration": {
                    "enabled": True
                }
            },
            "nbformat": 4,
            "nbformat_minor": 5
        }
        
        # Write the notebook to disk
        file_path = jp_root_dir / name
        with open(file_path, "w") as f:
            json.dump(content, f)
            
        created_files.append(file_path)
        return str(file_path)
    
    yield _create_document
    
    # Clean up created files
    for file_path in created_files:
        try:
            os.remove(file_path)
        except OSError:
            pass


@pytest.fixture
async def simulate_server_restart(jp_server_with_collab):
    """
    Simulates a server restart by stopping and starting the server.
    
    Args:
        jp_server_with_collab: The Jupyter server app with collaboration enabled
        
    Returns:
        A function that simulates a server restart.
    """
    async def _restart_server():
        """
        Restart the server by stopping and starting it.
        
        Returns:
            True if the restart was successful, False otherwise.
        """
        try:
            # Stop the server
            await jp_server_with_collab.stop()
            
            # Wait a moment to ensure it's fully stopped
            await asyncio.sleep(1)
            
            # Start the server again
            await jp_server_with_collab.start()
            
            # Wait a moment to ensure it's fully started
            await asyncio.sleep(1)
            
            return True
        except Exception as e:
            print(f"Server restart failed: {e}")
            return False
    
    return _restart_server


@pytest.fixture
async def create_collaborative_session(jp_ws_client, create_test_document):
    """
    Creates a collaborative editing session with multiple clients.
    
    Args:
        jp_ws_client: The WebSocket client factory fixture
        create_test_document: The test document creation fixture
        
    Returns:
        A function that creates a collaborative session with multiple clients.
    """
    async def _create_session(num_clients=2, document_name=None):
        """
        Create a collaborative session with multiple clients.
        
        Args:
            num_clients: The number of clients to create
            document_name: The name of the document to collaborate on
            
        Returns:
            A tuple containing (document_path, clients) where clients is a list of
            connected WebSocketTestClient instances.
        """
        # Create a test document
        document_path = await create_test_document(name=document_name)
        document_name = os.path.basename(document_path)
        
        # Create and connect clients
        clients = []
        for i in range(num_clients):
            client = await jp_ws_client(user_id=f"user-{i+1}")
            await client.connect(document_name)
            clients.append(client)
            
        # Wait a moment for all clients to fully connect
        await asyncio.sleep(1)
        
        return document_path, clients
    
    return _create_session


@pytest.fixture
async def verify_document_consistency(jp_ws_client):
    """
    Verifies that all clients see the same document state.
    
    Args:
        jp_ws_client: The WebSocket client factory fixture
        
    Returns:
        A function that verifies document consistency across clients.
    """
    async def _verify_consistency(clients, timeout=5.0):
        """
        Verify that all clients see the same document state.
        
        Args:
            clients: A list of WebSocketTestClient instances
            timeout: How long to wait for consistency in seconds
            
        Returns:
            True if all clients see the same state, False otherwise.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Get document state from all clients
            states = []
            for client in clients:
                state = await client.get_document_state()
                if state:
                    states.append(state)
            
            # If we have states from all clients, check if they're consistent
            if len(states) == len(clients) and all(states):
                # Check if all states are the same
                first_state = json.dumps(states[0], sort_keys=True)
                if all(json.dumps(state, sort_keys=True) == first_state for state in states):
                    return True
            
            # Wait a moment before trying again
            await asyncio.sleep(0.5)
        
        return False
    
    return _verify_consistency
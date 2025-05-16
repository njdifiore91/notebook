import asyncio
import json
import os
import pathlib
import pytest
import uuid
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
except ImportError:
    # Mock WebSocket components if not available
    ws_connect = MagicMock()
    ws_serve = MagicMock()


# Reuse fixtures from main conftest.py if needed
pytest_plugins = ["jupyter_server.pytest_plugin"]


@pytest.fixture
def yjs_doc():
    """
    Creates a Yjs document for testing CRDT-based synchronization.
    
    Returns:
        A Y.Doc instance that can be used for collaborative editing tests.
    """
    doc = Y.Doc()
    try:
        yield doc
    finally:
        # Clean up resources if needed
        pass


@pytest.fixture
def ynotebook(yjs_doc):
    """
    Creates a YNotebook instance for testing notebook-specific collaboration.
    
    Args:
        yjs_doc: The Yjs document fixture
        
    Returns:
        A YNotebook instance connected to the test Yjs document.
    """
    notebook = YNotebook(yjs_doc)
    try:
        yield notebook
    finally:
        # Clean up resources if needed
        pass


@pytest.fixture
def awareness_state():
    """
    Creates an awareness state for testing user presence features.
    
    Returns:
        A mock awareness state object for testing presence tracking.
    """
    # Create a mock awareness object or use actual implementation if available
    try:
        awareness = Y.Awareness(Y.Doc())
    except (AttributeError, TypeError):
        # Fall back to mock if Y.Awareness is not available or not working as expected
        awareness = MagicMock()
        awareness.set_local_state = MagicMock()
        awareness.get_states = MagicMock(return_value={})
        
    return awareness


@pytest.fixture
async def mock_websocket_server():
    """
    Creates a mock WebSocket server for testing collaboration communication.
    
    Yields:
        A tuple containing (server, port, messages) where:
        - server: The WebSocket server object
        - port: The port the server is listening on
        - messages: A list that will be populated with received messages
    """
    received_messages = []
    clients = set()
    
    async def handler(websocket):
        clients.add(websocket)
        try:
            async for message in websocket:
                received_messages.append(message)
                # Broadcast to all other clients
                for client in clients:
                    if client != websocket and client.open:
                        await client.send(message)
        finally:
            clients.remove(websocket)
    
    # Use a random port to avoid conflicts
    port = 8988  # Default test port, can be randomized if needed
    server = await ws_serve(handler, "localhost", port)
    
    try:
        yield server, port, received_messages
    finally:
        server.close()
        await server.wait_closed()


@pytest.fixture
async def multi_client_websocket_simulation(mock_websocket_server):
    """
    Provides a factory for creating multiple WebSocket clients for testing concurrent editing.
    
    Args:
        mock_websocket_server: The WebSocket server fixture
        
    Returns:
        A function that creates a new WebSocket client with the given user ID.
    """
    server, port, messages = mock_websocket_server
    clients = []
    
    async def create_client(user_id=None):
        if user_id is None:
            user_id = f"test-user-{len(clients) + 1}"
            
        websocket = await ws_connect(f"ws://localhost:{port}")
        
        # Create a client object with methods for testing
        client = {
            "websocket": websocket,
            "user_id": user_id,
            "send": websocket.send,
            "receive": websocket.recv,
            "close": websocket.close
        }
        
        clients.append(client)
        return client
    
    try:
        yield create_client
    finally:
        # Clean up all clients
        for client in clients:
            if not client["websocket"].closed:
                asyncio.create_task(client["websocket"].close())


@pytest.fixture
def mock_collaboration_provider():
    """
    Creates a mock collaboration provider for testing.
    
    Returns:
        A mock object implementing the ICollaborationProvider interface.
    """
    provider = MagicMock()
    provider.connect_document = MagicMock(return_value=asyncio.Future())
    provider.disconnect_document = MagicMock(return_value=asyncio.Future())
    provider.get_document = MagicMock()
    provider.is_connected = MagicMock(return_value=True)
    
    return provider


@pytest.fixture
def mock_presence_tracker():
    """
    Creates a mock presence tracker for testing user awareness features.
    
    Returns:
        A mock object implementing the IPresenceTracker interface.
    """
    tracker = MagicMock()
    tracker.set_awareness = MagicMock()
    tracker.get_awareness_states = MagicMock(return_value={})
    tracker.on_awareness_change = MagicMock(return_value=MagicMock())
    
    return tracker


@pytest.fixture
def mock_comment_manager():
    """
    Creates a mock comment manager for testing comment functionality.
    
    Returns:
        A mock object implementing the ICommentManager interface.
    """
    manager = MagicMock()
    manager.get_threads = MagicMock(return_value=asyncio.Future())
    manager.create_thread = MagicMock(return_value=asyncio.Future())
    manager.add_comment = MagicMock(return_value=asyncio.Future())
    manager.set_thread_status = MagicMock(return_value=asyncio.Future())
    
    return manager


@pytest.fixture
def mock_permission_manager():
    """
    Creates a mock permission manager for testing access control.
    
    Returns:
        A mock object implementing the IPermissionManager interface.
    """
    manager = MagicMock()
    manager.get_permissions = MagicMock(return_value=asyncio.Future())
    manager.check_permission = MagicMock(return_value=asyncio.Future())
    manager.set_permission = MagicMock(return_value=asyncio.Future())
    
    return manager


@pytest.fixture
def create_test_notebook_content():
    """
    Helper function to create test notebook content with predefined cells.
    
    Returns:
        A function that generates notebook content with the specified cells.
    """
    def _create_content(cells=None):
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
            
        return {
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
    
    return _create_content


@pytest.fixture
def create_test_yjs_update():
    """
    Helper function to create test Yjs updates for simulating collaborative edits.
    
    Returns:
        A function that generates a simulated Yjs update.
    """
    def _create_update(user_id=None, cell_id=None, content=None):
        if user_id is None:
            user_id = f"test-user-{uuid.uuid4().hex[:8]}"
            
        if cell_id is None:
            cell_id = f"cell-{uuid.uuid4().hex[:8]}"
            
        if content is None:
            content = "Test content"
            
        # Create a mock update that simulates a Yjs update
        # In a real implementation, this would be a binary Yjs update
        update = {
            "user_id": user_id,
            "cell_id": cell_id,
            "content": content,
            "timestamp": int(asyncio.get_event_loop().time() * 1000)
        }
        
        return json.dumps(update).encode()
    
    return _create_update


@pytest.fixture
def create_test_awareness_update():
    """
    Helper function to create test awareness updates for simulating user presence.
    
    Returns:
        A function that generates a simulated awareness update.
    """
    def _create_update(user_id=None, cursor_pos=None, selection=None, status="active"):
        if user_id is None:
            user_id = f"test-user-{uuid.uuid4().hex[:8]}"
            
        if cursor_pos is None:
            cursor_pos = {"line": 0, "ch": 0}
            
        # Create a mock awareness update
        update = {
            "user": {
                "id": user_id,
                "name": f"Test User {user_id}",
                "color": "#ff0000"
            },
            "cursor": cursor_pos,
            "selection": selection,
            "status": status,
            "timestamp": int(asyncio.get_event_loop().time() * 1000)
        }
        
        return json.dumps(update).encode()
    
    return _create_update


@pytest.fixture
def collab_test_config():
    """
    Provides configuration for collaboration tests.
    
    Returns:
        A dictionary with configuration values for collaboration tests.
    """
    return {
        "websocket_url": "ws://localhost:8988",
        "collaboration_enabled": True,
        "default_user": "test-user",
        "test_document_id": f"test-doc-{uuid.uuid4().hex[:8]}",
        "timeout": 5  # seconds
    }


@pytest.fixture
def mock_collaborative_notebook():
    """
    Creates a mock collaborative notebook for testing.
    
    Returns:
        A mock object implementing the ICollaborativeNotebook interface.
    """
    notebook = MagicMock()
    notebook.ydoc = MagicMock()
    notebook.is_dirty = False
    notebook.save = MagicMock(return_value=asyncio.Future())
    notebook.get_history = MagicMock()
    
    return notebook


@pytest.fixture
async def collab_server_app(jp_root_dir, jp_template_dir):
    """
    Creates a Jupyter server app with collaboration enabled for testing.
    
    Args:
        jp_root_dir: Jupyter root directory fixture from jupyter_server.pytest_plugin
        jp_template_dir: Jupyter template directory fixture from jupyter_server.pytest_plugin
        
    Returns:
        A configured ServerApp instance with collaboration enabled.
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
    
    # Initialize but don't start the app
    await app.initialize(argv=[])
    
    try:
        yield app
    finally:
        # Clean up
        await app.cleanup_kernels()
        app.clear_instance()


@pytest.fixture
async def collab_notebook_app(collab_server_app, jp_root_dir, jp_template_dir):
    """
    Creates a Jupyter notebook app with collaboration enabled for testing.
    
    Args:
        collab_server_app: The server app fixture with collaboration enabled
        jp_root_dir: Jupyter root directory fixture from jupyter_server.pytest_plugin
        jp_template_dir: Jupyter template directory fixture from jupyter_server.pytest_plugin
        
    Returns:
        A configured JupyterNotebookApp instance with collaboration enabled.
    """
    # Create a notebook app linked to the server app
    app = JupyterNotebookApp(serverapp=collab_server_app)
    app.static_dir = str(jp_root_dir)
    app.templates_dir = str(jp_template_dir)
    app.app_url = "/"
    
    # Initialize but don't start the app
    await app.initialize(argv=[])
    
    try:
        yield app
    finally:
        # Clean up
        app.clear_instance()


@pytest.fixture
def mock_websocket_client_factory():
    """
    Creates a factory for mock WebSocket clients for testing.
    
    Returns:
        A function that creates mock WebSocket clients with specified user information.
    """
    clients = []
    
    def create_client(user_id=None, roles=None):
        if user_id is None:
            user_id = f"test-user-{len(clients) + 1}"
            
        if roles is None:
            roles = ["editor"]
            
        # Create a mock WebSocket client
        client = MagicMock()
        client.user_id = user_id
        client.roles = roles
        client.connect = MagicMock(return_value=asyncio.Future())
        client.disconnect = MagicMock(return_value=asyncio.Future())
        client.send = MagicMock(return_value=asyncio.Future())
        client.receive = MagicMock(return_value=asyncio.Future())
        
        clients.append(client)
        return client
    
    return create_client
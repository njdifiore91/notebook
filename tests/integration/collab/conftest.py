import asyncio
import json
import os
import pytest
from unittest.mock import MagicMock, patch

# Fixtures for integration testing of collaboration features

@pytest.fixture
async def jp_collab_config():
    """Configuration for the collaboration server."""
    return {
        "collaboration_enabled": True,
        "collaboration_backend": "memory",
        "collaboration_lock_timeout": 5.0,  # 5 seconds for testing
        "collaboration_document_cleanup_delay": 30.0,  # 30 seconds
    }

@pytest.fixture
async def jp_collab_server(jp_serverapp, jp_collab_config):
    """Create a Jupyter server with collaboration enabled for testing."""
    # Configure the server with collaboration enabled
    for key, value in jp_collab_config.items():
        setattr(jp_serverapp, key, value)
    
    # Initialize the collaboration extension
    jp_serverapp.init_collaboration()
    
    return jp_serverapp

@pytest.fixture
async def mock_notebook():
    """Create a mock notebook for testing."""
    return {
        "metadata": {"kernelspec": {"name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": [
            {"id": "cell1", "cell_type": "code", "source": "print('Hello, world!')", "metadata": {}, "outputs": []},
            {"id": "cell2", "cell_type": "markdown", "source": "# Test Markdown", "metadata": {}},
            {"id": "cell3", "cell_type": "code", "source": "import numpy as np\nnp.random.rand(10)", "metadata": {}, "outputs": []}
        ]
    }

@pytest.fixture
async def test_notebook_path(jp_collab_server, mock_notebook):
    """Create a test notebook file for collaboration testing."""
    notebook_path = "test_collab_notebook.ipynb"
    
    # Create the notebook using the server API
    await jp_collab_server.contents_manager.save(
        model={"type": "notebook", "content": mock_notebook},
        path=notebook_path
    )
    
    yield notebook_path
    
    # Clean up the notebook file after the test
    try:
        await jp_collab_server.contents_manager.delete(notebook_path)
    except Exception:
        pass

@pytest.fixture
async def jp_collab_client(jp_collab_server, jp_ws_fetch, test_notebook_path):
    """Create a single WebSocket client connected to the collaboration server."""
    # Connect to the collaboration WebSocket endpoint
    ws = await jp_ws_fetch(
        "api", "collaboration", "documents", test_notebook_path,
        headers={"X-Jupyter-User-Id": "test_user"}
    )
    
    # Store the user ID with the client
    ws.user_id = "test_user"
    
    yield ws
    
    # Clean up: close the WebSocket connection
    await ws.close()

@pytest.fixture
async def jp_collab_clients(jp_collab_server, jp_ws_fetch, test_notebook_path):
    """Create multiple WebSocket clients connected to the collaboration server."""
    # Create WebSocket connections for multiple users
    clients = {}
    user_ids = ["user1", "user2", "admin"]
    
    for user_id in user_ids:
        # Connect to the collaboration WebSocket endpoint
        ws = await jp_ws_fetch(
            "api", "collaboration", "documents", test_notebook_path,
            headers={"X-Jupyter-User-Id": user_id}
        )
        
        # Store the user ID with the client
        ws.user_id = user_id
        clients[user_id] = ws
    
    # Wait for all clients to connect and initialize
    await asyncio.sleep(0.5)
    
    yield clients
    
    # Clean up: close all WebSocket connections
    for client in clients.values():
        await client.close()

# Helper functions for the tests

async def send_message(client, message_type, **kwargs):
    """Send a message through the WebSocket client."""
    message = {"type": message_type, **kwargs}
    await client.write_message(json.dumps(message))

async def send_lock_request(client, action, cell_id):
    """Send a lock request through the WebSocket client."""
    return await send_message(client, "lock", action=action, cellId=cell_id)

async def read_next_message(client):
    """Read the next message from the WebSocket client."""
    message = await client.read_message()
    return json.loads(message) if message else None

async def wait_for_message(client, message_type, timeout=2.0):
    """Wait for a specific type of message from the WebSocket client."""
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < timeout:
        message = await client.read_message()
        if not message:
            continue
            
        data = json.loads(message)
        if data.get("type") == message_type:
            return data
            
        # Small delay to avoid busy waiting
        await asyncio.sleep(0.05)
    
    raise TimeoutError(f"No {message_type} message received within {timeout} seconds")

async def wait_for_lock_message(client, expected_cell_id=None, timeout=2.0):
    """Wait for a lock-related message from the WebSocket client."""
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < timeout:
        message = await client.read_message()
        if not message:
            continue
            
        data = json.loads(message)
        if data.get("type") == "lock_state" and (expected_cell_id is None or data.get("cellId") == expected_cell_id):
            return data
            
        # Small delay to avoid busy waiting
        await asyncio.sleep(0.05)
    
    raise TimeoutError(f"No lock message received within {timeout} seconds")
import asyncio
import json
import pytest
import time
from unittest.mock import MagicMock, patch

# Import the necessary modules for testing
from tornado.websocket import WebSocketClientConnection
from tornado import gen

# Fixtures for integration testing

@pytest.fixture
async def jp_collab_server(jp_serverapp):
    """Create a Jupyter server with collaboration enabled for testing."""
    # Configure the server with collaboration enabled
    jp_serverapp.collaboration_enabled = True
    jp_serverapp.collaboration_backend = "memory"
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
async def jp_collab_clients(jp_collab_server, jp_ws_fetch, mock_notebook):
    """Create multiple WebSocket clients connected to the collaboration server."""
    # Create a notebook file for testing
    notebook_path = "test_notebook.ipynb"
    
    # Create the notebook using the server API
    await jp_collab_server.contents_manager.save(
        model={"type": "notebook", "content": mock_notebook},
        path=notebook_path
    )
    
    # Create WebSocket connections for multiple users
    clients = {}
    user_ids = ["user1", "user2", "admin"]
    
    for user_id in user_ids:
        # Connect to the collaboration WebSocket endpoint
        ws = await jp_ws_fetch(
            "api", "collaboration", "documents", notebook_path,
            headers={"X-Jupyter-User-Id": user_id}
        )
        
        # Store the client with its user ID
        ws.user_id = user_id
        clients[user_id] = ws
    
    # Wait for all clients to connect and initialize
    await asyncio.sleep(0.5)
    
    yield clients
    
    # Clean up: close all WebSocket connections
    for client in clients.values():
        await client.close()

# Helper functions for the tests

async def send_lock_request(client, action, cell_id):
    """Send a lock request through the WebSocket client."""
    message = {
        "type": "lock",
        "action": action,  # "acquire" or "release"
        "cellId": cell_id
    }
    await client.write_message(json.dumps(message))

async def read_next_message(client):
    """Read the next message from the WebSocket client."""
    message = await client.read_message()
    return json.loads(message)

async def wait_for_lock_message(client, expected_cell_id=None, timeout=2.0):
    """Wait for a lock-related message from the WebSocket client."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        message = await client.read_message()
        if not message:
            continue
            
        data = json.loads(message)
        if data.get("type") == "lock_state" and (expected_cell_id is None or data.get("cellId") == expected_cell_id):
            return data
            
        # Small delay to avoid busy waiting
        await asyncio.sleep(0.05)
    
    raise TimeoutError(f"No lock message received within {timeout} seconds")

# Integration tests for the cell locking mechanism

@pytest.mark.asyncio
async def test_lock_acquisition_and_broadcast(jp_collab_clients):
    """Test that when a user acquires a lock, it's broadcast to all clients."""
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell_id = "cell1"
    
    # User 1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    
    # User 1 should receive confirmation
    user1_message = await wait_for_lock_message(user1_client, cell_id)
    assert user1_message["type"] == "lock_state"
    assert user1_message["cellId"] == cell_id
    assert user1_message["locked"] is True
    assert user1_message["owner"] == "user1"
    
    # User 2 should also receive the lock notification
    user2_message = await wait_for_lock_message(user2_client, cell_id)
    assert user2_message["type"] == "lock_state"
    assert user2_message["cellId"] == cell_id
    assert user2_message["locked"] is True
    assert user2_message["owner"] == "user1"

@pytest.mark.asyncio
async def test_lock_conflict_resolution(jp_collab_clients):
    """Test that a user cannot acquire a lock on a cell that's already locked by another user."""
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell_id = "cell1"
    
    # User 1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    
    # Wait for confirmation
    await wait_for_lock_message(user1_client, cell_id)
    
    # User 2 attempts to acquire the same lock
    await send_lock_request(user2_client, "acquire", cell_id)
    
    # User 2 should receive a lock rejection
    user2_message = await wait_for_lock_message(user2_client, cell_id)
    assert user2_message["type"] == "lock_state"
    assert user2_message["cellId"] == cell_id
    assert user2_message["locked"] is True
    assert user2_message["owner"] == "user1"  # Still owned by user1
    assert user2_message.get("error") == "Cell is already locked"

@pytest.mark.asyncio
async def test_lock_release_and_broadcast(jp_collab_clients):
    """Test that when a user releases a lock, it's broadcast to all clients."""
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell_id = "cell1"
    
    # User 1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    await wait_for_lock_message(user1_client, cell_id)
    
    # User 1 releases the lock
    await send_lock_request(user1_client, "release", cell_id)
    
    # User 1 should receive confirmation of release
    user1_message = await wait_for_lock_message(user1_client, cell_id)
    assert user1_message["type"] == "lock_state"
    assert user1_message["cellId"] == cell_id
    assert user1_message["locked"] is False
    assert user1_message["owner"] is None
    
    # User 2 should also receive the lock release notification
    user2_message = await wait_for_lock_message(user2_client, cell_id)
    assert user2_message["type"] == "lock_state"
    assert user2_message["cellId"] == cell_id
    assert user2_message["locked"] is False
    assert user2_message["owner"] is None

@pytest.mark.asyncio
async def test_concurrent_locks_on_different_cells(jp_collab_clients):
    """Test that different users can lock different cells concurrently."""
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell1_id = "cell1"
    cell2_id = "cell2"
    
    # User 1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell1_id)
    await wait_for_lock_message(user1_client, cell1_id)
    
    # User 2 acquires a lock on cell2
    await send_lock_request(user2_client, "acquire", cell2_id)
    await wait_for_lock_message(user2_client, cell2_id)
    
    # Verify User 1's lock on cell1
    await send_lock_request(user1_client, "query", cell1_id)
    user1_message = await wait_for_lock_message(user1_client, cell1_id)
    assert user1_message["locked"] is True
    assert user1_message["owner"] == "user1"
    
    # Verify User 2's lock on cell2
    await send_lock_request(user2_client, "query", cell2_id)
    user2_message = await wait_for_lock_message(user2_client, cell2_id)
    assert user2_message["locked"] is True
    assert user2_message["owner"] == "user2"

@pytest.mark.asyncio
async def test_admin_override(jp_collab_clients):
    """Test that an admin can override a lock owned by another user."""
    user1_client = jp_collab_clients["user1"]
    admin_client = jp_collab_clients["admin"]
    cell_id = "cell1"
    
    # User 1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    await wait_for_lock_message(user1_client, cell_id)
    
    # Admin overrides the lock
    await send_lock_request(admin_client, "admin_override", cell_id)
    
    # Admin should receive confirmation
    admin_message = await wait_for_lock_message(admin_client, cell_id)
    assert admin_message["type"] == "lock_state"
    assert admin_message["cellId"] == cell_id
    assert admin_message["locked"] is False
    assert admin_message["owner"] is None
    
    # User 1 should also receive notification that their lock was overridden
    user1_message = await wait_for_lock_message(user1_client, cell_id)
    assert user1_message["type"] == "lock_state"
    assert user1_message["cellId"] == cell_id
    assert user1_message["locked"] is False
    assert user1_message["owner"] is None
    assert "overridden" in user1_message.get("message", "")

@pytest.mark.asyncio
async def test_non_admin_cannot_override(jp_collab_clients):
    """Test that a non-admin user cannot override a lock owned by another user."""
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]  # Not an admin
    cell_id = "cell1"
    
    # User 1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    await wait_for_lock_message(user1_client, cell_id)
    
    # User 2 attempts to override the lock
    await send_lock_request(user2_client, "admin_override", cell_id)
    
    # User 2 should receive an error
    user2_message = await wait_for_lock_message(user2_client, cell_id)
    assert user2_message["type"] == "lock_state"
    assert user2_message["cellId"] == cell_id
    assert user2_message["locked"] is True  # Lock still exists
    assert user2_message["owner"] == "user1"  # Still owned by user1
    assert "permission" in user2_message.get("error", "")

@pytest.mark.asyncio
async def test_automatic_lock_timeout(jp_collab_clients):
    """Test that locks are automatically released after a timeout period."""
    # This test assumes the server is configured with a short lock timeout for testing
    # In a real implementation, you might need to mock or configure this timeout
    
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell_id = "cell1"
    
    # Configure a short timeout for testing
    # This would typically be done through server configuration or mocking
    # For this test, we'll assume the server is configured with a 1-second timeout
    
    # User 1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    await wait_for_lock_message(user1_client, cell_id)
    
    # Wait for the lock to timeout
    # In a real test, this would be the actual timeout value
    await asyncio.sleep(2)  # Assuming a 1-second timeout
    
    # User 2 should now be able to acquire the lock
    await send_lock_request(user2_client, "acquire", cell_id)
    user2_message = await wait_for_lock_message(user2_client, cell_id)
    
    assert user2_message["type"] == "lock_state"
    assert user2_message["cellId"] == cell_id
    assert user2_message["locked"] is True
    assert user2_message["owner"] == "user2"  # User 2 now owns the lock

@pytest.mark.asyncio
async def test_lock_release_on_client_disconnect(jp_collab_clients):
    """Test that locks are released when a client disconnects."""
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell_id = "cell1"
    
    # User 1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    await wait_for_lock_message(user1_client, cell_id)
    
    # Simulate User 1 disconnecting
    await user1_client.close()
    
    # Wait for the server to process the disconnection
    await asyncio.sleep(0.5)
    
    # User 2 should now be able to acquire the lock
    await send_lock_request(user2_client, "acquire", cell_id)
    user2_message = await wait_for_lock_message(user2_client, cell_id)
    
    assert user2_message["type"] == "lock_state"
    assert user2_message["cellId"] == cell_id
    assert user2_message["locked"] is True
    assert user2_message["owner"] == "user2"  # User 2 now owns the lock
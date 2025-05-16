import pytest
import asyncio
import json
import time
from unittest.mock import MagicMock

# Import the WebSocketTestClient from conftest.py
# This is implicitly available through the pytest_plugins mechanism


@pytest.mark.asyncio
async def test_lock_acquisition_and_release(jp_ws_client, create_collaborative_session):
    """Test that users can acquire and release locks on specific cells."""
    # Create a collaborative session with 2 clients
    doc_path, clients = await create_collaborative_session(num_clients=2)
    user1, user2 = clients
    
    # Clear any existing messages
    user1.clear_received_messages()
    user2.clear_received_messages()
    
    # User 1 acquires a lock on cell1
    await user1.send({
        "type": "acquire_lock",
        "cell_id": "cell1",
        "user_id": user1.user_id,
        "user_name": "User 1"
    })
    
    # Wait for lock acquisition confirmation
    lock_message = await user1.wait_for_message_containing("lock_acquired")
    assert lock_message is not None
    
    # Verify user2 also receives the lock notification
    lock_notification = await user2.wait_for_message_containing("lock_acquired")
    assert lock_notification is not None
    
    # Parse the messages to verify details
    lock_data = json.loads(lock_message)
    assert lock_data["type"] == "lock_acquired"
    assert lock_data["cell_id"] == "cell1"
    assert lock_data["user_id"] == user1.user_id
    
    # User 1 releases the lock
    await user1.send({
        "type": "release_lock",
        "cell_id": "cell1",
        "user_id": user1.user_id
    })
    
    # Wait for lock release confirmation
    release_message = await user1.wait_for_message_containing("lock_released")
    assert release_message is not None
    
    # Verify user2 also receives the release notification
    release_notification = await user2.wait_for_message_containing("lock_released")
    assert release_notification is not None
    
    # Parse the messages to verify details
    release_data = json.loads(release_message)
    assert release_data["type"] == "lock_released"
    assert release_data["cell_id"] == "cell1"
    assert release_data["user_id"] == user1.user_id


@pytest.mark.asyncio
async def test_locked_cell_edit_prevention(jp_ws_client, create_collaborative_session):
    """Test that locked cells cannot be edited by other users."""
    # Create a collaborative session with 2 clients
    doc_path, clients = await create_collaborative_session(num_clients=2)
    user1, user2 = clients
    
    # Clear any existing messages
    user1.clear_received_messages()
    user2.clear_received_messages()
    
    # User 1 acquires a lock on cell1
    await user1.send({
        "type": "acquire_lock",
        "cell_id": "cell1",
        "user_id": user1.user_id,
        "user_name": "User 1"
    })
    
    # Wait for lock acquisition confirmation
    await user1.wait_for_message_containing("lock_acquired")
    
    # User 1 can edit the cell (should succeed)
    await user1.send({
        "type": "update_cell",
        "cell_id": "cell1",
        "content": "Updated by user 1",
        "user_id": user1.user_id
    })
    
    # Wait for update confirmation
    update_success = await user1.wait_for_message_containing("cell_updated")
    assert update_success is not None
    
    # User 2 attempts to edit the same cell (should fail)
    await user2.send({
        "type": "update_cell",
        "cell_id": "cell1",
        "content": "Updated by user 2",
        "user_id": user2.user_id
    })
    
    # Wait for error message
    error_message = await user2.wait_for_message_containing("error")
    assert error_message is not None
    
    # Parse the error message to verify details
    error_data = json.loads(error_message)
    assert error_data["type"] == "error"
    assert "locked" in error_data["message"].lower()
    assert "cell1" in error_data["message"]
    
    # User 2 should be able to edit a different cell
    await user2.send({
        "type": "update_cell",
        "cell_id": "cell2",
        "content": "Updated by user 2",
        "user_id": user2.user_id
    })
    
    # Wait for update confirmation
    update_success = await user2.wait_for_message_containing("cell_updated")
    assert update_success is not None


@pytest.mark.asyncio
async def test_lock_conflict_resolution(jp_ws_client, create_collaborative_session):
    """Test lock conflict resolution when multiple users attempt to lock the same cell."""
    # Create a collaborative session with 3 clients
    doc_path, clients = await create_collaborative_session(num_clients=3)
    user1, user2, user3 = clients
    
    # Clear any existing messages
    for client in clients:
        client.clear_received_messages()
    
    # User 1 acquires a lock on cell1
    await user1.send({
        "type": "acquire_lock",
        "cell_id": "cell1",
        "user_id": user1.user_id,
        "user_name": "User 1"
    })
    
    # Wait for lock acquisition confirmation
    await user1.wait_for_message_containing("lock_acquired")
    
    # User 2 attempts to acquire the same lock (should fail)
    await user2.send({
        "type": "acquire_lock",
        "cell_id": "cell1",
        "user_id": user2.user_id,
        "user_name": "User 2"
    })
    
    # Wait for lock acquisition failure
    lock_error = await user2.wait_for_message_containing("error")
    assert lock_error is not None
    
    # Parse the error message to verify details
    error_data = json.loads(lock_error)
    assert error_data["type"] == "error"
    assert "already locked" in error_data["message"].lower()
    assert user1.user_id in error_data["message"]
    
    # User 2 requests the lock (should be queued)
    await user2.send({
        "type": "request_lock",
        "cell_id": "cell1",
        "user_id": user2.user_id,
        "user_name": "User 2"
    })
    
    # Wait for lock request confirmation
    request_confirmation = await user2.wait_for_message_containing("lock_requested")
    assert request_confirmation is not None
    
    # User 1 should receive a notification about the lock request
    lock_request_notification = await user1.wait_for_message_containing("lock_requested")
    assert lock_request_notification is not None
    
    # User 1 releases the lock
    await user1.send({
        "type": "release_lock",
        "cell_id": "cell1",
        "user_id": user1.user_id
    })
    
    # Wait for lock release confirmation
    await user1.wait_for_message_containing("lock_released")
    
    # User 2 should automatically acquire the lock from the queue
    auto_lock_acquired = await user2.wait_for_message_containing("lock_acquired")
    assert auto_lock_acquired is not None
    
    # User 3 should see that user 2 now has the lock
    user3_notification = await user3.wait_for_message_containing("lock_acquired")
    assert user3_notification is not None
    
    # Parse the message to verify details
    lock_data = json.loads(auto_lock_acquired)
    assert lock_data["type"] == "lock_acquired"
    assert lock_data["cell_id"] == "cell1"
    assert lock_data["user_id"] == user2.user_id


@pytest.mark.asyncio
async def test_lock_timeout_and_auto_release(jp_ws_client, create_collaborative_session):
    """Test that locks are automatically released after timeout or disconnection."""
    # Create a collaborative session with 2 clients
    doc_path, clients = await create_collaborative_session(num_clients=2)
    user1, user2 = clients
    
    # Clear any existing messages
    user1.clear_received_messages()
    user2.clear_received_messages()
    
    # User 1 acquires a lock on cell1 with a short timeout (1 second for testing)
    await user1.send({
        "type": "acquire_lock",
        "cell_id": "cell1",
        "user_id": user1.user_id,
        "user_name": "User 1",
        "timeout": 1000  # 1 second timeout
    })
    
    # Wait for lock acquisition confirmation
    await user1.wait_for_message_containing("lock_acquired")
    
    # Wait for the timeout to expire (a bit more than the timeout)
    await asyncio.sleep(1.5)
    
    # Check that the lock was automatically released
    # User 2 should be able to acquire the lock now
    await user2.send({
        "type": "acquire_lock",
        "cell_id": "cell1",
        "user_id": user2.user_id,
        "user_name": "User 2"
    })
    
    # Wait for lock acquisition confirmation
    lock_acquired = await user2.wait_for_message_containing("lock_acquired")
    assert lock_acquired is not None
    
    # Parse the message to verify details
    lock_data = json.loads(lock_acquired)
    assert lock_data["type"] == "lock_acquired"
    assert lock_data["cell_id"] == "cell1"
    assert lock_data["user_id"] == user2.user_id
    
    # Now test disconnection auto-release
    # User 2 acquires a lock on cell2
    await user2.send({
        "type": "acquire_lock",
        "cell_id": "cell2",
        "user_id": user2.user_id,
        "user_name": "User 2"
    })
    
    # Wait for lock acquisition confirmation
    await user2.wait_for_message_containing("lock_acquired")
    
    # Simulate user2 disconnecting
    await user2.disconnect()
    
    # Wait for the server to detect the disconnection and release the locks
    await asyncio.sleep(2)
    
    # User 1 should be able to acquire the lock now
    await user1.send({
        "type": "acquire_lock",
        "cell_id": "cell2",
        "user_id": user1.user_id,
        "user_name": "User 1"
    })
    
    # Wait for lock acquisition confirmation
    lock_acquired = await user1.wait_for_message_containing("lock_acquired")
    assert lock_acquired is not None
    
    # Parse the message to verify details
    lock_data = json.loads(lock_acquired)
    assert lock_data["type"] == "lock_acquired"
    assert lock_data["cell_id"] == "cell2"
    assert lock_data["user_id"] == user1.user_id


@pytest.mark.asyncio
async def test_admin_lock_override(jp_ws_client, create_collaborative_session):
    """Test administrative override of locks."""
    # Create a collaborative session with 3 clients (one admin)
    doc_path, clients = await create_collaborative_session(num_clients=3)
    user1, user2, admin = clients
    
    # Set admin role for the third client
    admin.roles = ["admin"]
    
    # Clear any existing messages
    for client in clients:
        client.clear_received_messages()
    
    # User 1 acquires a lock on cell1
    await user1.send({
        "type": "acquire_lock",
        "cell_id": "cell1",
        "user_id": user1.user_id,
        "user_name": "User 1"
    })
    
    # Wait for lock acquisition confirmation
    await user1.wait_for_message_containing("lock_acquired")
    
    # Admin overrides the lock
    await admin.send({
        "type": "admin_override_lock",
        "cell_id": "cell1",
        "user_id": admin.user_id,
        "user_name": "Admin User"
    })
    
    # Wait for lock override confirmation
    override_message = await admin.wait_for_message_containing("lock_overridden")
    assert override_message is not None
    
    # User 1 should receive a notification about the lock override
    override_notification = await user1.wait_for_message_containing("lock_overridden")
    assert override_notification is not None
    
    # Parse the message to verify details
    override_data = json.loads(override_message)
    assert override_data["type"] == "lock_overridden"
    assert override_data["cell_id"] == "cell1"
    assert override_data["user_id"] == admin.user_id
    assert override_data["previous_owner_id"] == user1.user_id
    
    # Now test admin force release
    # Admin acquires a lock on cell2
    await admin.send({
        "type": "acquire_lock",
        "cell_id": "cell2",
        "user_id": admin.user_id,
        "user_name": "Admin User"
    })
    
    # Wait for lock acquisition confirmation
    await admin.wait_for_message_containing("lock_acquired")
    
    # Admin force releases the lock without acquiring it
    await admin.send({
        "type": "admin_force_release",
        "cell_id": "cell2",
        "user_id": admin.user_id
    })
    
    # Wait for force release confirmation
    force_release_message = await admin.wait_for_message_containing("lock_force_released")
    assert force_release_message is not None
    
    # Parse the message to verify details
    release_data = json.loads(force_release_message)
    assert release_data["type"] == "lock_force_released"
    assert release_data["cell_id"] == "cell2"
    
    # Test that non-admin users cannot override locks
    # User 1 acquires a lock on cell3
    await user1.send({
        "type": "acquire_lock",
        "cell_id": "cell3",
        "user_id": user1.user_id,
        "user_name": "User 1"
    })
    
    # Wait for lock acquisition confirmation
    await user1.wait_for_message_containing("lock_acquired")
    
    # User 2 (non-admin) attempts to override the lock
    await user2.send({
        "type": "admin_override_lock",
        "cell_id": "cell3",
        "user_id": user2.user_id,
        "user_name": "User 2"
    })
    
    # Wait for error message
    error_message = await user2.wait_for_message_containing("error")
    assert error_message is not None
    
    # Parse the error message to verify details
    error_data = json.loads(error_message)
    assert error_data["type"] == "error"
    assert "permission" in error_data["message"].lower() or "admin" in error_data["message"].lower()


@pytest.mark.asyncio
async def test_lock_visualization(jp_ws_client, create_collaborative_session):
    """Test lock visualization and indication to other users."""
    # Create a collaborative session with 3 clients
    doc_path, clients = await create_collaborative_session(num_clients=3)
    user1, user2, user3 = clients
    
    # Clear any existing messages
    for client in clients:
        client.clear_received_messages()
    
    # User 1 acquires a lock on cell1
    await user1.send({
        "type": "acquire_lock",
        "cell_id": "cell1",
        "user_id": user1.user_id,
        "user_name": "User 1",
        "user_color": "#ff0000",  # Red color for visualization
        "user_avatar": "https://example.com/avatar1.png"
    })
    
    # Wait for lock acquisition confirmation
    await user1.wait_for_message_containing("lock_acquired")
    
    # User 2 acquires a lock on cell2
    await user2.send({
        "type": "acquire_lock",
        "cell_id": "cell2",
        "user_id": user2.user_id,
        "user_name": "User 2",
        "user_color": "#00ff00",  # Green color for visualization
        "user_avatar": "https://example.com/avatar2.png"
    })
    
    # Wait for lock acquisition confirmation
    await user2.wait_for_message_containing("lock_acquired")
    
    # User 3 requests all lock statuses for visualization
    await user3.send({
        "type": "get_all_locks",
        "user_id": user3.user_id
    })
    
    # Wait for lock status response
    locks_message = await user3.wait_for_message_containing("all_locks")
    assert locks_message is not None
    
    # Parse the message to verify details
    locks_data = json.loads(locks_message)
    assert locks_data["type"] == "all_locks"
    assert "locks" in locks_data
    assert len(locks_data["locks"]) == 2  # Should have 2 locks
    
    # Verify lock details for visualization
    cell1_lock = None
    cell2_lock = None
    for lock in locks_data["locks"]:
        if lock["cell_id"] == "cell1":
            cell1_lock = lock
        elif lock["cell_id"] == "cell2":
            cell2_lock = lock
    
    assert cell1_lock is not None
    assert cell2_lock is not None
    
    # Verify user 1's lock visualization data
    assert cell1_lock["user_id"] == user1.user_id
    assert cell1_lock["user_name"] == "User 1"
    assert cell1_lock["user_color"] == "#ff0000"
    assert cell1_lock["user_avatar"] == "https://example.com/avatar1.png"
    
    # Verify user 2's lock visualization data
    assert cell2_lock["user_id"] == user2.user_id
    assert cell2_lock["user_name"] == "User 2"
    assert cell2_lock["user_color"] == "#00ff00"
    assert cell2_lock["user_avatar"] == "https://example.com/avatar2.png"
    
    # Test lock status for a specific cell
    await user3.send({
        "type": "get_lock_status",
        "cell_id": "cell1",
        "user_id": user3.user_id
    })
    
    # Wait for lock status response
    status_message = await user3.wait_for_message_containing("lock_status")
    assert status_message is not None
    
    # Parse the message to verify details
    status_data = json.loads(status_message)
    assert status_data["type"] == "lock_status"
    assert status_data["cell_id"] == "cell1"
    assert status_data["locked"] is True
    assert status_data["owner_id"] == user1.user_id
    assert status_data["owner_name"] == "User 1"
    assert status_data["owner_color"] == "#ff0000"
    assert status_data["owner_avatar"] == "https://example.com/avatar1.png"
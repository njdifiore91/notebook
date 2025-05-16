import asyncio
import json
import pytest
import time

# Import helper functions from conftest
from tests.integration.collab.conftest import (
    send_message, send_lock_request, read_next_message, 
    wait_for_message, wait_for_lock_message
)

@pytest.mark.asyncio
async def test_lock_acquisition_and_release(jp_collab_clients):
    """Test that a user can acquire and release a lock on a cell."""
    # Get the clients
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell_id = "cell1"
    
    # User1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    
    # Wait for the lock state message on user1's client
    lock_message = await wait_for_lock_message(user1_client, cell_id)
    assert lock_message["type"] == "lock_state"
    assert lock_message["cellId"] == cell_id
    assert lock_message["locked"] is True
    assert lock_message["owner"] == "user1"
    
    # User2 should also receive the lock state message
    lock_message = await wait_for_lock_message(user2_client, cell_id)
    assert lock_message["type"] == "lock_state"
    assert lock_message["cellId"] == cell_id
    assert lock_message["locked"] is True
    assert lock_message["owner"] == "user1"
    
    # User1 releases the lock
    await send_lock_request(user1_client, "release", cell_id)
    
    # Wait for the lock release message on user1's client
    lock_message = await wait_for_lock_message(user1_client, cell_id)
    assert lock_message["type"] == "lock_state"
    assert lock_message["cellId"] == cell_id
    assert lock_message["locked"] is False
    assert lock_message["owner"] is None
    
    # User2 should also receive the lock release message
    lock_message = await wait_for_lock_message(user2_client, cell_id)
    assert lock_message["type"] == "lock_state"
    assert lock_message["cellId"] == cell_id
    assert lock_message["locked"] is False
    assert lock_message["owner"] is None

@pytest.mark.asyncio
async def test_lock_conflict_resolution(jp_collab_clients):
    """Test that a lock cannot be acquired if another user already has it."""
    # Get the clients
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell_id = "cell1"
    
    # User1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    
    # Wait for the lock state message
    lock_message = await wait_for_lock_message(user1_client, cell_id)
    assert lock_message["locked"] is True
    assert lock_message["owner"] == "user1"
    
    # User2 attempts to acquire the same lock
    await send_lock_request(user2_client, "acquire", cell_id)
    
    # Wait for the lock conflict message on user2's client
    conflict_message = await wait_for_message(user2_client, "lock_conflict")
    assert conflict_message["type"] == "lock_conflict"
    assert conflict_message["cellId"] == cell_id
    assert conflict_message["currentOwner"] == "user1"
    
    # Verify the lock is still owned by user1
    # Send a query to check the current lock state
    await send_message(user2_client, "query_locks")
    
    # Wait for the response and check that user1 still owns the lock
    locks_message = await wait_for_message(user2_client, "locks_state")
    assert cell_id in locks_message["locks"]
    assert locks_message["locks"][cell_id]["owner"] == "user1"
    
    # Clean up: User1 releases the lock
    await send_lock_request(user1_client, "release", cell_id)
    await wait_for_lock_message(user1_client, cell_id)

@pytest.mark.asyncio
async def test_concurrent_editing_different_cells(jp_collab_clients):
    """Test that different users can lock different cells concurrently."""
    # Get the clients
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell1_id = "cell1"
    cell2_id = "cell2"
    
    # User1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell1_id)
    lock_message = await wait_for_lock_message(user1_client, cell1_id)
    assert lock_message["locked"] is True
    assert lock_message["owner"] == "user1"
    
    # User2 acquires a lock on cell2
    await send_lock_request(user2_client, "acquire", cell2_id)
    lock_message = await wait_for_lock_message(user2_client, cell2_id)
    assert lock_message["locked"] is True
    assert lock_message["owner"] == "user2"
    
    # Verify both locks are active by querying the lock state
    await send_message(user1_client, "query_locks")
    locks_message = await wait_for_message(user1_client, "locks_state")
    
    assert cell1_id in locks_message["locks"]
    assert locks_message["locks"][cell1_id]["owner"] == "user1"
    assert cell2_id in locks_message["locks"]
    assert locks_message["locks"][cell2_id]["owner"] == "user2"
    
    # Clean up: Both users release their locks
    await send_lock_request(user1_client, "release", cell1_id)
    await send_lock_request(user2_client, "release", cell2_id)
    await wait_for_lock_message(user1_client, cell1_id)
    await wait_for_lock_message(user2_client, cell2_id)

@pytest.mark.asyncio
async def test_lock_timeout_and_automatic_release(jp_collab_server, jp_collab_clients):
    """Test that locks are automatically released after a timeout period."""
    # Get the client
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell_id = "cell1"
    
    # Set a short timeout for testing
    original_timeout = jp_collab_server.collaboration_lock_timeout
    jp_collab_server.collaboration_lock_timeout = 1.0  # 1 second timeout
    
    try:
        # User1 acquires a lock on cell1
        await send_lock_request(user1_client, "acquire", cell_id)
        lock_message = await wait_for_lock_message(user1_client, cell_id)
        assert lock_message["locked"] is True
        assert lock_message["owner"] == "user1"
        
        # Wait for the lock to timeout (slightly longer than the timeout)
        await asyncio.sleep(1.5)
        
        # Verify the lock was automatically released
        # Send a query to check the current lock state
        await send_message(user2_client, "query_locks")
        locks_message = await wait_for_message(user2_client, "locks_state")
        
        # The lock should no longer be present or should be marked as unlocked
        if cell_id in locks_message["locks"]:
            assert locks_message["locks"][cell_id]["locked"] is False
        else:
            # If the lock was completely removed, this is also acceptable
            pass
        
        # User2 should now be able to acquire the lock
        await send_lock_request(user2_client, "acquire", cell_id)
        lock_message = await wait_for_lock_message(user2_client, cell_id)
        assert lock_message["locked"] is True
        assert lock_message["owner"] == "user2"
        
        # Clean up: User2 releases the lock
        await send_lock_request(user2_client, "release", cell_id)
        await wait_for_lock_message(user2_client, cell_id)
        
    finally:
        # Restore the original timeout
        jp_collab_server.collaboration_lock_timeout = original_timeout

@pytest.mark.asyncio
async def test_lock_refresh_prevents_timeout(jp_collab_server, jp_collab_clients):
    """Test that refreshing a lock prevents it from timing out."""
    # Get the client
    user1_client = jp_collab_clients["user1"]
    cell_id = "cell1"
    
    # Set a short timeout for testing
    original_timeout = jp_collab_server.collaboration_lock_timeout
    jp_collab_server.collaboration_lock_timeout = 1.0  # 1 second timeout
    
    try:
        # User1 acquires a lock on cell1
        await send_lock_request(user1_client, "acquire", cell_id)
        lock_message = await wait_for_lock_message(user1_client, cell_id)
        assert lock_message["locked"] is True
        
        # Wait a bit, but less than the timeout
        await asyncio.sleep(0.5)
        
        # Refresh the lock
        await send_message(user1_client, "refresh_lock", cellId=cell_id)
        
        # Wait for a period that would exceed the original timeout
        await asyncio.sleep(0.8)  # Total time is now 1.3s, which is > 1.0s timeout
        
        # Verify the lock is still active
        await send_message(user1_client, "query_locks")
        locks_message = await wait_for_message(user1_client, "locks_state")
        
        assert cell_id in locks_message["locks"]
        assert locks_message["locks"][cell_id]["locked"] is True
        assert locks_message["locks"][cell_id]["owner"] == "user1"
        
        # Clean up: Release the lock
        await send_lock_request(user1_client, "release", cell_id)
        await wait_for_lock_message(user1_client, cell_id)
        
    finally:
        # Restore the original timeout
        jp_collab_server.collaboration_lock_timeout = original_timeout

@pytest.mark.asyncio
async def test_admin_override_of_locks(jp_collab_clients):
    """Test that an admin can override a lock owned by another user."""
    # Get the clients
    user1_client = jp_collab_clients["user1"]
    admin_client = jp_collab_clients["admin"]
    cell_id = "cell1"
    
    # User1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    lock_message = await wait_for_lock_message(user1_client, cell_id)
    assert lock_message["locked"] is True
    assert lock_message["owner"] == "user1"
    
    # Admin overrides the lock
    await send_message(admin_client, "admin_override_lock", cellId=cell_id)
    
    # Wait for the lock release message
    lock_message = await wait_for_lock_message(admin_client, cell_id)
    assert lock_message["type"] == "lock_state"
    assert lock_message["cellId"] == cell_id
    assert lock_message["locked"] is False
    
    # User1 should also receive the lock release message
    lock_message = await wait_for_lock_message(user1_client, cell_id)
    assert lock_message["type"] == "lock_state"
    assert lock_message["cellId"] == cell_id
    assert lock_message["locked"] is False
    
    # Verify the lock is released by having user1 acquire it again
    await send_lock_request(user1_client, "acquire", cell_id)
    lock_message = await wait_for_lock_message(user1_client, cell_id)
    assert lock_message["locked"] is True
    assert lock_message["owner"] == "user1"
    
    # Clean up: User1 releases the lock
    await send_lock_request(user1_client, "release", cell_id)
    await wait_for_lock_message(user1_client, cell_id)

@pytest.mark.asyncio
async def test_non_admin_cannot_override_lock(jp_collab_clients):
    """Test that a non-admin user cannot override a lock owned by another user."""
    # Get the clients
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]  # Not an admin
    cell_id = "cell1"
    
    # User1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    lock_message = await wait_for_lock_message(user1_client, cell_id)
    assert lock_message["locked"] is True
    assert lock_message["owner"] == "user1"
    
    # User2 attempts to override the lock
    await send_message(user2_client, "admin_override_lock", cellId=cell_id)
    
    # Wait for the permission denied message
    permission_message = await wait_for_message(user2_client, "permission_denied")
    assert permission_message["type"] == "permission_denied"
    assert permission_message["action"] == "admin_override_lock"
    
    # Verify the lock is still owned by user1
    await send_message(user2_client, "query_locks")
    locks_message = await wait_for_message(user2_client, "locks_state")
    assert cell_id in locks_message["locks"]
    assert locks_message["locks"][cell_id]["owner"] == "user1"
    
    # Clean up: User1 releases the lock
    await send_lock_request(user1_client, "release", cell_id)
    await wait_for_lock_message(user1_client, cell_id)

@pytest.mark.asyncio
async def test_lock_visualization_across_clients(jp_collab_clients):
    """Test that lock state changes are properly visualized across all clients."""
    # Get the clients
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    admin_client = jp_collab_clients["admin"]
    cell_id = "cell1"
    
    # User1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    
    # All clients should receive the lock state message
    for client in [user1_client, user2_client, admin_client]:
        lock_message = await wait_for_lock_message(client, cell_id)
        assert lock_message["type"] == "lock_state"
        assert lock_message["cellId"] == cell_id
        assert lock_message["locked"] is True
        assert lock_message["owner"] == "user1"
    
    # User1 releases the lock
    await send_lock_request(user1_client, "release", cell_id)
    
    # All clients should receive the lock release message
    for client in [user1_client, user2_client, admin_client]:
        lock_message = await wait_for_lock_message(client, cell_id)
        assert lock_message["type"] == "lock_state"
        assert lock_message["cellId"] == cell_id
        assert lock_message["locked"] is False
        assert lock_message["owner"] is None

@pytest.mark.asyncio
async def test_edit_prevention_for_locked_cells(jp_collab_clients):
    """Test that users cannot edit cells that are locked by other users."""
    # Get the clients
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell_id = "cell1"
    
    # User1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    await wait_for_lock_message(user1_client, cell_id)
    
    # User1 can edit the cell
    edit_message = {
        "type": "cell_edit",
        "cellId": cell_id,
        "content": "print('Edited by user1')"
    }
    await send_message(user1_client, "cell_edit", **edit_message)
    
    # Wait for the edit confirmation
    edit_confirm = await wait_for_message(user1_client, "edit_confirmed")
    assert edit_confirm["cellId"] == cell_id
    
    # User2 attempts to edit the same cell
    edit_message = {
        "type": "cell_edit",
        "cellId": cell_id,
        "content": "print('Attempted edit by user2')"
    }
    await send_message(user2_client, "cell_edit", **edit_message)
    
    # Wait for the edit rejection message
    edit_reject = await wait_for_message(user2_client, "edit_rejected")
    assert edit_reject["cellId"] == cell_id
    assert edit_reject["reason"] == "cell_locked"
    assert edit_reject["owner"] == "user1"
    
    # Clean up: User1 releases the lock
    await send_lock_request(user1_client, "release", cell_id)
    await wait_for_lock_message(user1_client, cell_id)

@pytest.mark.asyncio
async def test_lock_release_on_disconnection(jp_collab_server, jp_collab_clients, jp_ws_fetch, test_notebook_path):
    """Test that locks are released when a user disconnects."""
    # Get the clients
    user1_client = jp_collab_clients["user1"]
    user2_client = jp_collab_clients["user2"]
    cell_id = "cell1"
    
    # User1 acquires a lock on cell1
    await send_lock_request(user1_client, "acquire", cell_id)
    await wait_for_lock_message(user1_client, cell_id)
    
    # Verify the lock is active
    await send_message(user2_client, "query_locks")
    locks_message = await wait_for_message(user2_client, "locks_state")
    assert cell_id in locks_message["locks"]
    assert locks_message["locks"][cell_id]["owner"] == "user1"
    
    # Simulate user1 disconnecting by closing the WebSocket
    await user1_client.close()
    
    # Wait a bit for the server to process the disconnection
    await asyncio.sleep(0.5)
    
    # Verify the lock was released
    await send_message(user2_client, "query_locks")
    locks_message = await wait_for_message(user2_client, "locks_state")
    
    # The lock should either be removed or marked as unlocked
    if cell_id in locks_message["locks"]:
        assert locks_message["locks"][cell_id]["locked"] is False
    else:
        # If the lock was completely removed, this is also acceptable
        pass
    
    # User2 should now be able to acquire the lock
    await send_lock_request(user2_client, "acquire", cell_id)
    lock_message = await wait_for_lock_message(user2_client, cell_id)
    assert lock_message["locked"] is True
    assert lock_message["owner"] == "user2"
    
    # Clean up: User2 releases the lock
    await send_lock_request(user2_client, "release", cell_id)
    await wait_for_lock_message(user2_client, cell_id)
    
    # Reconnect user1 for other tests
    jp_collab_clients["user1"] = await jp_ws_fetch(
        "api", "collaboration", "documents", test_notebook_path,
        headers={"X-Jupyter-User-Id": "user1"}
    )
    jp_collab_clients["user1"].user_id = "user1"
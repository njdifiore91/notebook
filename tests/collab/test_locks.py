import asyncio
import json
import pytest
import time
from unittest.mock import MagicMock, patch

# Import the necessary modules for testing
from tornado.websocket import WebSocketClientConnection
from tornado import gen

# Mock classes and fixtures for testing the lock mechanism

@pytest.fixture
def mock_yjs_shared_map():
    """Create a mock Yjs shared map for testing."""
    # This simulates the Yjs shared map that stores lock information
    mock_map = MagicMock()
    # Store the lock data in a dictionary for easy testing
    mock_map.data = {}
    
    # Mock the get method to retrieve from the data dictionary
    def mock_get(key, txn=None):
        return mock_map.data.get(key)
    mock_map.get = mock_get
    
    # Mock the set method to store in the data dictionary
    def mock_set(key, value, txn=None):
        mock_map.data[key] = value
    mock_map.set = mock_set
    
    # Mock the delete method to remove from the data dictionary
    def mock_delete(key, txn=None):
        if key in mock_map.data:
            del mock_map.data[key]
    mock_map.delete = mock_delete
    
    # Mock the keys method to return all keys in the data dictionary
    def mock_keys():
        return list(mock_map.data.keys())
    mock_map.keys = mock_keys
    
    return mock_map

@pytest.fixture
def mock_yjs_doc(mock_yjs_shared_map):
    """Create a mock Yjs document for testing."""
    mock_doc = MagicMock()
    
    # Mock the get_map method to return our mock shared map
    def mock_get_map(name):
        if name == "cell_locks":
            return mock_yjs_shared_map
        return MagicMock()
    mock_doc.get_map = mock_get_map
    
    # Mock the transaction method to execute the callback with a transaction object
    def mock_transaction(callback):
        mock_txn = MagicMock()
        callback(mock_txn)
    mock_doc.transaction = mock_transaction
    
    # Mock the on_update method to register update callbacks
    mock_doc.update_callbacks = []
    def mock_on_update(callback):
        mock_doc.update_callbacks.append(callback)
        # Return a function to unregister the callback
        return lambda: mock_doc.update_callbacks.remove(callback)
    mock_doc.on_update = mock_on_update
    
    # Method to simulate an update event
    def mock_emit_update(update_data):
        for callback in mock_doc.update_callbacks:
            callback(update_data)
    mock_doc.emit_update = mock_emit_update
    
    return mock_doc

@pytest.fixture
def mock_lock_manager(mock_yjs_doc):
    """Create a mock CellLockManager for testing."""
    # Import here to avoid circular imports during test collection
    with patch('notebook.collab.locks.YDoc', return_value=mock_yjs_doc):
        # Import the CellLockManager class
        from notebook.collab.locks import CellLockManager
        
        # Create a lock manager with the mock Yjs document
        lock_manager = CellLockManager()
        
        # Set a short timeout for testing
        lock_manager.lock_timeout = 0.5  # 500ms timeout
        
        # Mock the broadcast method to track calls
        lock_manager._broadcast_lock_state = MagicMock()
        
        yield lock_manager

@pytest.fixture
def mock_users():
    """Create mock users for testing collaborative features."""
    return {
        'user1': {'id': 'user1', 'name': 'User One', 'color': '#ff0000'},
        'user2': {'id': 'user2', 'name': 'User Two', 'color': '#00ff00'},
        'admin': {'id': 'admin', 'name': 'Admin User', 'color': '#0000ff', 'is_admin': True}
    }

@pytest.fixture
def mock_cells():
    """Create mock cells for testing locks."""
    return {
        'cell1': {'id': 'cell1', 'type': 'code'},
        'cell2': {'id': 'cell2', 'type': 'markdown'},
        'cell3': {'id': 'cell3', 'type': 'code'}
    }

@pytest.fixture
def mock_websocket_clients(mock_users):
    """Create mock WebSocket clients for each user."""
    clients = {}
    for user_id, user_info in mock_users.items():
        client = MagicMock(spec=WebSocketClientConnection)
        client.user_id = user_id
        client.user_info = user_info
        clients[user_id] = client
    return clients

# Test cases for the cell locking mechanism

@pytest.mark.asyncio
async def test_lock_acquisition(mock_lock_manager, mock_users, mock_cells):
    """Test that a user can acquire a lock on a cell."""
    user_id = 'user1'
    cell_id = 'cell1'
    
    # Acquire the lock
    result = await mock_lock_manager.acquire_lock(user_id, cell_id)
    
    # Verify the lock was acquired
    assert result is True
    assert mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) == user_id
    
    # Verify the lock data in the Yjs shared map
    lock_data = mock_lock_manager._locks_map.get(cell_id)
    assert lock_data is not None
    assert isinstance(lock_data, dict)
    assert lock_data.get('owner') == user_id
    assert lock_data.get('locked') is True
    assert 'timestamp' in lock_data

@pytest.mark.asyncio
async def test_lock_release(mock_lock_manager, mock_users, mock_cells):
    """Test that a user can release a lock they own."""
    user_id = 'user1'
    cell_id = 'cell1'
    
    # First acquire the lock
    await mock_lock_manager.acquire_lock(user_id, cell_id)
    assert mock_lock_manager.is_cell_locked(cell_id)
    
    # Then release it
    result = await mock_lock_manager.release_lock(user_id, cell_id)
    
    # Verify the lock was released
    assert result is True
    assert not mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) is None
    
    # Verify the lock was removed from the Yjs shared map
    lock_data = mock_lock_manager._locks_map.get(cell_id)
    assert lock_data is None

@pytest.mark.asyncio
async def test_lock_conflict_resolution(mock_lock_manager, mock_users, mock_cells):
    """Test that a lock cannot be acquired if another user already has it."""
    user1_id = 'user1'
    user2_id = 'user2'
    cell_id = 'cell1'
    
    # User 1 acquires the lock
    await mock_lock_manager.acquire_lock(user1_id, cell_id)
    assert mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) == user1_id
    
    # User 2 attempts to acquire the same lock
    result = await mock_lock_manager.acquire_lock(user2_id, cell_id)
    
    # Verify that User 2's attempt was rejected
    assert result is False
    assert mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) == user1_id
    
    # Verify the lock data in the Yjs shared map still shows User 1 as owner
    lock_data = mock_lock_manager._locks_map.get(cell_id)
    assert lock_data is not None
    assert lock_data.get('owner') == user1_id

@pytest.mark.asyncio
async def test_lock_visualization(mock_lock_manager, mock_websocket_clients, mock_cells):
    """Test that lock state changes are broadcast to all clients."""
    user_id = 'user1'
    cell_id = 'cell1'
    
    # Acquire the lock
    await mock_lock_manager.acquire_lock(user_id, cell_id)
    
    # Verify that the lock state was broadcast
    mock_lock_manager._broadcast_lock_state.assert_called_with(cell_id, user_id, True)
    
    # Reset the mock to check the next call
    mock_lock_manager._broadcast_lock_state.reset_mock()
    
    # Release the lock
    await mock_lock_manager.release_lock(user_id, cell_id)
    
    # Verify that the lock release was broadcast
    mock_lock_manager._broadcast_lock_state.assert_called_with(cell_id, None, False)

@pytest.mark.asyncio
async def test_automatic_lock_release_timeout(mock_lock_manager, mock_users, mock_cells):
    """Test that locks are automatically released after a timeout period."""
    user_id = 'user1'
    cell_id = 'cell1'
    
    # Set a short timeout for testing
    mock_lock_manager.lock_timeout = 0.1  # 100ms timeout
    
    # Acquire the lock
    await mock_lock_manager.acquire_lock(user_id, cell_id)
    assert mock_lock_manager.is_cell_locked(cell_id)
    
    # Wait for the timeout to expire
    await asyncio.sleep(0.2)  # Wait longer than the timeout
    
    # Verify the lock was automatically released
    assert not mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) is None
    
    # Verify the lock was removed from the Yjs shared map
    lock_data = mock_lock_manager._locks_map.get(cell_id)
    assert lock_data is None

@pytest.mark.asyncio
async def test_lock_release_on_disconnection(mock_lock_manager, mock_users, mock_cells):
    """Test that locks are released when a user disconnects."""
    user_id = 'user1'
    cell_id = 'cell1'
    
    # Acquire the lock
    await mock_lock_manager.acquire_lock(user_id, cell_id)
    assert mock_lock_manager.is_cell_locked(cell_id)
    
    # Simulate user disconnection
    await mock_lock_manager.handle_user_disconnect(user_id)
    
    # Verify the lock was released
    assert not mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) is None
    
    # Verify the lock was removed from the Yjs shared map
    lock_data = mock_lock_manager._locks_map.get(cell_id)
    assert lock_data is None

@pytest.mark.asyncio
async def test_admin_lock_override(mock_lock_manager, mock_users, mock_cells):
    """Test that an admin can override a lock owned by another user."""
    user_id = 'user1'
    admin_id = 'admin'
    cell_id = 'cell1'
    
    # User acquires the lock
    await mock_lock_manager.acquire_lock(user_id, cell_id)
    assert mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) == user_id
    
    # Admin overrides the lock
    result = await mock_lock_manager.admin_override_lock(admin_id, cell_id)
    
    # Verify the lock was overridden
    assert result is True
    assert not mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) is None
    
    # Verify the lock was removed from the Yjs shared map
    lock_data = mock_lock_manager._locks_map.get(cell_id)
    assert lock_data is None
    
    # Verify that the override was broadcast
    mock_lock_manager._broadcast_lock_state.assert_called_with(
        cell_id, None, False, message="Lock overridden by admin"
    )

@pytest.mark.asyncio
async def test_non_admin_cannot_override_lock(mock_lock_manager, mock_users, mock_cells):
    """Test that a non-admin user cannot override a lock owned by another user."""
    user1_id = 'user1'
    user2_id = 'user2'  # Not an admin
    cell_id = 'cell1'
    
    # User 1 acquires the lock
    await mock_lock_manager.acquire_lock(user1_id, cell_id)
    assert mock_lock_manager.is_cell_locked(cell_id)
    
    # User 2 attempts to override the lock
    result = await mock_lock_manager.admin_override_lock(user2_id, cell_id)
    
    # Verify the override attempt was rejected
    assert result is False
    assert mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) == user1_id
    
    # Verify the lock data in the Yjs shared map still shows User 1 as owner
    lock_data = mock_lock_manager._locks_map.get(cell_id)
    assert lock_data is not None
    assert lock_data.get('owner') == user1_id

@pytest.mark.asyncio
async def test_multiple_locks_by_same_user(mock_lock_manager, mock_users, mock_cells):
    """Test that a user can acquire locks on multiple cells."""
    user_id = 'user1'
    cell1_id = 'cell1'
    cell2_id = 'cell2'
    
    # Acquire locks on two different cells
    await mock_lock_manager.acquire_lock(user_id, cell1_id)
    await mock_lock_manager.acquire_lock(user_id, cell2_id)
    
    # Verify both locks were acquired
    assert mock_lock_manager.is_cell_locked(cell1_id)
    assert mock_lock_manager.is_cell_locked(cell2_id)
    assert mock_lock_manager.get_lock_owner(cell1_id) == user_id
    assert mock_lock_manager.get_lock_owner(cell2_id) == user_id
    
    # Verify the lock data in the Yjs shared map for both cells
    lock_data1 = mock_lock_manager._locks_map.get(cell1_id)
    lock_data2 = mock_lock_manager._locks_map.get(cell2_id)
    assert lock_data1 is not None and lock_data1.get('owner') == user_id
    assert lock_data2 is not None and lock_data2.get('owner') == user_id

@pytest.mark.asyncio
async def test_concurrent_editing_different_cells(mock_lock_manager, mock_users, mock_cells):
    """Test that different users can lock different cells concurrently."""
    user1_id = 'user1'
    user2_id = 'user2'
    cell1_id = 'cell1'
    cell2_id = 'cell2'
    
    # User 1 locks cell 1
    await mock_lock_manager.acquire_lock(user1_id, cell1_id)
    assert mock_lock_manager.is_cell_locked(cell1_id)
    assert mock_lock_manager.get_lock_owner(cell1_id) == user1_id
    
    # User 2 locks cell 2
    await mock_lock_manager.acquire_lock(user2_id, cell2_id)
    assert mock_lock_manager.is_cell_locked(cell2_id)
    assert mock_lock_manager.get_lock_owner(cell2_id) == user2_id
    
    # Verify both locks are maintained
    assert mock_lock_manager.is_cell_locked(cell1_id)
    assert mock_lock_manager.get_lock_owner(cell1_id) == user1_id
    assert mock_lock_manager.is_cell_locked(cell2_id)
    assert mock_lock_manager.get_lock_owner(cell2_id) == user2_id
    
    # Verify the lock data in the Yjs shared map for both cells
    lock_data1 = mock_lock_manager._locks_map.get(cell1_id)
    lock_data2 = mock_lock_manager._locks_map.get(cell2_id)
    assert lock_data1 is not None and lock_data1.get('owner') == user1_id
    assert lock_data2 is not None and lock_data2.get('owner') == user2_id

@pytest.mark.asyncio
async def test_yjs_update_triggers_lock_check(mock_lock_manager, mock_yjs_doc, mock_users, mock_cells):
    """Test that Yjs update events trigger lock timeout checks."""
    user_id = 'user1'
    cell_id = 'cell1'
    
    # Set a short timeout for testing
    mock_lock_manager.lock_timeout = 0.1  # 100ms timeout
    
    # Acquire the lock
    await mock_lock_manager.acquire_lock(user_id, cell_id)
    assert mock_lock_manager.is_cell_locked(cell_id)
    
    # Modify the timestamp to make the lock appear expired
    lock_data = mock_lock_manager._locks_map.get(cell_id)
    lock_data['timestamp'] = time.time() - 1.0  # Set timestamp to 1 second ago
    mock_lock_manager._locks_map.set(cell_id, lock_data)
    
    # Simulate a Yjs update event
    mock_yjs_doc.emit_update({"type": "update"})
    
    # Wait a short time for the async lock check to complete
    await asyncio.sleep(0.05)
    
    # Verify the lock was automatically released due to timeout
    assert not mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) is None

@pytest.mark.asyncio
async def test_lock_query(mock_lock_manager, mock_users, mock_cells):
    """Test that the lock status can be queried."""
    user_id = 'user1'
    cell_id = 'cell1'
    
    # Initially, the cell should not be locked
    assert not mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) is None
    
    # Acquire the lock
    await mock_lock_manager.acquire_lock(user_id, cell_id)
    
    # Query the lock status
    assert mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) == user_id
    
    # Get all locked cells
    locked_cells = mock_lock_manager.get_all_locked_cells()
    assert cell_id in locked_cells
    assert locked_cells[cell_id] == user_id

@pytest.mark.asyncio
async def test_lock_refresh(mock_lock_manager, mock_users, mock_cells):
    """Test that a lock's timestamp can be refreshed to prevent timeout."""
    user_id = 'user1'
    cell_id = 'cell1'
    
    # Set a short timeout for testing
    mock_lock_manager.lock_timeout = 0.2  # 200ms timeout
    
    # Acquire the lock
    await mock_lock_manager.acquire_lock(user_id, cell_id)
    assert mock_lock_manager.is_cell_locked(cell_id)
    
    # Get the initial timestamp
    initial_lock_data = mock_lock_manager._locks_map.get(cell_id)
    initial_timestamp = initial_lock_data.get('timestamp')
    
    # Wait a bit, but less than the timeout
    await asyncio.sleep(0.1)
    
    # Refresh the lock
    result = await mock_lock_manager.refresh_lock(user_id, cell_id)
    assert result is True
    
    # Verify the lock is still active and the timestamp was updated
    assert mock_lock_manager.is_cell_locked(cell_id)
    updated_lock_data = mock_lock_manager._locks_map.get(cell_id)
    updated_timestamp = updated_lock_data.get('timestamp')
    assert updated_timestamp > initial_timestamp
    
    # Wait longer than the original timeout, but the lock should still be active
    # due to the refresh
    await asyncio.sleep(0.15)  # Total wait time is now 0.25s, which is > 0.2s timeout
    assert mock_lock_manager.is_cell_locked(cell_id)

@pytest.mark.asyncio
async def test_another_user_cannot_refresh_lock(mock_lock_manager, mock_users, mock_cells):
    """Test that a user cannot refresh a lock owned by another user."""
    user1_id = 'user1'
    user2_id = 'user2'
    cell_id = 'cell1'
    
    # User 1 acquires the lock
    await mock_lock_manager.acquire_lock(user1_id, cell_id)
    assert mock_lock_manager.is_cell_locked(cell_id)
    assert mock_lock_manager.get_lock_owner(cell_id) == user1_id
    
    # Get the initial timestamp
    initial_lock_data = mock_lock_manager._locks_map.get(cell_id)
    initial_timestamp = initial_lock_data.get('timestamp')
    
    # User 2 attempts to refresh the lock
    result = await mock_lock_manager.refresh_lock(user2_id, cell_id)
    assert result is False
    
    # Verify the lock data was not changed
    updated_lock_data = mock_lock_manager._locks_map.get(cell_id)
    updated_timestamp = updated_lock_data.get('timestamp')
    assert updated_timestamp == initial_timestamp

@pytest.mark.asyncio
async def test_lock_metadata(mock_lock_manager, mock_users, mock_cells):
    """Test that locks can store additional metadata."""
    user_id = 'user1'
    cell_id = 'cell1'
    metadata = {"editing_mode": "exclusive", "purpose": "code refactoring"}
    
    # Acquire the lock with metadata
    result = await mock_lock_manager.acquire_lock(user_id, cell_id, metadata=metadata)
    assert result is True
    
    # Verify the lock was acquired with metadata
    assert mock_lock_manager.is_cell_locked(cell_id)
    lock_data = mock_lock_manager._locks_map.get(cell_id)
    assert lock_data.get('metadata') == metadata
    
    # Verify we can retrieve the metadata
    retrieved_metadata = mock_lock_manager.get_lock_metadata(cell_id)
    assert retrieved_metadata == metadata
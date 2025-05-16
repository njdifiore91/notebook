import pytest
import asyncio
from unittest.mock import MagicMock, patch

# Import the necessary modules for testing the locking mechanism
from notebook.collab.locks import CellLockManager
from notebook.collab.exceptions import LockAcquisitionError


@pytest.fixture
def lock_manager():
    """Fixture to create a CellLockManager instance for testing."""
    manager = CellLockManager()
    return manager


@pytest.fixture
def mock_user1():
    """Fixture to create a mock user for testing."""
    return {
        "id": "user1",
        "name": "User One",
        "color": "#ff0000",
        "avatar": "https://example.com/avatar1.png"
    }


@pytest.fixture
def mock_user2():
    """Fixture to create another mock user for testing."""
    return {
        "id": "user2",
        "name": "User Two",
        "color": "#00ff00",
        "avatar": "https://example.com/avatar2.png"
    }


@pytest.fixture
def mock_admin_user():
    """Fixture to create a mock admin user for testing."""
    return {
        "id": "admin",
        "name": "Admin User",
        "color": "#0000ff",
        "avatar": "https://example.com/admin.png",
        "is_admin": True
    }


class TestCellLockAcquisitionAndRelease:
    """Test cases for acquiring and releasing cell locks."""

    def test_acquire_lock(self, lock_manager, mock_user1):
        """Test that a user can acquire a lock on a cell."""
        cell_id = "cell1"
        
        # Acquire the lock
        lock = lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # Verify the lock was acquired
        assert lock_manager.is_cell_locked(cell_id)
        assert lock_manager.get_lock_owner(cell_id) == mock_user1["id"]
        assert lock_manager.get_lock_metadata(cell_id)["user"] == mock_user1

    def test_release_lock(self, lock_manager, mock_user1):
        """Test that a user can release a lock they've acquired."""
        cell_id = "cell1"
        
        # Acquire the lock
        lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # Release the lock
        lock_manager.release_lock(cell_id, mock_user1["id"])
        
        # Verify the lock was released
        assert not lock_manager.is_cell_locked(cell_id)
        assert lock_manager.get_lock_owner(cell_id) is None

    def test_multiple_cell_locks(self, lock_manager, mock_user1):
        """Test that a user can lock multiple cells simultaneously."""
        cell_ids = ["cell1", "cell2", "cell3"]
        
        # Acquire locks on multiple cells
        for cell_id in cell_ids:
            lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # Verify all cells are locked by the user
        for cell_id in cell_ids:
            assert lock_manager.is_cell_locked(cell_id)
            assert lock_manager.get_lock_owner(cell_id) == mock_user1["id"]

    def test_different_users_different_cells(self, lock_manager, mock_user1, mock_user2):
        """Test that different users can lock different cells simultaneously."""
        # User 1 locks cell 1
        lock_manager.acquire_lock("cell1", mock_user1["id"], mock_user1)
        
        # User 2 locks cell 2
        lock_manager.acquire_lock("cell2", mock_user2["id"], mock_user2)
        
        # Verify each user has their respective lock
        assert lock_manager.get_lock_owner("cell1") == mock_user1["id"]
        assert lock_manager.get_lock_owner("cell2") == mock_user2["id"]


class TestLockVisualization:
    """Test cases for lock visualization and indication to other users."""

    def test_get_all_locks(self, lock_manager, mock_user1, mock_user2):
        """Test retrieving all active locks for UI visualization."""
        # Set up multiple locks
        lock_manager.acquire_lock("cell1", mock_user1["id"], mock_user1)
        lock_manager.acquire_lock("cell2", mock_user2["id"], mock_user2)
        
        # Get all locks
        all_locks = lock_manager.get_all_locks()
        
        # Verify the locks information is correct
        assert len(all_locks) == 2
        assert all_locks["cell1"]["user_id"] == mock_user1["id"]
        assert all_locks["cell2"]["user_id"] == mock_user2["id"]
        assert all_locks["cell1"]["user"] == mock_user1
        assert all_locks["cell2"]["user"] == mock_user2

    def test_lock_event_callbacks(self, lock_manager, mock_user1):
        """Test that lock events trigger callbacks for UI updates."""
        # Create mock callbacks
        on_lock_acquired = MagicMock()
        on_lock_released = MagicMock()
        
        # Register callbacks
        lock_manager.on_lock_acquired(on_lock_acquired)
        lock_manager.on_lock_released(on_lock_released)
        
        # Acquire and release a lock
        cell_id = "cell1"
        lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        lock_manager.release_lock(cell_id, mock_user1["id"])
        
        # Verify callbacks were called with correct arguments
        on_lock_acquired.assert_called_once_with(cell_id, mock_user1["id"], mock_user1)
        on_lock_released.assert_called_once_with(cell_id, mock_user1["id"])

    def test_lock_status_for_ui(self, lock_manager, mock_user1):
        """Test getting lock status information formatted for UI display."""
        cell_id = "cell1"
        lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # Get lock status for UI
        lock_status = lock_manager.get_lock_status_for_ui(cell_id)
        
        # Verify the status contains necessary information for UI display
        assert lock_status["locked"] is True
        assert lock_status["owner_id"] == mock_user1["id"]
        assert lock_status["owner_name"] == mock_user1["name"]
        assert lock_status["owner_color"] == mock_user1["color"]
        assert lock_status["owner_avatar"] == mock_user1["avatar"]
        assert "acquired_time" in lock_status
        assert "time_remaining" in lock_status


class TestLockConflictResolution:
    """Test cases for lock conflict resolution."""

    def test_lock_conflict(self, lock_manager, mock_user1, mock_user2):
        """Test that a conflict occurs when a second user tries to lock a cell."""
        cell_id = "cell1"
        
        # User 1 acquires the lock
        lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # User 2 attempts to acquire the same lock, which should fail
        with pytest.raises(LockAcquisitionError) as excinfo:
            lock_manager.acquire_lock(cell_id, mock_user2["id"], mock_user2)
        
        # Verify the error contains information about the current lock owner
        assert mock_user1["id"] in str(excinfo.value)
        
        # Verify the lock is still owned by User 1
        assert lock_manager.get_lock_owner(cell_id) == mock_user1["id"]

    def test_lock_request_queue(self, lock_manager, mock_user1, mock_user2):
        """Test that lock requests can be queued for later acquisition."""
        cell_id = "cell1"
        
        # User 1 acquires the lock
        lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # User 2 requests the lock (should be queued)
        request_id = lock_manager.request_lock(cell_id, mock_user2["id"], mock_user2)
        
        # Verify the request is in the queue
        assert lock_manager.is_lock_requested(cell_id, mock_user2["id"])
        assert request_id in lock_manager.get_lock_requests(cell_id)
        
        # User 1 releases the lock
        lock_manager.release_lock(cell_id, mock_user1["id"])
        
        # Verify User 2 now has the lock (automatic acquisition from queue)
        assert lock_manager.get_lock_owner(cell_id) == mock_user2["id"]

    def test_lock_request_notification(self, lock_manager, mock_user1, mock_user2):
        """Test that lock requests trigger notifications to the current owner."""
        cell_id = "cell1"
        
        # Create a mock notification callback
        on_lock_requested = MagicMock()
        lock_manager.on_lock_requested(on_lock_requested)
        
        # User 1 acquires the lock
        lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # User 2 requests the lock
        lock_manager.request_lock(cell_id, mock_user2["id"], mock_user2)
        
        # Verify the notification callback was called with correct arguments
        on_lock_requested.assert_called_once_with(
            cell_id, mock_user1["id"], mock_user2["id"], mock_user2
        )


class TestLockTimeoutAndAutoRelease:
    """Test cases for lock timeout and automatic release."""

    @pytest.mark.asyncio
    async def test_lock_timeout(self, lock_manager, mock_user1):
        """Test that locks are automatically released after timeout."""
        cell_id = "cell1"
        
        # Set a short timeout for testing
        with patch.object(lock_manager, 'lock_timeout_seconds', 0.1):
            # Acquire the lock
            lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
            
            # Verify the lock exists
            assert lock_manager.is_cell_locked(cell_id)
            
            # Wait for the timeout to expire
            await asyncio.sleep(0.2)
            
            # Verify the lock was automatically released
            assert not lock_manager.is_cell_locked(cell_id)

    def test_user_disconnection_releases_locks(self, lock_manager, mock_user1, mock_user2):
        """Test that all locks are released when a user disconnects."""
        # User 1 acquires multiple locks
        lock_manager.acquire_lock("cell1", mock_user1["id"], mock_user1)
        lock_manager.acquire_lock("cell2", mock_user1["id"], mock_user1)
        
        # User 2 acquires a lock
        lock_manager.acquire_lock("cell3", mock_user2["id"], mock_user2)
        
        # Simulate User 1 disconnecting
        lock_manager.release_all_user_locks(mock_user1["id"])
        
        # Verify User 1's locks are released but User 2's lock remains
        assert not lock_manager.is_cell_locked("cell1")
        assert not lock_manager.is_cell_locked("cell2")
        assert lock_manager.is_cell_locked("cell3")
        assert lock_manager.get_lock_owner("cell3") == mock_user2["id"]

    def test_lock_refresh(self, lock_manager, mock_user1):
        """Test that active locks can be refreshed to prevent timeout."""
        cell_id = "cell1"
        
        # Acquire the lock
        lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # Get the original acquisition time
        original_time = lock_manager.get_lock_metadata(cell_id)["acquired_time"]
        
        # Wait a moment
        import time
        time.sleep(0.1)
        
        # Refresh the lock
        lock_manager.refresh_lock(cell_id, mock_user1["id"])
        
        # Get the new acquisition time
        new_time = lock_manager.get_lock_metadata(cell_id)["acquired_time"]
        
        # Verify the lock was refreshed (new timestamp)
        assert new_time > original_time


class TestAdministrativeLockOverride:
    """Test cases for administrative override of locks."""

    def test_admin_override_lock(self, lock_manager, mock_user1, mock_admin_user):
        """Test that an admin can override a lock owned by another user."""
        cell_id = "cell1"
        
        # User 1 acquires the lock
        lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # Admin overrides the lock
        lock_manager.admin_override_lock(cell_id, mock_admin_user["id"], mock_admin_user)
        
        # Verify the admin now owns the lock
        assert lock_manager.get_lock_owner(cell_id) == mock_admin_user["id"]
        assert lock_manager.get_lock_metadata(cell_id)["user"] == mock_admin_user

    def test_admin_force_release(self, lock_manager, mock_user1, mock_admin_user):
        """Test that an admin can force-release a lock without acquiring it."""
        cell_id = "cell1"
        
        # User 1 acquires the lock
        lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # Admin force-releases the lock
        lock_manager.admin_force_release(cell_id, mock_admin_user["id"])
        
        # Verify the lock is released
        assert not lock_manager.is_cell_locked(cell_id)

    def test_admin_release_all_locks(self, lock_manager, mock_user1, mock_user2, mock_admin_user):
        """Test that an admin can release all locks in the document."""
        # Multiple users acquire locks on different cells
        lock_manager.acquire_lock("cell1", mock_user1["id"], mock_user1)
        lock_manager.acquire_lock("cell2", mock_user2["id"], mock_user2)
        
        # Admin releases all locks
        lock_manager.admin_release_all_locks(mock_admin_user["id"])
        
        # Verify all locks are released
        assert not lock_manager.is_cell_locked("cell1")
        assert not lock_manager.is_cell_locked("cell2")

    def test_non_admin_cannot_override(self, lock_manager, mock_user1, mock_user2):
        """Test that non-admin users cannot override locks."""
        cell_id = "cell1"
        
        # User 1 acquires the lock
        lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # User 2 attempts to override the lock, which should fail
        with pytest.raises(LockAcquisitionError):
            lock_manager.admin_override_lock(cell_id, mock_user2["id"], mock_user2)
        
        # Verify User 1 still owns the lock
        assert lock_manager.get_lock_owner(cell_id) == mock_user1["id"]

    def test_admin_lock_override_notification(self, lock_manager, mock_user1, mock_admin_user):
        """Test that lock overrides trigger notifications to the previous owner."""
        cell_id = "cell1"
        
        # Create a mock notification callback
        on_lock_overridden = MagicMock()
        lock_manager.on_lock_overridden(on_lock_overridden)
        
        # User 1 acquires the lock
        lock_manager.acquire_lock(cell_id, mock_user1["id"], mock_user1)
        
        # Admin overrides the lock
        lock_manager.admin_override_lock(cell_id, mock_admin_user["id"], mock_admin_user)
        
        # Verify the notification callback was called with correct arguments
        on_lock_overridden.assert_called_once_with(
            cell_id, mock_user1["id"], mock_admin_user["id"], mock_admin_user
        )
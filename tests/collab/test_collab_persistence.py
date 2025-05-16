import os
import uuid
import json
import time
import pytest
import sqlalchemy as sa
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from notebook.collab.persistence import (
    PersistenceManager, 
    CollaborationSession, 
    YjsUpdateRecord,
    PresenceRecord,
    CellLock,
    PermissionEntry,
    CommentThread,
    Comment,
    VersionSnapshot,
    Base
)

# Skip tests if collaboration dependencies are not installed
pytestmark = pytest.mark.skipif(
    not hasattr(pytest, "importorskip") or pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed"),
    reason="Collaboration dependencies not installed"
)


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    db_url = "sqlite:///:memory:"
    engine = sa.create_engine(db_url)
    Base.metadata.create_all(engine)
    return db_url


@pytest.fixture
def persistence_manager(in_memory_db):
    """Create a persistence manager with an in-memory database."""
    manager = PersistenceManager(db_url=in_memory_db, initialize_db=True)
    yield manager
    manager.close()


@pytest.fixture
def sample_document_id():
    """Generate a sample document ID."""
    return f"notebook-{uuid.uuid4()}.ipynb"


@pytest.fixture
def sample_user_id():
    """Generate a sample user ID."""
    return f"user-{uuid.uuid4()}"


@pytest.fixture
def sample_client_id():
    """Generate a sample client ID."""
    return f"client-{uuid.uuid4()}"


@pytest.fixture
def sample_update_data():
    """Generate sample Yjs update data."""
    return b"\x01\x02\x03\x04\x05"


@pytest.fixture
def sample_session(persistence_manager, sample_document_id, sample_user_id):
    """Create a sample collaboration session."""
    metadata = {
        "title": "Test Notebook",
        "description": "A test notebook for collaboration",
        "tags": ["test", "collaboration"]
    }
    session_id = persistence_manager.create_collaboration_session(
        document_id=sample_document_id,
        owner_id=sample_user_id,
        metadata=metadata
    )
    return session_id


class TestCollaborationSession:
    """Tests for collaboration session management."""

    def test_create_session(self, persistence_manager, sample_document_id, sample_user_id):
        """Test creating a new collaboration session."""
        metadata = {"title": "Test Session"}
        session_id = persistence_manager.create_collaboration_session(
            document_id=sample_document_id,
            owner_id=sample_user_id,
            metadata=metadata
        )
        
        assert session_id is not None
        assert uuid.UUID(session_id)
        
        # Verify session was created correctly
        session_info = persistence_manager.get_collaboration_session(session_id)
        assert session_info is not None
        assert session_info["document_id"] == sample_document_id
        assert session_info["owner_id"] == sample_user_id
        assert session_info["metadata"]["title"] == "Test Session"
        assert session_info["active"] is True
    
    def test_get_session(self, persistence_manager, sample_session):
        """Test retrieving a collaboration session."""
        session_info = persistence_manager.get_collaboration_session(sample_session)
        assert session_info is not None
        assert session_info["session_id"] == sample_session
        assert "created_at" in session_info
        assert "updated_at" in session_info
        assert "metadata" in session_info
        assert session_info["metadata"]["title"] == "Test Notebook"
    
    def test_get_nonexistent_session(self, persistence_manager):
        """Test retrieving a non-existent session."""
        nonexistent_id = str(uuid.uuid4())
        session_info = persistence_manager.get_collaboration_session(nonexistent_id)
        assert session_info is None
    
    def test_get_sessions_for_document(self, persistence_manager, sample_document_id, sample_user_id):
        """Test retrieving all sessions for a document."""
        # Create multiple sessions for the same document
        session_id1 = persistence_manager.create_collaboration_session(
            document_id=sample_document_id,
            owner_id=sample_user_id,
            metadata={"title": "Session 1"}
        )
        session_id2 = persistence_manager.create_collaboration_session(
            document_id=sample_document_id,
            owner_id=f"{sample_user_id}-2",
            metadata={"title": "Session 2"}
        )
        
        # Create a session for a different document
        different_doc_id = f"different-{uuid.uuid4()}.ipynb"
        persistence_manager.create_collaboration_session(
            document_id=different_doc_id,
            owner_id=sample_user_id,
            metadata={"title": "Different Document"}
        )
        
        # Get sessions for the sample document
        sessions = persistence_manager.get_collaboration_sessions_for_document(sample_document_id)
        assert len(sessions) == 2
        session_ids = [s["session_id"] for s in sessions]
        assert session_id1 in session_ids
        assert session_id2 in session_ids
    
    def test_update_session(self, persistence_manager, sample_session):
        """Test updating a collaboration session."""
        # Update metadata
        new_metadata = {"title": "Updated Title", "new_field": "new_value"}
        result = persistence_manager.update_collaboration_session(
            session_id=sample_session,
            metadata=new_metadata
        )
        assert result is True
        
        # Verify update
        session_info = persistence_manager.get_collaboration_session(sample_session)
        assert session_info["metadata"]["title"] == "Updated Title"
        assert session_info["metadata"]["new_field"] == "new_value"
        # Original metadata fields should still be present
        assert "description" in session_info["metadata"]
        
        # Update active status
        result = persistence_manager.update_collaboration_session(
            session_id=sample_session,
            active=False
        )
        assert result is True
        
        # Verify update
        session_info = persistence_manager.get_collaboration_session(sample_session)
        assert session_info["active"] is False
    
    def test_update_nonexistent_session(self, persistence_manager):
        """Test updating a non-existent session."""
        nonexistent_id = str(uuid.uuid4())
        result = persistence_manager.update_collaboration_session(
            session_id=nonexistent_id,
            metadata={"title": "This should fail"}
        )
        assert result is False


class TestYjsUpdates:
    """Tests for Yjs update storage and retrieval."""

    def test_store_update(self, persistence_manager, sample_session, sample_client_id, 
                         sample_user_id, sample_update_data):
        """Test storing a Yjs update."""
        metadata = {"cell_ids": ["cell-1", "cell-2"], "update_type": "content_change"}
        update_id = persistence_manager.store_update(
            session_id=sample_session,
            sequence_number=1,
            update_data=sample_update_data,
            client_id=sample_client_id,
            user_id=sample_user_id,
            metadata=metadata
        )
        
        assert update_id is not None
        assert uuid.UUID(update_id)
    
    def test_get_updates(self, persistence_manager, sample_session, sample_client_id, 
                        sample_user_id, sample_update_data):
        """Test retrieving Yjs updates."""
        # Store multiple updates
        for i in range(5):
            persistence_manager.store_update(
                session_id=sample_session,
                sequence_number=i+1,
                update_data=sample_update_data,
                client_id=sample_client_id,
                user_id=sample_user_id,
                metadata={"update_index": i}
            )
        
        # Get all updates
        updates = persistence_manager.get_updates(sample_session)
        assert len(updates) == 5
        
        # Verify sequence numbers and order
        for i, update in enumerate(updates):
            assert update["sequence_number"] == i+1
            assert update["update_data"] == sample_update_data
            assert update["client_id"] == sample_client_id
            assert update["user_id"] == sample_user_id
            assert update["metadata"]["update_index"] == i
    
    def test_get_updates_with_range(self, persistence_manager, sample_session, sample_client_id, 
                                   sample_user_id, sample_update_data):
        """Test retrieving Yjs updates with sequence range."""
        # Store multiple updates
        for i in range(10):
            persistence_manager.store_update(
                session_id=sample_session,
                sequence_number=i+1,
                update_data=sample_update_data,
                client_id=sample_client_id,
                user_id=sample_user_id,
                metadata={"update_index": i}
            )
        
        # Get updates with start sequence
        updates = persistence_manager.get_updates(sample_session, start_sequence=5)
        assert len(updates) == 6  # Sequences 5-10
        assert updates[0]["sequence_number"] == 5
        assert updates[-1]["sequence_number"] == 10
        
        # Get updates with end sequence
        updates = persistence_manager.get_updates(sample_session, end_sequence=3)
        assert len(updates) == 3  # Sequences 1-3
        assert updates[0]["sequence_number"] == 1
        assert updates[-1]["sequence_number"] == 3
        
        # Get updates with start and end sequence
        updates = persistence_manager.get_updates(sample_session, start_sequence=3, end_sequence=7)
        assert len(updates) == 5  # Sequences 3-7
        assert updates[0]["sequence_number"] == 3
        assert updates[-1]["sequence_number"] == 7
        
        # Get updates with limit
        updates = persistence_manager.get_updates(sample_session, limit=3)
        assert len(updates) == 3
        assert updates[0]["sequence_number"] == 1
        assert updates[-1]["sequence_number"] == 3
    
    def test_store_and_get_snapshot(self, persistence_manager, sample_session):
        """Test storing and retrieving a version snapshot."""
        state_vector = b"\x01\x02\x03"
        document_state = b"\x04\x05\x06\x07\x08"
        metadata = {"snapshot_reason": "scheduled", "cell_count": 5}
        
        snapshot_id = persistence_manager.store_snapshot(
            session_id=sample_session,
            sequence_number=10,
            state_vector=state_vector,
            document_state=document_state,
            metadata=metadata
        )
        
        assert snapshot_id is not None
        assert uuid.UUID(snapshot_id)
        
        # Get the latest snapshot
        snapshot = persistence_manager.get_latest_snapshot(sample_session)
        assert snapshot is not None
        assert snapshot["sequence_number"] == 10
        assert snapshot["state_vector"] == state_vector
        assert snapshot["document_state"] == document_state
        assert snapshot["metadata"]["snapshot_reason"] == "scheduled"
        assert snapshot["metadata"]["cell_count"] == 5
    
    def test_get_latest_snapshot_with_multiple_snapshots(self, persistence_manager, sample_session):
        """Test retrieving the latest snapshot when multiple exist."""
        # Store multiple snapshots with increasing sequence numbers
        for i in range(3):
            persistence_manager.store_snapshot(
                session_id=sample_session,
                sequence_number=(i+1)*10,
                state_vector=b"\x01\x02\x03",
                document_state=b"\x04\x05\x06",
                metadata={"snapshot_index": i}
            )
        
        # Get the latest snapshot
        snapshot = persistence_manager.get_latest_snapshot(sample_session)
        assert snapshot is not None
        assert snapshot["sequence_number"] == 30  # The highest sequence number
        assert snapshot["metadata"]["snapshot_index"] == 2  # The last snapshot


class TestPresenceTracking:
    """Tests for user presence tracking."""

    def test_update_presence(self, persistence_manager, sample_session, sample_user_id, sample_client_id):
        """Test updating user presence information."""
        cursor_position = {"cell_id": "cell-1", "line": 5, "column": 10}
        selection_range = {
            "cell_id": "cell-1", 
            "start_line": 5, 
            "start_column": 8, 
            "end_line": 5, 
            "end_column": 15
        }
        metadata = {"user_name": "Test User", "avatar": "avatar.png"}
        
        presence_id = persistence_manager.update_presence(
            session_id=sample_session,
            user_id=sample_user_id,
            client_id=sample_client_id,
            cursor_position=cursor_position,
            selection_range=selection_range,
            status="active",
            metadata=metadata
        )
        
        assert presence_id is not None
        assert uuid.UUID(presence_id)
    
    def test_get_presence(self, persistence_manager, sample_session):
        """Test retrieving presence information for all users in a session."""
        # Add presence for multiple users
        for i in range(3):
            user_id = f"user-{i}"
            client_id = f"client-{i}"
            persistence_manager.update_presence(
                session_id=sample_session,
                user_id=user_id,
                client_id=client_id,
                cursor_position={"cell_id": f"cell-{i}"},
                status="active",
                metadata={"user_index": i}
            )
        
        # Get all presence records
        presence_records = persistence_manager.get_presence(sample_session)
        assert len(presence_records) == 3
        
        # Verify user IDs
        user_ids = [p["user_id"] for p in presence_records]
        for i in range(3):
            assert f"user-{i}" in user_ids
    
    def test_update_existing_presence(self, persistence_manager, sample_session, 
                                     sample_user_id, sample_client_id):
        """Test updating an existing presence record."""
        # Create initial presence
        persistence_manager.update_presence(
            session_id=sample_session,
            user_id=sample_user_id,
            client_id=sample_client_id,
            cursor_position={"cell_id": "cell-1", "line": 1},
            status="active",
            metadata={"initial": True}
        )
        
        # Update the presence
        new_cursor = {"cell_id": "cell-2", "line": 5}
        new_status = "idle"
        new_metadata = {"updated": True}
        
        persistence_manager.update_presence(
            session_id=sample_session,
            user_id=sample_user_id,
            client_id=sample_client_id,
            cursor_position=new_cursor,
            status=new_status,
            metadata=new_metadata
        )
        
        # Get the updated presence
        presence_records = persistence_manager.get_presence(sample_session)
        assert len(presence_records) == 1
        
        record = presence_records[0]
        assert record["user_id"] == sample_user_id
        assert record["client_id"] == sample_client_id
        assert record["cursor_position"] == new_cursor
        assert record["status"] == new_status
        assert record["metadata"]["initial"] is True  # Original metadata preserved
        assert record["metadata"]["updated"] is True  # New metadata added
    
    def test_presence_timeout(self, persistence_manager, sample_session, sample_user_id):
        """Test that inactive presence records are not returned after timeout."""
        # Set a short presence timeout for testing
        original_timeout = persistence_manager.presence_timeout
        persistence_manager.presence_timeout = 1  # 1 second
        
        try:
            # Add a presence record
            persistence_manager.update_presence(
                session_id=sample_session,
                user_id=sample_user_id,
                client_id="client-1",
                status="active"
            )
            
            # Verify it exists
            presence_records = persistence_manager.get_presence(sample_session)
            assert len(presence_records) == 1
            
            # Wait for timeout
            time.sleep(2)
            
            # Verify it's no longer returned
            presence_records = persistence_manager.get_presence(sample_session)
            assert len(presence_records) == 0
        finally:
            # Restore original timeout
            persistence_manager.presence_timeout = original_timeout


class TestCellLocks:
    """Tests for cell locking mechanism."""

    def test_acquire_cell_lock(self, persistence_manager, sample_session, sample_user_id):
        """Test acquiring a lock on a cell."""
        cell_id = "cell-1"
        metadata = {"lock_type": "edit", "lock_reason": "user_editing"}
        
        lock_info = persistence_manager.acquire_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=sample_user_id,
            metadata=metadata
        )
        
        assert lock_info is not None
        assert lock_info["session_id"] == sample_session
        assert lock_info["cell_id"] == cell_id
        assert lock_info["user_id"] == sample_user_id
        assert "acquired_at" in lock_info
        assert "expires_at" in lock_info
        assert lock_info["metadata"]["lock_type"] == "edit"
    
    def test_acquire_already_locked_cell(self, persistence_manager, sample_session):
        """Test acquiring a lock on a cell that's already locked by another user."""
        cell_id = "cell-2"
        
        # User 1 acquires the lock
        user1 = "user-1"
        lock_info = persistence_manager.acquire_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=user1
        )
        assert lock_info is not None
        
        # User 2 tries to acquire the same lock
        user2 = "user-2"
        lock_info = persistence_manager.acquire_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=user2
        )
        
        # Should fail because cell is already locked
        assert lock_info is None
    
    def test_acquire_own_locked_cell(self, persistence_manager, sample_session, sample_user_id):
        """Test acquiring a lock on a cell that's already locked by the same user."""
        cell_id = "cell-3"
        
        # First acquisition
        lock_info1 = persistence_manager.acquire_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=sample_user_id,
            metadata={"first": True}
        )
        assert lock_info1 is not None
        
        # Second acquisition by same user
        lock_info2 = persistence_manager.acquire_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=sample_user_id,
            metadata={"second": True}
        )
        
        # Should succeed and update the existing lock
        assert lock_info2 is not None
        assert lock_info2["lock_id"] == lock_info1["lock_id"]
        assert lock_info2["metadata"]["first"] is True  # Original metadata preserved
        assert lock_info2["metadata"]["second"] is True  # New metadata added
    
    def test_release_cell_lock(self, persistence_manager, sample_session, sample_user_id):
        """Test releasing a lock on a cell."""
        cell_id = "cell-4"
        
        # Acquire the lock
        persistence_manager.acquire_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=sample_user_id
        )
        
        # Release the lock
        result = persistence_manager.release_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=sample_user_id
        )
        assert result is True
        
        # Verify lock is released by trying to acquire it again
        lock_info = persistence_manager.acquire_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id="another-user"  # Different user
        )
        assert lock_info is not None  # Lock can be acquired by another user
    
    def test_release_nonexistent_lock(self, persistence_manager, sample_session, sample_user_id):
        """Test releasing a non-existent lock."""
        result = persistence_manager.release_cell_lock(
            session_id=sample_session,
            cell_id="nonexistent-cell",
            user_id=sample_user_id
        )
        assert result is False
    
    def test_release_another_users_lock(self, persistence_manager, sample_session):
        """Test releasing a lock owned by another user."""
        cell_id = "cell-5"
        user1 = "user-1"
        user2 = "user-2"
        
        # User 1 acquires the lock
        persistence_manager.acquire_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=user1
        )
        
        # User 2 tries to release the lock
        result = persistence_manager.release_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=user2
        )
        assert result is False  # Should fail
    
    def test_get_cell_locks(self, persistence_manager, sample_session):
        """Test retrieving all active cell locks for a session."""
        # Create locks for multiple cells
        for i in range(3):
            cell_id = f"cell-{i+10}"
            user_id = f"user-{i}"
            persistence_manager.acquire_cell_lock(
                session_id=sample_session,
                cell_id=cell_id,
                user_id=user_id,
                metadata={"lock_index": i}
            )
        
        # Get all locks
        locks = persistence_manager.get_cell_locks(sample_session)
        assert len(locks) == 3
        
        # Verify cell IDs
        cell_ids = [lock["cell_id"] for lock in locks]
        for i in range(3):
            assert f"cell-{i+10}" in cell_ids
    
    def test_lock_expiration(self, persistence_manager, sample_session, sample_user_id):
        """Test that expired locks are not returned and can be re-acquired."""
        cell_id = "cell-expiration"
        
        # Set a short lock timeout for testing
        lock_info = persistence_manager.acquire_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=sample_user_id,
            timeout=1  # 1 second timeout
        )
        assert lock_info is not None
        
        # Verify lock exists
        locks = persistence_manager.get_cell_locks(sample_session)
        assert any(lock["cell_id"] == cell_id for lock in locks)
        
        # Wait for expiration
        time.sleep(2)
        
        # Verify lock is no longer active
        locks = persistence_manager.get_cell_locks(sample_session)
        assert not any(lock["cell_id"] == cell_id for lock in locks)
        
        # Verify another user can acquire the lock
        lock_info = persistence_manager.acquire_cell_lock(
            session_id=sample_session,
            cell_id=cell_id,
            user_id="another-user"  # Different user
        )
        assert lock_info is not None


class TestComments:
    """Tests for comment thread and comment management."""

    def test_create_comment_thread(self, persistence_manager, sample_session, sample_user_id):
        """Test creating a new comment thread with an initial comment."""
        cell_id = "cell-comment-1"
        content = "This is a test comment"
        metadata = {"position": {"line": 5}}
        
        thread_info = persistence_manager.create_comment_thread(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=sample_user_id,
            content=content,
            metadata=metadata
        )
        
        assert thread_info is not None
        assert thread_info["session_id"] == sample_session
        assert thread_info["cell_id"] == cell_id
        assert thread_info["status"] == "open"
        assert thread_info["metadata"]["position"]["line"] == 5
        
        # Verify initial comment
        assert "comment" in thread_info
        assert thread_info["comment"]["user_id"] == sample_user_id
        assert thread_info["comment"]["content"] == content
    
    def test_add_comment(self, persistence_manager, sample_session, sample_user_id):
        """Test adding a comment to an existing thread."""
        # Create a thread
        thread_info = persistence_manager.create_comment_thread(
            session_id=sample_session,
            cell_id="cell-comment-2",
            user_id=sample_user_id,
            content="Initial comment"
        )
        thread_id = thread_info["thread_id"]
        
        # Add a comment to the thread
        comment_content = "This is a reply"
        comment_info = persistence_manager.add_comment(
            thread_id=thread_id,
            user_id="another-user",
            content=comment_content,
            metadata={"reply": True}
        )
        
        assert comment_info is not None
        assert comment_info["thread_id"] == thread_id
        assert comment_info["user_id"] == "another-user"
        assert comment_info["content"] == comment_content
        assert comment_info["metadata"]["reply"] is True
    
    def test_add_comment_to_nonexistent_thread(self, persistence_manager, sample_user_id):
        """Test adding a comment to a non-existent thread."""
        nonexistent_id = str(uuid.uuid4())
        comment_info = persistence_manager.add_comment(
            thread_id=nonexistent_id,
            user_id=sample_user_id,
            content="This should fail"
        )
        assert comment_info is None
    
    def test_get_comment_threads(self, persistence_manager, sample_session, sample_user_id):
        """Test retrieving comment threads for a session."""
        # Create threads for multiple cells
        cell_ids = ["cell-thread-1", "cell-thread-2", "cell-thread-3"]
        for i, cell_id in enumerate(cell_ids):
            persistence_manager.create_comment_thread(
                session_id=sample_session,
                cell_id=cell_id,
                user_id=sample_user_id,
                content=f"Comment for {cell_id}",
                metadata={"thread_index": i}
            )
        
        # Get all threads
        threads = persistence_manager.get_comment_threads(sample_session)
        assert len(threads) == 3
        
        # Verify cell IDs
        thread_cell_ids = [thread["cell_id"] for thread in threads]
        for cell_id in cell_ids:
            assert cell_id in thread_cell_ids
        
        # Verify comments are included
        for thread in threads:
            assert "comments" in thread
            assert len(thread["comments"]) == 1
            assert thread["comments"][0]["content"].startswith("Comment for")
    
    def test_get_comment_threads_by_cell(self, persistence_manager, sample_session, sample_user_id):
        """Test retrieving comment threads for a specific cell."""
        # Create multiple threads for the same cell
        cell_id = "cell-multi-thread"
        for i in range(3):
            persistence_manager.create_comment_thread(
                session_id=sample_session,
                cell_id=cell_id,
                user_id=sample_user_id,
                content=f"Thread {i+1}",
                metadata={"thread_number": i+1}
            )
        
        # Create a thread for a different cell
        persistence_manager.create_comment_thread(
            session_id=sample_session,
            cell_id="different-cell",
            user_id=sample_user_id,
            content="Different cell"
        )
        
        # Get threads for the specific cell
        threads = persistence_manager.get_comment_threads(sample_session, cell_id=cell_id)
        assert len(threads) == 3
        
        # Verify all threads are for the correct cell
        for thread in threads:
            assert thread["cell_id"] == cell_id
    
    def test_get_comment_threads_by_status(self, persistence_manager, sample_session, sample_user_id):
        """Test retrieving comment threads filtered by status."""
        # Create threads with different statuses
        cell_id = "cell-status"
        
        # Open thread
        open_thread = persistence_manager.create_comment_thread(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=sample_user_id,
            content="Open thread"
        )
        
        # Resolved thread
        resolved_thread = persistence_manager.create_comment_thread(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=sample_user_id,
            content="Resolved thread"
        )
        persistence_manager.update_thread_status(
            thread_id=resolved_thread["thread_id"],
            status="resolved",
            user_id=sample_user_id
        )
        
        # Archived thread
        archived_thread = persistence_manager.create_comment_thread(
            session_id=sample_session,
            cell_id=cell_id,
            user_id=sample_user_id,
            content="Archived thread"
        )
        persistence_manager.update_thread_status(
            thread_id=archived_thread["thread_id"],
            status="archived",
            user_id=sample_user_id
        )
        
        # Get open threads
        open_threads = persistence_manager.get_comment_threads(sample_session, status="open")
        assert len(open_threads) == 1
        assert open_threads[0]["status"] == "open"
        
        # Get resolved threads
        resolved_threads = persistence_manager.get_comment_threads(sample_session, status="resolved")
        assert len(resolved_threads) == 1
        assert resolved_threads[0]["status"] == "resolved"
        
        # Get archived threads
        archived_threads = persistence_manager.get_comment_threads(sample_session, status="archived")
        assert len(archived_threads) == 1
        assert archived_threads[0]["status"] == "archived"
    
    def test_update_thread_status(self, persistence_manager, sample_session, sample_user_id):
        """Test updating the status of a comment thread."""
        # Create a thread
        thread_info = persistence_manager.create_comment_thread(
            session_id=sample_session,
            cell_id="cell-status-update",
            user_id=sample_user_id,
            content="Status test"
        )
        thread_id = thread_info["thread_id"]
        
        # Update status to resolved
        result = persistence_manager.update_thread_status(
            thread_id=thread_id,
            status="resolved",
            user_id=sample_user_id
        )
        assert result is True
        
        # Verify status update
        threads = persistence_manager.get_comment_threads(
            sample_session, 
            cell_id="cell-status-update"
        )
        assert len(threads) == 1
        assert threads[0]["status"] == "resolved"
        
        # Verify status history in metadata
        assert "status_history" in threads[0]["metadata"]
        assert len(threads[0]["metadata"]["status_history"]) == 1
        assert threads[0]["metadata"]["status_history"][0]["status"] == "resolved"
        assert threads[0]["metadata"]["status_history"][0]["changed_by"] == sample_user_id
    
    def test_update_nonexistent_thread_status(self, persistence_manager, sample_user_id):
        """Test updating the status of a non-existent thread."""
        nonexistent_id = str(uuid.uuid4())
        result = persistence_manager.update_thread_status(
            thread_id=nonexistent_id,
            status="resolved",
            user_id=sample_user_id
        )
        assert result is False
    
    def test_reopening_resolved_thread(self, persistence_manager, sample_session, sample_user_id):
        """Test that adding a comment to a resolved thread reopens it."""
        # Create a thread
        thread_info = persistence_manager.create_comment_thread(
            session_id=sample_session,
            cell_id="cell-reopen",
            user_id=sample_user_id,
            content="Reopen test"
        )
        thread_id = thread_info["thread_id"]
        
        # Resolve the thread
        persistence_manager.update_thread_status(
            thread_id=thread_id,
            status="resolved",
            user_id=sample_user_id
        )
        
        # Add a new comment
        persistence_manager.add_comment(
            thread_id=thread_id,
            user_id="another-user",
            content="This should reopen the thread"
        )
        
        # Verify thread is reopened
        threads = persistence_manager.get_comment_threads(
            sample_session, 
            cell_id="cell-reopen"
        )
        assert len(threads) == 1
        assert threads[0]["status"] == "open"


class TestPermissions:
    """Tests for permission management."""

    def test_set_user_permission(self, persistence_manager, sample_session, sample_user_id):
        """Test setting a permission for a user on a resource."""
        resource_id = "document-1"
        resource_type = "document"
        permission_type = "edit"
        granted_by = "admin-user"
        metadata = {"expiration_date": "2023-12-31T23:59:59Z"}
        
        permission_id = persistence_manager.set_permission(
            session_id=sample_session,
            resource_id=resource_id,
            resource_type=resource_type,
            permission_type=permission_type,
            user_id=sample_user_id,
            granted_by=granted_by,
            metadata=metadata
        )
        
        assert permission_id is not None
        assert uuid.UUID(permission_id)
    
    def test_set_group_permission(self, persistence_manager, sample_session):
        """Test setting a permission for a group on a resource."""
        resource_id = "document-2"
        resource_type = "document"
        permission_type = "view"
        group_id = "group-1"
        granted_by = "admin-user"
        
        permission_id = persistence_manager.set_permission(
            session_id=sample_session,
            resource_id=resource_id,
            resource_type=resource_type,
            permission_type=permission_type,
            group_id=group_id,
            granted_by=granted_by
        )
        
        assert permission_id is not None
        assert uuid.UUID(permission_id)
    
    def test_update_existing_permission(self, persistence_manager, sample_session, sample_user_id):
        """Test updating an existing permission."""
        resource_id = "document-3"
        resource_type = "document"
        
        # Set initial permission
        permission_id = persistence_manager.set_permission(
            session_id=sample_session,
            resource_id=resource_id,
            resource_type=resource_type,
            permission_type="view",
            user_id=sample_user_id,
            granted_by="admin-user",
            metadata={"initial": True}
        )
        
        # Update permission
        updated_permission_id = persistence_manager.set_permission(
            session_id=sample_session,
            resource_id=resource_id,
            resource_type=resource_type,
            permission_type="edit",  # Changed from view to edit
            user_id=sample_user_id,
            granted_by="admin-user-2",
            metadata={"updated": True}
        )
        
        assert updated_permission_id == permission_id  # Same permission ID
        
        # Verify update
        permissions = persistence_manager.get_permissions(
            sample_session,
            resource_id=resource_id,
            user_id=sample_user_id
        )
        assert len(permissions) == 1
        assert permissions[0]["permission_type"] == "edit"  # Updated type
        assert permissions[0]["granted_by"] == "admin-user-2"  # Updated grantor
        assert permissions[0]["metadata"]["initial"] is True  # Original metadata preserved
        assert permissions[0]["metadata"]["updated"] is True  # New metadata added
    
    def test_get_permissions(self, persistence_manager, sample_session):
        """Test retrieving permissions for a session."""
        # Set permissions for multiple resources and users
        for i in range(3):
            resource_id = f"resource-{i}"
            user_id = f"user-{i}"
            permission_type = "edit" if i % 2 == 0 else "view"
            
            persistence_manager.set_permission(
                session_id=sample_session,
                resource_id=resource_id,
                resource_type="document",
                permission_type=permission_type,
                user_id=user_id,
                granted_by="admin"
            )
        
        # Get all permissions
        permissions = persistence_manager.get_permissions(sample_session)
        assert len(permissions) == 3
        
        # Verify resource IDs
        resource_ids = [p["resource_id"] for p in permissions]
        for i in range(3):
            assert f"resource-{i}" in resource_ids
    
    def test_get_permissions_with_filters(self, persistence_manager, sample_session):
        """Test retrieving permissions with various filters."""
        # Set up test data
        resource_types = ["document", "cell", "comment"]
        permission_types = ["view", "comment", "edit", "admin"]
        
        for i in range(12):  # Create a variety of permissions
            resource_id = f"filter-resource-{i % 4}"
            resource_type = resource_types[i % 3]
            permission_type = permission_types[i % 4]
            user_id = f"filter-user-{i % 3}"
            
            persistence_manager.set_permission(
                session_id=sample_session,
                resource_id=resource_id,
                resource_type=resource_type,
                permission_type=permission_type,
                user_id=user_id,
                granted_by="admin"
            )
        
        # Filter by resource ID
        permissions = persistence_manager.get_permissions(
            sample_session,
            resource_id="filter-resource-2"
        )
        assert len(permissions) == 3  # 3 permissions for this resource
        for p in permissions:
            assert p["resource_id"] == "filter-resource-2"
        
        # Filter by resource type
        permissions = persistence_manager.get_permissions(
            sample_session,
            resource_type="cell"
        )
        assert len(permissions) == 4  # 4 permissions of type "cell"
        for p in permissions:
            assert p["resource_type"] == "cell"
        
        # Filter by user ID
        permissions = persistence_manager.get_permissions(
            sample_session,
            user_id="filter-user-1"
        )
        assert len(permissions) == 4  # 4 permissions for this user
        for p in permissions:
            assert p["user_id"] == "filter-user-1"
        
        # Combined filters
        permissions = persistence_manager.get_permissions(
            sample_session,
            resource_type="document",
            user_id="filter-user-0"
        )
        assert len(permissions) > 0
        for p in permissions:
            assert p["resource_type"] == "document"
            assert p["user_id"] == "filter-user-0"
    
    def test_remove_permission(self, persistence_manager, sample_session, sample_user_id):
        """Test removing a permission."""
        # Set a permission
        permission_id = persistence_manager.set_permission(
            session_id=sample_session,
            resource_id="remove-test",
            resource_type="document",
            permission_type="edit",
            user_id=sample_user_id,
            granted_by="admin"
        )
        
        # Verify it exists
        permissions = persistence_manager.get_permissions(
            sample_session,
            resource_id="remove-test"
        )
        assert len(permissions) == 1
        
        # Remove the permission
        result = persistence_manager.remove_permission(permission_id)
        assert result is True
        
        # Verify it's gone
        permissions = persistence_manager.get_permissions(
            sample_session,
            resource_id="remove-test"
        )
        assert len(permissions) == 0
    
    def test_remove_nonexistent_permission(self, persistence_manager):
        """Test removing a non-existent permission."""
        nonexistent_id = str(uuid.uuid4())
        result = persistence_manager.remove_permission(nonexistent_id)
        assert result is False
    
    def test_check_permission(self, persistence_manager, sample_session):
        """Test checking if a user has the required permission on a resource."""
        document_id = "check-document"
        cell_id = "check-cell"
        user_id = "check-user"
        
        # Set document-level edit permission
        persistence_manager.set_permission(
            session_id=sample_session,
            resource_id=document_id,
            resource_type="document",
            permission_type="edit",
            user_id=user_id,
            granted_by="admin"
        )
        
        # Check permissions
        assert persistence_manager.check_permission(
            session_id=sample_session,
            resource_id=document_id,
            resource_type="document",
            user_id=user_id,
            required_permission="view"
        ) is True  # edit > view
        
        assert persistence_manager.check_permission(
            session_id=sample_session,
            resource_id=document_id,
            resource_type="document",
            user_id=user_id,
            required_permission="edit"
        ) is True  # edit == edit
        
        assert persistence_manager.check_permission(
            session_id=sample_session,
            resource_id=document_id,
            resource_type="document",
            user_id=user_id,
            required_permission="admin"
        ) is False  # edit < admin
        
        # Check cell-level permission (should inherit from document)
        assert persistence_manager.check_permission(
            session_id=sample_session,
            resource_id=cell_id,
            resource_type="cell",
            user_id=user_id,
            required_permission="edit"
        ) is True  # Inherited from document
        
        # Override with cell-level permission
        persistence_manager.set_permission(
            session_id=sample_session,
            resource_id=cell_id,
            resource_type="cell",
            permission_type="view",  # Downgrade to view-only
            user_id=user_id,
            granted_by="admin"
        )
        
        # Check cell-level permission again
        assert persistence_manager.check_permission(
            session_id=sample_session,
            resource_id=cell_id,
            resource_type="cell",
            user_id=user_id,
            required_permission="view"
        ) is True  # view == view
        
        assert persistence_manager.check_permission(
            session_id=sample_session,
            resource_id=cell_id,
            resource_type="cell",
            user_id=user_id,
            required_permission="edit"
        ) is False  # view < edit
    
    def test_session_owner_always_has_admin(self, persistence_manager, sample_session):
        """Test that the session owner always has admin permission."""
        # Create a session with a specific owner
        owner_id = "session-owner"
        document_id = "owner-document"
        session_id = persistence_manager.create_collaboration_session(
            document_id=document_id,
            owner_id=owner_id
        )
        
        # Check admin permission without explicitly setting it
        assert persistence_manager.check_permission(
            session_id=session_id,
            resource_id=document_id,
            resource_type="document",
            user_id=owner_id,
            required_permission="admin"
        ) is True  # Owner has implicit admin


class TestErrorHandling:
    """Tests for error handling and recovery."""

    def test_database_connection_error(self):
        """Test handling of database connection errors."""
        # Create a persistence manager with an invalid database URL
        with pytest.raises(Exception):
            PersistenceManager(db_url="invalid://connection/string", initialize_db=True)
    
    def test_transaction_rollback_on_error(self, persistence_manager, sample_session, sample_user_id):
        """Test that transactions are rolled back on error."""
        # Mock the session to simulate an error during commit
        with patch.object(persistence_manager, 'get_session') as mock_get_session:
            mock_session = MagicMock()
            mock_session.commit.side_effect = Exception("Simulated database error")
            mock_get_session.return_value = mock_session
            
            # Attempt an operation that should fail
            with pytest.raises(Exception, match="Simulated database error"):
                persistence_manager.create_comment_thread(
                    session_id=sample_session,
                    cell_id="error-cell",
                    user_id=sample_user_id,
                    content="This should fail"
                )
            
            # Verify rollback was called
            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()


class TestMaintenanceTasks:
    """Tests for cleanup and maintenance tasks."""

    def test_run_cleanup(self, persistence_manager, sample_session, sample_user_id):
        """Test running cleanup tasks."""
        # Create expired locks
        for i in range(3):
            cell_id = f"cleanup-cell-{i}"
            # Create lock with immediate expiration
            persistence_manager.acquire_cell_lock(
                session_id=sample_session,
                cell_id=cell_id,
                user_id=sample_user_id,
                timeout=0  # Immediate expiration
            )
        
        # Create inactive presence records (would normally timeout)
        for i in range(3):
            client_id = f"cleanup-client-{i}"
            persistence_manager.update_presence(
                session_id=sample_session,
                user_id=sample_user_id,
                client_id=client_id,
                status="active"
            )
        
        # Force cleanup to run regardless of interval
        cleanup_stats = persistence_manager.run_cleanup(force=True)
        
        assert cleanup_stats["skipped"] is False
        assert cleanup_stats["expired_locks_removed"] == 3
        # Note: presence records might not be removed immediately due to the 10x timeout multiplier
    
    def test_cleanup_interval(self, persistence_manager):
        """Test that cleanup respects the interval."""
        # Set a long cleanup interval
        persistence_manager.cleanup_interval = 3600  # 1 hour
        
        # Run cleanup once
        first_run = persistence_manager.run_cleanup(force=True)
        assert first_run["skipped"] is False
        
        # Run cleanup again immediately
        second_run = persistence_manager.run_cleanup(force=False)
        assert second_run["skipped"] is True  # Should be skipped due to interval
        
        # Force cleanup to run anyway
        third_run = persistence_manager.run_cleanup(force=True)
        assert third_run["skipped"] is False  # Should run when forced
    
    def test_compact_updates(self, persistence_manager, sample_session):
        """Test compacting update records."""
        # This is a placeholder test since the actual implementation is a placeholder
        result = persistence_manager.compact_updates(sample_session)
        assert result["session_id"] == sample_session
        assert "compacted" in result


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing document formats."""

    def test_collaboration_with_standard_notebook(self, persistence_manager, sample_document_id, sample_user_id):
        """Test that collaboration works with standard notebook format."""
        # Create a session for a standard notebook
        session_id = persistence_manager.create_collaboration_session(
            document_id=sample_document_id,
            owner_id=sample_user_id
        )
        
        # Store some updates
        for i in range(5):
            persistence_manager.store_update(
                session_id=session_id,
                sequence_number=i+1,
                update_data=b"\x01\x02\x03",
                client_id=f"client-{i}",
                user_id=sample_user_id,
                metadata={"standard_notebook": True}
            )
        
        # Verify updates were stored correctly
        updates = persistence_manager.get_updates(session_id)
        assert len(updates) == 5
        for update in updates:
            assert update["metadata"]["standard_notebook"] is True
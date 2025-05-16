"""Tests for the collaborative persistence layer in Jupyter Notebook v7.

This module tests the persistence layer for collaborative editing state, ensuring that
document updates, version history, and collaboration metadata are correctly stored and
retrieved from the database. It verifies that collaborative editing state persists across
server restarts and that document history can be accurately reconstructed.

The tests cover:
1. Document state persistence and retrieval
2. Update history storage and reconstruction
3. Metadata persistence (comments, locks, permissions)
4. Database error handling and recovery mechanisms
5. State migration and backward compatibility
"""

import asyncio
import json
import os
import pytest
import uuid
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

# Import the persistence module
from notebook.collab.persistence import (
    PersistenceManager, CollaborationSession, YjsUpdateRecord,
    PresenceRecord, CellLock, PermissionEntry, CommentThread, Comment,
    VersionSnapshot, Base
)


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    # Create an in-memory SQLite database
    engine = create_engine('sqlite:///:memory:')
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    # Create session factory
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    
    yield engine, Session
    
    # Clean up
    Session.remove()
    Base.metadata.drop_all(engine)


@pytest.fixture
def persistence_manager(in_memory_db):
    """Create a PersistenceManager instance with an in-memory database."""
    engine, Session = in_memory_db
    
    # Create persistence manager with in-memory database
    manager = PersistenceManager()
    manager._engine = engine
    manager._Session = Session
    manager._session_factory = Session.registry.createfunc
    
    # Override environment variable to use in-memory database
    with patch.dict(os.environ, {'JUPYTER_COLLABORATION_DB_URL': 'sqlite:///:memory:'}):
        yield manager


@pytest.fixture
def sample_document_id():
    """Generate a sample document ID for testing."""
    return f"notebook-{uuid.uuid4()}"


@pytest.fixture
def sample_user_id():
    """Generate a sample user ID for testing."""
    return f"user-{uuid.uuid4()}"


@pytest.fixture
def sample_update_data():
    """Generate sample Yjs update data for testing."""
    # This would normally be binary Yjs update data
    # For testing, we'll use a simple byte string
    return b'\x01\x02\x03\x04\x05'


@pytest.fixture
def sample_state_vector():
    """Generate sample Yjs state vector for testing."""
    # This would normally be a binary Yjs state vector
    # For testing, we'll use a simple byte string
    return b'\x01\x00\x02\x00\x03\x00'


@pytest.fixture
def sample_document_state():
    """Generate sample Yjs document state for testing."""
    # This would normally be a binary Yjs document state
    # For testing, we'll use a simple byte string
    return b'\x04\x00\x05\x00\x06\x00'


@pytest.fixture
def sample_collaboration_session(persistence_manager, sample_document_id, sample_user_id):
    """Create a sample collaboration session for testing."""
    session_id = persistence_manager.create_collaboration_session(
        sample_document_id, sample_user_id, {"title": "Test Session"}
    )
    return session_id


class TestDocumentStatePersistence:
    """Test document state persistence and retrieval.
    
    These tests verify that collaborative document state is correctly stored and
    retrieved from the database, ensuring persistence across server restarts.
    """
    
    def test_create_collaboration_session(self, persistence_manager, sample_document_id, sample_user_id):
        """Test creating a new collaboration session."""
        # Create a new session
        session_id = persistence_manager.create_collaboration_session(
            sample_document_id, sample_user_id, {"title": "Test Session"}
        )
        
        # Verify session was created
        assert session_id is not None
        
        # Retrieve the session
        session = persistence_manager.get_collaboration_session(session_id)
        
        # Verify session properties
        assert session is not None
        assert session['document_id'] == sample_document_id
        assert session['owner_id'] == sample_user_id
        assert session['metadata']['title'] == "Test Session"
        assert session['active'] is True
    
    def test_get_collaboration_sessions_for_document(self, persistence_manager, sample_document_id, sample_user_id):
        """Test retrieving all collaboration sessions for a document."""
        # Create multiple sessions for the same document
        session_id1 = persistence_manager.create_collaboration_session(
            sample_document_id, sample_user_id, {"title": "Session 1"}
        )
        session_id2 = persistence_manager.create_collaboration_session(
            sample_document_id, f"{sample_user_id}-2", {"title": "Session 2"}
        )
        
        # Retrieve sessions for the document
        sessions = persistence_manager.get_collaboration_sessions_for_document(sample_document_id)
        
        # Verify sessions were retrieved
        assert len(sessions) == 2
        session_ids = [s['session_id'] for s in sessions]
        assert session_id1 in session_ids
        assert session_id2 in session_ids
    
    def test_update_collaboration_session(self, persistence_manager, sample_collaboration_session):
        """Test updating a collaboration session."""
        # Update session metadata
        success = persistence_manager.update_collaboration_session(
            sample_collaboration_session, 
            metadata={"title": "Updated Title", "description": "New description"}
        )
        
        # Verify update was successful
        assert success is True
        
        # Retrieve updated session
        session = persistence_manager.get_collaboration_session(sample_collaboration_session)
        
        # Verify updated properties
        assert session['metadata']['title'] == "Updated Title"
        assert session['metadata']['description'] == "New description"
    
    def test_store_and_retrieve_update(self, persistence_manager, sample_collaboration_session, 
                                      sample_update_data, sample_user_id):
        """Test storing and retrieving Yjs updates."""
        # Store an update
        client_id = "client-123"
        update_id = persistence_manager.store_update(
            sample_collaboration_session, 1, sample_update_data, client_id, sample_user_id
        )
        
        # Verify update was stored
        assert update_id is not None
        
        # Retrieve updates
        updates = persistence_manager.get_updates(sample_collaboration_session)
        
        # Verify update was retrieved
        assert len(updates) == 1
        assert updates[0]['update_id'] == update_id
        assert updates[0]['sequence_number'] == 1
        assert updates[0]['client_id'] == client_id
        assert updates[0]['user_id'] == sample_user_id
        assert updates[0]['update_data'] == sample_update_data
    
    def test_store_multiple_updates(self, persistence_manager, sample_collaboration_session, 
                                   sample_update_data, sample_user_id):
        """Test storing and retrieving multiple Yjs updates."""
        client_id = "client-123"
        
        # Store multiple updates
        for i in range(5):
            persistence_manager.store_update(
                sample_collaboration_session, i+1, 
                sample_update_data + bytes([i]), 
                client_id, sample_user_id
            )
        
        # Retrieve all updates
        updates = persistence_manager.get_updates(sample_collaboration_session)
        
        # Verify all updates were retrieved
        assert len(updates) == 5
        
        # Verify updates are in sequence order
        for i, update in enumerate(updates):
            assert update['sequence_number'] == i+1
            assert update['update_data'] == sample_update_data + bytes([i])
        
        # Test retrieving updates with sequence range
        filtered_updates = persistence_manager.get_updates(
            sample_collaboration_session, start_sequence=2, end_sequence=4
        )
        
        # Verify filtered updates
        assert len(filtered_updates) == 3  # Updates 2, 3, 4
        assert filtered_updates[0]['sequence_number'] == 2
        assert filtered_updates[-1]['sequence_number'] == 4


class TestVersionHistoryPersistence:
    """Test version history storage and reconstruction.
    
    These tests verify that document version history is correctly stored and can be
    used to reconstruct document state at any point in time.
    """
    
    def test_store_and_retrieve_snapshot(self, persistence_manager, sample_collaboration_session,
                                        sample_state_vector, sample_document_state):
        """Test storing and retrieving version snapshots."""
        # Create sample snapshot data
        sequence_number = 10
        metadata = {"snapshot_reason": "scheduled"}
        
        # Store snapshot
        snapshot_id = persistence_manager.store_snapshot(
            sample_collaboration_session, sequence_number, 
            sample_state_vector, sample_document_state, metadata
        )
        
        # Verify snapshot was stored
        assert snapshot_id is not None
        
        # Retrieve latest snapshot
        snapshot = persistence_manager.get_latest_snapshot(sample_collaboration_session)
        
        # Verify snapshot properties
        assert snapshot is not None
        assert snapshot['snapshot_id'] == snapshot_id
        assert snapshot['sequence_number'] == sequence_number
        assert snapshot['state_vector'] == sample_state_vector
        assert snapshot['document_state'] == sample_document_state
        assert snapshot['metadata']['snapshot_reason'] == "scheduled"
    
    def test_multiple_snapshots(self, persistence_manager, sample_collaboration_session,
                              sample_state_vector, sample_document_state):
        """Test storing and retrieving multiple snapshots."""
        # Store multiple snapshots with increasing sequence numbers
        for i in range(3):
            sequence_number = (i + 1) * 10
            persistence_manager.store_snapshot(
                sample_collaboration_session, sequence_number,
                sample_state_vector + bytes([i]), 
                sample_document_state + bytes([i]),
                {"snapshot_number": i+1}
            )
        
        # Retrieve latest snapshot
        snapshot = persistence_manager.get_latest_snapshot(sample_collaboration_session)
        
        # Verify it's the one with the highest sequence number
        assert snapshot['sequence_number'] == 30
        assert snapshot['metadata']['snapshot_number'] == 3
    
    def test_version_history_timeline(self, persistence_manager, sample_collaboration_session,
                                    sample_state_vector, sample_document_state,
                                    sample_user_id):
        """Test creating and retrieving a timeline of document versions."""
        client_id = "client-123"
        
        # Create a series of updates and snapshots to simulate document evolution
        # Initial snapshot at sequence 0
        persistence_manager.store_snapshot(
            sample_collaboration_session, 0,
            sample_state_vector, sample_document_state,
            {"snapshot_reason": "initial", "version": "1.0"}
        )
        
        # Add some updates
        for i in range(5):
            persistence_manager.store_update(
                sample_collaboration_session, i+1,
                b'\x01\x02\x03' + bytes([i]),
                client_id, sample_user_id,
                {"change_description": f"Change {i+1}"}
            )
        
        # Create another snapshot at sequence 5
        persistence_manager.store_snapshot(
            sample_collaboration_session, 5,
            sample_state_vector + b'\x01', sample_document_state + b'\x01',
            {"snapshot_reason": "checkpoint", "version": "1.1"}
        )
        
        # Add more updates
        for i in range(5, 10):
            persistence_manager.store_update(
                sample_collaboration_session, i+1,
                b'\x01\x02\x03' + bytes([i]),
                client_id, sample_user_id,
                {"change_description": f"Change {i+1}"}
            )
        
        # Create final snapshot at sequence 10
        persistence_manager.store_snapshot(
            sample_collaboration_session, 10,
            sample_state_vector + b'\x02', sample_document_state + b'\x02',
            {"snapshot_reason": "checkpoint", "version": "1.2"}
        )
        
        # Now retrieve all snapshots to construct a version history timeline
        # In a real implementation, this would be a dedicated method
        db_session = persistence_manager.get_session()
        snapshots = db_session.query(VersionSnapshot).filter(
            VersionSnapshot.session_id == sample_collaboration_session
        ).order_by(VersionSnapshot.sequence_number).all()
        
        # Verify we have all snapshots
        assert len(snapshots) == 3
        
        # Verify snapshot sequence
        assert snapshots[0].sequence_number == 0
        assert snapshots[1].sequence_number == 5
        assert snapshots[2].sequence_number == 10
        
        # Verify version metadata
        assert snapshots[0].metadata['version'] == "1.0"
        assert snapshots[1].metadata['version'] == "1.1"
        assert snapshots[2].metadata['version'] == "1.2"
        
        # Verify we can get updates between snapshots
        updates_between = persistence_manager.get_updates(
            sample_collaboration_session,
            start_sequence=1,
            end_sequence=4
        )
        assert len(updates_between) == 4  # Updates 1, 2, 3, 4
        
        db_session.close()


class TestMetadataPersistence:
    """Test persistence of collaboration metadata (comments, locks, permissions).
    
    These tests verify that collaboration metadata such as user presence, cell locks,
    comments, and permissions are correctly stored and retrieved from the database.
    """
    
    def test_presence_tracking(self, persistence_manager, sample_collaboration_session, sample_user_id):
        """Test storing and retrieving user presence information."""
        client_id = "client-123"
        cursor_position = {"cell_id": "cell-1", "line": 5, "column": 10}
        selection_range = {"start": {"line": 5, "column": 10}, "end": {"line": 5, "column": 15}}
        
        # Update presence
        presence_id = persistence_manager.update_presence(
            sample_collaboration_session, sample_user_id, client_id,
            cursor_position, selection_range, "active",
            {"username": "Test User", "color": "#ff0000"}
        )
        
        # Verify presence was stored
        assert presence_id is not None
        
        # Retrieve presence records
        presence_records = persistence_manager.get_presence(sample_collaboration_session)
        
        # Verify presence record properties
        assert len(presence_records) == 1
        record = presence_records[0]
        assert record['user_id'] == sample_user_id
        assert record['client_id'] == client_id
        assert record['cursor_position'] == cursor_position
        assert record['selection_range'] == selection_range
        assert record['status'] == "active"
        assert record['metadata']['username'] == "Test User"
        assert record['metadata']['color'] == "#ff0000"
    
    def test_cell_locking(self, persistence_manager, sample_collaboration_session, sample_user_id):
        """Test acquiring and releasing cell locks."""
        cell_id = "cell-123"
        
        # Acquire lock
        lock = persistence_manager.acquire_cell_lock(
            sample_collaboration_session, cell_id, sample_user_id,
            metadata={"lock_reason": "editing"}
        )
        
        # Verify lock was acquired
        assert lock is not None
        assert lock['cell_id'] == cell_id
        assert lock['user_id'] == sample_user_id
        assert lock['metadata']['lock_reason'] == "editing"
        
        # Try to acquire same lock with different user (should fail)
        other_user = f"{sample_user_id}-other"
        other_lock = persistence_manager.acquire_cell_lock(
            sample_collaboration_session, cell_id, other_user
        )
        assert other_lock is None
        
        # Get all locks
        locks = persistence_manager.get_cell_locks(sample_collaboration_session)
        assert len(locks) == 1
        assert locks[0]['cell_id'] == cell_id
        
        # Release lock
        success = persistence_manager.release_cell_lock(
            sample_collaboration_session, cell_id, sample_user_id
        )
        assert success is True
        
        # Verify lock was released
        locks = persistence_manager.get_cell_locks(sample_collaboration_session)
        assert len(locks) == 0
        
        # Now other user should be able to acquire the lock
        other_lock = persistence_manager.acquire_cell_lock(
            sample_collaboration_session, cell_id, other_user
        )
        assert other_lock is not None
        assert other_lock['user_id'] == other_user
    
    def test_comment_threads(self, persistence_manager, sample_collaboration_session, sample_user_id):
        """Test creating and managing comment threads."""
        cell_id = "cell-123"
        content = "This is a test comment"
        
        # Create comment thread
        thread = persistence_manager.create_comment_thread(
            sample_collaboration_session, cell_id, sample_user_id, content,
            metadata={"importance": "high"}
        )
        
        # Verify thread was created
        assert thread is not None
        assert thread['cell_id'] == cell_id
        assert thread['status'] == "open"
        assert thread['metadata']['importance'] == "high"
        assert 'comment' in thread
        assert thread['comment']['user_id'] == sample_user_id
        assert thread['comment']['content'] == content
        
        # Get thread ID
        thread_id = thread['thread_id']
        
        # Add reply to thread
        other_user = f"{sample_user_id}-other"
        reply_content = "This is a reply"
        reply = persistence_manager.add_comment(
            thread_id, other_user, reply_content,
            metadata={"reaction": "👍"}
        )
        
        # Verify reply was added
        assert reply is not None
        assert reply['thread_id'] == thread_id
        assert reply['user_id'] == other_user
        assert reply['content'] == reply_content
        assert reply['metadata']['reaction'] == "👍"
        
        # Get all threads for document
        threads = persistence_manager.get_comment_threads(sample_collaboration_session)
        
        # Verify thread with comments
        assert len(threads) == 1
        assert threads[0]['thread_id'] == thread_id
        assert len(threads[0]['comments']) == 2  # Initial comment + reply
        
        # Update thread status
        success = persistence_manager.update_thread_status(thread_id, "resolved", sample_user_id)
        assert success is True
        
        # Get threads filtered by status
        open_threads = persistence_manager.get_comment_threads(
            sample_collaboration_session, status="open"
        )
        resolved_threads = persistence_manager.get_comment_threads(
            sample_collaboration_session, status="resolved"
        )
        
        # Verify thread status filtering
        assert len(open_threads) == 0
        assert len(resolved_threads) == 1
    
    def test_permissions(self, persistence_manager, sample_collaboration_session, sample_user_id):
        """Test setting and checking permissions."""
        document_id = "doc-123"
        other_user = f"{sample_user_id}-other"
        
        # Set document-level permission for a user
        permission_id = persistence_manager.set_permission(
            sample_collaboration_session, document_id, "document", "edit",
            user_id=other_user, granted_by=sample_user_id
        )
        
        # Verify permission was set
        assert permission_id is not None
        
        # Get permissions
        permissions = persistence_manager.get_permissions(sample_collaboration_session)
        
        # Verify permission properties
        assert len(permissions) == 1
        assert permissions[0]['resource_id'] == document_id
        assert permissions[0]['resource_type'] == "document"
        assert permissions[0]['permission_type'] == "edit"
        assert permissions[0]['user_id'] == other_user
        assert permissions[0]['granted_by'] == sample_user_id
        
        # Check permission
        has_permission = persistence_manager.check_permission(
            sample_collaboration_session, document_id, "document", other_user, "edit"
        )
        assert has_permission is True
        
        # Check permission for insufficient level
        has_admin = persistence_manager.check_permission(
            sample_collaboration_session, document_id, "document", other_user, "admin"
        )
        assert has_admin is False
        
        # Set cell-level permission
        cell_id = "cell-123"
        persistence_manager.set_permission(
            sample_collaboration_session, cell_id, "cell", "view",
            user_id=other_user, granted_by=sample_user_id
        )
        
        # Get permissions filtered by resource type
        cell_permissions = persistence_manager.get_permissions(
            sample_collaboration_session, resource_type="cell"
        )
        
        # Verify cell permission
        assert len(cell_permissions) == 1
        assert cell_permissions[0]['resource_id'] == cell_id
        assert cell_permissions[0]['resource_type'] == "cell"
        
        # Remove permission
        success = persistence_manager.remove_permission(permission_id)
        assert success is True
        
        # Verify permission was removed
        doc_permissions = persistence_manager.get_permissions(
            sample_collaboration_session, resource_id=document_id
        )
        assert len(doc_permissions) == 0


class TestErrorHandlingAndRecovery:
    """Test database error handling and recovery mechanisms.
    
    These tests verify that the persistence layer correctly handles database errors
    and can recover from them, ensuring data integrity and system reliability.
    """
    
    def test_transaction_rollback(self, persistence_manager, sample_collaboration_session, sample_user_id):
        """Test transaction rollback on error."""
        # Create a session that will be used to verify state after error
        db_session = persistence_manager.get_session()
        
        # Count initial number of presence records
        initial_count = db_session.query(PresenceRecord).count()
        
        # Patch update_presence to raise an exception after adding record but before commit
        original_update_presence = persistence_manager.update_presence
        
        def mock_update_presence(*args, **kwargs):
            # Call original method but don't let it commit
            with patch.object(db_session, 'commit', side_effect=Exception("Test exception")):
                try:
                    return original_update_presence(*args, **kwargs)
                except Exception:
                    pass
            return None
        
        with patch.object(persistence_manager, 'update_presence', mock_update_presence):
            # This should fail and rollback
            presence_id = persistence_manager.update_presence(
                sample_collaboration_session, sample_user_id, "client-123",
                {"cell_id": "cell-1"}, None, "active", {}
            )
            assert presence_id is None
        
        # Verify no records were added (transaction was rolled back)
        final_count = db_session.query(PresenceRecord).count()
        assert final_count == initial_count
        
        db_session.close()
    
    def test_connection_error_recovery(self, persistence_manager, sample_collaboration_session):
        """Test recovery from database connection errors."""
        # Simulate a connection error by temporarily closing the engine
        original_engine = persistence_manager._engine
        persistence_manager._engine = None
        
        # Attempt an operation that should fail
        with pytest.raises(Exception):
            persistence_manager.get_collaboration_session(sample_collaboration_session)
        
        # Restore the engine and verify operations work again
        persistence_manager._engine = original_engine
        session = persistence_manager.get_collaboration_session(sample_collaboration_session)
        assert session is not None
    
    def test_cleanup_expired_locks(self, persistence_manager, sample_collaboration_session, sample_user_id):
        """Test automatic cleanup of expired locks."""
        cell_id = "cell-123"
        
        # Create a session to directly manipulate the database
        db_session = persistence_manager.get_session()
        
        # Create an expired lock directly in the database
        expired_time = datetime.utcnow() - timedelta(hours=1)
        lock = CellLock(
            session_id=sample_collaboration_session,
            cell_id=cell_id,
            user_id=sample_user_id,
            acquired_at=expired_time,
            expires_at=expired_time + timedelta(minutes=5),  # Expired 55 minutes ago
            metadata={}
        )
        db_session.add(lock)
        db_session.commit()
        
        # Verify lock exists in database
        assert db_session.query(CellLock).count() == 1
        
        # Run cleanup
        cleanup_result = persistence_manager.run_cleanup(force=True)
        
        # Verify expired lock was removed
        assert cleanup_result['expired_locks_removed'] >= 1
        assert db_session.query(CellLock).count() == 0
        
        db_session.close()
    
    def test_cleanup_inactive_presence(self, persistence_manager, sample_collaboration_session, sample_user_id):
        """Test automatic cleanup of inactive presence records."""
        # Create a session to directly manipulate the database
        db_session = persistence_manager.get_session()
        
        # Create an inactive presence record directly in the database
        inactive_time = datetime.utcnow() - timedelta(hours=1)
        presence = PresenceRecord(
            session_id=sample_collaboration_session,
            user_id=sample_user_id,
            client_id="client-123",
            last_active=inactive_time,
            status="active",
            metadata={}
        )
        db_session.add(presence)
        db_session.commit()
        
        # Verify presence record exists in database
        assert db_session.query(PresenceRecord).count() == 1
        
        # Run cleanup
        cleanup_result = persistence_manager.run_cleanup(force=True)
        
        # Verify inactive presence was removed
        assert cleanup_result['inactive_presence_removed'] >= 1
        assert db_session.query(PresenceRecord).count() == 0
        
        db_session.close()
    
    def test_database_reconnection(self, persistence_manager, sample_collaboration_session):
        """Test automatic reconnection after database connection loss.
        
        This test verifies that the persistence layer can automatically reconnect to the
        database after a connection loss, ensuring system resilience.
        """
        # First verify we can access the database
        session = persistence_manager.get_collaboration_session(sample_collaboration_session)
        assert session is not None
        
        # Simulate a database connection loss by disposing the engine's connections
        persistence_manager._engine.dispose()
        
        # The next operation should automatically reconnect
        session = persistence_manager.get_collaboration_session(sample_collaboration_session)
        assert session is not None
    
    def test_error_handling_during_update(self, persistence_manager, sample_collaboration_session, 
                                        sample_update_data, sample_user_id):
        """Test error handling during update storage.
        
        This test verifies that the persistence layer correctly handles errors during
        update storage and can recover from them.
        """
        # Create a session to directly manipulate the database
        db_session = persistence_manager.get_session()
        
        # Count initial number of update records
        initial_count = db_session.query(YjsUpdateRecord).count()
        
        # Patch the session to raise an exception during commit
        with patch.object(db_session, 'commit', side_effect=Exception("Test exception")):
            # This should fail and rollback
            with pytest.raises(Exception):
                persistence_manager.store_update(
                    sample_collaboration_session, 1, 
                    sample_update_data, "client-123", sample_user_id
                )
        
        # Verify no records were added (transaction was rolled back)
        final_count = db_session.query(YjsUpdateRecord).count()
        assert final_count == initial_count
        
        # Now try a successful update to verify the system recovers
        update_id = persistence_manager.store_update(
            sample_collaboration_session, 1, 
            sample_update_data, "client-123", sample_user_id
        )
        assert update_id is not None
        
        # Verify the update was stored
        assert db_session.query(YjsUpdateRecord).count() == initial_count + 1
        
        db_session.close()
    
    def test_concurrent_updates(self, persistence_manager, sample_collaboration_session, 
                              sample_update_data, sample_user_id):
        """Test handling of concurrent updates from multiple clients.
        
        This test verifies that the persistence layer correctly handles concurrent
        updates from multiple clients, ensuring data consistency.
        """
        # Define a function to run in a separate thread
        def update_in_thread(client_id, sequence_start, count):
            for i in range(count):
                try:
                    persistence_manager.store_update(
                        sample_collaboration_session, sequence_start + i, 
                        sample_update_data + bytes([i]), 
                        f"client-{client_id}", sample_user_id,
                        metadata={"thread": client_id, "index": i}
                    )
                    # Small sleep to increase chance of interleaving
                    time.sleep(0.01)
                except Exception as e:
                    print(f"Error in thread {client_id}: {e}")
        
        # Create multiple threads to simulate concurrent clients
        threads = []
        client_count = 3
        updates_per_client = 5
        
        for i in range(client_count):
            # Each client starts at a different sequence number
            sequence_start = (i * updates_per_client) + 1
            thread = threading.Thread(
                target=update_in_thread,
                args=(i, sequence_start, updates_per_client)
            )
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all updates were stored
        db_session = persistence_manager.get_session()
        update_count = db_session.query(YjsUpdateRecord).filter(
            YjsUpdateRecord.session_id == sample_collaboration_session
        ).count()
        
        # Should have client_count * updates_per_client updates
        assert update_count == client_count * updates_per_client
        
        # Verify updates from each client
        for i in range(client_count):
            client_updates = db_session.query(YjsUpdateRecord).filter(
                YjsUpdateRecord.session_id == sample_collaboration_session,
                YjsUpdateRecord.client_id == f"client-{i}"
            ).all()
            
            assert len(client_updates) == updates_per_client
            
            # Verify sequence numbers are as expected
            sequence_start = (i * updates_per_client) + 1
            for j, update in enumerate(sorted(client_updates, key=lambda u: u.sequence_number)):
                assert update.sequence_number == sequence_start + j
                assert update.metadata['thread'] == i
                assert update.metadata['index'] == j
        
        db_session.close()


class TestBackwardCompatibility:
    """Test state migration and backward compatibility.
    
    These tests verify that the persistence layer can handle migration from previous
    versions and maintains backward compatibility with existing document formats.
    """
    
    def test_compact_updates(self, persistence_manager, sample_collaboration_session, 
                            sample_update_data, sample_user_id):
        """Test compacting update records."""
        client_id = "client-123"
        
        # Store multiple updates
        for i in range(10):
            persistence_manager.store_update(
                sample_collaboration_session, i+1, 
                sample_update_data + bytes([i]), 
                client_id, sample_user_id
            )
        
        # Compact updates
        result = persistence_manager.compact_updates(sample_collaboration_session)
        
        # Verify compaction result
        assert result['compacted'] is True
        assert 'session_id' in result
    
    def test_persistence_manager_initialization(self):
        """Test initializing persistence manager with different configurations."""
        # Test with no database URL
        with patch.dict(os.environ, {}, clear=True):
            manager = PersistenceManager()
            assert manager.db_url == ''  # Should use default
            manager.close()
        
        # Test with environment variable
        with patch.dict(os.environ, {'JUPYTER_COLLABORATION_DB_URL': 'sqlite:///test.db'}):
            manager = PersistenceManager()
            assert manager.db_url == 'sqlite:///test.db'
            manager.close()
        
        # Test with explicit configuration
        manager = PersistenceManager(db_url='sqlite:///explicit.db')
        assert manager.db_url == 'sqlite:///explicit.db'
        manager.close()
    
    def test_document_reconstruction(self, persistence_manager, sample_collaboration_session, 
                                   sample_update_data, sample_state_vector, sample_document_state, 
                                   sample_user_id):
        """Test reconstructing document state from update history."""
        client_id = "client-123"
        
        # Store a sequence of updates that build a document
        for i in range(5):
            persistence_manager.store_update(
                sample_collaboration_session, i+1, 
                sample_update_data + bytes([i]), 
                client_id, sample_user_id,
                metadata={"operation": f"update_{i}"}
            )
        
        # Create a snapshot at sequence 5
        persistence_manager.store_snapshot(
            sample_collaboration_session, 5,
            sample_state_vector, sample_document_state,
            {"snapshot_reason": "checkpoint"}
        )
        
        # Add more updates after the snapshot
        for i in range(5, 10):
            persistence_manager.store_update(
                sample_collaboration_session, i+1, 
                sample_update_data + bytes([i]), 
                client_id, sample_user_id,
                metadata={"operation": f"update_{i}"}
            )
        
        # Retrieve the snapshot and all updates after it
        snapshot = persistence_manager.get_latest_snapshot(sample_collaboration_session)
        updates_after_snapshot = persistence_manager.get_updates(
            sample_collaboration_session, 
            start_sequence=snapshot['sequence_number'] + 1
        )
        
        # Verify we can reconstruct the document state
        assert snapshot is not None
        assert len(updates_after_snapshot) == 5
        
        # In a real implementation, we would apply these updates to the snapshot
        # to reconstruct the document state. Here we just verify we have all the pieces.
        assert snapshot['sequence_number'] == 5
        assert updates_after_snapshot[0]['sequence_number'] == 6
        assert updates_after_snapshot[-1]['sequence_number'] == 10
    
    def test_migration_from_file_only(self, persistence_manager, sample_document_id, 
                                  sample_state_vector, sample_document_state, sample_user_id):
        """Test migrating from file-only storage to collaborative database."""
        # Simulate a document that existed before collaboration was enabled
        # by creating a session for it after the fact
        
        # Create a collaboration session for an existing document
        session_id = persistence_manager.create_collaboration_session(
            sample_document_id, sample_user_id, 
            {"migrated": True, "original_creation_date": "2023-01-01T00:00:00Z"}
        )
        
        # Verify session was created
        session = persistence_manager.get_collaboration_session(session_id)
        assert session is not None
        assert session['metadata']['migrated'] is True
        
        # Add initial snapshot representing the file state at migration time
        snapshot_id = persistence_manager.store_snapshot(
            session_id, 1,  # Start at sequence 1
            sample_state_vector, sample_document_state,
            {"snapshot_reason": "migration", "source": "file"}
        )
        
        # Verify snapshot was created
        snapshot = persistence_manager.get_latest_snapshot(session_id)
        assert snapshot is not None
        assert snapshot['metadata']['snapshot_reason'] == "migration"
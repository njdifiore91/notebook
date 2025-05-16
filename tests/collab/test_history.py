import os
import pytest
import json
import time
from unittest.mock import MagicMock, patch

# Import necessary components for testing
from notebook.collab.history import (
    VersionHistory,
    VersionSnapshot,
    HistoryManager,
    DocumentVersion,
)


@pytest.fixture
def mock_yjs_doc():
    """Create a mock Yjs document for testing."""
    mock_doc = MagicMock()
    mock_doc.get_state_vector = MagicMock(return_value=b"mock_state_vector")
    mock_doc.get_update = MagicMock(return_value=b"mock_update")
    return mock_doc


@pytest.fixture
def mock_db_connection():
    """Create a mock database connection for testing."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn


@pytest.fixture
def history_manager(mock_db_connection):
    """Create a HistoryManager instance for testing."""
    with patch("notebook.collab.history.get_db_connection", return_value=mock_db_connection):
        manager = HistoryManager("test_document_id")
        yield manager


@pytest.fixture
def sample_version_snapshots():
    """Create sample version snapshots for testing."""
    return [
        VersionSnapshot(
            snapshot_id="snapshot1",
            document_id="test_document_id",
            sequence_number=1,
            timestamp=time.time() - 3600,  # 1 hour ago
            state_vector=b"state_vector_1",
            document_state=b"document_state_1",
            metadata=json.dumps({
                "user_id": "user1",
                "username": "User One",
                "client_id": "client1",
                "cell_count": 3,
                "snapshot_label": "Initial version"
            })
        ),
        VersionSnapshot(
            snapshot_id="snapshot2",
            document_id="test_document_id",
            sequence_number=2,
            timestamp=time.time() - 1800,  # 30 minutes ago
            state_vector=b"state_vector_2",
            document_state=b"document_state_2",
            metadata=json.dumps({
                "user_id": "user2",
                "username": "User Two",
                "client_id": "client2",
                "cell_count": 4,
                "snapshot_label": "Added new cell"
            })
        ),
        VersionSnapshot(
            snapshot_id="snapshot3",
            document_id="test_document_id",
            sequence_number=3,
            timestamp=time.time() - 900,  # 15 minutes ago
            state_vector=b"state_vector_3",
            document_state=b"document_state_3",
            metadata=json.dumps({
                "user_id": "user1",
                "username": "User One",
                "client_id": "client1",
                "cell_count": 4,
                "snapshot_label": "Updated content"
            })
        ),
    ]


class TestVersionHistory:
    """Test the version history functionality."""

    def test_create_snapshot(self, history_manager, mock_yjs_doc):
        """Test creating a version snapshot."""
        # Setup mock cursor to return last inserted ID
        cursor = history_manager.db_connection.cursor.return_value
        cursor.lastrowid = 123
        
        # Create a snapshot
        snapshot_id = history_manager.create_snapshot(
            mock_yjs_doc,
            user_id="test_user",
            username="Test User",
            client_id="test_client",
            snapshot_label="Test snapshot"
        )
        
        # Verify the snapshot was created
        assert snapshot_id is not None
        assert cursor.execute.called
        
        # Verify the correct data was passed to the database
        args = cursor.execute.call_args[0]
        assert "INSERT INTO version_snapshots" in args[0]
        assert "test_document_id" in args[1]
        assert "test_user" in args[1]
        assert "Test snapshot" in args[1]

    def test_get_version_history(self, history_manager, sample_version_snapshots):
        """Test retrieving version history."""
        # Setup mock cursor to return sample snapshots
        cursor = history_manager.db_connection.cursor.return_value
        cursor.fetchall.return_value = [
            (s.snapshot_id, s.document_id, s.sequence_number, s.timestamp, 
             s.state_vector, s.document_state, s.metadata)
            for s in sample_version_snapshots
        ]
        
        # Get version history
        history = history_manager.get_version_history(limit=10)
        
        # Verify the history was retrieved
        assert len(history) == 3
        assert cursor.execute.called
        
        # Verify the history contains the expected data
        assert history[0].snapshot_id == "snapshot3"  # Most recent first
        assert history[1].snapshot_id == "snapshot2"
        assert history[2].snapshot_id == "snapshot1"
        
        # Verify user attribution is preserved
        assert json.loads(history[0].metadata)["user_id"] == "user1"
        assert json.loads(history[1].metadata)["user_id"] == "user2"
        assert json.loads(history[2].metadata)["user_id"] == "user1"

    def test_get_version_by_id(self, history_manager, sample_version_snapshots):
        """Test retrieving a specific version by ID."""
        # Setup mock cursor to return a specific snapshot
        cursor = history_manager.db_connection.cursor.return_value
        snapshot = sample_version_snapshots[1]  # snapshot2
        cursor.fetchone.return_value = (
            snapshot.snapshot_id, snapshot.document_id, snapshot.sequence_number,
            snapshot.timestamp, snapshot.state_vector, snapshot.document_state,
            snapshot.metadata
        )
        
        # Get version by ID
        version = history_manager.get_version_by_id("snapshot2")
        
        # Verify the version was retrieved
        assert version is not None
        assert cursor.execute.called
        
        # Verify the version contains the expected data
        assert version.snapshot_id == "snapshot2"
        assert version.sequence_number == 2
        assert json.loads(version.metadata)["username"] == "User Two"

    def test_get_version_by_timestamp(self, history_manager, sample_version_snapshots):
        """Test retrieving a version closest to a specific timestamp."""
        # Setup mock cursor to return a specific snapshot
        cursor = history_manager.db_connection.cursor.return_value
        snapshot = sample_version_snapshots[1]  # snapshot2
        cursor.fetchone.return_value = (
            snapshot.snapshot_id, snapshot.document_id, snapshot.sequence_number,
            snapshot.timestamp, snapshot.state_vector, snapshot.document_state,
            snapshot.metadata
        )
        
        # Get version by timestamp (around 30 minutes ago)
        target_time = time.time() - 1800
        version = history_manager.get_version_by_timestamp(target_time)
        
        # Verify the version was retrieved
        assert version is not None
        assert cursor.execute.called
        
        # Verify the version contains the expected data
        assert version.snapshot_id == "snapshot2"
        assert version.sequence_number == 2

    def test_delete_version(self, history_manager):
        """Test deleting a version snapshot."""
        # Delete a version
        history_manager.delete_version("snapshot1")
        
        # Verify the delete operation was called
        cursor = history_manager.db_connection.cursor.return_value
        assert cursor.execute.called
        
        # Verify the correct data was passed to the database
        args = cursor.execute.call_args[0]
        assert "DELETE FROM version_snapshots" in args[0]
        assert "snapshot1" in args[1]


class TestVersionRestoration:
    """Test the version restoration functionality."""

    def test_restore_version(self, history_manager, mock_yjs_doc, sample_version_snapshots):
        """Test restoring a document to a previous version."""
        # Setup mock cursor to return a specific snapshot
        cursor = history_manager.db_connection.cursor.return_value
        snapshot = sample_version_snapshots[1]  # snapshot2
        cursor.fetchone.return_value = (
            snapshot.snapshot_id, snapshot.document_id, snapshot.sequence_number,
            snapshot.timestamp, snapshot.state_vector, snapshot.document_state,
            snapshot.metadata
        )
        
        # Restore to a specific version
        success = history_manager.restore_version("snapshot2", mock_yjs_doc)
        
        # Verify the restoration was successful
        assert success is True
        assert cursor.execute.called
        
        # Verify the document was updated with the restored state
        assert mock_yjs_doc.apply_update.called
        mock_yjs_doc.apply_update.assert_called_with(b"document_state_2")

    def test_restore_version_not_found(self, history_manager, mock_yjs_doc):
        """Test handling of restoration when version is not found."""
        # Setup mock cursor to return None (version not found)
        cursor = history_manager.db_connection.cursor.return_value
        cursor.fetchone.return_value = None
        
        # Attempt to restore a non-existent version
        success = history_manager.restore_version("non_existent_snapshot", mock_yjs_doc)
        
        # Verify the restoration failed
        assert success is False
        assert cursor.execute.called
        
        # Verify the document was not updated
        assert not mock_yjs_doc.apply_update.called


class TestVersionDiff:
    """Test the version diff visualization functionality."""

    def test_get_version_diff(self, history_manager, sample_version_snapshots):
        """Test generating a diff between two versions."""
        # Setup mock cursor to return specific snapshots
        cursor = history_manager.db_connection.cursor.return_value
        snapshot1 = sample_version_snapshots[0]  # snapshot1
        snapshot2 = sample_version_snapshots[1]  # snapshot2
        
        # Mock the fetchone method to return different snapshots based on the query
        def mock_fetchone(*args, **kwargs):
            query = cursor.execute.call_args[0][0]
            if "snapshot1" in cursor.execute.call_args[0][1]:
                return (
                    snapshot1.snapshot_id, snapshot1.document_id, snapshot1.sequence_number,
                    snapshot1.timestamp, snapshot1.state_vector, snapshot1.document_state,
                    snapshot1.metadata
                )
            else:
                return (
                    snapshot2.snapshot_id, snapshot2.document_id, snapshot2.sequence_number,
                    snapshot2.timestamp, snapshot2.state_vector, snapshot2.document_state,
                    snapshot2.metadata
                )
        
        cursor.fetchone = MagicMock(side_effect=mock_fetchone)
        
        # Mock the diff generation function
        with patch("notebook.collab.history.generate_diff", return_value={
            "added": ["cell_id_4"],
            "removed": [],
            "modified": ["cell_id_2"],
            "unchanged": ["cell_id_1", "cell_id_3"]
        }):
            # Generate diff between two versions
            diff = history_manager.get_version_diff("snapshot1", "snapshot2")
        
        # Verify the diff was generated
        assert diff is not None
        assert cursor.execute.called
        
        # Verify the diff contains the expected data
        assert "added" in diff
        assert "removed" in diff
        assert "modified" in diff
        assert "unchanged" in diff
        assert "cell_id_4" in diff["added"]
        assert "cell_id_2" in diff["modified"]

    def test_get_version_diff_same_version(self, history_manager):
        """Test handling of diff generation when comparing the same version."""
        # Generate diff between the same version
        diff = history_manager.get_version_diff("snapshot1", "snapshot1")
        
        # Verify an empty diff is returned
        assert diff is not None
        assert diff["added"] == []
        assert diff["removed"] == []
        assert diff["modified"] == []
        # Note: unchanged cells would still be listed


class TestUserAttribution:
    """Test the user attribution functionality in version history."""

    def test_user_attribution_in_snapshots(self, history_manager, sample_version_snapshots):
        """Test that user attribution is correctly stored in snapshots."""
        # Setup mock cursor to return sample snapshots
        cursor = history_manager.db_connection.cursor.return_value
        cursor.fetchall.return_value = [
            (s.snapshot_id, s.document_id, s.sequence_number, s.timestamp, 
             s.state_vector, s.document_state, s.metadata)
            for s in sample_version_snapshots
        ]
        
        # Get version history
        history = history_manager.get_version_history(limit=10)
        
        # Verify user attribution in each snapshot
        for i, version in enumerate(history):
            metadata = json.loads(version.metadata)
            assert "user_id" in metadata
            assert "username" in metadata
            assert "client_id" in metadata
            
            # Verify specific user attributions
            if version.snapshot_id == "snapshot1":
                assert metadata["user_id"] == "user1"
                assert metadata["username"] == "User One"
            elif version.snapshot_id == "snapshot2":
                assert metadata["user_id"] == "user2"
                assert metadata["username"] == "User Two"

    def test_get_user_contributions(self, history_manager, sample_version_snapshots):
        """Test retrieving contributions by a specific user."""
        # Setup mock cursor to return filtered snapshots
        cursor = history_manager.db_connection.cursor.return_value
        # Filter for user1's snapshots
        user1_snapshots = [s for s in sample_version_snapshots 
                          if json.loads(s.metadata)["user_id"] == "user1"]
        cursor.fetchall.return_value = [
            (s.snapshot_id, s.document_id, s.sequence_number, s.timestamp, 
             s.state_vector, s.document_state, s.metadata)
            for s in user1_snapshots
        ]
        
        # Get contributions by user1
        contributions = history_manager.get_user_contributions("user1")
        
        # Verify the contributions were retrieved
        assert len(contributions) == 2  # user1 has 2 snapshots
        assert cursor.execute.called
        
        # Verify the contributions contain the expected data
        assert contributions[0].snapshot_id == "snapshot3"  # Most recent first
        assert contributions[1].snapshot_id == "snapshot1"
        
        # Verify all contributions are from user1
        for version in contributions:
            metadata = json.loads(version.metadata)
            assert metadata["user_id"] == "user1"


class TestVersionTimelineVisualization:
    """Test the version timeline visualization functionality."""

    def test_get_version_timeline(self, history_manager, sample_version_snapshots):
        """Test retrieving a timeline of versions with metadata for visualization."""
        # Setup mock cursor to return sample snapshots
        cursor = history_manager.db_connection.cursor.return_value
        cursor.fetchall.return_value = [
            (s.snapshot_id, s.document_id, s.sequence_number, s.timestamp, 
             s.state_vector, s.document_state, s.metadata)
            for s in sample_version_snapshots
        ]
        
        # Get version timeline
        timeline = history_manager.get_version_timeline(limit=10)
        
        # Verify the timeline was retrieved
        assert len(timeline) == 3
        assert cursor.execute.called
        
        # Verify the timeline contains the expected data
        assert timeline[0]["snapshot_id"] == "snapshot3"  # Most recent first
        assert timeline[1]["snapshot_id"] == "snapshot2"
        assert timeline[2]["snapshot_id"] == "snapshot1"
        
        # Verify timeline entries contain visualization metadata
        for entry in timeline:
            assert "timestamp" in entry
            assert "username" in entry
            assert "snapshot_label" in entry
            assert "sequence_number" in entry

    def test_get_version_timeline_with_filters(self, history_manager):
        """Test retrieving a filtered timeline of versions."""
        # Setup mock cursor
        cursor = history_manager.db_connection.cursor.return_value
        cursor.fetchall.return_value = []  # Empty result for simplicity
        
        # Get filtered timeline (by user and time range)
        start_time = time.time() - 3600  # 1 hour ago
        end_time = time.time()  # now
        timeline = history_manager.get_version_timeline(
            limit=10,
            user_id="user1",
            start_time=start_time,
            end_time=end_time
        )
        
        # Verify the query was executed with filters
        assert cursor.execute.called
        args = cursor.execute.call_args[0]
        assert "WHERE" in args[0]
        assert "user_id" in args[0]
        assert "timestamp >= ?" in args[0]
        assert "timestamp <= ?" in args[0]
        assert "user1" in args[1]
        assert start_time in args[1]
        assert end_time in args[1]


class TestIntegrationWithYjs:
    """Test integration with Yjs document updates."""

    def test_record_yjs_update(self, history_manager, mock_yjs_doc):
        """Test recording a Yjs update in the history."""
        # Setup mock cursor
        cursor = history_manager.db_connection.cursor.return_value
        cursor.lastrowid = 456
        
        # Record a Yjs update
        update_id = history_manager.record_update(
            update_data=b"yjs_update_data",
            user_id="test_user",
            client_id="test_client",
            metadata={"operation_type": "cell_edit", "cell_id": "cell123"}
        )
        
        # Verify the update was recorded
        assert update_id is not None
        assert cursor.execute.called
        
        # Verify the correct data was passed to the database
        args = cursor.execute.call_args[0]
        assert "INSERT INTO yjs_updates" in args[0]
        assert "test_document_id" in args[1]
        assert "test_user" in args[1]
        assert "test_client" in args[1]
        assert b"yjs_update_data" in args[1]

    def test_get_updates_between_snapshots(self, history_manager):
        """Test retrieving Yjs updates between two snapshots."""
        # Setup mock cursor
        cursor = history_manager.db_connection.cursor.return_value
        cursor.fetchall.return_value = [
            (1, "test_document_id", 1, time.time() - 3000, b"update1", "user1", "client1", "{}"),
            (2, "test_document_id", 2, time.time() - 2000, b"update2", "user2", "client2", "{}"),
            (3, "test_document_id", 3, time.time() - 1000, b"update3", "user1", "client1", "{}")
        ]
        
        # Get updates between snapshots
        updates = history_manager.get_updates_between_snapshots("snapshot1", "snapshot3")
        
        # Verify the updates were retrieved
        assert len(updates) == 3
        assert cursor.execute.called
        
        # Verify the updates contain the expected data
        assert updates[0][4] == b"update1"  # update_data
        assert updates[1][4] == b"update2"
        assert updates[2][4] == b"update3"


class TestPerformanceAndScaling:
    """Test performance and scaling aspects of the version history system."""

    def test_snapshot_pruning(self, history_manager):
        """Test pruning old snapshots to manage storage growth."""
        # Setup mock cursor
        cursor = history_manager.db_connection.cursor.return_value
        cursor.rowcount = 5  # Simulate 5 snapshots pruned
        
        # Prune snapshots older than 30 days, keeping at least 10
        max_age = 30 * 24 * 60 * 60  # 30 days in seconds
        min_snapshots = 10
        pruned_count = history_manager.prune_old_snapshots(max_age, min_snapshots)
        
        # Verify the pruning was executed
        assert cursor.execute.called
        assert pruned_count == 5
        
        # Verify the correct parameters were used
        args = cursor.execute.call_args[0]
        assert "DELETE FROM version_snapshots" in args[0]
        assert "test_document_id" in args[1]
        assert time.time() - max_age in args[1]
        assert min_snapshots in args[1]

    def test_create_milestone_snapshot(self, history_manager, mock_yjs_doc):
        """Test creating a milestone snapshot for long-term retention."""
        # Setup mock cursor
        cursor = history_manager.db_connection.cursor.return_value
        cursor.lastrowid = 789
        
        # Create a milestone snapshot
        snapshot_id = history_manager.create_milestone_snapshot(
            mock_yjs_doc,
            user_id="admin_user",
            username="Admin User",
            milestone_label="Version 1.0 Release",
            retention_policy="permanent"
        )
        
        # Verify the milestone was created
        assert snapshot_id is not None
        assert cursor.execute.called
        
        # Verify the correct data was passed to the database
        args = cursor.execute.call_args[0]
        assert "INSERT INTO version_snapshots" in args[0]
        assert "test_document_id" in args[1]
        assert "admin_user" in args[1]
        assert "Version 1.0 Release" in args[1]
        assert "permanent" in args[1]


if __name__ == "__main__":
    pytest.main(['-xvs', __file__])
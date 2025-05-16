import pytest
import asyncio
import json
from unittest.mock import MagicMock, patch

# Import necessary Yjs and collaboration-related modules
try:
    import Y
except ImportError:
    Y = None


@pytest.fixture
def yjs_doc():
    """Create a fresh Yjs document for testing."""
    if Y is None:
        pytest.skip("Yjs not available")
    doc = Y.Doc()
    try:
        yield doc
    finally:
        doc.destroy()


@pytest.fixture
def mock_version_history():
    """Mock version history service for testing."""
    history_service = MagicMock()
    # Mock a list of versions with user attribution
    versions = [
        {
            "id": "v1",
            "timestamp": 1620000000000,
            "user": {"id": "user1", "name": "User 1"},
            "changes": ["Added cell 1"],
        },
        {
            "id": "v2",
            "timestamp": 1620000100000,
            "user": {"id": "user2", "name": "User 2"},
            "changes": ["Modified cell 1"],
        },
        {
            "id": "v3",
            "timestamp": 1620000200000,
            "user": {"id": "user1", "name": "User 1"},
            "changes": ["Added cell 2"],
        },
    ]
    history_service.get_versions.return_value = versions
    history_service.get_version_details.side_effect = lambda version_id: next(
        (v for v in versions if v["id"] == version_id), None
    )
    history_service.restore_version.return_value = True
    history_service.get_diff.return_value = {
        "added": ["New content"],
        "removed": ["Old content"],
        "modified": [{"before": "Original", "after": "Modified"}],
    }
    return history_service


@pytest.fixture
def mock_collab_provider(yjs_doc, mock_version_history):
    """Mock collaboration provider for testing."""
    provider = MagicMock()
    provider.doc = yjs_doc
    provider.version_history = mock_version_history
    provider.get_document_state.return_value = {"cells": [{"id": "cell1", "content": "print('Hello')"}, {"id": "cell2", "content": "print('World')"}]}
    return provider


@pytest.fixture
def mock_users():
    """Mock users for testing."""
    return [
        {"id": "user1", "name": "User 1"},
        {"id": "user2", "name": "User 2"},
        {"id": "user3", "name": "User 3"},
    ]


@pytest.mark.asyncio
async def test_version_history_recording(mock_collab_provider, mock_users):
    """Test that document changes are properly recorded with user attribution."""
    # Simulate a change by user1
    user = mock_users[0]
    change_data = {"cell_id": "cell1", "content": "print('Updated')", "user": user}
    
    # Apply the change
    with patch("notebook.collab.history.record_change") as mock_record:
        await mock_collab_provider.apply_change(change_data)
        
        # Verify the change was recorded with proper attribution
        mock_record.assert_called_once()
        args, kwargs = mock_record.call_args
        assert args[0] == mock_collab_provider.doc
        assert args[1]["user"]["id"] == user["id"]
        assert "timestamp" in args[1]


@pytest.mark.asyncio
async def test_version_timeline_retrieval(mock_collab_provider):
    """Test version timeline visualization and navigation."""
    # Get the version history
    versions = await mock_collab_provider.version_history.get_versions()
    
    # Verify we have the expected versions
    assert len(versions) == 3
    assert versions[0]["id"] == "v1"
    assert versions[1]["id"] == "v2"
    assert versions[2]["id"] == "v3"
    
    # Verify user attribution
    assert versions[0]["user"]["id"] == "user1"
    assert versions[1]["user"]["id"] == "user2"
    assert versions[2]["user"]["id"] == "user1"
    
    # Verify timestamps are in ascending order
    assert versions[0]["timestamp"] < versions[1]["timestamp"]
    assert versions[1]["timestamp"] < versions[2]["timestamp"]


@pytest.mark.asyncio
async def test_version_details_retrieval(mock_collab_provider):
    """Test retrieval of specific version details."""
    # Get details for version v2
    version_details = await mock_collab_provider.version_history.get_version_details("v2")
    
    # Verify the details
    assert version_details["id"] == "v2"
    assert version_details["user"]["id"] == "user2"
    assert version_details["changes"] == ["Modified cell 1"]


@pytest.mark.asyncio
async def test_document_restoration(mock_collab_provider):
    """Test document restoration to previous states."""
    # Restore to version v1
    success = await mock_collab_provider.version_history.restore_version("v1")
    
    # Verify restoration was successful
    assert success is True
    
    # Verify the document state after restoration
    with patch("notebook.collab.provider.get_document_state") as mock_get_state:
        mock_get_state.return_value = {"cells": [{"id": "cell1", "content": "print('Hello')"}]}
        state = await mock_collab_provider.get_document_state()
        
        # Verify the state matches the expected state for version v1
        assert len(state["cells"]) == 1
        assert state["cells"][0]["id"] == "cell1"
        assert state["cells"][0]["content"] == "print('Hello')"


@pytest.mark.asyncio
async def test_change_attribution(mock_collab_provider, mock_users):
    """Test that changes are correctly attributed to specific users."""
    # Get the version history
    versions = await mock_collab_provider.version_history.get_versions()
    
    # Create a map of user IDs to names for verification
    user_map = {user["id"]: user["name"] for user in mock_users}
    
    # Verify each version has correct user attribution
    for version in versions:
        assert "user" in version
        assert "id" in version["user"]
        user_id = version["user"]["id"]
        
        # If this user is in our mock users, verify the name matches
        if user_id in user_map:
            assert version["user"]["name"] == user_map[user_id]


@pytest.mark.asyncio
async def test_diff_visualization(mock_collab_provider):
    """Test diff visualization between different document versions."""
    # Get diff between versions v1 and v2
    diff = await mock_collab_provider.version_history.get_diff("v1", "v2")
    
    # Verify the diff structure
    assert "added" in diff
    assert "removed" in diff
    assert "modified" in diff
    
    # Verify the diff content
    assert len(diff["added"]) > 0
    assert len(diff["removed"]) > 0
    assert len(diff["modified"]) > 0
    
    # Verify a specific modification
    assert diff["modified"][0]["before"] == "Original"
    assert diff["modified"][0]["after"] == "Modified"


@pytest.mark.asyncio
async def test_version_history_ui_integration(mock_collab_provider):
    """Test integration with UI components for version history."""
    # Mock UI component for version history
    mock_ui = MagicMock()
    
    # Simulate loading versions into the UI
    versions = await mock_collab_provider.version_history.get_versions()
    mock_ui.load_versions(versions)
    
    # Verify UI received the versions
    mock_ui.load_versions.assert_called_once_with(versions)
    
    # Simulate selecting a version in the UI
    mock_ui.select_version("v2")
    
    # Verify UI shows the correct version details
    version_details = await mock_collab_provider.version_history.get_version_details("v2")
    mock_ui.show_version_details.assert_called_once_with(version_details)


@pytest.mark.asyncio
async def test_concurrent_changes_history(mock_collab_provider, mock_users):
    """Test that concurrent changes from different users are properly recorded in history."""
    # Simulate concurrent changes by different users
    changes = [
        {"cell_id": "cell1", "content": "print('User 1 change')", "user": mock_users[0]},
        {"cell_id": "cell2", "content": "print('User 2 change')", "user": mock_users[1]},
        {"cell_id": "cell3", "content": "print('User 3 change')", "user": mock_users[2]},
    ]
    
    # Apply changes concurrently
    with patch("notebook.collab.history.record_change") as mock_record:
        tasks = [mock_collab_provider.apply_change(change) for change in changes]
        await asyncio.gather(*tasks)
        
        # Verify all changes were recorded
        assert mock_record.call_count == 3
        
        # Verify each change has correct user attribution
        recorded_users = [call.args[1]["user"]["id"] for call in mock_record.call_args_list]
        expected_users = [user["id"] for user in mock_users]
        assert sorted(recorded_users) == sorted(expected_users)


@pytest.mark.asyncio
async def test_large_history_performance(mock_collab_provider):
    """Test performance with a large history of changes."""
    # Mock a large history
    large_history = []
    for i in range(1000):
        large_history.append({
            "id": f"v{i+1}",
            "timestamp": 1620000000000 + i * 1000,
            "user": {"id": f"user{i % 3 + 1}", "name": f"User {i % 3 + 1}"},
            "changes": [f"Change {i+1}"],
        })
    
    # Replace the mock history with the large one
    mock_collab_provider.version_history.get_versions.return_value = large_history
    
    # Measure time to retrieve and process the history
    start_time = asyncio.get_event_loop().time()
    versions = await mock_collab_provider.version_history.get_versions()
    end_time = asyncio.get_event_loop().time()
    
    # Verify we got all versions
    assert len(versions) == 1000
    
    # Check that retrieval time is reasonable (adjust threshold as needed)
    retrieval_time = end_time - start_time
    assert retrieval_time < 1.0, f"History retrieval took too long: {retrieval_time} seconds"


@pytest.mark.asyncio
async def test_history_persistence(mock_collab_provider):
    """Test that version history persists across server restarts."""
    # Mock server restart by creating a new provider with the same document
    new_provider = MagicMock()
    new_provider.doc = mock_collab_provider.doc
    new_provider.version_history = mock_collab_provider.version_history
    
    # Verify history is still available after "restart"
    versions_before = await mock_collab_provider.version_history.get_versions()
    versions_after = await new_provider.version_history.get_versions()
    
    # Compare versions before and after
    assert len(versions_before) == len(versions_after)
    for i in range(len(versions_before)):
        assert versions_before[i]["id"] == versions_after[i]["id"]
        assert versions_before[i]["user"]["id"] == versions_after[i]["user"]["id"]
        assert versions_before[i]["timestamp"] == versions_after[i]["timestamp"]
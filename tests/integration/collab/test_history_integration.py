import asyncio
import pytest
import json
import time
from typing import List, Dict, Any, Callable, Awaitable

# Skip tests if y_py is not installed
pytest.importorskip("y_py")


@pytest.mark.asyncio
async def test_version_history_recording(jp_serverapp, jp_ws_client):
    """
    Test that document changes are properly recorded in the version history.
    
    Verifies that edits made by different users are recorded with correct attribution.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1", username="User One")
    client2 = await jp_ws_client(user_id="user2", username="User Two")
    
    # Both clients subscribe to the same document
    doc_id = "test-history-recording-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a cell
    cell1_id = "cell1"
    cell1_content = "# Heading created by User One"
    await client1.add_cell(doc_id, cell1_id, cell1_content, "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 2 adds another cell
    cell2_id = "cell2"
    cell2_content = "print('Code added by User Two')" 
    await client2.add_cell(doc_id, cell2_id, cell2_content, "code")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 modifies their cell
    cell1_updated = "# Updated heading by User One"
    await client1.update_cell_content(doc_id, cell1_id, cell1_updated)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Retrieve version history
    history = await client1.get_version_history(doc_id)
    
    # Verify history contains at least 3 versions (initial + 3 edits)
    assert len(history) >= 3, "Version history should contain at least 3 entries"
    
    # Verify user attribution in history
    user_entries = {}
    for entry in history:
        user_id = entry.get("user_id")
        if user_id not in user_entries:
            user_entries[user_id] = 0
        user_entries[user_id] += 1
    
    # Both users should have entries in the history
    assert "user1" in user_entries, "User1 should have entries in the version history"
    assert "user2" in user_entries, "User2 should have entries in the version history"
    
    # Verify timestamps are in descending order (most recent first)
    timestamps = [entry.get("timestamp") for entry in history]
    assert all(timestamps[i] >= timestamps[i+1] for i in range(len(timestamps)-1)), "History should be in descending timestamp order"


@pytest.mark.asyncio
async def test_version_timeline_navigation(jp_serverapp, jp_ws_client):
    """
    Test version timeline visualization and navigation.
    
    Verifies that users can view and navigate through the version timeline.
    """
    # Create a client
    client = await jp_ws_client(user_id="user1", username="User One")
    
    # Subscribe to a document
    doc_id = "test-version-timeline-doc"
    await client.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Create multiple versions by adding and modifying cells
    for i in range(5):
        cell_id = f"cell_{i}"
        cell_content = f"# Version {i} content"
        await client.add_cell(doc_id, cell_id, cell_content, "markdown")
        await asyncio.sleep(0.2)  # Small delay between operations
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Retrieve version timeline
    timeline = await client.get_version_timeline(doc_id)
    
    # Verify timeline contains at least 5 versions
    assert len(timeline) >= 5, "Version timeline should contain at least 5 entries"
    
    # Verify timeline entries have required fields
    for entry in timeline:
        assert "snapshot_id" in entry, "Timeline entry should have snapshot_id"
        assert "timestamp" in entry, "Timeline entry should have timestamp"
        assert "username" in entry, "Timeline entry should have username"
        assert "sequence_number" in entry, "Timeline entry should have sequence_number"
    
    # Get a specific version from the timeline
    middle_version = timeline[len(timeline) // 2]
    version_id = middle_version["snapshot_id"]
    
    # Retrieve the specific version
    version_data = await client.get_version_by_id(doc_id, version_id)
    
    # Verify the version data contains document state
    assert "document_state" in version_data, "Version data should contain document state"
    assert "metadata" in version_data, "Version data should contain metadata"
    
    # Verify we can navigate to a version by timestamp
    timestamp = middle_version["timestamp"]
    version_by_time = await client.get_version_by_timestamp(doc_id, timestamp)
    
    # Should be the same version or very close
    assert version_by_time["snapshot_id"] == version_id or \
           abs(version_by_time["timestamp"] - timestamp) < 1000, \
           "Version by timestamp should match or be very close to requested time"


@pytest.mark.asyncio
async def test_document_restoration(jp_serverapp, jp_ws_client):
    """
    Test document restoration to previous states.
    
    Verifies that a document can be restored to a previous version.
    """
    # Create a client
    client = await jp_ws_client(user_id="user1", username="User One")
    
    # Subscribe to a document
    doc_id = "test-document-restoration-doc"
    await client.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Create initial version with two cells
    await client.add_cell(doc_id, "cell1", "# First cell", "markdown")
    await client.add_cell(doc_id, "cell2", "print('Second cell')" , "code")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Get the current document state to restore later
    initial_state = await client.get_document_state(doc_id)
    
    # Get version history to find the initial version ID
    history = await client.get_version_history(doc_id)
    initial_version_id = history[-1]["snapshot_id"]  # Oldest version
    
    # Make additional changes to the document
    await client.update_cell_content(doc_id, "cell1", "# Modified first cell")
    await client.add_cell(doc_id, "cell3", "# Third cell added later", "markdown")
    await client.delete_cell(doc_id, "cell2")  # Delete the second cell
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify the document has changed
    modified_state = await client.get_document_state(doc_id)
    assert modified_state != initial_state, "Document should have changed after modifications"
    
    # Restore to the initial version
    restore_success = await client.restore_version(doc_id, initial_version_id)
    assert restore_success, "Version restoration should succeed"
    
    # Wait for restoration to complete
    await asyncio.sleep(0.5)
    
    # Get the restored document state
    restored_state = await client.get_document_state(doc_id)
    
    # Verify the document has been restored to match the initial state
    # Note: We compare the cells structure rather than the entire state as some metadata might differ
    assert len(restored_state["cells"]) == len(initial_state["cells"]), "Restored document should have the same number of cells"
    
    # Check that cell1 and cell2 exist with original content
    assert "cell1" in restored_state["cells"], "cell1 should exist in restored document"
    assert restored_state["cells"]["cell1"]["source"] == "# First cell", "cell1 content should be restored"
    assert "cell2" in restored_state["cells"], "cell2 should exist in restored document"
    assert restored_state["cells"]["cell2"]["source"] == "print('Second cell')", "cell2 content should be restored"
    
    # Check that cell3 doesn't exist in the restored state
    assert "cell3" not in restored_state["cells"], "cell3 should not exist in restored document"


@pytest.mark.asyncio
async def test_change_attribution(jp_serverapp, jp_ws_client):
    """
    Test that changes are correctly attributed to specific users.
    
    Verifies that each change in the version history is correctly attributed to the user who made it.
    """
    # Create three clients with different user identities
    client1 = await jp_ws_client(user_id="user1", username="User One")
    client2 = await jp_ws_client(user_id="user2", username="User Two")
    client3 = await jp_ws_client(user_id="user3", username="User Three")
    
    # All clients subscribe to the same document
    doc_id = "test-change-attribution-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    await client3.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Each client makes specific changes
    # Client 1 adds a markdown cell
    await client1.add_cell(doc_id, "cell1", "# Heading by User One", "markdown")
    await asyncio.sleep(0.5)
    
    # Client 2 adds a code cell
    await client2.add_cell(doc_id, "cell2", "print('Code by User Two')", "code")
    await asyncio.sleep(0.5)
    
    # Client 3 adds another markdown cell
    await client3.add_cell(doc_id, "cell3", "## Subheading by User Three", "markdown")
    await asyncio.sleep(0.5)
    
    # Client 1 modifies Client 3's cell
    await client1.update_cell_content(doc_id, "cell3", "## Modified by User One")
    await asyncio.sleep(0.5)
    
    # Get version history
    history = await client1.get_version_history(doc_id)
    
    # Create a mapping of changes to users
    change_map = {}
    for entry in history:
        user_id = entry.get("user_id")
        if user_id not in change_map:
            change_map[user_id] = []
        change_map[user_id].append(entry)
    
    # Verify each user's changes are recorded
    assert "user1" in change_map, "User1's changes should be recorded"
    assert len(change_map["user1"]) >= 2, "User1 should have at least 2 changes recorded"
    
    assert "user2" in change_map, "User2's changes should be recorded"
    assert len(change_map["user2"]) >= 1, "User2 should have at least 1 change recorded"
    
    assert "user3" in change_map, "User3's changes should be recorded"
    assert len(change_map["user3"]) >= 1, "User3 should have at least 1 change recorded"
    
    # Get user-specific contributions
    user1_contributions = await client1.get_user_contributions(doc_id, "user1")
    user2_contributions = await client1.get_user_contributions(doc_id, "user2")
    user3_contributions = await client1.get_user_contributions(doc_id, "user3")
    
    # Verify user-specific contributions match the expected counts
    assert len(user1_contributions) >= 2, "User1 should have at least 2 contributions"
    assert len(user2_contributions) >= 1, "User2 should have at least 1 contribution"
    assert len(user3_contributions) >= 1, "User3 should have at least 1 contribution"
    
    # Verify username is correctly recorded in the metadata
    for entry in user1_contributions:
        assert entry.get("username") == "User One", "Username should be correctly recorded"
    
    for entry in user2_contributions:
        assert entry.get("username") == "User Two", "Username should be correctly recorded"
    
    for entry in user3_contributions:
        assert entry.get("username") == "User Three", "Username should be correctly recorded"


@pytest.mark.asyncio
async def test_diff_visualization(jp_serverapp, jp_ws_client):
    """
    Test diff visualization between different document versions.
    
    Verifies that differences between versions can be visualized correctly.
    """
    # Create a client
    client = await jp_ws_client(user_id="user1", username="User One")
    
    # Subscribe to a document
    doc_id = "test-diff-visualization-doc"
    await client.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Create initial version with two cells
    await client.add_cell(doc_id, "cell1", "# Original heading", "markdown")
    await client.add_cell(doc_id, "cell2", "print('Original code')" , "code")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Get the current version ID
    history = await client.get_version_history(doc_id)
    first_version_id = history[0]["snapshot_id"]  # Most recent version
    
    # Make changes to the document
    await client.update_cell_content(doc_id, "cell1", "# Modified heading")
    await client.update_cell_content(doc_id, "cell2", "print('Modified code')")
    await client.add_cell(doc_id, "cell3", "# New cell added", "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Get the updated version ID
    history = await client.get_version_history(doc_id)
    second_version_id = history[0]["snapshot_id"]  # Most recent version
    
    # Get diff between versions
    diff = await client.get_version_diff(doc_id, first_version_id, second_version_id)
    
    # Verify diff structure
    assert "added" in diff, "Diff should contain 'added' section"
    assert "removed" in diff, "Diff should contain 'removed' section"
    assert "modified" in diff, "Diff should contain 'modified' section"
    assert "unchanged" in diff, "Diff should contain 'unchanged' section"
    
    # Verify diff content
    assert "cell3" in diff["added"], "cell3 should be in the 'added' section"
    assert "cell1" in diff["modified"], "cell1 should be in the 'modified' section"
    assert "cell2" in diff["modified"], "cell2 should be in the 'modified' section"
    assert len(diff["removed"]) == 0, "No cells were removed"
    
    # Verify cell-level diff details
    cell_diffs = diff.get("cell_diffs", {})
    if cell_diffs:  # If detailed cell diffs are available
        assert "cell1" in cell_diffs, "cell1 should have diff details"
        assert "cell2" in cell_diffs, "cell2 should have diff details"
        
        # Check that cell1 diff shows the heading change
        assert "Original heading" in str(cell_diffs["cell1"]), "cell1 diff should contain original content"
        assert "Modified heading" in str(cell_diffs["cell1"]), "cell1 diff should contain modified content"
        
        # Check that cell2 diff shows the code change
        assert "Original code" in str(cell_diffs["cell2"]), "cell2 diff should contain original content"
        assert "Modified code" in str(cell_diffs["cell2"]), "cell2 diff should contain modified content"


@pytest.mark.asyncio
async def test_version_history_persistence(jp_serverapp, jp_ws_client):
    """
    Test that version history persists across server restarts.
    
    Verifies that document history is properly stored and can be retrieved after a server restart.
    """
    # Create a client
    client = await jp_ws_client(user_id="user1", username="User One")
    
    # Subscribe to a document
    doc_id = "test-history-persistence-doc"
    await client.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Create multiple versions
    for i in range(3):
        cell_id = f"cell_{i}"
        cell_content = f"# Content version {i}"
        await client.add_cell(doc_id, cell_id, cell_content, "markdown")
        await asyncio.sleep(0.5)  # Ensure each change is processed separately
    
    # Get the version history before restart
    history_before = await client.get_version_history(doc_id)
    assert len(history_before) >= 3, "Should have at least 3 versions before restart"
    
    # Store version IDs for later comparison
    version_ids_before = [entry["snapshot_id"] for entry in history_before]
    
    # Simulate server restart by reconnecting the client
    await client.disconnect()
    await asyncio.sleep(1)  # Wait for disconnect to complete
    
    # Reconnect with the same user ID
    client = await jp_ws_client(user_id="user1", username="User One")
    await client.subscribe_document(doc_id)
    await asyncio.sleep(1)  # Wait for reconnection and state synchronization
    
    # Get the version history after restart
    history_after = await client.get_version_history(doc_id)
    
    # Verify history persisted
    assert len(history_after) >= len(history_before), "Version history should persist after restart"
    
    # Verify version IDs are preserved
    version_ids_after = [entry["snapshot_id"] for entry in history_after]
    for version_id in version_ids_before:
        assert version_id in version_ids_after, f"Version {version_id} should persist after restart"
    
    # Verify we can still access a specific version from before the restart
    old_version_id = version_ids_before[0]
    version_data = await client.get_version_by_id(doc_id, old_version_id)
    assert version_data is not None, "Should be able to retrieve pre-restart version"
    assert "document_state" in version_data, "Version should contain document state"


@pytest.mark.asyncio
async def test_milestone_versions(jp_serverapp, jp_ws_client):
    """
    Test creation and management of milestone versions.
    
    Verifies that important document versions can be marked as milestones with custom labels.
    """
    # Create a client
    client = await jp_ws_client(user_id="user1", username="User One")
    
    # Subscribe to a document
    doc_id = "test-milestone-versions-doc"
    await client.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Create initial content
    await client.add_cell(doc_id, "cell1", "# Initial draft", "markdown")
    await client.add_cell(doc_id, "cell2", "print('Draft code')" , "code")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Create a milestone version labeled "First Draft"
    milestone1_id = await client.create_milestone_snapshot(
        doc_id, 
        "First Draft", 
        "Initial version of the document"
    )
    assert milestone1_id is not None, "Should successfully create milestone"
    
    # Make additional changes
    await client.update_cell_content(doc_id, "cell1", "# Revised draft")
    await client.update_cell_content(doc_id, "cell2", "print('Improved code')")
    await client.add_cell(doc_id, "cell3", "# New section", "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Create another milestone labeled "Revision 1"
    milestone2_id = await client.create_milestone_snapshot(
        doc_id, 
        "Revision 1", 
        "First major revision with improvements"
    )
    assert milestone2_id is not None, "Should successfully create second milestone"
    
    # Get all milestones
    milestones = await client.get_milestone_snapshots(doc_id)
    
    # Verify milestones are recorded
    assert len(milestones) >= 2, "Should have at least 2 milestone snapshots"
    
    # Verify milestone metadata
    milestone_labels = [m.get("snapshot_label") for m in milestones]
    assert "First Draft" in milestone_labels, "First milestone should be recorded"
    assert "Revision 1" in milestone_labels, "Second milestone should be recorded"
    
    # Verify we can restore to a milestone
    first_draft = next(m for m in milestones if m.get("snapshot_label") == "First Draft")
    restore_success = await client.restore_version(doc_id, first_draft["snapshot_id"])
    assert restore_success, "Should successfully restore to milestone version"
    
    # Wait for restoration to complete
    await asyncio.sleep(0.5)
    
    # Verify the document state matches the first draft
    doc_state = await client.get_document_state(doc_id)
    assert len(doc_state["cells"]) == 2, "Restored document should have 2 cells"
    assert "cell3" not in doc_state["cells"], "cell3 should not exist in restored first draft"
    assert doc_state["cells"]["cell1"]["source"] == "# Initial draft", "cell1 content should match first draft"


@pytest.mark.asyncio
async def test_concurrent_history_access(jp_serverapp, jp_ws_client):
    """
    Test concurrent access to version history by multiple clients.
    
    Verifies that multiple clients can simultaneously access and modify version history.
    """
    # Create three clients
    client1 = await jp_ws_client(user_id="user1", username="User One")
    client2 = await jp_ws_client(user_id="user2", username="User Two")
    client3 = await jp_ws_client(user_id="user3", username="User Three")
    
    # All clients subscribe to the same document
    doc_id = "test-concurrent-history-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    await client3.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Create initial content
    await client1.add_cell(doc_id, "cell1", "# Initial content", "markdown")
    await asyncio.sleep(0.5)
    
    # Concurrently create milestone snapshots from different clients
    milestone_tasks = [
        client1.create_milestone_snapshot(doc_id, "Milestone from User 1", "Created by User One"),
        client2.create_milestone_snapshot(doc_id, "Milestone from User 2", "Created by User Two"),
        client3.create_milestone_snapshot(doc_id, "Milestone from User 3", "Created by User Three")
    ]
    
    # Execute concurrently
    milestone_results = await asyncio.gather(*milestone_tasks)
    
    # Verify all milestones were created successfully
    for result in milestone_results:
        assert result is not None, "All milestone creations should succeed"
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Each client retrieves the milestone list
    milestones1 = await client1.get_milestone_snapshots(doc_id)
    milestones2 = await client2.get_milestone_snapshots(doc_id)
    milestones3 = await client3.get_milestone_snapshots(doc_id)
    
    # Verify all clients see the same milestones
    assert len(milestones1) == len(milestones2) == len(milestones3), "All clients should see the same number of milestones"
    assert len(milestones1) >= 3, "Should have at least 3 milestones"
    
    # Verify milestone labels from all users are present
    milestone_labels = [m.get("snapshot_label") for m in milestones1]
    assert "Milestone from User 1" in milestone_labels, "User 1's milestone should be visible"
    assert "Milestone from User 2" in milestone_labels, "User 2's milestone should be visible"
    assert "Milestone from User 3" in milestone_labels, "User 3's milestone should be visible"
    
    # Concurrently access version history
    history_tasks = [
        client1.get_version_history(doc_id),
        client2.get_version_history(doc_id),
        client3.get_version_history(doc_id)
    ]
    
    # Execute concurrently
    history_results = await asyncio.gather(*history_tasks)
    
    # Verify all clients see the same history length
    assert len(history_results[0]) == len(history_results[1]) == len(history_results[2]), \
           "All clients should see the same history length"


@pytest.mark.asyncio
async def test_version_history_with_comments(jp_serverapp, jp_ws_client):
    """
    Test integration between version history and comments.
    
    Verifies that comments are properly tracked in version history and preserved during restoration.
    """
    # Create two clients
    client1 = await jp_ws_client(user_id="user1", username="User One")
    client2 = await jp_ws_client(user_id="user2", username="User Two")
    
    # Both clients subscribe to the same document
    doc_id = "test-history-comments-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Create initial content
    cell_id = "cell1"
    await client1.add_cell(doc_id, cell_id, "# Content to comment on", "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 2 adds a comment to the cell
    comment_id = await client2.add_comment(doc_id, cell_id, "This is a comment on the heading")
    assert comment_id is not None, "Comment should be created successfully"
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Create a snapshot with the comment
    snapshot_with_comment = await client1.create_snapshot(doc_id)
    
    # Verify comments exist in the document
    comments = await client1.get_comments(doc_id)
    assert len(comments) >= 1, "Document should have at least one comment"
    
    # Client 1 modifies the cell and adds another cell
    await client1.update_cell_content(doc_id, cell_id, "# Modified content with comment")
    await client1.add_cell(doc_id, "cell2", "# Second cell", "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Create another snapshot after modifications
    snapshot_after_modifications = await client1.create_snapshot(doc_id)
    
    # Restore to the version with just the comment
    restore_success = await client1.restore_version(doc_id, snapshot_with_comment)
    assert restore_success, "Version restoration should succeed"
    
    # Wait for restoration to complete
    await asyncio.sleep(0.5)
    
    # Verify the document content is restored
    doc_state = await client1.get_document_state(doc_id)
    assert len(doc_state["cells"]) == 1, "Restored document should have 1 cell"
    assert doc_state["cells"][cell_id]["source"] == "# Content to comment on", "Cell content should be restored"
    
    # Verify the comment is preserved after restoration
    comments_after_restore = await client1.get_comments(doc_id)
    assert len(comments_after_restore) >= 1, "Comments should be preserved after restoration"
    
    # Verify the comment ID is preserved
    comment_ids_after_restore = [c.get("id") for c in comments_after_restore]
    assert comment_id in comment_ids_after_restore, "Original comment should be preserved after restoration"


@pytest.mark.asyncio
async def test_version_comparison(jp_serverapp, jp_ws_client):
    """
    Test detailed comparison between document versions.
    
    Verifies that users can compare specific aspects of different versions.
    """
    # Create a client
    client = await jp_ws_client(user_id="user1", username="User One")
    
    # Subscribe to a document
    doc_id = "test-version-comparison-doc"
    await client.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Create initial version with metadata and cells
    notebook_metadata = {
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python", "version": "3.8.0"},
        "title": "Original Title"
    }
    await client.update_notebook_metadata(doc_id, notebook_metadata)
    
    await client.add_cell(doc_id, "cell1", "# Original heading", "markdown")
    await client.add_cell(doc_id, "cell2", "print('Original code')" , "code")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Create first snapshot
    first_version_id = await client.create_snapshot(doc_id)
    
    # Modify metadata and cells
    updated_metadata = {
        "title": "Updated Title",
        "description": "Added description"
    }
    await client.update_notebook_metadata(doc_id, updated_metadata)
    
    await client.update_cell_content(doc_id, "cell1", "# Updated heading")
    await client.update_cell_content(doc_id, "cell2", "print('Updated code')")
    await client.add_cell(doc_id, "cell3", "# New section", "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Create second snapshot
    second_version_id = await client.create_snapshot(doc_id)
    
    # Compare the two versions
    comparison = await client.compare_versions(doc_id, first_version_id, second_version_id)
    
    # Verify comparison structure
    assert "cell_changes" in comparison, "Comparison should include cell changes"
    assert "metadata_changes" in comparison, "Comparison should include metadata changes"
    assert "structure_changes" in comparison, "Comparison should include structure changes"
    
    # Verify cell content changes
    cell_changes = comparison["cell_changes"]
    assert "cell1" in cell_changes, "cell1 changes should be detected"
    assert "cell2" in cell_changes, "cell2 changes should be detected"
    assert cell_changes["cell1"]["old"] == "# Original heading", "Old content should be recorded"
    assert cell_changes["cell1"]["new"] == "# Updated heading", "New content should be recorded"
    
    # Verify metadata changes
    metadata_changes = comparison["metadata_changes"]
    assert "title" in metadata_changes, "Title change should be detected"
    assert "description" in metadata_changes, "Description addition should be detected"
    assert metadata_changes["title"]["old"] == "Original Title", "Old title should be recorded"
    assert metadata_changes["title"]["new"] == "Updated Title", "New title should be recorded"
    
    # Verify structure changes
    structure_changes = comparison["structure_changes"]
    assert "added_cells" in structure_changes, "Added cells should be recorded"
    assert "cell3" in structure_changes["added_cells"], "cell3 should be listed as added"


if __name__ == "__main__":
    pytest.main(['-xvs', __file__])
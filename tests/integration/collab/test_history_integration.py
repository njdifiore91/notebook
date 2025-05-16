import asyncio
import json
import os
import pytest
import time
from unittest.mock import MagicMock, patch


@pytest.mark.asyncio
async def test_version_history_recording(jp_server_with_collab, create_collaborative_session):
    """
    Test that document changes are properly recorded in the version history
    with correct user attribution.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    user1_client, user2_client = clients
    
    # Clear any initial messages
    user1_client.clear_received_messages()
    user2_client.clear_received_messages()
    
    # User 1 makes a change to a cell
    cell_id = "cell-1"
    await user1_client.update_cell(cell_id, "# Updated by User 1")
    
    # Wait for the change to be processed
    await asyncio.sleep(1)
    
    # User 2 makes a different change
    await user2_client.update_cell(cell_id, "# Updated by User 1\n# Then updated by User 2")
    
    # Wait for the change to be processed
    await asyncio.sleep(1)
    
    # Request version history from user 1's client
    await user1_client.send({"type": "get_version_history"})
    
    # Wait for the response and verify it contains both changes with correct attribution
    history_message = await user1_client.wait_for_message_containing("version_history")
    assert history_message is not None, "No version history message received"
    
    # Parse the history message
    history_data = json.loads(history_message)
    versions = history_data.get("versions", [])
    
    # Verify we have at least 2 versions (could be more with initial state)
    assert len(versions) >= 2, f"Expected at least 2 versions, got {len(versions)}"
    
    # Verify user attribution in the versions
    user_ids_in_history = [version.get("user_id") for version in versions]
    assert user1_client.user_id in user_ids_in_history, f"User 1 ({user1_client.user_id}) not found in version history"
    assert user2_client.user_id in user_ids_in_history, f"User 2 ({user2_client.user_id}) not found in version history"


@pytest.mark.asyncio
async def test_version_timeline_navigation(jp_server_with_collab, create_collaborative_session):
    """
    Test that users can navigate through the version timeline and view
    different versions of the document.
    """
    # Create a collaborative session with 1 client
    document_path, clients = await create_collaborative_session(num_clients=1)
    client = clients[0]
    
    # Clear any initial messages
    client.clear_received_messages()
    
    # Make a series of changes to create a version history
    cell_id = "cell-1"
    versions_content = [
        "# Version 1",
        "# Version 1\n# Version 2",
        "# Version 1\n# Version 2\n# Version 3"
    ]
    
    # Apply each change and record the timestamp
    version_timestamps = []
    for content in versions_content:
        await client.update_cell(cell_id, content)
        version_timestamps.append(int(time.time() * 1000))
        await asyncio.sleep(1)  # Wait between changes
    
    # Request version history
    await client.send({"type": "get_version_history"})
    history_message = await client.wait_for_message_containing("version_history")
    assert history_message is not None, "No version history message received"
    
    # Parse the history message
    history_data = json.loads(history_message)
    versions = history_data.get("versions", [])
    
    # Verify we have at least 3 versions
    assert len(versions) >= 3, f"Expected at least 3 versions, got {len(versions)}"
    
    # Navigate to the second version
    second_version_id = versions[-2].get("id")
    await client.send({"type": "view_version", "version_id": second_version_id})
    
    # Wait for the response with the document state at that version
    version_view_message = await client.wait_for_message_containing("version_state")
    assert version_view_message is not None, "No version state message received"
    
    # Parse the version state message
    version_state_data = json.loads(version_view_message)
    version_content = version_state_data.get("state", {}).get("cells", [])
    
    # Verify the content matches the expected version
    found_cell = False
    for cell in version_content:
        if cell.get("id") == cell_id:
            found_cell = True
            cell_content = cell.get("source", "")
            assert "Version 2" in cell_content, f"Expected 'Version 2' in content, got {cell_content}"
            assert "Version 3" not in cell_content, f"Unexpected 'Version 3' in content: {cell_content}"
    
    assert found_cell, f"Cell {cell_id} not found in version state"


@pytest.mark.asyncio
async def test_document_restoration(jp_server_with_collab, create_collaborative_session, verify_document_consistency):
    """
    Test that a document can be restored to a previous state from the version history.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    user1_client, user2_client = clients
    
    # Clear any initial messages
    user1_client.clear_received_messages()
    user2_client.clear_received_messages()
    
    # Make a series of changes to create a version history
    cell_id = "cell-1"
    initial_content = "# Initial content"
    updated_content = "# Updated content"
    final_content = "# Final content"
    
    # Initial change
    await user1_client.update_cell(cell_id, initial_content)
    await asyncio.sleep(1)
    
    # Request version history to get the initial version ID
    await user1_client.send({"type": "get_version_history"})
    history_message = await user1_client.wait_for_message_containing("version_history")
    history_data = json.loads(history_message)
    initial_version_id = history_data.get("versions", [])[0].get("id")
    
    # Make more changes
    await user1_client.update_cell(cell_id, updated_content)
    await asyncio.sleep(1)
    await user2_client.update_cell(cell_id, final_content)
    await asyncio.sleep(1)
    
    # Verify both clients see the final content
    await verify_document_consistency(clients)
    
    # Restore to the initial version
    await user1_client.send({"type": "restore_version", "version_id": initial_version_id})
    
    # Wait for the restoration to complete
    restore_message = await user1_client.wait_for_message_containing("version_restored")
    assert restore_message is not None, "No version restored message received"
    
    # Wait for synchronization
    await asyncio.sleep(2)
    
    # Verify both clients see the restored content
    await verify_document_consistency(clients)
    
    # Get the document state from both clients
    user1_state = await user1_client.get_document_state()
    user2_state = await user2_client.get_document_state()
    
    # Verify the content matches the initial version
    for state in [user1_state, user2_state]:
        found_cell = False
        for cell in state.get("cells", []):
            if cell.get("id") == cell_id:
                found_cell = True
                cell_content = cell.get("source", "")
                assert initial_content in cell_content, f"Expected '{initial_content}' in content, got {cell_content}"
        assert found_cell, f"Cell {cell_id} not found in document state"


@pytest.mark.asyncio
async def test_change_attribution(jp_server_with_collab, create_collaborative_session):
    """
    Test that changes in the version history are correctly attributed to specific users.
    """
    # Create a collaborative session with 3 clients representing different users
    document_path, clients = await create_collaborative_session(num_clients=3)
    user1_client, user2_client, user3_client = clients
    
    # Clear any initial messages
    for client in clients:
        client.clear_received_messages()
    
    # Each user makes a distinct change
    cell_id = "cell-1"
    await user1_client.update_cell(cell_id, "# Change by User 1")
    await asyncio.sleep(1)
    
    await user2_client.update_cell(cell_id, "# Change by User 1\n# Change by User 2")
    await asyncio.sleep(1)
    
    await user3_client.update_cell(cell_id, "# Change by User 1\n# Change by User 2\n# Change by User 3")
    await asyncio.sleep(1)
    
    # Request detailed version history with attribution
    await user1_client.send({"type": "get_detailed_history", "cell_id": cell_id})
    
    # Wait for the response
    detailed_history_message = await user1_client.wait_for_message_containing("detailed_history")
    assert detailed_history_message is not None, "No detailed history message received"
    
    # Parse the detailed history message
    history_data = json.loads(detailed_history_message)
    changes = history_data.get("changes", [])
    
    # Verify we have at least 3 changes
    assert len(changes) >= 3, f"Expected at least 3 changes, got {len(changes)}"
    
    # Verify each user's change is attributed correctly
    user_ids = [user1_client.user_id, user2_client.user_id, user3_client.user_id]
    for user_id in user_ids:
        user_changes = [change for change in changes if change.get("user_id") == user_id]
        assert len(user_changes) > 0, f"No changes found for user {user_id}"
        
        # Verify the change content contains the expected text
        for change in user_changes:
            content = change.get("content", "")
            user_number = user_id.split("-")[-1]  # Extract user number from ID
            assert f"User {user_number}" in content, f"Expected 'User {user_number}' in content, got {content}"


@pytest.mark.asyncio
async def test_diff_visualization(jp_server_with_collab, create_collaborative_session):
    """
    Test that users can view diffs between different document versions.
    """
    # Create a collaborative session with 1 client
    document_path, clients = await create_collaborative_session(num_clients=1)
    client = clients[0]
    
    # Clear any initial messages
    client.clear_received_messages()
    
    # Make a series of changes to create a version history
    cell_id = "cell-1"
    version1_content = "# Version 1 content\nThis is the first version."
    version2_content = "# Version 1 content\nThis is the first version.\n\n# Version 2 addition"
    
    # Apply changes
    await client.update_cell(cell_id, version1_content)
    await asyncio.sleep(1)
    
    # Request version history to get the first version ID
    await client.send({"type": "get_version_history"})
    history_message = await client.wait_for_message_containing("version_history")
    history_data = json.loads(history_message)
    version1_id = history_data.get("versions", [])[0].get("id")
    
    # Make second change
    await client.update_cell(cell_id, version2_content)
    await asyncio.sleep(1)
    
    # Request updated version history to get the second version ID
    await client.send({"type": "get_version_history"})
    history_message = await client.wait_for_message_containing("version_history")
    history_data = json.loads(history_message)
    version2_id = history_data.get("versions", [])[-1].get("id")
    
    # Request diff between versions
    await client.send({
        "type": "get_version_diff",
        "from_version_id": version1_id,
        "to_version_id": version2_id
    })
    
    # Wait for the diff response
    diff_message = await client.wait_for_message_containing("version_diff")
    assert diff_message is not None, "No version diff message received"
    
    # Parse the diff message
    diff_data = json.loads(diff_message)
    diffs = diff_data.get("diffs", [])
    
    # Verify the diff contains the expected changes
    assert len(diffs) > 0, "No diffs found in the response"
    
    # Find the diff for our cell
    cell_diff = None
    for diff in diffs:
        if diff.get("cell_id") == cell_id:
            cell_diff = diff
            break
    
    assert cell_diff is not None, f"No diff found for cell {cell_id}"
    
    # Verify the diff shows the addition of the Version 2 content
    diff_content = cell_diff.get("diff", [])
    added_content_found = False
    for part in diff_content:
        if part.get("added") and "Version 2 addition" in part.get("content", ""):
            added_content_found = True
            break
    
    assert added_content_found, "Added content not found in diff"


@pytest.mark.asyncio
async def test_version_history_persistence(jp_server_with_collab, create_collaborative_session, simulate_server_restart):
    """
    Test that version history is persisted across server restarts.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    user1_client, user2_client = clients
    
    # Clear any initial messages
    user1_client.clear_received_messages()
    user2_client.clear_received_messages()
    
    # Make changes to create a version history
    cell_id = "cell-1"
    await user1_client.update_cell(cell_id, "# Change before restart")
    await asyncio.sleep(1)
    
    # Request version history before restart
    await user1_client.send({"type": "get_version_history"})
    before_restart_history = await user1_client.wait_for_message_containing("version_history")
    assert before_restart_history is not None, "No version history message received before restart"
    
    # Parse the history message
    before_history_data = json.loads(before_restart_history)
    before_versions = before_history_data.get("versions", [])
    
    # Disconnect clients before server restart
    await user1_client.disconnect()
    await user2_client.disconnect()
    
    # Simulate server restart
    restart_successful = await simulate_server_restart()
    assert restart_successful, "Server restart failed"
    
    # Reconnect clients
    document_name = os.path.basename(document_path)
    await user1_client.connect(document_name)
    await user2_client.connect(document_name)
    
    # Wait for reconnection to stabilize
    await asyncio.sleep(2)
    
    # Clear any reconnection messages
    user1_client.clear_received_messages()
    
    # Request version history after restart
    await user1_client.send({"type": "get_version_history"})
    after_restart_history = await user1_client.wait_for_message_containing("version_history")
    assert after_restart_history is not None, "No version history message received after restart"
    
    # Parse the history message
    after_history_data = json.loads(after_restart_history)
    after_versions = after_history_data.get("versions", [])
    
    # Verify that the version history is preserved
    assert len(after_versions) >= len(before_versions), "Version history lost after restart"
    
    # Verify that the content of the versions is preserved
    before_version_ids = [v.get("id") for v in before_versions]
    after_version_ids = [v.get("id") for v in after_versions]
    
    for version_id in before_version_ids:
        assert version_id in after_version_ids, f"Version {version_id} missing after restart"
    
    # Make a new change after restart
    await user2_client.update_cell(cell_id, "# Change before restart\n# Change after restart")
    await asyncio.sleep(1)
    
    # Request updated version history
    await user1_client.send({"type": "get_version_history"})
    updated_history = await user1_client.wait_for_message_containing("version_history")
    assert updated_history is not None, "No updated version history message received"
    
    # Parse the updated history message
    updated_history_data = json.loads(updated_history)
    updated_versions = updated_history_data.get("versions", [])
    
    # Verify that the new version is added to the history
    assert len(updated_versions) > len(after_versions), "New version not added to history after restart"


@pytest.mark.asyncio
async def test_multi_user_version_history_view(jp_server_with_collab, create_collaborative_session):
    """
    Test that multiple users can view the same version history and see consistent information.
    """
    # Create a collaborative session with 3 clients
    document_path, clients = await create_collaborative_session(num_clients=3)
    user1_client, user2_client, user3_client = clients
    
    # Clear any initial messages
    for client in clients:
        client.clear_received_messages()
    
    # User 1 makes a change
    cell_id = "cell-1"
    await user1_client.update_cell(cell_id, "# Change by User 1")
    await asyncio.sleep(1)
    
    # User 2 makes a change
    await user2_client.update_cell(cell_id, "# Change by User 1\n# Change by User 2")
    await asyncio.sleep(1)
    
    # All users request version history
    for client in clients:
        await client.send({"type": "get_version_history"})
    
    # Wait for all responses
    history_messages = []
    for client in clients:
        history_message = await client.wait_for_message_containing("version_history")
        assert history_message is not None, f"No version history message received for {client.user_id}"
        history_messages.append(history_message)
    
    # Parse all history messages
    history_data_list = [json.loads(msg) for msg in history_messages]
    versions_list = [data.get("versions", []) for data in history_data_list]
    
    # Verify all clients see the same number of versions
    version_counts = [len(versions) for versions in versions_list]
    assert all(count == version_counts[0] for count in version_counts), "Inconsistent version counts across clients"
    
    # Verify all clients see the same version IDs in the same order
    version_ids_list = [[v.get("id") for v in versions] for versions in versions_list]
    for i in range(1, len(version_ids_list)):
        assert version_ids_list[i] == version_ids_list[0], f"Version IDs don't match between client 0 and client {i}"
    
    # Verify all clients see the same user attributions
    user_attributions_list = [[v.get("user_id") for v in versions] for versions in versions_list]
    for i in range(1, len(user_attributions_list)):
        assert user_attributions_list[i] == user_attributions_list[0], f"User attributions don't match between client 0 and client {i}"


@pytest.mark.asyncio
async def test_version_history_with_multiple_cells(jp_server_with_collab, create_test_document, jp_ws_client):
    """
    Test that version history correctly tracks changes across multiple cells.
    """
    # Create a test document with multiple cells
    cells = [
        {
            "cell_type": "markdown",
            "metadata": {"id": "cell-1"},
            "source": ["# Cell 1\n", "Initial content for cell 1."]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {"id": "cell-2"},
            "outputs": [],
            "source": ["# Cell 2\n", "print('Initial content for cell 2.')"]
        },
        {
            "cell_type": "markdown",
            "metadata": {"id": "cell-3"},
            "source": ["# Cell 3\n", "Initial content for cell 3."]
        }
    ]
    
    document_path = await create_test_document(cells=cells)
    document_name = os.path.basename(document_path)
    
    # Create a client and connect to the document
    client = await jp_ws_client()
    await client.connect(document_name)
    
    # Clear any initial messages
    client.clear_received_messages()
    
    # Make changes to different cells
    await client.update_cell("cell-1", "# Cell 1\nUpdated content for cell 1.")
    await asyncio.sleep(1)
    
    await client.update_cell("cell-2", "# Cell 2\nprint('Updated content for cell 2.')")
    await asyncio.sleep(1)
    
    await client.update_cell("cell-3", "# Cell 3\nUpdated content for cell 3.")
    await asyncio.sleep(1)
    
    # Request version history
    await client.send({"type": "get_version_history"})
    history_message = await client.wait_for_message_containing("version_history")
    assert history_message is not None, "No version history message received"
    
    # Parse the history message
    history_data = json.loads(history_message)
    versions = history_data.get("versions", [])
    
    # Verify we have at least 3 versions (one for each cell update)
    assert len(versions) >= 3, f"Expected at least 3 versions, got {len(versions)}"
    
    # Request cell-specific history for each cell
    for cell_id in ["cell-1", "cell-2", "cell-3"]:
        await client.send({"type": "get_cell_history", "cell_id": cell_id})
        cell_history_message = await client.wait_for_message_containing(f"cell_history_{cell_id}")
        assert cell_history_message is not None, f"No cell history message received for {cell_id}"
        
        # Parse the cell history message
        cell_history_data = json.loads(cell_history_message)
        cell_versions = cell_history_data.get("versions", [])
        
        # Verify we have at least 1 version for this cell
        assert len(cell_versions) >= 1, f"Expected at least 1 version for {cell_id}, got {len(cell_versions)}"
        
        # Verify the latest version contains the updated content
        latest_version = cell_versions[-1]
        content = latest_version.get("content", "")
        assert f"Updated content for {cell_id}" in content, f"Expected updated content in {cell_id}, got {content}"
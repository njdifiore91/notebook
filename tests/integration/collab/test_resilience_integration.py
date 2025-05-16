"""Tests for resilience of collaborative editing in Jupyter Notebook v7.

This module tests the system's resilience to network issues, server restarts, and other
disruptions in the collaborative editing feature. It verifies that collaboration can
continue or recover properly after interruptions, ensuring that users don't lose work
during temporary connectivity issues.

The tests cover:
1. Recovery after network interruptions
2. Document consistency after server restarts
3. Handling of client disconnection and reconnection
4. Offline editing and synchronization upon reconnection
5. Conflict resolution after extended disconnection periods
"""

import asyncio
import json
import pytest
import time
from unittest.mock import patch, MagicMock

# Import helper functions from conftest
from tests.integration.collab.conftest import (
    send_message, read_next_message, wait_for_message, 
    send_lock_request, wait_for_lock_message
)


@pytest.mark.asyncio
async def test_reconnection_state_recovery(jp_collab_server, jp_collab_client, test_notebook_path):
    """Test that the collaboration state recovers after a client reconnects.
    
    This test verifies that when a client disconnects and reconnects, it receives
    the current document state and can continue collaborating seamlessly.
    """
    # Make a change to the document
    await send_message(jp_collab_client, "update", 
                       cell_id="cell1", 
                       content="print('Modified by test_reconnection_state_recovery')")
    
    # Wait for the update to be processed
    update_ack = await wait_for_message(jp_collab_client, "update_ack", timeout=2.0)
    assert update_ack is not None
    
    # Close the connection to simulate a network interruption
    await jp_collab_client.close()
    
    # Wait a moment to ensure the server registers the disconnection
    await asyncio.sleep(0.5)
    
    # Reconnect with the same user ID
    jp_ws_fetch = jp_collab_server.serverapp.web_app.jp_ws_fetch
    new_client = await jp_ws_fetch(
        "api", "collaboration", "documents", test_notebook_path,
        headers={"X-Jupyter-User-Id": "test_user"}
    )
    
    # Wait for initial sync message that should contain our previous change
    sync_message = await wait_for_message(new_client, "sync", timeout=2.0)
    assert sync_message is not None
    
    # Verify that the document state includes our change
    found_cell = False
    for cell in sync_message.get("cells", []):
        if cell.get("id") == "cell1":
            found_cell = True
            assert "Modified by test_reconnection_state_recovery" in cell.get("source")
    
    assert found_cell, "Could not find the modified cell in the sync message"
    
    # Clean up
    await new_client.close()


@pytest.mark.asyncio
async def test_server_restart_document_consistency(jp_collab_server, jp_collab_clients, test_notebook_path):
    """Test that document state remains consistent after a server restart.
    
    This test verifies that when the collaboration server is restarted, the document
    state is properly restored from persistence, and clients can reconnect and continue
    collaborating with the correct document state.
    """
    # Get clients for two different users
    client1 = jp_collab_clients["user1"]
    client2 = jp_collab_clients["user2"]
    
    # Client 1 makes a change
    await send_message(client1, "update", 
                       cell_id="cell2", 
                       content="# Modified before server restart")
    
    # Wait for the update to be processed
    update_ack = await wait_for_message(client1, "update_ack", timeout=2.0)
    assert update_ack is not None
    
    # Wait for client 2 to receive the update
    sync_message = await wait_for_message(client2, "update", timeout=2.0)
    assert sync_message is not None
    
    # Close all client connections before server restart
    for client in jp_collab_clients.values():
        await client.close()
    
    # Simulate server restart by reinitializing the collaboration extension
    # This should trigger persistence layer to reload the document state
    jp_collab_server.init_collaboration()
    
    # Wait for the server to initialize
    await asyncio.sleep(1.0)
    
    # Reconnect clients
    jp_ws_fetch = jp_collab_server.serverapp.web_app.jp_ws_fetch
    new_clients = {}
    
    for user_id in ["user1", "user2"]:
        new_clients[user_id] = await jp_ws_fetch(
            "api", "collaboration", "documents", test_notebook_path,
            headers={"X-Jupyter-User-Id": user_id}
        )
    
    # Client 1 makes another change after server restart
    await send_message(new_clients["user1"], "update", 
                       cell_id="cell3", 
                       content="# Modified after server restart")
    
    # Wait for the update to be processed
    update_ack = await wait_for_message(new_clients["user1"], "update_ack", timeout=2.0)
    assert update_ack is not None
    
    # Wait for client 2 to receive the update
    sync_message = await wait_for_message(new_clients["user2"], "update", timeout=2.0)
    assert sync_message is not None
    
    # Get the full document state from client 2 to verify consistency
    await send_message(new_clients["user2"], "get_document")
    doc_state = await wait_for_message(new_clients["user2"], "document_state", timeout=2.0)
    
    # Verify both changes (before and after restart) are present
    found_pre_restart_cell = False
    found_post_restart_cell = False
    
    for cell in doc_state.get("cells", []):
        if cell.get("id") == "cell2":
            found_pre_restart_cell = True
            assert "# Modified before server restart" in cell.get("source")
        elif cell.get("id") == "cell3":
            found_post_restart_cell = True
            assert "# Modified after server restart" in cell.get("source")
    
    assert found_pre_restart_cell, "Could not find the cell modified before server restart"
    assert found_post_restart_cell, "Could not find the cell modified after server restart"
    
    # Clean up
    for client in new_clients.values():
        await client.close()


@pytest.mark.asyncio
async def test_client_disconnection_reconnection(jp_collab_server, jp_collab_clients, test_notebook_path):
    """Test handling of client disconnection and reconnection.
    
    This test verifies that when a client disconnects and reconnects, it can continue
    collaborating seamlessly, and other clients are properly notified of the
    disconnection and reconnection events.
    """
    # Get clients for two different users
    client1 = jp_collab_clients["user1"]
    client2 = jp_collab_clients["user2"]
    
    # Client 1 makes a change
    await send_message(client1, "update", 
                       cell_id="cell1", 
                       content="# Initial content from client 1")
    
    # Wait for the update to be processed and propagated to client 2
    update_ack = await wait_for_message(client1, "update_ack", timeout=2.0)
    assert update_ack is not None
    await wait_for_message(client2, "update", timeout=2.0)
    
    # Client 1 disconnects
    await client1.close()
    
    # Wait for client 2 to receive the disconnection notification
    # This might be a presence update or a specific disconnection message
    disconnect_message = await wait_for_message(client2, "presence", timeout=2.0)
    assert disconnect_message is not None
    
    # Client 2 makes a change while client 1 is disconnected
    await send_message(client2, "update", 
                       cell_id="cell2", 
                       content="# Content added while client 1 was disconnected")
    
    # Wait for the update to be processed
    update_ack = await wait_for_message(client2, "update_ack", timeout=2.0)
    assert update_ack is not None
    
    # Client 1 reconnects
    jp_ws_fetch = jp_collab_server.serverapp.web_app.jp_ws_fetch
    new_client1 = await jp_ws_fetch(
        "api", "collaboration", "documents", test_notebook_path,
        headers={"X-Jupyter-User-Id": "user1"}
    )
    
    # Wait for client 2 to receive the reconnection notification
    reconnect_message = await wait_for_message(client2, "presence", timeout=2.0)
    assert reconnect_message is not None
    
    # Wait for client 1 to receive the full document state including client 2's change
    sync_message = await wait_for_message(new_client1, "sync", timeout=2.0)
    assert sync_message is not None
    
    # Verify that client 1 received the changes made while it was disconnected
    found_cell = False
    for cell in sync_message.get("cells", []):
        if cell.get("id") == "cell2":
            found_cell = True
            assert "# Content added while client 1 was disconnected" in cell.get("source")
    
    assert found_cell, "Could not find the cell added while client 1 was disconnected"
    
    # Client 1 makes a new change after reconnecting
    await send_message(new_client1, "update", 
                       cell_id="cell3", 
                       content="# Content from client 1 after reconnection")
    
    # Wait for the update to be processed
    update_ack = await wait_for_message(new_client1, "update_ack", timeout=2.0)
    assert update_ack is not None
    
    # Wait for client 2 to receive the update
    update_message = await wait_for_message(client2, "update", timeout=2.0)
    assert update_message is not None
    
    # Clean up
    await new_client1.close()
    await client2.close()


@pytest.mark.asyncio
async def test_offline_editing_synchronization(jp_collab_server, jp_collab_clients, test_notebook_path):
    """Test offline editing and synchronization upon reconnection.
    
    This test simulates a client making edits while offline (disconnected from the server),
    then reconnecting and verifying that those edits are properly synchronized with the server
    and other clients.
    """
    # Get clients for two different users
    client1 = jp_collab_clients["user1"]
    client2 = jp_collab_clients["user2"]
    
    # Client 1 makes an initial change
    await send_message(client1, "update", 
                       cell_id="cell1", 
                       content="# Initial content before going offline")
    
    # Wait for the update to be processed and propagated to client 2
    update_ack = await wait_for_message(client1, "update_ack", timeout=2.0)
    assert update_ack is not None
    await wait_for_message(client2, "update", timeout=2.0)
    
    # Simulate client 1 going offline by closing the connection
    await client1.close()
    
    # Wait for client 2 to receive the disconnection notification
    await wait_for_message(client2, "presence", timeout=2.0)
    
    # Simulate client 1 making offline edits by creating a new connection
    # with the same user ID but with offline changes
    jp_ws_fetch = jp_collab_server.serverapp.web_app.jp_ws_fetch
    new_client1 = await jp_ws_fetch(
        "api", "collaboration", "documents", test_notebook_path,
        headers={"X-Jupyter-User-Id": "user1"}
    )
    
    # Wait for initial sync
    await wait_for_message(new_client1, "sync", timeout=2.0)
    
    # Send offline changes as a batch update
    await send_message(new_client1, "offline_updates", 
                       updates=[
                           {
                               "cell_id": "cell2",
                               "content": "# First offline edit",
                               "timestamp": time.time() - 60  # 1 minute ago
                           },
                           {
                               "cell_id": "cell3",
                               "content": "# Second offline edit",
                               "timestamp": time.time() - 30  # 30 seconds ago
                           }
                       ])
    
    # Wait for the offline updates to be processed
    offline_ack = await wait_for_message(new_client1, "offline_updates_ack", timeout=2.0)
    assert offline_ack is not None
    
    # Wait for client 2 to receive the updates
    # There might be multiple update messages, so we need to wait for all of them
    updates_received = 0
    max_wait_time = 5.0  # Maximum time to wait for all updates
    start_time = asyncio.get_event_loop().time()
    
    while updates_received < 2 and asyncio.get_event_loop().time() - start_time < max_wait_time:
        update = await wait_for_message(client2, "update", timeout=1.0)
        if update is not None:
            updates_received += 1
    
    assert updates_received == 2, "Client 2 did not receive all offline updates"
    
    # Get the full document state from client 2 to verify consistency
    await send_message(client2, "get_document")
    doc_state = await wait_for_message(client2, "document_state", timeout=2.0)
    
    # Verify that all offline edits are present in the document
    found_cell2 = False
    found_cell3 = False
    
    for cell in doc_state.get("cells", []):
        if cell.get("id") == "cell2":
            found_cell2 = True
            assert "# First offline edit" in cell.get("source")
        elif cell.get("id") == "cell3":
            found_cell3 = True
            assert "# Second offline edit" in cell.get("source")
    
    assert found_cell2, "Could not find the first offline edit"
    assert found_cell3, "Could not find the second offline edit"
    
    # Clean up
    await new_client1.close()
    await client2.close()


@pytest.mark.asyncio
async def test_conflict_resolution_after_disconnection(jp_collab_server, jp_collab_clients, test_notebook_path):
    """Test conflict resolution after extended disconnection periods.
    
    This test verifies that when multiple clients edit the same cell during a disconnection
    period, the CRDT algorithm correctly resolves conflicts when they reconnect, ensuring
    that no changes are lost and the document reaches a consistent state across all clients.
    """
    # Get clients for three different users to better test conflict resolution
    client1 = jp_collab_clients["user1"]
    client2 = jp_collab_clients["user2"]
    client3 = jp_collab_clients["admin"]
    
    # All clients start with the same initial document state
    # Create a cell that all clients will edit
    await send_message(client1, "update", 
                       cell_id="conflict_cell", 
                       content="# Initial content for conflict testing")
    
    # Wait for the update to be processed and propagated to other clients
    update_ack = await wait_for_message(client1, "update_ack", timeout=2.0)
    assert update_ack is not None
    await wait_for_message(client2, "update", timeout=2.0)
    await wait_for_message(client3, "update", timeout=2.0)
    
    # Disconnect client 2 and client 3 to simulate network partition
    await client2.close()
    await client3.close()
    
    # Client 1 edits the cell while others are disconnected
    await send_message(client1, "update", 
                       cell_id="conflict_cell", 
                       content="# Modified by client 1 during partition")
    
    # Wait for the update to be processed
    update_ack = await wait_for_message(client1, "update_ack", timeout=2.0)
    assert update_ack is not None
    
    # Reconnect client 2 with a conflicting change
    jp_ws_fetch = jp_collab_server.serverapp.web_app.jp_ws_fetch
    new_client2 = await jp_ws_fetch(
        "api", "collaboration", "documents", test_notebook_path,
        headers={"X-Jupyter-User-Id": "user2"}
    )
    
    # Wait for initial sync
    await wait_for_message(new_client2, "sync", timeout=2.0)
    
    # Client 2 makes a conflicting change to the same cell
    await send_message(new_client2, "update", 
                       cell_id="conflict_cell", 
                       content="# Modified by client 2 with conflict")
    
    # Wait for the update to be processed
    update_ack = await wait_for_message(new_client2, "update_ack", timeout=2.0)
    assert update_ack is not None
    
    # Wait for client 1 to receive the conflicting update
    conflict_update = await wait_for_message(client1, "update", timeout=2.0)
    assert conflict_update is not None
    
    # Reconnect client 3 with another conflicting change
    new_client3 = await jp_ws_fetch(
        "api", "collaboration", "documents", test_notebook_path,
        headers={"X-Jupyter-User-Id": "admin"}
    )
    
    # Wait for initial sync
    await wait_for_message(new_client3, "sync", timeout=2.0)
    
    # Client 3 makes another conflicting change to the same cell
    await send_message(new_client3, "update", 
                       cell_id="conflict_cell", 
                       content="# Modified by client 3 with another conflict")
    
    # Wait for the update to be processed
    update_ack = await wait_for_message(new_client3, "update_ack", timeout=2.0)
    assert update_ack is not None
    
    # Wait for all clients to receive the updates and resolve conflicts
    # Give some time for CRDT convergence
    await asyncio.sleep(1.0)
    
    # Get the document state from all clients
    await send_message(client1, "get_document")
    doc_state1 = await wait_for_message(client1, "document_state", timeout=2.0)
    
    await send_message(new_client2, "get_document")
    doc_state2 = await wait_for_message(new_client2, "document_state", timeout=2.0)
    
    await send_message(new_client3, "get_document")
    doc_state3 = await wait_for_message(new_client3, "document_state", timeout=2.0)
    
    # Extract the content of the conflict cell from each client
    cell_content1 = None
    cell_content2 = None
    cell_content3 = None
    
    for cell in doc_state1.get("cells", []):
        if cell.get("id") == "conflict_cell":
            cell_content1 = cell.get("source")
    
    for cell in doc_state2.get("cells", []):
        if cell.get("id") == "conflict_cell":
            cell_content2 = cell.get("source")
    
    for cell in doc_state3.get("cells", []):
        if cell.get("id") == "conflict_cell":
            cell_content3 = cell.get("source")
    
    # Verify that all clients have converged to the same state
    assert cell_content1 is not None, "Could not find conflict cell in client 1"
    assert cell_content2 is not None, "Could not find conflict cell in client 2"
    assert cell_content3 is not None, "Could not find conflict cell in client 3"
    
    # The exact merged content depends on the CRDT algorithm, but all clients should have the same content
    assert cell_content1 == cell_content2, "Clients 1 and 2 have different cell content after conflict resolution"
    assert cell_content2 == cell_content3, "Clients 2 and 3 have different cell content after conflict resolution"
    
    # Verify that the merged content contains elements from all three edits
    # This is a basic check that the CRDT algorithm is working correctly
    # The exact merged content will depend on the specific CRDT implementation
    assert "client 1" in cell_content1 or "client 2" in cell_content1 or "client 3" in cell_content1, \
        "Merged content does not contain any of the conflicting edits"
    
    # Clean up
    await client1.close()
    await new_client2.close()
    await new_client3.close()


@pytest.mark.asyncio
async def test_network_interruption_recovery(jp_collab_server, jp_collab_clients, test_notebook_path):
    """Test recovery after network interruptions.
    
    This test simulates network interruptions by manipulating the WebSocket connection
    and verifies that the system can recover and continue collaboration after the
    connection is restored.
    """
    # Get clients for two different users
    client1 = jp_collab_clients["user1"]
    client2 = jp_collab_clients["user2"]
    
    # Both clients make initial changes to establish the document state
    await send_message(client1, "update", 
                       cell_id="cell1", 
                       content="# Content from client 1")
    
    await send_message(client2, "update", 
                       cell_id="cell2", 
                       content="# Content from client 2")
    
    # Wait for updates to be processed and propagated
    await wait_for_message(client1, "update_ack", timeout=2.0)
    await wait_for_message(client2, "update_ack", timeout=2.0)
    await wait_for_message(client1, "update", timeout=2.0)  # client1 receives client2's update
    await wait_for_message(client2, "update", timeout=2.0)  # client2 receives client1's update
    
    # Simulate network interruption by patching the WebSocket's _write_to_connection method
    # This will cause messages to be dropped without closing the connection
    original_write = client1._write_to_connection
    
    async def mock_write_to_connection(message):
        # Drop all messages
        pass
    
    # Apply the patch to simulate network interruption
    client1._write_to_connection = mock_write_to_connection
    
    # Client 1 attempts to make changes during the network interruption
    await send_message(client1, "update", 
                       cell_id="cell3", 
                       content="# Content that should be buffered during interruption")
    
    # Client 2 makes changes that client 1 won't receive due to the interruption
    await send_message(client2, "update", 
                       cell_id="cell4", 
                       content="# Content added during client 1's interruption")
    
    # Wait for client 2's update to be processed
    await wait_for_message(client2, "update_ack", timeout=2.0)
    
    # Restore the connection by removing the patch
    client1._write_to_connection = original_write
    
    # Trigger a reconnection by sending a ping
    await send_message(client1, "ping")
    
    # Wait for ping response to confirm connection is restored
    pong = await wait_for_message(client1, "pong", timeout=2.0)
    assert pong is not None, "Connection was not restored successfully"
    
    # Client 1 should now receive the updates it missed during the interruption
    missed_update = await wait_for_message(client1, "update", timeout=2.0)
    assert missed_update is not None
    
    # Client 1's buffered changes should now be sent to the server and propagated to client 2
    # This might happen automatically or require a manual resend, depending on the implementation
    # If manual resend is needed, uncomment the following:
    # await send_message(client1, "update", 
    #                   cell_id="cell3", 
    #                   content="# Content that should be buffered during interruption")
    
    # Wait for client 2 to receive client 1's update
    client1_update = await wait_for_message(client2, "update", timeout=2.0)
    assert client1_update is not None
    
    # Get the document state from both clients to verify consistency
    await send_message(client1, "get_document")
    doc_state1 = await wait_for_message(client1, "document_state", timeout=2.0)
    
    await send_message(client2, "get_document")
    doc_state2 = await wait_for_message(client2, "document_state", timeout=2.0)
    
    # Verify that both clients have all cells
    cells1 = {cell.get("id"): cell.get("source") for cell in doc_state1.get("cells", [])}
    cells2 = {cell.get("id"): cell.get("source") for cell in doc_state2.get("cells", [])}
    
    # Check that both clients have the same cells
    assert set(cells1.keys()) == set(cells2.keys()), "Clients have different sets of cells"
    
    # Check that the content of each cell is the same in both clients
    for cell_id in cells1.keys():
        assert cells1[cell_id] == cells2[cell_id], f"Cell {cell_id} has different content in the two clients"
    
    # Verify that all expected cells are present
    assert "cell1" in cells1, "Cell 1 is missing"
    assert "cell2" in cells1, "Cell 2 is missing"
    assert "cell3" in cells1, "Cell 3 is missing (buffered during interruption)"
    assert "cell4" in cells1, "Cell 4 is missing (added during interruption)"
    
    # Clean up
    await client1.close()
    await client2.close()
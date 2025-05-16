import asyncio
import json
import os
import pytest
import time
from unittest.mock import patch

# Mark all tests in this file as asyncio tests
pytestmark = pytest.mark.asyncio


async def test_reconnection_after_network_interruption(jp_server_with_collab, create_collaborative_session, verify_document_consistency):
    """
    Test that collaboration state recovers after a client experiences a network interruption.
    
    This test verifies that when a client temporarily loses connection to the server,
    it can reconnect and continue collaborating without losing state or causing inconsistencies.
    """
    # Create a collaborative session with 3 clients
    document_path, clients = await create_collaborative_session(num_clients=3)
    
    # Make some initial edits with the first client
    await clients[0].update_cell("cell-1", "Initial content from client 1")
    
    # Make edits with the second client
    await clients[1].update_cell("cell-2", "Initial content from client 2")
    
    # Verify initial consistency
    assert await verify_document_consistency(clients)
    
    # Simulate network interruption for the first client
    await clients[0].simulate_network_interruption(duration=2.0)
    
    # Continue making edits with other clients during the interruption
    await clients[1].update_cell("cell-1", "Updated content from client 2")
    await clients[2].update_cell("cell-3", "New content from client 3")
    
    # Wait for reconnection to complete
    await asyncio.sleep(1)
    
    # Verify that the first client has reconnected
    assert clients[0].connected
    
    # Make an edit with the first client after reconnection
    await clients[0].update_cell("cell-4", "New content from client 1 after reconnection")
    
    # Verify document consistency across all clients
    assert await verify_document_consistency(clients)
    
    # Verify that all edits are visible to the first client
    client1_state = await clients[0].get_document_state()
    assert "Updated content from client 2" in str(client1_state)
    assert "New content from client 3" in str(client1_state)
    
    # Verify that the edit made by the first client after reconnection is visible to others
    client2_state = await clients[1].get_document_state()
    assert "New content from client 1 after reconnection" in str(client2_state)


async def test_document_consistency_after_server_restart(jp_server_with_collab, create_collaborative_session, 
                                                       verify_document_consistency, simulate_server_restart):
    """
    Test that document state is maintained after the server is restarted.
    
    This test verifies that when the collaboration server is restarted, the document
    state is properly persisted and clients can reconnect and continue collaborating.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    
    # Make some edits with both clients
    await clients[0].update_cell("cell-1", "Content from client 1 before restart")
    await clients[1].update_cell("cell-2", "Content from client 2 before restart")
    
    # Verify initial consistency
    assert await verify_document_consistency(clients)
    
    # Capture the document state before restart
    pre_restart_state = await clients[0].get_document_state()
    
    # Disconnect all clients before server restart
    for client in clients:
        await client.disconnect()
    
    # Restart the server
    assert await simulate_server_restart()
    
    # Reconnect all clients
    document_name = os.path.basename(document_path)
    for client in clients:
        await client.connect(document_name)
    
    # Wait for reconnection to complete
    await asyncio.sleep(2)
    
    # Verify that all clients have reconnected
    for client in clients:
        assert client.connected
    
    # Verify document consistency across all clients
    assert await verify_document_consistency(clients)
    
    # Verify that the document state is preserved after restart
    post_restart_state = await clients[0].get_document_state()
    assert "Content from client 1 before restart" in str(post_restart_state)
    assert "Content from client 2 before restart" in str(post_restart_state)
    
    # Make new edits after server restart
    await clients[0].update_cell("cell-3", "Content from client 1 after restart")
    await clients[1].update_cell("cell-4", "Content from client 2 after restart")
    
    # Verify consistency after new edits
    assert await verify_document_consistency(clients)
    
    # Verify that new edits are visible to all clients
    final_state = await clients[0].get_document_state()
    assert "Content from client 1 after restart" in str(final_state)
    assert "Content from client 2 after restart" in str(final_state)


async def test_client_disconnection_and_reconnection(jp_server_with_collab, create_collaborative_session, 
                                                   verify_document_consistency):
    """
    Test that a client can disconnect and reconnect without losing state.
    
    This test verifies that when a client disconnects and later reconnects,
    it can synchronize with the current document state and continue collaborating.
    """
    # Create a collaborative session with 3 clients
    document_path, clients = await create_collaborative_session(num_clients=3)
    
    # Make some initial edits with all clients
    await clients[0].update_cell("cell-1", "Initial content from client 1")
    await clients[1].update_cell("cell-2", "Initial content from client 2")
    await clients[2].update_cell("cell-3", "Initial content from client 3")
    
    # Verify initial consistency
    assert await verify_document_consistency(clients)
    
    # Disconnect the second client
    await clients[1].disconnect()
    
    # Make edits with the remaining clients
    await clients[0].update_cell("cell-1", "Updated content from client 1")
    await clients[2].update_cell("cell-3", "Updated content from client 3")
    
    # Verify consistency between connected clients
    assert await verify_document_consistency([clients[0], clients[2]])
    
    # Reconnect the second client
    document_name = os.path.basename(document_path)
    await clients[1].connect(document_name)
    
    # Wait for reconnection to complete
    await asyncio.sleep(2)
    
    # Verify that the client has reconnected
    assert clients[1].connected
    
    # Verify document consistency across all clients
    assert await verify_document_consistency(clients)
    
    # Verify that the reconnected client sees all updates
    client2_state = await clients[1].get_document_state()
    assert "Updated content from client 1" in str(client2_state)
    assert "Updated content from client 3" in str(client2_state)
    
    # Make an edit with the reconnected client
    await clients[1].update_cell("cell-2", "Updated content from client 2 after reconnection")
    
    # Verify consistency after new edit
    assert await verify_document_consistency(clients)
    
    # Verify that the edit from the reconnected client is visible to others
    client1_state = await clients[0].get_document_state()
    assert "Updated content from client 2 after reconnection" in str(client1_state)


async def test_offline_edits_synchronization(jp_server_with_collab, create_collaborative_session, 
                                           verify_document_consistency):
    """
    Test that edits made while offline are properly synchronized upon reconnection.
    
    This test verifies that when a client makes edits while disconnected from the server,
    those edits are properly synchronized when the client reconnects.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    
    # Make some initial edits with both clients
    await clients[0].update_cell("cell-1", "Initial content from client 1")
    await clients[1].update_cell("cell-2", "Initial content from client 2")
    
    # Verify initial consistency
    assert await verify_document_consistency(clients)
    
    # Simulate network interruption for the first client
    await clients[0].simulate_network_interruption(duration=0.1)  # Short interruption to trigger offline mode
    
    # Make offline edits with the first client
    # These should be queued in the client's offline_updates list
    await clients[0].update_cell("cell-3", "Offline content from client 1")
    await clients[0].update_cell("cell-4", "More offline content from client 1")
    
    # Make edits with the second client during the first client's offline period
    await clients[1].update_cell("cell-5", "Content from client 2 during offline period")
    
    # Wait for reconnection and synchronization to complete
    await asyncio.sleep(3)
    
    # Verify that the first client has reconnected
    assert clients[0].connected
    
    # Verify document consistency across all clients
    assert await verify_document_consistency(clients)
    
    # Verify that offline edits from the first client are visible to the second client
    client2_state = await clients[1].get_document_state()
    assert "Offline content from client 1" in str(client2_state)
    assert "More offline content from client 1" in str(client2_state)
    
    # Verify that edits made by the second client during the offline period
    # are visible to the first client
    client1_state = await clients[0].get_document_state()
    assert "Content from client 2 during offline period" in str(client1_state)


async def test_conflict_resolution_after_extended_disconnection(jp_server_with_collab, create_collaborative_session, 
                                                             verify_document_consistency):
    """
    Test that conflicts are properly resolved when a client reconnects after an extended disconnection period.
    
    This test verifies that when a client is disconnected for an extended period during which
    other clients make conflicting edits, the CRDT algorithm properly resolves the conflicts
    when the client reconnects.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    
    # Make some initial edits with both clients
    await clients[0].update_cell("cell-1", "Initial content from client 1")
    await clients[1].update_cell("cell-2", "Initial content from client 2")
    
    # Verify initial consistency
    assert await verify_document_consistency(clients)
    
    # Disconnect the first client
    await clients[0].disconnect()
    
    # Make edits with the second client to the same cells that the first client edited
    await clients[1].update_cell("cell-1", "Updated content from client 2 (conflict)")
    
    # Reconnect the first client
    document_name = os.path.basename(document_path)
    await clients[0].connect(document_name)
    
    # Wait for reconnection to complete
    await asyncio.sleep(2)
    
    # Make conflicting edits with the first client to the same cell
    await clients[0].update_cell("cell-1", "Updated content from client 1 (conflict)")
    
    # Wait for synchronization to complete
    await asyncio.sleep(2)
    
    # Verify document consistency across all clients
    assert await verify_document_consistency(clients)
    
    # Verify that both clients see the same final state
    client1_state = await clients[0].get_document_state()
    client2_state = await clients[1].get_document_state()
    
    # The exact merged content depends on the CRDT algorithm's conflict resolution strategy,
    # but both clients should see the same content
    assert json.dumps(client1_state, sort_keys=True) == json.dumps(client2_state, sort_keys=True)
    
    # Make additional edits with both clients to verify continued collaboration
    await clients[0].update_cell("cell-3", "New content from client 1 after conflict")
    await clients[1].update_cell("cell-4", "New content from client 2 after conflict")
    
    # Verify consistency after new edits
    assert await verify_document_consistency(clients)
    
    # Verify that new edits are visible to both clients
    final_state1 = await clients[0].get_document_state()
    final_state2 = await clients[1].get_document_state()
    
    assert "New content from client 1 after conflict" in str(final_state2)
    assert "New content from client 2 after conflict" in str(final_state1)


async def test_resilience_to_high_latency(jp_server_with_collab, create_collaborative_session, 
                                         verify_document_consistency):
    """
    Test that collaboration works correctly even with high network latency.
    
    This test verifies that the collaborative editing system can handle high network latency
    without losing edits or causing inconsistencies.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    
    # Make some initial edits with both clients
    await clients[0].update_cell("cell-1", "Initial content from client 1")
    await clients[1].update_cell("cell-2", "Initial content from client 2")
    
    # Verify initial consistency
    assert await verify_document_consistency(clients)
    
    # Simulate high latency for the first client
    await clients[0].simulate_high_latency(latency=0.5, duration=5.0)
    
    # Make edits with both clients during high latency
    await clients[0].update_cell("cell-3", "Content from client 1 during high latency")
    await clients[1].update_cell("cell-4", "Content from client 2 during high latency")
    
    # Wait for high latency simulation to end and synchronization to complete
    await asyncio.sleep(6)
    
    # Verify document consistency across all clients
    assert await verify_document_consistency(clients)
    
    # Verify that edits made during high latency are visible to both clients
    client1_state = await clients[0].get_document_state()
    client2_state = await clients[1].get_document_state()
    
    assert "Content from client 1 during high latency" in str(client2_state)
    assert "Content from client 2 during high latency" in str(client1_state)


async def test_multiple_reconnections(jp_server_with_collab, create_collaborative_session, 
                                     verify_document_consistency):
    """
    Test that clients can handle multiple reconnections without losing state.
    
    This test verifies that clients can disconnect and reconnect multiple times
    while maintaining document consistency.
    """
    # Create a collaborative session with 3 clients
    document_path, clients = await create_collaborative_session(num_clients=3)
    
    # Make some initial edits with all clients
    await clients[0].update_cell("cell-1", "Initial content from client 1")
    await clients[1].update_cell("cell-2", "Initial content from client 2")
    await clients[2].update_cell("cell-3", "Initial content from client 3")
    
    # Verify initial consistency
    assert await verify_document_consistency(clients)
    
    # Perform multiple reconnections for each client
    for i in range(3):
        # Disconnect and reconnect each client in sequence
        for j, client in enumerate(clients):
            # Disconnect the client
            await client.disconnect()
            
            # Make edits with other clients
            for k, other_client in enumerate(clients):
                if k != j and other_client.connected:
                    await other_client.update_cell(f"cell-{i+4}-{j}-{k}", 
                                                 f"Content from client {k+1} during client {j+1}'s disconnection {i+1}")
            
            # Reconnect the client
            document_name = os.path.basename(document_path)
            await client.connect(document_name)
            
            # Wait for reconnection to complete
            await asyncio.sleep(1)
            
            # Verify that the client has reconnected
            assert client.connected
            
            # Make an edit with the reconnected client
            await client.update_cell(f"cell-{i+7}-{j}", 
                                   f"Content from client {j+1} after reconnection {i+1}")
            
            # Verify document consistency
            assert await verify_document_consistency(clients)
    
    # Final verification of document consistency
    assert await verify_document_consistency(clients)
    
    # Verify that all edits are visible to all clients
    final_states = [await client.get_document_state() for client in clients]
    
    # Check that all states are the same
    first_state_json = json.dumps(final_states[0], sort_keys=True)
    for state in final_states[1:]:
        assert json.dumps(state, sort_keys=True) == first_state_json
    
    # Check that edits from all reconnection cycles are present
    for i in range(3):
        for j in range(3):
            assert f"Content from client {j+1} after reconnection {i+1}" in str(final_states[0])
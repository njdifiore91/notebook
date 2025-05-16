import asyncio
import pytest
import time
from unittest.mock import MagicMock, patch

# Skip tests if collaboration dependencies are not installed
pytestmark = pytest.mark.skipif(
    not pytest.importorskip("pycrdt", reason="Collaboration dependencies not installed"),
    reason="Collaboration dependencies not installed"
)

# Constants for testing
TEST_TIMEOUT = 0.1  # Short timeout for tests
CLEANUP_TIMEOUT = 0.5  # Timeout for awareness cleanup tests

# Test document and user IDs
TEST_DOC_ID = "test-awareness-doc"
USER1_ID = "user1"
USER2_ID = "user2"
USER3_ID = "user3"


class TestAwareness:
    """Test suite for the user presence awareness system in collaborative editing.
    
    The awareness system is responsible for tracking and synchronizing information about
    which users are currently viewing or editing a document, where their cursors are
    positioned, what text they have selected, and their current status (active, idle, etc.).
    
    These tests verify that the awareness system correctly tracks and synchronizes this
    information across multiple clients, enabling real-time visualization of collaborative
    editing activities.
    """
    
    @pytest.mark.asyncio
    async def test_user_presence_tracking(self, multi_client_websocket_simulation):
        """Test that user presence information is correctly tracked and synchronized.
        
        This test verifies that basic user information (ID, name, color) is correctly
        broadcast to all connected clients, enabling them to identify who else is
        currently viewing or editing the document.
        """
        """Test that user presence information is correctly tracked and synchronized."""
        # Create two clients
        client1 = await multi_client_websocket_simulation(user_id=USER1_ID)
        client2 = await multi_client_websocket_simulation(user_id=USER2_ID)
        
        # Connect both clients to the same document
        await client1.connect(doc_id=TEST_DOC_ID)
        await client2.connect(doc_id=TEST_DOC_ID)
        
        # Set user information for client1
        await client1.update_awareness({
            "user": {
                "id": USER1_ID,
                "name": "User 1",
                "color": "#ff0000"
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(0.1)
        
        # Get awareness states from client2
        client2_states = await client2.get_awareness_states()
        client1_id = client1.provider.awareness.client_id
        
        # Verify client2 received client1's presence information
        assert client1_id in client2_states
        assert client2_states[client1_id]["user"]["id"] == USER1_ID
        assert client2_states[client1_id]["user"]["name"] == "User 1"
        assert client2_states[client1_id]["user"]["color"] == "#ff0000"
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
    
    @pytest.mark.asyncio
    async def test_cursor_position_broadcasting(self, multi_client_websocket_simulation):
        """Test that cursor positions are correctly broadcast and visualized.
        
        This test verifies that when a user moves their cursor within a cell,
        the cursor position information is correctly broadcast to other clients,
        enabling real-time visualization of where other users are working.
        """
        """Test that cursor positions are correctly broadcast and visualized."""
        # Create two clients
        client1 = await multi_client_websocket_simulation(user_id=USER1_ID)
        client2 = await multi_client_websocket_simulation(user_id=USER2_ID)
        
        # Connect both clients to the same document
        doc_id = "test-cursor-doc"
        await client1.connect(doc_id=doc_id)
        await client2.connect(doc_id=doc_id)
        
        # Set cursor position for client1
        await client1.update_awareness({
            "user": {"id": USER1_ID, "name": "User 1"},
            "cursor": {
                "cellId": "cell1",
                "position": {"line": 10, "column": 15}
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(0.1)
        
        # Get awareness states from client2
        client2_states = await client2.get_awareness_states()
        client1_id = client1.provider.awareness.client_id
        
        # Verify client2 received client1's cursor position
        assert client1_id in client2_states
        assert "cursor" in client2_states[client1_id]
        assert client2_states[client1_id]["cursor"]["cellId"] == "cell1"
        assert client2_states[client1_id]["cursor"]["position"]["line"] == 10
        assert client2_states[client1_id]["cursor"]["position"]["column"] == 15
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
    
    @pytest.mark.asyncio
    async def test_selection_range_synchronization(self, multi_client_websocket_simulation):
        """Test that selection ranges are correctly synchronized across clients.
        
        This test verifies that when a user selects a range of text in a cell,
        the selection information is correctly broadcast to other clients,
        allowing them to visualize where other users are working.
        """
        """Test that selection ranges are correctly synchronized across clients."""
        # Create two clients
        client1 = await multi_client_websocket_simulation(user_id=USER1_ID)
        client2 = await multi_client_websocket_simulation(user_id=USER2_ID)
        
        # Connect both clients to the same document
        doc_id = "test-selection-doc"
        await client1.connect(doc_id=doc_id)
        await client2.connect(doc_id=doc_id)
        
        # Set selection range for client1
        await client1.update_awareness({
            "user": {"id": USER1_ID, "name": "User 1"},
            "selection": {
                "cellId": "cell1",
                "range": {
                    "start": {"line": 5, "column": 10},
                    "end": {"line": 5, "column": 20}
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Get awareness states from client2
        client2_states = await client2.get_awareness_states()
        client1_id = client1.provider.awareness.client_id
        
        # Verify client2 received client1's selection range
        assert client1_id in client2_states
        assert "selection" in client2_states[client1_id]
        assert client2_states[client1_id]["selection"]["cellId"] == "cell1"
        assert client2_states[client1_id]["selection"]["range"]["start"]["line"] == 5
        assert client2_states[client1_id]["selection"]["range"]["start"]["column"] == 10
        assert client2_states[client1_id]["selection"]["range"]["end"]["line"] == 5
        assert client2_states[client1_id]["selection"]["range"]["end"]["column"] == 20
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
    
    @pytest.mark.asyncio
    async def test_user_status_updates(self, multi_client_websocket_simulation):
        """Test that user status updates are properly propagated.
        
        This test verifies that when a user's status changes (e.g., from active to idle),
        the status update is correctly propagated to all other clients in real-time.
        """
        """Test that user status updates are properly propagated."""
        # Create two clients
        client1 = await multi_client_websocket_simulation(user_id=USER1_ID)
        client2 = await multi_client_websocket_simulation(user_id=USER2_ID)
        
        # Connect both clients to the same document
        doc_id = "test-status-doc"
        await client1.connect(doc_id=doc_id)
        await client2.connect(doc_id=doc_id)
        
        # Set active status for client1
        await client1.update_awareness({
            "user": {
                "id": USER1_ID,
                "name": "User 1",
                "status": "active"
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Get awareness states from client2
        client2_states = await client2.get_awareness_states()
        client1_id = client1.provider.awareness.client_id
        
        # Verify client2 received client1's active status
        assert client1_id in client2_states
        assert client2_states[client1_id]["user"]["status"] == "active"
        
        # Update to idle status
        await client1.update_awareness({
            "user": {
                "id": USER1_ID,
                "name": "User 1",
                "status": "idle"
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Get updated awareness states
        client2_states = await client2.get_awareness_states()
        
        # Verify status was updated to idle
        assert client2_states[client1_id]["user"]["status"] == "idle"
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
    
    @pytest.mark.asyncio
    async def test_awareness_cleanup_for_disconnected_users(self, multi_client_websocket_simulation):
        """Test that awareness state is cleaned up for disconnected users.
        
        This test verifies that when a client disconnects, their awareness state is
        properly cleaned up after a timeout period, ensuring that other clients
        don't continue to see presence information for users who are no longer connected.
        """
        """Test that awareness state is cleaned up for disconnected users."""
        # Create two clients
        client1 = await multi_client_websocket_simulation(user_id=USER1_ID)
        client2 = await multi_client_websocket_simulation(user_id=USER2_ID)
        
        # Connect both clients to the same document
        doc_id = "test-cleanup-doc"
        await client1.connect(doc_id=doc_id)
        await client2.connect(doc_id=doc_id)
        
        # Set awareness state for both clients
        await client1.update_awareness({
            "user": {"id": USER1_ID, "name": "User 1"}
        })
        
        await client2.update_awareness({
            "user": {"id": USER2_ID, "name": "User 2"}
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Verify both clients are aware of each other
        client1_states = await client1.get_awareness_states()
        client2_states = await client2.get_awareness_states()
        client1_id = client1.provider.awareness.client_id
        client2_id = client2.provider.awareness.client_id
        
        assert client2_id in client1_states
        assert client1_id in client2_states
        
        # Disconnect client1
        await client1.disconnect()
        
        # Wait for cleanup to occur (this may need adjustment based on actual cleanup timing)
        await asyncio.sleep(CLEANUP_TIMEOUT)
        
        # Get updated awareness states from client2
        client2_states = await client2.get_awareness_states()
        
        # Verify client1's state has been removed
        assert client1_id not in client2_states
        
        # Clean up
        await client2.disconnect()
    
    @pytest.mark.asyncio
    async def test_multiple_awareness_updates(self, multi_client_websocket_simulation):
        """Test that multiple awareness updates are correctly handled.
        
        This test verifies that when multiple clients are connected to the same document,
        all clients correctly receive and process awareness updates from all other clients.
        """
        """Test that multiple awareness updates are correctly handled."""
        # Create three clients
        client1 = await multi_client_websocket_simulation(user_id=USER1_ID)
        client2 = await multi_client_websocket_simulation(user_id=USER2_ID)
        client3 = await multi_client_websocket_simulation(user_id=USER3_ID)
        
        # Connect all clients to the same document
        doc_id = "test-multiple-doc"
        await client1.connect(doc_id=doc_id)
        await client2.connect(doc_id=doc_id)
        await client3.connect(doc_id=doc_id)
        
        # Set awareness states for all clients
        await client1.update_awareness({
            "user": {"id": USER1_ID, "name": "User 1"},
            "cursor": {"cellId": "cell1", "position": {"line": 1, "column": 5}}
        })
        
        await client2.update_awareness({
            "user": {"id": USER2_ID, "name": "User 2"},
            "cursor": {"cellId": "cell2", "position": {"line": 2, "column": 10}}
        })
        
        await client3.update_awareness({
            "user": {"id": USER3_ID, "name": "User 3"},
            "cursor": {"cellId": "cell3", "position": {"line": 3, "column": 15}}
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Get awareness states from client1
        client1_states = await client1.get_awareness_states()
        client2_id = client2.provider.awareness.client_id
        client3_id = client3.provider.awareness.client_id
        
        # Verify client1 received awareness states from both other clients
        assert client2_id in client1_states
        assert client3_id in client1_states
        assert client1_states[client2_id]["cursor"]["cellId"] == "cell2"
        assert client1_states[client3_id]["cursor"]["cellId"] == "cell3"
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
        await client3.disconnect()
    
    @pytest.mark.asyncio
    async def test_awareness_throttling(self, multi_client_websocket_simulation):
        """Test that rapid awareness updates are properly throttled.
        
        This test verifies that when a client sends multiple rapid awareness updates,
        the system properly throttles these updates to prevent overwhelming the network
        while ensuring that the final state is correctly synchronized.
        """
        """Test that rapid awareness updates are properly throttled."""
        # Create two clients
        client1 = await multi_client_websocket_simulation(user_id=USER1_ID)
        client2 = await multi_client_websocket_simulation(user_id=USER2_ID)
        
        # Connect both clients to the same document
        doc_id = "test-throttling-doc"
        await client1.connect(doc_id=doc_id)
        await client2.connect(doc_id=doc_id)
        
        # Perform multiple rapid cursor position updates
        for i in range(10):
            await client1.update_awareness({
                "user": {"id": USER1_ID, "name": "User 1"},
                "cursor": {
                    "cellId": "cell1",
                    "position": {"line": i, "column": i * 2}
                }
            })
            # No sleep between updates to simulate rapid changes
        
        # Wait for final awareness propagation
        await asyncio.sleep(TEST_TIMEOUT * 2)
        
        # Get awareness states from client2
        client2_states = await client2.get_awareness_states()
        client1_id = client1.provider.awareness.client_id
        
        # Verify client2 received the final cursor position
        assert client1_id in client2_states
        assert client2_states[client1_id]["cursor"]["position"]["line"] == 9
        assert client2_states[client1_id]["cursor"]["position"]["column"] == 18
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
    
    @pytest.mark.asyncio
    async def test_awareness_persistence_across_reconnection(self, multi_client_websocket_simulation):
        """Test that awareness state is preserved when a client reconnects.
        
        This test verifies that when a client disconnects and then reconnects,
        they can restore their awareness state and other clients will see the
        updated state with the new client ID.
        """
        """Test that awareness state is preserved when a client reconnects."""
        # Create two clients
        client1 = await multi_client_websocket_simulation(user_id=USER1_ID)
        client2 = await multi_client_websocket_simulation(user_id=USER2_ID)
        
        # Connect both clients to the same document
        doc_id = "test-reconnection-doc"
        await client1.connect(doc_id=doc_id)
        await client2.connect(doc_id=doc_id)
        
        # Set awareness state for client1
        await client1.update_awareness({
            "user": {"id": USER1_ID, "name": "User 1"},
            "cursor": {"cellId": "cell1", "position": {"line": 5, "column": 10}}
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Disconnect and reconnect client1
        client1_id = client1.provider.awareness.client_id
        await client1.disconnect()
        
        # Wait for cleanup to occur
        await asyncio.sleep(CLEANUP_TIMEOUT)
        
        # Verify client1's state has been removed
        client2_states = await client2.get_awareness_states()
        assert client1_id not in client2_states
        
        # Reconnect client1
        await client1.connect(doc_id=doc_id)
        
        # Set the same awareness state
        await client1.update_awareness({
            "user": {"id": USER1_ID, "name": "User 1"},
            "cursor": {"cellId": "cell1", "position": {"line": 5, "column": 10}}
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Get awareness states from client2
        client2_states = await client2.get_awareness_states()
        new_client1_id = client1.provider.awareness.client_id
        
        # Verify client1's state is present with the new client ID
        assert new_client1_id in client2_states
        assert client2_states[new_client1_id]["user"]["id"] == USER1_ID
        assert client2_states[new_client1_id]["cursor"]["cellId"] == "cell1"
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
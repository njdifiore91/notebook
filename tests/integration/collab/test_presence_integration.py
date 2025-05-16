import asyncio
import json
import pytest
import time
from unittest.mock import MagicMock, patch

# Skip tests if collaboration dependencies are not installed
pytestmark = pytest.mark.skipif(
    not pytest.importorskip("pycrdt", reason="Collaboration dependencies not installed"),
    reason="Collaboration dependencies not installed"
)

# Constants for testing
TEST_TIMEOUT = 0.2  # Short timeout for tests
CLEANUP_TIMEOUT = 1.0  # Timeout for awareness cleanup tests
RECONNECT_TIMEOUT = 0.5  # Timeout for reconnection tests

# Test document and user IDs
TEST_DOC_ID = "test-presence-integration-doc"
USER1_ID = "user1"
USER2_ID = "user2"
USER3_ID = "user3"


@pytest.mark.integration
class TestPresenceIntegration:
    """
    Integration tests for the user presence awareness system in collaborative editing.
    
    These tests verify that user presence information, cursor positions, and selection ranges
    are correctly tracked and synchronized across clients in a realistic environment.
    
    The presence awareness system is a critical component of collaborative editing, as it
    allows users to see each other's activities in real-time, enhancing the collaborative
    experience and reducing editing conflicts.
    """
    
    @pytest.mark.asyncio
    async def test_user_presence_information_sharing(self, jp_ws_client, create_test_document):
        """
        Test that user presence information is correctly shared among connected clients.
        
        This test verifies that when multiple clients connect to the same document,
        they can see each other's basic user information (ID, name, color).
        """
        # Create a test document
        doc_path = await create_test_document(name=TEST_DOC_ID)
        
        # Create two clients
        client1 = await jp_ws_client(user_id=USER1_ID)
        client2 = await jp_ws_client(user_id=USER2_ID)
        
        # Connect both clients to the same document
        await client1.connect(doc_id=TEST_DOC_ID)
        await client2.connect(doc_id=TEST_DOC_ID)
        
        # Set user information for client1
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER1_ID,
                    "name": "User One",
                    "color": "#ff0000"
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Check if client2 received client1's presence information
        message = await client2.wait_for_message_containing("User One")
        assert message is not None, "Client2 did not receive client1's presence information"
        
        # Parse the message to verify details
        try:
            data = json.loads(message)
            assert data.get("type") == "awareness"
            assert USER1_ID in str(data.get("data", {}))
            assert "#ff0000" in str(data.get("data", {}))
        except (json.JSONDecodeError, AssertionError) as e:
            pytest.fail(f"Failed to verify presence data: {e}")
        
        # Set user information for client2
        await client2.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER2_ID,
                    "name": "User Two",
                    "color": "#0000ff"
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Check if client1 received client2's presence information
        message = await client1.wait_for_message_containing("User Two")
        assert message is not None, "Client1 did not receive client2's presence information"
        
        # Parse the message to verify details
        try:
            data = json.loads(message)
            assert data.get("type") == "awareness"
            assert USER2_ID in str(data.get("data", {}))
            assert "#0000ff" in str(data.get("data", {}))
        except (json.JSONDecodeError, AssertionError) as e:
            pytest.fail(f"Failed to verify presence data: {e}")
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
    
    @pytest.mark.asyncio
    async def test_cursor_position_broadcasting(self, jp_ws_client, create_test_document):
        """
        Test that cursor positions are correctly broadcast and visualized across clients.
        
        This test verifies that when a user moves their cursor within a cell, the cursor
        position information is correctly broadcast to other clients, enabling real-time
        visualization of where other users are working.
        """
        # Create a test document
        doc_path = await create_test_document(name=TEST_DOC_ID)
        
        # Create two clients
        client1 = await jp_ws_client(user_id=USER1_ID)
        client2 = await jp_ws_client(user_id=USER2_ID)
        
        # Connect both clients to the same document
        await client1.connect(doc_id=TEST_DOC_ID)
        await client2.connect(doc_id=TEST_DOC_ID)
        
        # Set basic user information for both clients
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER1_ID,
                    "name": "User One",
                    "color": "#ff0000"
                }
            }
        })
        
        await client2.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER2_ID,
                    "name": "User Two",
                    "color": "#0000ff"
                }
            }
        })
        
        # Wait for initial awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Set cursor position for client1
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {"id": USER1_ID, "name": "User One"},
                "cursor": {
                    "cellId": "cell1",
                    "position": {"line": 5, "column": 10}
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Check if client2 received client1's cursor position
        message = await client2.wait_for_message_containing("cursor")
        assert message is not None, "Client2 did not receive client1's cursor position"
        
        # Parse the message to verify cursor details
        try:
            data = json.loads(message)
            assert data.get("type") == "awareness"
            cursor_data = str(data.get("data", {}))
            assert "cell1" in cursor_data
            assert "line" in cursor_data and "5" in cursor_data
            assert "column" in cursor_data and "10" in cursor_data
        except (json.JSONDecodeError, AssertionError) as e:
            pytest.fail(f"Failed to verify cursor position data: {e}")
        
        # Update cursor position for client1
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {"id": USER1_ID, "name": "User One"},
                "cursor": {
                    "cellId": "cell1",
                    "position": {"line": 8, "column": 15}
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Check if client2 received client1's updated cursor position
        message = await client2.wait_for_message_containing("line\":\s*8")
        assert message is not None, "Client2 did not receive client1's updated cursor position"
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
    
    @pytest.mark.asyncio
    async def test_selection_range_synchronization(self, jp_ws_client, create_test_document):
        """
        Test that selection ranges are correctly synchronized across clients.
        
        This test verifies that when a user selects a range of text in a cell, the selection
        information is correctly broadcast to other clients, allowing them to visualize
        where other users are working.
        """
        # Create a test document
        doc_path = await create_test_document(name=TEST_DOC_ID)
        
        # Create two clients
        client1 = await jp_ws_client(user_id=USER1_ID)
        client2 = await jp_ws_client(user_id=USER2_ID)
        
        # Connect both clients to the same document
        await client1.connect(doc_id=TEST_DOC_ID)
        await client2.connect(doc_id=TEST_DOC_ID)
        
        # Set basic user information for both clients
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER1_ID,
                    "name": "User One",
                    "color": "#ff0000"
                }
            }
        })
        
        # Wait for initial awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Set selection range for client1
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {"id": USER1_ID, "name": "User One"},
                "selection": {
                    "cellId": "cell1",
                    "range": {
                        "start": {"line": 3, "column": 5},
                        "end": {"line": 3, "column": 20}
                    }
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Check if client2 received client1's selection range
        message = await client2.wait_for_message_containing("selection")
        assert message is not None, "Client2 did not receive client1's selection range"
        
        # Parse the message to verify selection details
        try:
            data = json.loads(message)
            assert data.get("type") == "awareness"
            selection_data = str(data.get("data", {}))
            assert "cell1" in selection_data
            assert "start" in selection_data and "end" in selection_data
            assert "line" in selection_data and "column" in selection_data
            assert "3" in selection_data and "5" in selection_data and "20" in selection_data
        except (json.JSONDecodeError, AssertionError) as e:
            pytest.fail(f"Failed to verify selection range data: {e}")
        
        # Update selection range for client1
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {"id": USER1_ID, "name": "User One"},
                "selection": {
                    "cellId": "cell2",  # Changed cell
                    "range": {
                        "start": {"line": 1, "column": 0},
                        "end": {"line": 2, "column": 10}
                    }
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Check if client2 received client1's updated selection range
        message = await client2.wait_for_message_containing("cell2")
        assert message is not None, "Client2 did not receive client1's updated selection range"
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
    
    @pytest.mark.asyncio
    async def test_user_status_updates_propagation(self, jp_ws_client, create_test_document):
        """
        Test that user status updates are properly propagated across clients.
        
        This test verifies that when a user's status changes (e.g., from active to idle),
        the status update is correctly propagated to all other clients in real-time.
        """
        # Create a test document
        doc_path = await create_test_document(name=TEST_DOC_ID)
        
        # Create two clients
        client1 = await jp_ws_client(user_id=USER1_ID)
        client2 = await jp_ws_client(user_id=USER2_ID)
        
        # Connect both clients to the same document
        await client1.connect(doc_id=TEST_DOC_ID)
        await client2.connect(doc_id=TEST_DOC_ID)
        
        # Set active status for client1
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER1_ID,
                    "name": "User One",
                    "status": "active"
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Check if client2 received client1's active status
        message = await client2.wait_for_message_containing("active")
        assert message is not None, "Client2 did not receive client1's active status"
        
        # Update to idle status for client1
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER1_ID,
                    "name": "User One",
                    "status": "idle"
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Check if client2 received client1's idle status
        message = await client2.wait_for_message_containing("idle")
        assert message is not None, "Client2 did not receive client1's idle status"
        
        # Update to offline status for client1
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER1_ID,
                    "name": "User One",
                    "status": "offline"
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Check if client2 received client1's offline status
        message = await client2.wait_for_message_containing("offline")
        assert message is not None, "Client2 did not receive client1's offline status"
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
    
    @pytest.mark.asyncio
    async def test_awareness_state_cleanup_for_disconnected_users(self, jp_ws_client, create_test_document):
        """
        Test that awareness state is cleaned up for disconnected users.
        
        This test verifies that when a client disconnects, their awareness state is
        properly cleaned up after a timeout period, ensuring that other clients
        don't continue to see presence information for users who are no longer connected.
        """
        # Create a test document
        doc_path = await create_test_document(name=TEST_DOC_ID)
        
        # Create three clients
        client1 = await jp_ws_client(user_id=USER1_ID)
        client2 = await jp_ws_client(user_id=USER2_ID)
        client3 = await jp_ws_client(user_id=USER3_ID)
        
        # Connect all clients to the same document
        await client1.connect(doc_id=TEST_DOC_ID)
        await client2.connect(doc_id=TEST_DOC_ID)
        await client3.connect(doc_id=TEST_DOC_ID)
        
        # Set awareness state for all clients
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER1_ID,
                    "name": "User One",
                    "status": "active"
                }
            }
        })
        
        await client2.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER2_ID,
                    "name": "User Two",
                    "status": "active"
                }
            }
        })
        
        await client3.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER3_ID,
                    "name": "User Three",
                    "status": "active"
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Verify all clients are aware of each other
        message1 = await client1.wait_for_message_containing("User Two")
        message2 = await client1.wait_for_message_containing("User Three")
        assert message1 is not None and message2 is not None, "Client1 did not receive awareness from all clients"
        
        # Disconnect client2
        await client2.disconnect()
        
        # Wait for cleanup to occur
        await asyncio.sleep(CLEANUP_TIMEOUT)
        
        # Clear previous messages
        client1.clear_received_messages()
        client3.clear_received_messages()
        
        # Wait for cleanup message
        message = await client3.wait_for_message_containing("remove")
        assert message is not None, "Cleanup message not received"
        
        # Verify the cleanup message contains client2's ID
        try:
            data = json.loads(message)
            assert "remove" in str(data)
            assert USER2_ID in str(data) or "User Two" in str(data), "Cleanup message doesn't reference the disconnected user"
        except (json.JSONDecodeError, AssertionError) as e:
            pytest.fail(f"Failed to verify cleanup message: {e}")
        
        # Clean up remaining clients
        await client1.disconnect()
        await client3.disconnect()
    
    @pytest.mark.asyncio
    async def test_presence_information_persistence_across_page_reloads(self, jp_ws_client, create_test_document):
        """
        Test that presence information persists across page reloads.
        
        This test verifies that when a user reloads their page, they can restore their
        previous awareness state, and other users will see the updated state with
        minimal disruption to the collaborative experience.
        """
        # Create a test document
        doc_path = await create_test_document(name=TEST_DOC_ID)
        
        # Create two clients
        client1 = await jp_ws_client(user_id=USER1_ID)
        client2 = await jp_ws_client(user_id=USER2_ID)
        
        # Connect both clients to the same document
        await client1.connect(doc_id=TEST_DOC_ID)
        await client2.connect(doc_id=TEST_DOC_ID)
        
        # Set awareness state for client1
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER1_ID,
                    "name": "User One",
                    "color": "#ff0000",
                    "status": "active"
                },
                "cursor": {
                    "cellId": "cell1",
                    "position": {"line": 5, "column": 10}
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Verify client2 received client1's awareness
        message = await client2.wait_for_message_containing("User One")
        assert message is not None, "Client2 did not receive client1's awareness"
        
        # Simulate page reload by disconnecting and reconnecting client1
        await client1.disconnect()
        
        # Wait for cleanup to occur
        await asyncio.sleep(CLEANUP_TIMEOUT)
        
        # Verify client1's awareness was removed
        message = await client2.wait_for_message_containing("remove")
        assert message is not None, "Cleanup message not received after client1 disconnected"
        
        # Reconnect client1 (simulating page reload)
        client1 = await jp_ws_client(user_id=USER1_ID)
        await client1.connect(doc_id=TEST_DOC_ID)
        
        # Restore awareness state for client1
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {
                    "id": USER1_ID,
                    "name": "User One",
                    "color": "#ff0000",
                    "status": "active"
                },
                "cursor": {
                    "cellId": "cell1",
                    "position": {"line": 5, "column": 10}
                }
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Verify client2 received client1's restored awareness
        message = await client2.wait_for_message_containing("User One")
        assert message is not None, "Client2 did not receive client1's restored awareness"
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
    
    @pytest.mark.asyncio
    async def test_multiple_users_awareness_synchronization(self, jp_ws_client, create_test_document):
        """
        Test that awareness information is correctly synchronized among multiple users.
        
        This test verifies that when multiple users are connected to the same document,
        all awareness updates are properly broadcast to all participants, creating a
        cohesive collaborative environment.
        """
        # Create a test document
        doc_path = await create_test_document(name=TEST_DOC_ID)
        
        # Create three clients
        client1 = await jp_ws_client(user_id=USER1_ID)
        client2 = await jp_ws_client(user_id=USER2_ID)
        client3 = await jp_ws_client(user_id=USER3_ID)
        
        # Connect all clients to the same document
        await client1.connect(doc_id=TEST_DOC_ID)
        await client2.connect(doc_id=TEST_DOC_ID)
        await client3.connect(doc_id=TEST_DOC_ID)
        
        # Set awareness state for all clients
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {"id": USER1_ID, "name": "User One", "color": "#ff0000"},
                "cursor": {"cellId": "cell1", "position": {"line": 1, "column": 5}}
            }
        })
        
        await client2.send({
            "type": "awareness",
            "data": {
                "user": {"id": USER2_ID, "name": "User Two", "color": "#00ff00"},
                "cursor": {"cellId": "cell2", "position": {"line": 2, "column": 10}}
            }
        })
        
        await client3.send({
            "type": "awareness",
            "data": {
                "user": {"id": USER3_ID, "name": "User Three", "color": "#0000ff"},
                "cursor": {"cellId": "cell3", "position": {"line": 3, "column": 15}}
            }
        })
        
        # Wait for awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Verify client1 received awareness from both other clients
        message1 = await client1.wait_for_message_containing("User Two")
        message2 = await client1.wait_for_message_containing("User Three")
        assert message1 is not None and message2 is not None, "Client1 did not receive awareness from all clients"
        
        # Verify client2 received awareness from both other clients
        message1 = await client2.wait_for_message_containing("User One")
        message2 = await client2.wait_for_message_containing("User Three")
        assert message1 is not None and message2 is not None, "Client2 did not receive awareness from all clients"
        
        # Verify client3 received awareness from both other clients
        message1 = await client3.wait_for_message_containing("User One")
        message2 = await client3.wait_for_message_containing("User Two")
        assert message1 is not None and message2 is not None, "Client3 did not receive awareness from all clients"
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
        await client3.disconnect()
    
    @pytest.mark.asyncio
    async def test_awareness_throttling_in_high_frequency_updates(self, jp_ws_client, create_test_document):
        """
        Test that rapid awareness updates are properly throttled.
        
        This test verifies that when a client sends multiple rapid awareness updates,
        the system properly throttles these updates to prevent overwhelming the network
        while ensuring that the final state is correctly synchronized.
        """
        # Create a test document
        doc_path = await create_test_document(name=TEST_DOC_ID)
        
        # Create two clients
        client1 = await jp_ws_client(user_id=USER1_ID)
        client2 = await jp_ws_client(user_id=USER2_ID)
        
        # Connect both clients to the same document
        await client1.connect(doc_id=TEST_DOC_ID)
        await client2.connect(doc_id=TEST_DOC_ID)
        
        # Set basic user information
        await client1.send({
            "type": "awareness",
            "data": {
                "user": {"id": USER1_ID, "name": "User One", "color": "#ff0000"}
            }
        })
        
        # Wait for initial awareness propagation
        await asyncio.sleep(TEST_TIMEOUT)
        
        # Clear previous messages
        client2.clear_received_messages()
        
        # Perform multiple rapid cursor position updates
        for i in range(10):
            await client1.send({
                "type": "awareness",
                "data": {
                    "user": {"id": USER1_ID, "name": "User One"},
                    "cursor": {
                        "cellId": "cell1",
                        "position": {"line": i, "column": i * 2}
                    }
                }
            })
            # No sleep between updates to simulate rapid changes
        
        # Wait for final awareness propagation
        await asyncio.sleep(TEST_TIMEOUT * 2)
        
        # Check if client2 received the final cursor position
        message = await client2.wait_for_message_containing("line\":\s*9")
        assert message is not None, "Client2 did not receive client1's final cursor position"
        
        # Count the number of awareness messages received
        awareness_messages = [msg for msg in client2.received_messages if "awareness" in msg and "cursor" in msg]
        
        # The number of messages should be less than the number of updates sent (due to throttling)
        assert len(awareness_messages) < 10, "Awareness updates were not throttled"
        
        # Clean up
        await client1.disconnect()
        await client2.disconnect()
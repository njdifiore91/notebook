# -*- coding: utf-8 -*-
"""
Tests for the WebSocket handlers for collaborative editing in Jupyter Notebook v7.

This module tests the server-side WebSocket handlers for collaborative editing,
verifying that they correctly process Yjs update messages, broadcast changes to
connected clients, and handle connection lifecycle events.
"""

import asyncio
import json
import os
import pytest
import time
import uuid
from unittest.mock import MagicMock, patch, AsyncMock

try:
    import y_py as Y
    from pycrdt import Doc as YDoc
    HAS_COLLABORATION_DEPS = True
except ImportError:
    HAS_COLLABORATION_DEPS = False

from tornado.websocket import WebSocketClientConnection
from tornado.testing import AsyncHTTPTestCase, gen_test

from notebook.collab.handlers import CollaborationSocketHandler, YjsMessageType, CollaborationAPIHandler
from notebook.collab.persistence import CollaborationManager


# Skip all tests if collaboration dependencies are not installed
pytestmark = pytest.mark.skipif(not HAS_COLLABORATION_DEPS, reason="Collaboration dependencies not installed")


@pytest.fixture
def mock_collab_manager():
    """Fixture for mocking the CollaborationManager."""
    manager = MagicMock(spec=CollaborationManager)
    
    # Set up async method mocks
    manager.get_document_state = AsyncMock(return_value=b"document_state")
    manager.apply_update = AsyncMock(return_value=True)
    manager.update_awareness = AsyncMock()
    manager.get_awareness_states = AsyncMock(return_value={})
    manager.get_user_permissions = AsyncMock(return_value={"view": True, "edit": True})
    manager.get_cell_permissions = AsyncMock(return_value={"edit": True, "lock": True})
    manager.acquire_cell_lock = AsyncMock(return_value=True)
    manager.get_cell_lock = AsyncMock(return_value=None)
    manager.release_cell_lock = AsyncMock()
    manager.release_all_client_locks = AsyncMock()
    manager.should_create_snapshot = AsyncMock(return_value=False)
    manager.create_snapshot = AsyncMock()
    
    return manager


class MockWebSocket:
    """Mock WebSocket client for testing."""
    
    def __init__(self):
        self.messages = []
        self.closed = False
        self.close_code = None
        self.close_reason = None
    
    def write_message(self, message, binary=False):
        """Record a message sent by the handler."""
        self.messages.append((message, binary))
        return True
    
    def close(self, code=None, reason=None):
        """Record WebSocket close."""
        self.closed = True
        self.close_code = code
        self.close_reason = reason


class MockHandler(CollaborationSocketHandler):
    """Mock CollaborationSocketHandler for testing."""
    
    def __init__(self, mock_ws=None, document_id=None, client_id=None, user_id=None):
        # Initialize without calling super().__init__
        self.ws_connection = mock_ws or MockWebSocket()
        self.document_id = document_id or "test_doc"
        self.client_id = client_id or 12345
        self.user_id = user_id or "test_user"
        self.last_activity = time.time()
        self.permissions = {"view": True, "edit": True, "admin": False}
        self.authenticated = True
        self.current_user = {"name": self.user_id}
        self.request = MagicMock()
        self.application = MagicMock()
    
    def get_current_user(self):
        return self.current_user


@pytest.mark.asyncio
async def test_open_connection(mock_collab_manager):
    """Test WebSocket connection opening."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Call the open method
    await handler.open("test_doc")
    
    # Verify that the handler checked permissions
    mock_collab_manager.get_user_permissions.assert_called_once_with("test_doc", "test_user")
    
    # Verify that the handler retrieved the document state
    mock_collab_manager.get_document_state.assert_called_once_with("test_doc")
    
    # Verify that the handler sent the initial state to the client
    assert len(mock_ws.messages) > 0
    first_message, is_binary = mock_ws.messages[0]
    assert is_binary  # Should be a binary message
    assert first_message[0] == YjsMessageType.SYNC_REPLY  # First byte should be SYNC_REPLY


@pytest.mark.asyncio
async def test_open_connection_permission_denied(mock_collab_manager):
    """Test WebSocket connection opening with permission denied."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Configure the mock to deny permission
    mock_collab_manager.get_user_permissions.return_value = {"view": False}
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Call the open method
    await handler.open("test_doc")
    
    # Verify that the connection was closed with permission denied
    assert mock_ws.closed
    assert mock_ws.close_code == 1008  # Permission denied
    assert "Permission denied" in mock_ws.close_reason


@pytest.mark.asyncio
async def test_on_close(mock_collab_manager):
    """Test WebSocket connection closing."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    CollaborationSocketHandler.rooms = {"test_doc": set()}
    CollaborationSocketHandler.handler_info = {}
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc", client_id=12345)
    
    # Add the handler to the room
    CollaborationSocketHandler.rooms["test_doc"].add(handler)
    CollaborationSocketHandler.handler_info[handler] = ("test_doc", 12345)
    
    # Call the on_close method
    handler.on_close()
    
    # Verify that the handler was removed from the room
    assert handler not in CollaborationSocketHandler.rooms.get("test_doc", set())
    assert handler not in CollaborationSocketHandler.handler_info


@pytest.mark.asyncio
async def test_handle_sync_message(mock_collab_manager):
    """Test handling of Yjs document synchronization messages."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    CollaborationSocketHandler.rooms = {"test_doc": set()}
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Add the handler to the room
    CollaborationSocketHandler.rooms["test_doc"].add(handler)
    
    # Create a test update message
    update_message = b"test_update_data"
    
    # Call the handle_sync_message method
    await handler.handle_sync_message(update_message)
    
    # Verify that the update was applied to the document
    mock_collab_manager.apply_update.assert_called_once_with(
        "test_doc", update_message, 12345
    )


@pytest.mark.asyncio
async def test_handle_sync_message_permission_denied(mock_collab_manager):
    """Test handling of Yjs document synchronization messages with permission denied."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Configure the mock to deny edit permission
    mock_collab_manager.get_user_permissions.return_value = {"view": True, "edit": False}
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    handler.permissions = {"view": True, "edit": False}
    
    # Create a test update message
    update_message = b"test_update_data"
    
    # Call the handle_sync_message method
    await handler.handle_sync_message(update_message)
    
    # Verify that the update was not applied to the document
    mock_collab_manager.apply_update.assert_not_called()
    
    # Verify that an error message was sent
    assert any(isinstance(msg[0], str) and "Permission denied" in msg[0] for msg in mock_ws.messages)


@pytest.mark.asyncio
async def test_handle_awareness_message(mock_collab_manager):
    """Test handling of awareness update messages."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    CollaborationSocketHandler.rooms = {"test_doc": set()}
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Add the handler to the room
    CollaborationSocketHandler.rooms["test_doc"].add(handler)
    
    # Create a test awareness message
    awareness_message = b"test_awareness_data"
    
    # Call the handle_awareness_message method
    await handler.handle_awareness_message(awareness_message)
    
    # Verify that the awareness state was updated
    mock_collab_manager.update_awareness.assert_called_once_with(
        "test_doc", 12345, awareness_message
    )


@pytest.mark.asyncio
async def test_handle_lock_message(mock_collab_manager):
    """Test handling of cell lock request messages."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    CollaborationSocketHandler.rooms = {"test_doc": set()}
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Add the handler to the room
    CollaborationSocketHandler.rooms["test_doc"].add(handler)
    
    # Create a test lock message
    lock_data = {"cell_id": "cell123"}
    lock_message = json.dumps(lock_data).encode("utf-8")
    
    # Call the handle_lock_message method
    await handler.handle_lock_message(lock_message)
    
    # Verify that the lock was acquired
    mock_collab_manager.acquire_cell_lock.assert_called_once_with(
        "test_doc", "cell123", 12345, "test_user"
    )
    
    # Verify that a broadcast message was sent
    assert any(isinstance(msg[0], str) and "\"type\": \"lock\"" in msg[0] for msg in mock_ws.messages)


@pytest.mark.asyncio
async def test_handle_unlock_message(mock_collab_manager):
    """Test handling of cell unlock request messages."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    CollaborationSocketHandler.rooms = {"test_doc": set()}
    
    # Configure the mock to return a lock held by this client
    mock_collab_manager.get_cell_lock.return_value = {
        "client_id": 12345,
        "user_id": "test_user"
    }
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Add the handler to the room
    CollaborationSocketHandler.rooms["test_doc"].add(handler)
    
    # Create a test unlock message
    unlock_data = {"cell_id": "cell123"}
    unlock_message = json.dumps(unlock_data).encode("utf-8")
    
    # Call the handle_unlock_message method
    await handler.handle_unlock_message(unlock_message)
    
    # Verify that the lock was released
    mock_collab_manager.release_cell_lock.assert_called_once_with(
        "test_doc", "cell123", 12345
    )
    
    # Verify that a broadcast message was sent
    assert any(isinstance(msg[0], str) and "\"type\": \"unlock\"" in msg[0] for msg in mock_ws.messages)


@pytest.mark.asyncio
async def test_handle_unlock_message_not_lock_holder(mock_collab_manager):
    """Test handling of cell unlock request when client is not the lock holder."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Configure the mock to return a lock held by another client
    mock_collab_manager.get_cell_lock.return_value = {
        "client_id": 99999,  # Different client ID
        "user_id": "other_user"
    }
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Create a test unlock message
    unlock_data = {"cell_id": "cell123"}
    unlock_message = json.dumps(unlock_data).encode("utf-8")
    
    # Call the handle_unlock_message method
    await handler.handle_unlock_message(unlock_message)
    
    # Verify that the lock was not released
    mock_collab_manager.release_cell_lock.assert_not_called()
    
    # Verify that an error message was sent
    assert any(isinstance(msg[0], str) and "don't hold the lock" in msg[0] for msg in mock_ws.messages)


@pytest.mark.asyncio
async def test_broadcast_update(mock_collab_manager):
    """Test broadcasting of Yjs updates to connected clients."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create mock WebSockets
    mock_ws1 = MockWebSocket()
    mock_ws2 = MockWebSocket()
    mock_ws3 = MockWebSocket()
    
    # Create handler instances
    handler1 = MockHandler(mock_ws=mock_ws1, document_id="test_doc", client_id=1)
    handler2 = MockHandler(mock_ws=mock_ws2, document_id="test_doc", client_id=2)
    handler3 = MockHandler(mock_ws=mock_ws3, document_id="test_doc", client_id=3)
    
    # Set up the room with all handlers
    CollaborationSocketHandler.rooms = {"test_doc": {handler1, handler2, handler3}}
    
    # Create a test update message
    update_message = b"test_update_data"
    
    # Call the broadcast_update method from handler1
    await handler1.broadcast_update(update_message, exclude_self=True)
    
    # Verify that the update was sent to handler2 and handler3 but not handler1
    assert len(mock_ws1.messages) == 0  # Excluded self
    assert len(mock_ws2.messages) == 1
    assert len(mock_ws3.messages) == 1
    
    # Verify the message format
    message2, is_binary2 = mock_ws2.messages[0]
    assert is_binary2  # Should be a binary message
    assert message2[0] == YjsMessageType.SYNC  # First byte should be SYNC
    assert message2[1:] == update_message  # Rest should be the update data


@pytest.mark.asyncio
async def test_broadcast_awareness(mock_collab_manager):
    """Test broadcasting of awareness updates to connected clients."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create mock WebSockets
    mock_ws1 = MockWebSocket()
    mock_ws2 = MockWebSocket()
    
    # Create handler instances
    handler1 = MockHandler(mock_ws=mock_ws1, document_id="test_doc", client_id=1)
    handler2 = MockHandler(mock_ws=mock_ws2, document_id="test_doc", client_id=2)
    
    # Set up the room with both handlers
    CollaborationSocketHandler.rooms = {"test_doc": {handler1, handler2}}
    
    # Create a test awareness message
    awareness_message = b"test_awareness_data"
    
    # Call the broadcast_awareness method from handler1
    await handler1.broadcast_awareness(awareness_message, exclude_self=True)
    
    # Verify that the awareness update was sent to handler2 but not handler1
    assert len(mock_ws1.messages) == 0  # Excluded self
    assert len(mock_ws2.messages) == 1
    
    # Verify the message format
    message2, is_binary2 = mock_ws2.messages[0]
    assert is_binary2  # Should be a binary message
    assert message2[0] == YjsMessageType.AWARENESS  # First byte should be AWARENESS
    assert message2[1:] == awareness_message  # Rest should be the awareness data


@pytest.mark.asyncio
async def test_broadcast_json(mock_collab_manager):
    """Test broadcasting of JSON messages to connected clients."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create mock WebSockets
    mock_ws1 = MockWebSocket()
    mock_ws2 = MockWebSocket()
    
    # Create handler instances
    handler1 = MockHandler(mock_ws=mock_ws1, document_id="test_doc", client_id=1)
    handler2 = MockHandler(mock_ws=mock_ws2, document_id="test_doc", client_id=2)
    
    # Set up the room with both handlers
    CollaborationSocketHandler.rooms = {"test_doc": {handler1, handler2}}
    
    # Create a test JSON message
    json_data = {"type": "test", "data": "test_data"}
    
    # Call the broadcast_json method from handler1
    await handler1.broadcast_json(json_data)
    
    # Verify that the JSON message was sent to both handlers
    assert len(mock_ws1.messages) == 1
    assert len(mock_ws2.messages) == 1
    
    # Verify the message format
    message1, is_binary1 = mock_ws1.messages[0]
    assert not is_binary1  # Should be a text message
    assert json.loads(message1) == json_data


@pytest.mark.asyncio
async def test_on_message_sync(mock_collab_manager):
    """Test handling of SYNC message type."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Create a test SYNC message
    sync_message = bytes([YjsMessageType.SYNC]) + b"test_update_data"
    
    # Mock the handle_sync_message method
    handler.handle_sync_message = AsyncMock()
    
    # Call the on_message method
    await handler.on_message(sync_message)
    
    # Verify that handle_sync_message was called with the correct data
    handler.handle_sync_message.assert_called_once_with(b"test_update_data")


@pytest.mark.asyncio
async def test_on_message_awareness(mock_collab_manager):
    """Test handling of AWARENESS message type."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Create a test AWARENESS message
    awareness_message = bytes([YjsMessageType.AWARENESS]) + b"test_awareness_data"
    
    # Mock the handle_awareness_message method
    handler.handle_awareness_message = AsyncMock()
    
    # Call the on_message method
    await handler.on_message(awareness_message)
    
    # Verify that handle_awareness_message was called with the correct data
    handler.handle_awareness_message.assert_called_once_with(b"test_awareness_data")


@pytest.mark.asyncio
async def test_on_message_lock(mock_collab_manager):
    """Test handling of LOCK message type."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Create a test LOCK message
    lock_data = {"cell_id": "cell123"}
    lock_message = bytes([YjsMessageType.LOCK]) + json.dumps(lock_data).encode("utf-8")
    
    # Mock the handle_lock_message method
    handler.handle_lock_message = AsyncMock()
    
    # Call the on_message method
    await handler.on_message(lock_message)
    
    # Verify that handle_lock_message was called with the correct data
    handler.handle_lock_message.assert_called_once_with(json.dumps(lock_data).encode("utf-8"))


@pytest.mark.asyncio
async def test_on_message_unlock(mock_collab_manager):
    """Test handling of UNLOCK message type."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Create a test UNLOCK message
    unlock_data = {"cell_id": "cell123"}
    unlock_message = bytes([YjsMessageType.UNLOCK]) + json.dumps(unlock_data).encode("utf-8")
    
    # Mock the handle_unlock_message method
    handler.handle_unlock_message = AsyncMock()
    
    # Call the on_message method
    await handler.on_message(unlock_message)
    
    # Verify that handle_unlock_message was called with the correct data
    handler.handle_unlock_message.assert_called_once_with(json.dumps(unlock_data).encode("utf-8"))


@pytest.mark.asyncio
async def test_on_message_unknown_type(mock_collab_manager):
    """Test handling of unknown message type."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Create a test message with unknown type
    unknown_message = bytes([99]) + b"test_data"  # 99 is not a valid message type
    
    # Call the on_message method
    await handler.on_message(unknown_message)
    
    # No specific assertion needed - we're just making sure it doesn't raise an exception
    # In the actual implementation, it should log a warning


@pytest.mark.asyncio
async def test_on_message_non_binary(mock_collab_manager):
    """Test handling of non-binary message."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create a handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc")
    
    # Create a test non-binary message
    non_binary_message = "This is a text message"
    
    # Call the on_message method
    await handler.on_message(non_binary_message)
    
    # No specific assertion needed - we're just making sure it doesn't raise an exception
    # In the actual implementation, it should log a warning


@pytest.mark.asyncio
async def test_check_document_permission(mock_collab_manager):
    """Test checking document permissions."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a handler instance
    handler = MockHandler(document_id="test_doc", user_id="test_user")
    
    # Configure the mock to return permissions
    mock_collab_manager.get_user_permissions.return_value = {"view": True, "edit": True}
    
    # Call the check_document_permission method
    result = await handler.check_document_permission("test_doc")
    
    # Verify that the permissions were checked
    mock_collab_manager.get_user_permissions.assert_called_once_with("test_doc", "test_user")
    
    # Verify the result
    assert result is True
    assert handler.permissions == {"view": True, "edit": True}


@pytest.mark.asyncio
async def test_check_document_permission_denied(mock_collab_manager):
    """Test checking document permissions when denied."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a handler instance
    handler = MockHandler(document_id="test_doc", user_id="test_user")
    
    # Configure the mock to return permissions without view access
    mock_collab_manager.get_user_permissions.return_value = {"view": False, "edit": False}
    
    # Call the check_document_permission method
    result = await handler.check_document_permission("test_doc")
    
    # Verify that the permissions were checked
    mock_collab_manager.get_user_permissions.assert_called_once_with("test_doc", "test_user")
    
    # Verify the result
    assert result is False
    assert handler.permissions == {"view": False, "edit": False}


@pytest.mark.asyncio
async def test_check_edit_permission(mock_collab_manager):
    """Test checking edit permissions."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a handler instance
    handler = MockHandler(document_id="test_doc", user_id="test_user")
    handler.permissions = {"view": True, "edit": True}
    
    # Call the check_edit_permission method
    result = await handler.check_edit_permission("test_doc")
    
    # Verify the result
    assert result is True


@pytest.mark.asyncio
async def test_check_edit_permission_denied(mock_collab_manager):
    """Test checking edit permissions when denied."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a handler instance
    handler = MockHandler(document_id="test_doc", user_id="test_user")
    handler.permissions = {"view": True, "edit": False}
    
    # Call the check_edit_permission method
    result = await handler.check_edit_permission("test_doc")
    
    # Verify the result
    assert result is False


@pytest.mark.asyncio
async def test_check_cell_permission(mock_collab_manager):
    """Test checking cell-specific permissions."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a handler instance
    handler = MockHandler(document_id="test_doc", user_id="test_user")
    handler.permissions = {"view": True, "edit": True}
    
    # Configure the mock to return cell permissions
    mock_collab_manager.get_cell_permissions.return_value = {"edit": True, "lock": True}
    
    # Call the check_cell_permission method
    result = await handler.check_cell_permission("test_doc", "cell123", "lock")
    
    # Verify that the cell permissions were checked
    mock_collab_manager.get_cell_permissions.assert_called_once_with(
        "test_doc", "cell123", "test_user"
    )
    
    # Verify the result
    assert result is True


@pytest.mark.asyncio
async def test_check_cell_permission_denied(mock_collab_manager):
    """Test checking cell-specific permissions when denied."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a handler instance
    handler = MockHandler(document_id="test_doc", user_id="test_user")
    handler.permissions = {"view": True, "edit": True}
    
    # Configure the mock to return cell permissions without lock permission
    mock_collab_manager.get_cell_permissions.return_value = {"edit": True, "lock": False}
    
    # Call the check_cell_permission method
    result = await handler.check_cell_permission("test_doc", "cell123", "lock")
    
    # Verify that the cell permissions were checked
    mock_collab_manager.get_cell_permissions.assert_called_once_with(
        "test_doc", "cell123", "test_user"
    )
    
    # Verify the result
    assert result is False


@pytest.mark.asyncio
async def test_check_cell_permission_document_permission_denied(mock_collab_manager):
    """Test checking cell permissions when document-level edit permission is denied."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    
    # Create a handler instance
    handler = MockHandler(document_id="test_doc", user_id="test_user")
    handler.permissions = {"view": True, "edit": False}  # No edit permission at document level
    
    # Call the check_cell_permission method
    result = await handler.check_cell_permission("test_doc", "cell123", "lock")
    
    # Verify that cell permissions were not checked (short-circuited by document permission check)
    mock_collab_manager.get_cell_permissions.assert_not_called()
    
    # Verify the result
    assert result is False


# Test the CollaborationAPIHandler

class MockAPIHandler(CollaborationAPIHandler):
    """Mock CollaborationAPIHandler for testing."""
    
    def __init__(self):
        # Initialize without calling super().__init__
        self.current_user = {"name": "test_user"}
        self.request = MagicMock()
        self.request.body = b"{}"
        self.application = MagicMock()
        self.written_data = []
        self.status_code = 200
        self.error_message = None
    
    def get_current_user(self):
        return self.current_user
    
    def write(self, data):
        self.written_data.append(data)
    
    def set_status(self, status_code):
        self.status_code = status_code
    
    def send_error(self, status_code, **kwargs):
        self.status_code = status_code
        self.error_message = kwargs.get("message")


@pytest.mark.asyncio
async def test_api_handler_get_permissions(mock_collab_manager):
    """Test GET request for permissions."""
    # Set up the handler class with the mock manager
    CollaborationAPIHandler.collab_manager = mock_collab_manager
    
    # Configure the mock to return permissions
    mock_collab_manager.get_user_permissions.return_value = {"view": True, "edit": True}
    mock_collab_manager.list_permissions.return_value = [
        {"user_id": "user1", "role": "editor"},
        {"user_id": "user2", "role": "viewer"}
    ]
    
    # Create a handler instance
    handler = MockAPIHandler()
    
    # Call the get method for permissions endpoint
    await handler.get("permissions", "test_doc")
    
    # Verify that permissions were checked
    mock_collab_manager.get_user_permissions.assert_called_once_with("test_doc", "test_user")
    
    # Verify that permissions were listed
    mock_collab_manager.list_permissions.assert_called_once_with("test_doc")
    
    # Verify the response
    assert len(handler.written_data) == 1
    assert json.loads(handler.written_data[0]) == [
        {"user_id": "user1", "role": "editor"},
        {"user_id": "user2", "role": "viewer"}
    ]


@pytest.mark.asyncio
async def test_api_handler_get_permission_denied(mock_collab_manager):
    """Test GET request for permissions when permission is denied."""
    # Set up the handler class with the mock manager
    CollaborationAPIHandler.collab_manager = mock_collab_manager
    
    # Configure the mock to deny permission
    mock_collab_manager.get_user_permissions.return_value = {"view": False}
    
    # Create a handler instance
    handler = MockAPIHandler()
    
    # Call the get method for permissions endpoint
    await handler.get("permissions", "test_doc")
    
    # Verify that permissions were checked
    mock_collab_manager.get_user_permissions.assert_called_once_with("test_doc", "test_user")
    
    # Verify that permissions were not listed
    mock_collab_manager.list_permissions.assert_not_called()
    
    # Verify the error response
    assert handler.status_code == 403
    assert handler.error_message == "Permission denied"


@pytest.mark.asyncio
async def test_api_handler_post_permission(mock_collab_manager):
    """Test POST request for creating a permission."""
    # Set up the handler class with the mock manager
    CollaborationAPIHandler.collab_manager = mock_collab_manager
    
    # Configure the mock to return admin permissions
    mock_collab_manager.get_user_permissions.return_value = {"view": True, "edit": True, "admin": True}
    mock_collab_manager.create_permission.return_value = "perm123"
    
    # Create a handler instance
    handler = MockAPIHandler()
    handler.request.body = json.dumps({"user_id": "user3", "role": "editor"}).encode("utf-8")
    
    # Call the post method for permissions endpoint
    await handler.post("permissions", "test_doc")
    
    # Verify that permissions were checked
    mock_collab_manager.get_user_permissions.assert_called_once_with("test_doc", "test_user")
    
    # Verify that permission was created
    mock_collab_manager.create_permission.assert_called_once_with(
        "test_doc", {"user_id": "user3", "role": "editor"}
    )
    
    # Verify the response
    assert handler.status_code == 201
    assert len(handler.written_data) == 1
    assert json.loads(handler.written_data[0]) == {"id": "perm123"}


@pytest.mark.asyncio
async def test_api_handler_post_permission_not_admin(mock_collab_manager):
    """Test POST request for creating a permission when not admin."""
    # Set up the handler class with the mock manager
    CollaborationAPIHandler.collab_manager = mock_collab_manager
    
    # Configure the mock to return non-admin permissions
    mock_collab_manager.get_user_permissions.return_value = {"view": True, "edit": True, "admin": False}
    
    # Create a handler instance
    handler = MockAPIHandler()
    handler.request.body = json.dumps({"user_id": "user3", "role": "editor"}).encode("utf-8")
    
    # Call the post method for permissions endpoint
    await handler.post("permissions", "test_doc")
    
    # Verify that permissions were checked
    mock_collab_manager.get_user_permissions.assert_called_once_with("test_doc", "test_user")
    
    # Verify that permission was not created
    mock_collab_manager.create_permission.assert_not_called()
    
    # Verify the error response
    assert handler.status_code == 403
    assert handler.error_message == "Admin permission required"


# Integration test with multiple clients

@pytest.mark.asyncio
async def test_multiple_clients_sync(mock_collab_manager):
    """Test synchronization between multiple clients."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    CollaborationSocketHandler.rooms = {}
    CollaborationSocketHandler.handler_info = {}
    
    # Create mock WebSockets
    mock_ws1 = MockWebSocket()
    mock_ws2 = MockWebSocket()
    mock_ws3 = MockWebSocket()
    
    # Create handler instances
    handler1 = MockHandler(mock_ws=mock_ws1, document_id="test_doc", client_id=1, user_id="user1")
    handler2 = MockHandler(mock_ws=mock_ws2, document_id="test_doc", client_id=2, user_id="user2")
    handler3 = MockHandler(mock_ws=mock_ws3, document_id="test_doc", client_id=3, user_id="user3")
    
    # Initialize the room
    CollaborationSocketHandler.rooms["test_doc"] = {handler1, handler2, handler3}
    CollaborationSocketHandler.handler_info[handler1] = ("test_doc", 1)
    CollaborationSocketHandler.handler_info[handler2] = ("test_doc", 2)
    CollaborationSocketHandler.handler_info[handler3] = ("test_doc", 3)
    
    # Create a test update message
    update_message = b"test_update_data"
    
    # Simulate client1 sending an update
    await handler1.handle_sync_message(update_message)
    
    # Verify that the update was applied to the document
    mock_collab_manager.apply_update.assert_called_once_with(
        "test_doc", update_message, 1
    )
    
    # Verify that the update was broadcast to other clients
    assert len(mock_ws1.messages) == 0  # No message to self (handled by broadcast_update)
    assert len(mock_ws2.messages) == 1
    assert len(mock_ws3.messages) == 1
    
    # Verify the message format for client2
    message2, is_binary2 = mock_ws2.messages[0]
    assert is_binary2  # Should be a binary message
    assert message2[0] == YjsMessageType.SYNC  # First byte should be SYNC
    assert message2[1:] == update_message  # Rest should be the update data
    
    # Verify the message format for client3
    message3, is_binary3 = mock_ws3.messages[0]
    assert is_binary3  # Should be a binary message
    assert message3[0] == YjsMessageType.SYNC  # First byte should be SYNC
    assert message3[1:] == update_message  # Rest should be the update data


@pytest.mark.asyncio
async def test_client_disconnect_cleanup(mock_collab_manager):
    """Test cleanup when a client disconnects."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    CollaborationSocketHandler.rooms = {}
    CollaborationSocketHandler.handler_info = {}
    
    # Create mock WebSockets
    mock_ws1 = MockWebSocket()
    mock_ws2 = MockWebSocket()
    
    # Create handler instances
    handler1 = MockHandler(mock_ws=mock_ws1, document_id="test_doc", client_id=1, user_id="user1")
    handler2 = MockHandler(mock_ws=mock_ws2, document_id="test_doc", client_id=2, user_id="user2")
    
    # Initialize the room
    CollaborationSocketHandler.rooms["test_doc"] = {handler1, handler2}
    CollaborationSocketHandler.handler_info[handler1] = ("test_doc", 1)
    CollaborationSocketHandler.handler_info[handler2] = ("test_doc", 2)
    
    # Simulate client1 disconnecting
    handler1.on_close()
    
    # Verify that handler1 was removed from the room
    assert handler1 not in CollaborationSocketHandler.rooms["test_doc"]
    assert handler1 not in CollaborationSocketHandler.handler_info
    
    # Verify that handler2 is still in the room
    assert handler2 in CollaborationSocketHandler.rooms["test_doc"]
    assert handler2 in CollaborationSocketHandler.handler_info
    
    # Verify that locks held by client1 were released
    mock_collab_manager.release_all_client_locks.assert_called_once_with("test_doc", 1)


@pytest.mark.asyncio
async def test_empty_room_cleanup(mock_collab_manager):
    """Test cleanup when a room becomes empty."""
    # Set up the handler class with the mock manager
    CollaborationSocketHandler.collab_manager = mock_collab_manager
    CollaborationSocketHandler.rooms = {}
    CollaborationSocketHandler.handler_info = {}
    
    # Create mock WebSocket
    mock_ws = MockWebSocket()
    
    # Create handler instance
    handler = MockHandler(mock_ws=mock_ws, document_id="test_doc", client_id=1, user_id="user1")
    
    # Initialize the room with just one handler
    CollaborationSocketHandler.rooms["test_doc"] = {handler}
    CollaborationSocketHandler.handler_info[handler] = ("test_doc", 1)
    
    # Simulate the client disconnecting
    handler.on_close()
    
    # Verify that the room was removed
    assert "test_doc" not in CollaborationSocketHandler.rooms
    assert handler not in CollaborationSocketHandler.handler_info
    
    # Verify that locks held by the client were released
    mock_collab_manager.release_all_client_locks.assert_called_once_with("test_doc", 1)
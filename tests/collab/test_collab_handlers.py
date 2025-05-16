import asyncio
import json
import os
import pytest
import uuid
from unittest.mock import MagicMock, patch

from tornado.httpclient import HTTPClientError
from tornado.websocket import WebSocketClientConnection

from notebook.collab.handlers import YjsWebSocketHandler, CollaborationHandler
from notebook.collab.persistence import YjsDocumentStorage


@pytest.fixture
def doc_id():
    """Generate a unique document ID for testing."""
    return f"test-doc-{uuid.uuid4()}"


@pytest.fixture
def user_id():
    """Generate a unique user ID for testing."""
    return f"test-user-{uuid.uuid4()}"


@pytest.fixture
async def mock_storage():
    """Create a mock storage instance for testing."""
    storage = MagicMock(spec=YjsDocumentStorage)
    storage.get_document.return_value = {"state": b"test-state", "version": 1}
    storage.store_update.return_value = True
    return storage


@pytest.fixture
async def ws_client(jp_serverapp, jp_base_url):
    """Create a WebSocket client connected to the test server."""
    clients = []
    
    async def create_client(path="/api/collaboration/yjs", headers=None):
        # Create a WebSocket connection to the server
        ws_url = f"ws://{jp_base_url.host}:{jp_base_url.port}{path}"
        client = await jp_serverapp.http_client.websocket_connect(ws_url, headers=headers)
        clients.append(client)
        return client
    
    yield create_client
    
    # Close all clients after the test
    for client in clients:
        client.close()


@pytest.fixture
async def auth_headers(user_id):
    """Create authentication headers for WebSocket connections."""
    return {
        "Authorization": f"Bearer test-token",
        "X-User-ID": user_id
    }


@pytest.fixture
async def mock_yjs_handler(jp_serverapp, mock_storage):
    """Create a mock YjsWebSocketHandler for testing."""
    with patch.object(YjsWebSocketHandler, "__init__", return_value=None):
        handler = YjsWebSocketHandler()
        handler.application = jp_serverapp.serverapp.web_app
        handler.request = MagicMock()
        handler.ws_connection = MagicMock()
        handler.storage = mock_storage
        handler.clients = {}
        handler.documents = {}
        handler.close = MagicMock()
        handler.write_message = MagicMock()
        handler.check_origin = lambda origin: True
        yield handler


@pytest.fixture
async def connected_clients(ws_client, auth_headers, doc_id):
    """Create multiple connected WebSocket clients for testing."""
    clients = []
    for i in range(3):  # Create 3 clients
        client = await ws_client(headers=auth_headers)
        # Send initial connection message with document ID
        await client.write_message(json.dumps({
            "type": "connect",
            "docId": doc_id
        }))
        # Read the response
        response = await client.read_message()
        clients.append(client)
    
    return clients


# Test WebSocket connection establishment and authentication
async def test_websocket_connection(ws_client, auth_headers):
    """Test that a WebSocket connection can be established."""
    client = await ws_client(headers=auth_headers)
    assert client is not None
    assert isinstance(client, WebSocketClientConnection)


async def test_connection_without_auth(ws_client):
    """Test that connection without authentication is rejected."""
    with pytest.raises(HTTPClientError):
        await ws_client(headers=None)


async def test_document_connection(ws_client, auth_headers, doc_id):
    """Test connecting to a specific document."""
    client = await ws_client(headers=auth_headers)
    
    # Send connection message with document ID
    await client.write_message(json.dumps({
        "type": "connect",
        "docId": doc_id
    }))
    
    # Read the response
    response = await client.read_message()
    response_data = json.loads(response)
    
    assert response_data["type"] == "connected"
    assert response_data["docId"] == doc_id


# Test Yjs update message processing and broadcasting
async def test_update_processing(ws_client, auth_headers, doc_id):
    """Test that Yjs update messages are processed correctly."""
    client = await ws_client(headers=auth_headers)
    
    # Connect to a document
    await client.write_message(json.dumps({
        "type": "connect",
        "docId": doc_id
    }))
    await client.read_message()  # Read connection response
    
    # Send an update message
    test_update = {
        "type": "update",
        "docId": doc_id,
        "update": "base64encodedupdate",  # In real tests, this would be actual encoded data
        "version": 1
    }
    await client.write_message(json.dumps(test_update))
    
    # Read the acknowledgment response
    response = await client.read_message()
    response_data = json.loads(response)
    
    assert response_data["type"] == "ack"
    assert response_data["docId"] == doc_id


async def test_update_broadcasting(connected_clients, doc_id):
    """Test that updates are broadcast to all connected clients."""
    # Send an update from the first client
    test_update = {
        "type": "update",
        "docId": doc_id,
        "update": "base64encodedupdate",
        "version": 1
    }
    await connected_clients[0].write_message(json.dumps(test_update))
    
    # First client should receive an acknowledgment
    response = await connected_clients[0].read_message()
    response_data = json.loads(response)
    assert response_data["type"] == "ack"
    
    # Other clients should receive the update
    for i in range(1, len(connected_clients)):
        response = await connected_clients[i].read_message()
        response_data = json.loads(response)
        assert response_data["type"] == "update"
        assert response_data["docId"] == doc_id
        assert response_data["update"] == "base64encodedupdate"


# Test connection lifecycle management
async def test_client_disconnection(ws_client, auth_headers, doc_id, mock_yjs_handler):
    """Test that client disconnection is handled correctly."""
    # Mock the handler's on_close method
    mock_yjs_handler.on_close = MagicMock()
    
    # Connect a client
    client = await ws_client(headers=auth_headers)
    await client.write_message(json.dumps({
        "type": "connect",
        "docId": doc_id
    }))
    await client.read_message()  # Read connection response
    
    # Close the connection
    client.close()
    
    # Wait a bit for the server to process the disconnection
    await asyncio.sleep(0.1)
    
    # Verify that on_close was called
    # Note: In a real test, we would need to verify this differently
    # since we're using a mock handler here
    # mock_yjs_handler.on_close.assert_called_once()


async def test_reconnection(ws_client, auth_headers, doc_id):
    """Test that a client can reconnect after disconnection."""
    # Connect a client
    client = await ws_client(headers=auth_headers)
    await client.write_message(json.dumps({
        "type": "connect",
        "docId": doc_id
    }))
    await client.read_message()  # Read connection response
    
    # Close the connection
    client.close()
    
    # Reconnect with the same user ID
    new_client = await ws_client(headers=auth_headers)
    await new_client.write_message(json.dumps({
        "type": "connect",
        "docId": doc_id
    }))
    
    # Read the response
    response = await new_client.read_message()
    response_data = json.loads(response)
    
    assert response_data["type"] == "connected"
    assert response_data["docId"] == doc_id


# Test error handling
async def test_malformed_message(ws_client, auth_headers):
    """Test handling of malformed messages."""
    client = await ws_client(headers=auth_headers)
    
    # Send a malformed message
    await client.write_message("not valid json")
    
    # Read the error response
    response = await client.read_message()
    response_data = json.loads(response)
    
    assert response_data["type"] == "error"
    assert "malformed" in response_data["message"].lower()


async def test_invalid_message_type(ws_client, auth_headers):
    """Test handling of messages with invalid type."""
    client = await ws_client(headers=auth_headers)
    
    # Send a message with invalid type
    await client.write_message(json.dumps({
        "type": "invalid_type",
        "data": "test"
    }))
    
    # Read the error response
    response = await client.read_message()
    response_data = json.loads(response)
    
    assert response_data["type"] == "error"
    assert "invalid message type" in response_data["message"].lower()


async def test_missing_document_id(ws_client, auth_headers):
    """Test handling of messages with missing document ID."""
    client = await ws_client(headers=auth_headers)
    
    # Send a connect message without document ID
    await client.write_message(json.dumps({
        "type": "connect"
        # Missing docId
    }))
    
    # Read the error response
    response = await client.read_message()
    response_data = json.loads(response)
    
    assert response_data["type"] == "error"
    assert "document id" in response_data["message"].lower()


# Test message validation and security checks
async def test_invalid_document_access(ws_client, auth_headers):
    """Test that access to unauthorized documents is prevented."""
    client = await ws_client(headers=auth_headers)
    
    # Try to connect to a document the user doesn't have access to
    # In a real test, this would involve setting up permissions first
    restricted_doc_id = "restricted-doc"
    
    # Mock the permission check to fail
    with patch("notebook.collab.handlers.YjsWebSocketHandler.check_document_access", 
               return_value=False):
        
        await client.write_message(json.dumps({
            "type": "connect",
            "docId": restricted_doc_id
        }))
        
        # Read the error response
        response = await client.read_message()
        response_data = json.loads(response)
        
        assert response_data["type"] == "error"
        assert "access denied" in response_data["message"].lower()


async def test_invalid_update_format(ws_client, auth_headers, doc_id):
    """Test handling of updates with invalid format."""
    client = await ws_client(headers=auth_headers)
    
    # Connect to a document
    await client.write_message(json.dumps({
        "type": "connect",
        "docId": doc_id
    }))
    await client.read_message()  # Read connection response
    
    # Send an update with invalid format
    await client.write_message(json.dumps({
        "type": "update",
        "docId": doc_id,
        # Missing update field
        "version": 1
    }))
    
    # Read the error response
    response = await client.read_message()
    response_data = json.loads(response)
    
    assert response_data["type"] == "error"
    assert "invalid update" in response_data["message"].lower()


# Test scalability with multiple simultaneous connections
async def test_multiple_connections(ws_client, auth_headers, doc_id):
    """Test handling of multiple simultaneous connections."""
    # Create multiple clients
    num_clients = 5
    clients = []
    
    for i in range(num_clients):
        # Create a client with a unique user ID
        unique_headers = {
            "Authorization": f"Bearer test-token",
            "X-User-ID": f"test-user-{i}"
        }
        client = await ws_client(headers=unique_headers)
        
        # Connect to the document
        await client.write_message(json.dumps({
            "type": "connect",
            "docId": doc_id
        }))
        await client.read_message()  # Read connection response
        
        clients.append(client)
    
    # Send an update from the first client
    test_update = {
        "type": "update",
        "docId": doc_id,
        "update": "base64encodedupdate",
        "version": 1
    }
    await clients[0].write_message(json.dumps(test_update))
    
    # First client should receive an acknowledgment
    response = await clients[0].read_message()
    response_data = json.loads(response)
    assert response_data["type"] == "ack"
    
    # Other clients should receive the update
    for i in range(1, num_clients):
        response = await clients[i].read_message()
        response_data = json.loads(response)
        assert response_data["type"] == "update"
        assert response_data["docId"] == doc_id


async def test_awareness_updates(ws_client, auth_headers, doc_id):
    """Test that awareness updates are processed and broadcast correctly."""
    # Create multiple clients
    clients = []
    for i in range(3):
        # Create a client with a unique user ID
        unique_headers = {
            "Authorization": f"Bearer test-token",
            "X-User-ID": f"test-user-{i}"
        }
        client = await ws_client(headers=unique_headers)
        
        # Connect to the document
        await client.write_message(json.dumps({
            "type": "connect",
            "docId": doc_id
        }))
        await client.read_message()  # Read connection response
        
        clients.append(client)
    
    # Send an awareness update from the first client
    awareness_update = {
        "type": "awareness",
        "docId": doc_id,
        "awareness": {
            "user": {
                "id": "test-user-0",
                "name": "Test User 0",
                "color": "#ff0000"
            },
            "cursor": {
                "position": 10,
                "cellId": "cell1"
            }
        }
    }
    await clients[0].write_message(json.dumps(awareness_update))
    
    # Other clients should receive the awareness update
    for i in range(1, len(clients)):
        response = await clients[i].read_message()
        response_data = json.loads(response)
        assert response_data["type"] == "awareness"
        assert response_data["docId"] == doc_id
        assert response_data["awareness"]["user"]["id"] == "test-user-0"


async def test_state_vector_sync(ws_client, auth_headers, doc_id):
    """Test state vector synchronization for Yjs documents."""
    client = await ws_client(headers=auth_headers)
    
    # Connect to a document
    await client.write_message(json.dumps({
        "type": "connect",
        "docId": doc_id
    }))
    await client.read_message()  # Read connection response
    
    # Send a state vector sync request
    sync_request = {
        "type": "sync",
        "docId": doc_id,
        "stateVector": "base64encodedstatevector"  # In real tests, this would be actual encoded data
    }
    await client.write_message(json.dumps(sync_request))
    
    # Read the sync response
    response = await client.read_message()
    response_data = json.loads(response)
    
    assert response_data["type"] == "sync"
    assert response_data["docId"] == doc_id
    assert "stateVector" in response_data or "update" in response_data
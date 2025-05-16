import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch

# Fixtures for testing Yjs and collaboration features

@pytest.fixture
def mock_yjs_shared_map():
    """Create a mock Yjs shared map for testing."""
    # This simulates the Yjs shared map that stores data
    mock_map = MagicMock()
    # Store the data in a dictionary for easy testing
    mock_map.data = {}
    
    # Mock the get method to retrieve from the data dictionary
    def mock_get(key, txn=None):
        return mock_map.data.get(key)
    mock_map.get = mock_get
    
    # Mock the set method to store in the data dictionary
    def mock_set(key, value, txn=None):
        mock_map.data[key] = value
    mock_map.set = mock_set
    
    # Mock the delete method to remove from the data dictionary
    def mock_delete(key, txn=None):
        if key in mock_map.data:
            del mock_map.data[key]
    mock_map.delete = mock_delete
    
    # Mock the keys method to return all keys in the data dictionary
    def mock_keys():
        return list(mock_map.data.keys())
    mock_map.keys = mock_keys
    
    return mock_map

@pytest.fixture
def mock_yjs_shared_array():
    """Create a mock Yjs shared array for testing."""
    mock_array = MagicMock()
    # Store the data in a list for easy testing
    mock_array.data = []
    
    # Mock the insert method to insert into the data list
    def mock_insert(index, value, txn=None):
        mock_array.data.insert(index, value)
    mock_array.insert = mock_insert
    
    # Mock the push_back method to append to the data list
    def mock_push_back(value, txn=None):
        mock_array.data.append(value)
    mock_array.push_back = mock_push_back
    
    # Mock the delete method to remove from the data list
    def mock_delete(index, length=1, txn=None):
        del mock_array.data[index:index+length]
    mock_array.delete = mock_delete
    
    # Mock the get method to retrieve from the data list
    def mock_get(index):
        return mock_array.data[index]
    mock_array.get = mock_get
    
    # Mock the length property to return the length of the data list
    @property
    def mock_length():
        return len(mock_array.data)
    mock_array.length = mock_length
    
    return mock_array

@pytest.fixture
def mock_yjs_shared_text():
    """Create a mock Yjs shared text for testing."""
    mock_text = MagicMock()
    # Store the text as a string for easy testing
    mock_text.data = ""
    
    # Mock the insert method to insert into the text
    def mock_insert(index, text, txn=None):
        mock_text.data = mock_text.data[:index] + text + mock_text.data[index:]
    mock_text.insert = mock_insert
    
    # Mock the delete method to remove from the text
    def mock_delete(index, length, txn=None):
        mock_text.data = mock_text.data[:index] + mock_text.data[index+length:]
    mock_text.delete = mock_delete
    
    # Mock the toString method to return the text
    def mock_to_string():
        return mock_text.data
    mock_text.toString = mock_to_string
    
    # Mock the length property to return the length of the text
    @property
    def mock_length():
        return len(mock_text.data)
    mock_text.length = mock_length
    
    return mock_text

@pytest.fixture
def mock_yjs_doc(mock_yjs_shared_map, mock_yjs_shared_array, mock_yjs_shared_text):
    """Create a mock Yjs document for testing."""
    mock_doc = MagicMock()
    
    # Store maps, arrays, and texts in dictionaries for easy testing
    mock_doc.maps = {}
    mock_doc.arrays = {}
    mock_doc.texts = {}
    
    # Mock the get_map method to return a mock shared map
    def mock_get_map(name):
        if name not in mock_doc.maps:
            mock_doc.maps[name] = mock_yjs_shared_map
        return mock_doc.maps[name]
    mock_doc.get_map = mock_get_map
    
    # Mock the get_array method to return a mock shared array
    def mock_get_array(name):
        if name not in mock_doc.arrays:
            mock_doc.arrays[name] = mock_yjs_shared_array
        return mock_doc.arrays[name]
    mock_doc.get_array = mock_get_array
    
    # Mock the get_text method to return a mock shared text
    def mock_get_text(name):
        if name not in mock_doc.texts:
            mock_doc.texts[name] = mock_yjs_shared_text
        return mock_doc.texts[name]
    mock_doc.get_text = mock_get_text
    
    # Mock the transaction method to execute the callback with a transaction object
    def mock_transaction(callback):
        mock_txn = MagicMock()
        callback(mock_txn)
    mock_doc.transaction = mock_transaction
    
    # Mock the on_update method to register update callbacks
    mock_doc.update_callbacks = []
    def mock_on_update(callback):
        mock_doc.update_callbacks.append(callback)
        # Return a function to unregister the callback
        return lambda: mock_doc.update_callbacks.remove(callback)
    mock_doc.on_update = mock_on_update
    
    # Method to simulate an update event
    def mock_emit_update(update_data=None):
        if update_data is None:
            update_data = {"type": "update"}
        for callback in mock_doc.update_callbacks:
            callback(update_data)
    mock_doc.emit_update = mock_emit_update
    
    return mock_doc

@pytest.fixture
def mock_users():
    """Create mock users for testing collaborative features."""
    return {
        'user1': {'id': 'user1', 'name': 'User One', 'color': '#ff0000'},
        'user2': {'id': 'user2', 'name': 'User Two', 'color': '#00ff00'},
        'admin': {'id': 'admin', 'name': 'Admin User', 'color': '#0000ff', 'is_admin': True}
    }

@pytest.fixture
def mock_cells():
    """Create mock cells for testing."""
    return {
        'cell1': {'id': 'cell1', 'type': 'code', 'source': 'print("Hello, world!")'},
        'cell2': {'id': 'cell2', 'type': 'markdown', 'source': '# Test Markdown'},
        'cell3': {'id': 'cell3', 'type': 'code', 'source': 'import numpy as np\nnp.random.rand(10)'}
    }

@pytest.fixture
def mock_notebook(mock_cells):
    """Create a mock notebook for testing."""
    return {
        "metadata": {"kernelspec": {"name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": list(mock_cells.values())
    }

@pytest.fixture
def mock_websocket_client():
    """Create a mock WebSocket client for testing."""
    client = MagicMock()
    
    # Store sent messages for inspection
    client.sent_messages = []
    
    # Mock the write_message method to store sent messages
    async def mock_write_message(message):
        if isinstance(message, str):
            message = json.loads(message)
        client.sent_messages.append(message)
    client.write_message = mock_write_message
    
    # Mock the close method
    async def mock_close():
        pass
    client.close = mock_close
    
    return client

@pytest.fixture
def mock_websocket_clients(mock_users):
    """Create mock WebSocket clients for each user."""
    clients = {}
    for user_id, user_info in mock_users.items():
        client = MagicMock()
        client.user_id = user_id
        client.user_info = user_info
        
        # Store sent messages for inspection
        client.sent_messages = []
        
        # Mock the write_message method to store sent messages
        async def mock_write_message(message, client=client):
            if isinstance(message, str):
                message = json.loads(message)
            client.sent_messages.append(message)
        client.write_message = mock_write_message
        
        # Mock the close method
        async def mock_close():
            pass
        client.close = mock_close
        
        clients[user_id] = client
    return clients

@pytest.fixture
def mock_collaboration_manager(mock_yjs_doc, mock_websocket_clients):
    """Create a mock collaboration manager for testing."""
    # Import here to avoid circular imports during test collection
    with patch('notebook.collab.provider.YDoc', return_value=mock_yjs_doc):
        # Import the CollaborationManager class
        from notebook.collab.provider import CollaborationManager
        
        # Create a collaboration manager with the mock Yjs document
        collab_manager = CollaborationManager()
        
        # Register the mock clients
        for user_id, client in mock_websocket_clients.items():
            collab_manager.register_client(client, user_id)
        
        yield collab_manager
        
        # Clean up
        for user_id, client in mock_websocket_clients.items():
            collab_manager.unregister_client(client)
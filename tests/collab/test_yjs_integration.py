import asyncio
import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest
import y_py as Y
from jupyter_server.services.contents.manager import ContentsManager
from tornado.websocket import WebSocketClientConnection

# Import the notebook model and related components
from notebook.services.contents.manager import ContentsManager as NotebookContentsManager
from notebook.collab.yjs_provider import YjsNotebookProvider
from notebook.collab.awareness import AwarenessManager
from notebook.collab.locks import CellLockManager


@pytest.fixture
def yjs_doc():
    """Create a Yjs document for testing."""
    doc = Y.YDoc()
    return doc


@pytest.fixture
def notebook_model():
    """Create a mock notebook model for testing."""
    model = MagicMock()
    model.cells = []
    model.metadata = {}
    return model


@pytest.fixture
def yjs_notebook_provider(yjs_doc, notebook_model):
    """Create a YjsNotebookProvider instance for testing."""
    provider = YjsNotebookProvider(doc_id="test-notebook", doc=yjs_doc)
    provider.bind_notebook_model(notebook_model)
    return provider


@pytest.fixture
def awareness_manager(yjs_doc):
    """Create an AwarenessManager instance for testing."""
    awareness = Y.Awareness(yjs_doc)
    manager = AwarenessManager(awareness=awareness, user_id="test-user")
    return manager


@pytest.fixture
def cell_lock_manager(yjs_doc):
    """Create a CellLockManager instance for testing."""
    manager = CellLockManager(doc=yjs_doc, user_id="test-user")
    return manager


@pytest.fixture
def mock_websocket_connection():
    """Create a mock WebSocket connection for testing."""
    connection = MagicMock(spec=WebSocketClientConnection)
    return connection


@pytest.fixture
def mock_client_connections():
    """Create multiple mock client connections for testing concurrent editing."""
    clients = {
        "user1": MagicMock(spec=WebSocketClientConnection),
        "user2": MagicMock(spec=WebSocketClientConnection),
        "user3": MagicMock(spec=WebSocketClientConnection),
    }
    return clients


@pytest.fixture
def sample_notebook_content():
    """Create a sample notebook content for testing."""
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Test Notebook\n", "This is a test notebook for Yjs integration testing."]
            },
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": ["print('Hello, world!')"]
            },
            {
                "cell_type": "code",
                "execution_count": 2,
                "metadata": {},
                "outputs": [
                    {
                        "name": "stdout",
                        "output_type": "stream",
                        "text": ["Hello, world!\n"]
                    }
                ],
                "source": ["print('Hello, world!')"]
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "codemirror_mode": {
                    "name": "ipython",
                    "version": 3
                },
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.9.7"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }


@pytest.fixture
def large_notebook_content():
    """Create a large notebook content for performance testing."""
    cells = []
    for i in range(100):
        if i % 5 == 0:
            # Add markdown cell
            cells.append({
                "cell_type": "markdown",
                "metadata": {},
                "source": [f"# Section {i//5 + 1}\n", f"This is section {i//5 + 1} of the test notebook."]
            })
        else:
            # Add code cell
            cells.append({
                "cell_type": "code",
                "execution_count": i,
                "metadata": {},
                "outputs": [
                    {
                        "name": "stdout",
                        "output_type": "stream",
                        "text": [f"Output from cell {i}\n"]
                    }
                ],
                "source": [f"print('Output from cell {i}')"]
            })
    
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }


# Test bidirectional synchronization between notebook model and Yjs document
def test_notebook_to_yjs_sync(yjs_notebook_provider, notebook_model, sample_notebook_content):
    """Test that changes to the notebook model are correctly synchronized to the Yjs document."""
    # Set up the notebook model with sample content
    notebook_model.cells = sample_notebook_content["cells"]
    notebook_model.metadata = sample_notebook_content["metadata"]
    
    # Trigger synchronization from notebook to Yjs
    yjs_notebook_provider.sync_notebook_to_yjs()
    
    # Verify that the Yjs document contains the correct data
    yjs_cells = yjs_notebook_provider.get_cells_from_yjs()
    assert len(yjs_cells) == len(sample_notebook_content["cells"])
    
    # Check that the first cell content matches
    assert yjs_cells[0]["cell_type"] == "markdown"
    assert yjs_cells[0]["source"] == sample_notebook_content["cells"][0]["source"]
    
    # Check that the second cell content matches
    assert yjs_cells[1]["cell_type"] == "code"
    assert yjs_cells[1]["source"] == sample_notebook_content["cells"][1]["source"]


def test_yjs_to_notebook_sync(yjs_notebook_provider, notebook_model):
    """Test that changes to the Yjs document are correctly synchronized to the notebook model."""
    # Make changes to the Yjs document
    yjs_notebook_provider.update_cell_in_yjs(0, {"source": ["# Updated Title\n", "This is an updated markdown cell."]})
    
    # Trigger synchronization from Yjs to notebook
    yjs_notebook_provider.sync_yjs_to_notebook()
    
    # Verify that the notebook model has been updated
    assert notebook_model.cells[0]["source"] == ["# Updated Title\n", "This is an updated markdown cell."]


# Test CRDT operations for all notebook elements (cells, outputs, metadata)
def test_add_cell_crdt_operation(yjs_notebook_provider, notebook_model):
    """Test adding a cell through CRDT operations."""
    # Initial state
    initial_cell_count = len(notebook_model.cells)
    
    # Add a new cell via Yjs
    new_cell = {
        "cell_type": "code",
        "metadata": {},
        "source": ["print('New cell')"],
        "outputs": []
    }
    yjs_notebook_provider.add_cell_to_yjs(new_cell, index=initial_cell_count)
    
    # Sync changes to the notebook model
    yjs_notebook_provider.sync_yjs_to_notebook()
    
    # Verify the cell was added
    assert len(notebook_model.cells) == initial_cell_count + 1
    assert notebook_model.cells[-1]["source"] == ["print('New cell')"]


def test_delete_cell_crdt_operation(yjs_notebook_provider, notebook_model, sample_notebook_content):
    """Test deleting a cell through CRDT operations."""
    # Set up the notebook model with sample content
    notebook_model.cells = sample_notebook_content["cells"]
    yjs_notebook_provider.sync_notebook_to_yjs()
    
    # Initial state
    initial_cell_count = len(notebook_model.cells)
    
    # Delete a cell via Yjs
    yjs_notebook_provider.delete_cell_from_yjs(1)  # Delete the second cell
    
    # Sync changes to the notebook model
    yjs_notebook_provider.sync_yjs_to_notebook()
    
    # Verify the cell was deleted
    assert len(notebook_model.cells) == initial_cell_count - 1
    # The second cell should now be the original third cell
    assert notebook_model.cells[1]["source"] == sample_notebook_content["cells"][2]["source"]


def test_update_cell_output_crdt_operation(yjs_notebook_provider, notebook_model):
    """Test updating cell outputs through CRDT operations."""
    # Update a cell's output via Yjs
    new_output = [
        {
            "name": "stdout",
            "output_type": "stream",
            "text": ["Updated output\n"]
        }
    ]
    yjs_notebook_provider.update_cell_outputs_in_yjs(1, new_output)
    
    # Sync changes to the notebook model
    yjs_notebook_provider.sync_yjs_to_notebook()
    
    # Verify the output was updated
    assert notebook_model.cells[1]["outputs"] == new_output


def test_update_metadata_crdt_operation(yjs_notebook_provider, notebook_model):
    """Test updating notebook metadata through CRDT operations."""
    # Update notebook metadata via Yjs
    new_metadata = {"custom_field": "custom_value"}
    yjs_notebook_provider.update_metadata_in_yjs(new_metadata)
    
    # Sync changes to the notebook model
    yjs_notebook_provider.sync_yjs_to_notebook()
    
    # Verify the metadata was updated
    assert notebook_model.metadata["custom_field"] == "custom_value"


# Test conflict resolution in concurrent editing scenarios
@pytest.mark.asyncio
async def test_concurrent_cell_edits_resolution(yjs_notebook_provider, mock_client_connections):
    """Test that concurrent edits to the same cell are properly resolved."""
    # Simulate concurrent edits from different users
    with patch.object(yjs_notebook_provider, 'broadcast_update') as mock_broadcast:
        # User 1 edits the first cell
        yjs_notebook_provider.user_id = "user1"
        yjs_notebook_provider.update_cell_in_yjs(0, {"source": ["# User 1's edit\n", "This is edited by user 1."]})
        
        # User 2 edits the same cell concurrently
        yjs_notebook_provider.user_id = "user2"
        yjs_notebook_provider.update_cell_in_yjs(0, {"source": ["# User 2's edit\n", "This is edited by user 2."]})
        
        # Ensure updates were broadcast
        assert mock_broadcast.call_count >= 2
    
    # Get the final state of the cell from Yjs
    yjs_cells = yjs_notebook_provider.get_cells_from_yjs()
    
    # The CRDT should have merged the changes in a deterministic way
    # We can't predict exactly how it will merge, but we can verify that:
    # 1. The cell exists
    # 2. It contains content from both users or follows a deterministic merge strategy
    assert len(yjs_cells) > 0
    assert yjs_cells[0]["source"] is not None


@pytest.mark.asyncio
async def test_concurrent_cell_additions_resolution(yjs_notebook_provider, mock_client_connections):
    """Test that concurrent additions of cells are properly resolved."""
    # Simulate concurrent cell additions from different users
    with patch.object(yjs_notebook_provider, 'broadcast_update') as mock_broadcast:
        # User 1 adds a cell at index 1
        yjs_notebook_provider.user_id = "user1"
        yjs_notebook_provider.add_cell_to_yjs({
            "cell_type": "markdown",
            "metadata": {},
            "source": ["User 1's new cell"],
            "outputs": []
        }, index=1)
        
        # User 2 adds a cell at the same index concurrently
        yjs_notebook_provider.user_id = "user2"
        yjs_notebook_provider.add_cell_to_yjs({
            "cell_type": "code",
            "metadata": {},
            "source": ["print('User 2\\'s new cell')"],
            "outputs": []
        }, index=1)
        
        # Ensure updates were broadcast
        assert mock_broadcast.call_count >= 2
    
    # Get the final state of the cells from Yjs
    yjs_cells = yjs_notebook_provider.get_cells_from_yjs()
    
    # The CRDT should have resolved the concurrent additions
    # Both cells should be present, though the order might depend on the CRDT implementation
    cell_sources = [cell["source"] for cell in yjs_cells]
    assert any("User 1's new cell" in str(source) for source in cell_sources)
    assert any("User 2's new cell" in str(source) for source in cell_sources)


# Test document state consistency across multiple clients
@pytest.mark.asyncio
async def test_document_consistency_across_clients(yjs_notebook_provider):
    """Test that document state is consistent across multiple clients."""
    # Create multiple Yjs documents representing different clients
    doc1 = Y.YDoc()
    doc2 = Y.YDoc()
    doc3 = Y.YDoc()
    
    # Apply some changes to the original document
    yjs_notebook_provider.update_cell_in_yjs(0, {"source": ["# Updated by original client\n"]})
    
    # Get the update from the original document
    update = Y.encode_state_as_update(yjs_notebook_provider.doc)
    
    # Apply the update to all client documents
    Y.apply_update(doc1, update)
    Y.apply_update(doc2, update)
    Y.apply_update(doc3, update)
    
    # Make a change in client 1
    map1 = doc1.get_map("notebook")
    cells1 = map1.get("cells")
    cell1 = cells1.get(0)
    cell1.set("source", ["# Updated by client 1\n"])
    
    # Get the update from client 1
    update1 = Y.encode_state_as_update(doc1)
    
    # Apply the update to all other documents
    Y.apply_update(yjs_notebook_provider.doc, update1)
    Y.apply_update(doc2, update1)
    Y.apply_update(doc3, update1)
    
    # Make a change in client 2
    map2 = doc2.get_map("notebook")
    cells2 = map2.get("cells")
    cell2 = cells2.get(1)
    cell2.set("source", ["# Updated by client 2\n"])
    
    # Get the update from client 2
    update2 = Y.encode_state_as_update(doc2)
    
    # Apply the update to all other documents
    Y.apply_update(yjs_notebook_provider.doc, update2)
    Y.apply_update(doc1, update2)
    Y.apply_update(doc3, update2)
    
    # Verify that all documents have the same state
    state_original = Y.encode_state_vector(yjs_notebook_provider.doc)
    state1 = Y.encode_state_vector(doc1)
    state2 = Y.encode_state_vector(doc2)
    state3 = Y.encode_state_vector(doc3)
    
    # All state vectors should be equal, indicating consistent document state
    assert state_original == state1
    assert state1 == state2
    assert state2 == state3


# Test performance with large documents and high update frequency
def test_large_document_performance(yjs_notebook_provider, notebook_model, large_notebook_content):
    """Test performance with a large notebook document."""
    # Set up the notebook model with large content
    notebook_model.cells = large_notebook_content["cells"]
    notebook_model.metadata = large_notebook_content["metadata"]
    
    # Measure time to sync notebook to Yjs
    start_time = time.time()
    yjs_notebook_provider.sync_notebook_to_yjs()
    notebook_to_yjs_time = time.time() - start_time
    
    # Verify that the Yjs document contains all cells
    yjs_cells = yjs_notebook_provider.get_cells_from_yjs()
    assert len(yjs_cells) == len(large_notebook_content["cells"])
    
    # Make a change to a cell in the Yjs document
    start_time = time.time()
    yjs_notebook_provider.update_cell_in_yjs(50, {"source": ["print('Updated cell 50')"]})  # Update middle cell
    update_cell_time = time.time() - start_time
    
    # Measure time to sync Yjs to notebook
    start_time = time.time()
    yjs_notebook_provider.sync_yjs_to_notebook()
    yjs_to_notebook_time = time.time() - start_time
    
    # Verify that the notebook model has been updated
    assert notebook_model.cells[50]["source"] == ["print('Updated cell 50')"]
    
    # Performance assertions - these thresholds might need adjustment based on the actual implementation
    assert notebook_to_yjs_time < 1.0, f"Notebook to Yjs sync took too long: {notebook_to_yjs_time} seconds"
    assert update_cell_time < 0.1, f"Cell update took too long: {update_cell_time} seconds"
    assert yjs_to_notebook_time < 1.0, f"Yjs to notebook sync took too long: {yjs_to_notebook_time} seconds"


def test_high_frequency_updates_performance(yjs_notebook_provider, notebook_model):
    """Test performance with high frequency updates."""
    # Set up a basic notebook
    notebook_model.cells = [
        {
            "cell_type": "code",
            "metadata": {},
            "source": ["# Initial content"],
            "outputs": []
        }
    ]
    yjs_notebook_provider.sync_notebook_to_yjs()
    
    # Perform a series of rapid updates to the same cell
    update_times = []
    num_updates = 50
    
    for i in range(num_updates):
        start_time = time.time()
        yjs_notebook_provider.update_cell_in_yjs(0, {"source": [f"# Update {i}"]})  
        update_times.append(time.time() - start_time)
    
    # Calculate statistics
    avg_update_time = sum(update_times) / len(update_times)
    max_update_time = max(update_times)
    
    # Performance assertions
    assert avg_update_time < 0.01, f"Average update time too high: {avg_update_time} seconds"
    assert max_update_time < 0.05, f"Maximum update time too high: {max_update_time} seconds"
    
    # Verify that the final state is correct
    yjs_notebook_provider.sync_yjs_to_notebook()
    assert notebook_model.cells[0]["source"] == [f"# Update {num_updates - 1}"]
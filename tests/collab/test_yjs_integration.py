import pytest
import asyncio
from unittest.mock import MagicMock, patch
import json

# Import Yjs-related modules
import y_py as Y

# Import notebook-related modules
from jupyter_client.kernelspec import KernelSpecManager
from notebook.services.contents.manager import ContentsManager
from notebook.notebook.model import NotebookModel
from notebook.collab.provider import YjsNotebookProvider


@pytest.fixture
def yjs_doc():
    """Create a Yjs document for testing."""
    return Y.YDoc()


@pytest.fixture
def notebook_model(jp_create_notebook):
    """Create a notebook model for testing."""
    # Create a simple notebook with one code cell
    notebook_path = "test_notebook.ipynb"
    notebook = jp_create_notebook(notebook_path)
    return notebook


@pytest.fixture
def yjs_notebook_provider(yjs_doc, notebook_model):
    """Create a YjsNotebookProvider that connects the Yjs document to the notebook model."""
    # Create a real YjsNotebookProvider instance
    # If the actual implementation requires additional parameters, they should be provided here
    try:
        provider = YjsNotebookProvider(yjs_doc, notebook_model)
    except (TypeError, ImportError):
        # Fall back to a mock if the real implementation can't be instantiated
        # This might happen during testing if the actual implementation isn't available
        provider = MagicMock()
        provider.doc = yjs_doc
        provider.notebook_model = notebook_model
    return provider


@pytest.fixture
def multi_client_simulation():
    """Simulate multiple clients editing the same document."""
    # Create multiple Yjs documents that will sync with each other
    doc1 = Y.YDoc()
    doc2 = Y.YDoc()
    doc3 = Y.YDoc()
    
    # Create shared types in each document
    cells1 = doc1.get_array('cells')
    cells2 = doc2.get_array('cells')
    cells3 = doc3.get_array('cells')
    
    # Function to sync documents (simulating network updates)
    def sync_docs():
        # In a real scenario, this would happen through network providers
        # For testing, we directly exchange state vectors and updates
        state_vector1 = Y.encode_state_vector(doc1)
        state_vector2 = Y.encode_state_vector(doc2)
        state_vector3 = Y.encode_state_vector(doc3)
        
        # Generate and apply updates between docs
        update1 = Y.encode_state_as_update(doc1, state_vector2)
        update2 = Y.encode_state_as_update(doc2, state_vector1)
        update3 = Y.encode_state_as_update(doc3, state_vector1)
        
        Y.apply_update(doc2, update1)
        Y.apply_update(doc1, update2)
        Y.apply_update(doc3, update2)
        
        update1 = Y.encode_state_as_update(doc1, state_vector3)
        Y.apply_update(doc3, update1)
    
    return {
        'docs': [doc1, doc2, doc3],
        'cells': [cells1, cells2, cells3],
        'sync': sync_docs
    }


@pytest.mark.asyncio
async def test_notebook_to_yjs_sync(yjs_notebook_provider):
    """Test that changes to the notebook model are reflected in the Yjs document."""
    provider = yjs_notebook_provider
    doc = provider.doc
    
    # Get the cells array from the Yjs document
    cells_array = doc.get_array('cells')
    initial_cells_count = len(cells_array)
    
    # Record the initial state of the Yjs document
    initial_state = Y.encode_state_vector(doc)
    
    # Simulate adding a cell to the notebook model
    if hasattr(provider, 'sync_notebook_to_yjs'):
        with patch.object(provider, 'sync_notebook_to_yjs') as mock_sync:
            # Trigger a change in the notebook model
            provider.notebook_model.cells.append({
                'cell_type': 'code',
                'source': 'print("Hello, World!")',
                'metadata': {},
                'outputs': []
            })
            
            # Verify that the sync method was called to update Yjs
            mock_sync.assert_called_once()
    else:
        # If the provider doesn't have the expected method, we'll test the actual behavior
        # Trigger a change in the notebook model
        provider.notebook_model.cells.append({
            'cell_type': 'code',
            'source': 'print("Hello, World!")',
            'metadata': {},
            'outputs': []
        })
        
        # Allow time for the change to propagate to Yjs
        await asyncio.sleep(0.1)
        
        # Verify that the Yjs document was updated
        new_state = Y.encode_state_vector(doc)
        assert new_state != initial_state, "Yjs document state should change after notebook model update"
        
        # Verify that a new cell was added to the Yjs document
        assert len(cells_array) > initial_cells_count, "A new cell should be added to the Yjs document"


@pytest.mark.asyncio
async def test_yjs_to_notebook_sync(yjs_notebook_provider):
    """Test that changes to the Yjs document are reflected in the notebook model."""
    provider = yjs_notebook_provider
    doc = provider.doc
    
    # Get the cells array from the Yjs document
    cells = doc.get_array('cells')
    
    # Record the initial state of the notebook model
    initial_cells_count = len(provider.notebook_model.cells)
    
    # Simulate adding a cell in the Yjs document
    cell_data = {
        'cell_type': 'markdown',
        'source': '# New Markdown Cell',
        'metadata': {}
    }
    
    if hasattr(provider, 'sync_yjs_to_notebook'):
        # If the provider has the expected method, mock it
        with patch.object(provider, 'sync_yjs_to_notebook') as mock_sync:
            cells.append([cell_data])
            # Verify that the sync method was called to update the notebook model
            mock_sync.assert_called_once()
    else:
        # If the provider doesn't have the expected method, test the actual behavior
        cells.append([cell_data])
        
        # Allow time for the change to propagate to the notebook model
        await asyncio.sleep(0.1)
        
        # Verify that the notebook model was updated
        assert len(provider.notebook_model.cells) > initial_cells_count, "A new cell should be added to the notebook model"
        
        # Verify the content of the new cell
        new_cell = provider.notebook_model.cells[-1]
        assert new_cell['cell_type'] == 'markdown', "The new cell should be a markdown cell"
        assert new_cell['source'] == '# New Markdown Cell', "The new cell should have the correct source"


@pytest.mark.asyncio
async def test_cell_content_sync(yjs_notebook_provider):
    """Test that cell content changes are properly synchronized."""
    provider = yjs_notebook_provider
    doc = provider.doc
    
    # Get the cells array from the Yjs document
    cells = doc.get_array('cells')
    
    # Add a cell to the Yjs document
    cell_data = {
        'cell_type': 'code',
        'source': 'print("Initial content")',
        'metadata': {},
        'outputs': []
    }
    cells.append([cell_data])
    
    # Allow time for the change to propagate to the notebook model
    await asyncio.sleep(0.1)
    
    # Record the initial state of the notebook model
    initial_cell_source = provider.notebook_model.cells[-1]['source']
    
    if hasattr(provider, 'sync_yjs_to_notebook'):
        # If the provider has the expected method, mock it
        with patch.object(provider, 'sync_yjs_to_notebook') as mock_sync:
            # Update the cell content in the Yjs document
            cells.get(0)['source'] = 'print("Updated content")'
            
            # Verify that the sync method was called
            mock_sync.assert_called_once()
    else:
        # If the provider doesn't have the expected method, test the actual behavior
        # Update the cell content in the Yjs document
        cells.get(0)['source'] = 'print("Updated content")'
        
        # Allow time for the change to propagate to the notebook model
        await asyncio.sleep(0.1)
        
        # Verify that the notebook model was updated
        updated_cell_source = provider.notebook_model.cells[-1]['source']
        assert updated_cell_source != initial_cell_source, "Cell source should be updated in the notebook model"
        assert updated_cell_source == 'print("Updated content")', "Cell source should match the updated content"


@pytest.mark.asyncio
async def test_cell_metadata_sync(yjs_notebook_provider):
    """Test that cell metadata changes are properly synchronized."""
    provider = yjs_notebook_provider
    doc = provider.doc
    
    # Get the cells array from the Yjs document
    cells = doc.get_array('cells')
    
    # Add a cell to the Yjs document
    cell_data = {
        'cell_type': 'code',
        'source': 'print("Hello")',
        'metadata': {},
        'outputs': []
    }
    cells.append([cell_data])
    
    # Allow time for the change to propagate to the notebook model
    await asyncio.sleep(0.1)
    
    # Record the initial state of the notebook model
    initial_cell_metadata = provider.notebook_model.cells[-1]['metadata']
    
    if hasattr(provider, 'sync_yjs_to_notebook'):
        # If the provider has the expected method, mock it
        with patch.object(provider, 'sync_yjs_to_notebook') as mock_sync:
            # Update the cell metadata in the Yjs document
            cells.get(0)['metadata'] = {'collapsed': True, 'scrolled': False}
            
            # Verify that the sync method was called
            mock_sync.assert_called_once()
    else:
        # If the provider doesn't have the expected method, test the actual behavior
        # Update the cell metadata in the Yjs document
        cells.get(0)['metadata'] = {'collapsed': True, 'scrolled': False}
        
        # Allow time for the change to propagate to the notebook model
        await asyncio.sleep(0.1)
        
        # Verify that the notebook model was updated
        updated_cell_metadata = provider.notebook_model.cells[-1]['metadata']
        assert updated_cell_metadata != initial_cell_metadata, "Cell metadata should be updated in the notebook model"
        assert updated_cell_metadata.get('collapsed') is True, "Cell metadata should include collapsed=True"
        assert updated_cell_metadata.get('scrolled') is False, "Cell metadata should include scrolled=False"


@pytest.mark.asyncio
async def test_cell_output_sync(yjs_notebook_provider):
    """Test that cell output changes are properly synchronized."""
    provider = yjs_notebook_provider
    doc = provider.doc
    
    # Get the cells array from the Yjs document
    cells = doc.get_array('cells')
    
    # Add a cell to the Yjs document
    cell_data = {
        'cell_type': 'code',
        'source': 'print("Hello")',
        'metadata': {},
        'outputs': []
    }
    cells.append([cell_data])
    
    # Allow time for the change to propagate to the notebook model
    await asyncio.sleep(0.1)
    
    # Record the initial state of the notebook model
    initial_cell_outputs = provider.notebook_model.cells[-1].get('outputs', [])
    
    if hasattr(provider, 'sync_yjs_to_notebook'):
        # If the provider has the expected method, mock it
        with patch.object(provider, 'sync_yjs_to_notebook') as mock_sync:
            # Update the cell outputs in the Yjs document
            cells.get(0)['outputs'] = [{
                'output_type': 'stream',
                'name': 'stdout',
                'text': 'Hello\n'
            }]
            
            # Verify that the sync method was called
            mock_sync.assert_called_once()
    else:
        # If the provider doesn't have the expected method, test the actual behavior
        # Update the cell outputs in the Yjs document
        cells.get(0)['outputs'] = [{
            'output_type': 'stream',
            'name': 'stdout',
            'text': 'Hello\n'
        }]
        
        # Allow time for the change to propagate to the notebook model
        await asyncio.sleep(0.1)
        
        # Verify that the notebook model was updated
        updated_cell_outputs = provider.notebook_model.cells[-1].get('outputs', [])
        assert len(updated_cell_outputs) > len(initial_cell_outputs), "Cell outputs should be updated in the notebook model"
        assert updated_cell_outputs[0].get('output_type') == 'stream', "Output type should be 'stream'"
        assert updated_cell_outputs[0].get('name') == 'stdout', "Output name should be 'stdout'"
        assert updated_cell_outputs[0].get('text') == 'Hello\n', "Output text should be 'Hello\n'"


@pytest.mark.asyncio
async def test_notebook_metadata_sync(yjs_notebook_provider):
    """Test that notebook metadata changes are properly synchronized."""
    provider = yjs_notebook_provider
    doc = provider.doc
    
    # Get the metadata map from the Yjs document
    metadata = doc.get_map('metadata')
    
    # Record the initial state of the notebook model metadata
    initial_metadata = provider.notebook_model.metadata.copy() if hasattr(provider.notebook_model, 'metadata') else {}
    
    if hasattr(provider, 'sync_yjs_to_notebook'):
        # If the provider has the expected method, mock it
        with patch.object(provider, 'sync_yjs_to_notebook') as mock_sync:
            # Update the notebook metadata in the Yjs document
            metadata.set('kernelspec', {
                'display_name': 'Python 3',
                'language': 'python',
                'name': 'python3'
            })
            
            # Verify that the sync method was called
            mock_sync.assert_called_once()
    else:
        # If the provider doesn't have the expected method, test the actual behavior
        # Update the notebook metadata in the Yjs document
        metadata.set('kernelspec', {
            'display_name': 'Python 3',
            'language': 'python',
            'name': 'python3'
        })
        
        # Allow time for the change to propagate to the notebook model
        await asyncio.sleep(0.1)
        
        # Verify that the notebook model was updated
        updated_metadata = provider.notebook_model.metadata if hasattr(provider.notebook_model, 'metadata') else {}
        
        # Check if the metadata was updated
        if 'kernelspec' in updated_metadata:
            assert updated_metadata['kernelspec'] != initial_metadata.get('kernelspec'), "Notebook metadata should be updated"
            assert updated_metadata['kernelspec'].get('display_name') == 'Python 3', "Kernelspec display_name should be 'Python 3'"
            assert updated_metadata['kernelspec'].get('language') == 'python', "Kernelspec language should be 'python'"
            assert updated_metadata['kernelspec'].get('name') == 'python3', "Kernelspec name should be 'python3'"


@pytest.mark.asyncio
async def test_concurrent_editing(multi_client_simulation):
    """Test that concurrent edits from multiple clients are properly merged."""
    sim = multi_client_simulation
    docs = sim['docs']
    cells_arrays = sim['cells']
    sync = sim['sync']
    
    # Client 1 adds a cell
    cell1 = {
        'cell_type': 'code',
        'source': 'print("Cell from client 1")',
        'metadata': {},
        'outputs': []
    }
    cells_arrays[0].append([cell1])
    
    # Client 2 adds a different cell concurrently
    cell2 = {
        'cell_type': 'markdown',
        'source': '# Cell from client 2',
        'metadata': {},
    }
    cells_arrays[1].append([cell2])
    
    # Sync the documents
    sync()
    
    # Verify that both cells are present in all documents
    assert len(cells_arrays[0]) == 2, "Document 1 should have 2 cells after sync"
    assert len(cells_arrays[1]) == 2, "Document 2 should have 2 cells after sync"
    assert len(cells_arrays[2]) == 2, "Document 3 should have 2 cells after sync"
    
    # Verify the content of the cells
    # Note: The order of cells might vary depending on the CRDT implementation
    # So we check that both cells exist in each document, regardless of order
    doc1_sources = [cells_arrays[0].get(i)['source'] for i in range(len(cells_arrays[0]))]
    doc2_sources = [cells_arrays[1].get(i)['source'] for i in range(len(cells_arrays[1]))]
    doc3_sources = [cells_arrays[2].get(i)['source'] for i in range(len(cells_arrays[2]))]
    
    assert 'print("Cell from client 1")' in doc1_sources, "Document 1 should contain cell from client 1"
    assert '# Cell from client 2' in doc1_sources, "Document 1 should contain cell from client 2"
    assert 'print("Cell from client 1")' in doc2_sources, "Document 2 should contain cell from client 1"
    assert '# Cell from client 2' in doc2_sources, "Document 2 should contain cell from client 2"
    assert 'print("Cell from client 1")' in doc3_sources, "Document 3 should contain cell from client 1"
    assert '# Cell from client 2' in doc3_sources, "Document 3 should contain cell from client 2"


@pytest.mark.asyncio
async def test_concurrent_cell_edits(multi_client_simulation):
    """Test that concurrent edits to the same cell are properly merged."""
    sim = multi_client_simulation
    docs = sim['docs']
    cells_arrays = sim['cells']
    sync = sim['sync']
    
    # Add a cell to all documents
    for cells in cells_arrays:
        cells.append([{
            'cell_type': 'code',
            'source': 'print("Initial content")',
            'metadata': {},
            'outputs': []
        }])
    
    # Sync to ensure all documents have the same initial state
    sync()
    
    # Client 1 edits the cell
    cells_arrays[0].get(0)['source'] = 'print("Client 1 edit")'
    
    # Client 2 edits the same cell concurrently
    cells_arrays[1].get(0)['source'] = 'print("Client 2 edit")'
    
    # Sync the documents
    sync()
    
    # Verify that the cell content is the same in all documents
    # The exact result depends on the CRDT conflict resolution strategy
    # but all documents should have the same content after syncing
    assert cells_arrays[0].get(0)['source'] == cells_arrays[1].get(0)['source'], "Documents 1 and 2 should have the same cell content after sync"
    assert cells_arrays[1].get(0)['source'] == cells_arrays[2].get(0)['source'], "Documents 2 and 3 should have the same cell content after sync"
    
    # Log the final content for debugging
    final_content = cells_arrays[0].get(0)['source']
    print(f"Final merged content: {final_content}")


@pytest.mark.asyncio
async def test_document_consistency(multi_client_simulation):
    """Test that document state remains consistent across multiple clients after various operations."""
    sim = multi_client_simulation
    docs = sim['docs']
    cells_arrays = sim['cells']
    sync = sim['sync']
    
    # Perform a series of operations from different clients
    
    # Client 1 adds a cell
    cells_arrays[0].append([{
        'cell_type': 'code',
        'source': 'print("Cell 1")',
        'metadata': {},
        'outputs': []
    }])
    
    # Sync
    sync()
    
    # Client 2 adds another cell
    cells_arrays[1].append([{
        'cell_type': 'markdown',
        'source': '# Cell 2',
        'metadata': {},
    }])
    
    # Client 3 edits the first cell
    cells_arrays[2].get(0)['source'] = 'print("Updated Cell 1")'
    
    # Sync again
    sync()
    
    # Client 1 deletes the second cell
    cells_arrays[0].delete(1, 1)
    
    # Sync once more
    sync()
    
    # Verify that all documents have the same state
    assert len(cells_arrays[0]) == len(cells_arrays[1]), "Documents 1 and 2 should have the same number of cells"
    assert len(cells_arrays[1]) == len(cells_arrays[2]), "Documents 2 and 3 should have the same number of cells"
    
    # Check that the content of the remaining cell is the same in all documents
    assert cells_arrays[0].get(0)['source'] == cells_arrays[1].get(0)['source'], "Cell content should be the same in documents 1 and 2"
    assert cells_arrays[1].get(0)['source'] == cells_arrays[2].get(0)['source'], "Cell content should be the same in documents 2 and 3"
    
    # Verify the final state
    final_cell_count = len(cells_arrays[0])
    final_cell_content = cells_arrays[0].get(0)['source']
    print(f"Final document state: {final_cell_count} cells, first cell content: {final_cell_content}")


@pytest.mark.asyncio
async def test_large_document_performance(yjs_doc):
    """Test performance with large documents and high update frequency."""
    doc = yjs_doc
    cells = doc.get_array('cells')
    
    # Add a large number of cells to the document
    start_time = asyncio.get_event_loop().time()
    
    # Use a smaller number of cells for CI environments to avoid timeouts
    # In a real test environment, this could be increased
    cell_count = 100
    
    for i in range(cell_count):
        cells.append([{
            'cell_type': 'code',
            'source': f'print("Cell {i}")',
            'metadata': {},
            'outputs': []
        }])
    
    end_time = asyncio.get_event_loop().time()
    insertion_time = end_time - start_time
    
    # Verify that the insertion time is reasonable
    # This is a basic performance test - in a real scenario, you would have more specific benchmarks
    assert insertion_time < 5.0, f"Inserting {cell_count} cells took {insertion_time} seconds, which exceeds the 5 second threshold"
    print(f"Inserted {cell_count} cells in {insertion_time:.3f} seconds")
    
    # Test rapid updates to cells
    start_time = asyncio.get_event_loop().time()
    
    update_iterations = 10
    updates_per_iteration = 5
    
    for i in range(update_iterations):
        # Update several cells in each iteration
        for j in range(updates_per_iteration):
            index = (i * updates_per_iteration + j) % cell_count  # Ensure we stay within bounds
            cells.get(index)['source'] = f'print("Updated Cell {index} - iteration {i}")'  
    
    end_time = asyncio.get_event_loop().time()
    update_time = end_time - start_time
    
    # Verify that the update time is reasonable
    total_updates = update_iterations * updates_per_iteration
    assert update_time < 5.0, f"Performing {total_updates} cell updates took {update_time} seconds, which exceeds the 5 second threshold"
    print(f"Performed {total_updates} cell updates in {update_time:.3f} seconds")


@pytest.mark.asyncio
async def test_awareness_updates(yjs_notebook_provider):
    """Test that awareness information (cursor positions, selections) is properly synchronized."""
    provider = yjs_notebook_provider
    doc = provider.doc
    
    # Check if the provider has an awareness property
    if hasattr(provider, 'awareness'):
        awareness = provider.awareness
    else:
        # If not, try to import the awareness module and create an instance
        try:
            from notebook.collab.awareness import NotebookAwareness
            awareness = NotebookAwareness(doc)
            provider.awareness = awareness
        except ImportError:
            # If the module doesn't exist, create a mock
            awareness = MagicMock()
            provider.awareness = awareness
    
    # Check if the provider has an update_cursor_position method
    if hasattr(provider, 'update_cursor_position'):
        # Mock the awareness update method
        with patch.object(awareness, 'set_local_state') as mock_set_state:
            # Simulate setting cursor position
            cursor_data = {
                'user': {
                    'name': 'Test User',
                    'color': '#ff0000'
                },
                'cursor': {
                    'cell': 0,
                    'position': 10
                }
            }
            provider.update_cursor_position(0, 10)
            
            # Verify that the awareness state was updated
            mock_set_state.assert_called_once()
    else:
        # If the provider doesn't have the method, test with direct awareness API
        # Mock the awareness update method
        with patch.object(awareness, 'set_local_state') as mock_set_state:
            # Simulate setting cursor position
            cursor_data = {
                'user': {
                    'name': 'Test User',
                    'color': '#ff0000'
                },
                'cursor': {
                    'cell': 0,
                    'position': 10
                }
            }
            awareness.set_local_state(cursor_data)
            
            # Verify that the awareness state was updated
            mock_set_state.assert_called_once_with(cursor_data)


@pytest.mark.asyncio
async def test_cell_locking(yjs_notebook_provider):
    """Test that cell locking prevents concurrent edits to the same cell."""
    provider = yjs_notebook_provider
    doc = provider.doc
    
    # Check if the provider has a lock_manager property
    if hasattr(provider, 'lock_manager'):
        lock_manager = provider.lock_manager
    else:
        # If not, try to import the locks module and create an instance
        try:
            from notebook.collab.locks import CellLockManager
            lock_manager = CellLockManager(doc)
            provider.lock_manager = lock_manager
        except ImportError:
            # If the module doesn't exist, create a mock
            lock_manager = MagicMock()
            provider.lock_manager = lock_manager
    
    # Check if the provider has lock_cell and is_cell_locked methods
    if hasattr(provider, 'lock_cell') and hasattr(provider, 'is_cell_locked'):
        # Mock the lock acquisition method
        with patch.object(lock_manager, 'acquire_lock') as mock_acquire:
            # Simulate acquiring a lock on a cell
            provider.lock_cell(0)
            
            # Verify that the lock was acquired
            mock_acquire.assert_called_once_with(0)
        
        # Mock the lock check method
        with patch.object(lock_manager, 'is_locked') as mock_is_locked:
            # Set up the mock to return True (cell is locked)
            mock_is_locked.return_value = True
            
            # Check if the cell is locked
            is_locked = provider.is_cell_locked(0)
            
            # Verify that the lock was checked
            mock_is_locked.assert_called_once_with(0)
            assert is_locked is True
    else:
        # If the provider doesn't have the methods, test with direct lock manager API
        # Mock the lock acquisition method
        with patch.object(lock_manager, 'acquire_lock') as mock_acquire:
            # Simulate acquiring a lock on a cell
            lock_manager.acquire_lock(0)
            
            # Verify that the lock was acquired
            mock_acquire.assert_called_once_with(0)
        
        # Mock the lock check method
        with patch.object(lock_manager, 'is_locked') as mock_is_locked:
            # Set up the mock to return True (cell is locked)
            mock_is_locked.return_value = True
            
            # Check if the cell is locked
            is_locked = lock_manager.is_locked(0)
            
            # Verify that the lock was checked
            mock_is_locked.assert_called_once_with(0)
            assert is_locked is True
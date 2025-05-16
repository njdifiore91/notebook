import asyncio
import pytest
import json
import time
from typing import List, Dict, Any, Callable, Awaitable

# Assuming these fixtures are defined in conftest.py
pytest.importorskip("y_py")


@pytest.mark.asyncio
async def test_basic_synchronization(jp_serverapp, jp_ws_client):
    """
    Test basic document synchronization between two clients.
    
    Verifies that changes made by one client are properly propagated to another client.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1")
    client2 = await jp_ws_client(user_id="user2")
    
    # Both clients subscribe to the same document
    doc_id = "test-sync-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a new cell
    cell_id = "cell1"
    cell_content = "print('Hello from client 1')"
    await client1.add_cell(doc_id, cell_id, cell_content, "code")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 2 received the update
    doc_state = await client2.get_document_state(doc_id)
    assert cell_id in doc_state["cells"], "Cell not synchronized to client 2"
    assert doc_state["cells"][cell_id]["source"] == cell_content, "Cell content not synchronized correctly"


@pytest.mark.asyncio
async def test_bidirectional_synchronization(jp_serverapp, jp_ws_client):
    """
    Test bidirectional synchronization between multiple clients.
    
    Verifies that changes can flow in both directions between clients.
    """
    # Create three clients connected to the same document
    client1 = await jp_ws_client(user_id="user1")
    client2 = await jp_ws_client(user_id="user2")
    client3 = await jp_ws_client(user_id="user3")
    
    # All clients subscribe to the same document
    doc_id = "test-bidirectional-sync-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    await client3.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a cell
    cell1_id = "cell1"
    cell1_content = "print('Hello from client 1')"
    await client1.add_cell(doc_id, cell1_id, cell1_content, "code")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 2 adds another cell
    cell2_id = "cell2"
    cell2_content = "print('Hello from client 2')"
    await client2.add_cell(doc_id, cell2_id, cell2_content, "code")
    
    # Client 3 modifies the first cell
    cell1_updated_content = "print('Updated by client 3')"
    await client3.update_cell_content(doc_id, cell1_id, cell1_updated_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify all clients have the same document state
    doc_state1 = await client1.get_document_state(doc_id)
    doc_state2 = await client2.get_document_state(doc_id)
    doc_state3 = await client3.get_document_state(doc_id)
    
    # Check that all clients have both cells
    for doc_state in [doc_state1, doc_state2, doc_state3]:
        assert cell1_id in doc_state["cells"], "Cell 1 missing from document state"
        assert cell2_id in doc_state["cells"], "Cell 2 missing from document state"
        
        # Check that cell 1 has the updated content from client 3
        assert doc_state["cells"][cell1_id]["source"] == cell1_updated_content, "Cell 1 content not updated correctly"
        
        # Check that cell 2 has the content from client 2
        assert doc_state["cells"][cell2_id]["source"] == cell2_content, "Cell 2 content not synchronized correctly"


@pytest.mark.asyncio
async def test_concurrent_cell_editing(jp_serverapp, jp_ws_client):
    """
    Test concurrent editing of different cells.
    
    Verifies that multiple clients can simultaneously edit different cells without conflicts.
    """
    # Create three clients connected to the same document
    client1 = await jp_ws_client(user_id="user1")
    client2 = await jp_ws_client(user_id="user2")
    client3 = await jp_ws_client(user_id="user3")
    
    # All clients subscribe to the same document
    doc_id = "test-concurrent-cell-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    await client3.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Create three cells
    cells = [
        {"id": "cell1", "content": "# Cell 1 initial content", "cell_type": "markdown"},
        {"id": "cell2", "content": "# Cell 2 initial content", "cell_type": "markdown"},
        {"id": "cell3", "content": "# Cell 3 initial content", "cell_type": "markdown"}
    ]
    
    # Client 1 adds all three cells
    for cell in cells:
        await client1.add_cell(doc_id, cell["id"], cell["content"], cell["cell_type"])
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Concurrently edit different cells from different clients
    edit_tasks = [
        client1.update_cell_content(doc_id, "cell1", "# Cell 1 edited by client 1"),
        client2.update_cell_content(doc_id, "cell2", "# Cell 2 edited by client 2"),
        client3.update_cell_content(doc_id, "cell3", "# Cell 3 edited by client 3")
    ]
    
    # Run edits concurrently
    await asyncio.gather(*edit_tasks)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify all clients have the same document state with all edits
    doc_state1 = await client1.get_document_state(doc_id)
    doc_state2 = await client2.get_document_state(doc_id)
    doc_state3 = await client3.get_document_state(doc_id)
    
    expected_contents = {
        "cell1": "# Cell 1 edited by client 1",
        "cell2": "# Cell 2 edited by client 2",
        "cell3": "# Cell 3 edited by client 3"
    }
    
    # Check that all clients have the correct content for all cells
    for doc_state in [doc_state1, doc_state2, doc_state3]:
        for cell_id, expected_content in expected_contents.items():
            assert cell_id in doc_state["cells"], f"{cell_id} missing from document state"
            assert doc_state["cells"][cell_id]["source"] == expected_content, f"{cell_id} content not updated correctly"


@pytest.mark.asyncio
async def test_conflict_resolution(jp_serverapp, jp_ws_client):
    """
    Test conflict resolution during simultaneous editing of the same cell.
    
    Verifies that the CRDT algorithm correctly resolves conflicts when multiple clients
    edit the same cell simultaneously.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1")
    client2 = await jp_ws_client(user_id="user2")
    
    # Both clients subscribe to the same document
    doc_id = "test-conflict-resolution-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a cell
    cell_id = "conflict_cell"
    initial_content = "# Initial content"
    await client1.add_cell(doc_id, cell_id, initial_content, "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Both clients edit the same cell simultaneously at different positions
    # Client 1 adds text at the beginning
    # Client 2 adds text at the end
    edit_tasks = [
        client1.update_cell_content_at_position(doc_id, cell_id, "PREPEND: ", 0),
        client2.update_cell_content_at_position(doc_id, cell_id, " :APPEND", len(initial_content))
    ]
    
    # Run edits concurrently
    await asyncio.gather(*edit_tasks)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify both clients have the same merged content
    doc_state1 = await client1.get_document_state(doc_id)
    doc_state2 = await client2.get_document_state(doc_id)
    
    # The expected result should contain both edits
    expected_content = "PREPEND: # Initial content :APPEND"
    
    assert doc_state1["cells"][cell_id]["source"] == expected_content, "Conflict resolution failed on client 1"
    assert doc_state2["cells"][cell_id]["source"] == expected_content, "Conflict resolution failed on client 2"
    assert doc_state1["cells"][cell_id]["source"] == doc_state2["cells"][cell_id]["source"], "Document states diverged"


@pytest.mark.asyncio
async def test_document_state_consistency(jp_serverapp, jp_ws_client):
    """
    Test document state consistency across multiple clients after a series of edits.
    
    Verifies that all clients converge to the same document state after multiple
    rounds of edits from different clients.
    """
    # Create three clients connected to the same document
    clients = []
    for i in range(3):
        client = await jp_ws_client(user_id=f"user{i+1}")
        clients.append(client)
    
    # All clients subscribe to the same document
    doc_id = "test-consistency-doc"
    for client in clients:
        await client.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Perform multiple rounds of edits from different clients
    for round_num in range(5):
        edit_tasks = []
        
        # Each client adds or modifies a cell
        for i, client in enumerate(clients):
            cell_id = f"cell{i+1}_round{round_num}"
            
            if round_num == 0:
                # First round: add new cells
                task = client.add_cell(doc_id, cell_id, f"Content from client {i+1}, round {round_num}", "markdown")
            else:
                # Subsequent rounds: modify existing cells from previous round
                prev_cell_id = f"cell{i+1}_round{round_num-1}"
                task = client.update_cell_content(
                    doc_id, 
                    prev_cell_id, 
                    f"Updated content from client {i+1}, round {round_num}"
                )
            
            edit_tasks.append(task)
        
        # Run edits concurrently
        await asyncio.gather(*edit_tasks)
        
        # Wait for synchronization after each round
        await asyncio.sleep(0.5)
    
    # Verify all clients have the same document state
    doc_states = []
    for client in clients:
        doc_state = await client.get_document_state(doc_id)
        doc_states.append(doc_state)
    
    # Check that all document states are identical
    for i in range(1, len(doc_states)):
        assert doc_states[0] == doc_states[i], f"Document state mismatch between client 1 and client {i+1}"
    
    # Verify the document contains all expected cells
    for round_num in range(5):
        for i in range(len(clients)):
            cell_id = f"cell{i+1}_round{round_num}"
            
            # For round 0, cells should have their original content
            # For rounds 1-4, cells from the previous round should have updated content
            if round_num == 0:
                expected_content = f"Content from client {i+1}, round {round_num}"
            else:
                expected_content = f"Updated content from client {i+1}, round {round_num}"
                
            if round_num < 4:  # Cells from rounds 0-3 should have been updated
                assert cell_id in doc_states[0]["cells"], f"Cell {cell_id} missing from document state"
                assert doc_states[0]["cells"][cell_id]["source"] == expected_content, f"Cell {cell_id} has incorrect content"


@pytest.mark.asyncio
async def test_metadata_synchronization(jp_serverapp, jp_ws_client):
    """
    Test synchronization of notebook metadata across clients.
    
    Verifies that changes to notebook metadata are properly synchronized between clients.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1")
    client2 = await jp_ws_client(user_id="user2")
    
    # Both clients subscribe to the same document
    doc_id = "test-metadata-sync-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 updates notebook metadata
    metadata = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "name": "python",
            "version": "3.8.0"
        },
        "custom": {
            "tags": ["collaborative", "test"]
        }
    }
    
    await client1.update_notebook_metadata(doc_id, metadata)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 2 received the metadata update
    doc_state = await client2.get_document_state(doc_id)
    
    assert "metadata" in doc_state, "Metadata not present in document state"
    assert doc_state["metadata"]["kernelspec"]["name"] == "python3", "Kernelspec not synchronized correctly"
    assert doc_state["metadata"]["language_info"]["version"] == "3.8.0", "Language info not synchronized correctly"
    assert "collaborative" in doc_state["metadata"]["custom"]["tags"], "Custom metadata not synchronized correctly"
    
    # Client 2 updates a portion of the metadata
    updated_metadata = {
        "custom": {
            "tags": ["collaborative", "test", "updated"],
            "last_modified": "2023-01-01"
        }
    }
    
    await client2.update_notebook_metadata(doc_id, updated_metadata)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 1 received the metadata update
    doc_state = await client1.get_document_state(doc_id)
    
    assert "updated" in doc_state["metadata"]["custom"]["tags"], "Updated tags not synchronized correctly"
    assert doc_state["metadata"]["custom"]["last_modified"] == "2023-01-01", "New metadata field not synchronized correctly"
    assert doc_state["metadata"]["kernelspec"]["name"] == "python3", "Original metadata lost after update"


@pytest.mark.asyncio
async def test_cell_output_synchronization(jp_serverapp, jp_ws_client):
    """
    Test synchronization of cell outputs across clients.
    
    Verifies that cell execution outputs are properly synchronized between clients.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1")
    client2 = await jp_ws_client(user_id="user2")
    
    # Both clients subscribe to the same document
    doc_id = "test-output-sync-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a code cell
    cell_id = "code_cell"
    cell_content = "print('Hello, world!')"
    await client1.add_cell(doc_id, cell_id, cell_content, "code")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 executes the cell and gets output
    cell_output = [
        {
            "output_type": "stream",
            "name": "stdout",
            "text": "Hello, world!\n"
        }
    ]
    
    await client1.update_cell_outputs(doc_id, cell_id, cell_output)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 2 received the output update
    doc_state = await client2.get_document_state(doc_id)
    
    assert cell_id in doc_state["cells"], "Cell not synchronized to client 2"
    assert "outputs" in doc_state["cells"][cell_id], "Cell outputs not present"
    assert len(doc_state["cells"][cell_id]["outputs"]) == 1, "Incorrect number of outputs"
    assert doc_state["cells"][cell_id]["outputs"][0]["output_type"] == "stream", "Output type not synchronized correctly"
    assert doc_state["cells"][cell_id]["outputs"][0]["text"] == "Hello, world!\n", "Output text not synchronized correctly"
    
    # Client 2 clears the output
    await client2.update_cell_outputs(doc_id, cell_id, [])
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 1 sees the cleared output
    doc_state = await client1.get_document_state(doc_id)
    
    assert cell_id in doc_state["cells"], "Cell missing after output clear"
    assert "outputs" in doc_state["cells"][cell_id], "Outputs field missing after clear"
    assert len(doc_state["cells"][cell_id]["outputs"]) == 0, "Outputs not cleared correctly"


@pytest.mark.asyncio
async def test_cell_execution_count_synchronization(jp_serverapp, jp_ws_client):
    """
    Test synchronization of cell execution counts across clients.
    
    Verifies that cell execution counts are properly synchronized between clients.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1")
    client2 = await jp_ws_client(user_id="user2")
    
    # Both clients subscribe to the same document
    doc_id = "test-execution-count-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a code cell
    cell_id = "code_cell"
    cell_content = "print('Hello, world!')"
    await client1.add_cell(doc_id, cell_id, cell_content, "code")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 updates the execution count
    await client1.update_cell_execution_count(doc_id, cell_id, 1)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 2 received the execution count update
    doc_state = await client2.get_document_state(doc_id)
    
    assert cell_id in doc_state["cells"], "Cell not synchronized to client 2"
    assert "execution_count" in doc_state["cells"][cell_id], "Execution count not present"
    assert doc_state["cells"][cell_id]["execution_count"] == 1, "Execution count not synchronized correctly"
    
    # Client 2 updates the execution count
    await client2.update_cell_execution_count(doc_id, cell_id, 2)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 1 received the execution count update
    doc_state = await client1.get_document_state(doc_id)
    
    assert doc_state["cells"][cell_id]["execution_count"] == 2, "Updated execution count not synchronized correctly"


@pytest.mark.asyncio
async def test_large_document_synchronization(jp_serverapp, jp_ws_client):
    """
    Test synchronization of large documents with many cells.
    
    Verifies that large documents with many cells can be synchronized efficiently.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1")
    client2 = await jp_ws_client(user_id="user2")
    
    # Both clients subscribe to the same document
    doc_id = "test-large-doc"
    await client1.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds many cells
    num_cells = 100
    cell_ids = []
    
    for i in range(num_cells):
        cell_id = f"cell_{i}"
        cell_ids.append(cell_id)
        
        # Alternate between code and markdown cells
        cell_type = "code" if i % 2 == 0 else "markdown"
        
        # Create larger content for some cells
        if i % 10 == 0:
            # Create a larger cell with multiple lines
            lines = [f"Line {j} of cell {i}" for j in range(20)]
            content = "\n".join(lines)
        else:
            content = f"Content of cell {i}"
        
        await client1.add_cell(doc_id, cell_id, content, cell_type)
    
    # Now client 2 subscribes to the document with all cells
    await client2.subscribe_document(doc_id)
    
    # Wait for synchronization of the large document
    # This may take longer for a large document
    await asyncio.sleep(2)
    
    # Verify client 2 received all cells
    doc_state = await client2.get_document_state(doc_id)
    
    assert len(doc_state["cells"]) == num_cells, f"Not all cells synchronized. Expected {num_cells}, got {len(doc_state['cells'])}"
    
    # Verify a sample of cells to ensure content is correct
    for i in [0, 10, 50, 99]:  # Check a few specific cells
        cell_id = f"cell_{i}"
        assert cell_id in doc_state["cells"], f"Cell {cell_id} missing from document state"
        
        if i % 10 == 0:
            # Check that large cells have the correct number of lines
            content = doc_state["cells"][cell_id]["source"]
            lines = content.split("\n")
            assert len(lines) == 20, f"Large cell {cell_id} has incorrect number of lines"
        else:
            # Check content of regular cells
            assert doc_state["cells"][cell_id]["source"] == f"Content of cell {i}", f"Cell {cell_id} has incorrect content"


@pytest.mark.asyncio
async def test_high_frequency_updates(jp_serverapp, jp_ws_client):
    """
    Test synchronization with high-frequency updates from multiple clients.
    
    Verifies that the system can handle rapid updates from multiple clients
    without losing changes or corrupting the document state.
    """
    # Create three clients connected to the same document
    client1 = await jp_ws_client(user_id="user1")
    client2 = await jp_ws_client(user_id="user2")
    client3 = await jp_ws_client(user_id="user3")
    
    # All clients subscribe to the same document
    doc_id = "test-high-frequency-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    await client3.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a cell that will be rapidly updated
    cell_id = "rapid_update_cell"
    initial_content = "Initial content"
    await client1.add_cell(doc_id, cell_id, initial_content, "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Perform rapid updates from all clients
    num_updates = 50
    update_tasks = []
    
    # Each client will append its ID to the cell content multiple times
    for i in range(num_updates):
        client_idx = i % 3 + 1  # Alternate between clients 1, 2, and 3
        client = locals()[f"client{client_idx}"]  # Get the client object
        
        # Each update appends the client ID and update number
        update = f" [Client {client_idx}, Update {i}]"
        
        # Add the update task
        task = client.append_to_cell_content(doc_id, cell_id, update)
        update_tasks.append(task)
    
    # Run all updates concurrently
    await asyncio.gather(*update_tasks)
    
    # Wait for synchronization of all updates
    # This may take longer due to the high volume of updates
    await asyncio.sleep(2)
    
    # Verify all clients have the same document state
    doc_state1 = await client1.get_document_state(doc_id)
    doc_state2 = await client2.get_document_state(doc_id)
    doc_state3 = await client3.get_document_state(doc_id)
    
    # Check that all document states are identical
    assert doc_state1["cells"][cell_id]["source"] == doc_state2["cells"][cell_id]["source"], "Document states diverged between client 1 and 2"
    assert doc_state1["cells"][cell_id]["source"] == doc_state3["cells"][cell_id]["source"], "Document states diverged between client 1 and 3"
    
    # Verify that all updates were applied
    final_content = doc_state1["cells"][cell_id]["source"]
    
    # Check that the final content contains the initial content
    assert initial_content in final_content, "Initial content missing from final state"
    
    # Check that all updates are present in the final content
    # This is a basic check - the exact order might vary due to CRDT merging
    for i in range(num_updates):
        client_idx = i % 3 + 1
        update_marker = f"Client {client_idx}, Update {i}"
        assert update_marker in final_content, f"Update '{update_marker}' missing from final content"


@pytest.mark.asyncio
async def test_cell_deletion_synchronization(jp_serverapp, jp_ws_client):
    """
    Test synchronization of cell deletions across clients.
    
    Verifies that cell deletions are properly synchronized between clients.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1")
    client2 = await jp_ws_client(user_id="user2")
    
    # Both clients subscribe to the same document
    doc_id = "test-cell-deletion-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds multiple cells
    cell_ids = ["cell1", "cell2", "cell3", "cell4", "cell5"]
    for i, cell_id in enumerate(cell_ids):
        await client1.add_cell(doc_id, cell_id, f"Content of {cell_id}", "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 2 received all cells
    doc_state = await client2.get_document_state(doc_id)
    for cell_id in cell_ids:
        assert cell_id in doc_state["cells"], f"Cell {cell_id} not synchronized to client 2"
    
    # Client 1 deletes cell3
    await client1.delete_cell(doc_id, "cell3")
    
    # Client 2 deletes cell5
    await client2.delete_cell(doc_id, "cell5")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify both clients have the same document state with cells 3 and 5 removed
    doc_state1 = await client1.get_document_state(doc_id)
    doc_state2 = await client2.get_document_state(doc_id)
    
    # Check that the deleted cells are removed from both clients
    assert "cell3" not in doc_state1["cells"], "Deleted cell3 still present in client 1"
    assert "cell5" not in doc_state1["cells"], "Deleted cell5 not removed from client 1"
    assert "cell3" not in doc_state2["cells"], "Deleted cell3 not removed from client 2"
    assert "cell5" not in doc_state2["cells"], "Deleted cell5 still present in client 2"
    
    # Check that the remaining cells are still present
    for cell_id in ["cell1", "cell2", "cell4"]:
        assert cell_id in doc_state1["cells"], f"Cell {cell_id} missing from client 1 after deletions"
        assert cell_id in doc_state2["cells"], f"Cell {cell_id} missing from client 2 after deletions"
        
    # Check that both clients have the same number of cells
    assert len(doc_state1["cells"]) == len(doc_state2["cells"]), "Document states have different cell counts"
    assert len(doc_state1["cells"]) == 3, "Incorrect number of cells after deletion"


@pytest.mark.asyncio
async def test_cell_reordering_synchronization(jp_serverapp, jp_ws_client):
    """
    Test synchronization of cell reordering across clients.
    
    Verifies that changes to cell order are properly synchronized between clients.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1")
    client2 = await jp_ws_client(user_id="user2")
    
    # Both clients subscribe to the same document
    doc_id = "test-cell-reordering-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds multiple cells
    cell_ids = ["cell1", "cell2", "cell3", "cell4", "cell5"]
    for i, cell_id in enumerate(cell_ids):
        await client1.add_cell(doc_id, cell_id, f"Content of {cell_id}", "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 reorders the cells
    new_order = ["cell3", "cell1", "cell5", "cell2", "cell4"]
    await client1.reorder_cells(doc_id, new_order)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 2 received the reordering
    doc_state = await client2.get_document_state(doc_id)
    
    # Check that the cell order matches the new order
    assert list(doc_state["cells"].keys()) == new_order, "Cell order not synchronized correctly"
    
    # Client 2 reorders the cells again
    newer_order = ["cell5", "cell4", "cell3", "cell2", "cell1"]
    await client2.reorder_cells(doc_id, newer_order)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 1 received the reordering
    doc_state = await client1.get_document_state(doc_id)
    
    # Check that the cell order matches the newer order
    assert list(doc_state["cells"].keys()) == newer_order, "Second cell reordering not synchronized correctly"
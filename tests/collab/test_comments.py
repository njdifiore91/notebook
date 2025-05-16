import pytest
import json
import uuid
import asyncio
from unittest.mock import MagicMock, patch

# Skip tests if collaboration dependencies are not installed
pytestmark = pytest.mark.skipif(
    not pytest.importorskip("y_py", reason="Collaboration dependencies not installed"),
    reason="Collaboration dependencies not installed"
)


@pytest.fixture
def mock_comment_manager():
    """Fixture for mocking the comment manager component."""
    manager = MagicMock()
    manager.create_thread.side_effect = lambda doc_id, cell_id, content, user_id: {
        "id": str(uuid.uuid4()),
        "cell_id": cell_id,
        "status": "open",
        "created_at": "2023-01-01T00:00:00Z",
        "comments": [
            {
                "id": str(uuid.uuid4()),
                "content": content,
                "user_id": user_id,
                "created_at": "2023-01-01T00:00:00Z"
            }
        ]
    }
    manager.add_comment.side_effect = lambda doc_id, thread_id, content, user_id: {
        "id": str(uuid.uuid4()),
        "thread_id": thread_id,
        "content": content,
        "user_id": user_id,
        "created_at": "2023-01-01T00:00:00Z"
    }
    manager.get_threads.return_value = []
    manager.update_thread_status.side_effect = lambda doc_id, thread_id, status: {
        "id": thread_id,
        "status": status,
        "updated_at": "2023-01-01T00:00:00Z"
    }
    return manager


@pytest.fixture
def mock_notification_service():
    """Fixture for mocking the notification service."""
    service = MagicMock()
    service.notify_comment_created.return_value = None
    service.notify_thread_resolved.return_value = None
    return service


@pytest.fixture
def collaboration_config(notebookapp):
    """Fixture to ensure collaboration is enabled for tests"""
    app = notebookapp
    app.collaboration_enabled = True
    app.collaboration_backend = "memory"  # Use in-memory backend for tests
    app.collaboration_auth_mode = "token"  # Use token auth for tests
    return app


async def test_comment_creation(jp_fetch, collaboration_config):
    """Test creating a comment thread on a cell."""
    # Create a session first
    data = {"document_id": "test_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create a comment thread
    thread_data = {
        "cell_id": "cell-1",
        "content": "This is a test comment"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    assert r.code == 201
    thread = json.loads(r.body.decode())
    
    # Verify the thread was created correctly
    assert thread["cell_id"] == "cell-1"
    assert "id" in thread
    assert "comments" in thread
    assert len(thread["comments"]) == 1
    assert thread["comments"][0]["content"] == "This is a test comment"
    assert thread["status"] == "open"


async def test_comment_retrieval(jp_fetch, collaboration_config):
    """Test retrieving comments for a document."""
    # Create a session
    data = {"document_id": "test_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create a comment thread
    thread_data = {
        "cell_id": "cell-1",
        "content": "This is a test comment"
    }
    await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                  method="POST", 
                  body=json.dumps(thread_data))
    
    # Retrieve all comments for the document
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}")
    assert r.code == 200
    comments = json.loads(r.body.decode())
    
    # Verify the comments were retrieved correctly
    assert "threads" in comments
    assert len(comments["threads"]) == 1
    assert comments["threads"][0]["cell_id"] == "cell-1"
    assert len(comments["threads"][0]["comments"]) == 1
    assert comments["threads"][0]["comments"][0]["content"] == "This is a test comment"


async def test_comment_thread_replies(jp_fetch, collaboration_config):
    """Test adding replies to a comment thread."""
    # Create a session
    data = {"document_id": "test_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create a comment thread
    thread_data = {
        "cell_id": "cell-1",
        "content": "This is a test comment"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    thread = json.loads(r.body.decode())
    thread_id = thread["id"]
    
    # Add a reply to the thread
    reply_data = {"content": "This is a reply"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}", 
                      method="POST", 
                      body=json.dumps(reply_data))
    assert r.code == 201
    comment = json.loads(r.body.decode())
    
    # Verify the reply was added correctly
    assert comment["content"] == "This is a reply"
    assert "id" in comment
    assert "thread_id" in comment
    assert comment["thread_id"] == thread_id
    
    # Retrieve the thread to verify it contains both comments
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}")
    assert r.code == 200
    updated_thread = json.loads(r.body.decode())
    
    assert len(updated_thread["comments"]) == 2
    assert updated_thread["comments"][0]["content"] == "This is a test comment"
    assert updated_thread["comments"][1]["content"] == "This is a reply"


async def test_comment_resolution_workflow(jp_fetch, collaboration_config):
    """Test the comment resolution workflow."""
    # Create a session
    data = {"document_id": "test_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create a comment thread
    thread_data = {
        "cell_id": "cell-1",
        "content": "This is a test comment"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    thread = json.loads(r.body.decode())
    thread_id = thread["id"]
    
    # Resolve the thread
    resolve_data = {"status": "resolved"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}/status", 
                      method="PUT", 
                      body=json.dumps(resolve_data))
    assert r.code == 200
    updated_thread = json.loads(r.body.decode())
    
    # Verify the thread was resolved
    assert updated_thread["status"] == "resolved"
    
    # Reopen the thread
    reopen_data = {"status": "open"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}/status", 
                      method="PUT", 
                      body=json.dumps(reopen_data))
    assert r.code == 200
    reopened_thread = json.loads(r.body.decode())
    
    # Verify the thread was reopened
    assert reopened_thread["status"] == "open"


async def test_comment_synchronization(multi_client_websocket_simulation):
    """Test that comments are synchronized between clients."""
    # Create two clients
    client1 = await multi_client_websocket_simulation(user_id="user1")
    client2 = await multi_client_websocket_simulation(user_id="user2")
    
    # Connect both clients to the same document
    doc_id = "test_sync_notebook.ipynb"
    await client1.connect(doc_id=doc_id)
    await client2.connect(doc_id=doc_id)
    
    # Initialize the document structure if needed
    await client1.update_document({
        "metadata": {"kernelspec": {"name": "python3"}},
        "cells": [{"id": "cell-1", "cell_type": "code", "source": "print('Hello')"}, 
                  {"id": "cell-2", "cell_type": "markdown", "source": "# Header"}]
    })
    
    # Wait for synchronization
    await asyncio.sleep(0.1)
    
    # Client 1 adds a comment to cell-1
    await client1.update_document({
        "comments": {
            "threads": [{
                "id": "thread-1",
                "cell_id": "cell-1",
                "status": "open",
                "comments": [{
                    "id": "comment-1",
                    "user_id": "user1",
                    "content": "This code needs improvement",
                    "created_at": "2023-01-01T00:00:00Z"
                }]
            }]
        }
    })
    
    # Wait for synchronization
    await asyncio.sleep(0.1)
    
    # Verify client2 received the comment
    client2_state = await client2.get_document_state()
    assert "comments" in client2_state
    assert "threads" in client2_state["comments"]
    assert len(client2_state["comments"]["threads"]) == 1
    assert client2_state["comments"]["threads"][0]["cell_id"] == "cell-1"
    assert client2_state["comments"]["threads"][0]["comments"][0]["content"] == "This code needs improvement"
    
    # Client 2 adds a reply
    await client2.update_document({
        "comments": {
            "threads": [{
                "id": "thread-1",
                "cell_id": "cell-1",
                "status": "open",
                "comments": [
                    # Existing comment remains
                    {
                        "id": "comment-1",
                        "user_id": "user1",
                        "content": "This code needs improvement",
                        "created_at": "2023-01-01T00:00:00Z"
                    },
                    # New reply
                    {
                        "id": "comment-2",
                        "user_id": "user2",
                        "content": "I'll fix it",
                        "created_at": "2023-01-01T00:00:01Z"
                    }
                ]
            }]
        }
    })
    
    # Wait for synchronization
    await asyncio.sleep(0.1)
    
    # Verify client1 received the reply
    client1_state = await client1.get_document_state()
    assert len(client1_state["comments"]["threads"][0]["comments"]) == 2
    assert client1_state["comments"]["threads"][0]["comments"][1]["content"] == "I'll fix it"
    
    # Clean up
    await client1.disconnect()
    await client2.disconnect()


async def test_comment_persistence(jp_fetch, collaboration_config, multi_client_websocket_simulation):
    """Test that comments persist across sessions."""
    # Create a session
    data = {"document_id": "test_persistence_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create a comment thread via REST API
    thread_data = {
        "cell_id": "cell-1",
        "content": "This comment should persist"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    thread = json.loads(r.body.decode())
    thread_id = thread["id"]
    
    # Connect a client to the document via WebSocket
    client = await multi_client_websocket_simulation(user_id="test_user")
    await client.connect(doc_id=document_id)
    
    # Wait for synchronization
    await asyncio.sleep(0.1)
    
    # Verify the client received the existing comment
    client_state = await client.get_document_state()
    
    # The comments might be in a different structure depending on implementation
    # Try both possible structures
    if "comments" in client_state and isinstance(client_state["comments"], dict):
        assert "threads" in client_state["comments"]
        threads = client_state["comments"]["threads"]
    else:
        # Get comments from the client directly if not in document state
        r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}")
        comments_data = json.loads(r.body.decode())
        threads = comments_data["threads"]
    
    assert len(threads) > 0
    assert any(t["id"] == thread_id for t in threads)
    matching_thread = next(t for t in threads if t["id"] == thread_id)
    assert matching_thread["comments"][0]["content"] == "This comment should persist"
    
    # Disconnect the client
    await client.disconnect()
    
    # Connect a new client to verify persistence
    new_client = await multi_client_websocket_simulation(user_id="another_user")
    await new_client.connect(doc_id=document_id)
    
    # Wait for synchronization
    await asyncio.sleep(0.1)
    
    # Verify the new client also receives the comment
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}")
    comments_data = json.loads(r.body.decode())
    threads = comments_data["threads"]
    
    assert len(threads) > 0
    assert any(t["id"] == thread_id for t in threads)
    matching_thread = next(t for t in threads if t["id"] == thread_id)
    assert matching_thread["comments"][0]["content"] == "This comment should persist"
    
    # Clean up
    await new_client.disconnect()


@patch("notebook.collab.comments.NotificationService")
async def test_comment_notifications(mock_notification_service, jp_fetch, collaboration_config):
    """Test that notifications are sent for comment events."""
    # Setup mock notification service
    notification_service = MagicMock()
    mock_notification_service.return_value = notification_service
    
    # Create a session
    data = {"document_id": "test_notification_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create a comment thread
    thread_data = {
        "cell_id": "cell-1",
        "content": "This should trigger a notification"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    thread = json.loads(r.body.decode())
    thread_id = thread["id"]
    
    # Verify notification was sent for thread creation
    notification_service.notify_comment_created.assert_called_once()
    notification_service.notify_comment_created.reset_mock()
    
    # Add a reply to the thread
    reply_data = {"content": "This is a reply that should notify"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}", 
                      method="POST", 
                      body=json.dumps(reply_data))
    
    # Verify notification was sent for reply
    notification_service.notify_comment_created.assert_called_once()
    notification_service.notify_comment_created.reset_mock()
    
    # Resolve the thread
    resolve_data = {"status": "resolved"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}/status", 
                      method="PUT", 
                      body=json.dumps(resolve_data))
    
    # Verify notification was sent for resolution
    notification_service.notify_thread_resolved.assert_called_once()


async def test_comment_cell_deletion_handling(jp_fetch, collaboration_config, multi_client_websocket_simulation):
    """Test handling of comments when referenced cells are deleted."""
    # Create a session
    data = {"document_id": "test_cell_deletion_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Connect a client to set up the document
    client = await multi_client_websocket_simulation(user_id="test_user")
    await client.connect(doc_id=document_id)
    
    # Initialize the document with cells
    await client.update_document({
        "metadata": {"kernelspec": {"name": "python3"}},
        "cells": [
            {"id": "cell-to-delete", "cell_type": "code", "source": "print('Delete me')"},
            {"id": "cell-to-keep", "cell_type": "code", "source": "print('Keep me')"}
        ]
    })
    
    # Wait for synchronization
    await asyncio.sleep(0.1)
    
    # Create a comment thread on the cell that will be deleted
    thread_data = {
        "cell_id": "cell-to-delete",
        "content": "Comment on cell to be deleted"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    deleted_cell_thread = json.loads(r.body.decode())
    
    # Create a comment thread on the cell that will be kept
    thread_data = {
        "cell_id": "cell-to-keep",
        "content": "Comment on cell to keep"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    
    # Delete the cell
    await client.update_document({
        "cells": [
            # Only include the cell to keep
            {"id": "cell-to-keep", "cell_type": "code", "source": "print('Keep me')"}
        ]
    })
    
    # Wait for synchronization
    await asyncio.sleep(0.1)
    
    # Retrieve all comments for the document
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}")
    comments = json.loads(r.body.decode())
    
    # Verify the comment on the deleted cell is handled appropriately
    # Depending on implementation, it might be archived, reassigned, or marked as orphaned
    deleted_cell_thread_id = deleted_cell_thread["id"]
    matching_thread = next((t for t in comments["threads"] if t["id"] == deleted_cell_thread_id), None)
    
    # The thread should still exist but might be marked as orphaned or archived
    assert matching_thread is not None
    
    # Check if it's marked as orphaned, archived, or reassigned
    # This depends on the specific implementation
    assert any([
        matching_thread.get("status") == "archived",
        matching_thread.get("orphaned") is True,
        matching_thread.get("cell_id") != "cell-to-delete"  # Reassigned
    ])
    
    # Clean up
    await client.disconnect()


async def test_comment_filtering(jp_fetch, collaboration_config):
    """Test filtering comments by status and cell ID."""
    # Create a session
    data = {"document_id": "test_filtering_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create comment threads with different statuses and cell IDs
    # Thread 1: cell-1, open
    thread1_data = {"cell_id": "cell-1", "content": "Open comment on cell 1"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread1_data))
    thread1 = json.loads(r.body.decode())
    
    # Thread 2: cell-2, open
    thread2_data = {"cell_id": "cell-2", "content": "Open comment on cell 2"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread2_data))
    thread2 = json.loads(r.body.decode())
    
    # Thread 3: cell-1, resolved
    thread3_data = {"cell_id": "cell-1", "content": "To be resolved comment on cell 1"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread3_data))
    thread3 = json.loads(r.body.decode())
    
    # Resolve thread 3
    resolve_data = {"status": "resolved"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread3['id']}/status", 
                      method="PUT", 
                      body=json.dumps(resolve_data))
    
    # Test filtering by cell ID
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}?cell_id=cell-1")
    cell1_comments = json.loads(r.body.decode())
    
    assert len(cell1_comments["threads"]) == 2
    assert all(t["cell_id"] == "cell-1" for t in cell1_comments["threads"])
    
    # Test filtering by status
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}?status=open")
    open_comments = json.loads(r.body.decode())
    
    assert len(open_comments["threads"]) == 2
    assert all(t["status"] == "open" for t in open_comments["threads"])
    
    # Test filtering by both cell ID and status
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}?cell_id=cell-1&status=resolved")
    filtered_comments = json.loads(r.body.decode())
    
    assert len(filtered_comments["threads"]) == 1
    assert filtered_comments["threads"][0]["cell_id"] == "cell-1"
    assert filtered_comments["threads"][0]["status"] == "resolved"


async def test_comment_mentions(jp_fetch, collaboration_config):
    """Test comment mentions functionality."""
    # Create a session
    data = {"document_id": "test_mentions_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create a comment thread with mentions
    thread_data = {
        "cell_id": "cell-1",
        "content": "Hey @user1 and @user2, please review this code",
        "metadata": {
            "mentions": ["user1", "user2"]
        }
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    assert r.code == 201
    thread = json.loads(r.body.decode())
    
    # Verify the mentions were captured in the metadata
    assert "metadata" in thread
    assert "mentions" in thread["metadata"]
    assert "user1" in thread["metadata"]["mentions"]
    assert "user2" in thread["metadata"]["mentions"]
    
    # Test retrieving comments that mention a specific user
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}?mentioned=user1")
    mentioned_comments = json.loads(r.body.decode())
    
    assert len(mentioned_comments["threads"]) == 1
    assert "metadata" in mentioned_comments["threads"][0]
    assert "mentions" in mentioned_comments["threads"][0]["metadata"]
    assert "user1" in mentioned_comments["threads"][0]["metadata"]["mentions"]


async def test_comment_editing(jp_fetch, collaboration_config):
    """Test editing comments."""
    # Create a session
    data = {"document_id": "test_editing_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create a comment thread
    thread_data = {
        "cell_id": "cell-1",
        "content": "Original comment content"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    thread = json.loads(r.body.decode())
    thread_id = thread["id"]
    comment_id = thread["comments"][0]["id"]
    
    # Edit the comment
    edit_data = {
        "content": "Updated comment content",
        "user_id": thread["comments"][0]["user_id"]  # Same user editing their own comment
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}/{comment_id}", 
                      method="PUT", 
                      body=json.dumps(edit_data))
    assert r.code == 200
    edited_comment = json.loads(r.body.decode())
    
    # Verify the comment was edited
    assert edited_comment["content"] == "Updated comment content"
    assert "edited" in edited_comment
    assert edited_comment["edited"] is True
    assert "updated_at" in edited_comment
    
    # Get the thread to verify the edit persisted
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}")
    updated_thread = json.loads(r.body.decode())
    
    # Verify the edit is reflected in the thread
    comment = next(c for c in updated_thread["comments"] if c["id"] == comment_id)
    assert comment["content"] == "Updated comment content"
    assert comment["edited"] is True


async def test_comment_permissions(jp_fetch, collaboration_config):
    """Test comment permissions and authorization."""
    # Create a session
    data = {"document_id": "test_permissions_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create users with different roles
    owner_data = {"user_id": "owner_user", "role": "owner"}
    commenter_data = {"user_id": "commenter_user", "role": "commenter"}
    viewer_data = {"user_id": "viewer_user", "role": "viewer"}
    
    # Set up permissions for the document
    await jp_fetch(f"api/collaboration/v1/permissions/{document_id}", 
                  method="POST", 
                  body=json.dumps(owner_data))
    await jp_fetch(f"api/collaboration/v1/permissions/{document_id}", 
                  method="POST", 
                  body=json.dumps(commenter_data))
    await jp_fetch(f"api/collaboration/v1/permissions/{document_id}", 
                  method="POST", 
                  body=json.dumps(viewer_data))
    
    # Test that commenter can create comments
    thread_data = {
        "cell_id": "cell-1",
        "content": "Comment from commenter",
        "user_id": "commenter_user"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data),
                      headers={"X-Test-User-Id": "commenter_user"})
    assert r.code == 201
    thread = json.loads(r.body.decode())
    thread_id = thread["id"]
    
    # Test that viewer cannot create comments (should return 403)
    thread_data = {
        "cell_id": "cell-1",
        "content": "Comment from viewer",
        "user_id": "viewer_user"
    }
    try:
        r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                          method="POST", 
                          body=json.dumps(thread_data),
                          headers={"X-Test-User-Id": "viewer_user"})
        assert False, "Viewer should not be able to create comments"
    except Exception as e:
        assert "403" in str(e), f"Expected 403 error, got: {e}"
    
    # Test that owner can resolve comments
    resolve_data = {"status": "resolved", "user_id": "owner_user"}
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}/status", 
                      method="PUT", 
                      body=json.dumps(resolve_data),
                      headers={"X-Test-User-Id": "owner_user"})
    assert r.code == 200
    
    # Test that commenter cannot delete other's comments (should return 403)
    try:
        r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}", 
                          method="DELETE", 
                          headers={"X-Test-User-Id": "commenter_user"})
        assert False, "Commenter should not be able to delete others' comments"
    except Exception as e:
        assert "403" in str(e), f"Expected 403 error, got: {e}"
    
    # Test that owner can delete comments
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}", 
                      method="DELETE", 
                      headers={"X-Test-User-Id": "owner_user"})
    assert r.code == 204


async def test_comment_attachments(jp_fetch, collaboration_config):
    """Test comment attachments functionality."""
    # Create a session
    data = {"document_id": "test_attachments_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create a comment thread with attachment metadata
    thread_data = {
        "cell_id": "cell-1",
        "content": "Comment with attachment reference",
        "metadata": {
            "attachments": [{
                "id": "attachment-1",
                "name": "screenshot.png",
                "mime_type": "image/png",
                "size": 1024,
                "url": "/api/collaboration/v1/attachments/attachment-1"
            }]
        }
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    assert r.code == 201
    thread = json.loads(r.body.decode())
    
    # Verify the attachment metadata was saved
    assert "metadata" in thread
    assert "attachments" in thread["metadata"]
    assert len(thread["metadata"]["attachments"]) == 1
    assert thread["metadata"]["attachments"][0]["name"] == "screenshot.png"
    
    # Test uploading an attachment (mock the file upload)
    # This would typically be a multipart form request with a file
    # For testing purposes, we'll just verify the endpoint exists and returns expected status
    try:
        r = await jp_fetch(f"api/collaboration/v1/attachments", 
                          method="POST",
                          body=json.dumps({"mock": "file_upload"}),
                          headers={"Content-Type": "application/json"})
        # If the endpoint exists but doesn't accept our mock data, we'll get an error but not a 404
        assert r.code != 404, "Attachment upload endpoint should exist"
    except Exception as e:
        # We expect an error since we're not sending a proper file upload
        # Just verify it's not a 404 (endpoint not found)
        assert "404" not in str(e), "Attachment upload endpoint should exist"


async def test_comment_markdown_formatting(jp_fetch, collaboration_config):
    """Test markdown formatting in comments."""
    # Create a session
    data = {"document_id": "test_markdown_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create a comment thread with markdown formatting
    thread_data = {
        "cell_id": "cell-1",
        "content": "# Heading\n\n**Bold text** and *italic text*\n\n```python\nprint('Code block')\n```\n\n- List item 1\n- List item 2",
        "metadata": {
            "format": "markdown"
        }
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    assert r.code == 201
    thread = json.loads(r.body.decode())
    
    # Verify the format metadata was saved
    assert "metadata" in thread
    assert "format" in thread["metadata"]
    assert thread["metadata"]["format"] == "markdown"
    
    # Retrieve the thread to verify the content was preserved
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread['id']}")
    retrieved_thread = json.loads(r.body.decode())
    
    # Verify the markdown content was preserved
    assert "# Heading" in retrieved_thread["comments"][0]["content"]
    assert "**Bold text**" in retrieved_thread["comments"][0]["content"]
    assert "```python" in retrieved_thread["comments"][0]["content"]
    
    # Test that the client can render the markdown (simulated)
    # In a real test, we would check that the UI renders the markdown correctly
    # Here we just verify that the format information is available to the client
    assert retrieved_thread["metadata"]["format"] == "markdown"


async def test_comment_reactions(jp_fetch, collaboration_config):
    """Test adding reactions to comments."""
    # Create a session
    data = {"document_id": "test_reactions_notebook.ipynb"}
    r = await jp_fetch("api/collaboration/v1/sessions", method="POST", body=json.dumps(data))
    session = json.loads(r.body.decode())
    document_id = session["document_id"]
    
    # Create a comment thread
    thread_data = {
        "cell_id": "cell-1",
        "content": "Comment for reactions"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}", 
                      method="POST", 
                      body=json.dumps(thread_data))
    thread = json.loads(r.body.decode())
    thread_id = thread["id"]
    comment_id = thread["comments"][0]["id"]
    
    # Add a reaction to the comment
    reaction_data = {
        "reaction": "👍",
        "user_id": "test_user"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}/{comment_id}/reactions", 
                      method="POST", 
                      body=json.dumps(reaction_data))
    assert r.code == 201
    
    # Get the comment with reactions
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}")
    updated_thread = json.loads(r.body.decode())
    
    # Verify the reaction was added
    comment = next(c for c in updated_thread["comments"] if c["id"] == comment_id)
    assert "reactions" in comment
    assert "👍" in comment["reactions"]
    assert comment["reactions"]["👍"] == ["test_user"]
    
    # Add another reaction from a different user
    reaction_data = {
        "reaction": "👍",
        "user_id": "another_user"
    }
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}/{comment_id}/reactions", 
                      method="POST", 
                      body=json.dumps(reaction_data))
    
    # Get the updated comment
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}")
    updated_thread = json.loads(r.body.decode())
    
    # Verify both users' reactions are present
    comment = next(c for c in updated_thread["comments"] if c["id"] == comment_id)
    assert len(comment["reactions"]["👍"]) == 2
    assert "test_user" in comment["reactions"]["👍"]
    assert "another_user" in comment["reactions"]["👍"]
    
    # Remove a reaction
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}/{comment_id}/reactions/👍", 
                      method="DELETE",
                      body=json.dumps({"user_id": "test_user"}))
    assert r.code == 204
    
    # Get the updated comment
    r = await jp_fetch(f"api/collaboration/v1/comments/{document_id}/{thread_id}")
    updated_thread = json.loads(r.body.decode())
    
    # Verify the reaction was removed
    comment = next(c for c in updated_thread["comments"] if c["id"] == comment_id)
    assert len(comment["reactions"]["👍"]) == 1
    assert "another_user" in comment["reactions"]["👍"]
    assert "test_user" not in comment["reactions"]["👍"]
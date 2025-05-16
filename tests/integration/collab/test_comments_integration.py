import asyncio
import json
import os
import pytest
import time
import uuid

# Import test utilities
from tests.integration.collab.conftest import WebSocketTestClient

# Test constants
TIMEOUT = 5.0  # Default timeout for async operations in seconds


@pytest.mark.asyncio
async def test_comment_creation_and_synchronization(jp_ws_client, create_collaborative_session):
    """
    Test that comments can be created and synchronized across clients.
    
    This test verifies that when one user creates a comment on a cell, it is properly
    synchronized to other users viewing the same notebook.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    user1_client, user2_client = clients
    
    # Clear any existing messages
    user1_client.clear_received_messages()
    user2_client.clear_received_messages()
    
    # User 1 creates a comment on a cell
    cell_id = "cell-1"  # Assuming this cell exists in the test document
    comment_text = "This is a test comment from User 1"
    comment_id = str(uuid.uuid4())
    
    # Send comment creation message
    await user1_client.send({
        "type": "comment_create",
        "cell_id": cell_id,
        "comment_id": comment_id,
        "content": comment_text,
        "timestamp": int(time.time() * 1000)
    })
    
    # Wait for the comment to be synchronized to user 2
    message = await user2_client.wait_for_message_containing(comment_id, timeout=TIMEOUT)
    
    # Verify that user 2 received the comment
    assert message is not None, "Comment creation was not synchronized to user 2"
    
    # Parse the message and verify its contents
    try:
        data = json.loads(message)
        assert data.get("type") == "comment_update", "Incorrect message type"
        assert data.get("cell_id") == cell_id, "Incorrect cell ID"
        assert data.get("comment_id") == comment_id, "Incorrect comment ID"
        assert data.get("content") == comment_text, "Incorrect comment content"
        assert data.get("author") == user1_client.user_id, "Incorrect comment author"
    except json.JSONDecodeError:
        pytest.fail("Received message is not valid JSON")
    except KeyError as e:
        pytest.fail(f"Missing expected field in comment message: {e}")


@pytest.mark.asyncio
async def test_comment_thread_management_and_replies(jp_ws_client, create_collaborative_session):
    """
    Test comment thread management including replies to existing comments.
    
    This test verifies that users can reply to existing comments and that these replies
    are properly organized in threads and synchronized across clients.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    user1_client, user2_client = clients
    
    # Clear any existing messages
    user1_client.clear_received_messages()
    user2_client.clear_received_messages()
    
    # User 1 creates a comment thread on a cell
    cell_id = "cell-1"
    thread_id = str(uuid.uuid4())
    comment_text = "Initial comment to start a thread"
    
    # Send thread creation message
    await user1_client.send({
        "type": "thread_create",
        "cell_id": cell_id,
        "thread_id": thread_id,
        "content": comment_text,
        "timestamp": int(time.time() * 1000)
    })
    
    # Wait for the thread to be synchronized to user 2
    thread_message = await user2_client.wait_for_message_containing(thread_id, timeout=TIMEOUT)
    assert thread_message is not None, "Thread creation was not synchronized to user 2"
    
    # User 2 replies to the thread
    reply_id = str(uuid.uuid4())
    reply_text = "This is a reply from User 2"
    
    # Send reply message
    await user2_client.send({
        "type": "comment_reply",
        "thread_id": thread_id,
        "comment_id": reply_id,
        "content": reply_text,
        "timestamp": int(time.time() * 1000)
    })
    
    # Wait for the reply to be synchronized to user 1
    reply_message = await user1_client.wait_for_message_containing(reply_id, timeout=TIMEOUT)
    assert reply_message is not None, "Reply was not synchronized to user 1"
    
    # Parse the reply message and verify its contents
    try:
        data = json.loads(reply_message)
        assert data.get("type") == "comment_update", "Incorrect message type"
        assert data.get("thread_id") == thread_id, "Incorrect thread ID"
        assert data.get("comment_id") == reply_id, "Incorrect comment ID"
        assert data.get("content") == reply_text, "Incorrect reply content"
        assert data.get("author") == user2_client.user_id, "Incorrect reply author"
    except json.JSONDecodeError:
        pytest.fail("Received message is not valid JSON")
    except KeyError as e:
        pytest.fail(f"Missing expected field in reply message: {e}")
    
    # Verify thread structure by requesting the full thread
    await user1_client.send({
        "type": "get_thread",
        "thread_id": thread_id
    })
    
    # Wait for the thread data response
    thread_data_message = await user1_client.wait_for_message_containing("thread_data", timeout=TIMEOUT)
    assert thread_data_message is not None, "Failed to retrieve thread data"
    
    # Verify the thread structure contains both the initial comment and the reply
    try:
        data = json.loads(thread_data_message)
        assert data.get("type") == "thread_data", "Incorrect message type"
        assert data.get("thread_id") == thread_id, "Incorrect thread ID"
        
        comments = data.get("comments", [])
        assert len(comments) == 2, "Thread should contain 2 comments (initial + reply)"
        
        # Verify the comments are in the correct order (initial first, reply second)
        assert comments[0].get("content") == comment_text, "First comment should be the initial comment"
        assert comments[1].get("content") == reply_text, "Second comment should be the reply"
    except json.JSONDecodeError:
        pytest.fail("Received thread data is not valid JSON")
    except (KeyError, IndexError) as e:
        pytest.fail(f"Error verifying thread structure: {e}")


@pytest.mark.asyncio
async def test_comment_resolution_workflow(jp_ws_client, create_collaborative_session):
    """
    Test the comment resolution workflow.
    
    This test verifies that users can mark comment threads as resolved or reopen them,
    and that these status changes are properly synchronized across clients.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    user1_client, user2_client = clients
    
    # Clear any existing messages
    user1_client.clear_received_messages()
    user2_client.clear_received_messages()
    
    # User 1 creates a comment thread
    cell_id = "cell-1"
    thread_id = str(uuid.uuid4())
    comment_text = "This is a comment that will be resolved"
    
    # Create the thread
    await user1_client.send({
        "type": "thread_create",
        "cell_id": cell_id,
        "thread_id": thread_id,
        "content": comment_text,
        "timestamp": int(time.time() * 1000)
    })
    
    # Wait for the thread to be synchronized to user 2
    await user2_client.wait_for_message_containing(thread_id, timeout=TIMEOUT)
    
    # User 2 resolves the thread
    resolution_timestamp = int(time.time() * 1000)
    await user2_client.send({
        "type": "thread_resolve",
        "thread_id": thread_id,
        "resolved": True,
        "resolved_by": user2_client.user_id,
        "timestamp": resolution_timestamp
    })
    
    # Wait for the resolution to be synchronized to user 1
    resolution_message = await user1_client.wait_for_message_containing("thread_status", timeout=TIMEOUT)
    assert resolution_message is not None, "Thread resolution was not synchronized to user 1"
    
    # Verify the resolution message
    try:
        data = json.loads(resolution_message)
        assert data.get("type") == "thread_status", "Incorrect message type"
        assert data.get("thread_id") == thread_id, "Incorrect thread ID"
        assert data.get("resolved") is True, "Thread should be marked as resolved"
        assert data.get("resolved_by") == user2_client.user_id, "Incorrect resolver"
        assert data.get("timestamp") == resolution_timestamp, "Incorrect resolution timestamp"
    except json.JSONDecodeError:
        pytest.fail("Received message is not valid JSON")
    except KeyError as e:
        pytest.fail(f"Missing expected field in resolution message: {e}")
    
    # User 1 reopens the thread
    reopen_timestamp = int(time.time() * 1000)
    await user1_client.send({
        "type": "thread_resolve",
        "thread_id": thread_id,
        "resolved": False,
        "resolved_by": user1_client.user_id,
        "timestamp": reopen_timestamp
    })
    
    # Wait for the reopen action to be synchronized to user 2
    reopen_message = await user2_client.wait_for_message_containing("thread_status", timeout=TIMEOUT)
    assert reopen_message is not None, "Thread reopen was not synchronized to user 2"
    
    # Verify the reopen message
    try:
        data = json.loads(reopen_message)
        assert data.get("type") == "thread_status", "Incorrect message type"
        assert data.get("thread_id") == thread_id, "Incorrect thread ID"
        assert data.get("resolved") is False, "Thread should be marked as not resolved"
        assert data.get("resolved_by") == user1_client.user_id, "Incorrect resolver"
        assert data.get("timestamp") == reopen_timestamp, "Incorrect reopen timestamp"
    except json.JSONDecodeError:
        pytest.fail("Received message is not valid JSON")
    except KeyError as e:
        pytest.fail(f"Missing expected field in reopen message: {e}")


@pytest.mark.asyncio
async def test_comment_notifications(jp_ws_client, create_collaborative_session):
    """
    Test that comment notifications are delivered to relevant users.
    
    This test verifies that when a user is mentioned in a comment or when a comment is added
    to a thread they're participating in, they receive appropriate notifications.
    """
    # Create a collaborative session with 3 clients (to test targeted notifications)
    document_path, clients = await create_collaborative_session(num_clients=3)
    user1_client, user2_client, user3_client = clients
    
    # Clear any existing messages
    for client in clients:
        client.clear_received_messages()
    
    # User 1 creates a comment thread
    cell_id = "cell-1"
    thread_id = str(uuid.uuid4())
    comment_text = "Initial comment by User 1"
    
    await user1_client.send({
        "type": "thread_create",
        "cell_id": cell_id,
        "thread_id": thread_id,
        "content": comment_text,
        "timestamp": int(time.time() * 1000)
    })
    
    # Wait for the thread to be synchronized to all users
    for client in [user2_client, user3_client]:
        await client.wait_for_message_containing(thread_id, timeout=TIMEOUT)
    
    # User 2 replies with a mention of User 3
    mention_id = str(uuid.uuid4())
    mention_text = f"Hey @{user3_client.user_id}, can you take a look at this?"
    
    await user2_client.send({
        "type": "comment_reply",
        "thread_id": thread_id,
        "comment_id": mention_id,
        "content": mention_text,
        "mentions": [user3_client.user_id],
        "timestamp": int(time.time() * 1000)
    })
    
    # Wait for the mention notification to be delivered to User 3
    mention_notification = await user3_client.wait_for_message_containing("notification", timeout=TIMEOUT)
    assert mention_notification is not None, "Mention notification was not delivered to User 3"
    
    # Verify the mention notification
    try:
        data = json.loads(mention_notification)
        assert data.get("type") == "notification", "Incorrect message type"
        assert data.get("notification_type") == "mention", "Incorrect notification type"
        assert data.get("thread_id") == thread_id, "Incorrect thread ID"
        assert data.get("comment_id") == mention_id, "Incorrect comment ID"
        assert data.get("mentioned_by") == user2_client.user_id, "Incorrect mentioner"
    except json.JSONDecodeError:
        pytest.fail("Received notification is not valid JSON")
    except KeyError as e:
        pytest.fail(f"Missing expected field in notification message: {e}")
    
    # User 3 replies to the thread
    reply_id = str(uuid.uuid4())
    reply_text = "I'll take a look at it."
    
    await user3_client.send({
        "type": "comment_reply",
        "thread_id": thread_id,
        "comment_id": reply_id,
        "content": reply_text,
        "timestamp": int(time.time() * 1000)
    })
    
    # Both User 1 and User 2 should receive thread activity notifications
    # since they're participants in the thread
    for client, name in [(user1_client, "User 1"), (user2_client, "User 2")]:
        activity_notification = await client.wait_for_message_containing("notification", timeout=TIMEOUT)
        assert activity_notification is not None, f"Thread activity notification was not delivered to {name}"
        
        # Verify the activity notification
        try:
            data = json.loads(activity_notification)
            assert data.get("type") == "notification", "Incorrect message type"
            assert data.get("notification_type") == "thread_activity", "Incorrect notification type"
            assert data.get("thread_id") == thread_id, "Incorrect thread ID"
            assert data.get("comment_id") == reply_id, "Incorrect comment ID"
            assert data.get("author") == user3_client.user_id, "Incorrect author"
        except json.JSONDecodeError:
            pytest.fail("Received notification is not valid JSON")
        except KeyError as e:
            pytest.fail(f"Missing expected field in notification message: {e}")


@pytest.mark.asyncio
async def test_comment_persistence_across_sessions(jp_ws_client, create_collaborative_session, simulate_server_restart):
    """
    Test that comments persist across sessions and server restarts.
    
    This test verifies that comment threads and their content are properly persisted
    and can be retrieved after disconnection and reconnection or server restarts.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    user1_client, user2_client = clients
    document_name = os.path.basename(document_path)
    
    # Clear any existing messages
    user1_client.clear_received_messages()
    user2_client.clear_received_messages()
    
    # User 1 creates a comment thread
    cell_id = "cell-1"
    thread_id = str(uuid.uuid4())
    comment_text = "This comment should persist across sessions"
    
    await user1_client.send({
        "type": "thread_create",
        "cell_id": cell_id,
        "thread_id": thread_id,
        "content": comment_text,
        "timestamp": int(time.time() * 1000)
    })
    
    # Wait for the thread to be synchronized to user 2
    await user2_client.wait_for_message_containing(thread_id, timeout=TIMEOUT)
    
    # User 2 adds a reply
    reply_id = str(uuid.uuid4())
    reply_text = "This reply should also persist"
    
    await user2_client.send({
        "type": "comment_reply",
        "thread_id": thread_id,
        "comment_id": reply_id,
        "content": reply_text,
        "timestamp": int(time.time() * 1000)
    })
    
    # Wait for the reply to be synchronized to user 1
    await user1_client.wait_for_message_containing(reply_id, timeout=TIMEOUT)
    
    # Disconnect both clients
    await user1_client.disconnect()
    await user2_client.disconnect()
    
    # Simulate a server restart
    restart_successful = await simulate_server_restart()
    assert restart_successful, "Server restart simulation failed"
    
    # Create new clients and reconnect to the same document
    new_user1_client = await jp_ws_client(user_id=user1_client.user_id)
    new_user2_client = await jp_ws_client(user_id=user2_client.user_id)
    
    await new_user1_client.connect(document_name)
    await new_user2_client.connect(document_name)
    
    # Request all comment threads for the document
    await new_user1_client.send({
        "type": "get_document_threads",
        "document_id": document_name
    })
    
    # Wait for the threads response
    threads_message = await new_user1_client.wait_for_message_containing("document_threads", timeout=TIMEOUT)
    assert threads_message is not None, "Failed to retrieve document threads after reconnection"
    
    # Verify that the thread and comments are present in the response
    try:
        data = json.loads(threads_message)
        assert data.get("type") == "document_threads", "Incorrect message type"
        
        threads = data.get("threads", [])
        assert len(threads) > 0, "No threads found after reconnection"
        
        # Find our test thread
        test_thread = None
        for thread in threads:
            if thread.get("thread_id") == thread_id:
                test_thread = thread
                break
                
        assert test_thread is not None, "Test thread not found after reconnection"
        assert test_thread.get("cell_id") == cell_id, "Incorrect cell ID in persisted thread"
        
        # Verify the comments in the thread
        comments = test_thread.get("comments", [])
        assert len(comments) == 2, "Thread should contain 2 comments after reconnection"
        
        # Verify the initial comment
        assert comments[0].get("content") == comment_text, "Initial comment content not preserved"
        assert comments[0].get("author") == user1_client.user_id, "Initial comment author not preserved"
        
        # Verify the reply
        assert comments[1].get("content") == reply_text, "Reply content not preserved"
        assert comments[1].get("author") == user2_client.user_id, "Reply author not preserved"
        assert comments[1].get("comment_id") == reply_id, "Reply ID not preserved"
    except json.JSONDecodeError:
        pytest.fail("Received message is not valid JSON")
    except (KeyError, IndexError) as e:
        pytest.fail(f"Error verifying persisted comments: {e}")


@pytest.mark.asyncio
async def test_comment_editing_and_deletion(jp_ws_client, create_collaborative_session):
    """
    Test that users can edit and delete their own comments.
    
    This test verifies that users can edit and delete their own comments, and that these
    changes are properly synchronized to other users.
    """
    # Create a collaborative session with 2 clients
    document_path, clients = await create_collaborative_session(num_clients=2)
    user1_client, user2_client = clients
    
    # Clear any existing messages
    user1_client.clear_received_messages()
    user2_client.clear_received_messages()
    
    # User 1 creates a comment thread
    cell_id = "cell-1"
    thread_id = str(uuid.uuid4())
    comment_id = str(uuid.uuid4())
    original_text = "This is the original comment text"
    
    await user1_client.send({
        "type": "comment_create",
        "cell_id": cell_id,
        "thread_id": thread_id,
        "comment_id": comment_id,
        "content": original_text,
        "timestamp": int(time.time() * 1000)
    })
    
    # Wait for the comment to be synchronized to user 2
    await user2_client.wait_for_message_containing(comment_id, timeout=TIMEOUT)
    
    # User 1 edits their comment
    edited_text = "This is the edited comment text"
    edit_timestamp = int(time.time() * 1000)
    
    await user1_client.send({
        "type": "comment_edit",
        "thread_id": thread_id,
        "comment_id": comment_id,
        "content": edited_text,
        "timestamp": edit_timestamp
    })
    
    # Wait for the edit to be synchronized to user 2
    edit_message = await user2_client.wait_for_message_containing("comment_edit", timeout=TIMEOUT)
    assert edit_message is not None, "Comment edit was not synchronized to user 2"
    
    # Verify the edit message
    try:
        data = json.loads(edit_message)
        assert data.get("type") == "comment_update", "Incorrect message type"
        assert data.get("thread_id") == thread_id, "Incorrect thread ID"
        assert data.get("comment_id") == comment_id, "Incorrect comment ID"
        assert data.get("content") == edited_text, "Incorrect edited content"
        assert data.get("edited") is True, "Comment should be marked as edited"
        assert data.get("edited_at") == edit_timestamp, "Incorrect edit timestamp"
    except json.JSONDecodeError:
        pytest.fail("Received message is not valid JSON")
    except KeyError as e:
        pytest.fail(f"Missing expected field in edit message: {e}")
    
    # User 1 deletes their comment
    await user1_client.send({
        "type": "comment_delete",
        "thread_id": thread_id,
        "comment_id": comment_id,
        "timestamp": int(time.time() * 1000)
    })
    
    # Wait for the deletion to be synchronized to user 2
    delete_message = await user2_client.wait_for_message_containing("comment_delete", timeout=TIMEOUT)
    assert delete_message is not None, "Comment deletion was not synchronized to user 2"
    
    # Verify the deletion message
    try:
        data = json.loads(delete_message)
        assert data.get("type") == "comment_delete", "Incorrect message type"
        assert data.get("thread_id") == thread_id, "Incorrect thread ID"
        assert data.get("comment_id") == comment_id, "Incorrect comment ID"
        assert data.get("deleted_by") == user1_client.user_id, "Incorrect deleter"
    except json.JSONDecodeError:
        pytest.fail("Received message is not valid JSON")
    except KeyError as e:
        pytest.fail(f"Missing expected field in deletion message: {e}")
    
    # Verify the comment is no longer in the thread
    await user2_client.send({
        "type": "get_thread",
        "thread_id": thread_id
    })
    
    # Wait for the thread data response
    thread_data_message = await user2_client.wait_for_message_containing("thread_data", timeout=TIMEOUT)
    assert thread_data_message is not None, "Failed to retrieve thread data"
    
    # Verify the comment is marked as deleted or removed from the thread
    try:
        data = json.loads(thread_data_message)
        comments = data.get("comments", [])
        
        # Either the comment should be gone, or it should be marked as deleted
        deleted_comment = None
        for comment in comments:
            if comment.get("comment_id") == comment_id:
                deleted_comment = comment
                break
                
        if deleted_comment is not None:
            # If the comment is still in the list, it should be marked as deleted
            assert deleted_comment.get("deleted") is True, "Comment should be marked as deleted"
        else:
            # If the comment is not in the list, that's also acceptable behavior
            pass
    except json.JSONDecodeError:
        pytest.fail("Received thread data is not valid JSON")
    except KeyError as e:
        pytest.fail(f"Error verifying deleted comment: {e}")
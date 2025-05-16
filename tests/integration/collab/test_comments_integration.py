# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import asyncio
import pytest
import json
import time
from typing import List, Dict, Any, Callable, Awaitable

# Skip tests if y_py is not available
pytest.importorskip("y_py")

from packages.notebook.src.collab.comments import CommentStatus


@pytest.mark.asyncio
async def test_comment_creation_and_synchronization(jp_serverapp, jp_ws_client):
    """
    Test that comments can be created and synchronized between clients.
    
    Verifies that when one user creates a comment, it appears for other users.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1", display_name="User One")
    client2 = await jp_ws_client(user_id="user2", display_name="User Two")
    
    # Both clients subscribe to the same document
    doc_id = "test-comments-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a cell
    cell_id = "cell1"
    cell_content = "# Test cell for comments"
    await client1.add_cell(doc_id, cell_id, cell_content, "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 creates a comment on the cell
    comment_content = "This is a test comment from User One"
    comment_id = await client1.add_comment(doc_id, cell_id, comment_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 2 can see the comment
    comments = await client2.get_comments(doc_id)
    
    assert len(comments) > 0, "No comments synchronized to client 2"
    
    # Find the comment by ID
    found_comment = None
    for comment in comments:
        if comment["id"] == comment_id:
            found_comment = comment
            break
    
    assert found_comment is not None, f"Comment {comment_id} not found in client 2's comments"
    assert found_comment["content"] == comment_content, "Comment content not synchronized correctly"
    assert found_comment["authorId"] == "user1", "Comment author not synchronized correctly"
    assert found_comment["authorName"] == "User One", "Comment author name not synchronized correctly"
    assert found_comment["cellId"] == cell_id, "Comment cell ID not synchronized correctly"


@pytest.mark.asyncio
async def test_comment_thread_replies(jp_serverapp, jp_ws_client):
    """
    Test that users can reply to comments and form threads.
    
    Verifies that comment threads with replies are properly synchronized between clients.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1", display_name="User One")
    client2 = await jp_ws_client(user_id="user2", display_name="User Two")
    
    # Both clients subscribe to the same document
    doc_id = "test-comment-replies-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a cell
    cell_id = "cell1"
    cell_content = "# Test cell for comment replies"
    await client1.add_cell(doc_id, cell_id, cell_content, "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 creates a comment on the cell
    root_comment_content = "This is the root comment from User One"
    root_comment_id = await client1.add_comment(doc_id, cell_id, root_comment_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 2 replies to the comment
    reply_content = "This is a reply from User Two"
    reply_id = await client2.add_comment_reply(doc_id, root_comment_id, reply_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds another reply
    reply2_content = "This is a second reply from User One"
    reply2_id = await client1.add_comment_reply(doc_id, root_comment_id, reply2_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify both clients can see the complete thread
    threads1 = await client1.get_comment_threads(doc_id)
    threads2 = await client2.get_comment_threads(doc_id)
    
    # Find the thread in client 1's view
    thread1 = None
    for thread in threads1:
        if thread["id"] == root_comment_id:
            thread1 = thread
            break
    
    # Find the thread in client 2's view
    thread2 = None
    for thread in threads2:
        if thread["id"] == root_comment_id:
            thread2 = thread
            break
    
    # Verify thread exists in both clients
    assert thread1 is not None, "Thread not found in client 1's view"
    assert thread2 is not None, "Thread not found in client 2's view"
    
    # Verify thread has the correct structure
    assert thread1["rootComment"]["id"] == root_comment_id, "Root comment ID mismatch in client 1"
    assert thread2["rootComment"]["id"] == root_comment_id, "Root comment ID mismatch in client 2"
    
    # Verify thread has the correct number of replies
    assert len(thread1["replies"]) == 2, "Incorrect number of replies in client 1"
    assert len(thread2["replies"]) == 2, "Incorrect number of replies in client 2"
    
    # Verify reply content is correct
    reply_contents1 = [reply["content"] for reply in thread1["replies"]]
    reply_contents2 = [reply["content"] for reply in thread2["replies"]]
    
    assert reply_content in reply_contents1, "First reply content missing in client 1"
    assert reply2_content in reply_contents1, "Second reply content missing in client 1"
    assert reply_content in reply_contents2, "First reply content missing in client 2"
    assert reply2_content in reply_contents2, "Second reply content missing in client 2"
    
    # Verify reply authors are correct
    for reply in thread1["replies"]:
        if reply["content"] == reply_content:
            assert reply["authorId"] == "user2", "First reply author incorrect in client 1"
        elif reply["content"] == reply2_content:
            assert reply["authorId"] == "user1", "Second reply author incorrect in client 1"
    
    for reply in thread2["replies"]:
        if reply["content"] == reply_content:
            assert reply["authorId"] == "user2", "First reply author incorrect in client 2"
        elif reply["content"] == reply2_content:
            assert reply["authorId"] == "user1", "Second reply author incorrect in client 2"


@pytest.mark.asyncio
async def test_comment_resolution_workflow(jp_serverapp, jp_ws_client):
    """
    Test the comment resolution workflow.
    
    Verifies that comments can be resolved and reopened, and that these status
    changes are synchronized between clients.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1", display_name="User One")
    client2 = await jp_ws_client(user_id="user2", display_name="User Two")
    
    # Both clients subscribe to the same document
    doc_id = "test-comment-resolution-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a cell
    cell_id = "cell1"
    cell_content = "# Test cell for comment resolution"
    await client1.add_cell(doc_id, cell_id, cell_content, "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 creates a comment on the cell
    comment_content = "This needs to be fixed"
    comment_id = await client1.add_comment(doc_id, cell_id, comment_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 2 replies to the comment
    reply_content = "I've fixed it"
    reply_id = await client2.add_comment_reply(doc_id, comment_id, reply_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 resolves the comment thread
    await client1.resolve_comment_thread(doc_id, comment_id)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify both clients see the thread as resolved
    threads1 = await client1.get_comment_threads(doc_id)
    threads2 = await client2.get_comment_threads(doc_id)
    
    # Find the thread in both clients
    thread1 = next((t for t in threads1 if t["id"] == comment_id), None)
    thread2 = next((t for t in threads2 if t["id"] == comment_id), None)
    
    assert thread1 is not None, "Thread not found in client 1's view"
    assert thread2 is not None, "Thread not found in client 2's view"
    
    # Verify thread is marked as resolved in both clients
    assert thread1["status"] == CommentStatus.Resolved, "Thread not marked as resolved in client 1"
    assert thread2["status"] == CommentStatus.Resolved, "Thread not marked as resolved in client 2"
    
    # Client 2 reopens the thread
    await client2.reopen_comment_thread(doc_id, comment_id)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify both clients see the thread as reopened
    threads1 = await client1.get_comment_threads(doc_id)
    threads2 = await client2.get_comment_threads(doc_id)
    
    # Find the thread in both clients
    thread1 = next((t for t in threads1 if t["id"] == comment_id), None)
    thread2 = next((t for t in threads2 if t["id"] == comment_id), None)
    
    assert thread1 is not None, "Thread not found in client 1's view after reopening"
    assert thread2 is not None, "Thread not found in client 2's view after reopening"
    
    # Verify thread is marked as active in both clients
    assert thread1["status"] == CommentStatus.Active, "Thread not marked as active in client 1"
    assert thread2["status"] == CommentStatus.Active, "Thread not marked as active in client 2"
    
    # Client 1 changes the status to a question
    await client1.update_comment_status(doc_id, comment_id, CommentStatus.Question)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify both clients see the thread as a question
    threads1 = await client1.get_comment_threads(doc_id)
    threads2 = await client2.get_comment_threads(doc_id)
    
    # Find the thread in both clients
    thread1 = next((t for t in threads1 if t["id"] == comment_id), None)
    thread2 = next((t for t in threads2 if t["id"] == comment_id), None)
    
    # Verify thread is marked as a question in both clients
    assert thread1["status"] == CommentStatus.Question, "Thread not marked as a question in client 1"
    assert thread2["status"] == CommentStatus.Question, "Thread not marked as a question in client 2"


@pytest.mark.asyncio
async def test_comment_notifications(jp_serverapp, jp_ws_client):
    """
    Test that comment notifications are delivered to relevant users.
    
    Verifies that users receive notifications for new comments, replies, and mentions.
    """
    # Create three clients connected to the same document
    client1 = await jp_ws_client(user_id="user1", display_name="User One")
    client2 = await jp_ws_client(user_id="user2", display_name="User Two")
    client3 = await jp_ws_client(user_id="user3", display_name="User Three")
    
    # All clients subscribe to the same document
    doc_id = "test-comment-notifications-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    await client3.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a cell
    cell_id = "cell1"
    cell_content = "# Test cell for comment notifications"
    await client1.add_cell(doc_id, cell_id, cell_content, "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Clear any existing notifications
    await client1.clear_notifications()
    await client2.clear_notifications()
    await client3.clear_notifications()
    
    # Client 1 creates a comment on the cell
    comment_content = "This is a comment from User One"
    comment_id = await client1.add_comment(doc_id, cell_id, comment_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 2 replies to the comment
    reply_content = "This is a reply from User Two"
    reply_id = await client2.add_comment_reply(doc_id, comment_id, reply_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 3 adds a reply with @mentions
    mention_reply_content = "@User One and @User Two, please check this"
    mention_reply_id = await client3.add_comment_reply(doc_id, comment_id, mention_reply_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 1 received notifications for the replies
    notifications1 = await client1.get_notifications()
    
    # Should have at least 2 notifications: one for client2's reply and one for the @mention
    assert len(notifications1) >= 2, "Client 1 did not receive expected notifications"
    
    # Check for reply notification
    reply_notification = None
    for notification in notifications1:
        if notification["commentId"] == reply_id and notification["type"] == "reply":
            reply_notification = notification
            break
    
    assert reply_notification is not None, "Client 1 did not receive notification for reply"
    
    # Check for mention notification
    mention_notification = None
    for notification in notifications1:
        if notification["commentId"] == mention_reply_id and notification["type"] == "mention":
            mention_notification = notification
            break
    
    assert mention_notification is not None, "Client 1 did not receive notification for @mention"
    
    # Verify client 2 received notification for the @mention
    notifications2 = await client2.get_notifications()
    
    mention_notification2 = None
    for notification in notifications2:
        if notification["commentId"] == mention_reply_id and notification["type"] == "mention":
            mention_notification2 = notification
            break
    
    assert mention_notification2 is not None, "Client 2 did not receive notification for @mention"
    
    # Client 1 marks a notification as read
    if reply_notification:
        await client1.mark_notification_read(reply_notification["commentId"])
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify the notification is marked as read
    notifications1_after = await client1.get_unread_notifications()
    
    # The reply notification should no longer be in the unread list
    reply_notification_after = None
    for notification in notifications1_after:
        if notification["commentId"] == reply_id and notification["type"] == "reply":
            reply_notification_after = notification
            break
    
    assert reply_notification_after is None, "Notification still marked as unread after being read"


@pytest.mark.asyncio
async def test_comment_persistence_across_sessions(jp_serverapp, jp_ws_client):
    """
    Test that comments persist across sessions.
    
    Verifies that comments are stored persistently and can be retrieved when
    reconnecting to a document.
    """
    # Create a client and add comments
    client1 = await jp_ws_client(user_id="user1", display_name="User One")
    
    # Subscribe to a document
    doc_id = "test-comment-persistence-doc"
    await client1.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Add a cell
    cell_id = "cell1"
    cell_content = "# Test cell for comment persistence"
    await client1.add_cell(doc_id, cell_id, cell_content, "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Add a comment
    comment_content = "This is a persistent comment"
    comment_id = await client1.add_comment(doc_id, cell_id, comment_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Disconnect client1
    await client1.disconnect()
    
    # Wait for disconnection to complete
    await asyncio.sleep(0.5)
    
    # Create a new client with the same user ID
    client1_reconnected = await jp_ws_client(user_id="user1", display_name="User One")
    
    # Subscribe to the same document
    await client1_reconnected.subscribe_document(doc_id)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify the comment is still there
    comments = await client1_reconnected.get_comments(doc_id)
    
    # Find the comment by ID
    found_comment = None
    for comment in comments:
        if comment["id"] == comment_id:
            found_comment = comment
            break
    
    assert found_comment is not None, "Comment not persisted across sessions"
    assert found_comment["content"] == comment_content, "Comment content changed after reconnection"
    
    # Create a completely new client
    client2 = await jp_ws_client(user_id="user2", display_name="User Two")
    
    # Subscribe to the same document
    await client2.subscribe_document(doc_id)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify the new client can see the comment
    comments2 = await client2.get_comments(doc_id)
    
    # Find the comment by ID
    found_comment2 = None
    for comment in comments2:
        if comment["id"] == comment_id:
            found_comment2 = comment
            break
    
    assert found_comment2 is not None, "New client cannot see persisted comment"
    assert found_comment2["content"] == comment_content, "Comment content incorrect for new client"


@pytest.mark.asyncio
async def test_comment_editing_and_deletion(jp_serverapp, jp_ws_client):
    """
    Test that comments can be edited and deleted.
    
    Verifies that comment edits and deletions are synchronized between clients.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1", display_name="User One")
    client2 = await jp_ws_client(user_id="user2", display_name="User Two")
    
    # Both clients subscribe to the same document
    doc_id = "test-comment-editing-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a cell
    cell_id = "cell1"
    cell_content = "# Test cell for comment editing"
    await client1.add_cell(doc_id, cell_id, cell_content, "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 creates a comment on the cell
    original_content = "This is the original comment"
    comment_id = await client1.add_comment(doc_id, cell_id, original_content)
    
    # Client 2 creates a comment on the cell
    client2_content = "This is a comment from client 2"
    client2_comment_id = await client2.add_comment(doc_id, cell_id, client2_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 edits their comment
    edited_content = "This is the edited comment"
    await client1.update_comment(doc_id, comment_id, edited_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 2 sees the edited comment
    comments = await client2.get_comments(doc_id)
    
    # Find the comment by ID
    found_comment = None
    for comment in comments:
        if comment["id"] == comment_id:
            found_comment = comment
            break
    
    assert found_comment is not None, "Edited comment not found in client 2's view"
    assert found_comment["content"] == edited_content, "Comment edit not synchronized correctly"
    
    # Client 2 tries to edit client 1's comment (should fail due to permissions)
    unauthorized_edit = "This edit should fail"
    edit_success = await client2.update_comment(doc_id, comment_id, unauthorized_edit)
    
    # This should return False or raise an exception
    assert not edit_success, "Client 2 was able to edit Client 1's comment"
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify the comment still has client 1's edit
    comments = await client1.get_comments(doc_id)
    found_comment = next((c for c in comments if c["id"] == comment_id), None)
    assert found_comment is not None, "Comment disappeared after failed edit attempt"
    assert found_comment["content"] == edited_content, "Comment content changed after failed edit attempt"
    
    # Client 2 deletes their own comment
    await client2.delete_comment(doc_id, client2_comment_id)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify the comment is deleted for both clients
    comments1 = await client1.get_comments(doc_id)
    comments2 = await client2.get_comments(doc_id)
    
    assert not any(c["id"] == client2_comment_id for c in comments1), "Deleted comment still visible to client 1"
    assert not any(c["id"] == client2_comment_id for c in comments2), "Deleted comment still visible to client 2"
    
    # Client 2 tries to delete client 1's comment (should fail due to permissions)
    delete_success = await client2.delete_comment(doc_id, comment_id)
    
    # This should return False or raise an exception
    assert not delete_success, "Client 2 was able to delete Client 1's comment"
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify client 1's comment still exists
    comments = await client1.get_comments(doc_id)
    assert any(c["id"] == comment_id for c in comments), "Comment incorrectly deleted after failed deletion attempt"


@pytest.mark.asyncio
async def test_multiple_comment_threads_per_cell(jp_serverapp, jp_ws_client):
    """
    Test that multiple comment threads can be created on a single cell.
    
    Verifies that multiple threads on the same cell are properly managed and synchronized.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1", display_name="User One")
    client2 = await jp_ws_client(user_id="user2", display_name="User Two")
    
    # Both clients subscribe to the same document
    doc_id = "test-multiple-threads-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds a cell
    cell_id = "cell1"
    cell_content = "# Test cell for multiple comment threads"
    await client1.add_cell(doc_id, cell_id, cell_content, "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 creates first comment thread
    thread1_content = "This is the first thread"
    thread1_id = await client1.add_comment(doc_id, cell_id, thread1_content)
    
    # Client 2 creates second comment thread
    thread2_content = "This is the second thread"
    thread2_id = await client2.add_comment(doc_id, cell_id, thread2_content)
    
    # Client 1 creates third comment thread
    thread3_content = "This is the third thread"
    thread3_id = await client1.add_comment(doc_id, cell_id, thread3_content)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify both clients can see all three threads
    threads1 = await client1.get_comment_threads(doc_id)
    threads2 = await client2.get_comment_threads(doc_id)
    
    # Filter threads for the specific cell
    cell_threads1 = [t for t in threads1 if t["cellId"] == cell_id]
    cell_threads2 = [t for t in threads2 if t["cellId"] == cell_id]
    
    # Verify both clients see the same number of threads
    assert len(cell_threads1) == 3, "Client 1 does not see all three threads"
    assert len(cell_threads2) == 3, "Client 2 does not see all three threads"
    
    # Verify thread IDs match
    thread_ids1 = [t["id"] for t in cell_threads1]
    thread_ids2 = [t["id"] for t in cell_threads2]
    
    assert thread1_id in thread_ids1, "Thread 1 missing from client 1's view"
    assert thread2_id in thread_ids1, "Thread 2 missing from client 1's view"
    assert thread3_id in thread_ids1, "Thread 3 missing from client 1's view"
    
    assert thread1_id in thread_ids2, "Thread 1 missing from client 2's view"
    assert thread2_id in thread_ids2, "Thread 2 missing from client 2's view"
    assert thread3_id in thread_ids2, "Thread 3 missing from client 2's view"
    
    # Client 1 resolves their threads
    await client1.resolve_comment_thread(doc_id, thread1_id)
    await client1.resolve_comment_thread(doc_id, thread3_id)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Verify resolution status is synchronized
    threads1 = await client1.get_comment_threads(doc_id)
    threads2 = await client2.get_comment_threads(doc_id)
    
    # Check thread 1 status
    thread1_client1 = next((t for t in threads1 if t["id"] == thread1_id), None)
    thread1_client2 = next((t for t in threads2 if t["id"] == thread1_id), None)
    
    assert thread1_client1["status"] == CommentStatus.Resolved, "Thread 1 not resolved in client 1's view"
    assert thread1_client2["status"] == CommentStatus.Resolved, "Thread 1 not resolved in client 2's view"
    
    # Check thread 2 status (should still be active)
    thread2_client1 = next((t for t in threads1 if t["id"] == thread2_id), None)
    thread2_client2 = next((t for t in threads2 if t["id"] == thread2_id), None)
    
    assert thread2_client1["status"] == CommentStatus.Active, "Thread 2 incorrectly resolved in client 1's view"
    assert thread2_client2["status"] == CommentStatus.Active, "Thread 2 incorrectly resolved in client 2's view"
    
    # Check thread 3 status
    thread3_client1 = next((t for t in threads1 if t["id"] == thread3_id), None)
    thread3_client2 = next((t for t in threads2 if t["id"] == thread3_id), None)
    
    assert thread3_client1["status"] == CommentStatus.Resolved, "Thread 3 not resolved in client 1's view"
    assert thread3_client2["status"] == CommentStatus.Resolved, "Thread 3 not resolved in client 2's view"


@pytest.mark.asyncio
async def test_comment_filtering(jp_serverapp, jp_ws_client):
    """
    Test that comments can be filtered by status, cell, and author.
    
    Verifies that the comment filtering functionality works correctly.
    """
    # Create two clients connected to the same document
    client1 = await jp_ws_client(user_id="user1", display_name="User One")
    client2 = await jp_ws_client(user_id="user2", display_name="User Two")
    
    # Both clients subscribe to the same document
    doc_id = "test-comment-filtering-doc"
    await client1.subscribe_document(doc_id)
    await client2.subscribe_document(doc_id)
    
    # Wait for initial synchronization
    await asyncio.sleep(0.5)
    
    # Client 1 adds two cells
    cell1_id = "cell1"
    cell2_id = "cell2"
    await client1.add_cell(doc_id, cell1_id, "# Cell 1", "markdown")
    await client1.add_cell(doc_id, cell2_id, "# Cell 2", "markdown")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Create various comments with different statuses, cells, and authors
    # Cell 1, User 1, Active
    comment1_id = await client1.add_comment(doc_id, cell1_id, "Comment 1 from User 1 on Cell 1")
    
    # Cell 1, User 2, Active
    comment2_id = await client2.add_comment(doc_id, cell1_id, "Comment 2 from User 2 on Cell 1")
    
    # Cell 2, User 1, Active
    comment3_id = await client1.add_comment(doc_id, cell2_id, "Comment 3 from User 1 on Cell 2")
    
    # Cell 2, User 2, Active
    comment4_id = await client2.add_comment(doc_id, cell2_id, "Comment 4 from User 2 on Cell 2")
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Resolve some comments
    await client1.resolve_comment_thread(doc_id, comment1_id)
    await client2.resolve_comment_thread(doc_id, comment4_id)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Mark one comment as a question
    await client1.update_comment_status(doc_id, comment3_id, CommentStatus.Question)
    
    # Wait for synchronization
    await asyncio.sleep(0.5)
    
    # Test filtering by cell
    cell1_threads = await client1.get_cell_comment_threads(doc_id, cell1_id)
    assert len(cell1_threads) == 2, "Incorrect number of threads for cell 1"
    cell1_thread_ids = [t["id"] for t in cell1_threads]
    assert comment1_id in cell1_thread_ids, "Comment 1 missing from cell 1 threads"
    assert comment2_id in cell1_thread_ids, "Comment 2 missing from cell 1 threads"
    
    cell2_threads = await client1.get_cell_comment_threads(doc_id, cell2_id)
    assert len(cell2_threads) == 2, "Incorrect number of threads for cell 2"
    cell2_thread_ids = [t["id"] for t in cell2_threads]
    assert comment3_id in cell2_thread_ids, "Comment 3 missing from cell 2 threads"
    assert comment4_id in cell2_thread_ids, "Comment 4 missing from cell 2 threads"
    
    # Test filtering by status
    active_threads = await client1.get_comment_threads_by_status(doc_id, CommentStatus.Active)
    active_thread_ids = [t["id"] for t in active_threads]
    assert comment2_id in active_thread_ids, "Comment 2 missing from active threads"
    assert comment1_id not in active_thread_ids, "Resolved comment 1 incorrectly in active threads"
    
    resolved_threads = await client1.get_comment_threads_by_status(doc_id, CommentStatus.Resolved)
    resolved_thread_ids = [t["id"] for t in resolved_threads]
    assert comment1_id in resolved_thread_ids, "Comment 1 missing from resolved threads"
    assert comment4_id in resolved_thread_ids, "Comment 4 missing from resolved threads"
    
    question_threads = await client1.get_comment_threads_by_status(doc_id, CommentStatus.Question)
    question_thread_ids = [t["id"] for t in question_threads]
    assert comment3_id in question_thread_ids, "Comment 3 missing from question threads"
    
    # Test filtering by author
    user1_threads = await client1.get_comment_threads_by_author(doc_id, "user1")
    user1_thread_ids = [t["id"] for t in user1_threads]
    assert comment1_id in user1_thread_ids, "Comment 1 missing from user1 threads"
    assert comment3_id in user1_thread_ids, "Comment 3 missing from user1 threads"
    assert comment2_id not in user1_thread_ids, "Comment 2 incorrectly in user1 threads"
    
    user2_threads = await client1.get_comment_threads_by_author(doc_id, "user2")
    user2_thread_ids = [t["id"] for t in user2_threads]
    assert comment2_id in user2_thread_ids, "Comment 2 missing from user2 threads"
    assert comment4_id in user2_thread_ids, "Comment 4 missing from user2 threads"
    assert comment1_id not in user2_thread_ids, "Comment 1 incorrectly in user2 threads"
    
    # Test combined filtering (cell + status)
    cell1_resolved_threads = await client1.get_cell_comment_threads_by_status(
        doc_id, cell1_id, CommentStatus.Resolved
    )
    assert len(cell1_resolved_threads) == 1, "Incorrect number of resolved threads for cell 1"
    assert cell1_resolved_threads[0]["id"] == comment1_id, "Wrong thread in cell1 resolved threads"
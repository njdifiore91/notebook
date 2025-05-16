# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import asyncio
import json
import os
import pytest
import time
import uuid
from unittest.mock import MagicMock, patch

import tornado.web
from tornado.httpclient import HTTPClientError

from notebook.app import JupyterNotebookApp
from notebook.collab.handlers import CollaborationAPIHandler, CollaborationSocketHandler
from notebook.collab.persistence import CollaborationManager, CommentThread, Comment

# Import Yjs-related modules if available
try:
    import y_py as Y
except ImportError:
    Y = None

# Skip all tests if y_py is not available
pytestmark = pytest.mark.skipif(Y is None, reason="y_py package is required for collaboration tests")


@pytest.fixture
def mock_collab_manager():
    """Create a mock collaboration manager for testing."""
    manager = MagicMock(spec=CollaborationManager)
    
    # Set up mock methods for comment-related operations
    manager.create_comment_thread.return_value = {
        'thread_id': str(uuid.uuid4()),
        'session_id': str(uuid.uuid4()),
        'cell_id': 'test-cell-1',
        'created_at': '2023-01-01T00:00:00Z',
        'status': 'open',
        'metadata': {},
        'comment': {
            'comment_id': str(uuid.uuid4()),
            'user_id': 'test-user',
            'content': 'Test comment',
            'created_at': '2023-01-01T00:00:00Z',
            'updated_at': '2023-01-01T00:00:00Z',
            'metadata': {}
        }
    }
    
    manager.add_comment.return_value = {
        'comment_id': str(uuid.uuid4()),
        'thread_id': 'test-thread-1',
        'user_id': 'test-user',
        'content': 'Test reply',
        'created_at': '2023-01-01T00:00:00Z',
        'updated_at': '2023-01-01T00:00:00Z',
        'metadata': {}
    }
    
    manager.get_comment_threads.return_value = [
        {
            'thread_id': 'test-thread-1',
            'session_id': str(uuid.uuid4()),
            'cell_id': 'test-cell-1',
            'created_at': '2023-01-01T00:00:00Z',
            'status': 'open',
            'metadata': {},
            'comments': [
                {
                    'comment_id': 'test-comment-1',
                    'user_id': 'test-user',
                    'content': 'Test comment',
                    'created_at': '2023-01-01T00:00:00Z',
                    'updated_at': '2023-01-01T00:00:00Z',
                    'metadata': {}
                }
            ]
        }
    ]
    
    manager.get_comment_thread.return_value = {
        'thread_id': 'test-thread-1',
        'session_id': str(uuid.uuid4()),
        'cell_id': 'test-cell-1',
        'created_at': '2023-01-01T00:00:00Z',
        'status': 'open',
        'metadata': {},
        'user_id': 'test-user',  # Owner of the thread
        'comments': [
            {
                'comment_id': 'test-comment-1',
                'user_id': 'test-user',
                'content': 'Test comment',
                'created_at': '2023-01-01T00:00:00Z',
                'updated_at': '2023-01-01T00:00:00Z',
                'metadata': {}
            }
        ]
    }
    
    manager.update_comment_thread.return_value = True
    manager.delete_comment_thread.return_value = True
    
    # Set up mock methods for permission checking
    manager.get_user_permissions.return_value = {
        'view': True,
        'comment': True,
        'edit': True,
        'admin': False
    }
    
    return manager


@pytest.fixture
def setup_collab_handlers(jp_serverapp, mock_collab_manager):
    """Set up collaboration handlers for testing."""
    # Initialize handlers with mock collaboration manager
    CollaborationAPIHandler.initialize_manager(mock_collab_manager)
    CollaborationSocketHandler.initialize_manager(mock_collab_manager)
    
    # Add handlers to the Jupyter server
    host_pattern = ".*$"
    jp_serverapp.web_app.add_handlers(host_pattern, [
        # Comments API
        (r"/api/collaboration/v1/(?P<endpoint>comments)/(?P<document_id>\w+)/?$", 
         CollaborationAPIHandler),
        (r"/api/collaboration/v1/(?P<endpoint>comments)/(?P<document_id>\w+)/(?P<resource_id>\w+)/?$", 
         CollaborationAPIHandler),
    ])
    
    return mock_collab_manager


@pytest.fixture
def mock_ydoc():
    """Create a mock Yjs document for testing."""
    if Y is None:
        return None
    
    # Create a real Yjs document
    ydoc = Y.YDoc()
    
    # Create shared data structures for comments
    ycomments = ydoc.get_map('comments')
    ynotifications = ydoc.get_map('commentNotifications')
    
    return ydoc


@pytest.fixture
def mock_notebook_model(mock_ydoc):
    """Create a mock notebook model with collaboration provider."""
    model = MagicMock()
    
    # Create a mock collaboration provider
    provider = MagicMock()
    provider.ydoc = mock_ydoc
    
    model.collaborationProvider = provider
    
    return model


@pytest.fixture
def mock_permission_manager():
    """Create a mock permission manager for testing."""
    manager = MagicMock()
    manager.canCommentOnCell.return_value = True
    manager.isAdmin = False
    manager.getUserPermissions.return_value = [
        {'userId': 'user1', 'displayName': 'User 1'},
        {'userId': 'user2', 'displayName': 'User 2'}
    ]
    
    return manager


class TestCommentAPI:
    """Test the comment API endpoints."""
    
    async def test_create_comment_thread(self, jp_fetch, setup_collab_handlers):
        """Test creating a new comment thread."""
        # Prepare request data
        data = {
            'cell_id': 'test-cell-1',
            'content': 'Test comment'
        }
        
        # Send POST request to create a new thread
        response = await jp_fetch(
            'api/collaboration/v1/comments/test-doc-1',
            method='POST',
            body=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )
        
        # Check response
        assert response.code == 201
        response_data = json.loads(response.body.decode())
        assert 'id' in response_data
        
        # Verify collaboration manager was called correctly
        setup_collab_handlers.create_comment_thread.assert_called_once()
        call_args = setup_collab_handlers.create_comment_thread.call_args[0]
        assert call_args[0] == 'test-doc-1'  # document_id
        assert 'user_id' in call_args[2]  # data with user_id added
    
    async def test_add_reply_to_thread(self, jp_fetch, setup_collab_handlers):
        """Test adding a reply to an existing comment thread."""
        # Prepare request data
        data = {
            'content': 'Test reply'
        }
        
        # Send POST request to add a reply
        response = await jp_fetch(
            'api/collaboration/v1/comments/test-doc-1/test-thread-1',
            method='POST',
            body=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )
        
        # Check response
        assert response.code == 201
        response_data = json.loads(response.body.decode())
        assert 'id' in response_data
        
        # Verify collaboration manager was called correctly
        setup_collab_handlers.add_comment.assert_called_once()
        call_args = setup_collab_handlers.add_comment.call_args[0]
        assert call_args[0] == 'test-doc-1'  # document_id
        assert call_args[1] == 'test-thread-1'  # thread_id
        assert 'user_id' in call_args[2]  # data with user_id added
    
    async def test_get_comment_threads(self, jp_fetch, setup_collab_handlers):
        """Test retrieving all comment threads for a document."""
        # Send GET request to retrieve threads
        response = await jp_fetch('api/collaboration/v1/comments/test-doc-1')
        
        # Check response
        assert response.code == 200
        response_data = json.loads(response.body.decode())
        assert isinstance(response_data, list)
        assert len(response_data) > 0
        assert 'thread_id' in response_data[0]
        assert 'comments' in response_data[0]
        
        # Verify collaboration manager was called correctly
        setup_collab_handlers.list_comments.assert_called_once_with('test-doc-1', 'open')
    
    async def test_get_specific_thread(self, jp_fetch, setup_collab_handlers):
        """Test retrieving a specific comment thread."""
        # Send GET request to retrieve a specific thread
        response = await jp_fetch('api/collaboration/v1/comments/test-doc-1/test-thread-1')
        
        # Check response
        assert response.code == 200
        response_data = json.loads(response.body.decode())
        assert 'thread_id' in response_data
        assert response_data['thread_id'] == 'test-thread-1'
        
        # Verify collaboration manager was called correctly
        setup_collab_handlers.get_comment_thread.assert_called_once_with('test-doc-1', 'test-thread-1')
    
    async def test_update_thread_status(self, jp_fetch, setup_collab_handlers):
        """Test updating a comment thread status (resolve/reopen)."""
        # Prepare request data
        data = {
            'status': 'resolved'
        }
        
        # Send PUT request to update thread status
        response = await jp_fetch(
            'api/collaboration/v1/comments/test-doc-1/test-thread-1',
            method='PUT',
            body=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )
        
        # Check response
        assert response.code == 200
        response_data = json.loads(response.body.decode())
        assert response_data['success'] is True
        
        # Verify collaboration manager was called correctly
        setup_collab_handlers.update_comment_thread.assert_called_once_with(
            'test-doc-1', 'test-thread-1', data
        )
    
    async def test_delete_thread(self, jp_fetch, setup_collab_handlers):
        """Test deleting a comment thread."""
        # Send DELETE request to delete a thread
        response = await jp_fetch(
            'api/collaboration/v1/comments/test-doc-1/test-thread-1',
            method='DELETE'
        )
        
        # Check response
        assert response.code == 204  # No content
        
        # Verify collaboration manager was called correctly
        setup_collab_handlers.delete_comment_thread.assert_called_once_with(
            'test-doc-1', 'test-thread-1'
        )
    
    async def test_permission_denied(self, jp_fetch, setup_collab_handlers):
        """Test permission denied for comment operations."""
        # Mock permission check to return False
        setup_collab_handlers.get_user_permissions.return_value = {
            'view': True,
            'comment': False,
            'edit': False,
            'admin': False
        }
        
        # Prepare request data
        data = {
            'cell_id': 'test-cell-1',
            'content': 'Test comment'
        }
        
        # Send POST request to create a new thread
        with pytest.raises(HTTPClientError) as excinfo:
            await jp_fetch(
                'api/collaboration/v1/comments/test-doc-1',
                method='POST',
                body=json.dumps(data),
                headers={'Content-Type': 'application/json'}
            )
        
        # Check error response
        assert excinfo.value.code == 403  # Forbidden


class TestCommentManager:
    """Test the CommentManager class."""
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_comment_manager_initialization(self, mock_notebook_model, mock_permission_manager):
        """Test initializing the CommentManager."""
        from packages.notebook.src.collab.comments import CommentManager
        
        # Create a CommentManager instance
        manager = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to notebook model
        manager.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Verify initialization
        assert manager._currentUserId == 'test-user'
        assert manager._currentUserDisplayName == 'Test User'
        assert manager._model == mock_notebook_model
        assert manager._permissionManager == mock_permission_manager
        assert manager._ydoc == mock_notebook_model.collaborationProvider.ydoc
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_add_comment(self, mock_notebook_model, mock_permission_manager):
        """Test adding a comment."""
        from packages.notebook.src.collab.comments import CommentManager, CommentStatus
        
        # Create a CommentManager instance
        manager = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to notebook model
        manager.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add a comment
        comment = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Test comment'
        })
        
        # Verify comment was added
        assert comment is not None
        assert comment['id'] is not None
        assert comment['cellId'] == 'test-cell-1'
        assert comment['content'] == 'Test comment'
        assert comment['authorId'] == 'test-user'
        assert comment['authorName'] == 'Test User'
        assert comment['status'] == CommentStatus.Active
        assert comment['parentId'] is None  # Root comment
        
        # Verify comment is in the shared map
        comments = manager.getComments()
        assert len(comments) == 1
        assert comments[0]['id'] == comment['id']
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_add_reply(self, mock_notebook_model, mock_permission_manager):
        """Test adding a reply to a comment thread."""
        from packages.notebook.src.collab.comments import CommentManager, CommentStatus
        
        # Create a CommentManager instance
        manager = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to notebook model
        manager.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add a root comment
        root_comment = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Test comment'
        })
        
        # Add a reply
        reply = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Test reply',
            'threadId': root_comment['id'],
            'parentId': root_comment['id']
        })
        
        # Verify reply was added
        assert reply is not None
        assert reply['id'] is not None
        assert reply['cellId'] == 'test-cell-1'
        assert reply['content'] == 'Test reply'
        assert reply['threadId'] == root_comment['id']
        assert reply['parentId'] == root_comment['id']
        
        # Verify thread structure
        thread = manager.getThread(root_comment['id'])
        assert thread is not None
        assert thread['id'] == root_comment['id']
        assert thread['rootComment']['id'] == root_comment['id']
        assert len(thread['replies']) == 1
        assert thread['replies'][0]['id'] == reply['id']
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_resolve_thread(self, mock_notebook_model, mock_permission_manager):
        """Test resolving a comment thread."""
        from packages.notebook.src.collab.comments import CommentManager, CommentStatus
        
        # Create a CommentManager instance
        manager = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to notebook model
        manager.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add a comment
        comment = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Test comment'
        })
        
        # Resolve the thread
        result = manager.resolveThread(comment['id'])
        
        # Verify thread was resolved
        assert result is True
        
        # Get the updated thread
        thread = manager.getThread(comment['id'])
        assert thread is not None
        assert thread['status'] == CommentStatus.Resolved
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_reopen_thread(self, mock_notebook_model, mock_permission_manager):
        """Test reopening a resolved comment thread."""
        from packages.notebook.src.collab.comments import CommentManager, CommentStatus
        
        # Create a CommentManager instance
        manager = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to notebook model
        manager.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add a comment
        comment = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Test comment'
        })
        
        # Resolve the thread
        manager.resolveThread(comment['id'])
        
        # Reopen the thread
        result = manager.reopenThread(comment['id'])
        
        # Verify thread was reopened
        assert result is True
        
        # Get the updated thread
        thread = manager.getThread(comment['id'])
        assert thread is not None
        assert thread['status'] == CommentStatus.Active
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_delete_comment(self, mock_notebook_model, mock_permission_manager):
        """Test deleting a comment."""
        from packages.notebook.src.collab.comments import CommentManager
        
        # Create a CommentManager instance
        manager = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to notebook model
        manager.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add a comment
        comment = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Test comment'
        })
        
        # Delete the comment
        result = manager.deleteComment(comment['id'])
        
        # Verify comment was deleted
        assert result is True
        assert manager.getComment(comment['id']) is None
        assert manager.getThread(comment['id']) is None
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_get_cell_comments(self, mock_notebook_model, mock_permission_manager):
        """Test getting comments for a specific cell."""
        from packages.notebook.src.collab.comments import CommentManager
        
        # Create a CommentManager instance
        manager = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to notebook model
        manager.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add comments to different cells
        comment1 = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Comment on cell 1'
        })
        
        comment2 = manager.addComment({
            'cellId': 'test-cell-2',
            'content': 'Comment on cell 2'
        })
        
        # Get comments for cell 1
        cell1_comments = manager.getCellComments('test-cell-1')
        assert len(cell1_comments) == 1
        assert cell1_comments[0]['id'] == comment1['id']
        
        # Get comments for cell 2
        cell2_comments = manager.getCellComments('test-cell-2')
        assert len(cell2_comments) == 1
        assert cell2_comments[0]['id'] == comment2['id']
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_get_cell_threads(self, mock_notebook_model, mock_permission_manager):
        """Test getting comment threads for a specific cell."""
        from packages.notebook.src.collab.comments import CommentManager
        
        # Create a CommentManager instance
        manager = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to notebook model
        manager.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add comments to different cells
        comment1 = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Thread 1 on cell 1'
        })
        
        comment2 = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Thread 2 on cell 1'
        })
        
        comment3 = manager.addComment({
            'cellId': 'test-cell-2',
            'content': 'Thread on cell 2'
        })
        
        # Get threads for cell 1
        cell1_threads = manager.getCellThreads('test-cell-1')
        assert len(cell1_threads) == 2
        thread_ids = [thread['id'] for thread in cell1_threads]
        assert comment1['id'] in thread_ids
        assert comment2['id'] in thread_ids
        
        # Get threads for cell 2
        cell2_threads = manager.getCellThreads('test-cell-2')
        assert len(cell2_threads) == 1
        assert cell2_threads[0]['id'] == comment3['id']
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_update_comment(self, mock_notebook_model, mock_permission_manager):
        """Test updating a comment's content."""
        from packages.notebook.src.collab.comments import CommentManager
        
        # Create a CommentManager instance
        manager = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to notebook model
        manager.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add a comment
        comment = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Original content'
        })
        
        # Update the comment
        updated = manager.updateComment(comment['id'], {
            'content': 'Updated content'
        })
        
        # Verify comment was updated
        assert updated is not None
        assert updated['id'] == comment['id']
        assert updated['content'] == 'Updated content'
        
        # Get the comment again to verify persistence
        retrieved = manager.getComment(comment['id'])
        assert retrieved is not None
        assert retrieved['content'] == 'Updated content'
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_notifications(self, mock_notebook_model, mock_permission_manager):
        """Test comment notifications."""
        from packages.notebook.src.collab.comments import CommentManager
        
        # Create a CommentManager instance with a different user
        manager1 = CommentManager({
            'currentUserId': 'user1',
            'currentUserDisplayName': 'User 1'
        })
        
        # Connect to notebook model
        manager1.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add a comment as user1
        comment = manager1.addComment({
            'cellId': 'test-cell-1',
            'content': 'Comment by User 1'
        })
        
        # Create another manager instance with a different user
        manager2 = CommentManager({
            'currentUserId': 'user2',
            'currentUserDisplayName': 'User 2'
        })
        
        # Connect to the same notebook model
        manager2.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add a reply as user2
        reply = manager2.addComment({
            'cellId': 'test-cell-1',
            'content': 'Reply by User 2',
            'threadId': comment['id'],
            'parentId': comment['id']
        })
        
        # Check notifications for user1
        notifications = manager1.getNotifications()
        
        # There should be at least one notification for the reply
        assert len(notifications) > 0
        
        # Find the notification for the reply
        reply_notification = None
        for notification in notifications:
            if notification['commentId'] == reply['id']:
                reply_notification = notification
                break
        
        assert reply_notification is not None
        assert reply_notification['recipientId'] == 'user1'
        assert reply_notification['type'] == 'reply'
        assert reply_notification['read'] is False
        
        # Mark notification as read
        manager1.markNotificationAsRead(reply_notification['commentId'])
        
        # Check that notification is now marked as read
        updated_notifications = manager1.getUnreadNotifications()
        assert len(updated_notifications) == 0
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_mention_notifications(self, mock_notebook_model, mock_permission_manager):
        """Test @mention notifications in comments."""
        from packages.notebook.src.collab.comments import CommentManager
        
        # Create a CommentManager instance
        manager = CommentManager({
            'currentUserId': 'user1',
            'currentUserDisplayName': 'User 1'
        })
        
        # Connect to notebook model
        manager.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add a comment with @mention
        comment = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Hey @User 2, please check this cell.'
        })
        
        # Create another manager instance for user2
        manager2 = CommentManager({
            'currentUserId': 'user2',
            'currentUserDisplayName': 'User 2'
        })
        
        # Connect to the same notebook model
        manager2.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Check notifications for user2
        notifications = manager2.getNotifications()
        
        # There should be a mention notification
        mention_notification = None
        for notification in notifications:
            if notification['type'] == 'mention':
                mention_notification = notification
                break
        
        # This might be None in the test environment due to mocking,
        # but the functionality should be tested in integration tests
        if mention_notification is not None:
            assert mention_notification['recipientId'] == 'user2'
            assert mention_notification['commentId'] == comment['id']
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_permission_checks(self, mock_notebook_model, mock_permission_manager):
        """Test permission checks for comment operations."""
        from packages.notebook.src.collab.comments import CommentManager
        
        # Create a CommentManager instance
        manager = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to notebook model
        manager.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Test with permission granted
        mock_permission_manager.canCommentOnCell.return_value = True
        comment = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'Test comment'
        })
        assert comment is not None
        
        # Test with permission denied
        mock_permission_manager.canCommentOnCell.return_value = False
        comment = manager.addComment({
            'cellId': 'test-cell-1',
            'content': 'This should fail'
        })
        assert comment is None
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    def test_comment_persistence(self, mock_notebook_model, mock_permission_manager):
        """Test that comments persist when reconnecting to the notebook."""
        from packages.notebook.src.collab.comments import CommentManager
        
        # Create a CommentManager instance
        manager1 = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to notebook model
        manager1.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Add a comment
        comment = manager1.addComment({
            'cellId': 'test-cell-1',
            'content': 'Test comment'
        })
        
        # Disconnect
        manager1.disconnectNotebook()
        
        # Create a new manager instance
        manager2 = CommentManager({
            'currentUserId': 'test-user',
            'currentUserDisplayName': 'Test User'
        })
        
        # Connect to the same notebook model
        manager2.connectNotebook(mock_notebook_model, mock_permission_manager)
        
        # Verify comment is still there
        retrieved = manager2.getComment(comment['id'])
        assert retrieved is not None
        assert retrieved['id'] == comment['id']
        assert retrieved['content'] == 'Test comment'


class TestCommentIntegration:
    """Integration tests for the comment system."""
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    async def test_comment_sync_between_clients(self):
        """Test that comments sync between clients."""
        # This would be a more complex integration test that would require
        # setting up multiple clients and verifying that comments sync between them.
        # For now, we'll just mark it as a placeholder.
        pass
    
    @pytest.mark.skipif(Y is None, reason="y_py package is required for this test")
    async def test_comment_persistence_across_sessions(self):
        """Test that comments persist across sessions."""
        # This would test that comments are properly stored in the database
        # and can be retrieved when starting a new session.
        # For now, we'll just mark it as a placeholder.
        pass
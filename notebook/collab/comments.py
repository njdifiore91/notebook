"""Comment and review system for collaborative notebooks.

This module implements the server-side component of the comment and review system,
managing the creation, storage, and synchronization of comments attached to specific
notebook cells. It handles comment threads, notifications, and resolution status tracking.
"""

from __future__ import annotations

import json
import logging
import typing as t
from datetime import datetime
from uuid import uuid4

from jupyter_server.base.handlers import JupyterHandler
from tornado import web, websocket
from traitlets.config import Configurable
from traitlets import Instance, Dict, Bool, Int, default

from notebook.collab.permissions import (
    NotebookPermissionManager, PermissionAction, collaborative_authorized
)

# Type definitions
DocumentId = str  # Unique identifier for a document
CellId = str  # Unique identifier for a cell
ThreadId = str  # Unique identifier for a comment thread
CommentId = str  # Unique identifier for a comment
UserId = str  # Unique identifier for a user
ClientId = str  # Unique identifier for a client

# Comment thread status options
class ThreadStatus:
    """Status options for comment threads."""
    OPEN = "open"  # Thread is active and unresolved
    RESOLVED = "resolved"  # Thread has been marked as resolved
    ARCHIVED = "archived"  # Thread has been archived (hidden but preserved)


class CommentManager(Configurable):
    """Manages comments and review threads for collaborative notebooks.
    
    This class provides methods for creating, retrieving, updating, and resolving
    comment threads attached to specific notebook cells. It handles persistence,
    notifications, and access control for the comment system.
    """
    
    # Configuration parameters
    persistence_manager = Instance(
        'notebook.collab.persistence.PersistenceManager',
        allow_none=True,
        help="The persistence manager for storing comments"
    ).tag(config=True)
    
    permission_manager = Instance(
        'notebook.collab.permissions.NotebookPermissionManager',
        allow_none=True,
        help="The permission manager for checking comment permissions"
    ).tag(config=True)
    
    enable_notifications = Bool(
        default_value=True,
        help="Whether to enable notifications for new comments"
    ).tag(config=True)
    
    notification_debounce_ms = Int(
        default_value=2000,  # 2 seconds
        help="Debounce time in milliseconds for batching notifications"
    ).tag(config=True)
    
    # In-memory cache of active comment threads
    _comment_cache = Dict(help="Cache of active comment threads").tag(config=False)
    
    def __init__(self, **kwargs):
        """Initialize the comment manager.
        
        Args:
            **kwargs: Configuration parameters
        """
        super().__init__(**kwargs)
        self.logger = logging.getLogger(__name__)
        self._comment_cache = {}
        self._notification_queue = {}
        
    def create_thread(self, session_id: str, cell_id: CellId, user_id: UserId, 
                     content: str, metadata: t.Optional[t.Dict[str, t.Any]] = None) -> t.Dict[str, t.Any]:
        """Create a new comment thread with an initial comment.
        
        Args:
            session_id: The collaboration session ID
            cell_id: The cell ID to attach the comment to
            user_id: The user creating the comment
            content: The comment content
            metadata: Additional metadata for the thread (e.g., selection range)
            
        Returns:
            A dictionary containing the thread and comment information
            
        Raises:
            ValueError: If required parameters are missing
            PermissionError: If the user doesn't have permission to comment
        """
        if not session_id or not cell_id or not user_id or not content:
            raise ValueError("Missing required parameters for creating a comment thread")
        
        # Check permissions if permission manager is available
        if self.permission_manager:
            user_identity = {"name": user_id}
            if not self.permission_manager.has_cell_permission(
                session_id, cell_id, user_identity, PermissionAction.COMMENT_CELL
            ):
                raise PermissionError(f"User {user_id} does not have permission to comment on cell {cell_id}")
        
        # Create thread with persistence manager
        if not self.persistence_manager:
            self.logger.warning("No persistence manager available for comment storage")
            # Create in-memory thread
            thread_id = str(uuid4())
            comment_id = str(uuid4())
            timestamp = datetime.utcnow().isoformat()
            
            thread_data = {
                'thread_id': thread_id,
                'session_id': session_id,
                'cell_id': cell_id,
                'created_at': timestamp,
                'status': ThreadStatus.OPEN,
                'metadata': metadata or {},
                'comments': [{
                    'comment_id': comment_id,
                    'user_id': user_id,
                    'content': content,
                    'created_at': timestamp,
                    'updated_at': timestamp,
                    'metadata': {}
                }]
            }
            
            # Cache the thread
            if session_id not in self._comment_cache:
                self._comment_cache[session_id] = {}
            if cell_id not in self._comment_cache[session_id]:
                self._comment_cache[session_id][cell_id] = {}
            self._comment_cache[session_id][cell_id][thread_id] = thread_data
            
            return thread_data
        else:
            # Create thread with persistence manager
            thread_data = self.persistence_manager.create_comment_thread(
                session_id, cell_id, user_id, content, metadata
            )
            
            # Queue notification
            self._queue_notification(session_id, 'thread_created', thread_data)
            
            return thread_data
    
    def add_comment(self, thread_id: ThreadId, user_id: UserId, content: str, 
                   metadata: t.Optional[t.Dict[str, t.Any]] = None) -> t.Dict[str, t.Any]:
        """Add a comment to an existing thread.
        
        Args:
            thread_id: The thread ID to add the comment to
            user_id: The user creating the comment
            content: The comment content
            metadata: Additional metadata for the comment
            
        Returns:
            A dictionary containing the comment information
            
        Raises:
            ValueError: If required parameters are missing
            PermissionError: If the user doesn't have permission to comment
            KeyError: If the thread doesn't exist
        """
        if not thread_id or not user_id or not content:
            raise ValueError("Missing required parameters for adding a comment")
        
        # Get thread info to check permissions
        thread_info = self.get_thread(thread_id)
        if not thread_info:
            raise KeyError(f"Thread {thread_id} not found")
        
        session_id = thread_info['session_id']
        cell_id = thread_info['cell_id']
        
        # Check permissions if permission manager is available
        if self.permission_manager:
            user_identity = {"name": user_id}
            if not self.permission_manager.has_cell_permission(
                session_id, cell_id, user_identity, PermissionAction.COMMENT_CELL
            ):
                raise PermissionError(f"User {user_id} does not have permission to comment on cell {cell_id}")
        
        # Add comment with persistence manager
        if not self.persistence_manager:
            self.logger.warning("No persistence manager available for comment storage")
            # Add in-memory comment
            comment_id = str(uuid4())
            timestamp = datetime.utcnow().isoformat()
            
            comment_data = {
                'comment_id': comment_id,
                'thread_id': thread_id,
                'user_id': user_id,
                'content': content,
                'created_at': timestamp,
                'updated_at': timestamp,
                'metadata': metadata or {}
            }
            
            # Find thread in cache
            for session_cache in self._comment_cache.values():
                for cell_cache in session_cache.values():
                    if thread_id in cell_cache:
                        # Add comment to thread
                        cell_cache[thread_id]['comments'].append(comment_data)
                        # Reopen thread if it was resolved
                        if cell_cache[thread_id]['status'] == ThreadStatus.RESOLVED:
                            cell_cache[thread_id]['status'] = ThreadStatus.OPEN
                        return comment_data
            
            raise KeyError(f"Thread {thread_id} not found in cache")
        else:
            # Add comment with persistence manager
            comment_data = self.persistence_manager.add_comment(
                thread_id, user_id, content, metadata
            )
            
            if not comment_data:
                raise KeyError(f"Thread {thread_id} not found in persistence manager")
            
            # Queue notification
            notification_data = {
                'thread_id': thread_id,
                'comment': comment_data,
                'session_id': session_id,
                'cell_id': cell_id
            }
            self._queue_notification(session_id, 'comment_added', notification_data)
            
            return comment_data
    
    def get_thread(self, thread_id: ThreadId) -> t.Optional[t.Dict[str, t.Any]]:
        """Get a comment thread by ID.
        
        Args:
            thread_id: The thread ID to retrieve
            
        Returns:
            A dictionary containing the thread information, or None if not found
        """
        # Try to find in cache first
        for session_cache in self._comment_cache.values():
            for cell_cache in session_cache.values():
                if thread_id in cell_cache:
                    return cell_cache[thread_id]
        
        # If not in cache and persistence manager is available, try there
        if self.persistence_manager:
            # We need to find the session ID for this thread
            # This is a limitation of the current API design
            # In a real implementation, we would have a direct lookup method
            # For now, we'll query all sessions and look for this thread
            
            # This is inefficient but works for demonstration purposes
            # In a real implementation, we would have a better way to look up threads by ID
            sessions = self.persistence_manager.get_session()
            try:
                # Use SQLAlchemy directly to find the thread
                from notebook.collab.persistence import CommentThread
                thread = sessions.query(CommentThread).filter(
                    CommentThread.thread_id == thread_id
                ).first()
                
                if thread:
                    # Get the full thread with comments
                    threads = self.persistence_manager.get_comment_threads(
                        str(thread.session_id), thread.cell_id
                    )
                    for t in threads:
                        if t['thread_id'] == thread_id:
                            return t
            finally:
                sessions.close()
        
        return None
    
    def get_threads_for_cell(self, session_id: str, cell_id: CellId, 
                           status: t.Optional[str] = None) -> t.List[t.Dict[str, t.Any]]:
        """Get all comment threads for a specific cell.
        
        Args:
            session_id: The collaboration session ID
            cell_id: The cell ID to get comments for
            status: Optional filter by thread status
            
        Returns:
            A list of thread dictionaries
        """
        # Check cache first
        if session_id in self._comment_cache and cell_id in self._comment_cache[session_id]:
            threads = list(self._comment_cache[session_id][cell_id].values())
            if status:
                threads = [t for t in threads if t['status'] == status]
            return threads
        
        # If not in cache and persistence manager is available, try there
        if self.persistence_manager:
            return self.persistence_manager.get_comment_threads(session_id, cell_id, status)
        
        return []
    
    def get_threads_for_document(self, session_id: str, 
                              status: t.Optional[str] = None) -> t.List[t.Dict[str, t.Any]]:
        """Get all comment threads for a document.
        
        Args:
            session_id: The collaboration session ID
            status: Optional filter by thread status
            
        Returns:
            A list of thread dictionaries
        """
        # Check cache first
        if session_id in self._comment_cache:
            threads = []
            for cell_threads in self._comment_cache[session_id].values():
                threads.extend(cell_threads.values())
            
            if status:
                threads = [t for t in threads if t['status'] == status]
            return threads
        
        # If not in cache and persistence manager is available, try there
        if self.persistence_manager:
            return self.persistence_manager.get_comment_threads(session_id, None, status)
        
        return []
    
    def update_thread_status(self, thread_id: ThreadId, status: str, 
                           user_id: UserId) -> bool:
        """Update the status of a comment thread.
        
        Args:
            thread_id: The thread ID to update
            status: The new status (open, resolved, archived)
            user_id: The user updating the status
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            ValueError: If the status is invalid
            PermissionError: If the user doesn't have permission to update the thread
        """
        if status not in [ThreadStatus.OPEN, ThreadStatus.RESOLVED, ThreadStatus.ARCHIVED]:
            raise ValueError(f"Invalid thread status: {status}")
        
        # Get thread info to check permissions
        thread_info = self.get_thread(thread_id)
        if not thread_info:
            return False
        
        session_id = thread_info['session_id']
        cell_id = thread_info['cell_id']
        
        # Check permissions if permission manager is available
        if self.permission_manager:
            user_identity = {"name": user_id}
            # Need RESOLVE_THREAD permission to change status
            if not self.permission_manager.has_cell_permission(
                session_id, cell_id, user_identity, PermissionAction.RESOLVE_THREAD
            ):
                raise PermissionError(f"User {user_id} does not have permission to update thread status")
        
        # Update status
        if not self.persistence_manager:
            self.logger.warning("No persistence manager available for thread status update")
            # Update in-memory status
            for session_cache in self._comment_cache.values():
                for cell_cache in session_cache.values():
                    if thread_id in cell_cache:
                        # Update thread status
                        cell_cache[thread_id]['status'] = status
                        
                        # Add status change to metadata
                        if 'status_history' not in cell_cache[thread_id]['metadata']:
                            cell_cache[thread_id]['metadata']['status_history'] = []
                        
                        cell_cache[thread_id]['metadata']['status_history'].append({
                            'status': status,
                            'changed_by': user_id,
                            'timestamp': datetime.utcnow().isoformat()
                        })
                        
                        return True
            
            return False
        else:
            # Update with persistence manager
            success = self.persistence_manager.update_thread_status(thread_id, status, user_id)
            
            if success:
                # Queue notification
                notification_data = {
                    'thread_id': thread_id,
                    'status': status,
                    'updated_by': user_id,
                    'session_id': session_id,
                    'cell_id': cell_id
                }
                self._queue_notification(session_id, 'thread_status_updated', notification_data)
            
            return success
    
    def delete_comment(self, comment_id: CommentId, user_id: UserId) -> bool:
        """Delete a comment.
        
        Args:
            comment_id: The comment ID to delete
            user_id: The user deleting the comment
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            PermissionError: If the user doesn't have permission to delete the comment
        """
        # This is a placeholder implementation
        # In a real implementation, we would need to:
        # 1. Find the comment in the database
        # 2. Check if the user is the comment author or has admin permissions
        # 3. Soft-delete the comment (mark as deleted but keep in database)
        # 4. Send notification about the deletion
        
        self.logger.warning("Comment deletion not fully implemented")
        return False
    
    def edit_comment(self, comment_id: CommentId, user_id: UserId, 
                    new_content: str) -> t.Optional[t.Dict[str, t.Any]]:
        """Edit a comment.
        
        Args:
            comment_id: The comment ID to edit
            user_id: The user editing the comment
            new_content: The new comment content
            
        Returns:
            The updated comment data if successful, None otherwise
            
        Raises:
            PermissionError: If the user doesn't have permission to edit the comment
        """
        # This is a placeholder implementation
        # In a real implementation, we would need to:
        # 1. Find the comment in the database
        # 2. Check if the user is the comment author
        # 3. Update the comment content
        # 4. Send notification about the edit
        
        self.logger.warning("Comment editing not fully implemented")
        return None
    
    def _queue_notification(self, session_id: str, event_type: str, 
                          data: t.Dict[str, t.Any]) -> None:
        """Queue a notification for delivery to clients.
        
        Args:
            session_id: The collaboration session ID
            event_type: The type of event (thread_created, comment_added, etc.)
            data: The event data
        """
        if not self.enable_notifications:
            return
        
        if session_id not in self._notification_queue:
            self._notification_queue[session_id] = []
        
        self._notification_queue[session_id].append({
            'event': event_type,
            'data': data,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # In a real implementation, we would use a debounce mechanism
        # to batch notifications and send them periodically
        # For now, we'll just log that a notification was queued
        self.logger.debug(f"Queued {event_type} notification for session {session_id}")
    
    def get_pending_notifications(self, session_id: str) -> t.List[t.Dict[str, t.Any]]:
        """Get pending notifications for a session.
        
        Args:
            session_id: The collaboration session ID
            
        Returns:
            A list of notification dictionaries
        """
        if session_id not in self._notification_queue:
            return []
        
        notifications = self._notification_queue[session_id]
        self._notification_queue[session_id] = []
        return notifications
    
    def clear_cache(self, session_id: t.Optional[str] = None) -> None:
        """Clear the comment cache.
        
        Args:
            session_id: Optional session ID to clear cache for.
                       If None, clear cache for all sessions.
        """
        if session_id is None:
            self._comment_cache = {}
        elif session_id in self._comment_cache:
            del self._comment_cache[session_id]


class CommentWebSocketHandler(websocket.WebSocketHandler):
    """WebSocket handler for real-time comment updates.
    
    This handler manages WebSocket connections for delivering real-time
    comment notifications to clients. It handles subscription to comment
    events and delivers updates when comments are created or modified.
    """
    
    def initialize(self, comment_manager=None, permission_manager=None):
        """Initialize the handler.
        
        Args:
            comment_manager: The comment manager instance
            permission_manager: The permission manager instance
        """
        self.logger = logging.getLogger(__name__)
        self.comment_manager = comment_manager
        self.permission_manager = permission_manager
        self.session_id = None
        self.user_id = None
        self.client_id = None
    
    def open(self, session_id=None):
        """Handle WebSocket connection opening.
        
        Args:
            session_id: The collaboration session ID from the URL
        """
        self.logger.info(f"Comment WebSocket opened for session {session_id}")
        self.session_id = session_id
    
    def on_message(self, message):
        """Handle incoming WebSocket messages.
        
        Args:
            message: The message received from the client
        """
        try:
            data = json.loads(message)
            action = data.get('action')
            
            if action == 'subscribe':
                self._handle_subscribe(data)
            elif action == 'create_thread':
                self._handle_create_thread(data)
            elif action == 'add_comment':
                self._handle_add_comment(data)
            elif action == 'update_status':
                self._handle_update_status(data)
            elif action == 'get_threads':
                self._handle_get_threads(data)
            else:
                self.logger.warning(f"Unknown action: {action}")
                self.write_message(json.dumps({
                    'error': f"Unknown action: {action}"
                }))
        except json.JSONDecodeError:
            self.logger.error("Invalid JSON message")
            self.write_message(json.dumps({
                'error': "Invalid JSON message"
            }))
        except Exception as e:
            self.logger.exception(f"Error handling message: {e}")
            self.write_message(json.dumps({
                'error': str(e)
            }))
    
    def _handle_subscribe(self, data):
        """Handle subscription request.
        
        Args:
            data: The subscription request data
        """
        self.user_id = data.get('user_id')
        self.client_id = data.get('client_id')
        
        if not self.user_id or not self.client_id:
            self.write_message(json.dumps({
                'error': "Missing user_id or client_id in subscribe request"
            }))
            return
        
        # Check if user has permission to view comments
        if self.permission_manager and self.session_id:
            user_identity = {"name": self.user_id}
            document_id = self.session_id  # In this simple implementation, session_id is document_id
            
            if not self.permission_manager.has_permission(
                document_id, user_identity, PermissionAction.VIEW_DOCUMENT
            ):
                self.write_message(json.dumps({
                    'error': "You don't have permission to view comments in this document"
                }))
                return
        
        self.write_message(json.dumps({
            'event': 'subscribed',
            'session_id': self.session_id,
            'user_id': self.user_id,
            'client_id': self.client_id
        }))
        
        # Send any pending notifications
        if self.comment_manager and self.session_id:
            notifications = self.comment_manager.get_pending_notifications(self.session_id)
            if notifications:
                self.write_message(json.dumps({
                    'event': 'notifications',
                    'notifications': notifications
                }))
    
    def _handle_create_thread(self, data):
        """Handle thread creation request.
        
        Args:
            data: The thread creation request data
        """
        if not self.comment_manager or not self.session_id or not self.user_id:
            self.write_message(json.dumps({
                'error': "Not properly initialized or subscribed"
            }))
            return
        
        cell_id = data.get('cell_id')
        content = data.get('content')
        metadata = data.get('metadata', {})
        
        if not cell_id or not content:
            self.write_message(json.dumps({
                'error': "Missing cell_id or content in create_thread request"
            }))
            return
        
        try:
            thread = self.comment_manager.create_thread(
                self.session_id, cell_id, self.user_id, content, metadata
            )
            
            self.write_message(json.dumps({
                'event': 'thread_created',
                'thread': thread
            }))
            
            # In a real implementation, we would broadcast this to all clients
            # subscribed to this session
        except PermissionError as e:
            self.write_message(json.dumps({
                'error': str(e)
            }))
        except Exception as e:
            self.logger.exception(f"Error creating thread: {e}")
            self.write_message(json.dumps({
                'error': f"Error creating thread: {str(e)}"
            }))
    
    def _handle_add_comment(self, data):
        """Handle comment addition request.
        
        Args:
            data: The comment addition request data
        """
        if not self.comment_manager or not self.user_id:
            self.write_message(json.dumps({
                'error': "Not properly initialized or subscribed"
            }))
            return
        
        thread_id = data.get('thread_id')
        content = data.get('content')
        metadata = data.get('metadata', {})
        
        if not thread_id or not content:
            self.write_message(json.dumps({
                'error': "Missing thread_id or content in add_comment request"
            }))
            return
        
        try:
            comment = self.comment_manager.add_comment(
                thread_id, self.user_id, content, metadata
            )
            
            self.write_message(json.dumps({
                'event': 'comment_added',
                'comment': comment
            }))
            
            # In a real implementation, we would broadcast this to all clients
            # subscribed to this session
        except PermissionError as e:
            self.write_message(json.dumps({
                'error': str(e)
            }))
        except Exception as e:
            self.logger.exception(f"Error adding comment: {e}")
            self.write_message(json.dumps({
                'error': f"Error adding comment: {str(e)}"
            }))
    
    def _handle_update_status(self, data):
        """Handle thread status update request.
        
        Args:
            data: The status update request data
        """
        if not self.comment_manager or not self.user_id:
            self.write_message(json.dumps({
                'error': "Not properly initialized or subscribed"
            }))
            return
        
        thread_id = data.get('thread_id')
        status = data.get('status')
        
        if not thread_id or not status:
            self.write_message(json.dumps({
                'error': "Missing thread_id or status in update_status request"
            }))
            return
        
        try:
            success = self.comment_manager.update_thread_status(
                thread_id, status, self.user_id
            )
            
            if success:
                self.write_message(json.dumps({
                    'event': 'status_updated',
                    'thread_id': thread_id,
                    'status': status
                }))
            else:
                self.write_message(json.dumps({
                    'error': f"Failed to update thread status"
                }))
            
            # In a real implementation, we would broadcast this to all clients
            # subscribed to this session
        except PermissionError as e:
            self.write_message(json.dumps({
                'error': str(e)
            }))
        except Exception as e:
            self.logger.exception(f"Error updating thread status: {e}")
            self.write_message(json.dumps({
                'error': f"Error updating thread status: {str(e)}"
            }))
    
    def _handle_get_threads(self, data):
        """Handle thread retrieval request.
        
        Args:
            data: The thread retrieval request data
        """
        if not self.comment_manager or not self.session_id:
            self.write_message(json.dumps({
                'error': "Not properly initialized or subscribed"
            }))
            return
        
        cell_id = data.get('cell_id')
        status = data.get('status')
        
        try:
            if cell_id:
                threads = self.comment_manager.get_threads_for_cell(
                    self.session_id, cell_id, status
                )
            else:
                threads = self.comment_manager.get_threads_for_document(
                    self.session_id, status
                )
            
            self.write_message(json.dumps({
                'event': 'threads_retrieved',
                'threads': threads,
                'cell_id': cell_id,
                'status': status
            }))
        except Exception as e:
            self.logger.exception(f"Error retrieving threads: {e}")
            self.write_message(json.dumps({
                'error': f"Error retrieving threads: {str(e)}"
            }))
    
    def on_close(self):
        """Handle WebSocket connection closing."""
        self.logger.info(f"Comment WebSocket closed for session {self.session_id}")
    
    def check_origin(self, origin):
        """Check if the origin is allowed.
        
        Args:
            origin: The origin of the WebSocket connection
            
        Returns:
            True if the origin is allowed, False otherwise
        """
        # In a production environment, this should be more restrictive
        return True


class CommentHandler(JupyterHandler):
    """HTTP handler for comment operations.
    
    This handler provides REST API endpoints for comment operations,
    allowing clients to create, retrieve, update, and delete comments
    using standard HTTP methods.
    """
    
    def initialize(self, comment_manager=None, permission_manager=None):
        """Initialize the handler.
        
        Args:
            comment_manager: The comment manager instance
            permission_manager: The permission manager instance
        """
        self.logger = logging.getLogger(__name__)
        self.comment_manager = comment_manager
        self.permission_manager = permission_manager
    
    @web.authenticated
    @collaborative_authorized("CREATE_THREAD")
    async def post(self, session_id, cell_id=None):
        """Handle POST requests to create a new comment thread.
        
        Args:
            session_id: The collaboration session ID from the URL
            cell_id: The cell ID from the URL (optional)
        """
        if not self.comment_manager:
            raise web.HTTPError(500, "Comment manager not available")
        
        # Get user ID from current user
        user_id = self.current_user.get('name', None)
        if not user_id:
            raise web.HTTPError(401, "User not authenticated")
        
        # Parse request body
        try:
            data = json.loads(self.request.body)
        except json.JSONDecodeError:
            raise web.HTTPError(400, "Invalid JSON in request body")
        
        # If cell_id not in URL, get from request body
        if not cell_id:
            cell_id = data.get('cell_id')
        
        content = data.get('content')
        metadata = data.get('metadata', {})
        
        if not cell_id or not content:
            raise web.HTTPError(400, "Missing cell_id or content in request")
        
        try:
            thread = self.comment_manager.create_thread(
                session_id, cell_id, user_id, content, metadata
            )
            
            self.set_status(201)  # Created
            self.write(json.dumps(thread))
        except PermissionError as e:
            raise web.HTTPError(403, str(e))
        except Exception as e:
            self.logger.exception(f"Error creating thread: {e}")
            raise web.HTTPError(500, f"Error creating thread: {str(e)}")
    
    @web.authenticated
    @collaborative_authorized("VIEW_DOCUMENT")
    async def get(self, session_id, thread_id=None, cell_id=None):
        """Handle GET requests to retrieve comment threads.
        
        Args:
            session_id: The collaboration session ID from the URL
            thread_id: The thread ID from the URL (optional)
            cell_id: The cell ID from the URL (optional)
        """
        if not self.comment_manager:
            raise web.HTTPError(500, "Comment manager not available")
        
        # Get status filter from query parameters
        status = self.get_query_argument('status', None)
        
        try:
            if thread_id:
                # Get specific thread
                thread = self.comment_manager.get_thread(thread_id)
                if not thread:
                    raise web.HTTPError(404, f"Thread {thread_id} not found")
                
                self.write(json.dumps(thread))
            elif cell_id:
                # Get threads for cell
                threads = self.comment_manager.get_threads_for_cell(
                    session_id, cell_id, status
                )
                self.write(json.dumps(threads))
            else:
                # Get all threads for document
                threads = self.comment_manager.get_threads_for_document(
                    session_id, status
                )
                self.write(json.dumps(threads))
        except Exception as e:
            self.logger.exception(f"Error retrieving threads: {e}")
            raise web.HTTPError(500, f"Error retrieving threads: {str(e)}")
    
    @web.authenticated
    @collaborative_authorized("REPLY_THREAD")
    async def put(self, session_id, thread_id):
        """Handle PUT requests to add a comment to a thread or update thread status.
        
        Args:
            session_id: The collaboration session ID from the URL
            thread_id: The thread ID from the URL
        """
        if not self.comment_manager:
            raise web.HTTPError(500, "Comment manager not available")
        
        # Get user ID from current user
        user_id = self.current_user.get('name', None)
        if not user_id:
            raise web.HTTPError(401, "User not authenticated")
        
        # Parse request body
        try:
            data = json.loads(self.request.body)
        except json.JSONDecodeError:
            raise web.HTTPError(400, "Invalid JSON in request body")
        
        action = data.get('action')
        
        try:
            if action == 'add_comment':
                content = data.get('content')
                metadata = data.get('metadata', {})
                
                if not content:
                    raise web.HTTPError(400, "Missing content in request")
                
                comment = self.comment_manager.add_comment(
                    thread_id, user_id, content, metadata
                )
                
                self.write(json.dumps(comment))
            elif action == 'update_status':
                status = data.get('status')
                
                if not status:
                    raise web.HTTPError(400, "Missing status in request")
                
                success = self.comment_manager.update_thread_status(
                    thread_id, status, user_id
                )
                
                if not success:
                    raise web.HTTPError(404, f"Thread {thread_id} not found")
                
                self.write(json.dumps({'success': True, 'status': status}))
            else:
                raise web.HTTPError(400, f"Unknown action: {action}")
        except PermissionError as e:
            raise web.HTTPError(403, str(e))
        except KeyError as e:
            raise web.HTTPError(404, str(e))
        except ValueError as e:
            raise web.HTTPError(400, str(e))
        except Exception as e:
            self.logger.exception(f"Error processing request: {e}")
            raise web.HTTPError(500, f"Error processing request: {str(e)}")


def setup_handlers(web_app, comment_manager=None, permission_manager=None):
    """Set up the comment handlers for the Jupyter web application.
    
    Args:
        web_app: The Jupyter web application
        comment_manager: The comment manager instance
        permission_manager: The permission manager instance
    """
    host_pattern = ".*$"
    
    # HTTP handlers
    comment_handlers = [
        # Get all threads for a document
        (r"/api/collaboration/sessions/([^/]+)/comments", CommentHandler, {
            'comment_manager': comment_manager,
            'permission_manager': permission_manager
        }),
        # Get all threads for a cell
        (r"/api/collaboration/sessions/([^/]+)/cells/([^/]+)/comments", CommentHandler, {
            'comment_manager': comment_manager,
            'permission_manager': permission_manager
        }),
        # Get/update a specific thread
        (r"/api/collaboration/sessions/([^/]+)/comments/([^/]+)", CommentHandler, {
            'comment_manager': comment_manager,
            'permission_manager': permission_manager
        }),
    ]
    
    # WebSocket handler
    websocket_handlers = [
        (r"/api/collaboration/sessions/([^/]+)/comments/ws", CommentWebSocketHandler, {
            'comment_manager': comment_manager,
            'permission_manager': permission_manager
        }),
    ]
    
    web_app.add_handlers(host_pattern, comment_handlers)
    web_app.add_handlers(host_pattern, websocket_handlers)
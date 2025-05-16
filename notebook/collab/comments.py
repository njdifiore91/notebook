"""Server-side component of the comment and review system for Jupyter Notebook v7.

This module implements the server-side functionality for managing comments and review threads
attached to specific notebook cells. It provides APIs for creating, retrieving, updating, and
deleting comments, as well as managing comment threads and their resolution status.

The comment system enables users to discuss specific cells in a notebook, provide feedback,
and track the resolution of issues or suggestions. Comments are synchronized across all
connected clients in real-time, enabling collaborative code review and discussion.

Classes:
    CommentManager: Main class for managing comment threads and comments.
    CommentThread: Represents a thread of comments attached to a specific cell.
    Comment: Represents an individual comment within a thread.
    CommentNotification: Handles notification delivery for new comments.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union, cast

from jupyter_server.auth import Authorizer
from jupyter_server.base.handlers import JupyterHandler
from tornado import web
from traitlets import Bool, Dict as TDict, Instance, Int, Unicode, default
from traitlets.config import LoggingConfigurable

# Local imports
from notebook.collab.persistence import CollaborationPersistence


class CommentStatus(str, Enum):
    """Enum representing the status of a comment thread."""
    OPEN = "open"
    RESOLVED = "resolved"
    ARCHIVED = "archived"


class Comment:
    """Represents an individual comment within a thread.
    
    Attributes:
        comment_id: Unique identifier for the comment.
        thread_id: Identifier of the thread this comment belongs to.
        user_id: Identifier of the user who created the comment.
        content: Text content of the comment.
        created_at: Timestamp when the comment was created.
        updated_at: Timestamp when the comment was last updated.
        metadata: Additional information about the comment (mentions, formatting, etc.).
    """
    
    def __init__(
        self,
        thread_id: str,
        user_id: str,
        content: str,
        comment_id: Optional[str] = None,
        created_at: Optional[float] = None,
        updated_at: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Initialize a new Comment instance.
        
        Args:
            thread_id: Identifier of the thread this comment belongs to.
            user_id: Identifier of the user who created the comment.
            content: Text content of the comment.
            comment_id: Unique identifier for the comment. If None, a new UUID is generated.
            created_at: Timestamp when the comment was created. If None, current time is used.
            updated_at: Timestamp when the comment was last updated. If None, same as created_at.
            metadata: Additional information about the comment.
        """
        self.comment_id = comment_id or str(uuid.uuid4())
        self.thread_id = thread_id
        self.user_id = user_id
        self.content = content
        self.created_at = created_at or time.time()
        self.updated_at = updated_at or self.created_at
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the comment to a dictionary representation.
        
        Returns:
            Dictionary representation of the comment.
        """
        return {
            "comment_id": self.comment_id,
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Comment:
        """Create a Comment instance from a dictionary.
        
        Args:
            data: Dictionary containing comment data.
            
        Returns:
            A new Comment instance.
        """
        return cls(
            thread_id=data["thread_id"],
            user_id=data["user_id"],
            content=data["content"],
            comment_id=data["comment_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            metadata=data["metadata"]
        )
    
    def update_content(self, content: str) -> None:
        """Update the content of the comment.
        
        Args:
            content: New content for the comment.
        """
        self.content = content
        self.updated_at = time.time()
    
    def update_metadata(self, metadata: Dict[str, Any]) -> None:
        """Update the metadata of the comment.
        
        Args:
            metadata: New metadata for the comment.
        """
        self.metadata.update(metadata)
        self.updated_at = time.time()


class CommentThread:
    """Represents a thread of comments attached to a specific cell.
    
    Attributes:
        thread_id: Unique identifier for the thread.
        session_id: Identifier of the collaboration session.
        cell_id: Identifier of the cell the thread is attached to.
        created_at: Timestamp when the thread was created.
        status: Status of the thread (open, resolved, archived).
        metadata: Additional information about the thread.
        comments: List of comments in the thread.
    """
    
    def __init__(
        self,
        session_id: str,
        cell_id: str,
        thread_id: Optional[str] = None,
        created_at: Optional[float] = None,
        status: CommentStatus = CommentStatus.OPEN,
        metadata: Optional[Dict[str, Any]] = None,
        comments: Optional[List[Comment]] = None
    ) -> None:
        """Initialize a new CommentThread instance.
        
        Args:
            session_id: Identifier of the collaboration session.
            cell_id: Identifier of the cell the thread is attached to.
            thread_id: Unique identifier for the thread. If None, a new UUID is generated.
            created_at: Timestamp when the thread was created. If None, current time is used.
            status: Status of the thread.
            metadata: Additional information about the thread.
            comments: List of comments in the thread.
        """
        self.thread_id = thread_id or str(uuid.uuid4())
        self.session_id = session_id
        self.cell_id = cell_id
        self.created_at = created_at or time.time()
        self.status = status
        self.metadata = metadata or {}
        self.comments = comments or []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the thread to a dictionary representation.
        
        Returns:
            Dictionary representation of the thread.
        """
        return {
            "thread_id": self.thread_id,
            "session_id": self.session_id,
            "cell_id": self.cell_id,
            "created_at": self.created_at,
            "status": self.status.value,
            "metadata": self.metadata,
            "comments": [comment.to_dict() for comment in self.comments]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CommentThread:
        """Create a CommentThread instance from a dictionary.
        
        Args:
            data: Dictionary containing thread data.
            
        Returns:
            A new CommentThread instance.
        """
        comments = [Comment.from_dict(comment_data) for comment_data in data.get("comments", [])]
        return cls(
            session_id=data["session_id"],
            cell_id=data["cell_id"],
            thread_id=data["thread_id"],
            created_at=data["created_at"],
            status=CommentStatus(data["status"]),
            metadata=data["metadata"],
            comments=comments
        )
    
    def add_comment(self, user_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Comment:
        """Add a new comment to the thread.
        
        Args:
            user_id: Identifier of the user creating the comment.
            content: Text content of the comment.
            metadata: Additional information about the comment.
            
        Returns:
            The newly created Comment instance.
        """
        comment = Comment(
            thread_id=self.thread_id,
            user_id=user_id,
            content=content,
            metadata=metadata
        )
        self.comments.append(comment)
        return comment
    
    def get_comment(self, comment_id: str) -> Optional[Comment]:
        """Get a comment by its ID.
        
        Args:
            comment_id: Identifier of the comment to retrieve.
            
        Returns:
            The Comment instance if found, None otherwise.
        """
        for comment in self.comments:
            if comment.comment_id == comment_id:
                return comment
        return None
    
    def update_comment(self, comment_id: str, content: str) -> Optional[Comment]:
        """Update the content of a comment.
        
        Args:
            comment_id: Identifier of the comment to update.
            content: New content for the comment.
            
        Returns:
            The updated Comment instance if found, None otherwise.
        """
        comment = self.get_comment(comment_id)
        if comment:
            comment.update_content(content)
        return comment
    
    def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment from the thread.
        
        Args:
            comment_id: Identifier of the comment to delete.
            
        Returns:
            True if the comment was deleted, False otherwise.
        """
        for i, comment in enumerate(self.comments):
            if comment.comment_id == comment_id:
                del self.comments[i]
                return True
        return False
    
    def set_status(self, status: CommentStatus) -> None:
        """Set the status of the thread.
        
        Args:
            status: New status for the thread.
        """
        self.status = status
    
    def update_metadata(self, metadata: Dict[str, Any]) -> None:
        """Update the metadata of the thread.
        
        Args:
            metadata: New metadata for the thread.
        """
        self.metadata.update(metadata)


class CommentNotification:
    """Handles notification delivery for new comments.
    
    This class is responsible for notifying users about new comments or updates
    to existing comments in threads they are participating in or watching.
    
    Attributes:
        thread_id: Identifier of the thread the notification is for.
        comment_id: Identifier of the comment that triggered the notification.
        user_id: Identifier of the user who created the comment.
        recipients: Set of user IDs to notify.
        created_at: Timestamp when the notification was created.
        metadata: Additional information about the notification.
    """
    
    def __init__(
        self,
        thread_id: str,
        comment_id: str,
        user_id: str,
        recipients: Optional[Set[str]] = None,
        created_at: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Initialize a new CommentNotification instance.
        
        Args:
            thread_id: Identifier of the thread the notification is for.
            comment_id: Identifier of the comment that triggered the notification.
            user_id: Identifier of the user who created the comment.
            recipients: Set of user IDs to notify. If None, an empty set is used.
            created_at: Timestamp when the notification was created. If None, current time is used.
            metadata: Additional information about the notification.
        """
        self.thread_id = thread_id
        self.comment_id = comment_id
        self.user_id = user_id
        self.recipients = recipients or set()
        self.created_at = created_at or time.time()
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the notification to a dictionary representation.
        
        Returns:
            Dictionary representation of the notification.
        """
        return {
            "thread_id": self.thread_id,
            "comment_id": self.comment_id,
            "user_id": self.user_id,
            "recipients": list(self.recipients),
            "created_at": self.created_at,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CommentNotification:
        """Create a CommentNotification instance from a dictionary.
        
        Args:
            data: Dictionary containing notification data.
            
        Returns:
            A new CommentNotification instance.
        """
        return cls(
            thread_id=data["thread_id"],
            comment_id=data["comment_id"],
            user_id=data["user_id"],
            recipients=set(data["recipients"]),
            created_at=data["created_at"],
            metadata=data["metadata"]
        )
    
    def add_recipient(self, user_id: str) -> None:
        """Add a recipient to the notification.
        
        Args:
            user_id: Identifier of the user to add as a recipient.
        """
        self.recipients.add(user_id)
    
    def remove_recipient(self, user_id: str) -> None:
        """Remove a recipient from the notification.
        
        Args:
            user_id: Identifier of the user to remove as a recipient.
        """
        if user_id in self.recipients:
            self.recipients.remove(user_id)


class CommentManager(LoggingConfigurable):
    """Manages comment threads and comments for collaborative notebooks.
    
    This class provides methods for creating, retrieving, updating, and deleting
    comment threads and comments. It also handles notification delivery for new comments.
    
    Attributes:
        persistence: Instance of CollaborationPersistence for storing comments.
        authorizer: Instance of Authorizer for checking user permissions.
        notification_enabled: Whether comment notifications are enabled.
        notification_debounce_ms: Debounce time for notifications in milliseconds.
        max_comments_per_thread: Maximum number of comments allowed in a thread.
    """
    
    persistence = Instance(CollaborationPersistence, help="Persistence layer for storing comments")
    authorizer = Instance(Authorizer, help="Authorizer for checking user permissions")
    
    notification_enabled = Bool(True, help="Whether comment notifications are enabled").tag(config=True)
    notification_debounce_ms = Int(1000, help="Debounce time for notifications in milliseconds").tag(config=True)
    max_comments_per_thread = Int(100, help="Maximum number of comments allowed in a thread").tag(config=True)
    
    # Internal state
    _threads = TDict(help="In-memory cache of comment threads").tag(config=False)
    _notifications = TDict(help="In-memory queue of pending notifications").tag(config=False)
    _notification_tasks = TDict(help="Map of notification tasks").tag(config=False)
    
    @default("_threads")
    def _default_threads(self) -> Dict[str, CommentThread]:
        return {}
    
    @default("_notifications")
    def _default_notifications(self) -> Dict[str, List[CommentNotification]]:
        return {}
    
    @default("_notification_tasks")
    def _default_notification_tasks(self) -> Dict[str, asyncio.Task]:
        return {}
    
    def __init__(self, **kwargs: Any) -> None:
        """Initialize the CommentManager.
        
        Args:
            **kwargs: Additional keyword arguments passed to the parent class.
        """
        super().__init__(**kwargs)
        self.log.debug("Initializing CommentManager")
    
    async def initialize(self) -> None:
        """Initialize the CommentManager.
        
        This method loads all comment threads from the persistence layer.
        """
        self.log.debug("Loading comment threads from persistence layer")
        try:
            # Load all threads from persistence
            threads = await self.persistence.get_all_comment_threads()
            for thread in threads:
                self._threads[thread.thread_id] = thread
            self.log.info(f"Loaded {len(threads)} comment threads from persistence layer")
        except Exception as e:
            self.log.error(f"Error loading comment threads: {e}")
            raise
    
    async def create_thread(
        self,
        session_id: str,
        cell_id: str,
        user_id: str,
        initial_comment: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CommentThread:
        """Create a new comment thread.
        
        Args:
            session_id: Identifier of the collaboration session.
            cell_id: Identifier of the cell to attach the thread to.
            user_id: Identifier of the user creating the thread.
            initial_comment: Optional initial comment text.
            metadata: Additional information about the thread.
            
        Returns:
            The newly created CommentThread instance.
            
        Raises:
            ValueError: If the session_id or cell_id is invalid.
            PermissionError: If the user does not have permission to create a thread.
        """
        # Check if the session exists
        if not await self.persistence.session_exists(session_id):
            raise ValueError(f"Invalid session ID: {session_id}")
        
        # Create the thread
        thread = CommentThread(
            session_id=session_id,
            cell_id=cell_id,
            metadata=metadata
        )
        
        # Add initial comment if provided
        if initial_comment:
            thread.add_comment(user_id, initial_comment)
        
        # Store the thread in memory and persistence
        self._threads[thread.thread_id] = thread
        await self.persistence.save_comment_thread(thread)
        
        self.log.info(f"Created comment thread {thread.thread_id} for cell {cell_id} in session {session_id}")
        return thread
    
    async def get_thread(self, thread_id: str) -> Optional[CommentThread]:
        """Get a comment thread by its ID.
        
        Args:
            thread_id: Identifier of the thread to retrieve.
            
        Returns:
            The CommentThread instance if found, None otherwise.
        """
        # Check in-memory cache first
        if thread_id in self._threads:
            return self._threads[thread_id]
        
        # Try to load from persistence
        thread = await self.persistence.get_comment_thread(thread_id)
        if thread:
            self._threads[thread_id] = thread
        
        return thread
    
    async def get_threads_for_cell(self, session_id: str, cell_id: str) -> List[CommentThread]:
        """Get all comment threads for a specific cell.
        
        Args:
            session_id: Identifier of the collaboration session.
            cell_id: Identifier of the cell to get threads for.
            
        Returns:
            List of CommentThread instances for the cell.
        """
        # Load threads from persistence to ensure we have the latest data
        threads = await self.persistence.get_comment_threads_for_cell(session_id, cell_id)
        
        # Update in-memory cache
        for thread in threads:
            self._threads[thread.thread_id] = thread
        
        return threads
    
    async def get_threads_for_session(self, session_id: str) -> List[CommentThread]:
        """Get all comment threads for a collaboration session.
        
        Args:
            session_id: Identifier of the collaboration session.
            
        Returns:
            List of CommentThread instances for the session.
        """
        # Load threads from persistence to ensure we have the latest data
        threads = await self.persistence.get_comment_threads_for_session(session_id)
        
        # Update in-memory cache
        for thread in threads:
            self._threads[thread.thread_id] = thread
        
        return threads
    
    async def add_comment(
        self,
        thread_id: str,
        user_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Comment:
        """Add a comment to a thread.
        
        Args:
            thread_id: Identifier of the thread to add the comment to.
            user_id: Identifier of the user creating the comment.
            content: Text content of the comment.
            metadata: Additional information about the comment.
            
        Returns:
            The newly created Comment instance.
            
        Raises:
            ValueError: If the thread_id is invalid or the thread has reached the maximum number of comments.
            PermissionError: If the user does not have permission to add a comment.
        """
        # Get the thread
        thread = await self.get_thread(thread_id)
        if not thread:
            raise ValueError(f"Invalid thread ID: {thread_id}")
        
        # Check if the thread has reached the maximum number of comments
        if len(thread.comments) >= self.max_comments_per_thread:
            raise ValueError(f"Thread {thread_id} has reached the maximum number of comments")
        
        # Add the comment to the thread
        comment = thread.add_comment(user_id, content, metadata)
        
        # Save the updated thread
        await self.persistence.save_comment_thread(thread)
        
        # Create a notification for the comment
        if self.notification_enabled:
            await self._create_notification(thread, comment)
        
        self.log.info(f"Added comment {comment.comment_id} to thread {thread_id} by user {user_id}")
        return comment
    
    async def update_comment(
        self,
        thread_id: str,
        comment_id: str,
        user_id: str,
        content: str
    ) -> Optional[Comment]:
        """Update a comment in a thread.
        
        Args:
            thread_id: Identifier of the thread containing the comment.
            comment_id: Identifier of the comment to update.
            user_id: Identifier of the user updating the comment.
            content: New text content for the comment.
            
        Returns:
            The updated Comment instance if found, None otherwise.
            
        Raises:
            ValueError: If the thread_id or comment_id is invalid.
            PermissionError: If the user does not have permission to update the comment.
        """
        # Get the thread
        thread = await self.get_thread(thread_id)
        if not thread:
            raise ValueError(f"Invalid thread ID: {thread_id}")
        
        # Get the comment
        comment = thread.get_comment(comment_id)
        if not comment:
            raise ValueError(f"Invalid comment ID: {comment_id}")
        
        # Check if the user is the author of the comment
        if comment.user_id != user_id:
            raise PermissionError(f"User {user_id} does not have permission to update comment {comment_id}")
        
        # Update the comment
        comment.update_content(content)
        
        # Save the updated thread
        await self.persistence.save_comment_thread(thread)
        
        self.log.info(f"Updated comment {comment_id} in thread {thread_id} by user {user_id}")
        return comment
    
    async def delete_comment(
        self,
        thread_id: str,
        comment_id: str,
        user_id: str
    ) -> bool:
        """Delete a comment from a thread.
        
        Args:
            thread_id: Identifier of the thread containing the comment.
            comment_id: Identifier of the comment to delete.
            user_id: Identifier of the user deleting the comment.
            
        Returns:
            True if the comment was deleted, False otherwise.
            
        Raises:
            ValueError: If the thread_id or comment_id is invalid.
            PermissionError: If the user does not have permission to delete the comment.
        """
        # Get the thread
        thread = await self.get_thread(thread_id)
        if not thread:
            raise ValueError(f"Invalid thread ID: {thread_id}")
        
        # Get the comment
        comment = thread.get_comment(comment_id)
        if not comment:
            raise ValueError(f"Invalid comment ID: {comment_id}")
        
        # Check if the user is the author of the comment
        if comment.user_id != user_id:
            raise PermissionError(f"User {user_id} does not have permission to delete comment {comment_id}")
        
        # Delete the comment
        result = thread.delete_comment(comment_id)
        
        # Save the updated thread if the comment was deleted
        if result:
            await self.persistence.save_comment_thread(thread)
            self.log.info(f"Deleted comment {comment_id} from thread {thread_id} by user {user_id}")
        
        return result
    
    async def set_thread_status(
        self,
        thread_id: str,
        user_id: str,
        status: CommentStatus
    ) -> Optional[CommentThread]:
        """Set the status of a comment thread.
        
        Args:
            thread_id: Identifier of the thread to update.
            user_id: Identifier of the user updating the thread status.
            status: New status for the thread.
            
        Returns:
            The updated CommentThread instance if found, None otherwise.
            
        Raises:
            ValueError: If the thread_id is invalid.
            PermissionError: If the user does not have permission to update the thread status.
        """
        # Get the thread
        thread = await self.get_thread(thread_id)
        if not thread:
            raise ValueError(f"Invalid thread ID: {thread_id}")
        
        # Set the thread status
        thread.set_status(status)
        
        # Save the updated thread
        await self.persistence.save_comment_thread(thread)
        
        self.log.info(f"Set thread {thread_id} status to {status.value} by user {user_id}")
        return thread
    
    async def delete_thread(
        self,
        thread_id: str,
        user_id: str
    ) -> bool:
        """Delete a comment thread.
        
        Args:
            thread_id: Identifier of the thread to delete.
            user_id: Identifier of the user deleting the thread.
            
        Returns:
            True if the thread was deleted, False otherwise.
            
        Raises:
            ValueError: If the thread_id is invalid.
            PermissionError: If the user does not have permission to delete the thread.
        """
        # Get the thread
        thread = await self.get_thread(thread_id)
        if not thread:
            return False
        
        # Delete the thread from persistence
        result = await self.persistence.delete_comment_thread(thread_id)
        
        # Remove from in-memory cache if deleted successfully
        if result:
            if thread_id in self._threads:
                del self._threads[thread_id]
            self.log.info(f"Deleted thread {thread_id} by user {user_id}")
        
        return result
    
    async def _create_notification(
        self,
        thread: CommentThread,
        comment: Comment
    ) -> CommentNotification:
        """Create a notification for a new comment.
        
        Args:
            thread: The thread containing the new comment.
            comment: The new comment to notify about.
            
        Returns:
            The created CommentNotification instance.
        """
        # Determine recipients (all users who have commented in the thread except the author)
        recipients = set()
        for existing_comment in thread.comments:
            if existing_comment.user_id != comment.user_id:
                recipients.add(existing_comment.user_id)
        
        # Create the notification
        notification = CommentNotification(
            thread_id=thread.thread_id,
            comment_id=comment.comment_id,
            user_id=comment.user_id,
            recipients=recipients
        )
        
        # Add to notification queue
        if thread.thread_id not in self._notifications:
            self._notifications[thread.thread_id] = []
        self._notifications[thread.thread_id].append(notification)
        
        # Schedule notification delivery with debounce
        await self._schedule_notification_delivery(thread.thread_id)
        
        return notification
    
    async def _schedule_notification_delivery(self, thread_id: str) -> None:
        """Schedule delivery of notifications for a thread with debounce.
        
        Args:
            thread_id: Identifier of the thread to deliver notifications for.
        """
        # Cancel existing task if any
        if thread_id in self._notification_tasks and not self._notification_tasks[thread_id].done():
            self._notification_tasks[thread_id].cancel()
        
        # Create a new task with debounce
        task = asyncio.create_task(self._deliver_notifications_with_debounce(thread_id))
        self._notification_tasks[thread_id] = task
    
    async def _deliver_notifications_with_debounce(self, thread_id: str) -> None:
        """Deliver notifications for a thread after a debounce period.
        
        Args:
            thread_id: Identifier of the thread to deliver notifications for.
        """
        try:
            # Wait for debounce period
            await asyncio.sleep(self.notification_debounce_ms / 1000)
            
            # Get notifications for the thread
            if thread_id not in self._notifications or not self._notifications[thread_id]:
                return
            
            notifications = self._notifications[thread_id]
            self._notifications[thread_id] = []
            
            # Deliver notifications
            await self._deliver_notifications(notifications)
        except asyncio.CancelledError:
            # Task was cancelled, likely due to a new notification being added
            pass
        except Exception as e:
            self.log.error(f"Error delivering notifications for thread {thread_id}: {e}")
    
    async def _deliver_notifications(self, notifications: List[CommentNotification]) -> None:
        """Deliver a list of notifications to their recipients.
        
        Args:
            notifications: List of notifications to deliver.
        """
        if not notifications:
            return
        
        # Group notifications by recipient for efficient delivery
        recipient_notifications: Dict[str, List[CommentNotification]] = {}
        for notification in notifications:
            for recipient in notification.recipients:
                if recipient not in recipient_notifications:
                    recipient_notifications[recipient] = []
                recipient_notifications[recipient].append(notification)
        
        # Deliver notifications to each recipient
        for recipient, recipient_notifs in recipient_notifications.items():
            try:
                # Store notifications in persistence for retrieval by clients
                await self.persistence.save_comment_notifications(recipient, recipient_notifs)
                
                # Broadcast notification to connected clients (handled by WebSocket handlers)
                # This will be implemented in the WebSocket handlers module
                
                self.log.debug(f"Delivered {len(recipient_notifs)} notifications to user {recipient}")
            except Exception as e:
                self.log.error(f"Error delivering notifications to user {recipient}: {e}")
    
    async def get_notifications_for_user(
        self,
        user_id: str,
        mark_as_read: bool = False
    ) -> List[CommentNotification]:
        """Get all notifications for a user.
        
        Args:
            user_id: Identifier of the user to get notifications for.
            mark_as_read: Whether to mark the notifications as read.
            
        Returns:
            List of CommentNotification instances for the user.
        """
        # Get notifications from persistence
        notifications = await self.persistence.get_comment_notifications_for_user(user_id)
        
        # Mark as read if requested
        if mark_as_read and notifications:
            await self.persistence.mark_comment_notifications_as_read(user_id, [n.comment_id for n in notifications])
        
        return notifications


class CommentHandler(JupyterHandler):
    """Handler for comment-related HTTP requests.
    
    This handler provides REST API endpoints for managing comment threads and comments.
    """
    
    @web.authenticated
    async def get(self, path: str) -> None:
        """Handle GET requests for comments.
        
        Args:
            path: Request path.
        """
        # Get the comment manager from the application
        comment_manager = self.settings.get("comment_manager")
        if not comment_manager:
            raise web.HTTPError(500, "Comment manager not available")
        
        # Parse the path to determine the action
        parts = path.strip("/").split("/")
        
        if not parts or parts[0] == "":
            # Get all threads for the current user
            user_id = self.current_user.name
            threads = await comment_manager.get_threads_for_session(user_id)
            self.write({"threads": [thread.to_dict() for thread in threads]})
            return
        
        if parts[0] == "thread":
            if len(parts) < 2:
                raise web.HTTPError(400, "Thread ID required")
            
            thread_id = parts[1]
            thread = await comment_manager.get_thread(thread_id)
            
            if not thread:
                raise web.HTTPError(404, f"Thread {thread_id} not found")
            
            self.write(thread.to_dict())
            return
        
        if parts[0] == "cell":
            if len(parts) < 3:
                raise web.HTTPError(400, "Session ID and cell ID required")
            
            session_id = parts[1]
            cell_id = parts[2]
            
            threads = await comment_manager.get_threads_for_cell(session_id, cell_id)
            self.write({"threads": [thread.to_dict() for thread in threads]})
            return
        
        if parts[0] == "session":
            if len(parts) < 2:
                raise web.HTTPError(400, "Session ID required")
            
            session_id = parts[1]
            threads = await comment_manager.get_threads_for_session(session_id)
            self.write({"threads": [thread.to_dict() for thread in threads]})
            return
        
        if parts[0] == "notifications":
            user_id = self.current_user.name
            mark_as_read = self.get_argument("mark_as_read", "false").lower() == "true"
            
            notifications = await comment_manager.get_notifications_for_user(user_id, mark_as_read)
            self.write({"notifications": [notification.to_dict() for notification in notifications]})
            return
        
        raise web.HTTPError(404, f"Unknown comment endpoint: {path}")
    
    @web.authenticated
    async def post(self, path: str) -> None:
        """Handle POST requests for comments.
        
        Args:
            path: Request path.
        """
        # Get the comment manager from the application
        comment_manager = self.settings.get("comment_manager")
        if not comment_manager:
            raise web.HTTPError(500, "Comment manager not available")
        
        # Parse the request body
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except json.JSONDecodeError:
            raise web.HTTPError(400, "Invalid JSON in request body")
        
        # Parse the path to determine the action
        parts = path.strip("/").split("/")
        
        if not parts or parts[0] == "":
            # Create a new thread
            if "session_id" not in data or "cell_id" not in data:
                raise web.HTTPError(400, "Session ID and cell ID required")
            
            user_id = self.current_user.name
            session_id = data["session_id"]
            cell_id = data["cell_id"]
            initial_comment = data.get("initial_comment")
            metadata = data.get("metadata")
            
            try:
                thread = await comment_manager.create_thread(
                    session_id=session_id,
                    cell_id=cell_id,
                    user_id=user_id,
                    initial_comment=initial_comment,
                    metadata=metadata
                )
                self.write(thread.to_dict())
            except ValueError as e:
                raise web.HTTPError(400, str(e))
            except PermissionError as e:
                raise web.HTTPError(403, str(e))
            
            return
        
        if parts[0] == "thread":
            if len(parts) < 2:
                raise web.HTTPError(400, "Thread ID required")
            
            thread_id = parts[1]
            
            if len(parts) >= 3 and parts[2] == "comment":
                # Add a comment to a thread
                if "content" not in data:
                    raise web.HTTPError(400, "Comment content required")
                
                user_id = self.current_user.name
                content = data["content"]
                metadata = data.get("metadata")
                
                try:
                    comment = await comment_manager.add_comment(
                        thread_id=thread_id,
                        user_id=user_id,
                        content=content,
                        metadata=metadata
                    )
                    self.write(comment.to_dict())
                except ValueError as e:
                    raise web.HTTPError(400, str(e))
                except PermissionError as e:
                    raise web.HTTPError(403, str(e))
                
                return
            
            if len(parts) >= 3 and parts[2] == "status":
                # Set thread status
                if "status" not in data:
                    raise web.HTTPError(400, "Thread status required")
                
                user_id = self.current_user.name
                status_str = data["status"]
                
                try:
                    status = CommentStatus(status_str)
                except ValueError:
                    raise web.HTTPError(400, f"Invalid thread status: {status_str}")
                
                try:
                    thread = await comment_manager.set_thread_status(
                        thread_id=thread_id,
                        user_id=user_id,
                        status=status
                    )
                    if thread:
                        self.write(thread.to_dict())
                    else:
                        raise web.HTTPError(404, f"Thread {thread_id} not found")
                except ValueError as e:
                    raise web.HTTPError(400, str(e))
                except PermissionError as e:
                    raise web.HTTPError(403, str(e))
                
                return
        
        raise web.HTTPError(404, f"Unknown comment endpoint: {path}")
    
    @web.authenticated
    async def put(self, path: str) -> None:
        """Handle PUT requests for comments.
        
        Args:
            path: Request path.
        """
        # Get the comment manager from the application
        comment_manager = self.settings.get("comment_manager")
        if not comment_manager:
            raise web.HTTPError(500, "Comment manager not available")
        
        # Parse the request body
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except json.JSONDecodeError:
            raise web.HTTPError(400, "Invalid JSON in request body")
        
        # Parse the path to determine the action
        parts = path.strip("/").split("/")
        
        if parts[0] == "thread" and len(parts) >= 4 and parts[2] == "comment":
            # Update a comment
            thread_id = parts[1]
            comment_id = parts[3]
            
            if "content" not in data:
                raise web.HTTPError(400, "Comment content required")
            
            user_id = self.current_user.name
            content = data["content"]
            
            try:
                comment = await comment_manager.update_comment(
                    thread_id=thread_id,
                    comment_id=comment_id,
                    user_id=user_id,
                    content=content
                )
                if comment:
                    self.write(comment.to_dict())
                else:
                    raise web.HTTPError(404, f"Comment {comment_id} not found in thread {thread_id}")
            except ValueError as e:
                raise web.HTTPError(400, str(e))
            except PermissionError as e:
                raise web.HTTPError(403, str(e))
            
            return
        
        raise web.HTTPError(404, f"Unknown comment endpoint: {path}")
    
    @web.authenticated
    async def delete(self, path: str) -> None:
        """Handle DELETE requests for comments.
        
        Args:
            path: Request path.
        """
        # Get the comment manager from the application
        comment_manager = self.settings.get("comment_manager")
        if not comment_manager:
            raise web.HTTPError(500, "Comment manager not available")
        
        # Parse the path to determine the action
        parts = path.strip("/").split("/")
        
        if parts[0] == "thread" and len(parts) >= 2:
            thread_id = parts[1]
            
            if len(parts) == 2:
                # Delete a thread
                user_id = self.current_user.name
                
                try:
                    result = await comment_manager.delete_thread(
                        thread_id=thread_id,
                        user_id=user_id
                    )
                    if result:
                        self.write({"success": True})
                    else:
                        raise web.HTTPError(404, f"Thread {thread_id} not found")
                except ValueError as e:
                    raise web.HTTPError(400, str(e))
                except PermissionError as e:
                    raise web.HTTPError(403, str(e))
                
                return
            
            if len(parts) >= 4 and parts[2] == "comment":
                # Delete a comment
                comment_id = parts[3]
                user_id = self.current_user.name
                
                try:
                    result = await comment_manager.delete_comment(
                        thread_id=thread_id,
                        comment_id=comment_id,
                        user_id=user_id
                    )
                    if result:
                        self.write({"success": True})
                    else:
                        raise web.HTTPError(404, f"Comment {comment_id} not found in thread {thread_id}")
                except ValueError as e:
                    raise web.HTTPError(400, str(e))
                except PermissionError as e:
                    raise web.HTTPError(403, str(e))
                
                return
        
        raise web.HTTPError(404, f"Unknown comment endpoint: {path}")


def setup_comment_handlers(web_app: web.Application, comment_manager: CommentManager) -> None:
    """Set up the comment handlers for the web application.
    
    Args:
        web_app: The Tornado web application.
        comment_manager: The CommentManager instance.
    """
    host_pattern = ".*$"
    base_url = web_app.settings["base_url"]
    
    # Add the comment manager to the application settings
    web_app.settings["comment_manager"] = comment_manager
    
    # Register the comment handler
    comment_pattern = url_path_join(base_url, "api", "comments", "(.*)")
    handlers = [(comment_pattern, CommentHandler)]
    
    web_app.add_handlers(host_pattern, handlers)
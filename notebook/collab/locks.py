"""Cell locking mechanism for collaborative notebook editing.

This module implements the server-side component of the cell locking mechanism,
preventing editing conflicts by allowing only one user to edit a cell at a time.
It manages lock acquisition, release, timeout handling, and conflict resolution.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any

from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.websocket import WebSocketHandler

from notebook.collab.persistence import CollaborationPersistence
from notebook.collab.permissions import PermissionManager

# Configure logger
logger = logging.getLogger(__name__)

# Lock timeout in seconds (default: 5 minutes)
DEFAULT_LOCK_TIMEOUT = 300

# Lock cleanup interval in milliseconds (default: 30 seconds)
LOCK_CLEANUP_INTERVAL = 30000

# Lock types
class LockType:
    """Enumeration of lock types."""
    EDIT = "edit"  # Lock for editing a cell
    EXECUTE = "execute"  # Lock for executing a cell
    METADATA = "metadata"  # Lock for changing cell metadata


class LockStatus:
    """Enumeration of lock statuses."""
    ACQUIRED = "acquired"  # Lock successfully acquired
    DENIED = "denied"  # Lock acquisition denied
    RELEASED = "released"  # Lock successfully released
    EXPIRED = "expired"  # Lock expired due to timeout
    OVERRIDE = "override"  # Lock forcibly overridden by admin


class Lock:
    """Represents a cell lock in a collaborative notebook."""
    
    def __init__(self, 
                 document_id: str, 
                 cell_id: str, 
                 user_id: str, 
                 lock_type: str = LockType.EDIT,
                 timeout: int = DEFAULT_LOCK_TIMEOUT):
        """Initialize a new lock.
        
        Args:
            document_id: ID of the notebook document
            cell_id: ID of the cell being locked
            user_id: ID of the user acquiring the lock
            lock_type: Type of lock (edit, execute, metadata)
            timeout: Lock timeout in seconds
        """
        self.document_id = document_id
        self.cell_id = cell_id
        self.user_id = user_id
        self.lock_type = lock_type
        self.acquired_at = time.time()
        self.expires_at = self.acquired_at + timeout
        self.timeout = timeout
        self.last_activity = self.acquired_at
        
    def is_expired(self) -> bool:
        """Check if the lock has expired.
        
        Returns:
            True if the lock has expired, False otherwise
        """
        return time.time() > self.expires_at
    
    def update_activity(self) -> None:
        """Update the last activity timestamp and extend the expiration time."""
        self.last_activity = time.time()
        self.expires_at = self.last_activity + self.timeout
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the lock to a dictionary for serialization.
        
        Returns:
            Dictionary representation of the lock
        """
        return {
            "document_id": self.document_id,
            "cell_id": self.cell_id,
            "user_id": self.user_id,
            "lock_type": self.lock_type,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "last_activity": self.last_activity,
            "timeout": self.timeout
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Lock':
        """Create a lock from a dictionary.
        
        Args:
            data: Dictionary representation of a lock
            
        Returns:
            A new Lock instance
        """
        lock = cls(
            document_id=data["document_id"],
            cell_id=data["cell_id"],
            user_id=data["user_id"],
            lock_type=data["lock_type"],
            timeout=data["timeout"]
        )
        lock.acquired_at = data["acquired_at"]
        lock.expires_at = data["expires_at"]
        lock.last_activity = data["last_activity"]
        return lock


class LockManager:
    """Manages cell locks for collaborative notebook editing."""
    
    def __init__(self, persistence: CollaborationPersistence, permission_manager: PermissionManager):
        """Initialize the lock manager.
        
        Args:
            persistence: Persistence layer for storing locks
            permission_manager: Permission manager for checking user permissions
        """
        self.persistence = persistence
        self.permission_manager = permission_manager
        
        # In-memory cache of active locks: {document_id: {cell_id: Lock}}
        self._locks: Dict[str, Dict[str, Lock]] = {}
        
        # Set of connected clients by user_id
        self._connected_users: Set[str] = set()
        
        # Start periodic cleanup of expired locks
        self._cleanup_task = PeriodicCallback(
            self._cleanup_expired_locks,
            LOCK_CLEANUP_INTERVAL
        )
        self._cleanup_task.start()
        
        # Load existing locks from persistence
        IOLoop.current().add_callback(self._load_locks)
    
    async def _load_locks(self) -> None:
        """Load existing locks from persistence layer."""
        try:
            locks_data = await self.persistence.get_all_locks()
            for lock_data in locks_data:
                lock = Lock.from_dict(lock_data)
                if not lock.is_expired():
                    self._add_lock_to_cache(lock)
            logger.info(f"Loaded {len(locks_data)} locks from persistence")
        except Exception as e:
            logger.error(f"Error loading locks from persistence: {e}")
    
    def _add_lock_to_cache(self, lock: Lock) -> None:
        """Add a lock to the in-memory cache.
        
        Args:
            lock: The lock to add
        """
        if lock.document_id not in self._locks:
            self._locks[lock.document_id] = {}
        self._locks[lock.document_id][lock.cell_id] = lock
    
    def _remove_lock_from_cache(self, document_id: str, cell_id: str) -> None:
        """Remove a lock from the in-memory cache.
        
        Args:
            document_id: ID of the notebook document
            cell_id: ID of the cell
        """
        if document_id in self._locks and cell_id in self._locks[document_id]:
            del self._locks[document_id][cell_id]
            if not self._locks[document_id]:
                del self._locks[document_id]
    
    async def acquire_lock(self, 
                          document_id: str, 
                          cell_id: str, 
                          user_id: str, 
                          lock_type: str = LockType.EDIT,
                          force: bool = False) -> Tuple[str, Optional[Lock]]:
        """Attempt to acquire a lock on a cell.
        
        Args:
            document_id: ID of the notebook document
            cell_id: ID of the cell to lock
            user_id: ID of the user requesting the lock
            lock_type: Type of lock (edit, execute, metadata)
            force: Whether to force acquire the lock (admin override)
            
        Returns:
            Tuple of (status, lock) where status is one of the LockStatus values
            and lock is the acquired lock or None if acquisition failed
        """
        # Check if user has permission to edit this cell
        has_permission = await self.permission_manager.check_cell_permission(
            document_id, cell_id, user_id, "edit"
        )
        
        if not has_permission and not force:
            logger.warning(f"User {user_id} denied lock on {document_id}/{cell_id} due to permissions")
            return LockStatus.DENIED, None
        
        # Check if cell is already locked
        existing_lock = self._get_lock(document_id, cell_id)
        
        # If there's an existing lock
        if existing_lock:
            # If it's the same user, just update the activity timestamp
            if existing_lock.user_id == user_id:
                existing_lock.update_activity()
                await self.persistence.update_lock(existing_lock.to_dict())
                return LockStatus.ACQUIRED, existing_lock
            
            # If it's expired, release it and continue with acquisition
            if existing_lock.is_expired():
                await self.release_lock(document_id, cell_id, existing_lock.user_id, expired=True)
            # If force flag is set and user has admin permission, override the lock
            elif force:
                is_admin = await self.permission_manager.check_document_permission(
                    document_id, user_id, "admin"
                )
                if is_admin:
                    await self.release_lock(document_id, cell_id, existing_lock.user_id, override=True, override_by=user_id)
                else:
                    logger.warning(f"User {user_id} attempted to force acquire lock without admin permission")
                    return LockStatus.DENIED, None
            else:
                # Lock is valid and held by another user
                logger.info(f"Lock acquisition denied for {user_id} on {document_id}/{cell_id}, already locked by {existing_lock.user_id}")
                return LockStatus.DENIED, None
        
        # Create and store the new lock
        lock = Lock(document_id, cell_id, user_id, lock_type)
        self._add_lock_to_cache(lock)
        await self.persistence.add_lock(lock.to_dict())
        
        logger.info(f"Lock acquired for {user_id} on {document_id}/{cell_id}")
        return LockStatus.ACQUIRED, lock
    
    async def release_lock(self, 
                          document_id: str, 
                          cell_id: str, 
                          user_id: str, 
                          expired: bool = False,
                          override: bool = False,
                          override_by: Optional[str] = None) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Release a lock on a cell.
        
        Args:
            document_id: ID of the notebook document
            cell_id: ID of the cell
            user_id: ID of the user releasing the lock
            expired: Whether the lock is being released due to expiration
            override: Whether the lock is being forcibly released (admin override)
            override_by: ID of the admin user overriding the lock
            
        Returns:
            Tuple of (status, lock_info) where status is one of the LockStatus values
            and lock_info contains information about the released lock
        """
        lock = self._get_lock(document_id, cell_id)
        
        if not lock:
            logger.warning(f"Attempted to release non-existent lock on {document_id}/{cell_id}")
            return LockStatus.RELEASED, None
        
        # Only the lock owner or an admin can release a lock
        if lock.user_id != user_id and not override:
            is_admin = await self.permission_manager.check_document_permission(
                document_id, user_id, "admin"
            )
            if not is_admin:
                logger.warning(f"User {user_id} denied lock release on {document_id}/{cell_id}, owned by {lock.user_id}")
                return LockStatus.DENIED, None
        
        # Prepare lock info for notification
        lock_info = {
            "document_id": document_id,
            "cell_id": cell_id,
            "user_id": lock.user_id,
            "lock_type": lock.lock_type,
            "released_by": user_id,
            "expired": expired,
            "override": override,
            "override_by": override_by
        }
        
        # Remove the lock
        self._remove_lock_from_cache(document_id, cell_id)
        await self.persistence.remove_lock(document_id, cell_id)
        
        status = LockStatus.EXPIRED if expired else LockStatus.OVERRIDE if override else LockStatus.RELEASED
        logger.info(f"Lock released for {lock.user_id} on {document_id}/{cell_id} (status: {status})")
        
        return status, lock_info
    
    def _get_lock(self, document_id: str, cell_id: str) -> Optional[Lock]:
        """Get the current lock for a cell if it exists.
        
        Args:
            document_id: ID of the notebook document
            cell_id: ID of the cell
            
        Returns:
            The Lock object if found, None otherwise
        """
        if document_id in self._locks and cell_id in self._locks[document_id]:
            return self._locks[document_id][cell_id]
        return None
    
    async def get_document_locks(self, document_id: str) -> List[Dict[str, Any]]:
        """Get all locks for a document.
        
        Args:
            document_id: ID of the notebook document
            
        Returns:
            List of lock dictionaries for the document
        """
        if document_id not in self._locks:
            return []
        
        return [lock.to_dict() for lock in self._locks[document_id].values()]
    
    async def check_lock(self, document_id: str, cell_id: str, user_id: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Check if a user can edit a cell.
        
        Args:
            document_id: ID of the notebook document
            cell_id: ID of the cell
            user_id: ID of the user
            
        Returns:
            Tuple of (can_edit, lock_info) where can_edit is True if the user can edit the cell
            and lock_info contains information about any existing lock
        """
        lock = self._get_lock(document_id, cell_id)
        
        # No lock exists, user can edit
        if not lock:
            return True, None
        
        # Lock exists but is expired, clean it up and allow edit
        if lock.is_expired():
            status, lock_info = await self.release_lock(document_id, cell_id, lock.user_id, expired=True)
            return True, lock_info
        
        # User holds the lock, can edit
        if lock.user_id == user_id:
            lock.update_activity()
            await self.persistence.update_lock(lock.to_dict())
            return True, lock.to_dict()
        
        # Another user holds the lock, cannot edit
        return False, lock.to_dict()
    
    async def _cleanup_expired_locks(self) -> None:
        """Periodically clean up expired locks."""
        try:
            documents_to_check = list(self._locks.keys())
            for document_id in documents_to_check:
                if document_id not in self._locks:
                    continue
                    
                cells_to_check = list(self._locks[document_id].keys())
                for cell_id in cells_to_check:
                    if cell_id not in self._locks[document_id]:
                        continue
                        
                    lock = self._locks[document_id][cell_id]
                    if lock.is_expired():
                        logger.info(f"Cleaning up expired lock for {lock.user_id} on {document_id}/{cell_id}")
                        await self.release_lock(document_id, cell_id, lock.user_id, expired=True)
        except Exception as e:
            logger.error(f"Error during lock cleanup: {e}")
    
    async def user_connected(self, user_id: str) -> None:
        """Track a user connection.
        
        Args:
            user_id: ID of the connected user
        """
        self._connected_users.add(user_id)
    
    async def user_disconnected(self, user_id: str) -> List[Dict[str, Any]]:
        """Handle user disconnection by releasing their locks.
        
        Args:
            user_id: ID of the disconnected user
            
        Returns:
            List of released lock information
        """
        self._connected_users.discard(user_id)
        
        # Find all locks held by this user
        released_locks = []
        documents_to_check = list(self._locks.keys())
        
        for document_id in documents_to_check:
            if document_id not in self._locks:
                continue
                
            cells_to_check = list(self._locks[document_id].keys())
            for cell_id in cells_to_check:
                if cell_id not in self._locks[document_id]:
                    continue
                    
                lock = self._locks[document_id][cell_id]
                if lock.user_id == user_id:
                    status, lock_info = await self.release_lock(
                        document_id, cell_id, user_id, expired=True
                    )
                    if lock_info:
                        released_locks.append(lock_info)
        
        if released_locks:
            logger.info(f"Released {len(released_locks)} locks for disconnected user {user_id}")
        
        return released_locks


class LockHandler:
    """Handles lock-related WebSocket messages."""
    
    def __init__(self, lock_manager: LockManager):
        """Initialize the lock handler.
        
        Args:
            lock_manager: The lock manager instance
        """
        self.lock_manager = lock_manager
    
    async def handle_message(self, message: Dict[str, Any], handler: WebSocketHandler) -> Optional[Dict[str, Any]]:
        """Handle a lock-related WebSocket message.
        
        Args:
            message: The message to handle
            handler: The WebSocket handler instance
            
        Returns:
            Response message to send back to the client, or None if no response is needed
        """
        action = message.get("action")
        document_id = message.get("document_id")
        cell_id = message.get("cell_id")
        user_id = message.get("user_id")
        lock_type = message.get("lock_type", LockType.EDIT)
        force = message.get("force", False)
        
        if not all([action, document_id, user_id]):
            return {
                "type": "lock_error",
                "error": "Missing required fields",
                "message_id": message.get("message_id")
            }
        
        if action == "acquire":
            if not cell_id:
                return {
                    "type": "lock_error",
                    "error": "Missing cell_id for lock acquisition",
                    "message_id": message.get("message_id")
                }
                
            status, lock = await self.lock_manager.acquire_lock(
                document_id, cell_id, user_id, lock_type, force
            )
            
            response = {
                "type": "lock_response",
                "action": "acquire",
                "status": status,
                "document_id": document_id,
                "cell_id": cell_id,
                "user_id": user_id,
                "message_id": message.get("message_id")
            }
            
            if lock:
                response["lock"] = lock.to_dict()
            
            return response
            
        elif action == "release":
            if not cell_id:
                return {
                    "type": "lock_error",
                    "error": "Missing cell_id for lock release",
                    "message_id": message.get("message_id")
                }
                
            status, lock_info = await self.lock_manager.release_lock(
                document_id, cell_id, user_id, 
                override=force, 
                override_by=user_id if force else None
            )
            
            response = {
                "type": "lock_response",
                "action": "release",
                "status": status,
                "document_id": document_id,
                "cell_id": cell_id,
                "user_id": user_id,
                "message_id": message.get("message_id")
            }
            
            if lock_info:
                response["lock_info"] = lock_info
            
            return response
            
        elif action == "check":
            if not cell_id:
                return {
                    "type": "lock_error",
                    "error": "Missing cell_id for lock check",
                    "message_id": message.get("message_id")
                }
                
            can_edit, lock_info = await self.lock_manager.check_lock(
                document_id, cell_id, user_id
            )
            
            response = {
                "type": "lock_response",
                "action": "check",
                "can_edit": can_edit,
                "document_id": document_id,
                "cell_id": cell_id,
                "user_id": user_id,
                "message_id": message.get("message_id")
            }
            
            if lock_info:
                response["lock_info"] = lock_info
            
            return response
            
        elif action == "list":
            locks = await self.lock_manager.get_document_locks(document_id)
            
            return {
                "type": "lock_response",
                "action": "list",
                "document_id": document_id,
                "locks": locks,
                "message_id": message.get("message_id")
            }
            
        else:
            return {
                "type": "lock_error",
                "error": f"Unknown lock action: {action}",
                "message_id": message.get("message_id")
            }
    
    async def handle_connection(self, user_id: str) -> None:
        """Handle a new WebSocket connection.
        
        Args:
            user_id: ID of the connected user
        """
        await self.lock_manager.user_connected(user_id)
    
    async def handle_disconnection(self, user_id: str) -> List[Dict[str, Any]]:
        """Handle a WebSocket disconnection.
        
        Args:
            user_id: ID of the disconnected user
            
        Returns:
            List of released lock information
        """
        return await self.lock_manager.user_disconnected(user_id)
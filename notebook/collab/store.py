"""Persistence layer for collaborative documents in Jupyter Notebook.

This module implements the storage and retrieval of collaborative editing state,
including CRDT document updates, user awareness information, cell locks, comments,
and document history. It provides both in-memory storage for development and
persistent file-based storage for production deployments.
"""

import asyncio
import base64
import datetime
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union, BinaryIO
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# Import pycrdt for Yjs CRDT functionality
try:
    import pycrdt
    from pycrdt import Doc, TransactionEvent
    HAS_PYCRDT = True
except ImportError:
    HAS_PYCRDT = False

# Import pycrdt-websocket for WebSocket protocol handling
try:
    import pycrdt_websocket
    from pycrdt_websocket.protocol import (
        encode_state_as_update,
        encode_state_vector,
        decode_state_vector,
        decode_update,
    )
    HAS_PYCRDT_WEBSOCKET = True
except ImportError:
    HAS_PYCRDT_WEBSOCKET = False

from jupyter_server.utils import ensure_async
from traitlets.config import Configurable
from traitlets import Bool, Dict as TDict, Float, Integer, Unicode, default

# Set up logging
logger = logging.getLogger('notebook.collab.store')


class CollaborationStore(ABC):
    """Abstract base class for collaboration data storage.
    
    This class defines the interface for storing and retrieving collaboration data,
    including CRDT document updates, user awareness information, cell locks,
    comments, and document history.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the store.
        
        This method should be called before using the store to ensure
        that any necessary setup is performed.
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Shut down the store.
        
        This method should be called when the store is no longer needed
        to ensure that any resources are properly released.
        """
        pass
    
    @abstractmethod
    async def save_document(self, notebook_id: str, update: bytes) -> None:
        """Save a CRDT document update.
        
        Args:
            notebook_id: The notebook ID
            update: The CRDT update as bytes
        """
        pass
    
    @abstractmethod
    async def load_document(self, notebook_id: str) -> Optional[bytes]:
        """Load the latest CRDT document state.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[bytes]: The CRDT document state as bytes, or None if not found
        """
        pass
    
    @abstractmethod
    async def save_awareness(self, notebook_id: str, awareness: Dict[str, Any]) -> None:
        """Save user awareness information.
        
        Args:
            notebook_id: The notebook ID
            awareness: The awareness information as a dictionary
        """
        pass
    
    @abstractmethod
    async def load_awareness(self, notebook_id: str) -> Optional[Dict[str, Any]]:
        """Load user awareness information.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[Dict[str, Any]]: The awareness information, or None if not found
        """
        pass
    
    @abstractmethod
    async def save_cell_locks(self, notebook_id: str, locks: Dict[str, str]) -> None:
        """Save cell lock state.
        
        Args:
            notebook_id: The notebook ID
            locks: Dictionary mapping cell IDs to user IDs
        """
        pass
    
    @abstractmethod
    async def load_cell_locks(self, notebook_id: str) -> Optional[Dict[str, str]]:
        """Load cell lock state.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[Dict[str, str]]: Dictionary mapping cell IDs to user IDs, or None if not found
        """
        pass
    
    @abstractmethod
    async def save_comment(self, notebook_id: str, comment: Dict[str, Any]) -> None:
        """Save a comment.
        
        Args:
            notebook_id: The notebook ID
            comment: The comment data as a dictionary
        """
        pass
    
    @abstractmethod
    async def update_comment(self, notebook_id: str, comment_id: str, comment: Dict[str, Any]) -> None:
        """Update an existing comment.
        
        Args:
            notebook_id: The notebook ID
            comment_id: The comment ID
            comment: The updated comment data
        """
        pass
    
    @abstractmethod
    async def delete_comment(self, notebook_id: str, comment_id: str) -> None:
        """Delete a comment.
        
        Args:
            notebook_id: The notebook ID
            comment_id: The comment ID
        """
        pass
    
    @abstractmethod
    async def load_comments(self, notebook_id: str) -> List[Dict[str, Any]]:
        """Load all comments for a notebook.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            List[Dict[str, Any]]: List of comment dictionaries
        """
        pass
    
    @abstractmethod
    async def save_document_snapshot(self, notebook_id: str, snapshot: bytes, metadata: Dict[str, Any]) -> str:
        """Save a document snapshot for version history.
        
        Args:
            notebook_id: The notebook ID
            snapshot: The document snapshot as bytes
            metadata: Snapshot metadata (timestamp, author, etc.)
            
        Returns:
            str: The snapshot ID
        """
        pass
    
    @abstractmethod
    async def load_document_snapshot(self, notebook_id: str, snapshot_id: str) -> Tuple[Optional[bytes], Optional[Dict[str, Any]]]:
        """Load a document snapshot.
        
        Args:
            notebook_id: The notebook ID
            snapshot_id: The snapshot ID
            
        Returns:
            Tuple[Optional[bytes], Optional[Dict[str, Any]]]: The snapshot and its metadata, or (None, None) if not found
        """
        pass
    
    @abstractmethod
    async def list_document_snapshots(self, notebook_id: str) -> List[Dict[str, Any]]:
        """List all snapshots for a notebook.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            List[Dict[str, Any]]: List of snapshot metadata
        """
        pass
    
    @abstractmethod
    async def delete_document_snapshot(self, notebook_id: str, snapshot_id: str) -> None:
        """Delete a document snapshot.
        
        Args:
            notebook_id: The notebook ID
            snapshot_id: The snapshot ID
        """
        pass
    
    @abstractmethod
    async def save_permissions(self, notebook_id: str, permissions: Dict[str, Any]) -> None:
        """Save permission settings for a notebook.
        
        Args:
            notebook_id: The notebook ID
            permissions: The permission settings
        """
        pass
    
    @abstractmethod
    async def load_permissions(self, notebook_id: str) -> Optional[Dict[str, Any]]:
        """Load permission settings for a notebook.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[Dict[str, Any]]: The permission settings, or None if not found
        """
        pass
    
    @abstractmethod
    async def cleanup_notebook(self, notebook_id: str) -> None:
        """Clean up all collaboration data for a notebook.
        
        This method should be called when a notebook is deleted to ensure
        that all associated collaboration data is also removed.
        
        Args:
            notebook_id: The notebook ID
        """
        pass
    
    @abstractmethod
    async def list_notebooks(self) -> List[str]:
        """List all notebooks with collaboration data.
        
        Returns:
            List[str]: List of notebook IDs
        """
        pass


class MemoryCollaborationStore(CollaborationStore):
    """In-memory implementation of the collaboration store.
    
    This implementation stores all data in memory and is suitable for
    development and testing. Data is lost when the server is restarted.
    """
    
    def __init__(self):
        """Initialize the in-memory store."""
        # Document updates (notebook_id -> list of updates)
        self._documents: Dict[str, List[bytes]] = {}
        
        # Document state (notebook_id -> latest state)
        self._document_states: Dict[str, bytes] = {}
        
        # Awareness information (notebook_id -> awareness data)
        self._awareness: Dict[str, Dict[str, Any]] = {}
        
        # Cell locks (notebook_id -> {cell_id -> user_id})
        self._cell_locks: Dict[str, Dict[str, str]] = {}
        
        # Comments (notebook_id -> list of comments)
        self._comments: Dict[str, List[Dict[str, Any]]] = {}
        
        # Document snapshots (notebook_id -> {snapshot_id -> (snapshot, metadata)})
        self._snapshots: Dict[str, Dict[str, Tuple[bytes, Dict[str, Any]]]] = {}
        
        # Permissions (notebook_id -> permissions)
        self._permissions: Dict[str, Dict[str, Any]] = {}
    
    async def initialize(self) -> None:
        """Initialize the store.
        
        For the in-memory store, this is a no-op.
        """
        pass
    
    async def shutdown(self) -> None:
        """Shut down the store.
        
        For the in-memory store, this is a no-op.
        """
        pass
    
    async def save_document(self, notebook_id: str, update: bytes) -> None:
        """Save a CRDT document update.
        
        Args:
            notebook_id: The notebook ID
            update: The CRDT update as bytes
        """
        if notebook_id not in self._documents:
            self._documents[notebook_id] = []
        
        # Append the update to the list
        self._documents[notebook_id].append(update)
        
        # If we have a document state, apply the update
        if notebook_id in self._document_states and HAS_PYCRDT:
            try:
                # Create a temporary document
                doc = Doc()
                
                # Apply the current state
                doc.apply_update(self._document_states[notebook_id])
                
                # Apply the new update
                doc.apply_update(update)
                
                # Store the new state
                self._document_states[notebook_id] = encode_state_as_update(doc)
            except Exception as e:
                logger.error(f"Error applying update to document state: {e}")
        else:
            # Just store the update as the current state
            self._document_states[notebook_id] = update
    
    async def load_document(self, notebook_id: str) -> Optional[bytes]:
        """Load the latest CRDT document state.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[bytes]: The CRDT document state as bytes, or None if not found
        """
        return self._document_states.get(notebook_id)
    
    async def save_awareness(self, notebook_id: str, awareness: Dict[str, Any]) -> None:
        """Save user awareness information.
        
        Args:
            notebook_id: The notebook ID
            awareness: The awareness information as a dictionary
        """
        self._awareness[notebook_id] = awareness
    
    async def load_awareness(self, notebook_id: str) -> Optional[Dict[str, Any]]:
        """Load user awareness information.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[Dict[str, Any]]: The awareness information, or None if not found
        """
        return self._awareness.get(notebook_id)
    
    async def save_cell_locks(self, notebook_id: str, locks: Dict[str, str]) -> None:
        """Save cell lock state.
        
        Args:
            notebook_id: The notebook ID
            locks: Dictionary mapping cell IDs to user IDs
        """
        self._cell_locks[notebook_id] = locks
    
    async def load_cell_locks(self, notebook_id: str) -> Optional[Dict[str, str]]:
        """Load cell lock state.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[Dict[str, str]]: Dictionary mapping cell IDs to user IDs, or None if not found
        """
        return self._cell_locks.get(notebook_id)
    
    async def save_comment(self, notebook_id: str, comment: Dict[str, Any]) -> None:
        """Save a comment.
        
        Args:
            notebook_id: The notebook ID
            comment: The comment data as a dictionary
        """
        if notebook_id not in self._comments:
            self._comments[notebook_id] = []
        
        # Ensure the comment has an ID
        if 'id' not in comment:
            comment['id'] = str(uuid.uuid4())
        
        # Add timestamp if not present
        if 'timestamp' not in comment:
            comment['timestamp'] = time.time()
        
        self._comments[notebook_id].append(comment)
    
    async def update_comment(self, notebook_id: str, comment_id: str, comment: Dict[str, Any]) -> None:
        """Update an existing comment.
        
        Args:
            notebook_id: The notebook ID
            comment_id: The comment ID
            comment: The updated comment data
        """
        if notebook_id not in self._comments:
            return
        
        # Find the comment by ID
        for i, existing_comment in enumerate(self._comments[notebook_id]):
            if existing_comment.get('id') == comment_id:
                # Update the comment
                comment['id'] = comment_id  # Ensure ID is preserved
                comment['updatedAt'] = time.time()  # Add update timestamp
                self._comments[notebook_id][i] = comment
                break
    
    async def delete_comment(self, notebook_id: str, comment_id: str) -> None:
        """Delete a comment.
        
        Args:
            notebook_id: The notebook ID
            comment_id: The comment ID
        """
        if notebook_id not in self._comments:
            return
        
        # Filter out the comment with the given ID
        self._comments[notebook_id] = [
            comment for comment in self._comments[notebook_id]
            if comment.get('id') != comment_id
        ]
    
    async def load_comments(self, notebook_id: str) -> List[Dict[str, Any]]:
        """Load all comments for a notebook.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            List[Dict[str, Any]]: List of comment dictionaries
        """
        return self._comments.get(notebook_id, [])
    
    async def save_document_snapshot(self, notebook_id: str, snapshot: bytes, metadata: Dict[str, Any]) -> str:
        """Save a document snapshot for version history.
        
        Args:
            notebook_id: The notebook ID
            snapshot: The document snapshot as bytes
            metadata: Snapshot metadata (timestamp, author, etc.)
            
        Returns:
            str: The snapshot ID
        """
        if notebook_id not in self._snapshots:
            self._snapshots[notebook_id] = {}
        
        # Generate a snapshot ID if not provided
        snapshot_id = metadata.get('id', str(uuid.uuid4()))
        
        # Add timestamp if not present
        if 'timestamp' not in metadata:
            metadata['timestamp'] = time.time()
        
        # Store the snapshot and metadata
        self._snapshots[notebook_id][snapshot_id] = (snapshot, metadata)
        
        return snapshot_id
    
    async def load_document_snapshot(self, notebook_id: str, snapshot_id: str) -> Tuple[Optional[bytes], Optional[Dict[str, Any]]]:
        """Load a document snapshot.
        
        Args:
            notebook_id: The notebook ID
            snapshot_id: The snapshot ID
            
        Returns:
            Tuple[Optional[bytes], Optional[Dict[str, Any]]]: The snapshot and its metadata, or (None, None) if not found
        """
        if notebook_id not in self._snapshots or snapshot_id not in self._snapshots[notebook_id]:
            return None, None
        
        return self._snapshots[notebook_id][snapshot_id]
    
    async def list_document_snapshots(self, notebook_id: str) -> List[Dict[str, Any]]:
        """List all snapshots for a notebook.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            List[Dict[str, Any]]: List of snapshot metadata
        """
        if notebook_id not in self._snapshots:
            return []
        
        # Return a list of metadata dictionaries with snapshot IDs
        return [
            {**metadata, 'id': snapshot_id}
            for snapshot_id, (_, metadata) in self._snapshots[notebook_id].items()
        ]
    
    async def delete_document_snapshot(self, notebook_id: str, snapshot_id: str) -> None:
        """Delete a document snapshot.
        
        Args:
            notebook_id: The notebook ID
            snapshot_id: The snapshot ID
        """
        if notebook_id in self._snapshots and snapshot_id in self._snapshots[notebook_id]:
            del self._snapshots[notebook_id][snapshot_id]
    
    async def save_permissions(self, notebook_id: str, permissions: Dict[str, Any]) -> None:
        """Save permission settings for a notebook.
        
        Args:
            notebook_id: The notebook ID
            permissions: The permission settings
        """
        self._permissions[notebook_id] = permissions
    
    async def load_permissions(self, notebook_id: str) -> Optional[Dict[str, Any]]:
        """Load permission settings for a notebook.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[Dict[str, Any]]: The permission settings, or None if not found
        """
        return self._permissions.get(notebook_id)
    
    async def cleanup_notebook(self, notebook_id: str) -> None:
        """Clean up all collaboration data for a notebook.
        
        Args:
            notebook_id: The notebook ID
        """
        # Remove all data for this notebook
        self._documents.pop(notebook_id, None)
        self._document_states.pop(notebook_id, None)
        self._awareness.pop(notebook_id, None)
        self._cell_locks.pop(notebook_id, None)
        self._comments.pop(notebook_id, None)
        self._snapshots.pop(notebook_id, None)
        self._permissions.pop(notebook_id, None)
    
    async def list_notebooks(self) -> List[str]:
        """List all notebooks with collaboration data.
        
        Returns:
            List[str]: List of notebook IDs
        """
        # Collect all notebook IDs from all data stores
        notebook_ids = set()
        notebook_ids.update(self._documents.keys())
        notebook_ids.update(self._document_states.keys())
        notebook_ids.update(self._awareness.keys())
        notebook_ids.update(self._cell_locks.keys())
        notebook_ids.update(self._comments.keys())
        notebook_ids.update(self._snapshots.keys())
        notebook_ids.update(self._permissions.keys())
        
        return list(notebook_ids)


class FileCollaborationStore(CollaborationStore, Configurable):
    """File-based implementation of the collaboration store.
    
    This implementation stores data in files on disk and is suitable for
    production deployments. Data is persisted between server restarts.
    """
    
    # Configuration options
    collab_dir = Unicode(
        default_value=None,
        allow_none=True,
        help="Directory for storing collaboration data. If None, a default directory will be used."
    ).tag(config=True)
    
    buffer_flush_period = Float(
        default_value=2.0,
        help="Time in seconds between periodic buffer flushes"
    ).tag(config=True)
    
    buffer_size_limit = Integer(
        default_value=1048576,  # 1MB
        help="Maximum buffer size in bytes before forced flush"
    ).tag(config=True)
    
    use_binary_format = Bool(
        default_value=True,
        help="Whether to use binary format for CRDT updates"
    ).tag(config=True)
    
    snapshot_interval = Integer(
        default_value=100,
        help="Number of updates between automatic snapshots"
    ).tag(config=True)
    
    snapshot_cache_size = Integer(
        default_value=100,
        help="Maximum number of snapshots to keep in memory cache"
    ).tag(config=True)
    
    retention_days = Integer(
        default_value=90,
        help="Number of days to retain collaboration history"
    ).tag(config=True)
    
    def __init__(self, **kwargs):
        """Initialize the file-based store."""
        super().__init__(**kwargs)
        
        # Set up the collaboration directory
        if self.collab_dir is None:
            # Use default directory in Jupyter data dir
            from jupyter_core.paths import jupyter_data_dir
            self.collab_dir = os.path.join(jupyter_data_dir(), 'collab')
        
        # Create the directory if it doesn't exist
        os.makedirs(self.collab_dir, exist_ok=True)
        
        # Create subdirectories
        self._updates_dir = os.path.join(self.collab_dir, 'updates')
        self._snapshots_dir = os.path.join(self.collab_dir, 'snapshots')
        self._awareness_dir = os.path.join(self.collab_dir, 'awareness')
        self._locks_dir = os.path.join(self.collab_dir, 'locks')
        self._comments_dir = os.path.join(self.collab_dir, 'comments')
        self._permissions_dir = os.path.join(self.collab_dir, 'permissions')
        
        for directory in [self._updates_dir, self._snapshots_dir, self._awareness_dir,
                         self._locks_dir, self._comments_dir, self._permissions_dir]:
            os.makedirs(directory, exist_ok=True)
        
        # In-memory buffers for updates
        self._update_buffers: Dict[str, List[bytes]] = {}
        self._buffer_sizes: Dict[str, int] = {}
        
        # Snapshot cache
        self._snapshot_cache: Dict[str, Dict[str, Tuple[bytes, Dict[str, Any]]]] = {}
        
        # Update counters for snapshot creation
        self._update_counters: Dict[str, int] = {}
        
        # Locks for file operations
        self._file_locks: Dict[str, asyncio.Lock] = {}
        
        # Thread pool for file I/O operations
        self._executor = ThreadPoolExecutor(max_workers=4)
        
        # Periodic flush task
        self._flush_task = None
    
    async def initialize(self) -> None:
        """Initialize the store.
        
        This method sets up the periodic flush task and performs any
        necessary initialization.
        """
        # Start the periodic flush task
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._periodic_flush())
    
    async def shutdown(self) -> None:
        """Shut down the store.
        
        This method performs cleanup tasks such as flushing buffers and
        shutting down the thread pool executor.
        """
        # Cancel the periodic flush task
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Flush all buffers
        await self._flush_all_buffers()
        
        # Shut down the thread pool executor
        self._executor.shutdown(wait=True)
    
    async def _periodic_flush(self) -> None:
        """Periodically flush update buffers to disk."""
        try:
            while True:
                await asyncio.sleep(self.buffer_flush_period)
                await self._flush_all_buffers()
        except asyncio.CancelledError:
            # Final flush before cancellation
            await self._flush_all_buffers()
            raise
        except Exception as e:
            logger.error(f"Error in periodic flush task: {e}")
            # Only restart if this is still the active task
            if self._flush_task and self._flush_task.done():
                self._flush_task = asyncio.create_task(self._periodic_flush())
    
    async def _flush_all_buffers(self) -> None:
        """Flush all update buffers to disk."""
        for notebook_id in list(self._update_buffers.keys()):
            await self._flush_buffer(notebook_id)
    
    async def _flush_buffer(self, notebook_id: str) -> None:
        """Flush the update buffer for a notebook to disk.
        
        Args:
            notebook_id: The notebook ID
        """
        if notebook_id not in self._update_buffers or not self._update_buffers[notebook_id]:
            return
        
        # Get the lock for this notebook
        lock = self._get_file_lock(f"updates_{notebook_id}")
        async with lock:
            try:
                # Get the updates to flush
                updates = self._update_buffers[notebook_id]
                self._update_buffers[notebook_id] = []
                self._buffer_sizes[notebook_id] = 0
                
                # Write the updates to the file
                updates_file = os.path.join(self._updates_dir, f"{notebook_id}.yjsupdates")
                
                # Use a thread for file I/O
                await asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    partial(self._append_updates_to_file, updates_file, updates)
                )
                
                # Check if we need to create a snapshot
                self._update_counters[notebook_id] = self._update_counters.get(notebook_id, 0) + len(updates)
                if self._update_counters[notebook_id] >= self.snapshot_interval:
                    # Reset the counter
                    self._update_counters[notebook_id] = 0
                    
                    # Create a snapshot in the background
                    asyncio.create_task(self._create_snapshot(notebook_id))
            except Exception as e:
                logger.error(f"Error flushing update buffer for {notebook_id}: {e}")
                # Put the updates back in the buffer
                if notebook_id not in self._update_buffers:
                    self._update_buffers[notebook_id] = []
                self._update_buffers[notebook_id].extend(updates)
                self._buffer_sizes[notebook_id] = sum(len(update) for update in self._update_buffers[notebook_id])
    
    def _append_updates_to_file(self, file_path: str, updates: List[bytes]) -> None:
        """Append updates to a file.
        
        Args:
            file_path: The file path
            updates: The updates to append
        """
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Append the updates to the file
        with open(file_path, 'ab') as f:
            for update in updates:
                # Write the update length as a 4-byte integer
                f.write(len(update).to_bytes(4, byteorder='big'))
                # Write the update
                f.write(update)
    
    async def _create_snapshot(self, notebook_id: str) -> None:
        """Create a snapshot of the document state.
        
        Args:
            notebook_id: The notebook ID
        """
        try:
            # Load the document state
            state = await self.load_document(notebook_id)
            if not state:
                return
            
            # Create metadata for the snapshot
            metadata = {
                'timestamp': time.time(),
                'automatic': True,
                'updateCount': self._update_counters.get(notebook_id, 0)
            }
            
            # Save the snapshot
            await self.save_document_snapshot(notebook_id, state, metadata)
        except Exception as e:
            logger.error(f"Error creating snapshot for {notebook_id}: {e}")
    
    def _get_file_lock(self, key: str) -> asyncio.Lock:
        """Get a lock for file operations.
        
        Args:
            key: The lock key
            
        Returns:
            asyncio.Lock: The lock
        """
        if key not in self._file_locks:
            self._file_locks[key] = asyncio.Lock()
        return self._file_locks[key]
    
    async def save_document(self, notebook_id: str, update: bytes) -> None:
        """Save a CRDT document update.
        
        Args:
            notebook_id: The notebook ID
            update: The CRDT update as bytes
        """
        # Add the update to the buffer
        if notebook_id not in self._update_buffers:
            self._update_buffers[notebook_id] = []
            self._buffer_sizes[notebook_id] = 0
        
        self._update_buffers[notebook_id].append(update)
        self._buffer_sizes[notebook_id] += len(update)
        
        # Flush if the buffer is too large
        if self._buffer_sizes[notebook_id] >= self.buffer_size_limit:
            await self._flush_buffer(notebook_id)
    
    async def load_document(self, notebook_id: str) -> Optional[bytes]:
        """Load the latest CRDT document state.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[bytes]: The CRDT document state as bytes, or None if not found
        """
        # Check if we have any updates in the buffer
        if notebook_id in self._update_buffers and self._update_buffers[notebook_id]:
            # Flush the buffer to ensure we have the latest state on disk
            await self._flush_buffer(notebook_id)
        
        # Try to load the latest snapshot first
        snapshots = await self.list_document_snapshots(notebook_id)
        if snapshots:
            # Sort by timestamp (newest first)
            snapshots.sort(key=lambda s: s.get('timestamp', 0), reverse=True)
            snapshot_id = snapshots[0]['id']
            snapshot, _ = await self.load_document_snapshot(notebook_id, snapshot_id)
            if snapshot:
                return snapshot
        
        # If no snapshot is available, reconstruct from updates
        updates_file = os.path.join(self._updates_dir, f"{notebook_id}.yjsupdates")
        if not os.path.exists(updates_file):
            return None
        
        # Use a thread for file I/O
        updates = await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(self._read_updates_from_file, updates_file)
        )
        
        if not updates:
            return None
        
        # Reconstruct the document state
        if HAS_PYCRDT:
            try:
                doc = Doc()
                for update in updates:
                    doc.apply_update(update)
                return encode_state_as_update(doc)
            except Exception as e:
                logger.error(f"Error reconstructing document state: {e}")
                # Return the last update as a fallback
                return updates[-1]
        else:
            # If pycrdt is not available, just return the last update
            return updates[-1]
    
    def _read_updates_from_file(self, file_path: str) -> List[bytes]:
        """Read updates from a file.
        
        Args:
            file_path: The file path
            
        Returns:
            List[bytes]: The updates
        """
        if not os.path.exists(file_path):
            return []
        
        updates = []
        try:
            with open(file_path, 'rb') as f:
                while True:
                    # Read the update length (4 bytes)
                    length_bytes = f.read(4)
                    if not length_bytes or len(length_bytes) < 4:
                        break
                    
                    # Convert to integer
                    length = int.from_bytes(length_bytes, byteorder='big')
                    
                    # Read the update
                    update = f.read(length)
                    if not update or len(update) < length:
                        break
                    
                    updates.append(update)
        except Exception as e:
            logger.error(f"Error reading updates from {file_path}: {e}")
        
        return updates
    
    async def save_awareness(self, notebook_id: str, awareness: Dict[str, Any]) -> None:
        """Save user awareness information.
        
        Args:
            notebook_id: The notebook ID
            awareness: The awareness information as a dictionary
        """
        awareness_file = os.path.join(self._awareness_dir, f"{notebook_id}.json")
        
        # Use a thread for file I/O
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(self._write_json_file, awareness_file, awareness)
        )
    
    async def load_awareness(self, notebook_id: str) -> Optional[Dict[str, Any]]:
        """Load user awareness information.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[Dict[str, Any]]: The awareness information, or None if not found
        """
        awareness_file = os.path.join(self._awareness_dir, f"{notebook_id}.json")
        
        # Use a thread for file I/O
        return await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(self._read_json_file, awareness_file)
        )
    
    async def save_cell_locks(self, notebook_id: str, locks: Dict[str, str]) -> None:
        """Save cell lock state.
        
        Args:
            notebook_id: The notebook ID
            locks: Dictionary mapping cell IDs to user IDs
        """
        locks_file = os.path.join(self._locks_dir, f"{notebook_id}.json")
        
        # Use a thread for file I/O
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(self._write_json_file, locks_file, locks)
        )
    
    async def load_cell_locks(self, notebook_id: str) -> Optional[Dict[str, str]]:
        """Load cell lock state.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[Dict[str, str]]: Dictionary mapping cell IDs to user IDs, or None if not found
        """
        locks_file = os.path.join(self._locks_dir, f"{notebook_id}.json")
        
        # Use a thread for file I/O
        return await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(self._read_json_file, locks_file)
        )
    
    async def save_comment(self, notebook_id: str, comment: Dict[str, Any]) -> None:
        """Save a comment.
        
        Args:
            notebook_id: The notebook ID
            comment: The comment data as a dictionary
        """
        # Ensure the comment has an ID
        if 'id' not in comment:
            comment['id'] = str(uuid.uuid4())
        
        # Add timestamp if not present
        if 'timestamp' not in comment:
            comment['timestamp'] = time.time()
        
        # Load existing comments
        comments = await self.load_comments(notebook_id)
        
        # Add the new comment
        comments.append(comment)
        
        # Save all comments
        comments_file = os.path.join(self._comments_dir, f"{notebook_id}.json")
        
        # Use a thread for file I/O
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(self._write_json_file, comments_file, comments)
        )
    
    async def update_comment(self, notebook_id: str, comment_id: str, comment: Dict[str, Any]) -> None:
        """Update an existing comment.
        
        Args:
            notebook_id: The notebook ID
            comment_id: The comment ID
            comment: The updated comment data
        """
        # Load existing comments
        comments = await self.load_comments(notebook_id)
        
        # Find the comment by ID
        for i, existing_comment in enumerate(comments):
            if existing_comment.get('id') == comment_id:
                # Update the comment
                comment['id'] = comment_id  # Ensure ID is preserved
                comment['updatedAt'] = time.time()  # Add update timestamp
                comments[i] = comment
                break
        else:
            # Comment not found
            return
        
        # Save all comments
        comments_file = os.path.join(self._comments_dir, f"{notebook_id}.json")
        
        # Use a thread for file I/O
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(self._write_json_file, comments_file, comments)
        )
    
    async def delete_comment(self, notebook_id: str, comment_id: str) -> None:
        """Delete a comment.
        
        Args:
            notebook_id: The notebook ID
            comment_id: The comment ID
        """
        # Load existing comments
        comments = await self.load_comments(notebook_id)
        
        # Filter out the comment with the given ID
        comments = [comment for comment in comments if comment.get('id') != comment_id]
        
        # Save all comments
        comments_file = os.path.join(self._comments_dir, f"{notebook_id}.json")
        
        # Use a thread for file I/O
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(self._write_json_file, comments_file, comments)
        )
    
    async def load_comments(self, notebook_id: str) -> List[Dict[str, Any]]:
        """Load all comments for a notebook.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            List[Dict[str, Any]]: List of comment dictionaries
        """
        comments_file = os.path.join(self._comments_dir, f"{notebook_id}.json")
        
        # Use a thread for file I/O
        comments = await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(self._read_json_file, comments_file)
        )
        
        return comments or []
    
    async def save_document_snapshot(self, notebook_id: str, snapshot: bytes, metadata: Dict[str, Any]) -> str:
        """Save a document snapshot for version history.
        
        Args:
            notebook_id: The notebook ID
            snapshot: The document snapshot as bytes
            metadata: Snapshot metadata (timestamp, author, etc.)
            
        Returns:
            str: The snapshot ID
        """
        # Generate a snapshot ID if not provided
        snapshot_id = metadata.get('id', str(uuid.uuid4()))
        metadata['id'] = snapshot_id
        
        # Add timestamp if not present
        if 'timestamp' not in metadata:
            metadata['timestamp'] = time.time()
        
        # Create the snapshots directory for this notebook
        notebook_snapshots_dir = os.path.join(self._snapshots_dir, notebook_id)
        os.makedirs(notebook_snapshots_dir, exist_ok=True)
        
        # Save the snapshot
        snapshot_file = os.path.join(notebook_snapshots_dir, f"{snapshot_id}.bin")
        metadata_file = os.path.join(notebook_snapshots_dir, f"{snapshot_id}.json")
        
        # Use threads for file I/O
        await asyncio.gather(
            asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(self._write_binary_file, snapshot_file, snapshot)
            ),
            asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(self._write_json_file, metadata_file, metadata)
            )
        )
        
        # Update the snapshot cache
        if notebook_id not in self._snapshot_cache:
            self._snapshot_cache[notebook_id] = {}
        
        # Limit the cache size
        if len(self._snapshot_cache[notebook_id]) >= self.snapshot_cache_size:
            # Remove the oldest snapshot from the cache
            oldest_id = min(
                self._snapshot_cache[notebook_id].keys(),
                key=lambda sid: self._snapshot_cache[notebook_id][sid][1].get('timestamp', 0)
            )
            del self._snapshot_cache[notebook_id][oldest_id]
        
        # Add to cache
        self._snapshot_cache[notebook_id][snapshot_id] = (snapshot, metadata)
        
        return snapshot_id
    
    async def load_document_snapshot(self, notebook_id: str, snapshot_id: str) -> Tuple[Optional[bytes], Optional[Dict[str, Any]]]:
        """Load a document snapshot.
        
        Args:
            notebook_id: The notebook ID
            snapshot_id: The snapshot ID
            
        Returns:
            Tuple[Optional[bytes], Optional[Dict[str, Any]]]: The snapshot and its metadata, or (None, None) if not found
        """
        # Check the cache first
        if notebook_id in self._snapshot_cache and snapshot_id in self._snapshot_cache[notebook_id]:
            return self._snapshot_cache[notebook_id][snapshot_id]
        
        # Load from disk
        notebook_snapshots_dir = os.path.join(self._snapshots_dir, notebook_id)
        snapshot_file = os.path.join(notebook_snapshots_dir, f"{snapshot_id}.bin")
        metadata_file = os.path.join(notebook_snapshots_dir, f"{snapshot_id}.json")
        
        if not os.path.exists(snapshot_file) or not os.path.exists(metadata_file):
            return None, None
        
        # Use threads for file I/O
        snapshot, metadata = await asyncio.gather(
            asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(self._read_binary_file, snapshot_file)
            ),
            asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(self._read_json_file, metadata_file)
            )
        )
        
        if snapshot is None or metadata is None:
            return None, None
        
        # Update the cache
        if notebook_id not in self._snapshot_cache:
            self._snapshot_cache[notebook_id] = {}
        
        # Limit the cache size
        if len(self._snapshot_cache[notebook_id]) >= self.snapshot_cache_size:
            # Remove the oldest snapshot from the cache
            oldest_id = min(
                self._snapshot_cache[notebook_id].keys(),
                key=lambda sid: self._snapshot_cache[notebook_id][sid][1].get('timestamp', 0)
            )
            del self._snapshot_cache[notebook_id][oldest_id]
        
        # Add to cache
        self._snapshot_cache[notebook_id][snapshot_id] = (snapshot, metadata)
        
        return snapshot, metadata
    
    async def list_document_snapshots(self, notebook_id: str) -> List[Dict[str, Any]]:
        """List all snapshots for a notebook.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            List[Dict[str, Any]]: List of snapshot metadata
        """
        notebook_snapshots_dir = os.path.join(self._snapshots_dir, notebook_id)
        if not os.path.exists(notebook_snapshots_dir):
            return []
        
        # Use a thread for file I/O
        snapshot_files = await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(os.listdir, notebook_snapshots_dir)
        )
        
        # Find all metadata files
        metadata_files = [f for f in snapshot_files if f.endswith('.json')]
        
        # Load metadata for each snapshot
        metadata_list = []
        for metadata_file in metadata_files:
            snapshot_id = metadata_file[:-5]  # Remove .json extension
            metadata_path = os.path.join(notebook_snapshots_dir, metadata_file)
            
            # Use a thread for file I/O
            metadata = await asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(self._read_json_file, metadata_path)
            )
            
            if metadata:
                metadata['id'] = snapshot_id
                metadata_list.append(metadata)
        
        return metadata_list
    
    async def delete_document_snapshot(self, notebook_id: str, snapshot_id: str) -> None:
        """Delete a document snapshot.
        
        Args:
            notebook_id: The notebook ID
            snapshot_id: The snapshot ID
        """
        # Remove from cache
        if notebook_id in self._snapshot_cache and snapshot_id in self._snapshot_cache[notebook_id]:
            del self._snapshot_cache[notebook_id][snapshot_id]
        
        # Remove from disk
        notebook_snapshots_dir = os.path.join(self._snapshots_dir, notebook_id)
        snapshot_file = os.path.join(notebook_snapshots_dir, f"{snapshot_id}.bin")
        metadata_file = os.path.join(notebook_snapshots_dir, f"{snapshot_id}.json")
        
        # Use threads for file I/O
        await asyncio.gather(
            asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(self._delete_file_if_exists, snapshot_file)
            ),
            asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(self._delete_file_if_exists, metadata_file)
            )
        )
    
    async def save_permissions(self, notebook_id: str, permissions: Dict[str, Any]) -> None:
        """Save permission settings for a notebook.
        
        Args:
            notebook_id: The notebook ID
            permissions: The permission settings
        """
        permissions_file = os.path.join(self._permissions_dir, f"{notebook_id}.json")
        
        # Use a thread for file I/O
        await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(self._write_json_file, permissions_file, permissions)
        )
    
    async def load_permissions(self, notebook_id: str) -> Optional[Dict[str, Any]]:
        """Load permission settings for a notebook.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[Dict[str, Any]]: The permission settings, or None if not found
        """
        permissions_file = os.path.join(self._permissions_dir, f"{notebook_id}.json")
        
        # Use a thread for file I/O
        return await asyncio.get_event_loop().run_in_executor(
            self._executor,
            partial(self._read_json_file, permissions_file)
        )
    
    async def cleanup_notebook(self, notebook_id: str) -> None:
        """Clean up all collaboration data for a notebook.
        
        Args:
            notebook_id: The notebook ID
        """
        # Flush any pending updates
        if notebook_id in self._update_buffers and self._update_buffers[notebook_id]:
            await self._flush_buffer(notebook_id)
        
        # Remove from caches
        self._update_buffers.pop(notebook_id, None)
        self._buffer_sizes.pop(notebook_id, None)
        self._update_counters.pop(notebook_id, None)
        self._snapshot_cache.pop(notebook_id, None)
        
        # Remove files
        files_to_delete = [
            os.path.join(self._updates_dir, f"{notebook_id}.yjsupdates"),
            os.path.join(self._awareness_dir, f"{notebook_id}.json"),
            os.path.join(self._locks_dir, f"{notebook_id}.json"),
            os.path.join(self._comments_dir, f"{notebook_id}.json"),
            os.path.join(self._permissions_dir, f"{notebook_id}.json")
        ]
        
        # Use threads for file I/O
        await asyncio.gather(*[
            asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(self._delete_file_if_exists, file_path)
            )
            for file_path in files_to_delete
        ])
        
        # Remove snapshots directory
        notebook_snapshots_dir = os.path.join(self._snapshots_dir, notebook_id)
        if os.path.exists(notebook_snapshots_dir):
            await asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(shutil.rmtree, notebook_snapshots_dir, ignore_errors=True)
            )
    
    async def list_notebooks(self) -> List[str]:
        """List all notebooks with collaboration data.
        
        Returns:
            List[str]: List of notebook IDs
        """
        # Collect notebook IDs from all directories
        notebook_ids = set()
        
        # Check updates directory
        if os.path.exists(self._updates_dir):
            update_files = await asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(os.listdir, self._updates_dir)
            )
            for file_name in update_files:
                if file_name.endswith('.yjsupdates'):
                    notebook_ids.add(file_name[:-11])  # Remove .yjsupdates extension
        
        # Check other directories
        for directory, extension in [
            (self._awareness_dir, '.json'),
            (self._locks_dir, '.json'),
            (self._comments_dir, '.json'),
            (self._permissions_dir, '.json')
        ]:
            if os.path.exists(directory):
                files = await asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    partial(os.listdir, directory)
                )
                for file_name in files:
                    if file_name.endswith(extension):
                        notebook_ids.add(file_name[:-len(extension)])
        
        # Check snapshots directory
        if os.path.exists(self._snapshots_dir):
            snapshot_dirs = await asyncio.get_event_loop().run_in_executor(
                self._executor,
                partial(os.listdir, self._snapshots_dir)
            )
            notebook_ids.update(snapshot_dirs)
        
        return list(notebook_ids)
    
    def _write_json_file(self, file_path: str, data: Any) -> None:
        """Write data to a JSON file.
        
        Args:
            file_path: The file path
            data: The data to write
        """
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write to a temporary file first
        temp_file = f"{file_path}.tmp"
        try:
            with open(temp_file, 'w') as f:
                json.dump(data, f)
            
            # Rename to the target file (atomic operation)
            os.replace(temp_file, file_path)
        except Exception as e:
            logger.error(f"Error writing JSON file {file_path}: {e}")
            # Clean up the temporary file
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
    
    def _read_json_file(self, file_path: str) -> Optional[Any]:
        """Read data from a JSON file.
        
        Args:
            file_path: The file path
            
        Returns:
            Optional[Any]: The data, or None if the file doesn't exist or is invalid
        """
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading JSON file {file_path}: {e}")
            return None
    
    def _write_binary_file(self, file_path: str, data: bytes) -> None:
        """Write binary data to a file.
        
        Args:
            file_path: The file path
            data: The data to write
        """
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write to a temporary file first
        temp_file = f"{file_path}.tmp"
        try:
            with open(temp_file, 'wb') as f:
                f.write(data)
            
            # Rename to the target file (atomic operation)
            os.replace(temp_file, file_path)
        except Exception as e:
            logger.error(f"Error writing binary file {file_path}: {e}")
            # Clean up the temporary file
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
    
    def _read_binary_file(self, file_path: str) -> Optional[bytes]:
        """Read binary data from a file.
        
        Args:
            file_path: The file path
            
        Returns:
            Optional[bytes]: The data, or None if the file doesn't exist
        """
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'rb') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading binary file {file_path}: {e}")
            return None
    
    def _delete_file_if_exists(self, file_path: str) -> None:
        """Delete a file if it exists.
        
        Args:
            file_path: The file path
        """
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Error deleting file {file_path}: {e}")


class CollaborationStoreMaintenance:
    """Maintenance tasks for collaboration stores.
    
    This class provides methods for performing maintenance tasks on
    collaboration stores, such as cleaning up old data and checking
    for consistency.
    """
    
    @staticmethod
    async def cleanup_old_data(store: CollaborationStore, days: int = 90) -> Dict[str, int]:
        """Clean up old collaboration data.
        
        This method removes data that is older than the specified number of days.
        
        Args:
            store: The collaboration store
            days: The number of days to retain data
            
        Returns:
            Dict[str, int]: Statistics about the cleanup operation
        """
        if not isinstance(store, FileCollaborationStore):
            # Only file-based stores need cleanup
            return {'notebooks': 0, 'snapshots': 0}
        
        # Calculate the cutoff timestamp
        cutoff_time = time.time() - (days * 86400)  # 86400 seconds per day
        
        # Get all notebooks
        notebooks = await store.list_notebooks()
        
        # Statistics
        stats = {
            'notebooks': 0,
            'snapshots': 0
        }
        
        # Process each notebook
        for notebook_id in notebooks:
            # Get snapshots for this notebook
            snapshots = await store.list_document_snapshots(notebook_id)
            
            # Find old snapshots
            old_snapshots = [
                snapshot for snapshot in snapshots
                if snapshot.get('timestamp', 0) < cutoff_time
            ]
            
            # Delete old snapshots, keeping at least one
            if len(old_snapshots) < len(snapshots):
                for snapshot in old_snapshots:
                    await store.delete_document_snapshot(notebook_id, snapshot['id'])
                    stats['snapshots'] += 1
        
        return stats
    
    @staticmethod
    async def check_consistency(store: CollaborationStore) -> Dict[str, Any]:
        """Check the consistency of collaboration data.
        
        This method checks for inconsistencies in the collaboration data,
        such as missing files or corrupted data.
        
        Args:
            store: The collaboration store
            
        Returns:
            Dict[str, Any]: Consistency check results
        """
        if not isinstance(store, FileCollaborationStore):
            # Only file-based stores need consistency checks
            return {'status': 'ok', 'issues': []}
        
        # Get all notebooks
        notebooks = await store.list_notebooks()
        
        # Results
        results = {
            'status': 'ok',
            'issues': []
        }
        
        # Process each notebook
        for notebook_id in notebooks:
            # Check if the document state can be loaded
            try:
                state = await store.load_document(notebook_id)
                if state is None:
                    results['issues'].append({
                        'notebook_id': notebook_id,
                        'issue': 'missing_document_state'
                    })
                    results['status'] = 'issues_found'
            except Exception as e:
                results['issues'].append({
                    'notebook_id': notebook_id,
                    'issue': 'document_state_error',
                    'error': str(e)
                })
                results['status'] = 'issues_found'
            
            # Check if snapshots can be loaded
            try:
                snapshots = await store.list_document_snapshots(notebook_id)
                for snapshot in snapshots:
                    try:
                        snapshot_data, metadata = await store.load_document_snapshot(
                            notebook_id, snapshot['id']
                        )
                        if snapshot_data is None or metadata is None:
                            results['issues'].append({
                                'notebook_id': notebook_id,
                                'snapshot_id': snapshot['id'],
                                'issue': 'missing_snapshot_data'
                            })
                            results['status'] = 'issues_found'
                    except Exception as e:
                        results['issues'].append({
                            'notebook_id': notebook_id,
                            'snapshot_id': snapshot['id'],
                            'issue': 'snapshot_error',
                            'error': str(e)
                        })
                        results['status'] = 'issues_found'
            except Exception as e:
                results['issues'].append({
                    'notebook_id': notebook_id,
                    'issue': 'snapshot_list_error',
                    'error': str(e)
                })
                results['status'] = 'issues_found'
        
        return results


def create_collaboration_store(store_type: str = 'file', **kwargs) -> CollaborationStore:
    """Create a collaboration store of the specified type.
    
    Args:
        store_type: The type of store to create ('memory' or 'file')
        **kwargs: Additional arguments to pass to the store constructor
        
    Returns:
        CollaborationStore: The created store
        
    Raises:
        ValueError: If the store type is invalid
    """
    if store_type.lower() == 'memory':
        return MemoryCollaborationStore(**kwargs)
    elif store_type.lower() == 'file':
        return FileCollaborationStore(**kwargs)
    else:
        raise ValueError(f"Invalid collaboration store type: {store_type}")


# Usage example:
"""
# Create a file-based collaboration store
store = create_collaboration_store('file')

# Initialize the store
await store.initialize()

try:
    # Save a document update
    await store.save_document('notebook-123', update_bytes)
    
    # Load the document state
    state = await store.load_document('notebook-123')
    
    # Save user awareness information
    await store.save_awareness('notebook-123', {
        'user1': {'cursor': {'line': 5, 'ch': 10}, 'selection': {...}},
        'user2': {'cursor': {'line': 10, 'ch': 0}, 'selection': {...}}
    })
    
    # Save cell locks
    await store.save_cell_locks('notebook-123', {
        'cell-1': 'user1',
        'cell-2': 'user2'
    })
    
    # Save a comment
    await store.save_comment('notebook-123', {
        'cellId': 'cell-1',
        'userId': 'user1',
        'content': 'This code needs optimization',
        'timestamp': time.time()
    })
    
    # Create a document snapshot
    snapshot_id = await store.save_document_snapshot('notebook-123', snapshot_bytes, {
        'author': 'user1',
        'message': 'Checkpoint before refactoring',
        'timestamp': time.time()
    })
    
    # Clean up old data
    stats = await CollaborationStoreMaintenance.cleanup_old_data(store, days=30)
    
    # Check consistency
    consistency = await CollaborationStoreMaintenance.check_consistency(store)
    if consistency['status'] != 'ok':
        print(f"Consistency issues found: {consistency['issues']}")

finally:
    # Always shut down the store properly when done
    await store.shutdown()
"""
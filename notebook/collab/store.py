"""Persistence layer for collaborative documents in Jupyter Notebook.

This module implements the storage and retrieval mechanisms for collaborative editing data,
including CRDT document updates, user awareness information, cell locks, comments, and
document history. It provides both in-memory and persistent storage options.
"""

import asyncio
import json
import logging
import os
import time
import zlib
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union, BinaryIO
from functools import lru_cache

import tornado.web
from jupyter_server.utils import ensure_async
from tornado.ioloop import IOLoop

# Configure logger
logger = logging.getLogger(__name__)


class StorageBackend(Enum):
    """Enumeration of available storage backends."""

    MEMORY = "memory"  # In-memory storage (for development/testing)
    FILE = "file"  # File-based storage (default for production)


class CollaborationFileTypes(Enum):
    """Enumeration of collaboration file types."""

    UPDATES = "yjsupdates"  # Yjs document updates
    AWARENESS = "awareness.json"  # User awareness information
    LOCKS = "locks.json"  # Cell lock state
    COMMENTS = "comments.json"  # Comments and review threads
    PERMISSIONS = "permissions.json"  # Access control configuration
    HISTORY = "history"  # Directory for history snapshots


class CollaborationStore:
    """Base class for collaboration document storage.
    
    This class defines the interface for storing and retrieving collaboration data,
    including CRDT document updates, user awareness information, cell locks,
    comments, and document history.
    
    The store supports both in-memory storage for development and persistent storage
    for production deployments. It implements a hybrid persistence strategy with
    real-time updates, periodic state snapshots, and session lifecycle events.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the collaboration store.
        
        Args:
            config: Configuration options for the store
        """
        self.config = config or {}
        self.buffer_flush_period = self.config.get("buffer_flush_period", 2.0)  # seconds
        self.buffer_size_limit = self.config.get("buffer_size_limit", 1048576)  # 1MB
        self.compression_level = self.config.get("compression_level", 6)  # ZLIB compression level
        self.use_binary_format = self.config.get("use_binary_format", True)
        self.snapshot_interval = self.config.get("snapshot_interval", 100)  # operations
        self.snapshot_time_interval = self.config.get("snapshot_time_interval", 300)  # seconds
        
        # Initialize buffers and counters
        self._update_buffers: Dict[str, List[bytes]] = {}
        self._update_counters: Dict[str, int] = {}
        self._last_snapshot_time: Dict[str, float] = {}
        self._flush_tasks: Dict[str, asyncio.Task] = {}
        
    async def initialize(self) -> None:
        """Initialize the store and ensure required directories exist."""
        pass
        
    async def shutdown(self) -> None:
        """Perform cleanup operations before shutdown."""
        # Flush all pending updates
        for doc_id in list(self._update_buffers.keys()):
            await self.flush_updates(doc_id)
            
        # Cancel all pending flush tasks
        for task in self._flush_tasks.values():
            if not task.done():
                task.cancel()
                
        try:
            await asyncio.gather(*self._flush_tasks.values(), return_exceptions=True)
        except asyncio.CancelledError:
            pass
    
    async def document_exists(self, doc_id: str) -> bool:
        """Check if a collaborative document exists.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            True if the document exists, False otherwise
        """
        raise NotImplementedError()
    
    async def create_document(self, doc_id: str, initial_data: Optional[Dict[str, Any]] = None) -> None:
        """Create a new collaborative document.
        
        Args:
            doc_id: Document identifier
            initial_data: Initial document data (optional)
        """
        raise NotImplementedError()
    
    async def delete_document(self, doc_id: str) -> None:
        """Delete a collaborative document and all associated data.
        
        Args:
            doc_id: Document identifier
        """
        raise NotImplementedError()
    
    async def list_documents(self) -> List[str]:
        """List all collaborative documents.
        
        Returns:
            List of document identifiers
        """
        raise NotImplementedError()
    
    async def append_updates(self, doc_id: str, updates: bytes) -> None:
        """Append CRDT updates to the document update log.
        
        This method buffers updates in memory and periodically flushes them to
        persistent storage for efficiency.
        
        Args:
            doc_id: Document identifier
            updates: Binary Yjs update data
        """
        # Initialize buffer if needed
        if doc_id not in self._update_buffers:
            self._update_buffers[doc_id] = []
            self._update_counters[doc_id] = 0
            self._last_snapshot_time[doc_id] = time.time()
        
        # Add update to buffer
        self._update_buffers[doc_id].append(updates)
        self._update_counters[doc_id] += 1
        
        # Schedule flush if not already scheduled
        if doc_id not in self._flush_tasks or self._flush_tasks[doc_id].done():
            self._flush_tasks[doc_id] = asyncio.create_task(
                self._schedule_flush(doc_id)
            )
        
        # Immediate flush if buffer exceeds size limit
        buffer_size = sum(len(update) for update in self._update_buffers[doc_id])
        if buffer_size >= self.buffer_size_limit:
            await self.flush_updates(doc_id)
    
    async def _schedule_flush(self, doc_id: str) -> None:
        """Schedule a delayed flush of updates for a document.
        
        Args:
            doc_id: Document identifier
        """
        try:
            await asyncio.sleep(self.buffer_flush_period)
            await self.flush_updates(doc_id)
        except asyncio.CancelledError:
            # If cancelled, still try to flush
            await self.flush_updates(doc_id)
            raise
    
    async def flush_updates(self, doc_id: str) -> None:
        """Flush buffered updates to persistent storage.
        
        Args:
            doc_id: Document identifier
        """
        if doc_id not in self._update_buffers or not self._update_buffers[doc_id]:
            return
        
        updates = self._update_buffers[doc_id]
        self._update_buffers[doc_id] = []
        
        # Check if we need to create a snapshot
        create_snapshot = False
        if self._update_counters[doc_id] >= self.snapshot_interval:
            create_snapshot = True
            self._update_counters[doc_id] = 0
        
        current_time = time.time()
        if current_time - self._last_snapshot_time[doc_id] >= self.snapshot_time_interval:
            create_snapshot = True
            self._last_snapshot_time[doc_id] = current_time
        
        # Perform the actual storage operation (implemented by subclasses)
        await self._store_updates(doc_id, updates, create_snapshot)
    
    async def _store_updates(self, doc_id: str, updates: List[bytes], create_snapshot: bool) -> None:
        """Store updates in the persistent storage.
        
        Args:
            doc_id: Document identifier
            updates: List of binary Yjs update data
            create_snapshot: Whether to create a snapshot
        """
        raise NotImplementedError()
    
    async def get_updates(self, doc_id: str, from_version: Optional[int] = None) -> List[bytes]:
        """Get CRDT updates for a document.
        
        Args:
            doc_id: Document identifier
            from_version: Optional version to start from (None for all updates)
            
        Returns:
            List of binary Yjs update data
        """
        raise NotImplementedError()
    
    async def get_awareness(self, doc_id: str) -> Dict[str, Any]:
        """Get awareness state for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing awareness state
        """
        raise NotImplementedError()
    
    async def update_awareness(self, doc_id: str, awareness: Dict[str, Any]) -> None:
        """Update awareness state for a document.
        
        Args:
            doc_id: Document identifier
            awareness: Dictionary containing awareness state
        """
        raise NotImplementedError()
    
    async def get_locks(self, doc_id: str) -> Dict[str, Any]:
        """Get lock state for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing lock state
        """
        raise NotImplementedError()
    
    async def update_locks(self, doc_id: str, locks: Dict[str, Any]) -> None:
        """Update lock state for a document.
        
        Args:
            doc_id: Document identifier
            locks: Dictionary containing lock state
        """
        raise NotImplementedError()
    
    async def get_comments(self, doc_id: str) -> Dict[str, Any]:
        """Get comments for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing comments
        """
        raise NotImplementedError()
    
    async def update_comments(self, doc_id: str, comments: Dict[str, Any]) -> None:
        """Update comments for a document.
        
        Args:
            doc_id: Document identifier
            comments: Dictionary containing comments
        """
        raise NotImplementedError()
    
    async def get_permissions(self, doc_id: str) -> Dict[str, Any]:
        """Get permissions for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing permissions
        """
        raise NotImplementedError()
    
    async def update_permissions(self, doc_id: str, permissions: Dict[str, Any]) -> None:
        """Update permissions for a document.
        
        Args:
            doc_id: Document identifier
            permissions: Dictionary containing permissions
        """
        raise NotImplementedError()
    
    async def create_snapshot(self, doc_id: str, state: bytes) -> None:
        """Create a snapshot of the document state.
        
        Args:
            doc_id: Document identifier
            state: Binary Yjs document state
        """
        raise NotImplementedError()
    
    async def get_snapshot(self, doc_id: str, version: Optional[int] = None) -> Optional[bytes]:
        """Get a snapshot of the document state.
        
        Args:
            doc_id: Document identifier
            version: Optional version to retrieve (None for latest)
            
        Returns:
            Binary Yjs document state or None if not found
        """
        raise NotImplementedError()
    
    async def get_document_metadata(self, doc_id: str) -> Dict[str, Any]:
        """Get metadata for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing document metadata
        """
        raise NotImplementedError()


class MemoryCollaborationStore(CollaborationStore):
    """In-memory implementation of the collaboration store.
    
    This implementation stores all data in memory and is suitable for development
    and testing environments. Data is lost when the server is restarted.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the in-memory collaboration store.
        
        Args:
            config: Configuration options for the store
        """
        super().__init__(config)
        
        # Initialize in-memory storage
        self._documents: Set[str] = set()
        self._updates: Dict[str, List[bytes]] = {}
        self._awareness: Dict[str, Dict[str, Any]] = {}
        self._locks: Dict[str, Dict[str, Any]] = {}
        self._comments: Dict[str, Dict[str, Any]] = {}
        self._permissions: Dict[str, Dict[str, Any]] = {}
        self._snapshots: Dict[str, List[Tuple[int, bytes]]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
    
    async def initialize(self) -> None:
        """Initialize the store."""
        # Nothing to do for in-memory store
        pass
    
    async def document_exists(self, doc_id: str) -> bool:
        """Check if a collaborative document exists.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            True if the document exists, False otherwise
        """
        return doc_id in self._documents
    
    async def create_document(self, doc_id: str, initial_data: Optional[Dict[str, Any]] = None) -> None:
        """Create a new collaborative document.
        
        Args:
            doc_id: Document identifier
            initial_data: Initial document data (optional)
        """
        if await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} already exists")
        
        self._documents.add(doc_id)
        self._updates[doc_id] = []
        self._awareness[doc_id] = {}
        self._locks[doc_id] = {}
        self._comments[doc_id] = {}
        self._permissions[doc_id] = {}
        self._snapshots[doc_id] = []
        
        # Initialize metadata
        self._metadata[doc_id] = {
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "version": 0,
            "snapshot_count": 0,
        }
        
        # Apply initial data if provided
        if initial_data:
            if "awareness" in initial_data:
                self._awareness[doc_id] = initial_data["awareness"]
            if "locks" in initial_data:
                self._locks[doc_id] = initial_data["locks"]
            if "comments" in initial_data:
                self._comments[doc_id] = initial_data["comments"]
            if "permissions" in initial_data:
                self._permissions[doc_id] = initial_data["permissions"]
    
    async def delete_document(self, doc_id: str) -> None:
        """Delete a collaborative document and all associated data.
        
        Args:
            doc_id: Document identifier
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        self._documents.remove(doc_id)
        del self._updates[doc_id]
        del self._awareness[doc_id]
        del self._locks[doc_id]
        del self._comments[doc_id]
        del self._permissions[doc_id]
        del self._snapshots[doc_id]
        del self._metadata[doc_id]
        
        # Clean up any pending flush tasks
        if doc_id in self._flush_tasks and not self._flush_tasks[doc_id].done():
            self._flush_tasks[doc_id].cancel()
            del self._flush_tasks[doc_id]
        
        # Clean up buffers
        if doc_id in self._update_buffers:
            del self._update_buffers[doc_id]
        if doc_id in self._update_counters:
            del self._update_counters[doc_id]
        if doc_id in self._last_snapshot_time:
            del self._last_snapshot_time[doc_id]
    
    async def list_documents(self) -> List[str]:
        """List all collaborative documents.
        
        Returns:
            List of document identifiers
        """
        return list(self._documents)
    
    async def _store_updates(self, doc_id: str, updates: List[bytes], create_snapshot: bool) -> None:
        """Store updates in memory.
        
        Args:
            doc_id: Document identifier
            updates: List of binary Yjs update data
            create_snapshot: Whether to create a snapshot
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        # Append updates to the document
        self._updates[doc_id].extend(updates)
        
        # Update metadata
        self._metadata[doc_id]["updated_at"] = datetime.now().isoformat()
        self._metadata[doc_id]["version"] += len(updates)
        
        # Create snapshot if requested (in a real implementation, this would
        # require the actual document state to be provided)
        if create_snapshot and doc_id in self._snapshots:
            # In a real implementation, we would create a snapshot here
            # For now, we just update the metadata
            self._metadata[doc_id]["snapshot_count"] += 1
    
    async def get_updates(self, doc_id: str, from_version: Optional[int] = None) -> List[bytes]:
        """Get CRDT updates for a document.
        
        Args:
            doc_id: Document identifier
            from_version: Optional version to start from (None for all updates)
            
        Returns:
            List of binary Yjs update data
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        if from_version is None:
            return self._updates[doc_id].copy()
        
        # Ensure from_version is valid
        if from_version < 0 or from_version >= len(self._updates[doc_id]):
            raise ValueError(f"Invalid version {from_version}")
        
        return self._updates[doc_id][from_version:].copy()
    
    async def get_awareness(self, doc_id: str) -> Dict[str, Any]:
        """Get awareness state for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing awareness state
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        return self._awareness[doc_id].copy()
    
    async def update_awareness(self, doc_id: str, awareness: Dict[str, Any]) -> None:
        """Update awareness state for a document.
        
        Args:
            doc_id: Document identifier
            awareness: Dictionary containing awareness state
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        self._awareness[doc_id] = awareness.copy()
        self._metadata[doc_id]["updated_at"] = datetime.now().isoformat()
    
    async def get_locks(self, doc_id: str) -> Dict[str, Any]:
        """Get lock state for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing lock state
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        return self._locks[doc_id].copy()
    
    async def update_locks(self, doc_id: str, locks: Dict[str, Any]) -> None:
        """Update lock state for a document.
        
        Args:
            doc_id: Document identifier
            locks: Dictionary containing lock state
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        self._locks[doc_id] = locks.copy()
        self._metadata[doc_id]["updated_at"] = datetime.now().isoformat()
    
    async def get_comments(self, doc_id: str) -> Dict[str, Any]:
        """Get comments for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing comments
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        return self._comments[doc_id].copy()
    
    async def update_comments(self, doc_id: str, comments: Dict[str, Any]) -> None:
        """Update comments for a document.
        
        Args:
            doc_id: Document identifier
            comments: Dictionary containing comments
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        self._comments[doc_id] = comments.copy()
        self._metadata[doc_id]["updated_at"] = datetime.now().isoformat()
    
    async def get_permissions(self, doc_id: str) -> Dict[str, Any]:
        """Get permissions for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing permissions
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        return self._permissions[doc_id].copy()
    
    async def update_permissions(self, doc_id: str, permissions: Dict[str, Any]) -> None:
        """Update permissions for a document.
        
        Args:
            doc_id: Document identifier
            permissions: Dictionary containing permissions
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        self._permissions[doc_id] = permissions.copy()
        self._metadata[doc_id]["updated_at"] = datetime.now().isoformat()
    
    async def create_snapshot(self, doc_id: str, state: bytes) -> None:
        """Create a snapshot of the document state.
        
        Args:
            doc_id: Document identifier
            state: Binary Yjs document state
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        version = self._metadata[doc_id]["version"]
        self._snapshots[doc_id].append((version, state))
        self._metadata[doc_id]["snapshot_count"] += 1
    
    async def get_snapshot(self, doc_id: str, version: Optional[int] = None) -> Optional[bytes]:
        """Get a snapshot of the document state.
        
        Args:
            doc_id: Document identifier
            version: Optional version to retrieve (None for latest)
            
        Returns:
            Binary Yjs document state or None if not found
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        if not self._snapshots[doc_id]:
            return None
        
        if version is None:
            # Return the latest snapshot
            return self._snapshots[doc_id][-1][1]
        
        # Find the closest snapshot that is less than or equal to the requested version
        for i in range(len(self._snapshots[doc_id]) - 1, -1, -1):
            snapshot_version, snapshot_data = self._snapshots[doc_id][i]
            if snapshot_version <= version:
                return snapshot_data
        
        return None
    
    async def get_document_metadata(self, doc_id: str) -> Dict[str, Any]:
        """Get metadata for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing document metadata
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        return self._metadata[doc_id].copy()


class FileCollaborationStore(CollaborationStore):
    """File-based implementation of the collaboration store.
    
    This implementation stores data in files and is suitable for production
    environments. Data is persisted across server restarts.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the file-based collaboration store.
        
        Args:
            config: Configuration options for the store
        """
        super().__init__(config)
        
        # Get base directory from config or use default
        self.base_dir = Path(self.config.get("base_dir", os.path.join(os.path.expanduser("~"), ".jupyter", "collab")))
        
        # Cache for recently accessed data
        self.cache_size = self.config.get("cache_size", 100)  # Number of items to cache
        self.snapshot_cache_size_mb = self.config.get("snapshot_cache_size_mb", 100)  # MB
        
        # Initialize caches
        self._awareness_cache = lru_cache(maxsize=self.cache_size)(self._load_awareness_uncached)
        self._locks_cache = lru_cache(maxsize=self.cache_size)(self._load_locks_uncached)
        self._comments_cache = lru_cache(maxsize=self.cache_size)(self._load_comments_uncached)
        self._permissions_cache = lru_cache(maxsize=self.cache_size)(self._load_permissions_uncached)
        
        # File locks for concurrent access
        self._file_locks: Dict[str, asyncio.Lock] = {}
    
    async def initialize(self) -> None:
        """Initialize the store and ensure required directories exist."""
        # Create base directory if it doesn't exist
        os.makedirs(self.base_dir, exist_ok=True)
        
        # Create history directory if it doesn't exist
        os.makedirs(self.base_dir / CollaborationFileTypes.HISTORY.value, exist_ok=True)
    
    def _get_document_dir(self, doc_id: str) -> Path:
        """Get the directory for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Path to the document directory
        """
        return self.base_dir / doc_id
    
    def _get_updates_path(self, doc_id: str) -> Path:
        """Get the path to the updates file for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Path to the updates file
        """
        return self._get_document_dir(doc_id) / CollaborationFileTypes.UPDATES.value
    
    def _get_awareness_path(self, doc_id: str) -> Path:
        """Get the path to the awareness file for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Path to the awareness file
        """
        return self._get_document_dir(doc_id) / CollaborationFileTypes.AWARENESS.value
    
    def _get_locks_path(self, doc_id: str) -> Path:
        """Get the path to the locks file for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Path to the locks file
        """
        return self._get_document_dir(doc_id) / CollaborationFileTypes.LOCKS.value
    
    def _get_comments_path(self, doc_id: str) -> Path:
        """Get the path to the comments file for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Path to the comments file
        """
        return self._get_document_dir(doc_id) / CollaborationFileTypes.COMMENTS.value
    
    def _get_permissions_path(self, doc_id: str) -> Path:
        """Get the path to the permissions file for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Path to the permissions file
        """
        return self._get_document_dir(doc_id) / CollaborationFileTypes.PERMISSIONS.value
    
    def _get_history_dir(self, doc_id: str) -> Path:
        """Get the directory for document history.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Path to the history directory
        """
        return self.base_dir / CollaborationFileTypes.HISTORY.value / doc_id
    
    def _get_metadata_path(self, doc_id: str) -> Path:
        """Get the path to the metadata file for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Path to the metadata file
        """
        return self._get_document_dir(doc_id) / "metadata.json"
    
    def _get_snapshot_path(self, doc_id: str, version: int) -> Path:
        """Get the path to a snapshot file for a document.
        
        Args:
            doc_id: Document identifier
            version: Snapshot version
            
        Returns:
            Path to the snapshot file
        """
        return self._get_history_dir(doc_id) / f"snapshot_{version}.bin"
    
    async def _get_file_lock(self, path: str) -> asyncio.Lock:
        """Get a lock for a file path.
        
        Args:
            path: File path
            
        Returns:
            Lock for the file
        """
        if path not in self._file_locks:
            self._file_locks[path] = asyncio.Lock()
        return self._file_locks[path]
    
    async def document_exists(self, doc_id: str) -> bool:
        """Check if a collaborative document exists.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            True if the document exists, False otherwise
        """
        return self._get_document_dir(doc_id).exists()
    
    async def create_document(self, doc_id: str, initial_data: Optional[Dict[str, Any]] = None) -> None:
        """Create a new collaborative document.
        
        Args:
            doc_id: Document identifier
            initial_data: Initial document data (optional)
        """
        if await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} already exists")
        
        # Create document directory
        doc_dir = self._get_document_dir(doc_id)
        os.makedirs(doc_dir, exist_ok=True)
        
        # Create history directory
        history_dir = self._get_history_dir(doc_id)
        os.makedirs(history_dir, exist_ok=True)
        
        # Initialize metadata
        metadata = {
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "version": 0,
            "snapshot_count": 0,
        }
        
        # Write metadata file
        async with self._get_file_lock(str(self._get_metadata_path(doc_id))):
            with open(self._get_metadata_path(doc_id), "w") as f:
                json.dump(metadata, f)
        
        # Initialize empty files
        open(self._get_updates_path(doc_id), "wb").close()
        
        # Apply initial data if provided
        if initial_data:
            if "awareness" in initial_data:
                await self.update_awareness(doc_id, initial_data["awareness"])
            if "locks" in initial_data:
                await self.update_locks(doc_id, initial_data["locks"])
            if "comments" in initial_data:
                await self.update_comments(doc_id, initial_data["comments"])
            if "permissions" in initial_data:
                await self.update_permissions(doc_id, initial_data["permissions"])
    
    async def delete_document(self, doc_id: str) -> None:
        """Delete a collaborative document and all associated data.
        
        Args:
            doc_id: Document identifier
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        # Get all file paths
        doc_dir = self._get_document_dir(doc_id)
        history_dir = self._get_history_dir(doc_id)
        
        # Acquire locks for all files
        locks = []
        for path in [self._get_updates_path(doc_id), self._get_awareness_path(doc_id),
                    self._get_locks_path(doc_id), self._get_comments_path(doc_id),
                    self._get_permissions_path(doc_id), self._get_metadata_path(doc_id)]:
            locks.append(self._get_file_lock(str(path)))
        
        # Acquire all locks to ensure no concurrent access
        for lock in locks:
            await lock.acquire()
        
        try:
            # Delete all files and directories
            import shutil
            if history_dir.exists():
                shutil.rmtree(history_dir)
            if doc_dir.exists():
                shutil.rmtree(doc_dir)
            
            # Clean up any pending flush tasks
            if doc_id in self._flush_tasks and not self._flush_tasks[doc_id].done():
                self._flush_tasks[doc_id].cancel()
                del self._flush_tasks[doc_id]
            
            # Clean up buffers
            if doc_id in self._update_buffers:
                del self._update_buffers[doc_id]
            if doc_id in self._update_counters:
                del self._update_counters[doc_id]
            if doc_id in self._last_snapshot_time:
                del self._last_snapshot_time[doc_id]
            
            # Clear caches
            self._awareness_cache.cache_clear()
            self._locks_cache.cache_clear()
            self._comments_cache.cache_clear()
            self._permissions_cache.cache_clear()
        finally:
            # Release all locks
            for lock in locks:
                lock.release()
    
    async def list_documents(self) -> List[str]:
        """List all collaborative documents.
        
        Returns:
            List of document identifiers
        """
        # List all directories in the base directory that have a metadata.json file
        documents = []
        for item in os.listdir(self.base_dir):
            if os.path.isdir(os.path.join(self.base_dir, item)):
                if os.path.exists(os.path.join(self.base_dir, item, "metadata.json")):
                    documents.append(item)
        return documents
    
    async def _store_updates(self, doc_id: str, updates: List[bytes], create_snapshot: bool) -> None:
        """Store updates in the file system.
        
        Args:
            doc_id: Document identifier
            updates: List of binary Yjs update data
            create_snapshot: Whether to create a snapshot
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        # Get file paths
        updates_path = self._get_updates_path(doc_id)
        metadata_path = self._get_metadata_path(doc_id)
        
        # Acquire locks
        updates_lock = await self._get_file_lock(str(updates_path))
        metadata_lock = await self._get_file_lock(str(metadata_path))
        
        # Process updates
        async with updates_lock:
            # Append updates to the file
            with open(updates_path, "ab") as f:
                for update in updates:
                    # Write length prefix and update data
                    length = len(update)
                    f.write(length.to_bytes(4, byteorder="big"))
                    f.write(update)
        
        # Update metadata
        async with metadata_lock:
            metadata = await self.get_document_metadata(doc_id)
            metadata["updated_at"] = datetime.now().isoformat()
            metadata["version"] += len(updates)
            
            # Write metadata file (using atomic write pattern)
            temp_path = metadata_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(metadata, f)
            os.replace(temp_path, metadata_path)
        
        # Create snapshot if requested
        if create_snapshot:
            # In a real implementation, we would need the actual document state
            # For now, we just update the metadata to indicate a snapshot was created
            async with metadata_lock:
                metadata = await self.get_document_metadata(doc_id)
                metadata["snapshot_count"] += 1
                
                # Write metadata file (using atomic write pattern)
                temp_path = metadata_path.with_suffix(".tmp")
                with open(temp_path, "w") as f:
                    json.dump(metadata, f)
                os.replace(temp_path, metadata_path)
    
    async def get_updates(self, doc_id: str, from_version: Optional[int] = None) -> List[bytes]:
        """Get CRDT updates for a document.
        
        Args:
            doc_id: Document identifier
            from_version: Optional version to start from (None for all updates)
            
        Returns:
            List of binary Yjs update data
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        updates_path = self._get_updates_path(doc_id)
        
        # Acquire lock
        async with await self._get_file_lock(str(updates_path)):
            # Check if file exists
            if not updates_path.exists():
                return []
            
            # Read updates from file
            updates = []
            current_version = 0
            
            with open(updates_path, "rb") as f:
                while True:
                    # Read length prefix
                    length_bytes = f.read(4)
                    if not length_bytes or len(length_bytes) < 4:
                        break
                    
                    # Parse length
                    length = int.from_bytes(length_bytes, byteorder="big")
                    
                    # Read update data
                    update_data = f.read(length)
                    if not update_data or len(update_data) < length:
                        break
                    
                    # Skip updates before from_version
                    if from_version is None or current_version >= from_version:
                        updates.append(update_data)
                    
                    current_version += 1
            
            return updates
    
    def _load_awareness_uncached(self, doc_id: str) -> Dict[str, Any]:
        """Load awareness state from file (uncached version).
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing awareness state
        """
        awareness_path = self._get_awareness_path(doc_id)
        
        if not awareness_path.exists():
            return {}
        
        try:
            with open(awareness_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading awareness state for {doc_id}: {e}")
            return {}
    
    async def get_awareness(self, doc_id: str) -> Dict[str, Any]:
        """Get awareness state for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing awareness state
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        return self._awareness_cache(doc_id)
    
    async def update_awareness(self, doc_id: str, awareness: Dict[str, Any]) -> None:
        """Update awareness state for a document.
        
        Args:
            doc_id: Document identifier
            awareness: Dictionary containing awareness state
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        awareness_path = self._get_awareness_path(doc_id)
        
        # Acquire lock
        async with await self._get_file_lock(str(awareness_path)):
            # Write awareness file (using atomic write pattern)
            temp_path = awareness_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(awareness, f)
            os.replace(temp_path, awareness_path)
        
        # Update metadata
        metadata_path = self._get_metadata_path(doc_id)
        async with await self._get_file_lock(str(metadata_path)):
            metadata = await self.get_document_metadata(doc_id)
            metadata["updated_at"] = datetime.now().isoformat()
            
            # Write metadata file (using atomic write pattern)
            temp_path = metadata_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(metadata, f)
            os.replace(temp_path, metadata_path)
        
        # Clear cache
        self._awareness_cache.cache_clear()
    
    def _load_locks_uncached(self, doc_id: str) -> Dict[str, Any]:
        """Load lock state from file (uncached version).
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing lock state
        """
        locks_path = self._get_locks_path(doc_id)
        
        if not locks_path.exists():
            return {}
        
        try:
            with open(locks_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading lock state for {doc_id}: {e}")
            return {}
    
    async def get_locks(self, doc_id: str) -> Dict[str, Any]:
        """Get lock state for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing lock state
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        return self._locks_cache(doc_id)
    
    async def update_locks(self, doc_id: str, locks: Dict[str, Any]) -> None:
        """Update lock state for a document.
        
        Args:
            doc_id: Document identifier
            locks: Dictionary containing lock state
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        locks_path = self._get_locks_path(doc_id)
        
        # Acquire lock
        async with await self._get_file_lock(str(locks_path)):
            # Write locks file (using atomic write pattern)
            temp_path = locks_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(locks, f)
            os.replace(temp_path, locks_path)
        
        # Update metadata
        metadata_path = self._get_metadata_path(doc_id)
        async with await self._get_file_lock(str(metadata_path)):
            metadata = await self.get_document_metadata(doc_id)
            metadata["updated_at"] = datetime.now().isoformat()
            
            # Write metadata file (using atomic write pattern)
            temp_path = metadata_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(metadata, f)
            os.replace(temp_path, metadata_path)
        
        # Clear cache
        self._locks_cache.cache_clear()
    
    def _load_comments_uncached(self, doc_id: str) -> Dict[str, Any]:
        """Load comments from file (uncached version).
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing comments
        """
        comments_path = self._get_comments_path(doc_id)
        
        if not comments_path.exists():
            return {}
        
        try:
            with open(comments_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading comments for {doc_id}: {e}")
            return {}
    
    async def get_comments(self, doc_id: str) -> Dict[str, Any]:
        """Get comments for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing comments
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        return self._comments_cache(doc_id)
    
    async def update_comments(self, doc_id: str, comments: Dict[str, Any]) -> None:
        """Update comments for a document.
        
        Args:
            doc_id: Document identifier
            comments: Dictionary containing comments
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        comments_path = self._get_comments_path(doc_id)
        
        # Acquire lock
        async with await self._get_file_lock(str(comments_path)):
            # Write comments file (using atomic write pattern)
            temp_path = comments_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(comments, f)
            os.replace(temp_path, comments_path)
        
        # Update metadata
        metadata_path = self._get_metadata_path(doc_id)
        async with await self._get_file_lock(str(metadata_path)):
            metadata = await self.get_document_metadata(doc_id)
            metadata["updated_at"] = datetime.now().isoformat()
            
            # Write metadata file (using atomic write pattern)
            temp_path = metadata_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(metadata, f)
            os.replace(temp_path, metadata_path)
        
        # Clear cache
        self._comments_cache.cache_clear()
    
    def _load_permissions_uncached(self, doc_id: str) -> Dict[str, Any]:
        """Load permissions from file (uncached version).
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing permissions
        """
        permissions_path = self._get_permissions_path(doc_id)
        
        if not permissions_path.exists():
            return {}
        
        try:
            with open(permissions_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading permissions for {doc_id}: {e}")
            return {}
    
    async def get_permissions(self, doc_id: str) -> Dict[str, Any]:
        """Get permissions for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing permissions
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        return self._permissions_cache(doc_id)
    
    async def update_permissions(self, doc_id: str, permissions: Dict[str, Any]) -> None:
        """Update permissions for a document.
        
        Args:
            doc_id: Document identifier
            permissions: Dictionary containing permissions
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        permissions_path = self._get_permissions_path(doc_id)
        
        # Acquire lock
        async with await self._get_file_lock(str(permissions_path)):
            # Write permissions file (using atomic write pattern)
            temp_path = permissions_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(permissions, f)
            os.replace(temp_path, permissions_path)
        
        # Update metadata
        metadata_path = self._get_metadata_path(doc_id)
        async with await self._get_file_lock(str(metadata_path)):
            metadata = await self.get_document_metadata(doc_id)
            metadata["updated_at"] = datetime.now().isoformat()
            
            # Write metadata file (using atomic write pattern)
            temp_path = metadata_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(metadata, f)
            os.replace(temp_path, metadata_path)
        
        # Clear cache
        self._permissions_cache.cache_clear()
    
    async def create_snapshot(self, doc_id: str, state: bytes) -> None:
        """Create a snapshot of the document state.
        
        Args:
            doc_id: Document identifier
            state: Binary Yjs document state
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        # Get metadata to determine version
        metadata_path = self._get_metadata_path(doc_id)
        async with await self._get_file_lock(str(metadata_path)):
            metadata = await self.get_document_metadata(doc_id)
            version = metadata["version"]
            
            # Create history directory if it doesn't exist
            history_dir = self._get_history_dir(doc_id)
            os.makedirs(history_dir, exist_ok=True)
            
            # Write snapshot file
            snapshot_path = self._get_snapshot_path(doc_id, version)
            with open(snapshot_path, "wb") as f:
                # Compress the state if it's large
                if len(state) > 1024:  # Only compress if larger than 1KB
                    compressed = zlib.compress(state, level=self.compression_level)
                    # Write a flag indicating compression (1 byte) followed by the compressed data
                    f.write(b"\x01")
                    f.write(compressed)
                else:
                    # Write a flag indicating no compression (1 byte) followed by the raw data
                    f.write(b"\x00")
                    f.write(state)
            
            # Update metadata
            metadata["snapshot_count"] += 1
            metadata["last_snapshot_version"] = version
            metadata["last_snapshot_time"] = datetime.now().isoformat()
            
            # Write metadata file (using atomic write pattern)
            temp_path = metadata_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(metadata, f)
            os.replace(temp_path, metadata_path)
    
    async def get_snapshot(self, doc_id: str, version: Optional[int] = None) -> Optional[bytes]:
        """Get a snapshot of the document state.
        
        Args:
            doc_id: Document identifier
            version: Optional version to retrieve (None for latest)
            
        Returns:
            Binary Yjs document state or None if not found
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        # Get metadata
        metadata = await self.get_document_metadata(doc_id)
        
        if "last_snapshot_version" not in metadata or metadata["snapshot_count"] == 0:
            return None
        
        # Determine which snapshot to retrieve
        if version is None:
            version = metadata["last_snapshot_version"]
        
        # Find the closest snapshot that is less than or equal to the requested version
        history_dir = self._get_history_dir(doc_id)
        if not history_dir.exists():
            return None
        
        # List all snapshot files
        snapshot_files = []
        for item in os.listdir(history_dir):
            if item.startswith("snapshot_") and item.endswith(".bin"):
                try:
                    snapshot_version = int(item[9:-4])  # Extract version from filename
                    if snapshot_version <= version:
                        snapshot_files.append((snapshot_version, item))
                except ValueError:
                    continue
        
        if not snapshot_files:
            return None
        
        # Get the latest snapshot that is less than or equal to the requested version
        snapshot_files.sort(reverse=True)
        snapshot_path = history_dir / snapshot_files[0][1]
        
        # Read snapshot file
        with open(snapshot_path, "rb") as f:
            # Read compression flag
            compression_flag = f.read(1)
            if not compression_flag:
                return None
            
            # Read data
            data = f.read()
            if not data:
                return None
            
            # Decompress if necessary
            if compression_flag == b"\x01":
                return zlib.decompress(data)
            else:
                return data
    
    async def get_document_metadata(self, doc_id: str) -> Dict[str, Any]:
        """Get metadata for a document.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Dictionary containing document metadata
        """
        if not await self.document_exists(doc_id):
            raise ValueError(f"Document {doc_id} does not exist")
        
        metadata_path = self._get_metadata_path(doc_id)
        
        # Acquire lock
        async with await self._get_file_lock(str(metadata_path)):
            try:
                with open(metadata_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading metadata for {doc_id}: {e}")
                return {
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "version": 0,
                    "snapshot_count": 0,
                }


class CollaborationStoreFactory:
    """Factory for creating collaboration stores.
    
    This class provides methods for creating and configuring collaboration stores
    based on the specified backend type and configuration options.
    """
    
    @staticmethod
    async def create_store(backend: StorageBackend = StorageBackend.FILE, config: Dict[str, Any] = None) -> CollaborationStore:
        """Create a new collaboration store.
        
        Args:
            backend: Storage backend type
            config: Configuration options for the store
            
        Returns:
            Configured collaboration store instance
        """
        if backend == StorageBackend.MEMORY:
            store = MemoryCollaborationStore(config)
        elif backend == StorageBackend.FILE:
            store = FileCollaborationStore(config)
        else:
            raise ValueError(f"Unsupported backend: {backend}")
        
        # Initialize the store
        await store.initialize()
        
        return store


class CollaborationContentManager:
    """Content manager for collaborative documents.
    
    This class extends the standard Jupyter content manager with collaboration-specific
    functionality, providing an interface for the WebSocket handlers to persist
    collaboration state and retrieve it when clients reconnect.
    """
    
    def __init__(self, contents_manager, config: Dict[str, Any] = None):
        """Initialize the collaboration content manager.
        
        Args:
            contents_manager: Jupyter contents manager
            config: Configuration options
        """
        self.contents_manager = contents_manager
        self.config = config or {}
        
        # Default to file-based storage in production, memory in development
        self.storage_backend = StorageBackend(self.config.get("storage_backend", StorageBackend.FILE.value))
        
        # Store instance will be initialized in initialize()
        self.store = None
        
        # Map of notebook paths to document IDs
        self._path_to_doc_id: Dict[str, str] = {}
        self._doc_id_to_path: Dict[str, str] = {}
    
    async def initialize(self) -> None:
        """Initialize the collaboration content manager."""
        # Create store
        self.store = await CollaborationStoreFactory.create_store(
            backend=self.storage_backend,
            config=self.config
        )
    
    async def shutdown(self) -> None:
        """Perform cleanup operations before shutdown."""
        if self.store:
            await self.store.shutdown()
    
    def _get_doc_id_from_path(self, path: str) -> str:
        """Get document ID from notebook path.
        
        Args:
            path: Notebook path
            
        Returns:
            Document ID
        """
        # Use a deterministic mapping from path to document ID
        # This ensures that the same notebook always gets the same document ID
        import hashlib
        return hashlib.sha256(path.encode()).hexdigest()
    
    async def get_collab_document(self, path: str) -> Dict[str, Any]:
        """Get collaboration document for a notebook.
        
        Args:
            path: Notebook path
            
        Returns:
            Dictionary containing collaboration document data
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            # Create document if it doesn't exist
            await self.create_collab_document(path)
        
        # Update mapping
        self._path_to_doc_id[path] = doc_id
        self._doc_id_to_path[doc_id] = path
        
        # Get document data
        metadata = await self.store.get_document_metadata(doc_id)
        awareness = await self.store.get_awareness(doc_id)
        locks = await self.store.get_locks(doc_id)
        comments = await self.store.get_comments(doc_id)
        permissions = await self.store.get_permissions(doc_id)
        
        # Return document data
        return {
            "doc_id": doc_id,
            "path": path,
            "metadata": metadata,
            "awareness": awareness,
            "locks": locks,
            "comments": comments,
            "permissions": permissions,
        }
    
    async def create_collab_document(self, path: str, initial_data: Optional[Dict[str, Any]] = None) -> str:
        """Create a new collaboration document for a notebook.
        
        Args:
            path: Notebook path
            initial_data: Initial document data (optional)
            
        Returns:
            Document ID
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Create document
        await self.store.create_document(doc_id, initial_data)
        
        # Update mapping
        self._path_to_doc_id[path] = doc_id
        self._doc_id_to_path[doc_id] = path
        
        return doc_id
    
    async def delete_collab_document(self, path: str) -> None:
        """Delete a collaboration document for a notebook.
        
        Args:
            path: Notebook path
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Delete document
        await self.store.delete_document(doc_id)
        
        # Update mapping
        if path in self._path_to_doc_id:
            del self._path_to_doc_id[path]
        if doc_id in self._doc_id_to_path:
            del self._doc_id_to_path[doc_id]
    
    async def list_collab_documents(self) -> List[Dict[str, Any]]:
        """List all collaboration documents.
        
        Returns:
            List of dictionaries containing document information
        """
        doc_ids = await self.store.list_documents()
        
        # Get document information
        documents = []
        for doc_id in doc_ids:
            try:
                metadata = await self.store.get_document_metadata(doc_id)
                path = self._doc_id_to_path.get(doc_id, "Unknown")
                
                documents.append({
                    "doc_id": doc_id,
                    "path": path,
                    "metadata": metadata,
                })
            except Exception as e:
                logger.error(f"Error getting document information for {doc_id}: {e}")
        
        return documents
    
    async def append_crdt_updates(self, path: str, updates: bytes) -> None:
        """Append CRDT updates to a document.
        
        Args:
            path: Notebook path
            updates: Binary Yjs update data
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            # Create document if it doesn't exist
            await self.create_collab_document(path)
        
        # Append updates
        await self.store.append_updates(doc_id, updates)
    
    async def get_crdt_updates(self, path: str, from_version: Optional[int] = None) -> List[bytes]:
        """Get CRDT updates for a document.
        
        Args:
            path: Notebook path
            from_version: Optional version to start from (None for all updates)
            
        Returns:
            List of binary Yjs update data
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            return []
        
        # Get updates
        return await self.store.get_updates(doc_id, from_version)
    
    async def create_snapshot(self, path: str, state: bytes) -> None:
        """Create a snapshot of the document state.
        
        Args:
            path: Notebook path
            state: Binary Yjs document state
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            # Create document if it doesn't exist
            await self.create_collab_document(path)
        
        # Create snapshot
        await self.store.create_snapshot(doc_id, state)
    
    async def get_snapshot(self, path: str, version: Optional[int] = None) -> Optional[bytes]:
        """Get a snapshot of the document state.
        
        Args:
            path: Notebook path
            version: Optional version to retrieve (None for latest)
            
        Returns:
            Binary Yjs document state or None if not found
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            return None
        
        # Get snapshot
        return await self.store.get_snapshot(doc_id, version)
    
    async def get_awareness(self, path: str) -> Dict[str, Any]:
        """Get awareness state for a document.
        
        Args:
            path: Notebook path
            
        Returns:
            Dictionary containing awareness state
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            return {}
        
        # Get awareness
        return await self.store.get_awareness(doc_id)
    
    async def update_awareness(self, path: str, awareness: Dict[str, Any]) -> None:
        """Update awareness state for a document.
        
        Args:
            path: Notebook path
            awareness: Dictionary containing awareness state
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            # Create document if it doesn't exist
            await self.create_collab_document(path)
        
        # Update awareness
        await self.store.update_awareness(doc_id, awareness)
    
    async def get_locks(self, path: str) -> Dict[str, Any]:
        """Get lock state for a document.
        
        Args:
            path: Notebook path
            
        Returns:
            Dictionary containing lock state
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            return {}
        
        # Get locks
        return await self.store.get_locks(doc_id)
    
    async def update_locks(self, path: str, locks: Dict[str, Any]) -> None:
        """Update lock state for a document.
        
        Args:
            path: Notebook path
            locks: Dictionary containing lock state
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            # Create document if it doesn't exist
            await self.create_collab_document(path)
        
        # Update locks
        await self.store.update_locks(doc_id, locks)
    
    async def get_comments(self, path: str) -> Dict[str, Any]:
        """Get comments for a document.
        
        Args:
            path: Notebook path
            
        Returns:
            Dictionary containing comments
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            return {}
        
        # Get comments
        return await self.store.get_comments(doc_id)
    
    async def update_comments(self, path: str, comments: Dict[str, Any]) -> None:
        """Update comments for a document.
        
        Args:
            path: Notebook path
            comments: Dictionary containing comments
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            # Create document if it doesn't exist
            await self.create_collab_document(path)
        
        # Update comments
        await self.store.update_comments(doc_id, comments)
    
    async def get_permissions(self, path: str) -> Dict[str, Any]:
        """Get permissions for a document.
        
        Args:
            path: Notebook path
            
        Returns:
            Dictionary containing permissions
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            return {}
        
        # Get permissions
        return await self.store.get_permissions(doc_id)
    
    async def update_permissions(self, path: str, permissions: Dict[str, Any]) -> None:
        """Update permissions for a document.
        
        Args:
            path: Notebook path
            permissions: Dictionary containing permissions
        """
        doc_id = self._get_doc_id_from_path(path)
        
        # Check if document exists
        if not await self.store.document_exists(doc_id):
            # Create document if it doesn't exist
            await self.create_collab_document(path)
        
        # Update permissions
        await self.store.update_permissions(doc_id, permissions)
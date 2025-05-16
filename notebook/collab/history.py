"""Server-side component of the version history and change tracking system for Jupyter Notebook v7.

This module implements the server-side functionality for tracking, storing, and retrieving
the history of changes to notebook cells in collaborative editing sessions. It provides
mechanisms for recording Yjs update events, creating version snapshots, generating diffs
between versions, and attributing changes to specific users.
"""

import asyncio
import datetime
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

import y_py as Y
from jupyter_server.auth import Authorizer
from tornado.web import HTTPError

from notebook.collab.persistence import CollaborationPersistence

# Configure logger
logger = logging.getLogger(__name__)


class YjsUpdateRecord:
    """Represents a single Yjs update operation in the history.
    
    Each update record contains the binary-encoded Yjs update message,
    along with metadata about when it was created, who created it,
    and any additional context information.
    """
    
    def __init__(
        self,
        update_id: str,
        document_id: str,
        sequence_number: int,
        timestamp: datetime.datetime,
        update_data: bytes,
        client_id: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Initialize a new update record.
        
        Parameters
        ----------
        update_id : str
            Unique identifier for this update
        document_id : str
            Identifier of the notebook document
        sequence_number : int
            Monotonically increasing sequence number
        timestamp : datetime.datetime
            When the update was created
        update_data : bytes
            Binary-encoded Yjs update message
        client_id : str
            Unique identifier of the client that generated the update
        user_id : str
            Identifier of the user who made the change
        metadata : dict, optional
            Additional information about the update
        """
        self.update_id = update_id
        self.document_id = document_id
        self.sequence_number = sequence_number
        self.timestamp = timestamp
        self.update_data = update_data
        self.client_id = client_id
        self.user_id = user_id
        self.metadata = metadata or {}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'YjsUpdateRecord':
        """Create a YjsUpdateRecord from a dictionary representation.
        
        Parameters
        ----------
        data : dict
            Dictionary containing update record data
            
        Returns
        -------
        YjsUpdateRecord
            A new YjsUpdateRecord instance
        """
        return cls(
            update_id=data['update_id'],
            document_id=data['document_id'],
            sequence_number=data['sequence_number'],
            timestamp=datetime.datetime.fromisoformat(data['timestamp']),
            update_data=data['update_data'],
            client_id=data['client_id'],
            user_id=data['user_id'],
            metadata=data.get('metadata', {})
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the update record to a dictionary representation.
        
        Returns
        -------
        dict
            Dictionary representation of the update record
        """
        return {
            'update_id': self.update_id,
            'document_id': self.document_id,
            'sequence_number': self.sequence_number,
            'timestamp': self.timestamp.isoformat(),
            'update_data': self.update_data,
            'client_id': self.client_id,
            'user_id': self.user_id,
            'metadata': self.metadata
        }


class VersionDiff:
    """Represents the difference between two versions of a notebook document.
    
    A diff contains information about what changed between two versions,
    including cell additions, deletions, and modifications.
    """
    
    def __init__(
        self,
        diff_id: str,
        document_id: str,
        from_snapshot_id: str,
        to_snapshot_id: str,
        timestamp: datetime.datetime,
        changes: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Initialize a new version diff.
        
        Parameters
        ----------
        diff_id : str
            Unique identifier for this diff
        document_id : str
            Identifier of the notebook document
        from_snapshot_id : str
            Identifier of the source snapshot
        to_snapshot_id : str
            Identifier of the target snapshot
        timestamp : datetime.datetime
            When the diff was created
        changes : dict
            Dictionary containing the changes between versions
        metadata : dict, optional
            Additional information about the diff
        """
        self.diff_id = diff_id
        self.document_id = document_id
        self.from_snapshot_id = from_snapshot_id
        self.to_snapshot_id = to_snapshot_id
        self.timestamp = timestamp
        self.changes = changes
        self.metadata = metadata or {}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VersionDiff':
        """Create a VersionDiff from a dictionary representation.
        
        Parameters
        ----------
        data : dict
            Dictionary containing diff data
            
        Returns
        -------
        VersionDiff
            A new VersionDiff instance
        """
        return cls(
            diff_id=data['diff_id'],
            document_id=data['document_id'],
            from_snapshot_id=data['from_snapshot_id'],
            to_snapshot_id=data['to_snapshot_id'],
            timestamp=datetime.datetime.fromisoformat(data['timestamp']),
            changes=data['changes'],
            metadata=data.get('metadata', {})
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the diff to a dictionary representation.
        
        Returns
        -------
        dict
            Dictionary representation of the diff
        """
        return {
            'diff_id': self.diff_id,
            'document_id': self.document_id,
            'from_snapshot_id': self.from_snapshot_id,
            'to_snapshot_id': self.to_snapshot_id,
            'timestamp': self.timestamp.isoformat(),
            'changes': self.changes,
            'metadata': self.metadata
        }


class VersionSnapshot:
    """Represents a point-in-time snapshot of a notebook document.
    
    A snapshot contains the complete state of the document at a specific point in time,
    along with metadata about when it was created, who created it, and any additional
    context information.
    """
    
    def __init__(
        self,
        snapshot_id: str,
        document_id: str,
        user_id: str,
        timestamp: datetime.datetime,
        state_vector: bytes,
        document_state: bytes,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Initialize a new version snapshot.
        
        Parameters
        ----------
        snapshot_id : str
            Unique identifier for this snapshot
        document_id : str
            Identifier of the notebook document
        user_id : str
            Identifier of the user who created this snapshot
        timestamp : datetime.datetime
            When the snapshot was created
        state_vector : bytes
            Yjs state vector for the snapshot (binary encoded)
        document_state : bytes
            Serialized document state (binary encoded)
        metadata : dict, optional
            Additional information about the snapshot
        """
        self.snapshot_id = snapshot_id
        self.document_id = document_id
        self.user_id = user_id
        self.timestamp = timestamp
        self.state_vector = state_vector
        self.document_state = document_state
        self.metadata = metadata or {}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VersionSnapshot':
        """Create a VersionSnapshot from a dictionary representation.
        
        Parameters
        ----------
        data : dict
            Dictionary containing snapshot data
            
        Returns
        -------
        VersionSnapshot
            A new VersionSnapshot instance
        """
        return cls(
            snapshot_id=data['snapshot_id'],
            document_id=data['document_id'],
            user_id=data['user_id'],
            timestamp=datetime.datetime.fromisoformat(data['timestamp']),
            state_vector=data['state_vector'],
            document_state=data['document_state'],
            metadata=data.get('metadata', {})
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the snapshot to a dictionary representation.
        
        Returns
        -------
        dict
            Dictionary representation of the snapshot
        """
        return {
            'snapshot_id': self.snapshot_id,
            'document_id': self.document_id,
            'user_id': self.user_id,
            'timestamp': self.timestamp.isoformat(),
            'state_vector': self.state_vector,
            'document_state': self.document_state,
            'metadata': self.metadata
        }


class HistoryManager:
    """Manages version history for collaborative notebook documents.
    
    This class provides methods for recording, retrieving, and comparing
    different versions of a notebook document. It uses the Yjs CRDT framework
    to track changes and generate snapshots.
    """
    
    def __init__(self, persistence: CollaborationPersistence):
        """Initialize a new history manager.
        
        Parameters
        ----------
        persistence : CollaborationPersistence
            The persistence layer for storing history data
        """
        self.persistence = persistence
        self._snapshot_interval = 60  # seconds between automatic snapshots
        self._last_snapshot_time = {}  # document_id -> timestamp
    
    async def record_update(self, document_id: str, update_data: bytes, client_id: str, user_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Record a Yjs update in the history.
        
        Parameters
        ----------
        document_id : str
            Identifier of the notebook document
        update_data : bytes
            Binary-encoded Yjs update message
        client_id : str
            Unique identifier of the client that generated the update
        user_id : str
            Identifier of the user who made the change
        metadata : dict, optional
            Additional information about the update
            
        Returns
        -------
        str
            The ID of the recorded update
        """
        # Generate a unique ID for this update
        update_id = str(uuid.uuid4())
        
        # Get the next sequence number for this document
        sequence_number = await self.persistence.get_next_sequence_number(document_id)
        
        # Create the update record
        update_record = YjsUpdateRecord(
            update_id=update_id,
            document_id=document_id,
            sequence_number=sequence_number,
            timestamp=datetime.datetime.now(),
            update_data=update_data,
            client_id=client_id,
            user_id=user_id,
            metadata=metadata or {}
        )
        
        # Store the update record
        await self.persistence.store_update_record(update_record)
        
        # Check if we should create a snapshot
        await self._check_create_snapshot(document_id, user_id)
        
        return update_id
    
    async def _check_create_snapshot(self, document_id: str, user_id: str) -> None:
        """Check if we should create a snapshot and do so if needed.
        
        Parameters
        ----------
        document_id : str
            Identifier of the notebook document
        user_id : str
            Identifier of the user who triggered this check
        """
        current_time = time.time()
        last_time = self._last_snapshot_time.get(document_id, 0)
        
        if current_time - last_time >= self._snapshot_interval:
            try:
                await self.create_snapshot(document_id, user_id)
                self._last_snapshot_time[document_id] = current_time
            except Exception as e:
                logger.error(f"Failed to create automatic snapshot for document {document_id}: {e}")
    
    async def create_snapshot(self, document_id: str, user_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a snapshot of the current document state.
        
        Parameters
        ----------
        document_id : str
            Identifier of the notebook document
        user_id : str
            Identifier of the user creating the snapshot
        metadata : dict, optional
            Additional information about the snapshot
            
        Returns
        -------
        str
            The ID of the created snapshot
        """
        # Generate a unique ID for this snapshot
        snapshot_id = str(uuid.uuid4())
        
        # Get the current document state
        ydoc = await self._load_document(document_id)
        
        # Encode the document state and state vector
        state_vector = Y.encode_state_vector(ydoc)
        document_state = Y.encode_state_as_update(ydoc)
        
        # Create the snapshot
        snapshot = VersionSnapshot(
            snapshot_id=snapshot_id,
            document_id=document_id,
            user_id=user_id,
            timestamp=datetime.datetime.now(),
            state_vector=state_vector,
            document_state=document_state,
            metadata=metadata or {}
        )
        
        # Store the snapshot
        await self.persistence.store_snapshot(snapshot)
        
        return snapshot_id
    
    async def _load_document(self, document_id: str) -> Y.YDoc:
        """Load a document from its update history.
        
        Parameters
        ----------
        document_id : str
            Identifier of the notebook document
            
        Returns
        -------
        Y.YDoc
            The reconstructed Yjs document
        """
        # Create a new Yjs document
        ydoc = Y.YDoc()
        
        # Get all updates for this document
        updates = await self.persistence.get_updates(document_id)
        
        # Apply the updates in sequence
        for update in sorted(updates, key=lambda u: u.sequence_number):
            Y.apply_update(ydoc, update.update_data)
        
        return ydoc
    
    async def get_snapshots(self, document_id: str) -> List[VersionSnapshot]:
        """Get all snapshots for a document.
        
        Parameters
        ----------
        document_id : str
            Identifier of the notebook document
            
        Returns
        -------
        list
            List of VersionSnapshot objects
        """
        return await self.persistence.get_snapshots(document_id)
    
    async def get_snapshot(self, snapshot_id: str) -> Optional[VersionSnapshot]:
        """Get a specific snapshot by ID.
        
        Parameters
        ----------
        snapshot_id : str
            Identifier of the snapshot
            
        Returns
        -------
        VersionSnapshot or None
            The requested snapshot, or None if not found
        """
        return await self.persistence.get_snapshot(snapshot_id)
    
    async def get_document_at_snapshot(self, snapshot_id: str) -> Y.YDoc:
        """Get the document state at a specific snapshot.
        
        Parameters
        ----------
        snapshot_id : str
            Identifier of the snapshot
            
        Returns
        -------
        Y.YDoc
            The document state at the specified snapshot
            
        Raises
        ------
        HTTPError
            If the snapshot is not found
        """
        snapshot = await self.persistence.get_snapshot(snapshot_id)
        if not snapshot:
            raise HTTPError(404, f"Snapshot {snapshot_id} not found")
        
        # Create a new Yjs document and apply the snapshot state
        ydoc = Y.YDoc()
        Y.apply_update(ydoc, snapshot.document_state)
        
        return ydoc
    
    async def create_diff(self, from_snapshot_id: str, to_snapshot_id: str) -> VersionDiff:
        """Create a diff between two snapshots.
        
        Parameters
        ----------
        from_snapshot_id : str
            Identifier of the source snapshot
        to_snapshot_id : str
            Identifier of the target snapshot
            
        Returns
        -------
        VersionDiff
            The diff between the two snapshots
            
        Raises
        ------
        HTTPError
            If either snapshot is not found
        """
        # Get the snapshots
        from_snapshot = await self.persistence.get_snapshot(from_snapshot_id)
        to_snapshot = await self.persistence.get_snapshot(to_snapshot_id)
        
        if not from_snapshot or not to_snapshot:
            raise HTTPError(404, "One or both snapshots not found")
        
        if from_snapshot.document_id != to_snapshot.document_id:
            raise HTTPError(400, "Snapshots must be from the same document")
        
        # Load the documents
        from_doc = Y.YDoc()
        to_doc = Y.YDoc()
        
        Y.apply_update(from_doc, from_snapshot.document_state)
        Y.apply_update(to_doc, to_snapshot.document_state)
        
        # Generate the diff
        changes = self._compute_document_diff(from_doc, to_doc)
        
        # Create the diff object
        diff = VersionDiff(
            diff_id=str(uuid.uuid4()),
            document_id=from_snapshot.document_id,
            from_snapshot_id=from_snapshot_id,
            to_snapshot_id=to_snapshot_id,
            timestamp=datetime.datetime.now(),
            changes=changes,
            metadata={
                'from_timestamp': from_snapshot.timestamp.isoformat(),
                'to_timestamp': to_snapshot.timestamp.isoformat(),
                'from_user': from_snapshot.user_id,
                'to_user': to_snapshot.user_id
            }
        )
        
        # Store the diff
        await self.persistence.store_diff(diff)
        
        return diff
    
    def _compute_document_diff(self, from_doc: Y.YDoc, to_doc: Y.YDoc) -> Dict[str, Any]:
        """Compute the difference between two Yjs documents.
        
        Parameters
        ----------
        from_doc : Y.YDoc
            Source document
        to_doc : Y.YDoc
            Target document
            
        Returns
        -------
        dict
            Dictionary containing the changes between the documents
        """
        # Extract the notebook content from the Yjs documents
        from_content = self._extract_notebook_content(from_doc)
        to_content = self._extract_notebook_content(to_doc)
        
        # Compare the cells
        added_cells = []
        deleted_cells = []
        modified_cells = []
        
        # Track cells by ID
        from_cells_by_id = {cell.get('id', i): cell for i, cell in enumerate(from_content.get('cells', []))}
        to_cells_by_id = {cell.get('id', i): cell for i, cell in enumerate(to_content.get('cells', []))}
        
        # Find deleted and modified cells
        for cell_id, from_cell in from_cells_by_id.items():
            if cell_id not in to_cells_by_id:
                deleted_cells.append({
                    'id': cell_id,
                    'cell': from_cell
                })
            else:
                to_cell = to_cells_by_id[cell_id]
                if from_cell != to_cell:
                    modified_cells.append({
                        'id': cell_id,
                        'from': from_cell,
                        'to': to_cell
                    })
        
        # Find added cells
        for cell_id, to_cell in to_cells_by_id.items():
            if cell_id not in from_cells_by_id:
                added_cells.append({
                    'id': cell_id,
                    'cell': to_cell
                })
        
        # Compute metadata changes
        metadata_changes = {}
        from_metadata = from_content.get('metadata', {})
        to_metadata = to_content.get('metadata', {})
        
        for key in set(from_metadata.keys()) | set(to_metadata.keys()):
            from_value = from_metadata.get(key)
            to_value = to_metadata.get(key)
            
            if from_value != to_value:
                metadata_changes[key] = {
                    'from': from_value,
                    'to': to_value
                }
        
        return {
            'added_cells': added_cells,
            'deleted_cells': deleted_cells,
            'modified_cells': modified_cells,
            'metadata_changes': metadata_changes
        }
    
    def _extract_notebook_content(self, ydoc: Y.YDoc) -> Dict[str, Any]:
        """Extract the notebook content from a Yjs document.
        
        Parameters
        ----------
        ydoc : Y.YDoc
            The Yjs document
            
        Returns
        -------
        dict
            Dictionary containing the notebook content
        """
        try:
            # Get the shared data from the Yjs document
            notebook_map = ydoc.get_map('notebook')
            cells_array = notebook_map.get('cells')
            metadata_map = notebook_map.get('metadata')
            
            # Convert to Python objects
            cells = []
            if cells_array:
                for i in range(len(cells_array)):
                    cell_map = cells_array.get(i)
                    if cell_map:
                        cell = {
                            'id': cell_map.get('id'),
                            'cell_type': cell_map.get('cell_type'),
                            'source': cell_map.get('source'),
                            'metadata': cell_map.get('metadata', {})
                        }
                        
                        # Add outputs for code cells
                        if cell['cell_type'] == 'code':
                            outputs_array = cell_map.get('outputs')
                            if outputs_array:
                                cell['outputs'] = [outputs_array.get(j) for j in range(len(outputs_array))]
                            else:
                                cell['outputs'] = []
                            
                            cell['execution_count'] = cell_map.get('execution_count')
                        
                        cells.append(cell)
            
            # Convert metadata
            metadata = {}
            if metadata_map:
                for key in metadata_map.keys():
                    metadata[key] = metadata_map.get(key)
            
            return {
                'cells': cells,
                'metadata': metadata,
                'nbformat': notebook_map.get('nbformat', 4),
                'nbformat_minor': notebook_map.get('nbformat_minor', 5)
            }
        except Exception as e:
            logger.error(f"Error extracting notebook content: {e}")
            return {'cells': [], 'metadata': {}, 'nbformat': 4, 'nbformat_minor': 5}
    
    async def get_changes_by_user(self, document_id: str, user_id: str, start_time: Optional[datetime.datetime] = None, end_time: Optional[datetime.datetime] = None) -> List[YjsUpdateRecord]:
        """Get all changes made by a specific user.
        
        Parameters
        ----------
        document_id : str
            Identifier of the notebook document
        user_id : str
            Identifier of the user
        start_time : datetime.datetime, optional
            Start of the time range
        end_time : datetime.datetime, optional
            End of the time range
            
        Returns
        -------
        list
            List of YjsUpdateRecord objects
        """
        return await self.persistence.get_updates_by_user(document_id, user_id, start_time, end_time)
    
    async def get_document_history(self, document_id: str, start_time: Optional[datetime.datetime] = None, end_time: Optional[datetime.datetime] = None) -> Dict[str, Any]:
        """Get a summary of the document's history.
        
        Parameters
        ----------
        document_id : str
            Identifier of the notebook document
        start_time : datetime.datetime, optional
            Start of the time range
        end_time : datetime.datetime, optional
            End of the time range
            
        Returns
        -------
        dict
            Dictionary containing the history summary
        """
        # Get all updates and snapshots for this document in the specified time range
        updates = await self.persistence.get_updates(document_id, start_time, end_time)
        snapshots = await self.persistence.get_snapshots(document_id, start_time, end_time)
        
        # Group updates by user
        updates_by_user = {}
        for update in updates:
            if update.user_id not in updates_by_user:
                updates_by_user[update.user_id] = []
            updates_by_user[update.user_id].append(update)
        
        # Compute statistics
        user_stats = {}
        for user_id, user_updates in updates_by_user.items():
            user_stats[user_id] = {
                'update_count': len(user_updates),
                'first_update': min(u.timestamp for u in user_updates).isoformat(),
                'last_update': max(u.timestamp for u in user_updates).isoformat()
            }
        
        return {
            'document_id': document_id,
            'total_updates': len(updates),
            'total_snapshots': len(snapshots),
            'first_update': min(u.timestamp for u in updates).isoformat() if updates else None,
            'last_update': max(u.timestamp for u in updates).isoformat() if updates else None,
            'users': user_stats,
            'snapshots': [{
                'id': s.snapshot_id,
                'timestamp': s.timestamp.isoformat(),
                'user_id': s.user_id,
                'metadata': s.metadata
            } for s in snapshots]
        }
    
    async def restore_snapshot(self, snapshot_id: str, user_id: str) -> str:
        """Restore a document to a previous snapshot state.
        
        Parameters
        ----------
        snapshot_id : str
            Identifier of the snapshot to restore
        user_id : str
            Identifier of the user performing the restore
            
        Returns
        -------
        str
            The ID of the new snapshot created after the restore
        """
        # Get the snapshot
        snapshot = await self.persistence.get_snapshot(snapshot_id)
        if not snapshot:
            raise HTTPError(404, f"Snapshot {snapshot_id} not found")
        
        # Create a new Yjs document and apply the snapshot state
        ydoc = Y.YDoc()
        Y.apply_update(ydoc, snapshot.document_state)
        
        # Create a new snapshot with the restored state
        new_snapshot_id = str(uuid.uuid4())
        new_snapshot = VersionSnapshot(
            snapshot_id=new_snapshot_id,
            document_id=snapshot.document_id,
            user_id=user_id,
            timestamp=datetime.datetime.now(),
            state_vector=snapshot.state_vector,
            document_state=snapshot.document_state,
            metadata={
                'restored_from': snapshot_id,
                'restored_from_timestamp': snapshot.timestamp.isoformat(),
                'restored_by': user_id
            }
        )
        
        # Store the new snapshot
        await self.persistence.store_snapshot(new_snapshot)
        
        return new_snapshot_id


class HistoryHandler:
    """Handles HTTP requests for the version history API.
    
    This class provides methods for handling HTTP requests related to
    version history, such as creating snapshots, retrieving history,
    and generating diffs.
    """
    
    def __init__(self, history_manager: HistoryManager, authorizer: Authorizer):
        """Initialize a new history handler.
        
        Parameters
        ----------
        history_manager : HistoryManager
            The history manager to use
        authorizer : Authorizer
            The authorizer to use for permission checks
        """
        self.history_manager = history_manager
        self.authorizer = authorizer
    
    async def create_snapshot(self, document_id: str, user_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a snapshot of the current document state.
        
        Parameters
        ----------
        document_id : str
            Identifier of the notebook document
        user_id : str
            Identifier of the user creating the snapshot
        metadata : dict, optional
            Additional information about the snapshot
            
        Returns
        -------
        dict
            Dictionary containing the snapshot information
        """
        # Check permissions
        if not await self.authorizer.is_authorized('write', document_id, user_id):
            raise HTTPError(403, "Not authorized to create snapshots for this document")
        
        # Create the snapshot
        snapshot_id = await self.history_manager.create_snapshot(document_id, user_id, metadata)
        
        # Get the snapshot
        snapshot = await self.history_manager.get_snapshot(snapshot_id)
        
        return {
            'snapshot_id': snapshot_id,
            'document_id': document_id,
            'user_id': user_id,
            'timestamp': snapshot.timestamp.isoformat(),
            'metadata': snapshot.metadata
        }
    
    async def get_snapshots(self, document_id: str, user_id: str) -> Dict[str, Any]:
        """Get all snapshots for a document.
        
        Parameters
        ----------
        document_id : str
            Identifier of the notebook document
        user_id : str
            Identifier of the user making the request
            
        Returns
        -------
        dict
            Dictionary containing the snapshots
        """
        # Check permissions
        if not await self.authorizer.is_authorized('read', document_id, user_id):
            raise HTTPError(403, "Not authorized to view snapshots for this document")
        
        # Get the snapshots
        snapshots = await self.history_manager.get_snapshots(document_id)
        
        return {
            'document_id': document_id,
            'snapshots': [{
                'id': s.snapshot_id,
                'timestamp': s.timestamp.isoformat(),
                'user_id': s.user_id,
                'metadata': s.metadata
            } for s in snapshots]
        }
    
    async def get_document_history(self, document_id: str, user_id: str, start_time: Optional[str] = None, end_time: Optional[str] = None) -> Dict[str, Any]:
        """Get a summary of the document's history.
        
        Parameters
        ----------
        document_id : str
            Identifier of the notebook document
        user_id : str
            Identifier of the user making the request
        start_time : str, optional
            Start of the time range (ISO format)
        end_time : str, optional
            End of the time range (ISO format)
            
        Returns
        -------
        dict
            Dictionary containing the history summary
        """
        # Check permissions
        if not await self.authorizer.is_authorized('read', document_id, user_id):
            raise HTTPError(403, "Not authorized to view history for this document")
        
        # Parse time range
        start_datetime = datetime.datetime.fromisoformat(start_time) if start_time else None
        end_datetime = datetime.datetime.fromisoformat(end_time) if end_time else None
        
        # Get the history
        return await self.history_manager.get_document_history(document_id, start_datetime, end_datetime)
    
    async def create_diff(self, from_snapshot_id: str, to_snapshot_id: str, user_id: str) -> Dict[str, Any]:
        """Create a diff between two snapshots.
        
        Parameters
        ----------
        from_snapshot_id : str
            Identifier of the source snapshot
        to_snapshot_id : str
            Identifier of the target snapshot
        user_id : str
            Identifier of the user making the request
            
        Returns
        -------
        dict
            Dictionary containing the diff
        """
        # Get the snapshots to check permissions
        from_snapshot = await self.history_manager.get_snapshot(from_snapshot_id)
        if not from_snapshot:
            raise HTTPError(404, f"Snapshot {from_snapshot_id} not found")
        
        # Check permissions
        if not await self.authorizer.is_authorized('read', from_snapshot.document_id, user_id):
            raise HTTPError(403, "Not authorized to view diffs for this document")
        
        # Create the diff
        diff = await self.history_manager.create_diff(from_snapshot_id, to_snapshot_id)
        
        return diff.to_dict()
    
    async def restore_snapshot(self, snapshot_id: str, user_id: str) -> Dict[str, Any]:
        """Restore a document to a previous snapshot state.
        
        Parameters
        ----------
        snapshot_id : str
            Identifier of the snapshot to restore
        user_id : str
            Identifier of the user performing the restore
            
        Returns
        -------
        dict
            Dictionary containing the new snapshot information
        """
        # Get the snapshot to check permissions
        snapshot = await self.history_manager.get_snapshot(snapshot_id)
        if not snapshot:
            raise HTTPError(404, f"Snapshot {snapshot_id} not found")
        
        # Check permissions
        if not await self.authorizer.is_authorized('write', snapshot.document_id, user_id):
            raise HTTPError(403, "Not authorized to restore snapshots for this document")
        
        # Restore the snapshot
        new_snapshot_id = await self.history_manager.restore_snapshot(snapshot_id, user_id)
        
        # Get the new snapshot
        new_snapshot = await self.history_manager.get_snapshot(new_snapshot_id)
        
        return {
            'snapshot_id': new_snapshot_id,
            'document_id': snapshot.document_id,
            'user_id': user_id,
            'timestamp': new_snapshot.timestamp.isoformat(),
            'metadata': new_snapshot.metadata
        }


# Factory function to create a HistoryManager instance
def create_history_manager(persistence: CollaborationPersistence) -> HistoryManager:
    """Create a new HistoryManager instance.
    
    Parameters
    ----------
    persistence : CollaborationPersistence
        The persistence layer to use
        
    Returns
    -------
    HistoryManager
        A new HistoryManager instance
    """
    return HistoryManager(persistence)


# Factory function to create a HistoryHandler instance
def create_history_handler(history_manager: HistoryManager, authorizer: Authorizer) -> HistoryHandler:
    """Create a new HistoryHandler instance.
    
    Parameters
    ----------
    history_manager : HistoryManager
        The history manager to use
    authorizer : Authorizer
        The authorizer to use for permission checks
        
    Returns
    -------
    HistoryHandler
        A new HistoryHandler instance
    """
    return HistoryHandler(history_manager, authorizer)
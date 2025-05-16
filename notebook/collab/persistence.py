"""Persistence layer for collaborative notebook data.

This module implements the persistence layer for collaborative notebook data, storing
Yjs document updates, version history, user presence information, comments, and permissions.
It provides mechanisms to save and load collaboration state, enabling session recovery
and history reconstruction.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import sqlalchemy as sa
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, 
    create_engine, event, func, text
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import relationship, scoped_session, sessionmaker
from sqlalchemy.pool import QueuePool

from traitlets.config import Configurable
from traitlets import Bool, Int, Unicode, default

# Set up logging
logger = logging.getLogger(__name__)

# Base class for SQLAlchemy models
Base = declarative_base()


class CollaborationSession(Base):
    """Represents a shared editing session for a specific notebook document."""
    
    __tablename__ = 'collaboration_session'
    
    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    metadata = Column(MutableDict.as_mutable(JSONB), nullable=False, default=dict)
    active = Column(Boolean, nullable=False, default=True)
    owner_id = Column(String(255), nullable=False)
    
    # Relationships
    updates = relationship("YjsUpdateRecord", back_populates="session", cascade="all, delete-orphan")
    presence_records = relationship("PresenceRecord", back_populates="session", cascade="all, delete-orphan")
    cell_locks = relationship("CellLock", back_populates="session", cascade="all, delete-orphan")
    permission_entries = relationship("PermissionEntry", back_populates="session", cascade="all, delete-orphan")
    comment_threads = relationship("CommentThread", back_populates="session", cascade="all, delete-orphan")
    version_snapshots = relationship("VersionSnapshot", back_populates="session", cascade="all, delete-orphan")


class YjsUpdateRecord(Base):
    """Stores individual Yjs update messages representing incremental changes."""
    
    __tablename__ = 'yjs_update_record'
    
    update_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('collaboration_session.session_id'), nullable=False)
    sequence_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    update_data = Column(sa.LargeBinary, nullable=False)
    client_id = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    metadata = Column(MutableDict.as_mutable(JSONB), nullable=False, default=dict)
    
    # Relationships
    session = relationship("CollaborationSession", back_populates="updates")
    
    __table_args__ = (
        sa.Index('idx_yjs_update_session_seq', 'session_id', 'sequence_number'),
    )


class PresenceRecord(Base):
    """Tracks user presence and cursor/selection information."""
    
    __tablename__ = 'presence_record'
    
    presence_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('collaboration_session.session_id'), nullable=False)
    user_id = Column(String(255), nullable=False)
    client_id = Column(String(255), nullable=False)
    last_active = Column(DateTime, nullable=False, default=datetime.utcnow)
    cursor_position = Column(MutableDict.as_mutable(JSONB), nullable=True)
    selection_range = Column(MutableDict.as_mutable(JSONB), nullable=True)
    status = Column(String(50), nullable=False, default='active')
    metadata = Column(MutableDict.as_mutable(JSONB), nullable=False, default=dict)
    
    # Relationships
    session = relationship("CollaborationSession", back_populates="presence_records")
    
    __table_args__ = (
        sa.Index('idx_presence_session_user', 'session_id', 'user_id'),
        sa.Index('idx_presence_session_client', 'session_id', 'client_id'),
    )


class CellLock(Base):
    """Represents a lock on a specific cell to prevent concurrent editing conflicts."""
    
    __tablename__ = 'cell_lock'
    
    lock_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('collaboration_session.session_id'), nullable=False)
    cell_id = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    acquired_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    metadata = Column(MutableDict.as_mutable(JSONB), nullable=False, default=dict)
    
    # Relationships
    session = relationship("CollaborationSession", back_populates="cell_locks")
    
    __table_args__ = (
        sa.Index('idx_lock_session_cell', 'session_id', 'cell_id', unique=True),
    )


class PermissionEntry(Base):
    """Defines access control rules for users and groups."""
    
    __tablename__ = 'permission_entry'
    
    permission_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('collaboration_session.session_id'), nullable=False)
    user_id = Column(String(255), nullable=True)  # Null for group permissions
    group_id = Column(String(255), nullable=True)  # Null for user permissions
    resource_id = Column(String(255), nullable=False)  # Document or cell ID
    resource_type = Column(String(50), nullable=False)  # 'document', 'cell', 'comment'
    permission_type = Column(String(50), nullable=False)  # 'view', 'comment', 'edit', 'admin'
    granted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    granted_by = Column(String(255), nullable=False)
    metadata = Column(MutableDict.as_mutable(JSONB), nullable=False, default=dict)
    
    # Relationships
    session = relationship("CollaborationSession", back_populates="permission_entries")
    
    __table_args__ = (
        sa.Index('idx_permission_session_resource', 'session_id', 'resource_id', 'resource_type'),
        sa.Index('idx_permission_user', 'user_id'),
        sa.Index('idx_permission_group', 'group_id'),
        sa.CheckConstraint('(user_id IS NULL) != (group_id IS NULL)', name='ck_user_or_group'),
    )


class CommentThread(Base):
    """Represents a thread of comments attached to a specific cell."""
    
    __tablename__ = 'comment_thread'
    
    thread_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('collaboration_session.session_id'), nullable=False)
    cell_id = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(String(50), nullable=False, default='open')  # 'open', 'resolved', 'archived'
    metadata = Column(MutableDict.as_mutable(JSONB), nullable=False, default=dict)
    
    # Relationships
    session = relationship("CollaborationSession", back_populates="comment_threads")
    comments = relationship("Comment", back_populates="thread", cascade="all, delete-orphan")
    
    __table_args__ = (
        sa.Index('idx_thread_session_cell', 'session_id', 'cell_id'),
    )


class Comment(Base):
    """Represents individual comments within a thread."""
    
    __tablename__ = 'comment'
    
    comment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('comment_thread.thread_id'), nullable=False)
    user_id = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    metadata = Column(MutableDict.as_mutable(JSONB), nullable=False, default=dict)
    
    # Relationships
    thread = relationship("CommentThread", back_populates="comments")
    
    __table_args__ = (
        sa.Index('idx_comment_thread', 'thread_id'),
        sa.Index('idx_comment_user', 'user_id'),
    )


class VersionSnapshot(Base):
    """Stores periodic snapshots of the document state for efficient history navigation."""
    
    __tablename__ = 'version_snapshot'
    
    snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('collaboration_session.session_id'), nullable=False)
    sequence_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    state_vector = Column(sa.LargeBinary, nullable=False)
    document_state = Column(sa.LargeBinary, nullable=False)
    metadata = Column(MutableDict.as_mutable(JSONB), nullable=False, default=dict)
    
    # Relationships
    session = relationship("CollaborationSession", back_populates="version_snapshots")
    
    __table_args__ = (
        sa.Index('idx_snapshot_session_seq', 'session_id', 'sequence_number'),
        sa.Index('idx_snapshot_timestamp', 'timestamp'),
    )


class PersistenceManager(Configurable):
    """Manages persistence of collaborative notebook data.
    
    This class provides methods to save and load Yjs document updates, version history,
    user presence information, comments, and permissions. It handles database connections,
    transaction management, and state recovery.
    """
    
    # Configuration parameters
    db_url = Unicode(
        default_value="",
        help="Database URL for the collaboration state database"
    ).tag(config=True)
    
    pool_size = Int(
        default_value=10,
        help="Connection pool size for the database"
    ).tag(config=True)
    
    max_overflow = Int(
        default_value=20,
        help="Maximum number of connections to overflow from the pool"
    ).tag(config=True)
    
    pool_timeout = Int(
        default_value=30,
        help="Timeout in seconds for getting a connection from the pool"
    ).tag(config=True)
    
    initialize_db = Bool(
        default_value=False,
        help="Whether to initialize the database schema on startup"
    ).tag(config=True)
    
    snapshot_interval = Int(
        default_value=100,
        help="Number of updates between automatic version snapshots"
    ).tag(config=True)
    
    lock_timeout = Int(
        default_value=300,  # 5 minutes
        help="Default timeout in seconds for cell locks"
    ).tag(config=True)
    
    presence_timeout = Int(
        default_value=60,  # 1 minute
        help="Timeout in seconds for user presence before marking as idle"
    ).tag(config=True)
    
    cleanup_interval = Int(
        default_value=3600,  # 1 hour
        help="Interval in seconds for running cleanup tasks"
    ).tag(config=True)
    
    def __init__(self, **kwargs):
        """Initialize the persistence manager."""
        super().__init__(**kwargs)
        self._engine = None
        self._session_factory = None
        self._Session = None
        self._last_cleanup = time.time()
        self._initialize_db_connection()
    
    @default('db_url')
    def _default_db_url(self):
        """Get the database URL from environment variables if not specified."""
        return os.environ.get('JUPYTER_COLLABORATION_DB_URL', '')
    
    def _initialize_db_connection(self):
        """Initialize the database connection and session factory."""
        if not self.db_url:
            logger.warning("No database URL provided for collaboration persistence. Using in-memory SQLite.")
            self.db_url = "sqlite:///:memory:"
        
        # Create engine with connection pooling
        self._engine = create_engine(
            self.db_url,
            poolclass=QueuePool,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_timeout=self.pool_timeout,
            pool_pre_ping=True,  # Verify connections before using them
        )
        
        # Create session factory
        self._session_factory = sessionmaker(bind=self._engine)
        self._Session = scoped_session(self._session_factory)
        
        # Initialize database schema if requested
        if self.initialize_db:
            self._initialize_schema()
    
    def _initialize_schema(self):
        """Initialize the database schema."""
        logger.info("Initializing collaboration database schema")
        Base.metadata.create_all(self._engine)
    
    def get_session(self):
        """Get a database session.
        
        Returns:
            SQLAlchemy session object
        """
        return self._Session()
    
    def create_collaboration_session(self, document_id, owner_id, metadata=None):
        """Create a new collaboration session for a document.
        
        Args:
            document_id (str): Identifier of the notebook document
            owner_id (str): User identifier of the session owner
            metadata (dict, optional): Additional session metadata
            
        Returns:
            str: The session ID of the created session
        """
        if metadata is None:
            metadata = {}
        
        session = self.get_session()
        try:
            collab_session = CollaborationSession(
                document_id=document_id,
                owner_id=owner_id,
                metadata=metadata
            )
            session.add(collab_session)
            session.commit()
            return str(collab_session.session_id)
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating collaboration session: {e}")
            raise
        finally:
            session.close()
    
    def get_collaboration_session(self, session_id):
        """Get a collaboration session by ID.
        
        Args:
            session_id (str): The session ID to retrieve
            
        Returns:
            dict: Session information or None if not found
        """
        session = self.get_session()
        try:
            collab_session = session.query(CollaborationSession).filter(
                CollaborationSession.session_id == session_id
            ).first()
            
            if collab_session is None:
                return None
            
            return {
                'session_id': str(collab_session.session_id),
                'document_id': collab_session.document_id,
                'created_at': collab_session.created_at.isoformat(),
                'updated_at': collab_session.updated_at.isoformat(),
                'metadata': collab_session.metadata,
                'active': collab_session.active,
                'owner_id': collab_session.owner_id
            }
        except Exception as e:
            logger.error(f"Error retrieving collaboration session: {e}")
            raise
        finally:
            session.close()
    
    def get_collaboration_sessions_for_document(self, document_id):
        """Get all collaboration sessions for a document.
        
        Args:
            document_id (str): The document ID to query
            
        Returns:
            list: List of session information dictionaries
        """
        session = self.get_session()
        try:
            collab_sessions = session.query(CollaborationSession).filter(
                CollaborationSession.document_id == document_id,
                CollaborationSession.active == True
            ).all()
            
            return [
                {
                    'session_id': str(cs.session_id),
                    'document_id': cs.document_id,
                    'created_at': cs.created_at.isoformat(),
                    'updated_at': cs.updated_at.isoformat(),
                    'metadata': cs.metadata,
                    'active': cs.active,
                    'owner_id': cs.owner_id
                }
                for cs in collab_sessions
            ]
        except Exception as e:
            logger.error(f"Error retrieving collaboration sessions for document: {e}")
            raise
        finally:
            session.close()
    
    def update_collaboration_session(self, session_id, metadata=None, active=None):
        """Update a collaboration session.
        
        Args:
            session_id (str): The session ID to update
            metadata (dict, optional): Updated metadata (will be merged with existing)
            active (bool, optional): Whether the session is active
            
        Returns:
            bool: True if successful, False if session not found
        """
        session = self.get_session()
        try:
            collab_session = session.query(CollaborationSession).filter(
                CollaborationSession.session_id == session_id
            ).first()
            
            if collab_session is None:
                return False
            
            if metadata is not None:
                # Merge new metadata with existing
                if collab_session.metadata is None:
                    collab_session.metadata = metadata
                else:
                    collab_session.metadata.update(metadata)
            
            if active is not None:
                collab_session.active = active
            
            # Updated timestamp will be set automatically by SQLAlchemy
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating collaboration session: {e}")
            raise
        finally:
            session.close()
    
    def store_update(self, session_id, sequence_number, update_data, client_id, user_id, metadata=None):
        """Store a Yjs update message.
        
        Args:
            session_id (str): The collaboration session ID
            sequence_number (int): Monotonically increasing sequence number
            update_data (bytes): Binary-encoded Yjs update message
            client_id (str): Client identifier that generated the update
            user_id (str): User identifier who made the change
            metadata (dict, optional): Additional update metadata
            
        Returns:
            str: The update ID of the stored update
        """
        if metadata is None:
            metadata = {}
        
        session = self.get_session()
        try:
            update = YjsUpdateRecord(
                session_id=session_id,
                sequence_number=sequence_number,
                update_data=update_data,
                client_id=client_id,
                user_id=user_id,
                metadata=metadata
            )
            session.add(update)
            
            # Check if we need to create a snapshot
            if sequence_number % self.snapshot_interval == 0:
                # This would be handled by a separate method in a real implementation
                # that would generate the snapshot from the current state
                pass
            
            session.commit()
            
            # Update the session's updated_at timestamp
            self.update_collaboration_session(session_id)
            
            return str(update.update_id)
        except Exception as e:
            session.rollback()
            logger.error(f"Error storing update: {e}")
            raise
        finally:
            session.close()
    
    def get_updates(self, session_id, start_sequence=None, end_sequence=None, limit=None):
        """Get Yjs updates for a session.
        
        Args:
            session_id (str): The collaboration session ID
            start_sequence (int, optional): Starting sequence number (inclusive)
            end_sequence (int, optional): Ending sequence number (inclusive)
            limit (int, optional): Maximum number of updates to return
            
        Returns:
            list: List of update records
        """
        session = self.get_session()
        try:
            query = session.query(YjsUpdateRecord).filter(
                YjsUpdateRecord.session_id == session_id
            ).order_by(YjsUpdateRecord.sequence_number)
            
            if start_sequence is not None:
                query = query.filter(YjsUpdateRecord.sequence_number >= start_sequence)
            
            if end_sequence is not None:
                query = query.filter(YjsUpdateRecord.sequence_number <= end_sequence)
            
            if limit is not None:
                query = query.limit(limit)
            
            updates = query.all()
            
            return [
                {
                    'update_id': str(update.update_id),
                    'session_id': str(update.session_id),
                    'sequence_number': update.sequence_number,
                    'timestamp': update.timestamp.isoformat(),
                    'update_data': update.update_data,
                    'client_id': update.client_id,
                    'user_id': update.user_id,
                    'metadata': update.metadata
                }
                for update in updates
            ]
        except Exception as e:
            logger.error(f"Error retrieving updates: {e}")
            raise
        finally:
            session.close()
    
    def store_snapshot(self, session_id, sequence_number, state_vector, document_state, metadata=None):
        """Store a version snapshot of the document state.
        
        Args:
            session_id (str): The collaboration session ID
            sequence_number (int): Sequence number of the snapshot
            state_vector (bytes): Yjs state vector for the snapshot
            document_state (bytes): Serialized document state
            metadata (dict, optional): Additional snapshot metadata
            
        Returns:
            str: The snapshot ID of the stored snapshot
        """
        if metadata is None:
            metadata = {}
        
        session = self.get_session()
        try:
            snapshot = VersionSnapshot(
                session_id=session_id,
                sequence_number=sequence_number,
                state_vector=state_vector,
                document_state=document_state,
                metadata=metadata
            )
            session.add(snapshot)
            session.commit()
            return str(snapshot.snapshot_id)
        except Exception as e:
            session.rollback()
            logger.error(f"Error storing snapshot: {e}")
            raise
        finally:
            session.close()
    
    def get_latest_snapshot(self, session_id):
        """Get the latest version snapshot for a session.
        
        Args:
            session_id (str): The collaboration session ID
            
        Returns:
            dict: Snapshot information or None if not found
        """
        session = self.get_session()
        try:
            snapshot = session.query(VersionSnapshot).filter(
                VersionSnapshot.session_id == session_id
            ).order_by(VersionSnapshot.sequence_number.desc()).first()
            
            if snapshot is None:
                return None
            
            return {
                'snapshot_id': str(snapshot.snapshot_id),
                'session_id': str(snapshot.session_id),
                'sequence_number': snapshot.sequence_number,
                'timestamp': snapshot.timestamp.isoformat(),
                'state_vector': snapshot.state_vector,
                'document_state': snapshot.document_state,
                'metadata': snapshot.metadata
            }
        except Exception as e:
            logger.error(f"Error retrieving latest snapshot: {e}")
            raise
        finally:
            session.close()
    
    def update_presence(self, session_id, user_id, client_id, cursor_position=None, 
                       selection_range=None, status=None, metadata=None):
        """Update user presence information.
        
        Args:
            session_id (str): The collaboration session ID
            user_id (str): User identifier
            client_id (str): Client identifier
            cursor_position (dict, optional): Current cursor position data
            selection_range (dict, optional): Current text selection range
            status (str, optional): User status (active, idle, away)
            metadata (dict, optional): Additional presence information
            
        Returns:
            str: The presence record ID
        """
        if metadata is None:
            metadata = {}
        
        session = self.get_session()
        try:
            # Check if presence record already exists
            presence = session.query(PresenceRecord).filter(
                PresenceRecord.session_id == session_id,
                PresenceRecord.user_id == user_id,
                PresenceRecord.client_id == client_id
            ).first()
            
            if presence is None:
                # Create new presence record
                presence = PresenceRecord(
                    session_id=session_id,
                    user_id=user_id,
                    client_id=client_id,
                    cursor_position=cursor_position,
                    selection_range=selection_range,
                    status=status or 'active',
                    metadata=metadata
                )
                session.add(presence)
            else:
                # Update existing presence record
                presence.last_active = datetime.utcnow()
                
                if cursor_position is not None:
                    presence.cursor_position = cursor_position
                
                if selection_range is not None:
                    presence.selection_range = selection_range
                
                if status is not None:
                    presence.status = status
                
                if metadata is not None:
                    # Merge new metadata with existing
                    if presence.metadata is None:
                        presence.metadata = metadata
                    else:
                        presence.metadata.update(metadata)
            
            session.commit()
            return str(presence.presence_id)
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating presence: {e}")
            raise
        finally:
            session.close()
    
    def get_presence(self, session_id):
        """Get all presence records for a session.
        
        Args:
            session_id (str): The collaboration session ID
            
        Returns:
            list: List of presence records
        """
        session = self.get_session()
        try:
            # Get only active presence records (updated within presence_timeout)
            timeout = datetime.utcnow() - timedelta(seconds=self.presence_timeout)
            presence_records = session.query(PresenceRecord).filter(
                PresenceRecord.session_id == session_id,
                PresenceRecord.last_active >= timeout
            ).all()
            
            return [
                {
                    'presence_id': str(pr.presence_id),
                    'session_id': str(pr.session_id),
                    'user_id': pr.user_id,
                    'client_id': pr.client_id,
                    'last_active': pr.last_active.isoformat(),
                    'cursor_position': pr.cursor_position,
                    'selection_range': pr.selection_range,
                    'status': pr.status,
                    'metadata': pr.metadata
                }
                for pr in presence_records
            ]
        except Exception as e:
            logger.error(f"Error retrieving presence records: {e}")
            raise
        finally:
            session.close()
    
    def acquire_cell_lock(self, session_id, cell_id, user_id, timeout=None, metadata=None):
        """Acquire a lock on a cell.
        
        Args:
            session_id (str): The collaboration session ID
            cell_id (str): Identifier of the cell to lock
            user_id (str): User who wants to acquire the lock
            timeout (int, optional): Lock timeout in seconds (default: self.lock_timeout)
            metadata (dict, optional): Additional lock information
            
        Returns:
            dict: Lock information if successful, None if cell is already locked
        """
        if metadata is None:
            metadata = {}
        
        if timeout is None:
            timeout = self.lock_timeout
        
        session = self.get_session()
        try:
            # Check if cell is already locked by someone else
            existing_lock = session.query(CellLock).filter(
                CellLock.session_id == session_id,
                CellLock.cell_id == cell_id,
                CellLock.expires_at > datetime.utcnow()  # Lock hasn't expired
            ).first()
            
            if existing_lock is not None and existing_lock.user_id != user_id:
                # Cell is locked by someone else
                return None
            
            # Calculate expiration time
            expires_at = datetime.utcnow() + timedelta(seconds=timeout)
            
            if existing_lock is not None and existing_lock.user_id == user_id:
                # Update existing lock
                existing_lock.expires_at = expires_at
                existing_lock.metadata.update(metadata)
                lock = existing_lock
            else:
                # Create new lock
                lock = CellLock(
                    session_id=session_id,
                    cell_id=cell_id,
                    user_id=user_id,
                    expires_at=expires_at,
                    metadata=metadata
                )
                session.add(lock)
            
            session.commit()
            
            return {
                'lock_id': str(lock.lock_id),
                'session_id': str(lock.session_id),
                'cell_id': lock.cell_id,
                'user_id': lock.user_id,
                'acquired_at': lock.acquired_at.isoformat(),
                'expires_at': lock.expires_at.isoformat(),
                'metadata': lock.metadata
            }
        except Exception as e:
            session.rollback()
            logger.error(f"Error acquiring cell lock: {e}")
            raise
        finally:
            session.close()
    
    def release_cell_lock(self, session_id, cell_id, user_id):
        """Release a lock on a cell.
        
        Args:
            session_id (str): The collaboration session ID
            cell_id (str): Identifier of the cell to unlock
            user_id (str): User who wants to release the lock
            
        Returns:
            bool: True if successful, False if lock not found or not owned by user
        """
        session = self.get_session()
        try:
            # Find the lock
            lock = session.query(CellLock).filter(
                CellLock.session_id == session_id,
                CellLock.cell_id == cell_id
            ).first()
            
            if lock is None:
                return False
            
            # Check if user owns the lock
            if lock.user_id != user_id:
                return False
            
            # Delete the lock
            session.delete(lock)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error releasing cell lock: {e}")
            raise
        finally:
            session.close()
    
    def get_cell_locks(self, session_id):
        """Get all active cell locks for a session.
        
        Args:
            session_id (str): The collaboration session ID
            
        Returns:
            list: List of active lock records
        """
        session = self.get_session()
        try:
            # Get only non-expired locks
            locks = session.query(CellLock).filter(
                CellLock.session_id == session_id,
                CellLock.expires_at > datetime.utcnow()  # Lock hasn't expired
            ).all()
            
            return [
                {
                    'lock_id': str(lock.lock_id),
                    'session_id': str(lock.session_id),
                    'cell_id': lock.cell_id,
                    'user_id': lock.user_id,
                    'acquired_at': lock.acquired_at.isoformat(),
                    'expires_at': lock.expires_at.isoformat(),
                    'metadata': lock.metadata
                }
                for lock in locks
            ]
        except Exception as e:
            logger.error(f"Error retrieving cell locks: {e}")
            raise
        finally:
            session.close()
    
    def create_comment_thread(self, session_id, cell_id, user_id, content, metadata=None):
        """Create a new comment thread with an initial comment.
        
        Args:
            session_id (str): The collaboration session ID
            cell_id (str): Identifier of the cell to comment on
            user_id (str): User creating the comment
            content (str): Comment content
            metadata (dict, optional): Additional thread metadata
            
        Returns:
            dict: Thread and comment information
        """
        if metadata is None:
            metadata = {}
        
        session = self.get_session()
        try:
            # Create new thread
            thread = CommentThread(
                session_id=session_id,
                cell_id=cell_id,
                metadata=metadata
            )
            session.add(thread)
            
            # Create initial comment
            comment = Comment(
                thread=thread,  # Use relationship to set thread_id
                user_id=user_id,
                content=content,
                metadata={}
            )
            session.add(comment)
            
            session.commit()
            
            return {
                'thread_id': str(thread.thread_id),
                'session_id': str(thread.session_id),
                'cell_id': thread.cell_id,
                'created_at': thread.created_at.isoformat(),
                'status': thread.status,
                'metadata': thread.metadata,
                'comment': {
                    'comment_id': str(comment.comment_id),
                    'user_id': comment.user_id,
                    'content': comment.content,
                    'created_at': comment.created_at.isoformat(),
                    'updated_at': comment.updated_at.isoformat(),
                    'metadata': comment.metadata
                }
            }
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating comment thread: {e}")
            raise
        finally:
            session.close()
    
    def add_comment(self, thread_id, user_id, content, metadata=None):
        """Add a comment to an existing thread.
        
        Args:
            thread_id (str): The thread ID to add the comment to
            user_id (str): User creating the comment
            content (str): Comment content
            metadata (dict, optional): Additional comment metadata
            
        Returns:
            dict: Comment information or None if thread not found
        """
        if metadata is None:
            metadata = {}
        
        session = self.get_session()
        try:
            # Check if thread exists
            thread = session.query(CommentThread).filter(
                CommentThread.thread_id == thread_id
            ).first()
            
            if thread is None:
                return None
            
            # Create new comment
            comment = Comment(
                thread_id=thread_id,
                user_id=user_id,
                content=content,
                metadata=metadata
            )
            session.add(comment)
            
            # Update thread status if it was resolved
            if thread.status == 'resolved':
                thread.status = 'open'
            
            session.commit()
            
            return {
                'comment_id': str(comment.comment_id),
                'thread_id': str(comment.thread_id),
                'user_id': comment.user_id,
                'content': comment.content,
                'created_at': comment.created_at.isoformat(),
                'updated_at': comment.updated_at.isoformat(),
                'metadata': comment.metadata
            }
        except Exception as e:
            session.rollback()
            logger.error(f"Error adding comment: {e}")
            raise
        finally:
            session.close()
    
    def get_comment_threads(self, session_id, cell_id=None, status=None):
        """Get comment threads for a session.
        
        Args:
            session_id (str): The collaboration session ID
            cell_id (str, optional): Filter by cell ID
            status (str, optional): Filter by thread status
            
        Returns:
            list: List of thread records with comments
        """
        session = self.get_session()
        try:
            # Build query
            query = session.query(CommentThread).filter(
                CommentThread.session_id == session_id
            )
            
            if cell_id is not None:
                query = query.filter(CommentThread.cell_id == cell_id)
            
            if status is not None:
                query = query.filter(CommentThread.status == status)
            
            threads = query.all()
            
            result = []
            for thread in threads:
                # Get comments for this thread
                comments = session.query(Comment).filter(
                    Comment.thread_id == thread.thread_id
                ).order_by(Comment.created_at).all()
                
                thread_data = {
                    'thread_id': str(thread.thread_id),
                    'session_id': str(thread.session_id),
                    'cell_id': thread.cell_id,
                    'created_at': thread.created_at.isoformat(),
                    'status': thread.status,
                    'metadata': thread.metadata,
                    'comments': [
                        {
                            'comment_id': str(comment.comment_id),
                            'user_id': comment.user_id,
                            'content': comment.content,
                            'created_at': comment.created_at.isoformat(),
                            'updated_at': comment.updated_at.isoformat(),
                            'metadata': comment.metadata
                        }
                        for comment in comments
                    ]
                }
                result.append(thread_data)
            
            return result
        except Exception as e:
            logger.error(f"Error retrieving comment threads: {e}")
            raise
        finally:
            session.close()
    
    def update_thread_status(self, thread_id, status, user_id):
        """Update the status of a comment thread.
        
        Args:
            thread_id (str): The thread ID to update
            status (str): New status ('open', 'resolved', 'archived')
            user_id (str): User updating the status
            
        Returns:
            bool: True if successful, False if thread not found
        """
        session = self.get_session()
        try:
            # Check if thread exists
            thread = session.query(CommentThread).filter(
                CommentThread.thread_id == thread_id
            ).first()
            
            if thread is None:
                return False
            
            # Update status
            thread.status = status
            
            # Add status change to metadata
            if thread.metadata is None:
                thread.metadata = {}
            
            if 'status_history' not in thread.metadata:
                thread.metadata['status_history'] = []
            
            thread.metadata['status_history'].append({
                'status': status,
                'changed_by': user_id,
                'timestamp': datetime.utcnow().isoformat()
            })
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating thread status: {e}")
            raise
        finally:
            session.close()
    
    def set_permission(self, session_id, resource_id, resource_type, permission_type, 
                      user_id=None, group_id=None, granted_by=None, metadata=None):
        """Set a permission for a user or group on a resource.
        
        Args:
            session_id (str): The collaboration session ID
            resource_id (str): Identifier of the resource (document, cell)
            resource_type (str): Type of resource ('document', 'cell', 'comment')
            permission_type (str): Type of permission ('view', 'comment', 'edit', 'admin')
            user_id (str, optional): User identifier (required if group_id is None)
            group_id (str, optional): Group identifier (required if user_id is None)
            granted_by (str, optional): User who granted the permission
            metadata (dict, optional): Additional permission information
            
        Returns:
            str: The permission ID of the created permission
        """
        if metadata is None:
            metadata = {}
        
        if user_id is None and group_id is None:
            raise ValueError("Either user_id or group_id must be provided")
        
        if user_id is not None and group_id is not None:
            raise ValueError("Only one of user_id or group_id can be provided")
        
        if granted_by is None:
            granted_by = user_id or "system"
        
        session = self.get_session()
        try:
            # Check if permission already exists
            query = session.query(PermissionEntry).filter(
                PermissionEntry.session_id == session_id,
                PermissionEntry.resource_id == resource_id,
                PermissionEntry.resource_type == resource_type
            )
            
            if user_id is not None:
                query = query.filter(PermissionEntry.user_id == user_id)
            else:
                query = query.filter(PermissionEntry.group_id == group_id)
            
            existing_permission = query.first()
            
            if existing_permission is not None:
                # Update existing permission
                existing_permission.permission_type = permission_type
                existing_permission.granted_by = granted_by
                existing_permission.granted_at = datetime.utcnow()
                
                # Merge new metadata with existing
                if existing_permission.metadata is None:
                    existing_permission.metadata = metadata
                else:
                    existing_permission.metadata.update(metadata)
                
                permission = existing_permission
            else:
                # Create new permission
                permission = PermissionEntry(
                    session_id=session_id,
                    resource_id=resource_id,
                    resource_type=resource_type,
                    permission_type=permission_type,
                    user_id=user_id,
                    group_id=group_id,
                    granted_by=granted_by,
                    metadata=metadata
                )
                session.add(permission)
            
            session.commit()
            return str(permission.permission_id)
        except Exception as e:
            session.rollback()
            logger.error(f"Error setting permission: {e}")
            raise
        finally:
            session.close()
    
    def get_permissions(self, session_id, resource_id=None, resource_type=None, user_id=None, group_id=None):
        """Get permissions for a session.
        
        Args:
            session_id (str): The collaboration session ID
            resource_id (str, optional): Filter by resource ID
            resource_type (str, optional): Filter by resource type
            user_id (str, optional): Filter by user ID
            group_id (str, optional): Filter by group ID
            
        Returns:
            list: List of permission records
        """
        session = self.get_session()
        try:
            # Build query
            query = session.query(PermissionEntry).filter(
                PermissionEntry.session_id == session_id
            )
            
            if resource_id is not None:
                query = query.filter(PermissionEntry.resource_id == resource_id)
            
            if resource_type is not None:
                query = query.filter(PermissionEntry.resource_type == resource_type)
            
            if user_id is not None:
                query = query.filter(PermissionEntry.user_id == user_id)
            
            if group_id is not None:
                query = query.filter(PermissionEntry.group_id == group_id)
            
            permissions = query.all()
            
            return [
                {
                    'permission_id': str(perm.permission_id),
                    'session_id': str(perm.session_id),
                    'user_id': perm.user_id,
                    'group_id': perm.group_id,
                    'resource_id': perm.resource_id,
                    'resource_type': perm.resource_type,
                    'permission_type': perm.permission_type,
                    'granted_at': perm.granted_at.isoformat(),
                    'granted_by': perm.granted_by,
                    'metadata': perm.metadata
                }
                for perm in permissions
            ]
        except Exception as e:
            logger.error(f"Error retrieving permissions: {e}")
            raise
        finally:
            session.close()
    
    def remove_permission(self, permission_id):
        """Remove a permission.
        
        Args:
            permission_id (str): The permission ID to remove
            
        Returns:
            bool: True if successful, False if permission not found
        """
        session = self.get_session()
        try:
            # Find the permission
            permission = session.query(PermissionEntry).filter(
                PermissionEntry.permission_id == permission_id
            ).first()
            
            if permission is None:
                return False
            
            # Delete the permission
            session.delete(permission)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error removing permission: {e}")
            raise
        finally:
            session.close()
    
    def check_permission(self, session_id, resource_id, resource_type, user_id, required_permission):
        """Check if a user has the required permission on a resource.
        
        Args:
            session_id (str): The collaboration session ID
            resource_id (str): Identifier of the resource
            resource_type (str): Type of resource
            user_id (str): User to check permissions for
            required_permission (str): Required permission type
            
        Returns:
            bool: True if user has permission, False otherwise
        """
        # Permission hierarchy: admin > edit > comment > view
        permission_hierarchy = {
            'admin': 4,
            'edit': 3,
            'comment': 2,
            'view': 1
        }
        
        required_level = permission_hierarchy.get(required_permission, 0)
        if required_level == 0:
            logger.warning(f"Invalid permission type: {required_permission}")
            return False
        
        session = self.get_session()
        try:
            # Get collaboration session to check owner
            collab_session = session.query(CollaborationSession).filter(
                CollaborationSession.session_id == session_id
            ).first()
            
            if collab_session is None:
                return False
            
            # Session owner always has admin permission
            if collab_session.owner_id == user_id:
                return True
            
            # Check user-specific permissions
            user_permission = session.query(PermissionEntry).filter(
                PermissionEntry.session_id == session_id,
                PermissionEntry.resource_id == resource_id,
                PermissionEntry.resource_type == resource_type,
                PermissionEntry.user_id == user_id
            ).first()
            
            if user_permission is not None:
                user_level = permission_hierarchy.get(user_permission.permission_type, 0)
                if user_level >= required_level:
                    return True
            
            # Check document-level permissions if this is a cell
            if resource_type == 'cell':
                doc_permission = session.query(PermissionEntry).filter(
                    PermissionEntry.session_id == session_id,
                    PermissionEntry.resource_id == collab_session.document_id,
                    PermissionEntry.resource_type == 'document',
                    PermissionEntry.user_id == user_id
                ).first()
                
                if doc_permission is not None:
                    doc_level = permission_hierarchy.get(doc_permission.permission_type, 0)
                    if doc_level >= required_level:
                        return True
            
            # TODO: Check group permissions
            
            return False
        except Exception as e:
            logger.error(f"Error checking permission: {e}")
            raise
        finally:
            session.close()
    
    def run_cleanup(self, force=False):
        """Run cleanup tasks to remove expired locks and inactive presence records.
        
        Args:
            force (bool): Force cleanup regardless of interval
            
        Returns:
            dict: Cleanup statistics
        """
        current_time = time.time()
        if not force and (current_time - self._last_cleanup) < self.cleanup_interval:
            # Not time to run cleanup yet
            return {'skipped': True, 'next_cleanup': self._last_cleanup + self.cleanup_interval}
        
        session = self.get_session()
        try:
            # Remove expired locks
            expired_locks = session.query(CellLock).filter(
                CellLock.expires_at < datetime.utcnow()
            ).delete()
            
            # Remove inactive presence records
            timeout = datetime.utcnow() - timedelta(seconds=self.presence_timeout * 10)  # 10x normal timeout
            inactive_presence = session.query(PresenceRecord).filter(
                PresenceRecord.last_active < timeout
            ).delete()
            
            # TODO: Implement update compaction to reduce storage
            
            session.commit()
            self._last_cleanup = current_time
            
            return {
                'skipped': False,
                'expired_locks_removed': expired_locks,
                'inactive_presence_removed': inactive_presence,
                'next_cleanup': current_time + self.cleanup_interval
            }
        except Exception as e:
            session.rollback()
            logger.error(f"Error running cleanup: {e}")
            raise
        finally:
            session.close()
    
    def compact_updates(self, session_id, max_age=None):
        """Compact update records by creating snapshots and removing old updates.
        
        Args:
            session_id (str): The collaboration session ID
            max_age (int, optional): Maximum age in seconds of updates to keep
            
        Returns:
            dict: Compaction statistics
        """
        # This is a placeholder for a more complex implementation
        # In a real implementation, this would:
        # 1. Create a new snapshot of the current document state
        # 2. Remove all updates older than the snapshot (or max_age)
        # 3. Keep a minimum number of snapshots for history navigation
        
        logger.info(f"Compacting updates for session {session_id}")
        return {
            'session_id': session_id,
            'compacted': True,
            'updates_removed': 0,
            'snapshot_created': False
        }
    
    def close(self):
        """Close the database connection."""
        if self._Session is not None:
            self._Session.remove()
        
        if self._engine is not None:
            self._engine.dispose()
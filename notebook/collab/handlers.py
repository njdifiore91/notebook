"""WebSocket handlers for real-time collaboration in Jupyter Notebook."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set, Union
import uuid

from tornado.websocket import WebSocketHandler, WebSocketClosedError
from tornado.web import HTTPError
from jupyter_server.base.handlers import JupyterHandler
from jupyter_server.auth import authorized

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
        encode_awareness_update,
        encode_state_as_update,
        encode_state_vector,
        decode_awareness_update,
        decode_state_vector,
        decode_update,
    )
    HAS_PYCRDT_WEBSOCKET = True
except ImportError:
    HAS_PYCRDT_WEBSOCKET = False

from .store import CollaborationStore
from .auth import CollaborationAuthorizer

# Set up logging
logger = logging.getLogger('notebook.collab.handlers')


class CollaborationWebSocketHandler(WebSocketHandler, JupyterHandler):
    """WebSocket handler for real-time collaboration using Yjs CRDT framework.
    
    This handler manages WebSocket connections for document synchronization,
    user presence awareness, cell locking, and comment system. It implements
    the Yjs protocol for CRDT operations and integrates with the persistence
    layer and authentication system.
    """
    
    # Class variables to track active connections and documents
    # Maps notebook_id to a set of connected handlers
    _connections: Dict[str, Set['CollaborationWebSocketHandler']] = {}
    # Maps notebook_id to the shared Yjs document
    _documents: Dict[str, Doc] = {}
    # Maps notebook_id to a dict of cell locks (cell_id -> user_id)
    _cell_locks: Dict[str, Dict[str, str]] = {}
    # Flag to track if the handler is closing
    _closing: bool = False
    # Store instance for persistence
    _store: Optional[CollaborationStore] = None
    # Authorizer for permission checks
    _authorizer: Optional[CollaborationAuthorizer] = None
    
    def initialize(self, **kwargs: Any) -> None:
        """Initialize the handler with configuration."""
        super().initialize(**kwargs)
        
        # Check if required dependencies are available
        if not HAS_PYCRDT or not HAS_PYCRDT_WEBSOCKET:
            logger.error("Required dependencies not available: pycrdt and pycrdt-websocket")
            raise ImportError(
                "Collaboration features require pycrdt and pycrdt-websocket. "
                "Please install with: pip install pycrdt pycrdt-websocket"
            )
        
        # Get the collaboration store from settings
        self._store = self.settings.get('collaboration_store')
        if self._store is None:
            from .store import MemoryCollaborationStore
            self._store = MemoryCollaborationStore()
            self.settings['collaboration_store'] = self._store
        
        # Get the collaboration authorizer from settings
        self._authorizer = self.settings.get('collaboration_authorizer')
        if self._authorizer is None:
            self._authorizer = CollaborationAuthorizer()
            self.settings['collaboration_authorizer'] = self._authorizer
    
    def check_origin(self, origin: str) -> bool:
        """Check if the origin is allowed.
        
        This method is called during the WebSocket handshake to verify that
        the origin is allowed to connect.
        
        Args:
            origin: The origin of the WebSocket connection
            
        Returns:
            bool: True if the origin is allowed, False otherwise
        """
        # Use the same origin check as the Jupyter server
        return self.allow_origin(origin)
    
    def select_subprotocol(self, subprotocols: List[str]) -> Optional[str]:
        """Select the WebSocket subprotocol to use.
        
        Args:
            subprotocols: List of subprotocols offered by the client
            
        Returns:
            Optional[str]: The selected subprotocol or None
        """
        # Yjs WebSocket provider uses 'yjs' as the subprotocol
        if 'yjs' in subprotocols:
            return 'yjs'
        return None
    
    def get_notebook_id(self) -> str:
        """Extract the notebook ID from the request path.
        
        Returns:
            str: The notebook ID
        """
        # The path format is expected to be /api/collaboration/{notebook_id}
        path_parts = self.request.path.strip('/').split('/')
        if len(path_parts) < 3:
            raise HTTPError(400, "Invalid collaboration WebSocket path")
        return path_parts[2]
    
    def get_user_id(self) -> str:
        """Get the current user's ID.
        
        Returns:
            str: The user ID
        """
        # Use the Jupyter server's user information if available
        if hasattr(self, 'current_user') and self.current_user:
            if hasattr(self.current_user, 'name'):
                return self.current_user.name
            return str(self.current_user)
        
        # Fallback to a generated ID if user info is not available
        return f"anonymous-{uuid.uuid4().hex[:8]}"
    
    def get_user_info(self) -> Dict[str, Any]:
        """Get information about the current user for awareness.
        
        Returns:
            Dict[str, Any]: User information including ID, name, and color
        """
        user_id = self.get_user_id()
        
        # Try to get more user information if available
        user_name = user_id
        user_color = self._generate_user_color(user_id)
        
        if hasattr(self, 'current_user') and self.current_user:
            if hasattr(self.current_user, 'name'):
                user_name = self.current_user.name
            if hasattr(self.current_user, 'email'):
                user_email = getattr(self.current_user, 'email', '')
            if hasattr(self.current_user, 'avatar_url'):
                user_avatar = getattr(self.current_user, 'avatar_url', '')
        
        return {
            "id": user_id,
            "name": user_name,
            "color": user_color,
            # Add other user information as needed
        }
    
    def _generate_user_color(self, user_id: str) -> str:
        """Generate a consistent color for a user based on their ID.
        
        Args:
            user_id: The user ID
            
        Returns:
            str: A hex color code
        """
        # Simple hash function to generate a color from user_id
        hash_val = sum(ord(c) for c in user_id) % 360
        return f"hsl({hash_val}, 70%, 50%)"
    
    @authorized('notebook:join')
    async def open(self, *args: Any, **kwargs: Any) -> None:
        """Handle WebSocket connection open.
        
        This method is called when a new WebSocket connection is established.
        It initializes the collaboration session for the notebook.
        """
        if self._closing:
            return
        
        try:
            # Get the notebook ID from the request path
            notebook_id = self.get_notebook_id()
            user_id = self.get_user_id()
            
            # Check if the user is authorized to join this notebook
            if not self._authorizer.is_authorized_for_collaboration(self, 'join', notebook_id):
                logger.warning(f"Unauthorized collaboration access attempt by {user_id} for notebook {notebook_id}")
                self.close(code=403, reason="Unauthorized")
                return
            
            # Initialize connection tracking for this notebook if needed
            if notebook_id not in self._connections:
                self._connections[notebook_id] = set()
            
            # Add this connection to the set of connections for this notebook
            self._connections[notebook_id].add(self)
            
            # Initialize the shared document if it doesn't exist
            if notebook_id not in self._documents:
                # Create a new Yjs document
                doc = Doc()
                self._documents[notebook_id] = doc
                
                # Try to load the document state from the store
                try:
                    if self._store:
                        state = await self._store.load_document(notebook_id)
                        if state:
                            doc.apply_update(state)
                except Exception as e:
                    logger.error(f"Error loading document state for {notebook_id}: {e}")
            
            # Initialize cell locks for this notebook if needed
            if notebook_id not in self._cell_locks:
                self._cell_locks[notebook_id] = {}
                
                # Try to load cell locks from the store
                try:
                    if self._store:
                        locks = await self._store.load_cell_locks(notebook_id)
                        if locks:
                            self._cell_locks[notebook_id] = locks
                except Exception as e:
                    logger.error(f"Error loading cell locks for {notebook_id}: {e}")
            
            # Store user information for this connection
            self.notebook_id = notebook_id
            self.user_id = user_id
            self.user_info = self.get_user_info()
            
            # Send initial state to the client
            await self._send_initial_state()
            
            # Broadcast user presence to other clients
            await self._broadcast_user_joined()
            
            logger.info(f"User {user_id} joined collaboration on notebook {notebook_id}")
            
        except Exception as e:
            logger.exception(f"Error in WebSocket open: {e}")
            self.close(code=1011, reason=f"Internal server error: {str(e)}")
    
    async def _send_initial_state(self) -> None:
        """Send the initial state to the client.
        
        This includes the document state, awareness information, and cell locks.
        """
        if not hasattr(self, 'notebook_id'):
            return
        
        notebook_id = self.notebook_id
        doc = self._documents.get(notebook_id)
        
        if not doc:
            return
        
        try:
            # Send the current document state
            state_update = encode_state_as_update(doc)
            if state_update:
                await self.write_message(state_update, binary=True)
            
            # Send awareness information about other users
            awareness_update = self._create_awareness_update(notebook_id)
            if awareness_update:
                await self.write_message(awareness_update, binary=True)
            
            # Send cell locks information
            locks = self._cell_locks.get(notebook_id, {})
            if locks:
                locks_msg = {
                    "type": "cell-locks",
                    "locks": locks
                }
                await self.write_message(json.dumps(locks_msg))
                
        except Exception as e:
            logger.exception(f"Error sending initial state: {e}")
    
    def _create_awareness_update(self, notebook_id: str) -> Optional[bytes]:
        """Create an awareness update containing all users' information.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Optional[bytes]: The encoded awareness update or None
        """
        if notebook_id not in self._connections:
            return None
        
        # Collect awareness information from all connections
        awareness_states = {}
        for conn in self._connections[notebook_id]:
            if hasattr(conn, 'user_id') and hasattr(conn, 'user_info'):
                awareness_states[conn.user_id] = {
                    "user": conn.user_info
                }
        
        if not awareness_states:
            return None
        
        # Encode the awareness update
        try:
            return encode_awareness_update(awareness_states)
        except Exception as e:
            logger.error(f"Error encoding awareness update: {e}")
            return None
    
    async def _broadcast_user_joined(self) -> None:
        """Broadcast to all clients that a new user has joined."""
        if not hasattr(self, 'notebook_id') or not hasattr(self, 'user_info'):
            return
        
        notebook_id = self.notebook_id
        
        # Create an awareness update with just this user's information
        awareness_states = {
            self.user_id: {
                "user": self.user_info
            }
        }
        
        try:
            awareness_update = encode_awareness_update(awareness_states)
            if awareness_update:
                await self._broadcast(awareness_update, binary=True, exclude_self=False)
        except Exception as e:
            logger.error(f"Error broadcasting user joined: {e}")
    
    async def on_message(self, message: Union[str, bytes]) -> None:
        """Handle incoming WebSocket messages.
        
        This method processes various message types including document updates,
        awareness information, and cell locks.
        
        Args:
            message: The message received from the client
        """
        if self._closing or not hasattr(self, 'notebook_id'):
            return
        
        notebook_id = self.notebook_id
        user_id = self.user_id
        
        try:
            # Handle binary messages (Yjs protocol)
            if isinstance(message, bytes):
                await self._handle_binary_message(message)
            # Handle JSON messages (custom protocol)
            elif isinstance(message, str):
                await self._handle_json_message(message)
            
        except Exception as e:
            logger.exception(f"Error processing message: {e}")
            error_msg = {
                "type": "error",
                "message": str(e)
            }
            await self.write_message(json.dumps(error_msg))
    
    async def _handle_binary_message(self, message: bytes) -> None:
        """Handle binary messages (Yjs protocol).
        
        Args:
            message: The binary message
        """
        if not hasattr(self, 'notebook_id'):
            return
        
        notebook_id = self.notebook_id
        doc = self._documents.get(notebook_id)
        
        if not doc:
            logger.error(f"Document not found for notebook {notebook_id}")
            return
        
        # The first byte of the message indicates the message type
        if not message:
            return
        
        message_type = message[0]
        
        # Handle different message types based on the Yjs protocol
        if message_type == 0:  # State Vector message
            # Client is asking for the state difference
            try:
                # Decode the state vector from the client
                state_vector = decode_state_vector(message)
                
                # Create an update based on the difference between our state and client's state
                update = encode_state_as_update(doc, state_vector)
                
                # Send the update to the client
                if update:
                    await self.write_message(update, binary=True)
            except Exception as e:
                logger.error(f"Error handling state vector message: {e}")
        
        elif message_type == 1:  # Update message
            # Client is sending document updates
            try:
                # Check if the user is authorized to edit this document
                if not self._authorizer.is_authorized_for_collaboration(self, 'edit', notebook_id):
                    logger.warning(f"Unauthorized edit attempt by {self.user_id} for notebook {notebook_id}")
                    error_msg = {
                        "type": "error",
                        "message": "You don't have permission to edit this document"
                    }
                    await self.write_message(json.dumps(error_msg))
                    return
                
                # Decode and apply the update to our document
                update = decode_update(message)
                doc.apply_update(update)
                
                # Broadcast the update to all other clients
                await self._broadcast(message, binary=True, exclude_self=True)
                
                # Persist the document state
                if self._store:
                    asyncio.create_task(self._store.save_document(notebook_id, update))
            except Exception as e:
                logger.error(f"Error handling update message: {e}")
        
        elif message_type == 2:  # Awareness message
            # Client is sending awareness information (cursor position, selection, etc.)
            try:
                # Decode the awareness update
                awareness_update = decode_awareness_update(message)
                
                # Broadcast the awareness update to all clients
                await self._broadcast(message, binary=True, exclude_self=True)
            except Exception as e:
                logger.error(f"Error handling awareness message: {e}")
        
        else:
            logger.warning(f"Unknown binary message type: {message_type}")
    
    async def _handle_json_message(self, message: str) -> None:
        """Handle JSON messages (custom protocol).
        
        Args:
            message: The JSON message as a string
        """
        if not hasattr(self, 'notebook_id'):
            return
        
        notebook_id = self.notebook_id
        user_id = self.user_id
        
        try:
            data = json.loads(message)
            message_type = data.get('type')
            
            if message_type == 'cell-lock-request':
                # Client is requesting to lock a cell
                cell_id = data.get('cellId')
                if not cell_id:
                    return
                
                # Check if the user is authorized to lock cells
                if not self._authorizer.is_authorized_for_collaboration(self, 'lock', notebook_id):
                    logger.warning(f"Unauthorized lock attempt by {user_id} for notebook {notebook_id}")
                    error_msg = {
                        "type": "error",
                        "message": "You don't have permission to lock cells"
                    }
                    await self.write_message(json.dumps(error_msg))
                    return
                
                # Check if the cell is already locked
                locks = self._cell_locks.get(notebook_id, {})
                if cell_id in locks and locks[cell_id] != user_id:
                    # Cell is locked by another user
                    lock_error = {
                        "type": "cell-lock-error",
                        "cellId": cell_id,
                        "message": f"Cell is locked by {locks[cell_id]}"
                    }
                    await self.write_message(json.dumps(lock_error))
                    return
                
                # Lock the cell
                if notebook_id not in self._cell_locks:
                    self._cell_locks[notebook_id] = {}
                self._cell_locks[notebook_id][cell_id] = user_id
                
                # Broadcast the lock to all clients
                lock_msg = {
                    "type": "cell-lock",
                    "cellId": cell_id,
                    "userId": user_id
                }
                await self._broadcast(json.dumps(lock_msg), exclude_self=False)
                
                # Persist the cell locks
                if self._store:
                    asyncio.create_task(self._store.save_cell_locks(notebook_id, self._cell_locks[notebook_id]))
            
            elif message_type == 'cell-unlock-request':
                # Client is requesting to unlock a cell
                cell_id = data.get('cellId')
                if not cell_id:
                    return
                
                # Check if the cell is locked by this user
                locks = self._cell_locks.get(notebook_id, {})
                if cell_id in locks:
                    if locks[cell_id] == user_id or self._authorizer.is_authorized_for_collaboration(self, 'force-unlock', notebook_id):
                        # User owns the lock or has admin privileges to force unlock
                        del locks[cell_id]
                        
                        # Broadcast the unlock to all clients
                        unlock_msg = {
                            "type": "cell-unlock",
                            "cellId": cell_id
                        }
                        await self._broadcast(json.dumps(unlock_msg), exclude_self=False)
                        
                        # Persist the cell locks
                        if self._store:
                            asyncio.create_task(self._store.save_cell_locks(notebook_id, locks))
                    else:
                        # User doesn't own the lock
                        unlock_error = {
                            "type": "cell-unlock-error",
                            "cellId": cell_id,
                            "message": f"Cell is locked by {locks[cell_id]}"
                        }
                        await self.write_message(json.dumps(unlock_error))
            
            elif message_type == 'comment-add':
                # Client is adding a comment
                if not self._authorizer.is_authorized_for_collaboration(self, 'comment', notebook_id):
                    logger.warning(f"Unauthorized comment attempt by {user_id} for notebook {notebook_id}")
                    error_msg = {
                        "type": "error",
                        "message": "You don't have permission to add comments"
                    }
                    await self.write_message(json.dumps(error_msg))
                    return
                
                # Add user information to the comment
                data['userId'] = user_id
                data['userName'] = self.user_info.get('name', user_id)
                data['timestamp'] = data.get('timestamp', asyncio.get_event_loop().time())
                
                # Broadcast the comment to all clients
                await self._broadcast(json.dumps(data), exclude_self=False)
                
                # Persist the comment
                if self._store:
                    asyncio.create_task(self._store.save_comment(notebook_id, data))
            
            elif message_type == 'comment-edit' or message_type == 'comment-delete' or message_type == 'comment-resolve':
                # Client is editing, deleting, or resolving a comment
                comment_id = data.get('commentId')
                if not comment_id:
                    return
                
                # Check if the user is authorized to modify this comment
                comment_user_id = data.get('userId')
                if comment_user_id != user_id and not self._authorizer.is_authorized_for_collaboration(self, 'admin', notebook_id):
                    logger.warning(f"Unauthorized comment modification by {user_id} for notebook {notebook_id}")
                    error_msg = {
                        "type": "error",
                        "message": "You don't have permission to modify this comment"
                    }
                    await self.write_message(json.dumps(error_msg))
                    return
                
                # Broadcast the comment modification to all clients
                await self._broadcast(json.dumps(data), exclude_self=False)
                
                # Persist the comment modification
                if self._store:
                    asyncio.create_task(self._store.update_comment(notebook_id, comment_id, data))
            
            elif message_type == 'ping':
                # Client is sending a ping to keep the connection alive
                pong_msg = {
                    "type": "pong",
                    "timestamp": data.get('timestamp', asyncio.get_event_loop().time())
                }
                await self.write_message(json.dumps(pong_msg))
            
            else:
                logger.warning(f"Unknown JSON message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON message: {message}")
        except Exception as e:
            logger.exception(f"Error handling JSON message: {e}")
    
    async def _broadcast(self, message: Union[str, bytes], binary: bool = False, exclude_self: bool = False) -> None:
        """Broadcast a message to all connected clients for this notebook.
        
        Args:
            message: The message to broadcast
            binary: Whether the message is binary
            exclude_self: Whether to exclude the current connection from the broadcast
        """
        if not hasattr(self, 'notebook_id'):
            return
        
        notebook_id = self.notebook_id
        
        if notebook_id not in self._connections:
            return
        
        for conn in self._connections[notebook_id]:
            if exclude_self and conn is self:
                continue
            
            try:
                await conn.write_message(message, binary=binary)
            except WebSocketClosedError:
                # Connection is closed, will be cleaned up on close handler
                pass
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}")
    
    def on_close(self) -> None:
        """Handle WebSocket connection close.
        
        This method is called when the WebSocket connection is closed.
        It cleans up resources and notifies other clients.
        """
        self._closing = True
        
        if not hasattr(self, 'notebook_id'):
            return
        
        notebook_id = self.notebook_id
        user_id = getattr(self, 'user_id', None)
        
        try:
            # Remove this connection from the set of connections for this notebook
            if notebook_id in self._connections:
                self._connections[notebook_id].discard(self)
                
                # If this was the last connection, clean up resources
                if not self._connections[notebook_id]:
                    # Persist the final document state before removing
                    if notebook_id in self._documents and self._store:
                        doc = self._documents[notebook_id]
                        update = encode_state_as_update(doc)
                        if update:
                            asyncio.create_task(self._store.save_document(notebook_id, update))
                    
                    # Clean up resources
                    self._connections.pop(notebook_id, None)
                    self._documents.pop(notebook_id, None)
                    self._cell_locks.pop(notebook_id, None)
                else:
                    # Notify other clients that this user has left
                    if user_id:
                        # Create an empty awareness state for this user to indicate they've left
                        awareness_states = {user_id: None}
                        try:
                            awareness_update = encode_awareness_update(awareness_states)
                            if awareness_update:
                                asyncio.create_task(self._broadcast(awareness_update, binary=True, exclude_self=True))
                        except Exception as e:
                            logger.error(f"Error creating awareness update for user departure: {e}")
                        
                        # Release any cell locks held by this user
                        if notebook_id in self._cell_locks:
                            locks = self._cell_locks[notebook_id]
                            cells_to_unlock = [cell_id for cell_id, lock_user_id in locks.items() if lock_user_id == user_id]
                            
                            for cell_id in cells_to_unlock:
                                locks.pop(cell_id, None)
                                
                                # Notify other clients about the unlocked cells
                                unlock_msg = {
                                    "type": "cell-unlock",
                                    "cellId": cell_id,
                                    "reason": "user-disconnected"
                                }
                                asyncio.create_task(self._broadcast(json.dumps(unlock_msg), exclude_self=True))
                            
                            # Persist the updated cell locks
                            if self._store and cells_to_unlock:
                                asyncio.create_task(self._store.save_cell_locks(notebook_id, locks))
            
            if user_id and notebook_id:
                logger.info(f"User {user_id} left collaboration on notebook {notebook_id}")
                
        except Exception as e:
            logger.exception(f"Error in WebSocket close: {e}")


def setup_handlers(web_app, base_url):
    """Set up the WebSocket handlers for the Jupyter server.
    
    Args:
        web_app: The Jupyter web application
        base_url: The base URL for the Jupyter server
    """
    host_pattern = ".*$"
    
    # Check if required dependencies are available
    if not HAS_PYCRDT or not HAS_PYCRDT_WEBSOCKET:
        logger.warning(
            "Collaboration features are disabled because required dependencies "
            "are not available. Please install pycrdt and pycrdt-websocket."
        )
        return
    
    # Set up the collaboration WebSocket handler
    route_pattern = url_path_join(base_url, r"/api/collaboration/(.*)")
    handlers = [(route_pattern, CollaborationWebSocketHandler)]
    
    web_app.add_handlers(host_pattern, handlers)
    
    logger.info("Collaboration WebSocket handlers initialized")


# Helper function to join URL paths
def url_path_join(*parts):
    """Join URL path components and normalize the result.
    
    Args:
        *parts: URL path components
        
    Returns:
        str: The joined URL path
    """
    initial = list(parts[0])
    for part in parts[1:]:
        if part.startswith('/'):
            part = part[1:]
        if initial[-1] == '/':
            initial.extend(part)
        else:
            initial.append('/')
            initial.extend(part)
    return ''.join(initial)
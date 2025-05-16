"""WebSocket handlers for Yjs CRDT protocol in Jupyter Notebook.

This module implements WebSocket handlers for the Yjs CRDT protocol, enabling real-time
synchronization of notebook content between multiple clients. It processes binary Yjs
update messages, broadcasts changes to connected clients, handles user presence information,
and enforces access permissions.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union, cast

import tornado.web
import tornado.websocket
from jupyter_server.auth import authorized
from jupyter_server.base.handlers import JupyterHandler
from tornado.ioloop import IOLoop

try:
    import y_py as Y
except ImportError:
    Y = None  # type: ignore

from .persistence import CollaborationManager

# Set up logging
logger = logging.getLogger('notebook.collab.handlers')


class YjsMessageType:
    """Enum for Yjs message types."""
    SYNC = 0
    AWARENESS = 1
    AUTH = 2
    QUERY_AWARENESS = 3
    SYNC_REPLY = 4
    LOCK = 5
    UNLOCK = 6


class CollaborationSocketHandler(tornado.websocket.WebSocketHandler, JupyterHandler):
    """WebSocket handler for Yjs CRDT protocol.
    
    This handler processes binary Yjs update messages, broadcasts changes to connected
    clients, handles user presence information, and enforces access permissions.
    """
    
    # Class-level variables to track connections and rooms
    rooms: Dict[str, Set['CollaborationSocketHandler']] = {}
    # Maps document_id to a set of connected handlers
    
    # Maps handler to (document_id, client_id) tuple
    handler_info: Dict['CollaborationSocketHandler', Tuple[str, int]] = {}
    
    # Collaboration manager for persistence
    collab_manager: Optional[CollaborationManager] = None
    
    @classmethod
    def initialize_manager(cls, collab_manager: CollaborationManager) -> None:
        """Initialize the collaboration manager for persistence."""
        cls.collab_manager = collab_manager
    
    def initialize(self, **kwargs: Any) -> None:
        """Initialize the handler with configuration."""
        super().initialize(**kwargs)
        self.document_id = None
        self.client_id = None
        self.user_id = None
        self.last_activity = time.time()
        self.permissions = None
        self.authenticated = False
    
    def check_origin(self, origin: str) -> bool:
        """Check if the origin is allowed.
        
        This method can be overridden to implement custom origin validation.
        By default, it allows all origins for WebSocket connections.
        """
        # Allow all origins by default, can be overridden for stricter security
        return True
    
    @authorized
    async def open(self, document_id: str) -> None:
        """Handle WebSocket connection open.
        
        Args:
            document_id: The ID of the document to collaborate on
        """
        if Y is None:
            self.close(1011, "y_py package is not installed")
            return
        
        if not self.collab_manager:
            self.close(1011, "Collaboration manager not initialized")
            return
        
        self.document_id = document_id
        self.client_id = self.get_client_id()
        self.user_id = self.current_user.get('name', 'anonymous') if self.current_user else 'anonymous'
        
        # Check if user has permission to access this document
        has_permission = await self.check_document_permission(document_id)
        if not has_permission:
            self.close(1008, "Permission denied")
            return
        
        # Add this handler to the room for the document
        if document_id not in self.rooms:
            self.rooms[document_id] = set()
        self.rooms[document_id].add(self)
        self.handler_info[self] = (document_id, self.client_id)
        
        # Load initial document state
        try:
            initial_state = await self.collab_manager.get_document_state(document_id)
            if initial_state:
                # Send initial state to client
                await self.send_sync_reply(initial_state)
            
            # Notify other clients about new user
            await self.broadcast_user_joined()
            
            logger.info(f"Client {self.client_id} ({self.user_id}) connected to document {document_id}")
        except Exception as e:
            logger.exception(f"Error during WebSocket open: {e}")
            self.close(1011, f"Error loading document: {str(e)}")
    
    def on_close(self) -> None:
        """Handle WebSocket connection close."""
        if self in self.handler_info:
            document_id, client_id = self.handler_info[self]
            
            # Remove this handler from the room
            if document_id in self.rooms and self in self.rooms[document_id]:
                self.rooms[document_id].remove(self)
                if not self.rooms[document_id]:
                    # If room is empty, clean up
                    del self.rooms[document_id]
            
            # Clean up handler info
            del self.handler_info[self]
            
            # Broadcast user left message asynchronously
            IOLoop.current().add_callback(self.broadcast_user_left, document_id, client_id)
            
            logger.info(f"Client {client_id} ({self.user_id}) disconnected from document {document_id}")
    
    async def on_message(self, message: Union[str, bytes]) -> None:
        """Handle incoming WebSocket messages.
        
        Args:
            message: Binary message from client containing Yjs updates or awareness info
        """
        if not isinstance(message, bytes):
            logger.warning(f"Received non-binary message: {message[:100]}")
            return
        
        if not self.document_id or not self.client_id:
            logger.warning("Received message but handler not properly initialized")
            return
        
        try:
            # Update last activity timestamp
            self.last_activity = time.time()
            
            # First byte indicates message type
            message_type = message[0] if message else None
            
            if message_type == YjsMessageType.SYNC:
                # Handle Yjs document sync message
                await self.handle_sync_message(message[1:])
            
            elif message_type == YjsMessageType.AWARENESS:
                # Handle awareness update (cursor positions, selections, etc.)
                await self.handle_awareness_message(message[1:])
            
            elif message_type == YjsMessageType.AUTH:
                # Handle authentication message
                await self.handle_auth_message(message[1:])
            
            elif message_type == YjsMessageType.QUERY_AWARENESS:
                # Handle request for current awareness states
                await self.handle_query_awareness()
            
            elif message_type == YjsMessageType.LOCK:
                # Handle cell lock request
                await self.handle_lock_message(message[1:])
            
            elif message_type == YjsMessageType.UNLOCK:
                # Handle cell unlock request
                await self.handle_unlock_message(message[1:])
            
            else:
                logger.warning(f"Unknown message type: {message_type}")
        
        except Exception as e:
            logger.exception(f"Error processing message: {e}")
    
    async def handle_sync_message(self, message: bytes) -> None:
        """Handle Yjs document synchronization message.
        
        Args:
            message: Binary Yjs update message
        """
        if not self.collab_manager:
            return
        
        # Validate permissions for document updates
        if not await self.check_edit_permission(self.document_id):
            logger.warning(f"User {self.user_id} attempted to edit document {self.document_id} without permission")
            # Send permission denied message
            await self.send_error("Permission denied for document updates")
            return
        
        try:
            # Process and store the update
            update_successful = await self.collab_manager.apply_update(self.document_id, message, self.client_id)
            
            if update_successful:
                # Broadcast update to all other clients in the room
                await self.broadcast_update(message, exclude_self=True)
                
                # Create a version snapshot periodically or based on update size
                await self.maybe_create_snapshot()
            else:
                logger.warning(f"Failed to apply update to document {self.document_id}")
        
        except Exception as e:
            logger.exception(f"Error handling sync message: {e}")
            await self.send_error(f"Error processing document update: {str(e)}")
    
    async def handle_awareness_message(self, message: bytes) -> None:
        """Handle awareness update message (cursor positions, selections, etc.).
        
        Args:
            message: Binary awareness update message
        """
        if not self.collab_manager:
            return
        
        try:
            # Store awareness state
            await self.collab_manager.update_awareness(self.document_id, self.client_id, message)
            
            # Broadcast awareness update to all other clients in the room
            await self.broadcast_awareness(message, exclude_self=True)
        
        except Exception as e:
            logger.exception(f"Error handling awareness message: {e}")
    
    async def handle_auth_message(self, message: bytes) -> None:
        """Handle authentication message.
        
        Args:
            message: Authentication message containing token or credentials
        """
        try:
            # Parse authentication data
            auth_data = json.loads(message.decode('utf-8'))
            
            # Validate authentication (implementation depends on auth system)
            auth_successful = await self.validate_auth(auth_data)
            
            if auth_successful:
                self.authenticated = True
                # Send success response
                await self.send_auth_response(True, "Authentication successful")
            else:
                # Send failure response
                await self.send_auth_response(False, "Authentication failed")
        
        except Exception as e:
            logger.exception(f"Error handling auth message: {e}")
            await self.send_auth_response(False, f"Authentication error: {str(e)}")
    
    async def handle_query_awareness(self) -> None:
        """Handle request for current awareness states."""
        if not self.collab_manager or not self.document_id:
            return
        
        try:
            # Get all current awareness states for this document
            awareness_states = await self.collab_manager.get_awareness_states(self.document_id)
            
            # Send each awareness state to the client
            for client_id, state in awareness_states.items():
                if client_id != self.client_id:  # Don't send client's own state back
                    await self.send_awareness(state)
        
        except Exception as e:
            logger.exception(f"Error handling query awareness: {e}")
    
    async def handle_lock_message(self, message: bytes) -> None:
        """Handle cell lock request.
        
        Args:
            message: Lock request containing cell ID
        """
        if not self.collab_manager or not self.document_id:
            return
        
        try:
            # Parse lock request
            lock_data = json.loads(message.decode('utf-8'))
            cell_id = lock_data.get('cell_id')
            
            if not cell_id:
                logger.warning("Lock request missing cell_id")
                return
            
            # Check if user has permission to lock this cell
            if not await self.check_cell_permission(self.document_id, cell_id, 'lock'):
                await self.send_error("Permission denied for cell lock")
                return
            
            # Try to acquire lock
            lock_acquired = await self.collab_manager.acquire_cell_lock(
                self.document_id, cell_id, self.client_id, self.user_id
            )
            
            if lock_acquired:
                # Broadcast lock acquisition to all clients in the room
                lock_message = {
                    'type': 'lock',
                    'cell_id': cell_id,
                    'client_id': self.client_id,
                    'user_id': self.user_id
                }
                await self.broadcast_json(lock_message)
            else:
                # Send lock denied message to requesting client
                current_lock = await self.collab_manager.get_cell_lock(self.document_id, cell_id)
                await self.send_error(f"Cell is locked by {current_lock.get('user_id')}")
        
        except Exception as e:
            logger.exception(f"Error handling lock message: {e}")
            await self.send_error(f"Error processing lock request: {str(e)}")
    
    async def handle_unlock_message(self, message: bytes) -> None:
        """Handle cell unlock request.
        
        Args:
            message: Unlock request containing cell ID
        """
        if not self.collab_manager or not self.document_id:
            return
        
        try:
            # Parse unlock request
            unlock_data = json.loads(message.decode('utf-8'))
            cell_id = unlock_data.get('cell_id')
            
            if not cell_id:
                logger.warning("Unlock request missing cell_id")
                return
            
            # Check if this client holds the lock
            current_lock = await self.collab_manager.get_cell_lock(self.document_id, cell_id)
            if not current_lock or current_lock.get('client_id') != self.client_id:
                await self.send_error("You don't hold the lock for this cell")
                return
            
            # Release the lock
            await self.collab_manager.release_cell_lock(self.document_id, cell_id, self.client_id)
            
            # Broadcast unlock notification to all clients in the room
            unlock_message = {
                'type': 'unlock',
                'cell_id': cell_id,
                'client_id': self.client_id,
                'user_id': self.user_id
            }
            await self.broadcast_json(unlock_message)
        
        except Exception as e:
            logger.exception(f"Error handling unlock message: {e}")
            await self.send_error(f"Error processing unlock request: {str(e)}")
    
    async def broadcast_update(self, update: bytes, exclude_self: bool = False) -> None:
        """Broadcast Yjs update to all clients in the room.
        
        Args:
            update: Binary Yjs update message
            exclude_self: Whether to exclude sending to the originating client
        """
        if not self.document_id:
            return
        
        # Prepare sync message with type byte
        sync_message = bytes([YjsMessageType.SYNC]) + update
        
        # Get all handlers in this room
        handlers = self.rooms.get(self.document_id, set())
        
        # Broadcast to all handlers except self if exclude_self is True
        for handler in handlers:
            if exclude_self and handler == self:
                continue
            try:
                handler.write_message(sync_message, binary=True)
            except Exception as e:
                logger.exception(f"Error broadcasting update: {e}")
    
    async def broadcast_awareness(self, awareness: bytes, exclude_self: bool = False) -> None:
        """Broadcast awareness update to all clients in the room.
        
        Args:
            awareness: Binary awareness update message
            exclude_self: Whether to exclude sending to the originating client
        """
        if not self.document_id:
            return
        
        # Prepare awareness message with type byte
        awareness_message = bytes([YjsMessageType.AWARENESS]) + awareness
        
        # Get all handlers in this room
        handlers = self.rooms.get(self.document_id, set())
        
        # Broadcast to all handlers except self if exclude_self is True
        for handler in handlers:
            if exclude_self and handler == self:
                continue
            try:
                handler.write_message(awareness_message, binary=True)
            except Exception as e:
                logger.exception(f"Error broadcasting awareness: {e}")
    
    async def broadcast_json(self, data: Dict[str, Any]) -> None:
        """Broadcast JSON message to all clients in the room.
        
        Args:
            data: JSON-serializable data to broadcast
        """
        if not self.document_id:
            return
        
        # Get all handlers in this room
        handlers = self.rooms.get(self.document_id, set())
        
        # Serialize message once
        message = json.dumps(data)
        
        # Broadcast to all handlers
        for handler in handlers:
            try:
                handler.write_message(message)
            except Exception as e:
                logger.exception(f"Error broadcasting JSON: {e}")
    
    async def broadcast_user_joined(self) -> None:
        """Broadcast notification that a user has joined the document."""
        if not self.document_id or not self.client_id or not self.user_id:
            return
        
        join_message = {
            'type': 'user_joined',
            'client_id': self.client_id,
            'user_id': self.user_id,
            'timestamp': time.time()
        }
        
        await self.broadcast_json(join_message)
    
    async def broadcast_user_left(self, document_id: str, client_id: int) -> None:
        """Broadcast notification that a user has left the document.
        
        Args:
            document_id: Document ID the user left
            client_id: Client ID of the user who left
        """
        if not document_id or not client_id:
            return
        
        leave_message = {
            'type': 'user_left',
            'client_id': client_id,
            'user_id': self.user_id,
            'timestamp': time.time()
        }
        
        # Get all handlers in this room
        handlers = self.rooms.get(document_id, set())
        
        # Serialize message once
        message = json.dumps(leave_message)
        
        # Broadcast to all handlers
        for handler in handlers:
            try:
                handler.write_message(message)
            except Exception as e:
                logger.exception(f"Error broadcasting user left: {e}")
        
        # Also clean up any locks held by this client
        if self.collab_manager:
            await self.collab_manager.release_all_client_locks(document_id, client_id)
    
    async def send_sync_reply(self, state: bytes) -> None:
        """Send initial document state to client.
        
        Args:
            state: Binary Yjs document state
        """
        try:
            # Prepare sync reply message with type byte
            sync_reply = bytes([YjsMessageType.SYNC_REPLY]) + state
            self.write_message(sync_reply, binary=True)
        except Exception as e:
            logger.exception(f"Error sending sync reply: {e}")
    
    async def send_awareness(self, awareness: bytes) -> None:
        """Send awareness state to client.
        
        Args:
            awareness: Binary awareness state
        """
        try:
            # Prepare awareness message with type byte
            awareness_message = bytes([YjsMessageType.AWARENESS]) + awareness
            self.write_message(awareness_message, binary=True)
        except Exception as e:
            logger.exception(f"Error sending awareness: {e}")
    
    async def send_auth_response(self, success: bool, message: str) -> None:
        """Send authentication response to client.
        
        Args:
            success: Whether authentication was successful
            message: Message to send to client
        """
        try:
            response = {
                'type': 'auth_response',
                'success': success,
                'message': message
            }
            self.write_message(json.dumps(response))
        except Exception as e:
            logger.exception(f"Error sending auth response: {e}")
    
    async def send_error(self, message: str) -> None:
        """Send error message to client.
        
        Args:
            message: Error message to send
        """
        try:
            error_message = {
                'type': 'error',
                'message': message
            }
            self.write_message(json.dumps(error_message))
        except Exception as e:
            logger.exception(f"Error sending error message: {e}")
    
    async def maybe_create_snapshot(self) -> None:
        """Create a document snapshot if needed.
        
        This method decides whether to create a snapshot based on time or update count.
        """
        if not self.collab_manager or not self.document_id:
            return
        
        try:
            # Check if it's time to create a snapshot
            should_snapshot = await self.collab_manager.should_create_snapshot(self.document_id)
            
            if should_snapshot:
                await self.collab_manager.create_snapshot(self.document_id)
        except Exception as e:
            logger.exception(f"Error creating snapshot: {e}")
    
    def get_client_id(self) -> int:
        """Generate a unique client ID.
        
        Returns:
            A unique integer client ID
        """
        # Simple implementation using timestamp and random component
        # In production, you might want a more sophisticated approach
        import random
        return int(time.time() * 1000) + random.randint(0, 1000)
    
    async def check_document_permission(self, document_id: str) -> bool:
        """Check if the current user has permission to access the document.
        
        Args:
            document_id: Document ID to check
            
        Returns:
            True if user has permission, False otherwise
        """
        if not self.collab_manager:
            return False
        
        try:
            # Get user permissions for this document
            self.permissions = await self.collab_manager.get_user_permissions(
                document_id, self.user_id
            )
            
            # At minimum, user needs 'view' permission
            return bool(self.permissions and self.permissions.get('view', False))
        
        except Exception as e:
            logger.exception(f"Error checking document permission: {e}")
            return False
    
    async def check_edit_permission(self, document_id: str) -> bool:
        """Check if the current user has permission to edit the document.
        
        Args:
            document_id: Document ID to check
            
        Returns:
            True if user has edit permission, False otherwise
        """
        if not self.permissions:
            # Reload permissions if not available
            await self.check_document_permission(document_id)
        
        # User needs 'edit' permission to modify document
        return bool(self.permissions and self.permissions.get('edit', False))
    
    async def check_cell_permission(self, document_id: str, cell_id: str, action: str) -> bool:
        """Check if the current user has permission for a specific action on a cell.
        
        Args:
            document_id: Document ID to check
            cell_id: Cell ID to check
            action: Action to check (e.g., 'edit', 'execute', 'lock')
            
        Returns:
            True if user has permission, False otherwise
        """
        if not self.collab_manager:
            return False
        
        try:
            # First check document-level permissions
            if not await self.check_edit_permission(document_id):
                return False
            
            # Then check cell-specific permissions if they exist
            cell_permissions = await self.collab_manager.get_cell_permissions(
                document_id, cell_id, self.user_id
            )
            
            # If no cell-specific permissions, fall back to document permissions
            if not cell_permissions:
                return True  # Already checked document-level edit permission
            
            # Check the specific action permission for this cell
            return bool(cell_permissions.get(action, False))
        
        except Exception as e:
            logger.exception(f"Error checking cell permission: {e}")
            return False
    
    async def validate_auth(self, auth_data: Dict[str, Any]) -> bool:
        """Validate authentication data.
        
        Args:
            auth_data: Authentication data from client
            
        Returns:
            True if authentication is valid, False otherwise
        """
        # This is a placeholder implementation
        # In a real implementation, you would validate tokens, API keys, etc.
        token = auth_data.get('token')
        
        if not token:
            return False
        
        # In a real implementation, validate the token against your auth system
        # For now, we'll just return True for any non-empty token
        return bool(token)


class CollaborationAPIHandler(JupyterHandler):
    """HTTP API handler for collaboration metadata.
    
    This handler provides REST API endpoints for managing collaboration sessions,
    permissions, comments, and version history.
    """
    
    collab_manager: Optional[CollaborationManager] = None
    
    @classmethod
    def initialize_manager(cls, collab_manager: CollaborationManager) -> None:
        """Initialize the collaboration manager for persistence."""
        cls.collab_manager = collab_manager
    
    @authorized
    async def get(self, endpoint: str, document_id: str, resource_id: Optional[str] = None) -> None:
        """Handle GET requests for collaboration resources.
        
        Args:
            endpoint: API endpoint (permissions, comments, history, etc.)
            document_id: Document ID
            resource_id: Optional resource ID within the document
        """
        if not self.collab_manager:
            self.send_error(500, message="Collaboration manager not initialized")
            return
        
        user_id = self.current_user.get('name', 'anonymous') if self.current_user else 'anonymous'
        
        try:
            # Check if user has permission to access this document
            permissions = await self.collab_manager.get_user_permissions(document_id, user_id)
            if not permissions or not permissions.get('view', False):
                self.send_error(403, message="Permission denied")
                return
            
            if endpoint == 'permissions':
                if resource_id:
                    # Get specific permission
                    permission = await self.collab_manager.get_permission(document_id, resource_id)
                    self.write(json.dumps(permission))
                else:
                    # List all permissions for document
                    all_permissions = await self.collab_manager.list_permissions(document_id)
                    self.write(json.dumps(all_permissions))
            
            elif endpoint == 'comments':
                if resource_id:
                    # Get specific comment thread
                    comment = await self.collab_manager.get_comment_thread(document_id, resource_id)
                    self.write(json.dumps(comment))
                else:
                    # List all comments for document
                    status = self.get_argument('status', 'open')
                    comments = await self.collab_manager.list_comments(document_id, status)
                    self.write(json.dumps(comments))
            
            elif endpoint == 'history':
                if resource_id:
                    # Get specific version
                    version = await self.collab_manager.get_version(document_id, resource_id)
                    self.write(json.dumps(version))
                else:
                    # List version history
                    limit = int(self.get_argument('limit', '10'))
                    history = await self.collab_manager.get_history(document_id, limit)
                    self.write(json.dumps(history))
            
            elif endpoint == 'presence':
                # Get current users in the document
                presence = await self.collab_manager.get_document_presence(document_id)
                self.write(json.dumps(presence))
            
            elif endpoint == 'locks':
                if resource_id:
                    # Get specific cell lock
                    lock = await self.collab_manager.get_cell_lock(document_id, resource_id)
                    self.write(json.dumps(lock if lock else {}))
                else:
                    # List all locks for document
                    locks = await self.collab_manager.list_cell_locks(document_id)
                    self.write(json.dumps(locks))
            
            else:
                self.send_error(404, message=f"Unknown endpoint: {endpoint}")
        
        except Exception as e:
            logger.exception(f"Error handling GET request: {e}")
            self.send_error(500, message=str(e))
    
    @authorized
    async def post(self, endpoint: str, document_id: str, resource_id: Optional[str] = None) -> None:
        """Handle POST requests for collaboration resources.
        
        Args:
            endpoint: API endpoint (permissions, comments, history, etc.)
            document_id: Document ID
            resource_id: Optional resource ID within the document
        """
        if not self.collab_manager:
            self.send_error(500, message="Collaboration manager not initialized")
            return
        
        user_id = self.current_user.get('name', 'anonymous') if self.current_user else 'anonymous'
        
        try:
            # Parse request body
            data = json.loads(self.request.body.decode('utf-8'))
            
            if endpoint == 'permissions':
                # Check if user has admin permission to manage permissions
                permissions = await self.collab_manager.get_user_permissions(document_id, user_id)
                if not permissions or not permissions.get('admin', False):
                    self.send_error(403, message="Admin permission required")
                    return
                
                # Create new permission
                permission_id = await self.collab_manager.create_permission(document_id, data)
                self.set_status(201)
                self.write(json.dumps({'id': permission_id}))
            
            elif endpoint == 'comments':
                # Check if user has comment permission
                permissions = await self.collab_manager.get_user_permissions(document_id, user_id)
                if not permissions or not permissions.get('comment', False):
                    self.send_error(403, message="Comment permission required")
                    return
                
                if resource_id:
                    # Add reply to existing thread
                    data['user_id'] = user_id
                    comment_id = await self.collab_manager.add_comment(document_id, resource_id, data)
                    self.set_status(201)
                    self.write(json.dumps({'id': comment_id}))
                else:
                    # Create new comment thread
                    data['user_id'] = user_id
                    thread_id = await self.collab_manager.create_comment_thread(document_id, data)
                    self.set_status(201)
                    self.write(json.dumps({'id': thread_id}))
            
            elif endpoint == 'sessions':
                # Create or join collaboration session
                session_id = await self.collab_manager.create_session(document_id, user_id, data)
                self.set_status(201)
                self.write(json.dumps({'id': session_id}))
            
            else:
                self.send_error(404, message=f"Unknown endpoint: {endpoint}")
        
        except json.JSONDecodeError:
            self.send_error(400, message="Invalid JSON in request body")
        except Exception as e:
            logger.exception(f"Error handling POST request: {e}")
            self.send_error(500, message=str(e))
    
    @authorized
    async def put(self, endpoint: str, document_id: str, resource_id: str) -> None:
        """Handle PUT requests for collaboration resources.
        
        Args:
            endpoint: API endpoint (permissions, comments, history, etc.)
            document_id: Document ID
            resource_id: Resource ID to update
        """
        if not self.collab_manager:
            self.send_error(500, message="Collaboration manager not initialized")
            return
        
        user_id = self.current_user.get('name', 'anonymous') if self.current_user else 'anonymous'
        
        try:
            # Parse request body
            data = json.loads(self.request.body.decode('utf-8'))
            
            if endpoint == 'permissions':
                # Check if user has admin permission
                permissions = await self.collab_manager.get_user_permissions(document_id, user_id)
                if not permissions or not permissions.get('admin', False):
                    self.send_error(403, message="Admin permission required")
                    return
                
                # Update permission
                success = await self.collab_manager.update_permission(document_id, resource_id, data)
                if success:
                    self.write(json.dumps({'success': True}))
                else:
                    self.send_error(404, message="Permission not found")
            
            elif endpoint == 'comments':
                # Update comment thread status (e.g., resolve/reopen)
                # First check if user is thread owner or has admin permission
                thread = await self.collab_manager.get_comment_thread(document_id, resource_id)
                permissions = await self.collab_manager.get_user_permissions(document_id, user_id)
                
                if not thread:
                    self.send_error(404, message="Comment thread not found")
                    return
                
                if thread.get('user_id') != user_id and not (permissions and permissions.get('admin', False)):
                    self.send_error(403, message="Permission denied to update comment thread")
                    return
                
                # Update thread
                success = await self.collab_manager.update_comment_thread(document_id, resource_id, data)
                if success:
                    self.write(json.dumps({'success': True}))
                else:
                    self.send_error(500, message="Failed to update comment thread")
            
            else:
                self.send_error(404, message=f"Unknown endpoint: {endpoint}")
        
        except json.JSONDecodeError:
            self.send_error(400, message="Invalid JSON in request body")
        except Exception as e:
            logger.exception(f"Error handling PUT request: {e}")
            self.send_error(500, message=str(e))
    
    @authorized
    async def delete(self, endpoint: str, document_id: str, resource_id: str) -> None:
        """Handle DELETE requests for collaboration resources.
        
        Args:
            endpoint: API endpoint (permissions, comments, history, etc.)
            document_id: Document ID
            resource_id: Resource ID to delete
        """
        if not self.collab_manager:
            self.send_error(500, message="Collaboration manager not initialized")
            return
        
        user_id = self.current_user.get('name', 'anonymous') if self.current_user else 'anonymous'
        
        try:
            if endpoint == 'permissions':
                # Check if user has admin permission
                permissions = await self.collab_manager.get_user_permissions(document_id, user_id)
                if not permissions or not permissions.get('admin', False):
                    self.send_error(403, message="Admin permission required")
                    return
                
                # Delete permission
                success = await self.collab_manager.delete_permission(document_id, resource_id)
                if success:
                    self.set_status(204)  # No content
                else:
                    self.send_error(404, message="Permission not found")
            
            elif endpoint == 'comments':
                # Delete comment thread
                # First check if user is thread owner or has admin permission
                thread = await self.collab_manager.get_comment_thread(document_id, resource_id)
                permissions = await self.collab_manager.get_user_permissions(document_id, user_id)
                
                if not thread:
                    self.send_error(404, message="Comment thread not found")
                    return
                
                if thread.get('user_id') != user_id and not (permissions and permissions.get('admin', False)):
                    self.send_error(403, message="Permission denied to delete comment thread")
                    return
                
                # Delete thread
                success = await self.collab_manager.delete_comment_thread(document_id, resource_id)
                if success:
                    self.set_status(204)  # No content
                else:
                    self.send_error(500, message="Failed to delete comment thread")
            
            elif endpoint == 'sessions':
                # Leave collaboration session
                success = await self.collab_manager.leave_session(document_id, resource_id, user_id)
                if success:
                    self.set_status(204)  # No content
                else:
                    self.send_error(404, message="Session not found")
            
            else:
                self.send_error(404, message=f"Unknown endpoint: {endpoint}")
        
        except Exception as e:
            logger.exception(f"Error handling DELETE request: {e}")
            self.send_error(500, message=str(e))


def setup_handlers(web_app, collab_manager: CollaborationManager) -> None:
    """Set up the WebSocket and HTTP handlers for collaboration.
    
    Args:
        web_app: Jupyter web application instance
        collab_manager: Collaboration manager instance for persistence
    """
    host_pattern = ".*$"
    
    # Initialize handlers with collaboration manager
    CollaborationSocketHandler.initialize_manager(collab_manager)
    CollaborationAPIHandler.initialize_manager(collab_manager)
    
    # Register WebSocket handler for Yjs CRDT protocol
    web_app.add_handlers(host_pattern, [
        (r"/collaboration/(?P<document_id>\w+)", CollaborationSocketHandler),
    ])
    
    # Register HTTP API handlers for collaboration metadata
    web_app.add_handlers(host_pattern, [
        # Permissions API
        (r"/api/collaboration/v1/(?P<endpoint>permissions)/(?P<document_id>\w+)/?$", 
         CollaborationAPIHandler),
        (r"/api/collaboration/v1/(?P<endpoint>permissions)/(?P<document_id>\w+)/(?P<resource_id>\w+)/?$", 
         CollaborationAPIHandler),
        
        # Comments API
        (r"/api/collaboration/v1/(?P<endpoint>comments)/(?P<document_id>\w+)/?$", 
         CollaborationAPIHandler),
        (r"/api/collaboration/v1/(?P<endpoint>comments)/(?P<document_id>\w+)/(?P<resource_id>\w+)/?$", 
         CollaborationAPIHandler),
        
        # History API
        (r"/api/collaboration/v1/(?P<endpoint>history)/(?P<document_id>\w+)/?$", 
         CollaborationAPIHandler),
        (r"/api/collaboration/v1/(?P<endpoint>history)/(?P<document_id>\w+)/(?P<resource_id>\w+)/?$", 
         CollaborationAPIHandler),
        
        # Presence API
        (r"/api/collaboration/v1/(?P<endpoint>presence)/(?P<document_id>\w+)/?$", 
         CollaborationAPIHandler),
        
        # Locks API
        (r"/api/collaboration/v1/(?P<endpoint>locks)/(?P<document_id>\w+)/?$", 
         CollaborationAPIHandler),
        (r"/api/collaboration/v1/(?P<endpoint>locks)/(?P<document_id>\w+)/(?P<resource_id>\w+)/?$", 
         CollaborationAPIHandler),
        
        # Sessions API
        (r"/api/collaboration/v1/(?P<endpoint>sessions)/(?P<document_id>\w+)/?$", 
         CollaborationAPIHandler),
        (r"/api/collaboration/v1/(?P<endpoint>sessions)/(?P<document_id>\w+)/(?P<resource_id>\w+)/?$", 
         CollaborationAPIHandler),
    ])
    
    logger.info("Collaboration handlers registered")
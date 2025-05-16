"""Server-side implementation of the Yjs awareness protocol for Jupyter Notebook.

This module implements the server-side component of the user presence awareness system,
tracking and broadcasting information about connected users, their cursor positions,
selections, and activity status. It handles awareness update messages, manages user
metadata, and provides cleanup mechanisms for disconnected users.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import tornado.ioloop
from jupyter_server.base.handlers import JupyterHandler

logger = logging.getLogger(__name__)

# Default timeout for awareness states (in milliseconds)
# After this period without updates, a client is considered disconnected
AWARENESS_CLEANUP_TIMEOUT = 30000  # 30 seconds

# Message type for awareness updates in the Yjs protocol
AWARENESS_MESSAGE_TYPE = 1

class AwarenessState:
    """Represents the awareness state for a single client."""
    
    def __init__(self, client_id: int, state: Dict[str, Any]):
        """Initialize a new awareness state.
        
        Args:
            client_id: The unique identifier for the client
            state: The awareness state data (user info, cursor position, etc.)
        """
        self.client_id = client_id
        self.state = state
        self.last_updated = time.time() * 1000  # Current time in milliseconds
    
    def update(self, state: Dict[str, Any]) -> None:
        """Update the awareness state.
        
        Args:
            state: The new awareness state data
        """
        self.state = state
        self.last_updated = time.time() * 1000
    
    def is_expired(self, timeout: int = AWARENESS_CLEANUP_TIMEOUT) -> bool:
        """Check if this awareness state has expired.
        
        Args:
            timeout: The timeout period in milliseconds
            
        Returns:
            True if the state has not been updated within the timeout period
        """
        current_time = time.time() * 1000
        return (current_time - self.last_updated) > timeout


class AwarenessManager:
    """Manages awareness states for all clients connected to a document."""
    
    def __init__(self, document_id: str):
        """Initialize a new awareness manager for a document.
        
        Args:
            document_id: The unique identifier for the document
        """
        self.document_id = document_id
        self.states: Dict[int, AwarenessState] = {}  # client_id -> AwarenessState
        self.clients: Dict[str, int] = {}  # connection_id -> client_id
        self._cleanup_task = None
        self._handlers = set()  # WebSocket handlers for broadcasting
    
    def start_cleanup_task(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Start the periodic cleanup task for expired awareness states.
        
        Args:
            loop: The event loop to use for the cleanup task
        """
        if self._cleanup_task is None:
            loop = loop or asyncio.get_event_loop()
            self._cleanup_task = loop.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self) -> None:
        """Periodically check for and remove expired awareness states."""
        try:
            while True:
                # Check every 5 seconds
                await asyncio.sleep(5)
                self.cleanup_expired_states()
        except asyncio.CancelledError:
            logger.debug(f"Awareness cleanup task for document {self.document_id} cancelled")
        except Exception as e:
            logger.exception(f"Error in awareness cleanup task: {e}")
    
    def stop_cleanup_task(self) -> None:
        """Stop the periodic cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            self._cleanup_task = None
    
    def register_handler(self, handler: JupyterHandler) -> None:
        """Register a WebSocket handler for broadcasting awareness updates.
        
        Args:
            handler: The WebSocket handler to register
        """
        self._handlers.add(handler)
    
    def unregister_handler(self, handler: JupyterHandler) -> None:
        """Unregister a WebSocket handler.
        
        Args:
            handler: The WebSocket handler to unregister
        """
        if handler in self._handlers:
            self._handlers.remove(handler)
    
    def update_state(self, client_id: int, state: Dict[str, Any]) -> Tuple[bool, List[int]]:
        """Update the awareness state for a client.
        
        Args:
            client_id: The unique identifier for the client
            state: The new awareness state data
            
        Returns:
            A tuple of (is_new_client, [updated_client_ids])
        """
        is_new = client_id not in self.states
        
        if is_new:
            self.states[client_id] = AwarenessState(client_id, state)
        else:
            self.states[client_id].update(state)
        
        return is_new, [client_id]
    
    def remove_states(self, client_ids: List[int]) -> List[int]:
        """Remove awareness states for specified clients.
        
        Args:
            client_ids: List of client IDs to remove
            
        Returns:
            List of client IDs that were actually removed
        """
        removed = []
        for client_id in client_ids:
            if client_id in self.states:
                del self.states[client_id]
                removed.append(client_id)
                
                # Also remove from clients mapping
                for conn_id, cid in list(self.clients.items()):
                    if cid == client_id:
                        del self.clients[conn_id]
        
        return removed
    
    def cleanup_expired_states(self) -> List[int]:
        """Remove awareness states that have expired.
        
        Returns:
            List of client IDs that were removed
        """
        expired_clients = []
        
        for client_id, state in list(self.states.items()):
            if state.is_expired():
                expired_clients.append(client_id)
        
        if expired_clients:
            removed = self.remove_states(expired_clients)
            if removed:
                logger.debug(f"Removed expired awareness states for clients: {removed}")
            return removed
        
        return []
    
    def get_states(self) -> Dict[int, Dict[str, Any]]:
        """Get all current awareness states.
        
        Returns:
            Dictionary mapping client IDs to their awareness states
        """
        return {client_id: state.state for client_id, state in self.states.items()}
    
    def get_state(self, client_id: int) -> Optional[Dict[str, Any]]:
        """Get the awareness state for a specific client.
        
        Args:
            client_id: The client ID to get the state for
            
        Returns:
            The awareness state or None if not found
        """
        if client_id in self.states:
            return self.states[client_id].state
        return None
    
    def associate_connection(self, connection_id: str, client_id: int) -> None:
        """Associate a connection ID with a client ID.
        
        Args:
            connection_id: The unique connection identifier
            client_id: The client ID to associate with this connection
        """
        self.clients[connection_id] = client_id
    
    def remove_connection(self, connection_id: str) -> Optional[int]:
        """Remove a connection and its associated awareness state.
        
        Args:
            connection_id: The connection ID to remove
            
        Returns:
            The client ID that was removed, or None if not found
        """
        if connection_id in self.clients:
            client_id = self.clients[connection_id]
            del self.clients[connection_id]
            
            # Check if this client ID is used by other connections
            if client_id not in [cid for cid in self.clients.values()]:
                # If not, remove the awareness state
                if client_id in self.states:
                    del self.states[client_id]
                    return client_id
        
        return None
    
    async def broadcast_awareness_update(self, updated_clients: List[int], exclude_handler: Optional[JupyterHandler] = None) -> None:
        """Broadcast awareness updates to all connected clients.
        
        Args:
            updated_clients: List of client IDs whose states have been updated
            exclude_handler: Optional handler to exclude from broadcasting
        """
        if not updated_clients or not self._handlers:
            return
        
        # Encode the awareness update
        update = encode_awareness_update(self, updated_clients)
        
        # Broadcast to all handlers except the excluded one
        for handler in self._handlers:
            if handler != exclude_handler and hasattr(handler, 'write_message'):
                try:
                    await handler.write_message(update, binary=True)
                except Exception as e:
                    logger.error(f"Error broadcasting awareness update: {e}")
                    # Unregister the handler if we can't write to it
                    self.unregister_handler(handler)


class AwarenessRegistry:
    """Registry of awareness managers for all active documents."""
    
    def __init__(self):
        """Initialize a new awareness registry."""
        self.managers: Dict[str, AwarenessManager] = {}
    
    def get_manager(self, document_id: str) -> AwarenessManager:
        """Get or create an awareness manager for a document.
        
        Args:
            document_id: The document ID to get the manager for
            
        Returns:
            The awareness manager for the document
        """
        if document_id not in self.managers:
            self.managers[document_id] = AwarenessManager(document_id)
            # Start the cleanup task for the new manager
            self.managers[document_id].start_cleanup_task()
        
        return self.managers[document_id]
    
    def remove_manager(self, document_id: str) -> None:
        """Remove an awareness manager for a document.
        
        Args:
            document_id: The document ID to remove the manager for
        """
        if document_id in self.managers:
            # Stop the cleanup task before removing
            self.managers[document_id].stop_cleanup_task()
            del self.managers[document_id]


# Global registry of awareness managers
awareness_registry = AwarenessRegistry()


def encode_awareness_update(manager: AwarenessManager, client_ids: List[int]) -> bytes:
    """Encode awareness states into a binary update message.
    
    This function encodes awareness states in a format compatible with the
    y-protocols/awareness JavaScript implementation.
    
    Args:
        manager: The awareness manager containing the states
        client_ids: List of client IDs to include in the update
        
    Returns:
        Binary encoded awareness update message
    """
    # Format: [messageType, stateVector]
    # where stateVector is a map of client_id -> state
    states = {}
    for client_id in client_ids:
        if client_id in manager.states:
            states[str(client_id)] = manager.states[client_id].state
    
    # Create the awareness update message
    # First byte is message type (1 for awareness)
    # Rest is JSON encoded state data
    message = bytearray([AWARENESS_MESSAGE_TYPE])
    message.extend(json.dumps(states).encode('utf-8'))
    
    return bytes(message)


def decode_awareness_update(update: bytes) -> Tuple[int, Dict[int, Dict[str, Any]]]:
    """Decode a binary awareness update message.
    
    Args:
        update: Binary encoded awareness update message
        
    Returns:
        Tuple of (message_type, {client_id: state})
    """
    if not update or len(update) < 1:
        raise ValueError("Invalid awareness update: empty message")
    
    # First byte is the message type
    message_type = update[0]
    
    if message_type != AWARENESS_MESSAGE_TYPE:
        raise ValueError(f"Invalid awareness message type: {message_type}")
    
    # Rest is JSON encoded state data
    try:
        states_json = update[1:].decode('utf-8')
        states_dict = json.loads(states_json)
        
        # Convert string client IDs to integers
        states = {int(client_id): state for client_id, state in states_dict.items()}
        
        return message_type, states
    except Exception as e:
        raise ValueError(f"Failed to decode awareness update: {e}")


async def apply_awareness_update(manager: AwarenessManager, update: bytes, source_handler: Optional[JupyterHandler] = None) -> List[int]:
    """Apply an awareness update to a manager and broadcast changes.
    
    Args:
        manager: The awareness manager to apply the update to
        update: Binary encoded awareness update message
        source_handler: The handler that sent the update (to exclude from broadcast)
        
    Returns:
        List of client IDs that were updated
    """
    try:
        _, states = decode_awareness_update(update)
        
        updated_clients = []
        for client_id, state in states.items():
            is_new, updated = manager.update_state(client_id, state)
            updated_clients.extend(updated)
        
        # Broadcast the update to all other clients
        if updated_clients:
            await manager.broadcast_awareness_update(updated_clients, exclude_handler=source_handler)
        
        return updated_clients
    
    except Exception as e:
        logger.error(f"Error applying awareness update: {e}")
        return []


async def remove_awareness_states(manager: AwarenessManager, client_ids: List[int], source_handler: Optional[JupyterHandler] = None) -> List[int]:
    """Remove awareness states for specified clients and broadcast the change.
    
    Args:
        manager: The awareness manager to remove states from
        client_ids: List of client IDs to remove
        source_handler: The handler that requested the removal (to exclude from broadcast)
        
    Returns:
        List of client IDs that were removed
    """
    removed = manager.remove_states(client_ids)
    
    if removed:
        # Broadcast the removal to all clients
        await manager.broadcast_awareness_update(removed, exclude_handler=source_handler)
    
    return removed
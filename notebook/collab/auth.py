"""Authentication and authorization for collaborative editing in Jupyter Notebook.

This module provides classes and functions for authenticating users in collaborative
sessions and enforcing permissions for collaborative actions. It integrates with
JupyterHub for user identity and implements a permission model with different
access levels (view, edit, comment, admin).

Classes:
    CollaborationRole: Enum defining possible roles for collaborative editing
    CollaborationPermission: Represents a permission for a user or group on a notebook
    CollaborationAction: Enum defining possible actions for collaborative operations
    CollaborationAuthorizer: Authorizer that handles collaboration-specific permissions
    CollaborationAuthConfig: Configuration for collaboration authentication and authorization

Functions:
    authorized_for_collaboration: Decorator for checking collaboration authorization
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import json
import logging
import os
import time
import typing as t
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import parse_qs, urlparse

from jupyter_server.auth import Authorizer
from jupyter_server.base.handlers import JupyterHandler
from tornado import web
from tornado.websocket import WebSocketHandler
from traitlets import Bool, Dict, Enum, Float, Instance, Integer, Unicode, default
from traitlets.config import Configurable

# Set up logging
logger = logging.getLogger('notebook.collab.auth')


class CollaborationRole(enum.Enum):
    """Defines the possible roles for collaborative editing.
    
    Roles are hierarchical, with each role having all the permissions of the roles below it:
    VIEWER < COMMENTER < EDITOR < ADMIN < OWNER
    """
    VIEWER = 'viewer'  # Can only view the notebook
    COMMENTER = 'commenter'  # Can view and add comments
    EDITOR = 'editor'  # Can edit cells and add comments
    ADMIN = 'admin'  # Can edit and manage permissions
    OWNER = 'owner'  # Full control including deletion


@dataclass
class CollaborationPermission:
    """Represents a permission for a user or group on a notebook."""
    notebook_id: str
    user_id: str = ''  # Empty for group permissions
    group_id: str = ''  # Empty for user permissions
    role: CollaborationRole = CollaborationRole.VIEWER
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        """Initialize timestamps if not provided."""
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'notebook_id': self.notebook_id,
            'user_id': self.user_id,
            'group_id': self.group_id,
            'role': self.role.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> CollaborationPermission:
        """Create from dictionary after deserialization."""
        role = CollaborationRole(data['role'])
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        return cls(
            notebook_id=data['notebook_id'],
            user_id=data['user_id'],
            group_id=data['group_id'],
            role=role,
            created_at=created_at,
            updated_at=updated_at,
        )


class CollaborationAction(enum.Enum):
    """Defines the possible actions for collaborative operations.
    
    These actions are used for permission checking in the collaboration system.
    Each action corresponds to a specific operation that can be performed in
    a collaborative session.
    
    The actions are grouped by category:
    - Session actions: Basic session operations
    - Comment actions: Operations related to the comment system
    - Lock actions: Operations related to cell locking
    - History actions: Operations related to version history
    - Permission actions: Operations related to permission management
    """
    # Session actions
    JOIN = 'join'  # Join a collaborative session
    LEAVE = 'leave'  # Leave a collaborative session
    VIEW = 'view'  # View notebook content
    EDIT = 'edit'  # Edit notebook content
    
    # Comment actions
    COMMENT_CREATE = 'comment:create'  # Create a new comment
    COMMENT_EDIT = 'comment:edit'  # Edit an existing comment
    COMMENT_DELETE = 'comment:delete'  # Delete a comment
    COMMENT_RESOLVE = 'comment:resolve'  # Resolve a comment thread
    
    # Lock actions
    LOCK_ACQUIRE = 'lock:acquire'  # Acquire a cell lock
    LOCK_RELEASE = 'lock:release'  # Release a cell lock
    LOCK_FORCE_RELEASE = 'lock:force_release'  # Force release another user's lock
    
    # History actions
    HISTORY_VIEW = 'history:view'  # View version history
    HISTORY_COMPARE = 'history:compare'  # Compare versions
    HISTORY_REVERT = 'history:revert'  # Revert to a previous version
    HISTORY_PRUNE = 'history:prune'  # Clean up history
    
    # Permission actions
    PERMISSION_VIEW = 'permission:view'  # View permissions
    PERMISSION_EDIT = 'permission:edit'  # Edit permissions


class CollaborationAuthorizer(Authorizer):
    """Authorizer that handles collaboration-specific permissions."""
    
    # Configuration for anonymous access
    allow_anonymous = Bool(False, config=True,
        help="Whether to allow anonymous access to collaborative sessions")
    
    anonymous_role = Enum(
        values=[role.value for role in CollaborationRole],
        default_value=CollaborationRole.VIEWER.value,
        config=True,
        help="Default role for anonymous users if anonymous access is allowed"
    )
    
    # Token configuration
    token_secret = Unicode(config=True,
        help="Secret key for signing collaboration tokens. If not set, a random one will be generated.")
    
    token_expiration = Float(86400.0, config=True,
        help="Expiration time for collaboration tokens in seconds (default: 24 hours)")
    
    # Lock timeouts
    lock_timeout = Integer(300, config=True,
        help="Timeout for cell locks in seconds (default: 5 minutes)")
    
    # Permission cache timeout
    permission_cache_timeout = Integer(60, config=True,
        help="Timeout for permission cache in seconds (default: 1 minute)")
    
    # Permission store
    permission_store = Instance('notebook.collab.store.CollaborationStore', allow_none=True)
    
    # In-memory cache for permissions
    _permission_cache = Dict()
    _permission_cache_timestamps = Dict()
    
    @default('token_secret')
    def _default_token_secret(self):
        """Generate a random token secret if none is provided."""
        return os.urandom(32).hex()
    
    def is_authorized(self, handler: JupyterHandler, action: str, resource: str) -> bool:
        """Check if the user is authorized for a standard Jupyter action.
        
        This extends the base Authorizer.is_authorized method to handle
        collaboration-specific permissions.
        
        Args:
            handler: The handler processing the request
            action: The action being performed (e.g., 'read', 'write')
            resource: The resource being accessed
            
        Returns:
            bool: True if authorized, False otherwise
        """
        # First check standard authorization
        if not super().is_authorized(handler, action, resource):
            return False
            
        # If this is a collaboration action, check collaboration permissions
        if action.startswith('notebook:collab:'):
            collab_action = action.split(':', 2)[2]  # Extract the collaboration action
            try:
                return self.is_authorized_for_collaboration(
                    handler, CollaborationAction(collab_action), resource
                )
            except ValueError:
                # Invalid collaboration action
                logger.warning(f"Invalid collaboration action: {collab_action}")
                return False
                
        # Not a collaboration action, so standard authorization is sufficient
        return True
    
    def is_authorized_for_collaboration(
        self, handler: JupyterHandler, action: CollaborationAction, notebook_id: str
    ) -> bool:
        """Check if the user is authorized for a collaboration action.
        
        This is the main authorization method for collaboration actions.
        It extracts the user ID from the handler, determines the user's role
        for the specified notebook, and checks if that role allows the
        requested action.
        
        This method is used by the authorized_for_collaboration decorator
        to enforce permissions on handler methods.
        
        Args:
            handler: The handler processing the request
            action: The collaboration action being performed
            notebook_id: The ID of the notebook being accessed
            
        Returns:
            bool: True if authorized, False otherwise
        """
        # Get user information
        user_id = self._get_user_id(handler)
        if not user_id and not self.allow_anonymous:
            logger.warning(f"Anonymous access denied for {action.value} on {notebook_id}")
            return False
            
        # Get user's role for this notebook
        role = self._get_user_role(user_id, notebook_id)
        if role is None:
            logger.warning(f"No role found for user {user_id} on notebook {notebook_id}")
            return False
            
        # Check if the role allows the action
        return self._is_action_allowed(role, action)
    
    def validate_crdt_update(self, user_id: str, notebook_id: str, update: dict) -> bool:
        """Validate if a CRDT update is allowed for the user.
        
        This method checks if the user has permission to make the specific CRDT update.
        The actual parsing of the Yjs update structure depends on the specific format
        used by the Yjs implementation.
        
        Args:
            user_id: The ID of the user making the update
            notebook_id: The ID of the notebook being updated
            update: The CRDT update data
            
        Returns:
            bool: True if the update is allowed, False otherwise
        """
        # Get user's role for this notebook
        role = self._get_user_role(user_id, notebook_id)
        if role is None:
            logger.warning(f"No role found for user {user_id} on notebook {notebook_id}")
            return False
            
        # Viewers can't make any updates
        if role == CollaborationRole.VIEWER:
            return False
            
        # Commenters can only update comment-related data
        if role == CollaborationRole.COMMENTER:
            # Check if update only affects comments (implementation depends on CRDT structure)
            # This is a simplified check - real implementation would need to parse the Yjs update
            if 'comments' not in str(update):
                return False
                
        # Editors, admins, and owners can make any updates
        return True
    
    def check_lock_permission(
        self, user_id: str, notebook_id: str, cell_id: str, action: CollaborationAction
    ) -> bool:
        """Check if user can acquire/release locks on cells.
        
        Args:
            user_id: The ID of the user performing the lock action
            notebook_id: The ID of the notebook containing the cell
            cell_id: The ID of the cell being locked/unlocked
            action: The lock action (LOCK_ACQUIRE, LOCK_RELEASE, LOCK_FORCE_RELEASE)
            
        Returns:
            bool: True if the lock action is allowed, False otherwise
        """
        # Get user's role for this notebook
        role = self._get_user_role(user_id, notebook_id)
        if role is None:
            logger.warning(f"No role found for user {user_id} on notebook {notebook_id}")
            return False
            
        # Check lock acquisition
        if action == CollaborationAction.LOCK_ACQUIRE:
            # Only editors, admins, and owners can acquire locks
            return role in (
                CollaborationRole.EDITOR,
                CollaborationRole.ADMIN,
                CollaborationRole.OWNER
            )
            
        # Check lock release
        elif action == CollaborationAction.LOCK_RELEASE:
            # Anyone can release their own locks, which will be checked at the handler level
            return True
            
        # Check force release (admin override)
        elif action == CollaborationAction.LOCK_FORCE_RELEASE:
            # Only admins and owners can force release locks
            return role in (CollaborationRole.ADMIN, CollaborationRole.OWNER)
            
        # Unknown lock action
        logger.warning(f"Unknown lock action: {action}")
        return False
    
    def create_collaboration_token(self, user_id: str, notebook_id: str) -> str:
        """Create a signed token for WebSocket authentication.
        
        This method creates a secure token that can be used to authenticate
        WebSocket connections for collaborative editing. The token includes
        the user ID, notebook ID, and expiration time, and is signed with
        the token_secret to prevent tampering.
        
        The token is base64-encoded and can be included in WebSocket requests
        as described in extract_token_from_request().
        
        Args:
            user_id: The ID of the user
            notebook_id: The ID of the notebook
            
        Returns:
            str: A signed token for WebSocket authentication
        """
        # Create token payload
        now = int(time.time())
        expiration = now + int(self.token_expiration)
        payload = {
            'user_id': user_id,
            'notebook_id': notebook_id,
            'iat': now,
            'exp': expiration
        }
        
        # Convert payload to JSON string
        payload_str = json.dumps(payload, sort_keys=True)
        
        # Create signature
        signature = hmac.new(
            self.token_secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Combine payload and signature
        token_data = {
            'payload': payload,
            'signature': signature
        }
        
        # Return base64-encoded token
        import base64
        return base64.urlsafe_b64encode(json.dumps(token_data).encode()).decode()
    
    def validate_collaboration_token(self, token: str) -> t.Optional[dict]:
        """Validate a collaboration token and return the payload if valid.
        
        This method validates a token created by create_collaboration_token().
        It checks the signature to ensure the token hasn't been tampered with,
        and verifies that the token hasn't expired.
        
        If the token is valid, the payload is returned, which includes:
        - user_id: The ID of the user
        - notebook_id: The ID of the notebook
        - iat: The timestamp when the token was issued
        - exp: The timestamp when the token expires
        
        Args:
            token: The token to validate
            
        Returns:
            Optional[dict]: The token payload if valid, None otherwise
        """
        try:
            # Decode token
            import base64
            token_data = json.loads(base64.urlsafe_b64decode(token).decode())
            
            # Extract payload and signature
            payload = token_data['payload']
            signature = token_data['signature']
            
            # Verify signature
            payload_str = json.dumps(payload, sort_keys=True)
            expected_signature = hmac.new(
                self.token_secret.encode(),
                payload_str.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Invalid token signature")
                return None
                
            # Check expiration
            now = int(time.time())
            if payload['exp'] < now:
                logger.warning("Token expired")
                return None
                
            # Token is valid
            return payload
        except Exception as e:
            logger.warning(f"Error validating token: {e}")
            return None
    
    def extract_token_from_request(self, handler: WebSocketHandler) -> t.Optional[str]:
        """Extract collaboration token from a WebSocket request.
        
        This method is used during WebSocket handshake to authenticate the connection.
        The token can be provided in several ways:
        1. In the Authorization header: 'Authorization: token <token>'
        2. In a custom header: 'Jupyter-Collab-Token: <token>'
        3. As a URL parameter: '?collab_token=<token>'
        
        The extracted token is then validated using validate_collaboration_token().
        
        Args:
            handler: The WebSocket handler processing the request
            
        Returns:
            Optional[str]: The token if found, None otherwise
        """
        # Check Authorization header
        auth_header = handler.request.headers.get('Authorization', '')
        if auth_header.startswith('token '):
            return auth_header[6:]
            
        # Check custom header
        custom_header = handler.request.headers.get('Jupyter-Collab-Token', '')
        if custom_header:
            return custom_header
            
        # Check URL parameters
        query = urlparse(handler.request.uri).query
        params = parse_qs(query)
        if 'collab_token' in params and params['collab_token']:
            return params['collab_token'][0]
            
        # No token found
        return None
    
    def get_user_identity(self, handler: JupyterHandler) -> dict:
        """Extract user identity information from the handler.
        
        This method extracts user information from the Jupyter handler,
        including JupyterHub-specific information if available. The returned
        information is used for user presence awareness in collaborative sessions.
        
        The returned dictionary includes:
        - user_id: Unique identifier for the user
        - username: Username for display
        - display_name: Full name for display
        - initials: Initials for avatar
        - color: Consistent color for user highlighting
        - is_anonymous: Whether the user is anonymous
        - groups: List of group memberships (if available from JupyterHub)
        - admin: Whether the user is an admin (if available from JupyterHub)
        
        Args:
            handler: The handler processing the request
            
        Returns:
            dict: User identity information
        """
        user_id = self._get_user_id(handler)
        if not user_id:
            # Anonymous user
            return {
                'user_id': '',
                'username': 'anonymous',
                'display_name': 'Anonymous User',
                'initials': 'AU',
                'color': '#808080',  # Gray for anonymous users
                'is_anonymous': True
            }
            
        # Get JupyterHub user info if available
        hub_user = {}
        if hasattr(handler, 'hub_auth') and handler.hub_auth.get_user(handler):
            hub_user = handler.hub_auth.get_user(handler)
            
        # Extract username and display name
        username = hub_user.get('name', user_id)
        display_name = hub_user.get('display_name', username)
        
        # Generate initials from display name
        initials = ''.join([name[0].upper() for name in display_name.split() if name])
        if not initials and display_name:
            initials = display_name[0].upper()
        if not initials:
            initials = username[0].upper() if username else 'U'
            
        # Generate a consistent color based on the user ID
        color_hash = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        # Use a predefined set of colors for better visibility and contrast
        colors = [
            '#F44336', '#E91E63', '#9C27B0', '#673AB7', '#3F51B5',
            '#2196F3', '#03A9F4', '#00BCD4', '#009688', '#4CAF50',
            '#8BC34A', '#CDDC39', '#FFEB3B', '#FFC107', '#FF9800',
            '#FF5722', '#795548', '#9E9E9E', '#607D8B'
        ]
        color = colors[color_hash % len(colors)]
        
        return {
            'user_id': user_id,
            'username': username,
            'display_name': display_name,
            'initials': initials,
            'color': color,
            'is_anonymous': False,
            # Include additional JupyterHub info if available
            'groups': hub_user.get('groups', []),
            'admin': hub_user.get('admin', False)
        }
    
    def set_notebook_permission(
        self, notebook_id: str, user_id: str, role: CollaborationRole, group_id: str = ''
    ) -> bool:
        """Set permission for a user or group on a notebook.
        
        This method creates or updates a permission for a user or group on a notebook.
        It stores the permission in the permission_store and clears the cache for
        the affected notebook.
        
        Either user_id or group_id must be provided, but not both. If both are provided,
        user_id takes precedence.
        
        Args:
            notebook_id: The ID of the notebook
            user_id: The ID of the user (empty for group permissions)
            role: The role to assign
            group_id: The ID of the group (empty for user permissions)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.permission_store:
            logger.error("Permission store not available")
            return False
            
        # Create or update permission
        permission = CollaborationPermission(
            notebook_id=notebook_id,
            user_id=user_id,
            group_id=group_id,
            role=role,
            updated_at=datetime.utcnow()
        )
        
        # Store the permission
        success = self.permission_store.set_permission(permission)
        
        # Clear cache for this notebook
        self._clear_permission_cache(notebook_id)
        
        return success
    
    def get_notebook_permissions(self, notebook_id: str) -> list[CollaborationPermission]:
        """Get all permissions for a notebook.
        
        Args:
            notebook_id: The ID of the notebook
            
        Returns:
            list[CollaborationPermission]: List of permissions
        """
        if not self.permission_store:
            logger.error("Permission store not available")
            return []
            
        return self.permission_store.get_notebook_permissions(notebook_id)
    
    def get_user_notebooks(self, user_id: str) -> list[str]:
        """Get all notebooks a user has access to.
        
        Args:
            user_id: The ID of the user
            
        Returns:
            list[str]: List of notebook IDs
        """
        if not self.permission_store:
            logger.error("Permission store not available")
            return []
            
        return self.permission_store.get_user_notebooks(user_id)
    
    def delete_notebook_permission(
        self, notebook_id: str, user_id: str = '', group_id: str = ''
    ) -> bool:
        """Delete a permission for a user or group on a notebook.
        
        Args:
            notebook_id: The ID of the notebook
            user_id: The ID of the user (empty for group permissions)
            group_id: The ID of the group (empty for user permissions)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.permission_store:
            logger.error("Permission store not available")
            return False
            
        # Delete the permission
        success = self.permission_store.delete_permission(notebook_id, user_id, group_id)
        
        # Clear cache for this notebook
        self._clear_permission_cache(notebook_id)
        
        return success
    
    def _get_user_id(self, handler: JupyterHandler) -> str:
        """Extract user ID from the handler.
        
        Args:
            handler: The handler processing the request
            
        Returns:
            str: The user ID, or empty string for anonymous users
        """
        # Check if JupyterHub integration is available
        if hasattr(handler, 'hub_auth') and handler.hub_auth.get_user(handler):
            return handler.hub_auth.get_user(handler).get('name', '')
            
        # Fall back to the username from the handler
        return getattr(handler, 'current_user', None) or ''
    
    def _get_user_role(self, user_id: str, notebook_id: str) -> t.Optional[CollaborationRole]:
        """Get the role of a user for a notebook.
        
        This method checks the cache first, then falls back to the permission store.
        
        Args:
            user_id: The ID of the user
            notebook_id: The ID of the notebook
            
        Returns:
            Optional[CollaborationRole]: The user's role, or None if not found
        """
        # Anonymous user handling
        if not user_id:
            return CollaborationRole(self.anonymous_role) if self.allow_anonymous else None
            
        # Check cache first
        cache_key = f"{user_id}:{notebook_id}"
        if cache_key in self._permission_cache:
            # Check if cache is still valid
            timestamp = self._permission_cache_timestamps.get(cache_key, 0)
            if time.time() - timestamp < self.permission_cache_timeout:
                return self._permission_cache[cache_key]
            
        # Cache miss or expired, check permission store
        if not self.permission_store:
            logger.error("Permission store not available")
            return None
            
        # Get user's direct permissions
        user_permission = self.permission_store.get_user_permission(user_id, notebook_id)
        if user_permission:
            # Cache the result
            self._permission_cache[cache_key] = user_permission.role
            self._permission_cache_timestamps[cache_key] = time.time()
            return user_permission.role
            
        # Check group permissions if no direct permission
        # This requires JupyterHub integration to get user groups
        # For now, we'll return None if no direct permission is found
        # TODO: Implement group permission checking
        
        # No permission found
        return None
    
    def _is_action_allowed(self, role: CollaborationRole, action: CollaborationAction) -> bool:
        """Check if an action is allowed for a role.
        
        This method implements the permission matrix that defines which actions
        are allowed for each role. The permissions are hierarchical, with each
        role having all the permissions of the roles below it.
        
        The permission matrix is defined as follows:
        - VIEWER: Can view the notebook and history, but cannot edit or comment
        - COMMENTER: Can view and add/edit/resolve comments, but cannot edit cells
        - EDITOR: Can view, comment, and edit cells, but cannot manage permissions
        - ADMIN: Can do everything except delete the notebook
        - OWNER: Has full control, including deletion
        
        Args:
            role: The user's role
            action: The action being performed
            
        Returns:
            bool: True if the action is allowed, False otherwise
        """
        # Define permissions for each role
        permissions = {
            CollaborationRole.VIEWER: {
                CollaborationAction.JOIN,
                CollaborationAction.LEAVE,
                CollaborationAction.VIEW,
                CollaborationAction.HISTORY_VIEW,
                CollaborationAction.HISTORY_COMPARE,
            },
            CollaborationRole.COMMENTER: {
                CollaborationAction.JOIN,
                CollaborationAction.LEAVE,
                CollaborationAction.VIEW,
                CollaborationAction.COMMENT_CREATE,
                CollaborationAction.COMMENT_EDIT,  # Can edit own comments
                CollaborationAction.COMMENT_DELETE,  # Can delete own comments
                CollaborationAction.COMMENT_RESOLVE,  # Can resolve comments
                CollaborationAction.HISTORY_VIEW,
                CollaborationAction.HISTORY_COMPARE,
            },
            CollaborationRole.EDITOR: {
                CollaborationAction.JOIN,
                CollaborationAction.LEAVE,
                CollaborationAction.VIEW,
                CollaborationAction.EDIT,
                CollaborationAction.COMMENT_CREATE,
                CollaborationAction.COMMENT_EDIT,
                CollaborationAction.COMMENT_DELETE,
                CollaborationAction.COMMENT_RESOLVE,
                CollaborationAction.LOCK_ACQUIRE,
                CollaborationAction.LOCK_RELEASE,
                CollaborationAction.HISTORY_VIEW,
                CollaborationAction.HISTORY_COMPARE,
                CollaborationAction.HISTORY_REVERT,
            },
            CollaborationRole.ADMIN: {
                CollaborationAction.JOIN,
                CollaborationAction.LEAVE,
                CollaborationAction.VIEW,
                CollaborationAction.EDIT,
                CollaborationAction.COMMENT_CREATE,
                CollaborationAction.COMMENT_EDIT,
                CollaborationAction.COMMENT_DELETE,
                CollaborationAction.COMMENT_RESOLVE,
                CollaborationAction.LOCK_ACQUIRE,
                CollaborationAction.LOCK_RELEASE,
                CollaborationAction.LOCK_FORCE_RELEASE,
                CollaborationAction.HISTORY_VIEW,
                CollaborationAction.HISTORY_COMPARE,
                CollaborationAction.HISTORY_REVERT,
                CollaborationAction.HISTORY_PRUNE,
                CollaborationAction.PERMISSION_VIEW,
                CollaborationAction.PERMISSION_EDIT,
            },
            CollaborationRole.OWNER: {
                # Owners can do everything
                action for action in CollaborationAction
            }
        }
        
        # Check if the action is allowed for the role
        return action in permissions.get(role, set())
    
    def _clear_permission_cache(self, notebook_id: str = None):
        """Clear the permission cache for a notebook or all notebooks.
        
        Args:
            notebook_id: The ID of the notebook, or None to clear all
        """
        if notebook_id is None:
            # Clear all cache
            self._permission_cache = {}
            self._permission_cache_timestamps = {}
            return
            
        # Clear cache for specific notebook
        keys_to_remove = []
        for key in self._permission_cache:
            if key.endswith(f":{notebook_id}"):
                keys_to_remove.append(key)
                
        for key in keys_to_remove:
            self._permission_cache.pop(key, None)
            self._permission_cache_timestamps.pop(key, None)


def authorized_for_collaboration(action: CollaborationAction):
    """Decorator for checking collaboration authorization.
    
    This decorator can be used on handler methods to check if the user
    is authorized for a specific collaboration action. It should be applied
    to methods of handlers that process collaboration requests.
    
    Example:
        ```python
        class CollaborationHandler(JupyterHandler):
            @authorized_for_collaboration(CollaborationAction.EDIT)
            async def post(self, notebook_id):
                # Handle edit request
                pass
        ```
    
    Args:
        action: The collaboration action to check
        
    Returns:
        callable: Decorator function
    """
    def decorator(method):
        @wraps(method)
        async def wrapper(self, notebook_id, *args, **kwargs):
            # Get the authorizer
            authorizer = self.settings.get('authorizer')
            if not isinstance(authorizer, CollaborationAuthorizer):
                raise web.HTTPError(500, "Collaboration authorizer not configured")
                
            # Check authorization
            if not authorizer.is_authorized_for_collaboration(self, action, notebook_id):
                raise web.HTTPError(403, f"Not authorized for {action.value} on {notebook_id}")
                
            # Call the original method
            return await method(self, notebook_id, *args, **kwargs)
        return wrapper
    return decorator


class CollaborationAuthConfig(Configurable):
    """Configuration for collaboration authentication and authorization.
    
    This class provides configuration options for the collaboration authentication
    and authorization system. It can be configured through the Jupyter configuration
    system, either in jupyter_notebook_config.py or via command-line arguments.
    
    Example:
        ```python
        # In jupyter_notebook_config.py
        c.CollaborationAuthConfig.allow_anonymous = True
        c.CollaborationAuthConfig.anonymous_role = 'viewer'
        c.CollaborationAuthConfig.token_expiration = 43200  # 12 hours
        ```
    """
    
    # JupyterHub integration
    jupyterhub_integration = Bool(True, config=True,
        help="Whether to integrate with JupyterHub for authentication")
    
    # Anonymous access
    allow_anonymous = Bool(False, config=True,
        help="Whether to allow anonymous access to collaborative sessions")
    
    anonymous_role = Enum(
        values=[role.value for role in CollaborationRole],
        default_value=CollaborationRole.VIEWER.value,
        config=True,
        help="Default role for anonymous users if anonymous access is allowed"
    )
    
    # Default owner role assignment
    default_owner_assignment = Bool(True, config=True,
        help="Whether to automatically assign owner role to the creator of a notebook")
    
    # Token configuration
    token_secret = Unicode(config=True,
        help="Secret key for signing collaboration tokens. If not set, a random one will be generated.")
    
    token_expiration = Float(86400.0, config=True,
        help="Expiration time for collaboration tokens in seconds (default: 24 hours)")
    
    # WebSocket security
    require_wss = Bool(True, config=True,
        help="Whether to require WSS (WebSocket Secure) for collaboration connections")
    
    # Session timeouts
    session_timeout = Integer(3600, config=True,
        help="Timeout for inactive collaboration sessions in seconds (default: 1 hour)")
    
    # Lock timeouts
    lock_timeout = Integer(300, config=True,
        help="Timeout for cell locks in seconds (default: 5 minutes)")
    
    # Permission cache timeout
    permission_cache_timeout = Integer(60, config=True,
        help="Timeout for permission cache in seconds (default: 1 minute)")
    
    @default('token_secret')
    def _default_token_secret(self):
        """Generate a random token secret if none is provided."""
        return os.urandom(32).hex()
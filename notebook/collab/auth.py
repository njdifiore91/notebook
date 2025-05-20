"""Authentication and authorization for collaborative editing in Jupyter Notebook.

This module implements authentication and authorization for collaborative editing
in Jupyter Notebook. It provides integration with JupyterHub authentication,
a permission model with different access levels (view, edit, comment, admin),
and permission checking for collaborative operations.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from jupyter_server.auth import Authorizer
from jupyter_server.base.handlers import JupyterHandler
from tornado.web import HTTPError
from traitlets import Bool, Dict as TDict, Enum as TEnum, Integer, Unicode
from traitlets.config import Configurable

# Set up logging
logger = logging.getLogger('notebook.collab.auth')


class CollaborationPermission(str, Enum):
    """Permissions for collaborative editing."""
    VIEW = "view"  # Can view the notebook but not edit
    COMMENT = "comment"  # Can add comments but not edit cells
    EDIT = "edit"  # Can edit cells
    LOCK = "lock"  # Can lock/unlock cells
    ADMIN = "admin"  # Can manage permissions
    FORCE_UNLOCK = "force-unlock"  # Can force unlock cells locked by others
    VIEW_HISTORY = "view-history"  # Can view document history
    REVERT_HISTORY = "revert-history"  # Can revert to previous versions


class CollaborationRole(str, Enum):
    """Roles for collaborative editing."""
    VIEWER = "viewer"  # Read-only access
    COMMENTER = "commenter"  # Can comment but not edit
    EDITOR = "editor"  # Can edit cells
    ADMIN = "admin"  # Full control
    OWNER = "owner"  # Owner of the notebook


# Define permissions for each role
ROLE_PERMISSIONS = {
    CollaborationRole.VIEWER: {
        CollaborationPermission.VIEW,
        CollaborationPermission.VIEW_HISTORY,
    },
    CollaborationRole.COMMENTER: {
        CollaborationPermission.VIEW,
        CollaborationPermission.COMMENT,
        CollaborationPermission.VIEW_HISTORY,
    },
    CollaborationRole.EDITOR: {
        CollaborationPermission.VIEW,
        CollaborationPermission.COMMENT,
        CollaborationPermission.EDIT,
        CollaborationPermission.LOCK,
        CollaborationPermission.VIEW_HISTORY,
    },
    CollaborationRole.ADMIN: {
        CollaborationPermission.VIEW,
        CollaborationPermission.COMMENT,
        CollaborationPermission.EDIT,
        CollaborationPermission.LOCK,
        CollaborationPermission.ADMIN,
        CollaborationPermission.FORCE_UNLOCK,
        CollaborationPermission.VIEW_HISTORY,
        CollaborationPermission.REVERT_HISTORY,
    },
    CollaborationRole.OWNER: {
        CollaborationPermission.VIEW,
        CollaborationPermission.COMMENT,
        CollaborationPermission.EDIT,
        CollaborationPermission.LOCK,
        CollaborationPermission.ADMIN,
        CollaborationPermission.FORCE_UNLOCK,
        CollaborationPermission.VIEW_HISTORY,
        CollaborationPermission.REVERT_HISTORY,
    },
}


class CollaborationAuthConfig(Configurable):
    """Configuration for collaboration authentication and authorization."""
    
    # Default role for users without explicit permissions
    default_role = TEnum(
        default_value=CollaborationRole.VIEWER,
        values=[role.value for role in CollaborationRole],
        help="Default role for users without explicit permissions"
    ).tag(config=True)
    
    # Whether to allow anonymous access
    allow_anonymous = Bool(
        default_value=False,
        help="Whether to allow anonymous access to collaborative sessions"
    ).tag(config=True)
    
    # Role for anonymous users
    anonymous_role = TEnum(
        default_value=CollaborationRole.VIEWER,
        values=[role.value for role in CollaborationRole],
        help="Role for anonymous users if anonymous access is allowed"
    ).tag(config=True)
    
    # Token expiration time in seconds (default: 24 hours)
    token_expiration = Integer(
        default_value=86400,
        help="Collaboration token expiration time in seconds"
    ).tag(config=True)
    
    # Secret for signing collaboration tokens
    token_secret = Unicode(
        help="Secret for signing collaboration tokens"
    ).tag(config=True)
    
    # Whether to require secure WebSocket connections (WSS)
    require_wss = Bool(
        default_value=True,
        help="Whether to require secure WebSocket connections (WSS)"
    ).tag(config=True)
    
    # JupyterHub scopes mapping to collaboration roles
    jupyterhub_scope_mapping = TDict(
        default_value={
            "notebooks:read:{notebook_id}": CollaborationRole.VIEWER,
            "notebooks:comment:{notebook_id}": CollaborationRole.COMMENTER,
            "notebooks:write:{notebook_id}": CollaborationRole.EDITOR,
            "notebooks:admin:{notebook_id}": CollaborationRole.ADMIN,
            "notebooks:own:{notebook_id}": CollaborationRole.OWNER,
        },
        help="Mapping of JupyterHub scopes to collaboration roles"
    ).tag(config=True)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Generate a random token secret if not provided
        if not self.token_secret:
            self.token_secret = os.urandom(32).hex()


class CollaborationAuthorizer(Authorizer):
    """Authorizer for collaborative editing operations.
    
    This class extends the Jupyter Server Authorizer to add support for
    collaboration-specific permissions.
    """
    
    def __init__(self, config=None):
        super().__init__(config=config)
        
        # Configuration
        self.config = CollaborationAuthConfig(config=config)
        
        # Permission cache
        # Maps notebook_id -> {user_id: role}
        self._permission_cache = {}
        
        # Token cache
        # Maps token -> {user_id, notebook_id, expiration, role}
        self._token_cache = {}
    
    def is_authorized_for_collaboration(self, handler, action, notebook_id):
        """Check if the user is authorized for a collaboration action.
        
        Args:
            handler: The request handler
            action: The collaboration action
            notebook_id: The notebook ID
            
        Returns:
            bool: True if authorized, False otherwise
        """
        # Get the user ID
        user_id = self._get_user_id(handler)
        
        # Convert action to CollaborationPermission if it's a string
        try:
            permission = CollaborationPermission(action)
        except ValueError:
            logger.warning(f"Unknown collaboration permission: {action}")
            return False
        
        # Get the user's role for this notebook
        role = self._get_user_role(user_id, notebook_id)
        
        # Check if the role has the required permission
        return permission in ROLE_PERMISSIONS.get(role, set())
    
    def validate_crdt_update(self, user_id, notebook_id, update):
        """Validate if a CRDT update is allowed for the user.
        
        Args:
            user_id: The user ID
            notebook_id: The notebook ID
            update: The CRDT update
            
        Returns:
            bool: True if the update is allowed, False otherwise
        """
        # Get the user's role for this notebook
        role = self._get_user_role(user_id, notebook_id)
        
        # Check if the user has edit permission
        return CollaborationPermission.EDIT in ROLE_PERMISSIONS.get(role, set())
    
    def check_lock_permission(self, user_id, notebook_id, cell_id, action):
        """Check if the user can perform a lock action on a cell.
        
        Args:
            user_id: The user ID
            notebook_id: The notebook ID
            cell_id: The cell ID
            action: The lock action ('lock', 'unlock', 'force-unlock')
            
        Returns:
            bool: True if allowed, False otherwise
        """
        # Get the user's role for this notebook
        role = self._get_user_role(user_id, notebook_id)
        
        # Map action to permission
        if action == 'lock' or action == 'unlock':
            permission = CollaborationPermission.LOCK
        elif action == 'force-unlock':
            permission = CollaborationPermission.FORCE_UNLOCK
        else:
            logger.warning(f"Unknown lock action: {action}")
            return False
        
        # Check if the role has the required permission
        return permission in ROLE_PERMISSIONS.get(role, set())
    
    def set_user_role(self, notebook_id, user_id, role):
        """Set a user's role for a notebook.
        
        Args:
            notebook_id: The notebook ID
            user_id: The user ID
            role: The role to set
        """
        # Convert role to CollaborationRole if it's a string
        if isinstance(role, str):
            try:
                role = CollaborationRole(role)
            except ValueError:
                logger.warning(f"Invalid role: {role}")
                return
        
        # Initialize notebook permissions if needed
        if notebook_id not in self._permission_cache:
            self._permission_cache[notebook_id] = {}
        
        # Set the user's role
        self._permission_cache[notebook_id][user_id] = role
    
    def get_user_role(self, notebook_id, user_id):
        """Get a user's role for a notebook.
        
        Args:
            notebook_id: The notebook ID
            user_id: The user ID
            
        Returns:
            Optional[CollaborationRole]: The user's role
        """
        return self._get_user_role(user_id, notebook_id)
    
    def get_notebook_permissions(self, notebook_id):
        """Get all permissions for a notebook.
        
        Args:
            notebook_id: The notebook ID
            
        Returns:
            Dict[str, CollaborationRole]: Map of user IDs to roles
        """
        return self._permission_cache.get(notebook_id, {}).copy()
    
    def remove_user_role(self, notebook_id, user_id):
        """Remove a user's role for a notebook.
        
        Args:
            notebook_id: The notebook ID
            user_id: The user ID
        """
        # Check if the notebook has any permissions set
        if notebook_id not in self._permission_cache:
            return
        
        # Remove the user's role
        self._permission_cache[notebook_id].pop(user_id, None)
    
    def clear_notebook_permissions(self, notebook_id):
        """Clear all permissions for a notebook.
        
        Args:
            notebook_id: The notebook ID
        """
        self._permission_cache.pop(notebook_id, None)
    
    def generate_collaboration_token(self, user_id, notebook_id, role=None, expiration=None):
        """Generate a token for collaboration authentication.
        
        Args:
            user_id: The user ID
            notebook_id: The notebook ID
            role: Optional role override for this token
            expiration: Optional expiration time in seconds
            
        Returns:
            str: The generated token
        """
        # Use default expiration if not provided
        if expiration is None:
            expiration = self.config.token_expiration
        
        # Calculate expiration timestamp
        expiration_time = time.time() + expiration
        
        # Use the user's current role if not provided
        if role is None:
            role = self._get_user_role(user_id, notebook_id)
        
        # Create token data
        token_data = {
            "user_id": user_id,
            "notebook_id": notebook_id,
            "role": role.value if isinstance(role, CollaborationRole) else role,
            "expiration": expiration_time,
            "created": time.time(),
            "id": uuid.uuid4().hex
        }
        
        # Generate token
        token = self._create_signed_token(token_data)
        
        # Store in cache
        self._token_cache[token] = token_data
        
        return token
    
    def validate_collaboration_token(self, token, notebook_id=None):
        """Validate a collaboration token.
        
        Args:
            token: The token to validate
            notebook_id: Optional notebook ID to validate against
            
        Returns:
            Optional[Dict[str, Any]]: Token data if valid, None otherwise
        """
        try:
            # Check if token is in cache
            if token in self._token_cache:
                cached_token = self._token_cache[token]
                
                # Check if the token has expired
                if cached_token['expiration'] < time.time():
                    # Remove expired token from cache
                    self._token_cache.pop(token, None)
                    return None
                
                # Check if notebook_id matches if provided
                if notebook_id and cached_token['notebook_id'] != notebook_id:
                    return None
                
                return cached_token
            
            # Decode and verify token
            token_data = self._verify_signed_token(token)
            if not token_data:
                return None
            
            # Check if the token has expired
            if token_data['expiration'] < time.time():
                return None
            
            # Check if notebook_id matches if provided
            if notebook_id and token_data['notebook_id'] != notebook_id:
                return None
            
            # Store in cache for future validation
            self._token_cache[token] = token_data
            
            return token_data
            
        except Exception as e:
            logger.error(f"Error validating collaboration token: {e}")
            return None
    
    def revoke_collaboration_token(self, token):
        """Revoke a collaboration token.
        
        Args:
            token: The token to revoke
        """
        self._token_cache.pop(token, None)
    
    def revoke_user_tokens(self, user_id):
        """Revoke all tokens for a user.
        
        Args:
            user_id: The user ID
        """
        tokens_to_revoke = [
            token for token, data in self._token_cache.items()
            if data['user_id'] == user_id
        ]
        
        for token in tokens_to_revoke:
            self._token_cache.pop(token, None)
    
    def revoke_notebook_tokens(self, notebook_id):
        """Revoke all tokens for a notebook.
        
        Args:
            notebook_id: The notebook ID
        """
        tokens_to_revoke = [
            token for token, data in self._token_cache.items()
            if data['notebook_id'] == notebook_id
        ]
        
        for token in tokens_to_revoke:
            self._token_cache.pop(token, None)
    
    def _get_user_role(self, user_id, notebook_id):
        """Get a user's role for a notebook.
        
        Args:
            user_id: The user ID
            notebook_id: The notebook ID
            
        Returns:
            CollaborationRole: The user's role
        """
        # Check if the user is anonymous
        if user_id.startswith('anonymous-'):
            if not self.config.allow_anonymous:
                return CollaborationRole.VIEWER  # Default to viewer for anonymous users
            return self.config.anonymous_role
        
        # Check if the user has an explicit role for this notebook
        if notebook_id in self._permission_cache and user_id in self._permission_cache[notebook_id]:
            return self._permission_cache[notebook_id][user_id]
        
        # Check if the user has a role from JupyterHub
        jupyterhub_role = self._get_jupyterhub_role(user_id, notebook_id)
        if jupyterhub_role:
            return jupyterhub_role
        
        # Fall back to the default role
        return self.config.default_role
    
    def _get_jupyterhub_role(self, user_id, notebook_id):
        """Get a user's role from JupyterHub scopes.
        
        Args:
            user_id: The user ID
            notebook_id: The notebook ID
            
        Returns:
            Optional[CollaborationRole]: The user's role from JupyterHub
        """
        # This method would integrate with JupyterHub to check user scopes
        # For now, we'll just return None and rely on explicit permissions
        # or the default role
        
        # In a real implementation, this would check JupyterHub scopes against
        # the mapping in self.config.jupyterhub_scope_mapping
        
        # Example implementation:
        # if hasattr(self.handler, 'hub_auth') and self.handler.hub_auth:
        #     # Get user scopes from JupyterHub
        #     scopes = self.handler.hub_auth.get_user_scopes(user_id)
        #     
        #     # Check scopes against mapping
        #     for scope_template, mapped_role in self.config.jupyterhub_scope_mapping.items():
        #         # Replace {notebook_id} with the actual notebook ID
        #         scope = scope_template.replace('{notebook_id}', notebook_id)
        #         
        #         if scope in scopes:
        #             try:
        #                 return CollaborationRole(mapped_role)
        #             except ValueError:
        #                 pass
        
        return None
    
    def _get_user_id(self, handler):
        """Get the user ID from a handler.
        
        Args:
            handler: The request handler
            
        Returns:
            str: The user ID
        """
        # Check if the handler has a current_user attribute
        if hasattr(handler, 'current_user') and handler.current_user:
            if hasattr(handler.current_user, 'name'):
                return handler.current_user.name
            return str(handler.current_user)
        
        # Generate an anonymous ID if no user is authenticated
        return f"anonymous-{uuid.uuid4().hex[:8]}"
    
    def _create_signed_token(self, token_data):
        """Create a signed token from token data.
        
        Args:
            token_data: The token data to encode
            
        Returns:
            str: The signed token
        """
        # Convert token data to JSON
        token_json = json.dumps(token_data)
        
        # Encode token data
        token_bytes = token_json.encode('utf-8')
        token_b64 = base64.urlsafe_b64encode(token_bytes).decode('utf-8')
        
        # Create signature
        signature = hmac.new(
            self.config.token_secret.encode('utf-8'),
            token_b64.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Combine token and signature
        return f"{token_b64}.{signature}"
    
    def _verify_signed_token(self, token):
        """Verify a signed token and extract the token data.
        
        Args:
            token: The signed token
            
        Returns:
            Optional[Dict[str, Any]]: The token data if valid, None otherwise
        """
        try:
            # Split token and signature
            token_parts = token.split('.')
            if len(token_parts) != 2:
                return None
            
            token_b64, signature = token_parts
            
            # Verify signature
            expected_signature = hmac.new(
                self.config.token_secret.encode('utf-8'),
                token_b64.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if signature != expected_signature:
                return None
            
            # Decode token data
            token_bytes = base64.urlsafe_b64decode(token_b64)
            token_json = token_bytes.decode('utf-8')
            token_data = json.loads(token_json)
            
            return token_data
            
        except Exception:
            return None


class WebSocketAuthenticator:
    """Authenticator for WebSocket connections.
    
    This class handles authentication for WebSocket connections used in
    collaborative editing.
    """
    
    def __init__(self, handler, authorizer):
        """Initialize the authenticator.
        
        Args:
            handler: The WebSocket handler
            authorizer: The collaboration authorizer
        """
        self.handler = handler
        self.authorizer = authorizer
    
    def authenticate(self, notebook_id=None):
        """Authenticate a WebSocket connection.
        
        Args:
            notebook_id: Optional notebook ID to validate against
            
        Returns:
            Tuple[bool, str, Dict[str, Any]]: 
                - Whether authentication was successful
                - Error message if authentication failed
                - User information if authentication succeeded
        """
        # Check if the connection is secure (WSS)
        if not self._is_secure_connection():
            return False, "WebSocket connections must use WSS (secure WebSockets)", None
        
        # Try different authentication methods
        
        # 1. Cookie-based authentication
        auth_result = self._authenticate_with_cookie(notebook_id)
        if auth_result[0]:
            return auth_result
        
        # 2. Header-based authentication
        auth_result = self._authenticate_with_header(notebook_id)
        if auth_result[0]:
            return auth_result
        
        # 3. URL parameter authentication
        auth_result = self._authenticate_with_url_param(notebook_id)
        if auth_result[0]:
            return auth_result
        
        # Authentication failed
        return False, "Authentication required", None
    
    def _is_secure_connection(self):
        """Check if the WebSocket connection is secure (WSS).
        
        Returns:
            bool: True if secure, False otherwise
        """
        # Skip check if not required
        if not self.authorizer.config.require_wss:
            return True
        
        # Check if the connection is secure
        return self.handler.request.protocol == 'https' or \
               self.handler.request.headers.get('X-Forwarded-Proto') == 'https'
    
    def _authenticate_with_cookie(self, notebook_id):
        """Authenticate using the session cookie.
        
        Args:
            notebook_id: Optional notebook ID to validate against
            
        Returns:
            Tuple[bool, str, Dict[str, Any]]: Authentication result
        """
        # Check if the handler has a current_user attribute
        if hasattr(self.handler, 'current_user') and self.handler.current_user:
            user_id = self.authorizer._get_user_id(self.handler)
            
            # Create user info
            user_info = {
                'id': user_id,
                'name': user_id
            }
            
            # Add additional user information if available
            if hasattr(self.handler.current_user, 'name'):
                user_info['name'] = self.handler.current_user.name
            if hasattr(self.handler.current_user, 'email'):
                user_info['email'] = self.handler.current_user.email
            if hasattr(self.handler.current_user, 'avatar_url'):
                user_info['avatar_url'] = self.handler.current_user.avatar_url
            
            # Check if the user is authorized for this notebook
            if notebook_id:
                user_id = user_info['id']
                role = self.authorizer._get_user_role(user_id, notebook_id)
                user_info['role'] = role.value
            
            return True, "", user_info
        
        return False, "No valid session cookie found", None
    
    def _authenticate_with_header(self, notebook_id):
        """Authenticate using the Authorization header.
        
        Args:
            notebook_id: Optional notebook ID to validate against
            
        Returns:
            Tuple[bool, str, Dict[str, Any]]: Authentication result
        """
        # Check for Authorization header
        auth_header = self.handler.request.headers.get('Authorization')
        if auth_header and auth_header.startswith('token '):
            token = auth_header[6:]
            return self._validate_token(token, notebook_id)
        
        # Check for Jupyter-Collab-Token header
        collab_token_header = self.handler.request.headers.get('Jupyter-Collab-Token')
        if collab_token_header:
            return self._validate_token(collab_token_header, notebook_id)
        
        return False, "No valid authorization header found", None
    
    def _authenticate_with_url_param(self, notebook_id):
        """Authenticate using URL parameters.
        
        Args:
            notebook_id: Optional notebook ID to validate against
            
        Returns:
            Tuple[bool, str, Dict[str, Any]]: Authentication result
        """
        # Check for token parameter
        token = self.handler.get_argument('token', None)
        if token:
            return self._validate_token(token, notebook_id)
        
        return False, "No token parameter found", None
    
    def _validate_token(self, token, notebook_id):
        """Validate a token and extract user information.
        
        Args:
            token: The token to validate
            notebook_id: Optional notebook ID to validate against
            
        Returns:
            Tuple[bool, str, Dict[str, Any]]: Authentication result
        """
        # Validate the token
        token_data = self.authorizer.validate_collaboration_token(token, notebook_id)
        if not token_data:
            # Try validating as a Jupyter server token
            # This would integrate with the Jupyter server's token authentication
            # For now, we'll just return failure
            return False, "Invalid token", None
        
        # Check if the token is for the requested notebook
        request_notebook_id = self._get_notebook_id_from_request()
        if request_notebook_id and request_notebook_id != notebook_id:
            return False, "Token is not valid for this notebook", None
        
        # Create user info from token data
        user_id = token_data['user_id']
        user_info = {
            'id': user_id,
            'name': user_id,
            'role': token_data.get('role', CollaborationRole.VIEWER.value)
        }
        
        return True, "", user_info
    
    def _get_notebook_id_from_request(self):
        """Extract the notebook ID from the request path.
        
        Returns:
            Optional[str]: The notebook ID or None
        """
        # The path format is expected to be /api/collaboration/{notebook_id}
        path_parts = self.handler.request.path.strip('/').split('/')
        if len(path_parts) >= 3 and path_parts[1] == 'collaboration':
            return path_parts[2]
        return None


class JupyterHubAuthIntegration:
    """Integration with JupyterHub authentication.
    
    This class provides methods for integrating with JupyterHub authentication
    and retrieving user information and scopes.
    """
    
    @staticmethod
    def get_hub_user(handler):
        """Get JupyterHub user information from a handler.
        
        Args:
            handler: The request handler
            
        Returns:
            Optional[Dict[str, Any]]: User information or None
        """
        # Check if running under JupyterHub
        if not hasattr(handler, 'hub_auth') or not handler.hub_auth:
            return None
        
        # Get user information from JupyterHub
        user_model = handler.hub_auth.get_user(handler)
        if not user_model:
            return None
        
        # Extract relevant user information
        user_info = {
            'id': user_model.get('name'),
            'name': user_model.get('name'),
        }
        
        # Add additional user information if available
        if 'admin' in user_model:
            user_info['admin'] = user_model['admin']
        if 'groups' in user_model:
            user_info['groups'] = user_model['groups']
        
        return user_info
    
    @staticmethod
    def get_hub_scopes(handler, user_id):
        """Get JupyterHub scopes for a user.
        
        Args:
            handler: The request handler
            user_id: The user ID
            
        Returns:
            List[str]: List of scopes or empty list
        """
        # Check if running under JupyterHub
        if not hasattr(handler, 'hub_auth') or not handler.hub_auth:
            return []
        
        # This is a placeholder for actual JupyterHub scope retrieval
        # In a real implementation, this would use the JupyterHub API to get scopes
        # For now, we'll just return an empty list
        
        # Example implementation:
        # try:
        #     # Get scopes from JupyterHub API
        #     response = await handler.hub_auth.api_request(
        #         f'/users/{user_id}/scopes',
        #         method='GET'
        #     )
        #     return response.get('scopes', [])
        # except Exception as e:
        #     logger.error(f"Error getting JupyterHub scopes: {e}")
        #     return []
        
        return []
    
    @staticmethod
    def is_running_under_jupyterhub(handler):
        """Check if the application is running under JupyterHub.
        
        Args:
            handler: The request handler
            
        Returns:
            bool: True if running under JupyterHub, False otherwise
        """
        return hasattr(handler, 'hub_auth') and handler.hub_auth is not None


def authenticate_websocket(handler, authorizer=None):
    """Authenticate a WebSocket connection.
    
    Args:
        handler: The WebSocket handler
        authorizer: Optional collaboration authorizer
        
    Returns:
        Tuple[bool, str, Dict[str, Any]]: 
            - Whether authentication was successful
            - Error message if authentication failed
            - User information if authentication succeeded
    """
    authenticator = WebSocketAuthenticator(handler, authorizer or CollaborationAuthorizer())
    return authenticator.authenticate()
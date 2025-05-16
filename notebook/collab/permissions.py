"""Permission system for collaborative notebooks.

This module implements the server-side permission system for collaborative notebooks,
managing access control at both document and cell levels. It defines permission roles
(owner, editor, commenter, viewer), validates user operations against their permissions,
and integrates with JupyterHub for authentication.
"""

from __future__ import annotations

import enum
import functools
import json
import logging
import typing as t
from datetime import datetime
from uuid import uuid4

from jupyter_server.base.handlers import JupyterHandler
from tornado import web
from traitlets.config import Configurable
from traitlets import Instance, Dict, Bool, default

# Type definitions
DocumentId = str  # Unique identifier for a document
CellId = str  # Unique identifier for a cell
UserId = str  # Unique identifier for a user
GroupId = str  # Unique identifier for a group
PermissionId = str  # Unique identifier for a permission entry

# Set up logging
logger = logging.getLogger('notebook.collab.permissions')


class PermissionRole(enum.Enum):
    """Defines the permission roles for collaborative notebooks."""
    OWNER = "owner"  # Full control of the document, including permission assignment and deletion rights
    ADMIN = "admin"  # Can modify content, manage permissions, and control collaborative sessions
    EDITOR = "editor"  # Can modify notebook content and execute cells
    COMMENTER = "commenter"  # Can add comments but cannot modify notebook content
    VIEWER = "viewer"  # Read-only access to the notebook


class PermissionAction(enum.Enum):
    """Defines the permission actions that can be performed on resources."""
    # Document-level actions
    VIEW_DOCUMENT = "view_document"  # View the document
    EDIT_DOCUMENT = "edit_document"  # Edit the document content
    COMMENT_DOCUMENT = "comment_document"  # Add comments to the document
    ADMIN_DOCUMENT = "admin_document"  # Administer the document (manage permissions, etc.)
    
    # Cell-level actions
    VIEW_CELL = "view_cell"  # View a specific cell
    EDIT_CELL = "edit_cell"  # Edit a specific cell
    EXECUTE_CELL = "execute_cell"  # Execute a specific cell
    COMMENT_CELL = "comment_cell"  # Comment on a specific cell
    LOCK_CELL = "lock_cell"  # Lock a cell for exclusive editing
    UNLOCK_CELL = "unlock_cell"  # Unlock a cell
    
    # Comment-related actions
    CREATE_THREAD = "create_thread"  # Create a new comment thread
    REPLY_THREAD = "reply_thread"  # Reply to an existing comment thread
    RESOLVE_THREAD = "resolve_thread"  # Resolve a comment thread
    
    # Version history actions
    VIEW_HISTORY = "view_history"  # View document version history
    RESTORE_VERSION = "restore_version"  # Restore a previous document version
    
    # Session management actions
    CREATE_SESSION = "create_session"  # Create a new collaborative session
    JOIN_SESSION = "join_session"  # Join an existing collaborative session
    MANAGE_SESSION = "manage_session"  # Manage session settings and participants


# Role to action mapping
ROLE_PERMISSIONS = {
    PermissionRole.OWNER: {
        action.value for action in PermissionAction  # Owners can do everything
    },
    PermissionRole.ADMIN: {
        action.value for action in PermissionAction  # Admins can do everything
    } - {
        # Except these actions reserved for owners
        PermissionAction.ADMIN_DOCUMENT.value
    },
    PermissionRole.EDITOR: {
        PermissionAction.VIEW_DOCUMENT.value,
        PermissionAction.EDIT_DOCUMENT.value,
        PermissionAction.COMMENT_DOCUMENT.value,
        PermissionAction.VIEW_CELL.value,
        PermissionAction.EDIT_CELL.value,
        PermissionAction.EXECUTE_CELL.value,
        PermissionAction.COMMENT_CELL.value,
        PermissionAction.LOCK_CELL.value,
        PermissionAction.UNLOCK_CELL.value,
        PermissionAction.CREATE_THREAD.value,
        PermissionAction.REPLY_THREAD.value,
        PermissionAction.RESOLVE_THREAD.value,
        PermissionAction.VIEW_HISTORY.value,
        PermissionAction.RESTORE_VERSION.value,
        PermissionAction.JOIN_SESSION.value,
    },
    PermissionRole.COMMENTER: {
        PermissionAction.VIEW_DOCUMENT.value,
        PermissionAction.COMMENT_DOCUMENT.value,
        PermissionAction.VIEW_CELL.value,
        PermissionAction.COMMENT_CELL.value,
        PermissionAction.CREATE_THREAD.value,
        PermissionAction.REPLY_THREAD.value,
        PermissionAction.RESOLVE_THREAD.value,
        PermissionAction.VIEW_HISTORY.value,
        PermissionAction.JOIN_SESSION.value,
    },
    PermissionRole.VIEWER: {
        PermissionAction.VIEW_DOCUMENT.value,
        PermissionAction.VIEW_CELL.value,
        PermissionAction.VIEW_HISTORY.value,
        PermissionAction.JOIN_SESSION.value,
    }
}


class NotebookPermissionManager(Configurable):
    """Manages permissions for collaborative notebooks.
    
    This class provides methods for checking, granting, and revoking permissions
    for collaborative notebooks at both document and cell levels. It integrates with
    JupyterHub for authentication and maintains a permission model that supports
    role-based access control.
    """
    
    # Configuration parameters
    persistence_manager = Instance(
        'notebook.collab.persistence.PersistenceManager',
        allow_none=True,
        help="The persistence manager for storing permissions"
    ).tag(config=True)
    
    enable_jupyterhub_integration = Bool(
        default_value=True,
        help="Whether to integrate with JupyterHub for authentication"
    ).tag(config=True)
    
    default_permission_role = Instance(
        PermissionRole,
        default_value=PermissionRole.VIEWER,
        help="Default permission role for users without explicit permissions"
    ).tag(config=True)
    
    owner_permission_role = Instance(
        PermissionRole,
        default_value=PermissionRole.OWNER,
        help="Permission role for document owners"
    ).tag(config=True)
    
    # In-memory cache of permissions
    _permission_cache = Dict(help="Cache of permissions").tag(config=False)
    
    def __init__(self, **kwargs):
        """Initialize the permission manager.
        
        Args:
            **kwargs: Configuration parameters
        """
        super().__init__(**kwargs)
        self._permission_cache = {}
        self._jupyterhub_groups_cache = {}
        self._last_cache_update = {}
    
    def get_user_role(self, document_id: DocumentId, user_identity: t.Dict[str, t.Any]) -> PermissionRole:
        """Get the role of a user for a document.
        
        Args:
            document_id: The document ID to check
            user_identity: User identity information (from current_user)
            
        Returns:
            The user's permission role for the document
        """
        user_id = user_identity.get('name', '')
        if not user_id:
            return self.default_permission_role
        
        # Check if document exists in persistence manager
        if self.persistence_manager:
            # Get collaboration sessions for this document
            sessions = self.persistence_manager.get_collaboration_sessions_for_document(document_id)
            
            # Check if user is the owner of any session
            for session in sessions:
                if session.get('owner_id') == user_id:
                    return self.owner_permission_role
            
            # Get user permissions from persistence manager
            permissions = self.persistence_manager.get_permissions(
                sessions[0]['session_id'] if sessions else None,
                resource_id=document_id,
                resource_type='document',
                user_id=user_id
            )
            
            if permissions:
                # Get the highest permission role
                highest_role = self.default_permission_role
                for perm in permissions:
                    perm_type = perm.get('permission_type')
                    try:
                        role = PermissionRole(perm_type)
                        if list(PermissionRole).index(role) < list(PermissionRole).index(highest_role):
                            highest_role = role
                    except (ValueError, KeyError):
                        logger.warning(f"Unknown permission type: {perm_type}")
                
                return highest_role
            
            # Check group permissions if no user-specific permissions
            if self.enable_jupyterhub_integration:
                user_groups = self._get_user_groups(user_identity)
                for group_id in user_groups:
                    group_permissions = self.persistence_manager.get_permissions(
                        sessions[0]['session_id'] if sessions else None,
                        resource_id=document_id,
                        resource_type='document',
                        group_id=group_id
                    )
                    
                    for perm in group_permissions:
                        perm_type = perm.get('permission_type')
                        try:
                            role = PermissionRole(perm_type)
                            if list(PermissionRole).index(role) < list(PermissionRole).index(highest_role):
                                highest_role = role
                        except (ValueError, KeyError):
                            logger.warning(f"Unknown permission type: {perm_type}")
                
                return highest_role
        
        # If no permissions found or no persistence manager, return default role
        return self.default_permission_role
    
    def has_permission(self, document_id: DocumentId, user_identity: t.Dict[str, t.Any], 
                      action: t.Union[PermissionAction, str]) -> bool:
        """Check if a user has permission to perform an action on a document.
        
        Args:
            document_id: The document ID to check
            user_identity: User identity information (from current_user)
            action: The action to check permission for
            
        Returns:
            True if the user has permission, False otherwise
        """
        # Convert string action to enum if needed
        if isinstance(action, str):
            try:
                action = PermissionAction(action)
            except ValueError:
                logger.warning(f"Unknown permission action: {action}")
                return False
        
        # Get user's role for this document
        role = self.get_user_role(document_id, user_identity)
        
        # Check if the action is allowed for this role
        return action.value in ROLE_PERMISSIONS.get(role, set())
    
    def has_cell_permission(self, document_id: DocumentId, cell_id: CellId, 
                          user_identity: t.Dict[str, t.Any], 
                          action: t.Union[PermissionAction, str]) -> bool:
        """Check if a user has permission to perform an action on a cell.
        
        Args:
            document_id: The document ID containing the cell
            cell_id: The cell ID to check
            user_identity: User identity information (from current_user)
            action: The action to check permission for
            
        Returns:
            True if the user has permission, False otherwise
        """
        # Convert string action to enum if needed
        if isinstance(action, str):
            try:
                action = PermissionAction(action)
            except ValueError:
                logger.warning(f"Unknown permission action: {action}")
                return False
        
        user_id = user_identity.get('name', '')
        if not user_id:
            return False
        
        # First check document-level permissions
        # If user doesn't have document-level permission, they can't have cell-level permission
        document_action = None
        if action == PermissionAction.VIEW_CELL:
            document_action = PermissionAction.VIEW_DOCUMENT
        elif action == PermissionAction.EDIT_CELL:
            document_action = PermissionAction.EDIT_DOCUMENT
        elif action == PermissionAction.EXECUTE_CELL:
            document_action = PermissionAction.EDIT_DOCUMENT
        elif action == PermissionAction.COMMENT_CELL:
            document_action = PermissionAction.COMMENT_DOCUMENT
        elif action == PermissionAction.LOCK_CELL:
            document_action = PermissionAction.EDIT_DOCUMENT
        elif action == PermissionAction.UNLOCK_CELL:
            document_action = PermissionAction.EDIT_DOCUMENT
        
        if document_action and not self.has_permission(document_id, user_identity, document_action):
            return False
        
        # Check for cell-specific permissions if persistence manager is available
        if self.persistence_manager:
            # Get collaboration sessions for this document
            sessions = self.persistence_manager.get_collaboration_sessions_for_document(document_id)
            if not sessions:
                return False
            
            session_id = sessions[0]['session_id']
            
            # Check if there are any cell-specific permissions
            cell_permissions = self.persistence_manager.get_permissions(
                session_id,
                resource_id=cell_id,
                resource_type='cell',
                user_id=user_id
            )
            
            if cell_permissions:
                # Check if any permission allows this action
                for perm in cell_permissions:
                    perm_type = perm.get('permission_type')
                    try:
                        role = PermissionRole(perm_type)
                        if action.value in ROLE_PERMISSIONS.get(role, set()):
                            return True
                    except (ValueError, KeyError):
                        logger.warning(f"Unknown permission type: {perm_type}")
                
                # If cell-specific permissions exist but none allow this action, deny
                return False
            
            # Check if cell is locked by someone else
            if action in [PermissionAction.EDIT_CELL, PermissionAction.EXECUTE_CELL]:
                locks = self.persistence_manager.get_cell_locks(session_id)
                for lock in locks:
                    if lock.get('cell_id') == cell_id and lock.get('user_id') != user_id:
                        # Cell is locked by someone else
                        return False
        
        # If no cell-specific permissions or no persistence manager,
        # fall back to document-level permissions
        return self.has_permission(document_id, user_identity, action)
    
    def grant_permission(self, document_id: DocumentId, role: PermissionRole, 
                        user_id: t.Optional[UserId] = None, 
                        group_id: t.Optional[GroupId] = None, 
                        granted_by: t.Optional[UserId] = None) -> PermissionId:
        """Grant a permission role to a user or group for a document.
        
        Args:
            document_id: The document ID to grant permission for
            role: The permission role to grant
            user_id: The user ID to grant permission to (required if group_id is None)
            group_id: The group ID to grant permission to (required if user_id is None)
            granted_by: The user ID who granted the permission
            
        Returns:
            The permission ID of the created permission
            
        Raises:
            ValueError: If neither user_id nor group_id is provided
            RuntimeError: If persistence manager is not available
        """
        if not self.persistence_manager:
            raise RuntimeError("Persistence manager not available for permission storage")
        
        if user_id is None and group_id is None:
            raise ValueError("Either user_id or group_id must be provided")
        
        # Get collaboration sessions for this document
        sessions = self.persistence_manager.get_collaboration_sessions_for_document(document_id)
        if not sessions:
            # Create a new session if none exists
            session_id = self.persistence_manager.create_collaboration_session(
                document_id, granted_by or "system"
            )
        else:
            session_id = sessions[0]['session_id']
        
        # Grant permission
        permission_id = self.persistence_manager.set_permission(
            session_id,
            resource_id=document_id,
            resource_type='document',
            permission_type=role.value,
            user_id=user_id,
            group_id=group_id,
            granted_by=granted_by or "system"
        )
        
        # Clear cache for this document
        if document_id in self._permission_cache:
            del self._permission_cache[document_id]
        
        return permission_id
    
    def grant_cell_permission(self, document_id: DocumentId, cell_id: CellId, 
                            role: PermissionRole, user_id: UserId, 
                            granted_by: t.Optional[UserId] = None) -> PermissionId:
        """Grant a permission role to a user for a specific cell.
        
        Args:
            document_id: The document ID containing the cell
            cell_id: The cell ID to grant permission for
            role: The permission role to grant
            user_id: The user ID to grant permission to
            granted_by: The user ID who granted the permission
            
        Returns:
            The permission ID of the created permission
            
        Raises:
            RuntimeError: If persistence manager is not available
        """
        if not self.persistence_manager:
            raise RuntimeError("Persistence manager not available for permission storage")
        
        # Get collaboration sessions for this document
        sessions = self.persistence_manager.get_collaboration_sessions_for_document(document_id)
        if not sessions:
            raise ValueError(f"No collaboration session found for document {document_id}")
        
        session_id = sessions[0]['session_id']
        
        # Grant permission
        permission_id = self.persistence_manager.set_permission(
            session_id,
            resource_id=cell_id,
            resource_type='cell',
            permission_type=role.value,
            user_id=user_id,
            granted_by=granted_by or "system"
        )
        
        # Clear cache for this document
        if document_id in self._permission_cache:
            del self._permission_cache[document_id]
        
        return permission_id
    
    def revoke_permission(self, permission_id: PermissionId) -> bool:
        """Revoke a permission.
        
        Args:
            permission_id: The permission ID to revoke
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            RuntimeError: If persistence manager is not available
        """
        if not self.persistence_manager:
            raise RuntimeError("Persistence manager not available for permission storage")
        
        # Revoke permission
        success = self.persistence_manager.remove_permission(permission_id)
        
        # Clear entire cache since we don't know which document this was for
        self._permission_cache = {}
        
        return success
    
    def get_document_permissions(self, document_id: DocumentId) -> t.List[t.Dict[str, t.Any]]:
        """Get all permissions for a document.
        
        Args:
            document_id: The document ID to get permissions for
            
        Returns:
            A list of permission dictionaries
            
        Raises:
            RuntimeError: If persistence manager is not available
        """
        if not self.persistence_manager:
            raise RuntimeError("Persistence manager not available for permission storage")
        
        # Get collaboration sessions for this document
        sessions = self.persistence_manager.get_collaboration_sessions_for_document(document_id)
        if not sessions:
            return []
        
        session_id = sessions[0]['session_id']
        
        # Get permissions
        return self.persistence_manager.get_permissions(
            session_id,
            resource_id=document_id,
            resource_type='document'
        )
    
    def get_cell_permissions(self, document_id: DocumentId, cell_id: CellId) -> t.List[t.Dict[str, t.Any]]:
        """Get all permissions for a cell.
        
        Args:
            document_id: The document ID containing the cell
            cell_id: The cell ID to get permissions for
            
        Returns:
            A list of permission dictionaries
            
        Raises:
            RuntimeError: If persistence manager is not available
        """
        if not self.persistence_manager:
            raise RuntimeError("Persistence manager not available for permission storage")
        
        # Get collaboration sessions for this document
        sessions = self.persistence_manager.get_collaboration_sessions_for_document(document_id)
        if not sessions:
            return []
        
        session_id = sessions[0]['session_id']
        
        # Get permissions
        return self.persistence_manager.get_permissions(
            session_id,
            resource_id=cell_id,
            resource_type='cell'
        )
    
    def _get_user_groups(self, user_identity: t.Dict[str, t.Any]) -> t.List[str]:
        """Get the groups a user belongs to from JupyterHub.
        
        Args:
            user_identity: User identity information (from current_user)
            
        Returns:
            A list of group IDs the user belongs to
        """
        if not self.enable_jupyterhub_integration:
            return []
        
        user_id = user_identity.get('name', '')
        if not user_id:
            return []
        
        # Check cache first
        if user_id in self._jupyterhub_groups_cache:
            return self._jupyterhub_groups_cache[user_id]
        
        # In a real implementation, this would query JupyterHub API
        # For now, we'll just return an empty list
        groups = []
        
        # Cache the result
        self._jupyterhub_groups_cache[user_id] = groups
        return groups
    
    def get_jupyterhub_user_info(self, user_identity: t.Dict[str, t.Any]) -> t.Dict[str, t.Any]:
        """Get additional user information from JupyterHub.
        
        Args:
            user_identity: User identity information (from current_user)
            
        Returns:
            A dictionary with additional user information
        """
        if not self.enable_jupyterhub_integration:
            return {}
        
        user_id = user_identity.get('name', '')
        if not user_id:
            return {}
        
        # In a real implementation, this would query JupyterHub API
        # For now, we'll just return basic information
        return {
            'name': user_id,
            'admin': False,
            'groups': self._get_user_groups(user_identity)
        }
    
    def clear_cache(self):
        """Clear the permission cache."""
        self._permission_cache = {}
        self._jupyterhub_groups_cache = {}
        self._last_cache_update = {}


def collaborative_authorized(action: t.Union[PermissionAction, str]):
    """Decorator for checking permission to perform an action in collaborative mode.
    
    Args:
        action: The action to check permission for
        
    Returns:
        A decorator function that checks permission before executing the handler method
    """
    def decorator(method):
        @functools.wraps(method)
        async def wrapper(self, *args, **kwargs):
            # Skip permission check if handler doesn't have permission_manager
            if not hasattr(self, 'permission_manager') or not self.permission_manager:
                return await method(self, *args, **kwargs)
            
            # Get document_id from path arguments or query parameters
            document_id = None
            if hasattr(self, 'path_kwargs') and 'document_id' in self.path_kwargs:
                document_id = self.path_kwargs['document_id']
            elif hasattr(self, 'path_kwargs') and 'session_id' in self.path_kwargs:
                document_id = self.path_kwargs['session_id']  # In some handlers, session_id is document_id
            elif self.get_argument('document_id', None):
                document_id = self.get_argument('document_id')
            
            if not document_id:
                raise web.HTTPError(400, "Missing document_id parameter")
            
            # Check permission
            if not self.permission_manager.has_permission(document_id, self.current_user, action):
                raise web.HTTPError(403, f"Permission denied: {action}")
            
            return await method(self, *args, **kwargs)
        return wrapper
    return decorator


class PermissionHandler(JupyterHandler):
    """HTTP handler for permission management.
    
    This handler provides REST API endpoints for managing permissions,
    allowing clients to grant, revoke, and query permissions using
    standard HTTP methods.
    """
    
    def initialize(self, permission_manager=None):
        """Initialize the handler.
        
        Args:
            permission_manager: The permission manager instance
        """
        self.logger = logging.getLogger(__name__)
        self.permission_manager = permission_manager
    
    @web.authenticated
    @collaborative_authorized(PermissionAction.ADMIN_DOCUMENT)
    async def get(self, document_id, user_id=None):
        """Handle GET requests to retrieve permissions.
        
        Args:
            document_id: The document ID from the URL
            user_id: The user ID from the URL (optional)
        """
        if not self.permission_manager:
            raise web.HTTPError(500, "Permission manager not available")
        
        try:
            if user_id:
                # Get permissions for specific user
                permissions = [p for p in self.permission_manager.get_document_permissions(document_id)
                              if p.get('user_id') == user_id]
            else:
                # Get all permissions for document
                permissions = self.permission_manager.get_document_permissions(document_id)
            
            self.write(json.dumps(permissions))
        except Exception as e:
            self.logger.exception(f"Error retrieving permissions: {e}")
            raise web.HTTPError(500, f"Error retrieving permissions: {str(e)}")
    
    @web.authenticated
    @collaborative_authorized(PermissionAction.ADMIN_DOCUMENT)
    async def post(self, document_id):
        """Handle POST requests to grant permissions.
        
        Args:
            document_id: The document ID from the URL
        """
        if not self.permission_manager:
            raise web.HTTPError(500, "Permission manager not available")
        
        # Get user ID from current user
        granted_by = self.current_user.get('name', None)
        if not granted_by:
            raise web.HTTPError(401, "User not authenticated")
        
        # Parse request body
        try:
            data = json.loads(self.request.body)
        except json.JSONDecodeError:
            raise web.HTTPError(400, "Invalid JSON in request body")
        
        user_id = data.get('user_id')
        group_id = data.get('group_id')
        role_name = data.get('role')
        
        if not role_name:
            raise web.HTTPError(400, "Missing role in request")
        
        if not user_id and not group_id:
            raise web.HTTPError(400, "Either user_id or group_id must be provided")
        
        try:
            role = PermissionRole(role_name)
        except ValueError:
            raise web.HTTPError(400, f"Invalid role: {role_name}")
        
        try:
            permission_id = self.permission_manager.grant_permission(
                document_id, role, user_id, group_id, granted_by
            )
            
            self.set_status(201)  # Created
            self.write(json.dumps({'id': permission_id}))
        except Exception as e:
            self.logger.exception(f"Error granting permission: {e}")
            raise web.HTTPError(500, f"Error granting permission: {str(e)}")
    
    @web.authenticated
    @collaborative_authorized(PermissionAction.ADMIN_DOCUMENT)
    async def delete(self, document_id, permission_id):
        """Handle DELETE requests to revoke permissions.
        
        Args:
            document_id: The document ID from the URL
            permission_id: The permission ID from the URL
        """
        if not self.permission_manager:
            raise web.HTTPError(500, "Permission manager not available")
        
        try:
            success = self.permission_manager.revoke_permission(permission_id)
            
            if success:
                self.set_status(204)  # No content
            else:
                raise web.HTTPError(404, f"Permission {permission_id} not found")
        except Exception as e:
            self.logger.exception(f"Error revoking permission: {e}")
            raise web.HTTPError(500, f"Error revoking permission: {str(e)}")


class CellPermissionHandler(JupyterHandler):
    """HTTP handler for cell-level permission management.
    
    This handler provides REST API endpoints for managing cell-level permissions,
    allowing clients to grant, revoke, and query cell permissions using
    standard HTTP methods.
    """
    
    def initialize(self, permission_manager=None):
        """Initialize the handler.
        
        Args:
            permission_manager: The permission manager instance
        """
        self.logger = logging.getLogger(__name__)
        self.permission_manager = permission_manager
    
    @web.authenticated
    @collaborative_authorized(PermissionAction.ADMIN_DOCUMENT)
    async def get(self, document_id, cell_id):
        """Handle GET requests to retrieve cell permissions.
        
        Args:
            document_id: The document ID from the URL
            cell_id: The cell ID from the URL
        """
        if not self.permission_manager:
            raise web.HTTPError(500, "Permission manager not available")
        
        try:
            permissions = self.permission_manager.get_cell_permissions(document_id, cell_id)
            self.write(json.dumps(permissions))
        except Exception as e:
            self.logger.exception(f"Error retrieving cell permissions: {e}")
            raise web.HTTPError(500, f"Error retrieving cell permissions: {str(e)}")
    
    @web.authenticated
    @collaborative_authorized(PermissionAction.ADMIN_DOCUMENT)
    async def post(self, document_id, cell_id):
        """Handle POST requests to grant cell permissions.
        
        Args:
            document_id: The document ID from the URL
            cell_id: The cell ID from the URL
        """
        if not self.permission_manager:
            raise web.HTTPError(500, "Permission manager not available")
        
        # Get user ID from current user
        granted_by = self.current_user.get('name', None)
        if not granted_by:
            raise web.HTTPError(401, "User not authenticated")
        
        # Parse request body
        try:
            data = json.loads(self.request.body)
        except json.JSONDecodeError:
            raise web.HTTPError(400, "Invalid JSON in request body")
        
        user_id = data.get('user_id')
        role_name = data.get('role')
        
        if not user_id or not role_name:
            raise web.HTTPError(400, "Missing user_id or role in request")
        
        try:
            role = PermissionRole(role_name)
        except ValueError:
            raise web.HTTPError(400, f"Invalid role: {role_name}")
        
        try:
            permission_id = self.permission_manager.grant_cell_permission(
                document_id, cell_id, role, user_id, granted_by
            )
            
            self.set_status(201)  # Created
            self.write(json.dumps({'id': permission_id}))
        except Exception as e:
            self.logger.exception(f"Error granting cell permission: {e}")
            raise web.HTTPError(500, f"Error granting cell permission: {str(e)}")
    
    @web.authenticated
    @collaborative_authorized(PermissionAction.ADMIN_DOCUMENT)
    async def delete(self, document_id, cell_id, permission_id):
        """Handle DELETE requests to revoke cell permissions.
        
        Args:
            document_id: The document ID from the URL
            cell_id: The cell ID from the URL
            permission_id: The permission ID from the URL
        """
        if not self.permission_manager:
            raise web.HTTPError(500, "Permission manager not available")
        
        try:
            success = self.permission_manager.revoke_permission(permission_id)
            
            if success:
                self.set_status(204)  # No content
            else:
                raise web.HTTPError(404, f"Permission {permission_id} not found")
        except Exception as e:
            self.logger.exception(f"Error revoking cell permission: {e}")
            raise web.HTTPError(500, f"Error revoking cell permission: {str(e)}")


def setup_handlers(web_app, permission_manager=None):
    """Set up the permission handlers for the Jupyter web application.
    
    Args:
        web_app: The Jupyter web application
        permission_manager: The permission manager instance
    """
    host_pattern = ".*$"
    
    permission_handlers = [
        # Document-level permissions
        (r"/api/collaboration/documents/([^/]+)/permissions", PermissionHandler, {
            'permission_manager': permission_manager
        }),
        (r"/api/collaboration/documents/([^/]+)/permissions/users/([^/]+)", PermissionHandler, {
            'permission_manager': permission_manager
        }),
        (r"/api/collaboration/documents/([^/]+)/permissions/([^/]+)", PermissionHandler, {
            'permission_manager': permission_manager
        }),
        
        # Cell-level permissions
        (r"/api/collaboration/documents/([^/]+)/cells/([^/]+)/permissions", CellPermissionHandler, {
            'permission_manager': permission_manager
        }),
        (r"/api/collaboration/documents/([^/]+)/cells/([^/]+)/permissions/([^/]+)", CellPermissionHandler, {
            'permission_manager': permission_manager
        }),
    ]
    
    web_app.add_handlers(host_pattern, permission_handlers)
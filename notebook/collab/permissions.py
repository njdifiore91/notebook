"""Permission system for collaborative notebooks.

This module implements the server-side permission system for collaborative notebooks,
managing access control at both document and cell levels. It defines permission roles
(owner, editor, commenter, viewer), validates user operations against their permissions,
and integrates with JupyterHub for authentication.
"""

from __future__ import annotations

import enum
import json
import logging
import typing as t
from datetime import datetime
from functools import wraps

from jupyter_server.auth import Authorizer
from jupyter_server.base.handlers import JupyterHandler
from tornado import web

# Type definitions
UserIdentity = t.Dict[str, t.Any]  # User identity information
DocumentId = str  # Unique identifier for a document
CellId = str  # Unique identifier for a cell
PermissionRecord = t.Dict[str, t.Any]  # Permission record structure


class PermissionRole(enum.Enum):
    """Defines the permission roles for collaborative notebooks.
    
    Roles are hierarchical, with higher-level roles inheriting all permissions
    from lower-level roles.
    """
    OWNER = 100  # Full control, including permission management and deletion
    ADMIN = 80   # Can modify content, manage permissions, control sessions
    EDITOR = 60  # Can modify notebook content and execute cells
    COMMENTER = 40  # Can add comments but cannot modify notebook content
    VIEWER = 20  # Read-only access to the notebook
    NONE = 0     # No access to the notebook


class CellPermissionRole(enum.Enum):
    """Defines the permission roles for individual cells in collaborative notebooks.
    
    Cell-level permissions can override document-level permissions for greater specificity.
    """
    CELL_OWNER = 100  # Has primary control over an individual cell
    CELL_EDITOR = 80  # Can modify the specific cell's content
    CELL_EXECUTOR = 60  # Can run the cell but not modify its content
    CELL_COMMENTER = 40  # Can attach comments to the cell
    CELL_VIEWER = 20  # Can only view the cell content and output
    CELL_NONE = 0  # No access to the cell


class PermissionAction(enum.Enum):
    """Defines the actions that can be performed on collaborative notebooks.
    
    These actions are used to check if a user has permission to perform a specific operation.
    """
    # Document-level actions
    VIEW_DOCUMENT = "view_document"  # View the notebook content
    EDIT_DOCUMENT = "edit_document"  # Modify the notebook content
    EXECUTE_DOCUMENT = "execute_document"  # Execute cells in the notebook
    COMMENT_DOCUMENT = "comment_document"  # Add comments to the notebook
    MANAGE_PERMISSIONS = "manage_permissions"  # Modify permission settings
    DELETE_DOCUMENT = "delete_document"  # Delete the notebook
    SHARE_DOCUMENT = "share_document"  # Share the notebook with others
    
    # Cell-level actions
    VIEW_CELL = "view_cell"  # View a specific cell
    EDIT_CELL = "edit_cell"  # Modify a specific cell
    EXECUTE_CELL = "execute_cell"  # Execute a specific cell
    COMMENT_CELL = "comment_cell"  # Add comments to a specific cell
    LOCK_CELL = "lock_cell"  # Acquire a lock on a specific cell
    UNLOCK_CELL = "unlock_cell"  # Release a lock on a specific cell
    OVERRIDE_LOCK = "override_lock"  # Force-release another user's lock
    
    # Collaboration session actions
    CREATE_SESSION = "create_session"  # Create a new collaborative session
    JOIN_SESSION = "join_session"  # Join an existing collaborative session
    CONFIGURE_SESSION = "configure_session"  # Modify session settings
    END_SESSION = "end_session"  # Terminate a collaborative session
    MANAGE_PARTICIPANTS = "manage_participants"  # Control who can join a session
    
    # Comment thread actions
    CREATE_THREAD = "create_thread"  # Start a new comment thread
    REPLY_THREAD = "reply_thread"  # Add comments to an existing thread
    EDIT_COMMENT = "edit_comment"  # Modify one's own comment
    DELETE_COMMENT = "delete_comment"  # Remove comments
    RESOLVE_THREAD = "resolve_thread"  # Mark a thread as resolved or reopen it
    
    # Version history actions
    VIEW_HISTORY = "view_history"  # Access to browse version history
    COMPARE_VERSIONS = "compare_versions"  # Diff between document versions
    RESTORE_VERSION = "restore_version"  # Revert to a previous version
    CREATE_SNAPSHOT = "create_snapshot"  # Manually create a version checkpoint
    MANAGE_HISTORY = "manage_history"  # Configure history settings, delete versions


class PermissionError(Exception):
    """Exception raised for permission-related errors."""
    pass


class NotebookPermissionManager:
    """Manages permissions for collaborative notebooks.
    
    This class provides methods for checking, granting, and revoking permissions
    at both document and cell levels. It integrates with JupyterHub for user
    authentication and maintains permission records in the collaboration database.
    """
    
    def __init__(self, persistence_manager=None):
        """Initialize the permission manager.
        
        Args:
            persistence_manager: The persistence manager for storing permission records.
                                If None, permissions will not be persisted.
        """
        self.logger = logging.getLogger(__name__)
        self._persistence_manager = persistence_manager
        self._permission_cache = {}  # In-memory cache of permission records
        self._default_permissions = {
            PermissionRole.OWNER.name: self._get_role_permissions(PermissionRole.OWNER),
            PermissionRole.ADMIN.name: self._get_role_permissions(PermissionRole.ADMIN),
            PermissionRole.EDITOR.name: self._get_role_permissions(PermissionRole.EDITOR),
            PermissionRole.COMMENTER.name: self._get_role_permissions(PermissionRole.COMMENTER),
            PermissionRole.VIEWER.name: self._get_role_permissions(PermissionRole.VIEWER),
            PermissionRole.NONE.name: self._get_role_permissions(PermissionRole.NONE),
        }
        
    def _get_role_permissions(self, role: PermissionRole) -> t.Dict[str, bool]:
        """Get the permissions for a specific role.
        
        Args:
            role: The permission role.
            
        Returns:
            A dictionary mapping permission actions to boolean values.
        """
        permissions = {action.value: False for action in PermissionAction}
        
        # Define permissions based on role
        if role == PermissionRole.NONE:
            # No permissions
            pass
        
        elif role == PermissionRole.VIEWER:
            # Viewer permissions
            for action in [
                PermissionAction.VIEW_DOCUMENT,
                PermissionAction.VIEW_CELL,
                PermissionAction.VIEW_HISTORY,
                PermissionAction.COMPARE_VERSIONS,
                PermissionAction.JOIN_SESSION,
            ]:
                permissions[action.value] = True
        
        elif role == PermissionRole.COMMENTER:
            # Commenter permissions (includes Viewer permissions)
            permissions.update(self._get_role_permissions(PermissionRole.VIEWER))
            for action in [
                PermissionAction.COMMENT_DOCUMENT,
                PermissionAction.COMMENT_CELL,
                PermissionAction.CREATE_THREAD,
                PermissionAction.REPLY_THREAD,
                PermissionAction.EDIT_COMMENT,  # Can edit own comments
                PermissionAction.DELETE_COMMENT,  # Can delete own comments
                PermissionAction.RESOLVE_THREAD,  # Can resolve own threads
            ]:
                permissions[action.value] = True
        
        elif role == PermissionRole.EDITOR:
            # Editor permissions (includes Commenter permissions)
            permissions.update(self._get_role_permissions(PermissionRole.COMMENTER))
            for action in [
                PermissionAction.EDIT_DOCUMENT,
                PermissionAction.EDIT_CELL,
                PermissionAction.EXECUTE_DOCUMENT,
                PermissionAction.EXECUTE_CELL,
                PermissionAction.LOCK_CELL,
                PermissionAction.UNLOCK_CELL,  # Can unlock own locks
                PermissionAction.RESTORE_VERSION,
                PermissionAction.CREATE_SNAPSHOT,
            ]:
                permissions[action.value] = True
        
        elif role == PermissionRole.ADMIN:
            # Admin permissions (includes Editor permissions)
            permissions.update(self._get_role_permissions(PermissionRole.EDITOR))
            for action in [
                PermissionAction.MANAGE_PERMISSIONS,
                PermissionAction.SHARE_DOCUMENT,
                PermissionAction.OVERRIDE_LOCK,
                PermissionAction.CONFIGURE_SESSION,
                PermissionAction.END_SESSION,
                PermissionAction.MANAGE_PARTICIPANTS,
                PermissionAction.MANAGE_HISTORY,
            ]:
                permissions[action.value] = True
        
        elif role == PermissionRole.OWNER:
            # Owner permissions (includes Admin permissions)
            permissions.update(self._get_role_permissions(PermissionRole.ADMIN))
            for action in [
                PermissionAction.DELETE_DOCUMENT,
                PermissionAction.CREATE_SESSION,
            ]:
                permissions[action.value] = True
        
        return permissions
    
    def _get_cell_role_permissions(self, role: CellPermissionRole) -> t.Dict[str, bool]:
        """Get the permissions for a specific cell role.
        
        Args:
            role: The cell permission role.
            
        Returns:
            A dictionary mapping permission actions to boolean values.
        """
        permissions = {action.value: False for action in PermissionAction}
        
        # Define permissions based on cell role
        if role == CellPermissionRole.CELL_NONE:
            # No permissions
            pass
        
        elif role == CellPermissionRole.CELL_VIEWER:
            # Cell viewer permissions
            for action in [
                PermissionAction.VIEW_CELL,
            ]:
                permissions[action.value] = True
        
        elif role == CellPermissionRole.CELL_COMMENTER:
            # Cell commenter permissions (includes Cell Viewer permissions)
            permissions.update(self._get_cell_role_permissions(CellPermissionRole.CELL_VIEWER))
            for action in [
                PermissionAction.COMMENT_CELL,
                PermissionAction.CREATE_THREAD,
                PermissionAction.REPLY_THREAD,
                PermissionAction.EDIT_COMMENT,  # Can edit own comments
                PermissionAction.DELETE_COMMENT,  # Can delete own comments
                PermissionAction.RESOLVE_THREAD,  # Can resolve own threads
            ]:
                permissions[action.value] = True
        
        elif role == CellPermissionRole.CELL_EXECUTOR:
            # Cell executor permissions (includes Cell Commenter permissions)
            permissions.update(self._get_cell_role_permissions(CellPermissionRole.CELL_COMMENTER))
            for action in [
                PermissionAction.EXECUTE_CELL,
            ]:
                permissions[action.value] = True
        
        elif role == CellPermissionRole.CELL_EDITOR:
            # Cell editor permissions (includes Cell Executor permissions)
            permissions.update(self._get_cell_role_permissions(CellPermissionRole.CELL_EXECUTOR))
            for action in [
                PermissionAction.EDIT_CELL,
                PermissionAction.LOCK_CELL,
                PermissionAction.UNLOCK_CELL,  # Can unlock own locks
            ]:
                permissions[action.value] = True
        
        elif role == CellPermissionRole.CELL_OWNER:
            # Cell owner permissions (includes Cell Editor permissions)
            permissions.update(self._get_cell_role_permissions(CellPermissionRole.CELL_EDITOR))
            for action in [
                PermissionAction.OVERRIDE_LOCK,
            ]:
                permissions[action.value] = True
        
        return permissions
    
    def get_document_permissions(self, document_id: DocumentId) -> t.Dict[str, t.Dict[str, t.Any]]:
        """Get all permission records for a document.
        
        Args:
            document_id: The unique identifier for the document.
            
        Returns:
            A dictionary mapping user IDs/names to their permission records.
        """
        if not self._persistence_manager:
            self.logger.warning("No persistence manager available for permission retrieval")
            return {}
        
        # Try to get from cache first
        if document_id in self._permission_cache:
            return self._permission_cache[document_id]
        
        # Get from persistence manager
        try:
            permissions = self._persistence_manager.get_document_permissions(document_id)
            self._permission_cache[document_id] = permissions
            return permissions
        except Exception as e:
            self.logger.error(f"Error retrieving permissions for document {document_id}: {e}")
            return {}
    
    def get_cell_permissions(self, document_id: DocumentId, cell_id: CellId) -> t.Dict[str, t.Dict[str, t.Any]]:
        """Get all permission records for a specific cell.
        
        Args:
            document_id: The unique identifier for the document.
            cell_id: The unique identifier for the cell.
            
        Returns:
            A dictionary mapping user IDs/names to their permission records.
        """
        if not self._persistence_manager:
            self.logger.warning("No persistence manager available for permission retrieval")
            return {}
        
        # Get from persistence manager
        try:
            return self._persistence_manager.get_cell_permissions(document_id, cell_id)
        except Exception as e:
            self.logger.error(f"Error retrieving permissions for cell {cell_id} in document {document_id}: {e}")
            return {}
    
    def get_user_role(self, document_id: DocumentId, user_identity: UserIdentity) -> PermissionRole:
        """Get the role of a user for a document.
        
        Args:
            document_id: The unique identifier for the document.
            user_identity: The user identity information.
            
        Returns:
            The permission role of the user for the document.
        """
        user_id = self._get_user_id(user_identity)
        permissions = self.get_document_permissions(document_id)
        
        if user_id in permissions:
            role_name = permissions[user_id].get("role", PermissionRole.NONE.name)
            try:
                return PermissionRole[role_name]
            except KeyError:
                self.logger.error(f"Invalid role name: {role_name}")
                return PermissionRole.NONE
        
        # Check if the user is the owner based on JupyterHub information
        if self._is_document_owner(document_id, user_identity):
            return PermissionRole.OWNER
        
        # Default to NONE if no permission record exists
        return PermissionRole.NONE
    
    def get_cell_user_role(self, document_id: DocumentId, cell_id: CellId, 
                          user_identity: UserIdentity) -> CellPermissionRole:
        """Get the role of a user for a specific cell.
        
        Args:
            document_id: The unique identifier for the document.
            cell_id: The unique identifier for the cell.
            user_identity: The user identity information.
            
        Returns:
            The cell permission role of the user for the cell.
        """
        user_id = self._get_user_id(user_identity)
        cell_permissions = self.get_cell_permissions(document_id, cell_id)
        
        if user_id in cell_permissions:
            role_name = cell_permissions[user_id].get("role", CellPermissionRole.CELL_NONE.name)
            try:
                return CellPermissionRole[role_name]
            except KeyError:
                self.logger.error(f"Invalid cell role name: {role_name}")
                return CellPermissionRole.CELL_NONE
        
        # If no cell-specific permission exists, map from document-level permission
        document_role = self.get_user_role(document_id, user_identity)
        return self._map_document_to_cell_role(document_role)
    
    def _map_document_to_cell_role(self, document_role: PermissionRole) -> CellPermissionRole:
        """Map a document-level role to a cell-level role.
        
        Args:
            document_role: The document-level permission role.
            
        Returns:
            The equivalent cell-level permission role.
        """
        role_mapping = {
            PermissionRole.OWNER: CellPermissionRole.CELL_OWNER,
            PermissionRole.ADMIN: CellPermissionRole.CELL_OWNER,
            PermissionRole.EDITOR: CellPermissionRole.CELL_EDITOR,
            PermissionRole.COMMENTER: CellPermissionRole.CELL_COMMENTER,
            PermissionRole.VIEWER: CellPermissionRole.CELL_VIEWER,
            PermissionRole.NONE: CellPermissionRole.CELL_NONE,
        }
        return role_mapping.get(document_role, CellPermissionRole.CELL_NONE)
    
    def _get_user_id(self, user_identity: UserIdentity) -> str:
        """Extract a unique user ID from the user identity information.
        
        Args:
            user_identity: The user identity information.
            
        Returns:
            A unique identifier for the user.
        """
        # Try to get user ID from JupyterHub identity
        if "name" in user_identity:
            return user_identity["name"]
        
        # Fall back to other identifiers
        for key in ["username", "user_id", "id", "email"]:
            if key in user_identity and user_identity[key]:
                return str(user_identity[key])
        
        # Last resort: use the string representation of the identity
        return str(user_identity)
    
    def _is_document_owner(self, document_id: DocumentId, user_identity: UserIdentity) -> bool:
        """Check if a user is the owner of a document based on JupyterHub information.
        
        Args:
            document_id: The unique identifier for the document.
            user_identity: The user identity information.
            
        Returns:
            True if the user is the owner of the document, False otherwise.
        """
        # This method would typically check with the JupyterHub API or file system
        # to determine if the user is the owner of the document.
        # For now, we'll use a simple implementation based on document metadata.
        
        if not self._persistence_manager:
            return False
        
        try:
            document_metadata = self._persistence_manager.get_document_metadata(document_id)
            owner_id = document_metadata.get("owner_id")
            user_id = self._get_user_id(user_identity)
            return owner_id == user_id
        except Exception as e:
            self.logger.error(f"Error checking document ownership: {e}")
            return False
    
    def has_permission(self, document_id: DocumentId, user_identity: UserIdentity, 
                      action: PermissionAction) -> bool:
        """Check if a user has permission to perform a specific action on a document.
        
        Args:
            document_id: The unique identifier for the document.
            user_identity: The user identity information.
            action: The action to check permission for.
            
        Returns:
            True if the user has permission to perform the action, False otherwise.
        """
        # Get the user's role for the document
        role = self.get_user_role(document_id, user_identity)
        
        # Get the permissions for the role
        role_permissions = self._get_role_permissions(role)
        
        # Check if the action is permitted
        return role_permissions.get(action.value, False)
    
    def has_cell_permission(self, document_id: DocumentId, cell_id: CellId, 
                           user_identity: UserIdentity, action: PermissionAction) -> bool:
        """Check if a user has permission to perform a specific action on a cell.
        
        Args:
            document_id: The unique identifier for the document.
            cell_id: The unique identifier for the cell.
            user_identity: The user identity information.
            action: The action to check permission for.
            
        Returns:
            True if the user has permission to perform the action, False otherwise.
        """
        # Get the user's role for the cell
        cell_role = self.get_cell_user_role(document_id, cell_id, user_identity)
        
        # Get the permissions for the cell role
        cell_permissions = self._get_cell_role_permissions(cell_role)
        
        # Check if the action is permitted at the cell level
        if cell_permissions.get(action.value, False):
            return True
        
        # If not permitted at cell level, check document level for certain actions
        if action in [
            PermissionAction.OVERRIDE_LOCK,  # Admin/Owner can override locks
            PermissionAction.MANAGE_PERMISSIONS,  # Admin/Owner can manage permissions
        ]:
            return self.has_permission(document_id, user_identity, action)
        
        return False
    
    def set_user_role(self, document_id: DocumentId, target_user_identity: UserIdentity, 
                     role: PermissionRole, granter_identity: UserIdentity) -> bool:
        """Set the role of a user for a document.
        
        Args:
            document_id: The unique identifier for the document.
            target_user_identity: The identity of the user to set the role for.
            role: The permission role to assign.
            granter_identity: The identity of the user granting the permission.
            
        Returns:
            True if the role was successfully set, False otherwise.
        """
        # Check if the granter has permission to manage permissions
        if not self.has_permission(document_id, granter_identity, PermissionAction.MANAGE_PERMISSIONS):
            self.logger.warning(f"User {self._get_user_id(granter_identity)} does not have permission to manage permissions")
            return False
        
        # Check if trying to set OWNER role, which requires special handling
        if role == PermissionRole.OWNER:
            # Only the current owner can transfer ownership
            if not self._is_document_owner(document_id, granter_identity):
                self.logger.warning(f"Only the document owner can transfer ownership")
                return False
        
        # Get the target user ID
        target_user_id = self._get_user_id(target_user_identity)
        
        # Create or update the permission record
        permission_record = {
            "role": role.name,
            "granted_by": self._get_user_id(granter_identity),
            "granted_at": datetime.utcnow().isoformat(),
            "permissions": self._get_role_permissions(role)
        }
        
        # Update the permission cache
        if document_id in self._permission_cache:
            self._permission_cache[document_id][target_user_id] = permission_record
        else:
            self._permission_cache[document_id] = {target_user_id: permission_record}
        
        # Persist the permission record
        if self._persistence_manager:
            try:
                self._persistence_manager.set_document_permission(
                    document_id, target_user_id, permission_record
                )
                return True
            except Exception as e:
                self.logger.error(f"Error setting permission: {e}")
                return False
        else:
            self.logger.warning("No persistence manager available for permission storage")
            return True  # Return True even without persistence for in-memory operation
    
    def set_cell_user_role(self, document_id: DocumentId, cell_id: CellId, 
                          target_user_identity: UserIdentity, role: CellPermissionRole, 
                          granter_identity: UserIdentity) -> bool:
        """Set the role of a user for a specific cell.
        
        Args:
            document_id: The unique identifier for the document.
            cell_id: The unique identifier for the cell.
            target_user_identity: The identity of the user to set the role for.
            role: The cell permission role to assign.
            granter_identity: The identity of the user granting the permission.
            
        Returns:
            True if the role was successfully set, False otherwise.
        """
        # Check if the granter has permission to manage permissions
        if not self.has_permission(document_id, granter_identity, PermissionAction.MANAGE_PERMISSIONS):
            self.logger.warning(f"User {self._get_user_id(granter_identity)} does not have permission to manage permissions")
            return False
        
        # Get the target user ID
        target_user_id = self._get_user_id(target_user_identity)
        
        # Create the cell permission record
        permission_record = {
            "role": role.name,
            "granted_by": self._get_user_id(granter_identity),
            "granted_at": datetime.utcnow().isoformat(),
            "permissions": self._get_cell_role_permissions(role)
        }
        
        # Persist the cell permission record
        if self._persistence_manager:
            try:
                self._persistence_manager.set_cell_permission(
                    document_id, cell_id, target_user_id, permission_record
                )
                return True
            except Exception as e:
                self.logger.error(f"Error setting cell permission: {e}")
                return False
        else:
            self.logger.warning("No persistence manager available for permission storage")
            return True  # Return True even without persistence for in-memory operation
    
    def remove_user_permission(self, document_id: DocumentId, target_user_identity: UserIdentity, 
                              remover_identity: UserIdentity) -> bool:
        """Remove a user's permission for a document.
        
        Args:
            document_id: The unique identifier for the document.
            target_user_identity: The identity of the user to remove permissions for.
            remover_identity: The identity of the user removing the permission.
            
        Returns:
            True if the permission was successfully removed, False otherwise.
        """
        # Check if the remover has permission to manage permissions
        if not self.has_permission(document_id, remover_identity, PermissionAction.MANAGE_PERMISSIONS):
            self.logger.warning(f"User {self._get_user_id(remover_identity)} does not have permission to manage permissions")
            return False
        
        # Cannot remove the owner's permission
        target_role = self.get_user_role(document_id, target_user_identity)
        if target_role == PermissionRole.OWNER and not self._is_document_owner(document_id, remover_identity):
            self.logger.warning("Cannot remove the owner's permission")
            return False
        
        # Get the target user ID
        target_user_id = self._get_user_id(target_user_identity)
        
        # Update the permission cache
        if document_id in self._permission_cache and target_user_id in self._permission_cache[document_id]:
            del self._permission_cache[document_id][target_user_id]
        
        # Remove from persistence manager
        if self._persistence_manager:
            try:
                self._persistence_manager.remove_document_permission(document_id, target_user_id)
                return True
            except Exception as e:
                self.logger.error(f"Error removing permission: {e}")
                return False
        else:
            self.logger.warning("No persistence manager available for permission removal")
            return True  # Return True even without persistence for in-memory operation
    
    def remove_cell_user_permission(self, document_id: DocumentId, cell_id: CellId, 
                                   target_user_identity: UserIdentity, 
                                   remover_identity: UserIdentity) -> bool:
        """Remove a user's permission for a specific cell.
        
        Args:
            document_id: The unique identifier for the document.
            cell_id: The unique identifier for the cell.
            target_user_identity: The identity of the user to remove permissions for.
            remover_identity: The identity of the user removing the permission.
            
        Returns:
            True if the permission was successfully removed, False otherwise.
        """
        # Check if the remover has permission to manage permissions
        if not self.has_permission(document_id, remover_identity, PermissionAction.MANAGE_PERMISSIONS):
            self.logger.warning(f"User {self._get_user_id(remover_identity)} does not have permission to manage permissions")
            return False
        
        # Get the target user ID
        target_user_id = self._get_user_id(target_user_identity)
        
        # Remove from persistence manager
        if self._persistence_manager:
            try:
                self._persistence_manager.remove_cell_permission(document_id, cell_id, target_user_id)
                return True
            except Exception as e:
                self.logger.error(f"Error removing cell permission: {e}")
                return False
        else:
            self.logger.warning("No persistence manager available for permission removal")
            return True  # Return True even without persistence for in-memory operation
    
    def clear_permission_cache(self, document_id: DocumentId = None) -> None:
        """Clear the permission cache for a document or all documents.
        
        Args:
            document_id: The unique identifier for the document to clear the cache for.
                        If None, clear the cache for all documents.
        """
        if document_id is None:
            self._permission_cache = {}
        elif document_id in self._permission_cache:
            del self._permission_cache[document_id]


class CollaborativeAuthorizer(Authorizer):
    """Authorizer for collaborative notebooks.
    
    This class extends the Jupyter Server Authorizer to add support for
    collaborative permission checking at both document and cell levels.
    """
    
    def __init__(self, permission_manager: NotebookPermissionManager = None, **kwargs):
        """Initialize the authorizer.
        
        Args:
            permission_manager: The permission manager to use for checking permissions.
            **kwargs: Additional arguments to pass to the parent class.
        """
        super().__init__(**kwargs)
        self.logger = logging.getLogger(__name__)
        self._permission_manager = permission_manager or NotebookPermissionManager()
    
    def is_authorized(self, handler: JupyterHandler, user: t.Dict[str, t.Any], action: str, resource: str) -> bool:
        """Check if a user is authorized to perform an action on a resource.
        
        Args:
            handler: The Jupyter handler processing the request.
            user: The user identity information.
            action: The action being performed.
            resource: The resource being accessed.
            
        Returns:
            True if the user is authorized, False otherwise.
        """
        # First, check the parent class authorization
        if not super().is_authorized(handler, user, action, resource):
            return False
        
        # For collaborative actions, perform additional checks
        if action.startswith("collaborative:"):
            return self._check_collaborative_permission(handler, user, action, resource)
        
        # For non-collaborative actions, the parent class authorization is sufficient
        return True
    
    def _check_collaborative_permission(self, handler: JupyterHandler, user: t.Dict[str, t.Any], 
                                       action: str, resource: str) -> bool:
        """Check if a user is authorized to perform a collaborative action.
        
        Args:
            handler: The Jupyter handler processing the request.
            user: The user identity information.
            action: The collaborative action being performed.
            resource: The resource being accessed.
            
        Returns:
            True if the user is authorized, False otherwise.
        """
        try:
            # Parse the resource to extract document_id and cell_id (if applicable)
            resource_parts = resource.split("/")
            document_id = resource_parts[0] if len(resource_parts) > 0 else None
            cell_id = resource_parts[1] if len(resource_parts) > 1 else None
            
            # Map the action string to a PermissionAction enum
            action_parts = action.split(":")
            if len(action_parts) < 2:
                self.logger.error(f"Invalid collaborative action format: {action}")
                return False
            
            action_name = action_parts[1].upper()
            try:
                permission_action = getattr(PermissionAction, action_name)
            except AttributeError:
                self.logger.error(f"Unknown permission action: {action_name}")
                return False
            
            # Check the appropriate permission based on whether it's a cell-level action
            if cell_id and permission_action.value.endswith("_cell"):
                return self._permission_manager.has_cell_permission(
                    document_id, cell_id, user, permission_action
                )
            else:
                return self._permission_manager.has_permission(
                    document_id, user, permission_action
                )
        
        except Exception as e:
            self.logger.error(f"Error checking collaborative permission: {e}")
            return False


def collaborative_authorized(action: str):
    """Decorator for checking collaborative authorization.
    
    This decorator can be applied to handler methods to check if the current user
    is authorized to perform the specified collaborative action on the resource.
    
    Args:
        action: The collaborative action to check authorization for.
        
    Returns:
        A decorator function that checks authorization before executing the handler method.
    """
    def decorator(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            # Extract the resource from the request path
            path = self.request.path
            path_parts = path.strip("/").split("/")
            
            # The resource is typically the document ID and possibly cell ID
            resource = "/".join(path_parts[2:]) if len(path_parts) > 2 else ""
            
            # Check if the user is authorized
            if not self.application.authorizer.is_authorized(
                self, self.current_user, f"collaborative:{action}", resource
            ):
                raise web.HTTPError(403, f"Not authorized to perform {action} on {resource}")
            
            # If authorized, execute the original method
            return method(self, *args, **kwargs)
        return wrapper
    return decorator


# JupyterHub integration utilities
def get_jupyterhub_user(handler: JupyterHandler) -> t.Optional[t.Dict[str, t.Any]]:
    """Get the JupyterHub user information from a handler.
    
    Args:
        handler: The Jupyter handler to extract user information from.
        
    Returns:
        A dictionary containing JupyterHub user information, or None if not available.
    """
    # Check if running under JupyterHub
    if not hasattr(handler, "hub_auth") or not handler.hub_auth:
        return None
    
    # Get the user information from the handler
    if hasattr(handler, "hub_user") and handler.hub_user:
        return handler.hub_user
    
    # Try to get from the current_user attribute
    if hasattr(handler, "current_user") and handler.current_user:
        return handler.current_user
    
    return None


def get_jupyterhub_user_id(handler: JupyterHandler) -> t.Optional[str]:
    """Get the JupyterHub user ID from a handler.
    
    Args:
        handler: The Jupyter handler to extract user ID from.
        
    Returns:
        The JupyterHub user ID, or None if not available.
    """
    user = get_jupyterhub_user(handler)
    if not user:
        return None
    
    # Try different attributes that might contain the user ID
    for attr in ["name", "username", "id"]:
        if attr in user and user[attr]:
            return str(user[attr])
    
    return None


def map_jupyterhub_scopes_to_roles(scopes: t.List[str]) -> PermissionRole:
    """Map JupyterHub scopes to permission roles.
    
    Args:
        scopes: A list of JupyterHub scopes assigned to the user.
        
    Returns:
        The highest permission role that the scopes map to.
    """
    # Define scope to role mapping
    scope_role_mapping = {
        "notebooks:collaborative:own": PermissionRole.OWNER,
        "notebooks:collaborative:admin": PermissionRole.ADMIN,
        "notebooks:collaborative:edit": PermissionRole.EDITOR,
        "notebooks:collaborative:comment": PermissionRole.COMMENTER,
        "notebooks:collaborative:read": PermissionRole.VIEWER,
    }
    
    # Find the highest role that the user's scopes map to
    highest_role = PermissionRole.NONE
    for scope in scopes:
        if scope in scope_role_mapping:
            role = scope_role_mapping[scope]
            if role.value > highest_role.value:
                highest_role = role
    
    return highest_role


# Permission validation functions for WebSocket handlers
def validate_websocket_permission(permission_manager: NotebookPermissionManager,
                                 document_id: DocumentId,
                                 user_identity: UserIdentity,
                                 action: PermissionAction) -> bool:
    """Validate if a WebSocket client has permission to perform an action.
    
    Args:
        permission_manager: The permission manager to use for checking permissions.
        document_id: The unique identifier for the document.
        user_identity: The user identity information.
        action: The action to check permission for.
        
    Returns:
        True if the user has permission, False otherwise.
    """
    return permission_manager.has_permission(document_id, user_identity, action)


def validate_websocket_cell_permission(permission_manager: NotebookPermissionManager,
                                      document_id: DocumentId,
                                      cell_id: CellId,
                                      user_identity: UserIdentity,
                                      action: PermissionAction) -> bool:
    """Validate if a WebSocket client has permission to perform an action on a cell.
    
    Args:
        permission_manager: The permission manager to use for checking permissions.
        document_id: The unique identifier for the document.
        cell_id: The unique identifier for the cell.
        user_identity: The user identity information.
        action: The action to check permission for.
        
    Returns:
        True if the user has permission, False otherwise.
    """
    return permission_manager.has_cell_permission(document_id, cell_id, user_identity, action)
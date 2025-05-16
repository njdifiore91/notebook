import pytest
import unittest.mock as mock
import json
import os
import sys
from unittest.mock import MagicMock, patch

# Import the permission system components
from notebook.collab.permissions import (
    PermissionRole,
    PermissionAction,
    NotebookPermissionManager,
    collaborative_authorized,
    ROLE_PERMISSIONS
)

# Skip tests if collaboration dependencies are not installed
pytestmark = pytest.mark.skipif(
    not pytest.importorskip('tests.conftest').HAS_COLLABORATION_DEPS,
    reason='Collaboration dependencies not installed'
)


class TestPermissionRoles:
    """Test the permission role definitions and their associated actions."""
    
    def test_role_hierarchy(self):
        """Test that the role hierarchy is correctly defined."""
        # Verify the order of roles from highest to lowest privilege
        roles = list(PermissionRole)
        assert roles[0] == PermissionRole.OWNER
        assert roles[1] == PermissionRole.ADMIN
        assert roles[2] == PermissionRole.EDITOR
        assert roles[3] == PermissionRole.COMMENTER
        assert roles[4] == PermissionRole.VIEWER
    
    def test_role_permissions_mapping(self):
        """Test that each role has the correct set of permissions."""
        # Owner should have all permissions
        assert len(ROLE_PERMISSIONS[PermissionRole.OWNER]) == len(list(PermissionAction))
        
        # Admin should have all permissions except ADMIN_DOCUMENT
        admin_permissions = ROLE_PERMISSIONS[PermissionRole.ADMIN]
        assert PermissionAction.ADMIN_DOCUMENT.value not in admin_permissions
        assert len(admin_permissions) == len(list(PermissionAction)) - 1
        
        # Editor should have edit permissions but not admin permissions
        editor_permissions = ROLE_PERMISSIONS[PermissionRole.EDITOR]
        assert PermissionAction.EDIT_DOCUMENT.value in editor_permissions
        assert PermissionAction.EDIT_CELL.value in editor_permissions
        assert PermissionAction.ADMIN_DOCUMENT.value not in editor_permissions
        
        # Commenter should have comment permissions but not edit permissions
        commenter_permissions = ROLE_PERMISSIONS[PermissionRole.COMMENTER]
        assert PermissionAction.COMMENT_DOCUMENT.value in commenter_permissions
        assert PermissionAction.COMMENT_CELL.value in commenter_permissions
        assert PermissionAction.EDIT_DOCUMENT.value not in commenter_permissions
        assert PermissionAction.EDIT_CELL.value not in commenter_permissions
        
        # Viewer should only have view permissions
        viewer_permissions = ROLE_PERMISSIONS[PermissionRole.VIEWER]
        assert PermissionAction.VIEW_DOCUMENT.value in viewer_permissions
        assert PermissionAction.VIEW_CELL.value in viewer_permissions
        assert PermissionAction.EDIT_DOCUMENT.value not in viewer_permissions
        assert PermissionAction.COMMENT_DOCUMENT.value not in viewer_permissions
    
    def test_permission_inheritance(self):
        """Test that permissions are properly inherited in the role hierarchy."""
        # All roles should have VIEW_DOCUMENT permission
        for role in PermissionRole:
            assert PermissionAction.VIEW_DOCUMENT.value in ROLE_PERMISSIONS[role]
        
        # OWNER, ADMIN, EDITOR, COMMENTER should have COMMENT_DOCUMENT permission
        for role in [PermissionRole.OWNER, PermissionRole.ADMIN, PermissionRole.EDITOR, PermissionRole.COMMENTER]:
            assert PermissionAction.COMMENT_DOCUMENT.value in ROLE_PERMISSIONS[role]
        
        # OWNER, ADMIN, EDITOR should have EDIT_DOCUMENT permission
        for role in [PermissionRole.OWNER, PermissionRole.ADMIN, PermissionRole.EDITOR]:
            assert PermissionAction.EDIT_DOCUMENT.value in ROLE_PERMISSIONS[role]
        
        # Only OWNER should have ADMIN_DOCUMENT permission
        assert PermissionAction.ADMIN_DOCUMENT.value in ROLE_PERMISSIONS[PermissionRole.OWNER]
        for role in [PermissionRole.ADMIN, PermissionRole.EDITOR, PermissionRole.COMMENTER, PermissionRole.VIEWER]:
            assert PermissionAction.ADMIN_DOCUMENT.value not in ROLE_PERMISSIONS[role]


class TestNotebookPermissionManager:
    """Test the NotebookPermissionManager class."""
    
    @pytest.fixture
    def mock_persistence_manager(self):
        """Create a mock persistence manager for testing."""
        persistence_manager = MagicMock()
        
        # Mock get_collaboration_sessions_for_document
        persistence_manager.get_collaboration_sessions_for_document.return_value = [{
            'session_id': 'test-session-id',
            'document_id': 'test-document-id',
            'owner_id': 'owner-user-id'
        }]
        
        # Mock get_permissions
        persistence_manager.get_permissions.return_value = []
        
        # Mock create_collaboration_session
        persistence_manager.create_collaboration_session.return_value = 'new-session-id'
        
        return persistence_manager
    
    @pytest.fixture
    def permission_manager(self, mock_persistence_manager):
        """Create a permission manager with a mock persistence manager."""
        manager = NotebookPermissionManager()
        manager.persistence_manager = mock_persistence_manager
        return manager
    
    def test_get_user_role_owner(self, permission_manager, mock_persistence_manager):
        """Test that the owner of a document gets the owner role."""
        # Set up the test
        document_id = 'test-document-id'
        user_identity = {'name': 'owner-user-id'}
        
        # Call the method
        role = permission_manager.get_user_role(document_id, user_identity)
        
        # Verify the result
        assert role == PermissionRole.OWNER
        mock_persistence_manager.get_collaboration_sessions_for_document.assert_called_once_with(document_id)
    
    def test_get_user_role_explicit_permission(self, permission_manager, mock_persistence_manager):
        """Test that a user with explicit permissions gets the correct role."""
        # Set up the test
        document_id = 'test-document-id'
        user_identity = {'name': 'editor-user-id'}
        
        # Mock the permissions
        mock_persistence_manager.get_permissions.return_value = [{
            'permission_type': 'editor',
            'user_id': 'editor-user-id'
        }]
        
        # Call the method
        role = permission_manager.get_user_role(document_id, user_identity)
        
        # Verify the result
        assert role == PermissionRole.EDITOR
        mock_persistence_manager.get_collaboration_sessions_for_document.assert_called_once_with(document_id)
        mock_persistence_manager.get_permissions.assert_called_once()
    
    def test_get_user_role_default(self, permission_manager, mock_persistence_manager):
        """Test that a user with no explicit permissions gets the default role."""
        # Set up the test
        document_id = 'test-document-id'
        user_identity = {'name': 'unknown-user-id'}
        
        # Call the method
        role = permission_manager.get_user_role(document_id, user_identity)
        
        # Verify the result
        assert role == permission_manager.default_permission_role
        mock_persistence_manager.get_collaboration_sessions_for_document.assert_called_once_with(document_id)
        mock_persistence_manager.get_permissions.assert_called_once()
    
    def test_has_permission_allowed(self, permission_manager):
        """Test that has_permission returns True when the action is allowed."""
        # Set up the test
        document_id = 'test-document-id'
        user_identity = {'name': 'owner-user-id'}
        action = PermissionAction.EDIT_DOCUMENT
        
        # Call the method
        result = permission_manager.has_permission(document_id, user_identity, action)
        
        # Verify the result
        assert result is True
    
    def test_has_permission_denied(self, permission_manager, mock_persistence_manager):
        """Test that has_permission returns False when the action is not allowed."""
        # Set up the test
        document_id = 'test-document-id'
        user_identity = {'name': 'viewer-user-id'}
        action = PermissionAction.EDIT_DOCUMENT
        
        # Mock the permissions to make the user a viewer
        mock_persistence_manager.get_permissions.return_value = [{
            'permission_type': 'viewer',
            'user_id': 'viewer-user-id'
        }]
        
        # Call the method
        result = permission_manager.has_permission(document_id, user_identity, action)
        
        # Verify the result
        assert result is False
    
    def test_has_cell_permission(self, permission_manager, mock_persistence_manager):
        """Test that cell-level permissions are correctly checked."""
        # Set up the test
        document_id = 'test-document-id'
        cell_id = 'test-cell-id'
        user_identity = {'name': 'editor-user-id'}
        action = PermissionAction.EDIT_CELL
        
        # Mock the permissions to make the user an editor
        mock_persistence_manager.get_permissions.side_effect = [
            # First call for document permissions
            [{'permission_type': 'editor', 'user_id': 'editor-user-id'}],
            # Second call for cell permissions
            []
        ]
        
        # Call the method
        result = permission_manager.has_cell_permission(document_id, cell_id, user_identity, action)
        
        # Verify the result
        assert result is True
        assert mock_persistence_manager.get_permissions.call_count == 2
    
    def test_has_cell_permission_with_lock(self, permission_manager, mock_persistence_manager):
        """Test that locked cells cannot be edited by non-owners."""
        # Set up the test
        document_id = 'test-document-id'
        cell_id = 'locked-cell-id'
        user_identity = {'name': 'editor-user-id'}
        action = PermissionAction.EDIT_CELL
        
        # Mock the permissions to make the user an editor
        mock_persistence_manager.get_permissions.side_effect = [
            # First call for document permissions
            [{'permission_type': 'editor', 'user_id': 'editor-user-id'}],
            # Second call for cell permissions
            []
        ]
        
        # Mock the cell locks to show the cell is locked by another user
        mock_persistence_manager.get_cell_locks.return_value = [{
            'cell_id': 'locked-cell-id',
            'user_id': 'other-user-id'
        }]
        
        # Call the method
        result = permission_manager.has_cell_permission(document_id, cell_id, user_identity, action)
        
        # Verify the result
        assert result is False
        assert mock_persistence_manager.get_permissions.call_count == 2
        mock_persistence_manager.get_cell_locks.assert_called_once()
    
    def test_grant_permission(self, permission_manager, mock_persistence_manager):
        """Test that permissions can be granted to users."""
        # Set up the test
        document_id = 'test-document-id'
        user_id = 'new-editor-id'
        role = PermissionRole.EDITOR
        granted_by = 'admin-user-id'
        
        # Mock set_permission
        mock_persistence_manager.set_permission.return_value = 'new-permission-id'
        
        # Call the method
        permission_id = permission_manager.grant_permission(document_id, role, user_id, None, granted_by)
        
        # Verify the result
        assert permission_id == 'new-permission-id'
        mock_persistence_manager.set_permission.assert_called_once_with(
            'test-session-id',
            resource_id='test-document-id',
            resource_type='document',
            permission_type='editor',
            user_id='new-editor-id',
            group_id=None,
            granted_by='admin-user-id'
        )
    
    def test_grant_cell_permission(self, permission_manager, mock_persistence_manager):
        """Test that cell-level permissions can be granted."""
        # Set up the test
        document_id = 'test-document-id'
        cell_id = 'test-cell-id'
        user_id = 'editor-user-id'
        role = PermissionRole.EDITOR
        granted_by = 'admin-user-id'
        
        # Mock set_permission
        mock_persistence_manager.set_permission.return_value = 'new-cell-permission-id'
        
        # Call the method
        permission_id = permission_manager.grant_cell_permission(document_id, cell_id, role, user_id, granted_by)
        
        # Verify the result
        assert permission_id == 'new-cell-permission-id'
        mock_persistence_manager.set_permission.assert_called_once_with(
            'test-session-id',
            resource_id='test-cell-id',
            resource_type='cell',
            permission_type='editor',
            user_id='editor-user-id',
            granted_by='admin-user-id'
        )
    
    def test_revoke_permission(self, permission_manager, mock_persistence_manager):
        """Test that permissions can be revoked."""
        # Set up the test
        permission_id = 'permission-to-revoke'
        
        # Mock remove_permission
        mock_persistence_manager.remove_permission.return_value = True
        
        # Call the method
        result = permission_manager.revoke_permission(permission_id)
        
        # Verify the result
        assert result is True
        mock_persistence_manager.remove_permission.assert_called_once_with('permission-to-revoke')
    
    def test_get_document_permissions(self, permission_manager, mock_persistence_manager):
        """Test retrieving all permissions for a document."""
        # Set up the test
        document_id = 'test-document-id'
        expected_permissions = [
            {'permission_type': 'owner', 'user_id': 'owner-user-id'},
            {'permission_type': 'editor', 'user_id': 'editor-user-id'}
        ]
        
        # Mock get_permissions
        mock_persistence_manager.get_permissions.return_value = expected_permissions
        
        # Call the method
        permissions = permission_manager.get_document_permissions(document_id)
        
        # Verify the result
        assert permissions == expected_permissions
        mock_persistence_manager.get_collaboration_sessions_for_document.assert_called_once_with(document_id)
        mock_persistence_manager.get_permissions.assert_called_once()
    
    def test_get_cell_permissions(self, permission_manager, mock_persistence_manager):
        """Test retrieving all permissions for a cell."""
        # Set up the test
        document_id = 'test-document-id'
        cell_id = 'test-cell-id'
        expected_permissions = [
            {'permission_type': 'editor', 'user_id': 'editor-user-id'}
        ]
        
        # Mock get_permissions
        mock_persistence_manager.get_permissions.return_value = expected_permissions
        
        # Call the method
        permissions = permission_manager.get_cell_permissions(document_id, cell_id)
        
        # Verify the result
        assert permissions == expected_permissions
        mock_persistence_manager.get_collaboration_sessions_for_document.assert_called_once_with(document_id)
        mock_persistence_manager.get_permissions.assert_called_once()
    
    def test_jupyterhub_integration(self, permission_manager):
        """Test integration with JupyterHub for user information."""
        # Set up the test
        user_identity = {'name': 'test-user'}
        
        # Call the method
        user_info = permission_manager.get_jupyterhub_user_info(user_identity)
        
        # Verify the result
        assert user_info['name'] == 'test-user'
        assert 'groups' in user_info
        
        # Test with jupyterhub integration disabled
        permission_manager.enable_jupyterhub_integration = False
        user_info = permission_manager.get_jupyterhub_user_info(user_identity)
        assert user_info == {}
    
    def test_clear_cache(self, permission_manager):
        """Test clearing the permission cache."""
        # Set up the test - add some items to the cache
        permission_manager._permission_cache = {'doc1': 'cache1', 'doc2': 'cache2'}
        permission_manager._jupyterhub_groups_cache = {'user1': ['group1']}
        permission_manager._last_cache_update = {'doc1': 12345}
        
        # Call the method
        permission_manager.clear_cache()
        
        # Verify the result
        assert permission_manager._permission_cache == {}
        assert permission_manager._jupyterhub_groups_cache == {}
        assert permission_manager._last_cache_update == {}


class TestCollaborativeAuthorized:
    """Test the collaborative_authorized decorator."""
    
    @pytest.fixture
    def mock_handler(self):
        """Create a mock handler for testing the decorator."""
        handler = MagicMock()
        handler.permission_manager = MagicMock()
        handler.current_user = {'name': 'test-user'}
        handler.path_kwargs = {'document_id': 'test-document-id'}
        return handler
    
    @pytest.mark.asyncio
    async def test_authorized_allowed(self, mock_handler):
        """Test that the decorator allows access when permission is granted."""
        # Set up the test
        mock_handler.permission_manager.has_permission.return_value = True
        
        # Create a test method with the decorator
        @collaborative_authorized(PermissionAction.VIEW_DOCUMENT)
        async def test_method(self):
            return "success"
        
        # Call the decorated method
        result = await test_method(mock_handler)
        
        # Verify the result
        assert result == "success"
        mock_handler.permission_manager.has_permission.assert_called_once_with(
            'test-document-id', mock_handler.current_user, PermissionAction.VIEW_DOCUMENT
        )
    
    @pytest.mark.asyncio
    async def test_authorized_denied(self, mock_handler):
        """Test that the decorator denies access when permission is not granted."""
        # Set up the test
        mock_handler.permission_manager.has_permission.return_value = False
        
        # Create a test method with the decorator
        @collaborative_authorized(PermissionAction.EDIT_DOCUMENT)
        async def test_method(self):
            return "success"
        
        # Call the decorated method and expect an exception
        from tornado import web
        with pytest.raises(web.HTTPError) as excinfo:
            await test_method(mock_handler)
        
        # Verify the exception
        assert excinfo.value.status_code == 403
        mock_handler.permission_manager.has_permission.assert_called_once_with(
            'test-document-id', mock_handler.current_user, PermissionAction.EDIT_DOCUMENT
        )
    
    @pytest.mark.asyncio
    async def test_authorized_no_permission_manager(self, mock_handler):
        """Test that the decorator skips permission check if no permission manager is available."""
        # Set up the test - remove permission manager
        mock_handler.permission_manager = None
        
        # Create a test method with the decorator
        @collaborative_authorized(PermissionAction.EDIT_DOCUMENT)
        async def test_method(self):
            return "success"
        
        # Call the decorated method
        result = await test_method(mock_handler)
        
        # Verify the result
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_authorized_session_id(self, mock_handler):
        """Test that the decorator works with session_id instead of document_id."""
        # Set up the test - use session_id instead of document_id
        mock_handler.path_kwargs = {'session_id': 'test-session-id'}
        mock_handler.permission_manager.has_permission.return_value = True
        
        # Create a test method with the decorator
        @collaborative_authorized(PermissionAction.VIEW_DOCUMENT)
        async def test_method(self):
            return "success"
        
        # Call the decorated method
        result = await test_method(mock_handler)
        
        # Verify the result
        assert result == "success"
        mock_handler.permission_manager.has_permission.assert_called_once_with(
            'test-session-id', mock_handler.current_user, PermissionAction.VIEW_DOCUMENT
        )
    
    @pytest.mark.asyncio
    async def test_authorized_query_param(self, mock_handler):
        """Test that the decorator works with document_id as a query parameter."""
        # Set up the test - use query parameter instead of path kwargs
        mock_handler.path_kwargs = {}
        mock_handler.get_argument = MagicMock(return_value='test-query-doc-id')
        mock_handler.permission_manager.has_permission.return_value = True
        
        # Create a test method with the decorator
        @collaborative_authorized(PermissionAction.VIEW_DOCUMENT)
        async def test_method(self):
            return "success"
        
        # Call the decorated method
        result = await test_method(mock_handler)
        
        # Verify the result
        assert result == "success"
        mock_handler.get_argument.assert_called_once_with('document_id', None)
        mock_handler.permission_manager.has_permission.assert_called_once_with(
            'test-query-doc-id', mock_handler.current_user, PermissionAction.VIEW_DOCUMENT
        )


class TestPermissionHandler:
    """Test the PermissionHandler class."""
    
    @pytest.fixture
    def mock_permission_manager(self):
        """Create a mock permission manager for testing."""
        manager = MagicMock()
        return manager
    
    @pytest.fixture
    def permission_handler(self, mock_permission_manager):
        """Create a permission handler with a mock permission manager."""
        from notebook.collab.permissions import PermissionHandler
        handler = PermissionHandler()
        handler.permission_manager = mock_permission_manager
        handler.current_user = {'name': 'admin-user-id'}
        handler.request = MagicMock()
        handler.write = MagicMock()
        handler.set_status = MagicMock()
        return handler
    
    @pytest.mark.asyncio
    async def test_get_all_permissions(self, permission_handler, mock_permission_manager):
        """Test retrieving all permissions for a document."""
        # Set up the test
        document_id = 'test-document-id'
        expected_permissions = [
            {'permission_type': 'owner', 'user_id': 'owner-user-id'},
            {'permission_type': 'editor', 'user_id': 'editor-user-id'}
        ]
        
        # Mock get_document_permissions
        mock_permission_manager.get_document_permissions.return_value = expected_permissions
        
        # Mock has_permission to allow the action
        mock_permission_manager.has_permission.return_value = True
        
        # Call the method
        await permission_handler.get(document_id)
        
        # Verify the result
        mock_permission_manager.get_document_permissions.assert_called_once_with(document_id)
        permission_handler.write.assert_called_once_with(json.dumps(expected_permissions))
    
    @pytest.mark.asyncio
    async def test_get_user_permissions(self, permission_handler, mock_permission_manager):
        """Test retrieving permissions for a specific user."""
        # Set up the test
        document_id = 'test-document-id'
        user_id = 'editor-user-id'
        all_permissions = [
            {'permission_type': 'owner', 'user_id': 'owner-user-id'},
            {'permission_type': 'editor', 'user_id': 'editor-user-id'}
        ]
        expected_permissions = [
            {'permission_type': 'editor', 'user_id': 'editor-user-id'}
        ]
        
        # Mock get_document_permissions
        mock_permission_manager.get_document_permissions.return_value = all_permissions
        
        # Mock has_permission to allow the action
        mock_permission_manager.has_permission.return_value = True
        
        # Call the method
        await permission_handler.get(document_id, user_id)
        
        # Verify the result
        mock_permission_manager.get_document_permissions.assert_called_once_with(document_id)
        permission_handler.write.assert_called_once_with(json.dumps(expected_permissions))
    
    @pytest.mark.asyncio
    async def test_post_grant_permission(self, permission_handler, mock_permission_manager):
        """Test granting a permission to a user."""
        # Set up the test
        document_id = 'test-document-id'
        request_body = json.dumps({
            'user_id': 'new-editor-id',
            'role': 'editor'
        })
        
        # Mock the request body
        permission_handler.request.body = request_body
        
        # Mock has_permission to allow the action
        mock_permission_manager.has_permission.return_value = True
        
        # Mock grant_permission
        mock_permission_manager.grant_permission.return_value = 'new-permission-id'
        
        # Call the method
        await permission_handler.post(document_id)
        
        # Verify the result
        mock_permission_manager.grant_permission.assert_called_once_with(
            document_id, PermissionRole.EDITOR, 'new-editor-id', None, 'admin-user-id'
        )
        permission_handler.set_status.assert_called_once_with(201)
        permission_handler.write.assert_called_once_with(json.dumps({'id': 'new-permission-id'}))
    
    @pytest.mark.asyncio
    async def test_delete_permission(self, permission_handler, mock_permission_manager):
        """Test revoking a permission."""
        # Set up the test
        document_id = 'test-document-id'
        permission_id = 'permission-to-revoke'
        
        # Mock has_permission to allow the action
        mock_permission_manager.has_permission.return_value = True
        
        # Mock revoke_permission
        mock_permission_manager.revoke_permission.return_value = True
        
        # Call the method
        await permission_handler.delete(document_id, permission_id)
        
        # Verify the result
        mock_permission_manager.revoke_permission.assert_called_once_with(permission_id)
        permission_handler.set_status.assert_called_once_with(204)
    
    @pytest.mark.asyncio
    async def test_delete_permission_not_found(self, permission_handler, mock_permission_manager):
        """Test attempting to revoke a non-existent permission."""
        # Set up the test
        document_id = 'test-document-id'
        permission_id = 'nonexistent-permission'
        
        # Mock has_permission to allow the action
        mock_permission_manager.has_permission.return_value = True
        
        # Mock revoke_permission to return False (not found)
        mock_permission_manager.revoke_permission.return_value = False
        
        # Call the method and expect an exception
        from tornado import web
        with pytest.raises(web.HTTPError) as excinfo:
            await permission_handler.delete(document_id, permission_id)
        
        # Verify the exception
        assert excinfo.value.status_code == 404
        mock_permission_manager.revoke_permission.assert_called_once_with(permission_id)


class TestCellPermissionHandler:
    """Test the CellPermissionHandler class."""
    
    @pytest.fixture
    def mock_permission_manager(self):
        """Create a mock permission manager for testing."""
        manager = MagicMock()
        return manager
    
    @pytest.fixture
    def cell_permission_handler(self, mock_permission_manager):
        """Create a cell permission handler with a mock permission manager."""
        from notebook.collab.permissions import CellPermissionHandler
        handler = CellPermissionHandler()
        handler.permission_manager = mock_permission_manager
        handler.current_user = {'name': 'admin-user-id'}
        handler.request = MagicMock()
        handler.write = MagicMock()
        handler.set_status = MagicMock()
        return handler
    
    @pytest.mark.asyncio
    async def test_get_cell_permissions(self, cell_permission_handler, mock_permission_manager):
        """Test retrieving permissions for a cell."""
        # Set up the test
        document_id = 'test-document-id'
        cell_id = 'test-cell-id'
        expected_permissions = [
            {'permission_type': 'editor', 'user_id': 'editor-user-id'}
        ]
        
        # Mock get_cell_permissions
        mock_permission_manager.get_cell_permissions.return_value = expected_permissions
        
        # Mock has_permission to allow the action
        mock_permission_manager.has_permission.return_value = True
        
        # Call the method
        await cell_permission_handler.get(document_id, cell_id)
        
        # Verify the result
        mock_permission_manager.get_cell_permissions.assert_called_once_with(document_id, cell_id)
        cell_permission_handler.write.assert_called_once_with(json.dumps(expected_permissions))
    
    @pytest.mark.asyncio
    async def test_post_grant_cell_permission(self, cell_permission_handler, mock_permission_manager):
        """Test granting a permission for a cell."""
        # Set up the test
        document_id = 'test-document-id'
        cell_id = 'test-cell-id'
        request_body = json.dumps({
            'user_id': 'editor-user-id',
            'role': 'editor'
        })
        
        # Mock the request body
        cell_permission_handler.request.body = request_body
        
        # Mock has_permission to allow the action
        mock_permission_manager.has_permission.return_value = True
        
        # Mock grant_cell_permission
        mock_permission_manager.grant_cell_permission.return_value = 'new-cell-permission-id'
        
        # Call the method
        await cell_permission_handler.post(document_id, cell_id)
        
        # Verify the result
        mock_permission_manager.grant_cell_permission.assert_called_once_with(
            document_id, cell_id, PermissionRole.EDITOR, 'editor-user-id', 'admin-user-id'
        )
        cell_permission_handler.set_status.assert_called_once_with(201)
        cell_permission_handler.write.assert_called_once_with(json.dumps({'id': 'new-cell-permission-id'}))
    
    @pytest.mark.asyncio
    async def test_delete_cell_permission(self, cell_permission_handler, mock_permission_manager):
        """Test revoking a cell permission."""
        # Set up the test
        document_id = 'test-document-id'
        cell_id = 'test-cell-id'
        permission_id = 'cell-permission-to-revoke'
        
        # Mock has_permission to allow the action
        mock_permission_manager.has_permission.return_value = True
        
        # Mock revoke_permission
        mock_permission_manager.revoke_permission.return_value = True
        
        # Call the method
        await cell_permission_handler.delete(document_id, cell_id, permission_id)
        
        # Verify the result
        mock_permission_manager.revoke_permission.assert_called_once_with(permission_id)
        cell_permission_handler.set_status.assert_called_once_with(204)
    
    @pytest.mark.asyncio
    async def test_delete_cell_permission_not_found(self, cell_permission_handler, mock_permission_manager):
        """Test attempting to revoke a non-existent cell permission."""
        # Set up the test
        document_id = 'test-document-id'
        cell_id = 'test-cell-id'
        permission_id = 'nonexistent-permission'
        
        # Mock has_permission to allow the action
        mock_permission_manager.has_permission.return_value = True
        
        # Mock revoke_permission to return False (not found)
        mock_permission_manager.revoke_permission.return_value = False
        
        # Call the method and expect an exception
        from tornado import web
        with pytest.raises(web.HTTPError) as excinfo:
            await cell_permission_handler.delete(document_id, cell_id, permission_id)
        
        # Verify the exception
        assert excinfo.value.status_code == 404
        mock_permission_manager.revoke_permission.assert_called_once_with(permission_id)


class TestSetupHandlers:
    """Test the setup_handlers function."""
    
    def test_setup_handlers(self):
        """Test that handlers are correctly set up."""
        # Set up the test
        from notebook.collab.permissions import setup_handlers
        web_app = MagicMock()
        permission_manager = MagicMock()
        
        # Call the function
        setup_handlers(web_app, permission_manager)
        
        # Verify the result
        web_app.add_handlers.assert_called_once()
        # Check that the first argument is the host pattern
        assert web_app.add_handlers.call_args[0][0] == ".*$"
        # Check that the second argument is a list of handlers
        handlers = web_app.add_handlers.call_args[0][1]
        assert isinstance(handlers, list)
        assert len(handlers) > 0
        
        # Check that each handler has the correct structure
        for handler in handlers:
            assert isinstance(handler, tuple)
            assert len(handler) == 3
            assert isinstance(handler[0], str)  # URL pattern
            assert handler[2]['permission_manager'] == permission_manager  # Handler options
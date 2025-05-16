import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock

# Skip tests if collaboration dependencies are not installed
pytestmark = pytest.mark.skipif(
    not pytest.importorskip('tests.conftest').HAS_COLLABORATION_DEPS,
    reason='Collaboration dependencies not installed'
)


class TestPermissions:
    """Test suite for the permission system in collaborative editing."""

    @pytest.mark.asyncio
    async def test_document_level_permissions(self, multi_client_websocket_simulation):
        """Test that document-level permissions are correctly enforced."""
        # Create clients with different roles
        owner_client = await multi_client_websocket_simulation(user_id="owner", roles=["owner"])
        admin_client = await multi_client_websocket_simulation(user_id="admin", roles=["admin"])
        editor_client = await multi_client_websocket_simulation(user_id="editor", roles=["editor"])
        commenter_client = await multi_client_websocket_simulation(user_id="commenter", roles=["commenter"])
        viewer_client = await multi_client_websocket_simulation(user_id="viewer", roles=["viewer"])
        
        # Connect all clients to the same document
        doc_id = "test-permissions-doc"
        await owner_client.connect(doc_id=doc_id)
        await admin_client.connect(doc_id=doc_id)
        await editor_client.connect(doc_id=doc_id)
        await commenter_client.connect(doc_id=doc_id)
        await viewer_client.connect(doc_id=doc_id)
        
        try:
            # Owner should be able to modify the document
            await owner_client.update_document({"cell1": "print('Hello from owner')"})
            
            # Admin should be able to modify the document
            await admin_client.update_document({"cell2": "print('Hello from admin')"})
            
            # Editor should be able to modify the document
            await editor_client.update_document({"cell3": "print('Hello from editor')"})
            
            # Commenter should NOT be able to modify the document (will be rejected by server)
            with pytest.raises(Exception):
                await commenter_client.update_document({"cell4": "print('Hello from commenter')"})
            
            # Viewer should NOT be able to modify the document (will be rejected by server)
            with pytest.raises(Exception):
                await viewer_client.update_document({"cell5": "print('Hello from viewer')"})
            
            # Verify document state reflects permissions
            doc_state = await owner_client.get_document_state()
            assert "cell1" in doc_state
            assert "cell2" in doc_state
            assert "cell3" in doc_state
            assert "cell4" not in doc_state
            assert "cell5" not in doc_state
        finally:
            # Disconnect all clients
            await owner_client.disconnect()
            await admin_client.disconnect()
            await editor_client.disconnect()
            await commenter_client.disconnect()
            await viewer_client.disconnect()
    
    @pytest.mark.asyncio
    async def test_cell_level_permissions(self, multi_client_websocket_simulation):
        """Test that cell-level permissions override document-level permissions."""
        # Create clients with different roles
        owner_client = await multi_client_websocket_simulation(user_id="owner", roles=["owner"])
        editor_client = await multi_client_websocket_simulation(user_id="editor", roles=["editor"])
        
        # Connect clients to the same document
        doc_id = "test-cell-permissions-doc"
        await owner_client.connect(doc_id=doc_id)
        await editor_client.connect(doc_id=doc_id)
        
        try:
            # Owner creates initial cells
            await owner_client.update_document({
                "cell1": "print('Cell 1')",
                "cell2": "print('Cell 2')",
                "cell3": "print('Cell 3')"
            })
            
            # Mock the permission system to simulate cell-level permissions
            # In a real implementation, this would be handled by the server
            with patch('notebook.collab.permissions.check_cell_permission') as mock_check:
                # Set up mock to allow editing cell1, but deny editing cell2
                def check_permission_side_effect(user_id, cell_id, action):
                    if cell_id == "cell2" and action == "edit" and user_id == "editor":
                        return False
                    return True
                
                mock_check.side_effect = check_permission_side_effect
                
                # Editor should be able to edit cell1
                await editor_client.update_document({"cell1": "print('Updated Cell 1')"})  
                
                # Editor should NOT be able to edit cell2 due to cell-level permission
                with pytest.raises(Exception):
                    await editor_client.update_document({"cell2": "print('Trying to update Cell 2')"})  
                
                # Editor should be able to edit cell3
                await editor_client.update_document({"cell3": "print('Updated Cell 3')"})  
            
            # Verify document state reflects cell-level permissions
            doc_state = await owner_client.get_document_state()
            assert "print('Updated Cell 1')" in doc_state["cell1"]
            assert "print('Cell 2')" in doc_state["cell2"]
            assert "print('Updated Cell 3')" in doc_state["cell3"]
        finally:
            # Disconnect clients
            await owner_client.disconnect()
            await editor_client.disconnect()
    
    @pytest.mark.asyncio
    async def test_permission_changes(self, multi_client_websocket_simulation):
        """Test that permission changes are immediately enforced."""
        # Create clients with different roles
        owner_client = await multi_client_websocket_simulation(user_id="owner", roles=["owner"])
        user_client = await multi_client_websocket_simulation(user_id="user", roles=["viewer"])
        
        # Connect clients to the same document
        doc_id = "test-permission-changes-doc"
        await owner_client.connect(doc_id=doc_id)
        await user_client.connect(doc_id=doc_id)
        
        try:
            # Owner creates initial cell
            await owner_client.update_document({"cell1": "print('Initial cell')"})  
            
            # User with viewer role should NOT be able to edit
            with pytest.raises(Exception):
                await user_client.update_document({"cell1": "print('Trying to edit as viewer')"})  
            
            # Mock permission change from viewer to editor
            with patch('notebook.collab.permissions.get_user_role') as mock_role:
                # First return viewer, then editor after "permission change"
                mock_role.side_effect = ["viewer", "editor", "editor"]
                
                # Simulate permission change by owner
                await owner_client.update_document({
                    "permissions": {"user": "editor"}
                })
                
                # After permission change, user should be able to edit
                await user_client.update_document({"cell1": "print('Edited after permission change')"})  
            
            # Verify document state reflects the edit after permission change
            doc_state = await owner_client.get_document_state()
            assert "print('Edited after permission change')" in doc_state["cell1"]
        finally:
            # Disconnect clients
            await owner_client.disconnect()
            await user_client.disconnect()
    
    @pytest.mark.asyncio
    async def test_authentication_integration(self, multi_client_websocket_simulation):
        """Test that permissions integrate correctly with authentication systems."""
        # Create a client with no authentication
        unauthenticated_client = await multi_client_websocket_simulation()
        
        # Create a client with proper authentication
        authenticated_client = await multi_client_websocket_simulation(user_id="auth_user", roles=["editor"])
        
        # Connect authenticated client to document
        doc_id = "test-auth-doc"
        await authenticated_client.connect(doc_id=doc_id)
        
        try:
            # Create initial content as authenticated user
            await authenticated_client.update_document({"cell1": "print('Authenticated content')"})  
            
            # Mock authentication check to simulate authentication failure
            with patch('notebook.collab.handlers.authenticate_websocket') as mock_auth:
                mock_auth.return_value = False
                
                # Unauthenticated client should not be able to connect
                with pytest.raises(Exception):
                    await unauthenticated_client.connect(doc_id=doc_id)
            
            # Mock authentication check to simulate successful authentication but insufficient permissions
            with patch('notebook.collab.handlers.authenticate_websocket') as mock_auth:
                mock_auth.return_value = True
                
                # Mock permission check to deny access
                with patch('notebook.collab.permissions.check_document_permission') as mock_perm:
                    mock_perm.return_value = False
                    
                    # Client should connect but not be able to access document
                    with pytest.raises(Exception):
                        await unauthenticated_client.connect(doc_id=doc_id)
        finally:
            # Disconnect clients
            if authenticated_client.connected:
                await authenticated_client.disconnect()
            if unauthenticated_client.connected:
                await unauthenticated_client.disconnect()
    
    @pytest.mark.asyncio
    async def test_permission_inheritance(self, multi_client_websocket_simulation):
        """Test that permission inheritance and override mechanisms work correctly."""
        # Create clients with different roles
        admin_client = await multi_client_websocket_simulation(user_id="admin", roles=["admin"])
        user_client = await multi_client_websocket_simulation(user_id="user", roles=["editor"])
        
        # Connect clients to the same document
        doc_id = "test-permission-inheritance-doc"
        await admin_client.connect(doc_id=doc_id)
        await user_client.connect(doc_id=doc_id)
        
        try:
            # Admin creates initial cells
            await admin_client.update_document({
                "cell1": "print('Cell 1')",
                "cell2": "print('Cell 2')",
                "metadata": {"cells": {"cell1": {}, "cell2": {}}}
            })
            
            # Mock permission inheritance system
            with patch('notebook.collab.permissions.get_effective_permission') as mock_perm:
                # Define permission inheritance logic
                def get_effective_permission(user_id, resource_id, action):
                    # Document-level permission: editor can edit all cells by default
                    if resource_id == doc_id:
                        return True
                    
                    # Cell-level override: user cannot edit cell2
                    if resource_id == "cell2" and user_id == "user" and action == "edit":
                        return False
                    
                    # Inherit from document-level permission
                    return True
                
                mock_perm.side_effect = get_effective_permission
                
                # User should be able to edit cell1 (inherited from document permission)
                await user_client.update_document({"cell1": "print('Updated Cell 1')"})  
                
                # User should NOT be able to edit cell2 (overridden at cell level)
                with pytest.raises(Exception):
                    await user_client.update_document({"cell2": "print('Trying to update Cell 2')"})  
            
            # Verify document state reflects permission inheritance
            doc_state = await admin_client.get_document_state()
            assert "print('Updated Cell 1')" in doc_state["cell1"]
            assert "print('Cell 2')" in doc_state["cell2"]
        finally:
            # Disconnect clients
            await admin_client.disconnect()
            await user_client.disconnect()
    
    @pytest.mark.asyncio
    async def test_admin_override_permissions(self, multi_client_websocket_simulation):
        """Test that admin users can override normal permission flow."""
        # Create clients with different roles
        admin_client = await multi_client_websocket_simulation(user_id="admin", roles=["admin"])
        owner_client = await multi_client_websocket_simulation(user_id="owner", roles=["owner"])
        
        # Connect clients to the same document
        doc_id = "test-admin-override-doc"
        await admin_client.connect(doc_id=doc_id)
        await owner_client.connect(doc_id=doc_id)
        
        try:
            # Owner creates initial document with locked cell
            await owner_client.update_document({
                "cell1": "print('Locked cell')",
                "locks": {"cell1": {"locked_by": "owner", "locked_at": "2023-01-01T12:00:00Z"}}
            })
            
            # Mock lock system to simulate cell locking
            with patch('notebook.collab.locks.check_lock_status') as mock_lock:
                # Define lock checking logic
                def check_lock_status(cell_id, user_id):
                    # Cell is locked by owner
                    if cell_id == "cell1" and user_id != "owner":
                        return {"locked": True, "locked_by": "owner"}
                    return {"locked": False}
                
                mock_lock.side_effect = check_lock_status
                
                # Admin should be able to override the lock with force flag
                with patch('notebook.collab.locks.can_override_lock') as mock_override:
                    # Admin can override locks
                    mock_override.return_value = True
                    
                    # Admin overrides the lock and edits the cell
                    await admin_client.update_document({
                        "cell1": "print('Admin override')",
                        "locks": {"cell1": {"force_unlock": True}}
                    })
            
            # Verify admin was able to override the lock
            doc_state = await owner_client.get_document_state()
            assert "print('Admin override')" in doc_state["cell1"]
            
            # Verify lock status was updated
            if "locks" in doc_state:
                assert "cell1" not in doc_state["locks"] or \
                       doc_state["locks"]["cell1"].get("locked") is not True
        finally:
            # Disconnect clients
            await admin_client.disconnect()
            await owner_client.disconnect()
    
    @pytest.mark.asyncio
    async def test_jupyterhub_integration(self, multi_client_websocket_simulation):
        """Test that permissions integrate with JupyterHub authentication."""
        # Mock JupyterHub authentication data
        jupyterhub_user_data = {
            "hub_user": {
                "name": "hub_user",
                "admin": False,
                "scopes": ["access:servers", "notebooks:collaborative:edit"]
            },
            "hub_admin": {
                "name": "hub_admin",
                "admin": True,
                "scopes": ["access:servers", "notebooks:collaborative:admin"]
            }
        }
        
        # Create clients with JupyterHub identities
        with patch('notebook.collab.auth.get_jupyterhub_user') as mock_hub_user:
            # Mock JupyterHub user data retrieval
            def get_hub_user(token):
                if token == "user_token":
                    return jupyterhub_user_data["hub_user"]
                elif token == "admin_token":
                    return jupyterhub_user_data["hub_admin"]
                return None
            
            mock_hub_user.side_effect = get_hub_user
            
            # Create clients with different JupyterHub tokens
            hub_user_client = await multi_client_websocket_simulation(user_id="hub_user")
            hub_admin_client = await multi_client_websocket_simulation(user_id="hub_admin")
            
            # Mock token validation
            with patch('notebook.collab.auth.validate_jupyterhub_token') as mock_validate:
                mock_validate.return_value = True
                
                # Connect clients with their tokens
                doc_id = "test-jupyterhub-doc"
                
                # Mock the WebSocket connection to include token
                with patch.object(hub_user_client, 'connect') as mock_user_connect:
                    mock_user_connect.return_value = hub_user_client
                    await hub_user_client.connect(doc_id=doc_id)
                
                with patch.object(hub_admin_client, 'connect') as mock_admin_connect:
                    mock_admin_connect.return_value = hub_admin_client
                    await hub_admin_client.connect(doc_id=doc_id)
                
                try:
                    # Mock permission mapping from JupyterHub scopes to roles
                    with patch('notebook.collab.permissions.map_jupyterhub_scopes_to_role') as mock_map:
                        def map_scopes_to_role(scopes):
                            if "notebooks:collaborative:admin" in scopes:
                                return "admin"
                            elif "notebooks:collaborative:edit" in scopes:
                                return "editor"
                            elif "notebooks:collaborative:comment" in scopes:
                                return "commenter"
                            else:
                                return "viewer"
                        
                        mock_map.side_effect = map_scopes_to_role
                        
                        # Admin should be able to create content
                        await hub_admin_client.update_document({"cell1": "print('Admin content')"})  
                        
                        # User with edit scope should be able to edit
                        await hub_user_client.update_document({"cell2": "print('User content')"})  
                        
                        # Verify document state reflects both edits
                        doc_state = await hub_admin_client.get_document_state()
                        assert "print('Admin content')" in doc_state["cell1"]
                        assert "print('User content')" in doc_state["cell2"]
                finally:
                    # Disconnect clients
                    if hub_user_client.connected:
                        await hub_user_client.disconnect()
                    if hub_admin_client.connected:
                        await hub_admin_client.disconnect()
    
    @pytest.mark.asyncio
    async def test_audit_logging(self, multi_client_websocket_simulation):
        """Test that permission-related actions are properly logged for audit purposes."""
        # Create clients with different roles
        admin_client = await multi_client_websocket_simulation(user_id="admin", roles=["admin"])
        user_client = await multi_client_websocket_simulation(user_id="user", roles=["viewer"])
        
        # Connect clients to the same document
        doc_id = "test-audit-logging-doc"
        await admin_client.connect(doc_id=doc_id)
        await user_client.connect(doc_id=doc_id)
        
        # Mock audit logging system
        audit_logs = []
        
        with patch('notebook.collab.audit.log_permission_event') as mock_audit_log:
            # Define audit logging function
            def log_permission_event(event_type, user_id, resource_id, action, result, metadata=None):
                log_entry = {
                    "event_type": event_type,
                    "user_id": user_id,
                    "resource_id": resource_id,
                    "action": action,
                    "result": result,
                    "timestamp": "2023-01-01T12:00:00Z",  # Mock timestamp
                    "metadata": metadata or {}
                }
                audit_logs.append(log_entry)
            
            mock_audit_log.side_effect = log_permission_event
            
            try:
                # Admin creates initial content
                await admin_client.update_document({"cell1": "print('Initial content')"})  
                
                # Admin changes user's role from viewer to editor
                await admin_client.update_document({
                    "permissions": {"user": "editor"}
                })
                
                # Mock permission check to log the attempt
                with patch('notebook.collab.permissions.check_permission') as mock_check:
                    # First deny, then allow after role change
                    mock_check.side_effect = [False, True]
                    
                    # First attempt should fail and be logged
                    with pytest.raises(Exception):
                        await user_client.update_document({"cell1": "print('Unauthorized edit')"})  
                    
                    # Second attempt should succeed after role change
                    await user_client.update_document({"cell1": "print('Authorized edit')"})  
                
                # Verify audit logs contain the expected events
                permission_change_logs = [log for log in audit_logs if log["event_type"] == "permission_change"]
                assert len(permission_change_logs) > 0
                assert any(log["user_id"] == "admin" and log["action"] == "grant" for log in permission_change_logs)
                
                access_attempt_logs = [log for log in audit_logs if log["event_type"] == "access_attempt"]
                assert len(access_attempt_logs) > 0
                assert any(log["user_id"] == "user" and log["result"] == "denied" for log in access_attempt_logs)
                assert any(log["user_id"] == "user" and log["result"] == "allowed" for log in access_attempt_logs)
            finally:
                # Disconnect clients
                await admin_client.disconnect()
                await user_client.disconnect()
import pytest
import asyncio
import json
import os
from unittest.mock import patch, MagicMock

# Skip tests if collaboration dependencies are not installed
pytestmark = pytest.mark.skipif(
    not pytest.importorskip('tests.conftest').HAS_COLLABORATION_DEPS,
    reason='Collaboration dependencies not installed'
)


class TestPermissionsIntegration:
    """Integration tests for the permission system in collaborative editing."""

    @pytest.mark.asyncio
    async def test_role_based_access_control(self, jp_ws_client, create_test_document):
        """Test that role-based access controls are correctly enforced across multiple clients."""
        # Create a test document
        doc_path = await create_test_document(name="permissions-test.ipynb")
        doc_name = os.path.basename(doc_path)

        # Create clients with different roles
        owner_client = await jp_ws_client(user_id="owner", roles=["owner"])
        admin_client = await jp_ws_client(user_id="admin", roles=["admin"])
        editor_client = await jp_ws_client(user_id="editor", roles=["editor"])
        commenter_client = await jp_ws_client(user_id="commenter", roles=["commenter"])
        viewer_client = await jp_ws_client(user_id="viewer", roles=["viewer"])

        # Connect all clients to the document
        await owner_client.connect(doc_name)
        await admin_client.connect(doc_name)
        await editor_client.connect(doc_name)
        await commenter_client.connect(doc_name)
        await viewer_client.connect(doc_name)

        try:
            # Owner should be able to modify the document
            await owner_client.update_cell("cell1", "print('Hello from owner')")
            
            # Admin should be able to modify the document
            await admin_client.update_cell("cell2", "print('Hello from admin')")
            
            # Editor should be able to modify the document
            await editor_client.update_cell("cell3", "print('Hello from editor')")
            
            # Commenter should NOT be able to modify the document
            with pytest.raises(Exception):
                await commenter_client.update_cell("cell4", "print('Hello from commenter')")
            
            # Viewer should NOT be able to modify the document
            with pytest.raises(Exception):
                await viewer_client.update_cell("cell5", "print('Hello from viewer')")
            
            # Wait for updates to propagate
            await asyncio.sleep(1)
            
            # Verify document state reflects permissions
            doc_state = await owner_client.get_document_state()
            assert "Hello from owner" in str(doc_state)
            assert "Hello from admin" in str(doc_state)
            assert "Hello from editor" in str(doc_state)
            assert "Hello from commenter" not in str(doc_state)
            assert "Hello from viewer" not in str(doc_state)
        finally:
            # Disconnect all clients
            await owner_client.disconnect()
            await admin_client.disconnect()
            await editor_client.disconnect()
            await commenter_client.disconnect()
            await viewer_client.disconnect()

    @pytest.mark.asyncio
    async def test_permission_changes_propagation(self, jp_ws_client, create_test_document):
        """Test that permission changes are immediately propagated to all clients."""
        # Create a test document
        doc_path = await create_test_document(name="permission-changes-test.ipynb")
        doc_name = os.path.basename(doc_path)

        # Create clients with different roles
        admin_client = await jp_ws_client(user_id="admin", roles=["admin"])
        user_client = await jp_ws_client(user_id="user", roles=["viewer"])

        # Connect clients to the document
        await admin_client.connect(doc_name)
        await user_client.connect(doc_name)

        try:
            # Admin creates initial content
            await admin_client.update_cell("cell1", "print('Initial content')")
            
            # User with viewer role should NOT be able to edit
            with pytest.raises(Exception):
                await user_client.update_cell("cell1", "print('Trying to edit as viewer')")
            
            # Admin changes user's role from viewer to editor
            # In a real implementation, this would be a proper permission update message
            await admin_client.send({
                "type": "update_permissions",
                "user_id": "user",
                "role": "editor"
            })
            
            # Wait for permission change to propagate
            await asyncio.sleep(1)
            
            # After permission change, user should be able to edit
            await user_client.update_cell("cell1", "print('Edited after permission change')")
            
            # Wait for updates to propagate
            await asyncio.sleep(1)
            
            # Verify document state reflects the edit after permission change
            doc_state = await admin_client.get_document_state()
            assert "Edited after permission change" in str(doc_state)
        finally:
            # Disconnect clients
            await admin_client.disconnect()
            await user_client.disconnect()

    @pytest.mark.asyncio
    async def test_cell_level_permissions(self, jp_ws_client, create_test_document):
        """Test that cell-level permissions override document-level permissions."""
        # Create a test document
        doc_path = await create_test_document(name="cell-permissions-test.ipynb")
        doc_name = os.path.basename(doc_path)

        # Create clients with different roles
        owner_client = await jp_ws_client(user_id="owner", roles=["owner"])
        editor_client = await jp_ws_client(user_id="editor", roles=["editor"])

        # Connect clients to the document
        await owner_client.connect(doc_name)
        await editor_client.connect(doc_name)

        try:
            # Owner creates initial cells
            await owner_client.update_cell("cell1", "print('Cell 1')")
            await owner_client.update_cell("cell2", "print('Cell 2')")
            await owner_client.update_cell("cell3", "print('Cell 3')")
            
            # Owner sets cell-level permissions
            # In a real implementation, this would be a proper cell permission update message
            await owner_client.send({
                "type": "update_cell_permissions",
                "cell_id": "cell2",
                "permissions": {
                    "editor": "view"  # Restrict editor to view-only for cell2
                }
            })
            
            # Wait for permission change to propagate
            await asyncio.sleep(1)
            
            # Editor should be able to edit cell1
            await editor_client.update_cell("cell1", "print('Updated Cell 1')")
            
            # Editor should NOT be able to edit cell2 due to cell-level permission
            with pytest.raises(Exception):
                await editor_client.update_cell("cell2", "print('Trying to update Cell 2')")
            
            # Editor should be able to edit cell3
            await editor_client.update_cell("cell3", "print('Updated Cell 3')")
            
            # Wait for updates to propagate
            await asyncio.sleep(1)
            
            # Verify document state reflects cell-level permissions
            doc_state = await owner_client.get_document_state()
            assert "Updated Cell 1" in str(doc_state)
            assert "Cell 2" in str(doc_state)
            assert "Trying to update Cell 2" not in str(doc_state)
            assert "Updated Cell 3" in str(doc_state)
        finally:
            # Disconnect clients
            await owner_client.disconnect()
            await editor_client.disconnect()

    @pytest.mark.asyncio
    async def test_admin_override_permissions(self, jp_ws_client, create_test_document):
        """Test that admin users can override normal permission flow."""
        # Create a test document
        doc_path = await create_test_document(name="admin-override-test.ipynb")
        doc_name = os.path.basename(doc_path)

        # Create clients with different roles
        admin_client = await jp_ws_client(user_id="admin", roles=["admin"])
        owner_client = await jp_ws_client(user_id="owner", roles=["owner"])
        editor_client = await jp_ws_client(user_id="editor", roles=["editor"])

        # Connect clients to the document
        await admin_client.connect(doc_name)
        await owner_client.connect(doc_name)
        await editor_client.connect(doc_name)

        try:
            # Owner creates initial cell and locks it
            await owner_client.update_cell("cell1", "print('Locked cell')")
            
            # Owner locks the cell
            await owner_client.send({
                "type": "lock_cell",
                "cell_id": "cell1",
                "user_id": "owner"
            })
            
            # Wait for lock to propagate
            await asyncio.sleep(1)
            
            # Editor should NOT be able to edit the locked cell
            with pytest.raises(Exception):
                await editor_client.update_cell("cell1", "print('Trying to edit locked cell')")
            
            # Admin should be able to override the lock
            await admin_client.send({
                "type": "force_unlock_cell",
                "cell_id": "cell1"
            })
            
            # Wait for unlock to propagate
            await asyncio.sleep(1)
            
            # Admin edits the cell after unlocking
            await admin_client.update_cell("cell1", "print('Admin override')")
            
            # Wait for updates to propagate
            await asyncio.sleep(1)
            
            # Verify admin was able to override the lock
            doc_state = await owner_client.get_document_state()
            assert "Admin override" in str(doc_state)
        finally:
            # Disconnect clients
            await admin_client.disconnect()
            await owner_client.disconnect()
            await editor_client.disconnect()

    @pytest.mark.asyncio
    async def test_permission_inheritance(self, jp_ws_client, create_test_document):
        """Test that permission inheritance and override mechanisms work correctly."""
        # Create a test document with nested cells
        doc_path = await create_test_document(name="permission-inheritance-test.ipynb")
        doc_name = os.path.basename(doc_path)

        # Create clients with different roles
        admin_client = await jp_ws_client(user_id="admin", roles=["admin"])
        user_client = await jp_ws_client(user_id="user", roles=["editor"])

        # Connect clients to the document
        await admin_client.connect(doc_name)
        await user_client.connect(doc_name)

        try:
            # Admin creates initial cells and sets up a cell group
            await admin_client.update_cell("cell1", "print('Cell 1')")
            await admin_client.update_cell("cell2", "print('Cell 2')")
            await admin_client.update_cell("cell3", "print('Cell 3')")
            
            # Admin creates a cell group with restricted permissions
            await admin_client.send({
                "type": "create_cell_group",
                "group_id": "group1",
                "cell_ids": ["cell2", "cell3"],
                "permissions": {
                    "user": "view"  # Restrict user to view-only for the group
                }
            })
            
            # Wait for group creation to propagate
            await asyncio.sleep(1)
            
            # User should be able to edit cell1 (not in the restricted group)
            await user_client.update_cell("cell1", "print('Updated Cell 1')")
            
            # User should NOT be able to edit cell2 (in the restricted group)
            with pytest.raises(Exception):
                await user_client.update_cell("cell2", "print('Trying to update Cell 2')")
            
            # User should NOT be able to edit cell3 (in the restricted group)
            with pytest.raises(Exception):
                await user_client.update_cell("cell3", "print('Trying to update Cell 3')")
            
            # Wait for updates to propagate
            await asyncio.sleep(1)
            
            # Verify document state reflects permission inheritance
            doc_state = await admin_client.get_document_state()
            assert "Updated Cell 1" in str(doc_state)
            assert "Cell 2" in str(doc_state)
            assert "Cell 3" in str(doc_state)
            assert "Trying to update Cell 2" not in str(doc_state)
            assert "Trying to update Cell 3" not in str(doc_state)
        finally:
            # Disconnect clients
            await admin_client.disconnect()
            await user_client.disconnect()

    @pytest.mark.asyncio
    async def test_authentication_integration(self, jp_ws_client, create_test_document):
        """Test that permissions integrate correctly with authentication systems."""
        # Create a test document
        doc_path = await create_test_document(name="auth-integration-test.ipynb")
        doc_name = os.path.basename(doc_path)

        # Create a client with proper authentication
        authenticated_client = await jp_ws_client(user_id="auth_user", roles=["editor"])

        # Connect authenticated client to document
        await authenticated_client.connect(doc_name)

        try:
            # Create initial content as authenticated user
            await authenticated_client.update_cell("cell1", "print('Authenticated content')")
            
            # Create a client with invalid authentication
            # In a real implementation, this would be rejected at the WebSocket connection level
            # Here we simulate by creating a client with no roles
            unauthenticated_client = await jp_ws_client(user_id="unauth_user", roles=[])
            
            # Attempt to connect with invalid authentication should fail
            with pytest.raises(Exception):
                await unauthenticated_client.connect(doc_name)
            
            # Wait for any potential updates to propagate
            await asyncio.sleep(1)
            
            # Verify document state is unchanged
            doc_state = await authenticated_client.get_document_state()
            assert "Authenticated content" in str(doc_state)
        finally:
            # Disconnect clients
            await authenticated_client.disconnect()
            # Ensure unauthenticated client is disconnected if it somehow connected
            try:
                await unauthenticated_client.disconnect()
            except:
                pass

    @pytest.mark.asyncio
    async def test_permission_persistence(self, jp_ws_client, create_test_document, simulate_server_restart):
        """Test that permissions persist across server restarts."""
        # Create a test document
        doc_path = await create_test_document(name="permission-persistence-test.ipynb")
        doc_name = os.path.basename(doc_path)

        # Create clients with different roles
        admin_client = await jp_ws_client(user_id="admin", roles=["admin"])
        user_client = await jp_ws_client(user_id="user", roles=["viewer"])

        # Connect clients to the document
        await admin_client.connect(doc_name)
        await user_client.connect(doc_name)

        try:
            # Admin creates initial content
            await admin_client.update_cell("cell1", "print('Initial content')")
            
            # User with viewer role should NOT be able to edit
            with pytest.raises(Exception):
                await user_client.update_cell("cell1", "print('Trying to edit as viewer')")
            
            # Admin changes user's role from viewer to editor
            await admin_client.send({
                "type": "update_permissions",
                "user_id": "user",
                "role": "editor"
            })
            
            # Wait for permission change to propagate
            await asyncio.sleep(1)
            
            # Disconnect clients before server restart
            await admin_client.disconnect()
            await user_client.disconnect()
            
            # Simulate server restart
            await simulate_server_restart()
            
            # Reconnect clients after server restart
            await admin_client.connect(doc_name)
            await user_client.connect(doc_name)
            
            # Wait for reconnection to complete
            await asyncio.sleep(1)
            
            # User should still have editor role after server restart
            await user_client.update_cell("cell1", "print('Edited after server restart')")
            
            # Wait for updates to propagate
            await asyncio.sleep(1)
            
            # Verify document state reflects the edit after server restart
            doc_state = await admin_client.get_document_state()
            assert "Edited after server restart" in str(doc_state)
        finally:
            # Disconnect clients
            await admin_client.disconnect()
            await user_client.disconnect()

    @pytest.mark.asyncio
    async def test_audit_logging(self, jp_ws_client, create_test_document):
        """Test that permission-related actions are properly logged for audit purposes."""
        # Create a test document
        doc_path = await create_test_document(name="audit-logging-test.ipynb")
        doc_name = os.path.basename(doc_path)

        # Create clients with different roles
        admin_client = await jp_ws_client(user_id="admin", roles=["admin"])
        user_client = await jp_ws_client(user_id="user", roles=["viewer"])

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
            
            # Connect clients to the document
            await admin_client.connect(doc_name)
            await user_client.connect(doc_name)

            try:
                # Admin creates initial content
                await admin_client.update_cell("cell1", "print('Initial content')")
                
                # User with viewer role attempts to edit (should fail and be logged)
                with pytest.raises(Exception):
                    await user_client.update_cell("cell1", "print('Unauthorized edit')")
                
                # Admin changes user's role from viewer to editor
                await admin_client.send({
                    "type": "update_permissions",
                    "user_id": "user",
                    "role": "editor"
                })
                
                # Wait for permission change to propagate
                await asyncio.sleep(1)
                
                # User with editor role attempts to edit (should succeed and be logged)
                await user_client.update_cell("cell1", "print('Authorized edit')")
                
                # Wait for updates to propagate
                await asyncio.sleep(1)
                
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
# Permissions System

Jupyter Notebook v7 includes a comprehensive permissions system for collaborative editing that enables fine-grained access control at both document and cell levels. This system ensures that collaborative notebooks can be securely shared with appropriate access restrictions.

```{note}
The permissions system is only active when collaborative editing is enabled. See the [Collaboration Overview](./index.md) for information on enabling and configuring collaborative features.
```

## Permission Roles

The collaborative editing environment in Jupyter Notebook v7 implements a role-based access control system with the following roles:

### Document-Level Roles

| Role | Description | Capabilities |
|------|-------------|-------------|
| Owner | Full control of the document | Can modify content, manage permissions, delete the document, and control collaborative sessions |
| Admin | Administrative control | Can modify content, manage permissions, and control collaborative sessions |
| Editor | Content modification | Can modify notebook content and execute cells |
| Commenter | Discussion only | Can add comments but cannot modify notebook content |
| Viewer | Read-only access | Can only view the notebook content and outputs |

### Cell-Level Roles

For more granular control, permissions can also be set at the cell level:

| Role | Description | Capabilities |
|------|-------------|-------------|
| Cell Owner | Primary control over a cell | Has full control over an individual cell |
| Cell Editor | Content modification | Can modify the specific cell's content |
| Cell Executor | Execution only | Can run the cell but not modify its content |
| Cell Commenter | Discussion only | Can attach comments to the cell |
| Cell Viewer | Read-only access | Can only view the cell content and output |

## Managing Permissions

### Document Permissions

To manage document-level permissions:

1. Open the notebook in collaborative mode
2. Click the "Collaboration" button in the toolbar
3. Select "Manage Permissions" from the dropdown menu
4. In the permissions dialog, you can:
   - Add users or groups by username/email
   - Assign roles to users or groups
   - Remove users or groups from the permissions list
   - Set default access for unauthenticated or new users

### Cell Permissions

To manage cell-level permissions:

1. Right-click on a cell or click the cell menu (three dots)
2. Select "Cell Permissions" from the context menu
3. In the cell permissions dialog, you can:
   - Override document-level permissions for specific users
   - Assign cell-specific roles
   - Reset to inherit document-level permissions

## Permission Inheritance and Precedence

Permissions in Jupyter Notebook v7 follow a hierarchical model:

1. **System-level permissions** (from JupyterHub) take precedence over all others
2. **Document-level permissions** establish baseline access for the notebook
3. **Cell-level permissions** can override document permissions for greater specificity
4. **Admin-level permissions** can override normal permission flow in administrative scenarios

When a user attempts an action, the permission check follows this sequence:

1. Check if the user has system-level permission (if using JupyterHub)
2. Check if the user has an explicit cell-level permission (if applicable)
3. Fall back to document-level permission if no cell-specific permission exists
4. Apply the default permission if no explicit permission is found

## JupyterHub Integration

When using Jupyter Notebook v7 with JupyterHub, the permissions system integrates with JupyterHub's authentication and scope-based permission system.

### Scope Mapping

The following table shows how collaborative roles map to JupyterHub scopes:

| Collaborative Role | JupyterHub Scope |
|-------------------|-------------------|
| Owner | notebooks:collaborative:own, notebooks:collaborative:admin, notebooks:collaborative:edit |
| Admin | notebooks:collaborative:admin, notebooks:collaborative:edit |
| Editor | notebooks:collaborative:edit |
| Commenter | notebooks:collaborative:comment |
| Viewer | notebooks:collaborative:read |

This mapping allows JupyterHub administrators to centrally control which users have access to specific collaborative capabilities by assigning the appropriate scopes.

### Authentication Flow

When a user attempts to join a collaborative session:

1. The user's JupyterHub identity is verified
2. The system checks if the user has appropriate JupyterHub scopes
3. Document and cell-level permissions are evaluated
4. Access is granted based on the most restrictive applicable permission

## Configuration Options

### Server Configuration

The following options can be set in `jupyter_notebook_config.py` to configure the permissions system:

```python
# Enable or disable the collaborative permissions system
c.CollaborationManager.permissions_enabled = True

# Default role for new users (viewer, commenter, editor, admin, owner)
c.CollaborationManager.default_role = 'viewer'

# Allow or disallow public access (without authentication)
c.CollaborationManager.allow_public_access = False

# Maximum number of users that can be assigned permissions per document
c.CollaborationManager.max_users_per_document = 50

# Enable or disable cell-level permissions
c.CollaborationManager.cell_permissions_enabled = True
```

### Permission Enforcement

Permissions are enforced at multiple layers to ensure security:

1. **Frontend Layer**: UI elements adapt based on permission checks
2. **WebSocket Handler Layer**: All incoming CRDT updates are validated against permission rules
3. **Server Extension Layer**: Final validation before applying changes to server-side document state
4. **Storage Layer**: Permission records are persisted in the collaboration database

This multi-layered approach provides defense in depth, ensuring that even if client-side permission checks are bypassed, server-side validation will prevent unauthorized operations.

## Audit Logging

All permission-related actions are logged for security and compliance purposes:

- Permission changes (who changed permissions, for whom, and what changed)
- Permission check failures (attempted actions that were denied)
- Administrative overrides of permissions
- Cell lock acquisitions and releases

Logs include the following information:

- Timestamp of the action
- User ID and username performing the action
- Target user ID and username (if applicable)
- Action type and result
- Resource identifier (document ID, cell ID)
- Permission context (user's role at the time)

## Examples

### Example 1: Research Team Collaboration

A research team might set up permissions as follows:

```python
# Principal Investigator has owner access
notebook.set_permission('user:pi@example.org', 'owner')

# Senior researchers have admin access
notebook.set_permission('group:senior-researchers', 'admin')

# Research assistants have editor access
notebook.set_permission('group:research-assistants', 'editor')

# External reviewers have commenter access
notebook.set_permission('group:external-reviewers', 'commenter')

# Other department members have viewer access
notebook.set_permission('group:department', 'viewer')
```

### Example 2: Educational Setting

In a classroom setting, permissions might be configured as:

```python
# Instructors have admin access
notebook.set_permission('group:instructors', 'admin')

# Teaching assistants have editor access
notebook.set_permission('group:teaching-assistants', 'editor')

# Students have commenter access by default
notebook.set_permission('group:students', 'commenter')

# For specific cells (e.g., exercise cells), grant students editor access
cell.set_permission('group:students', 'cell_editor')

# For solution cells, restrict to viewer access only
solution_cell.set_permission('group:students', 'cell_viewer')
```

### Example 3: Corporate Environment

In a corporate setting with sensitive data:

```python
# Data scientists have editor access to the notebook
notebook.set_permission('group:data-scientists', 'editor')

# Analysts have commenter access to the notebook
notebook.set_permission('group:analysts', 'commenter')

# For cells containing sensitive data, restrict access
sensitive_cell.set_permission('group:data-scientists', 'cell_viewer')
sensitive_cell.set_permission('user:compliance@example.com', 'cell_owner')

# For cells with proprietary algorithms, limit execution
algorithm_cell.set_permission('group:data-scientists', 'cell_executor')
```

## Troubleshooting

### Common Permission Issues

1. **Unable to edit a cell despite having editor access**
   - Check if another user has locked the cell
   - Verify if cell-level permissions override your document permissions
   - Ensure your JupyterHub token has the necessary scopes

2. **Cannot see the Collaboration menu**
   - Verify that collaborative editing is enabled
   - Check if you have at least viewer permission for the document
   - Ensure your authentication is working correctly

3. **Permission changes not taking effect**
   - Refresh the page to ensure you have the latest permission data
   - Check if there are conflicting permissions at different levels
   - Verify that the permission change was saved successfully

### Permission Debugging

To debug permission issues, you can enable verbose permission logging:

```python
c.CollaborationManager.permission_log_level = 'DEBUG'
```

This will provide detailed logs of all permission checks, which can help identify why a particular action is being denied.
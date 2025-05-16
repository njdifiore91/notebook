# Collaborative Editing in Jupyter Notebook v7

Jupyter Notebook v7 introduces comprehensive real-time collaborative editing capabilities, enabling multiple users to simultaneously work on the same notebook document. This feature leverages the Yjs Conflict-free Replicated Data Type (CRDT) framework to provide a seamless collaborative experience.

```{contents} Table of Contents
:depth: 3
:local:
```

## Overview

The collaborative editing system in Jupyter Notebook v7 allows multiple users to edit notebook documents simultaneously with the following key capabilities:

- **Real-time synchronization** of notebook content (code cells, markdown cells, outputs)
- **User presence awareness** showing who is viewing/editing the notebook
- **Cursor/selection synchronization** to visualize other users' work areas
- **Cell-level locking mechanism** to prevent editing conflicts
- **Change history and versioning** system for tracking individual contributions
- **Permissions system** with fine-grained access control
- **Comment and review system** for discussing specific cells

## Getting Started

### Installation

The collaborative editing features are built into Jupyter Notebook v7 but require additional dependencies to be installed:

```bash
pip install jupyter-collaboration
```

or with conda:

```bash
conda install -c conda-forge jupyter-collaboration
```

After installing the extension, restart the Jupyter Server for the extension to be loaded.

### Enabling Collaboration

Collaboration is disabled by default. To enable it, you can use one of the following methods:

#### Command Line

Start Jupyter Notebook with the collaboration flag:

```bash
jupyter notebook --collaborative
```

#### Configuration File

Add the following to your Jupyter configuration file (`jupyter_notebook_config.py`):

```python
c.NotebookApp.collaborative = True
```

## Using Collaborative Features

### Sharing a Notebook

When collaboration is enabled, each notebook has a "Share" button in the toolbar. Clicking this button opens the sharing dialog with options to:

1. **Generate a shareable link** - Creates a URL that can be shared with collaborators
2. **Set permissions** - Configure access levels for collaborators
3. **View current collaborators** - See who has access to the notebook

### User Presence

When multiple users are editing the same notebook, you'll see:

- **User avatars** in the collaboration panel showing who is currently viewing the document
- **Colored cursors** indicating each user's current position in the notebook
- **Highlighted selections** showing text selected by other users
- **Status indicators** showing whether users are active, idle, or away

### Real-time Editing

All changes made by any collaborator are instantly synchronized to all other users. This includes:

- Adding, editing, and deleting cells
- Changing cell types
- Executing cells and viewing outputs
- Reordering cells
- Editing markdown content

The Yjs CRDT framework ensures that concurrent edits are merged correctly without conflicts, even when users are editing the same area of the document.

### Cell Locking

To prevent conflicts when multiple users are working on the same notebook, Jupyter Notebook v7 implements a cell locking mechanism:

- **Automatic locking** - When a user begins editing a cell, it's automatically locked for exclusive editing
- **Lock indicators** - Locked cells display the avatar of the user who is currently editing them
- **Lock release** - Locks are automatically released when the user finishes editing or after a period of inactivity
- **Manual locking** - Users can explicitly lock cells for longer editing sessions

To manually lock a cell:

1. Right-click on the cell
2. Select "Lock Cell" from the context menu

To release a lock:

1. Right-click on the cell you've locked
2. Select "Release Lock" from the context menu

### Permissions and Access Control

Jupyter Notebook v7 provides fine-grained access control for collaborative notebooks with the following permission roles:

- **Owner** - Full control including permission management
- **Admin** - Can modify content and some permissions
- **Editor** - Can modify notebook content
- **Commenter** - Can add comments but not edit content
- **Viewer** - Read-only access

To manage permissions:

1. Click the "Share" button in the toolbar
2. Select the "Permissions" tab
3. Add collaborators by email or username
4. Assign appropriate permission roles
5. Click "Save" to apply the changes

Permissions can be set at both the document level and the cell level for more granular control.

### Comments and Reviews

The comment system allows collaborators to discuss specific cells without modifying the content:

1. **Adding comments**:
   - Click the comment icon in the cell toolbar or use the right-click menu
   - Enter your comment text
   - Click "Post" to add the comment

2. **Viewing comments**:
   - Cells with comments show a comment indicator with the number of comments
   - Click the indicator to view the comment thread

3. **Replying to comments**:
   - Open a comment thread
   - Type your reply in the text box
   - Click "Reply" to add your response

4. **Resolving comments**:
   - Once an issue is addressed, click "Resolve" on the comment
   - Resolved comments are collapsed but can be expanded if needed

### Version History

The version history feature tracks changes to the notebook over time:

1. **Viewing history**:
   - Click the "History" button in the toolbar
   - Browse the timeline of changes
   - Select a version to view its state

2. **Comparing versions**:
   - Select two versions in the history panel
   - Click "Compare" to see the differences highlighted

3. **Restoring previous versions**:
   - Select the version you want to restore
   - Click "Restore" to revert to that version
   - The restoration is tracked as a new version in the history

## Advanced Configuration

### Server Configuration Options

The following options can be configured in `jupyter_notebook_config.py`:

```python
# Enable/disable collaboration features
c.NotebookApp.collaborative = True

# Configure the collaboration WebSocket endpoint
c.NotebookApp.collaboration_endpoint = '/collaboration'

# Set the persistence backend for collaboration data
c.NotebookApp.collaboration_persistence = 'file'  # Options: 'file', 'database'

# Configure database connection for collaboration persistence (if using 'database')
c.NotebookApp.collaboration_database_url = 'sqlite:///jupyter_collaboration.db'

# Set the maximum number of versions to keep in history
c.NotebookApp.max_collaboration_versions = 100

# Configure default permission role for new collaborators
c.NotebookApp.default_collaboration_role = 'viewer'  # Options: 'viewer', 'commenter', 'editor', 'admin'

# Set the inactivity timeout for automatic lock release (in seconds)
c.NotebookApp.collaboration_lock_timeout = 60
```

### JupyterHub Integration

When using Jupyter Notebook v7 with JupyterHub, the collaboration features integrate with JupyterHub's authentication system:

- User identities from JupyterHub are used for collaboration presence
- JupyterHub user permissions can be mapped to notebook collaboration roles
- Administrators can configure collaboration settings at the hub level

Add the following to your JupyterHub configuration to enable collaboration:

```python
c.Spawner.args = ['--collaborative']
```

## Troubleshooting

### Common Issues

#### Connection Problems

**Symptom**: Collaboration features don't work or show "Disconnected" status

**Solutions**:
- Check that the collaboration extension is properly installed
- Verify that collaboration is enabled in the configuration
- Ensure WebSocket connections are not blocked by firewalls or proxies
- Check browser console for error messages

#### Permission Errors

**Symptom**: Unable to edit cells or see other users despite having the notebook open

**Solutions**:
- Verify that you have the correct permission role assigned
- Ask the notebook owner to check permission settings
- Ensure you're logged in with the correct account

#### Synchronization Issues

**Symptom**: Changes made by collaborators aren't appearing or are delayed

**Solutions**:
- Check your internet connection
- Refresh the page to re-establish the connection
- Verify that all users are using compatible versions of Jupyter Notebook

### Logs and Debugging

To enable detailed logging for collaboration features:

```bash
jupyter notebook --collaborative --log-level=DEBUG
```

Collaboration-specific logs will be prefixed with `[Collaboration]` in the server logs.

## Technical Details

The collaborative editing system in Jupyter Notebook v7 is built on several key technologies:

- **Yjs** - A CRDT framework that enables conflict-free real-time editing
- **y-websocket** - A WebSocket provider for Yjs that handles network communication
- **y-protocols/awareness** - A protocol for tracking user presence information

The system architecture includes:

1. **Client-side components**:
   - Collaboration Provider that integrates with the notebook model
   - Presence tracking for user awareness
   - UI components for visualization of collaborative features

2. **Server-side components**:
   - WebSocket handlers for real-time updates
   - Persistence layer for collaboration data
   - Permission management system
   - Comment and version history storage

## Further Reading

- [Yjs Documentation](https://docs.yjs.dev/)
- [Jupyter Notebook v7 Features](./notebook_7_features.md)
- [Configuring Jupyter Notebook](./configuration.md)
- [Troubleshooting Guide](./troubleshooting.md)
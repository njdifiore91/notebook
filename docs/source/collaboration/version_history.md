# Version History

## Overview

Jupyter Notebook v7 includes a comprehensive version history system as part of its collaborative editing environment. This feature allows you to track changes made to notebooks over time, view previous versions, compare differences, and restore content when needed.

The version history system provides:

- Automatic tracking of all changes made by collaborators
- A visual timeline of document modifications
- Ability to view and compare different versions of a notebook
- User attribution for all changes
- Options to restore previous versions or specific cells

## How Version History Works

The version history system is built on the Yjs Conflict-free Replicated Data Type (CRDT) framework that powers Jupyter Notebook v7's collaborative editing capabilities.

### Yjs Update Events

When any user makes changes to a notebook, these changes generate Yjs update events that are:

1. Captured by the local Collaboration Provider
2. Transmitted to the server via WebSocket
3. Stored in the Collaboration State Database
4. Broadcast to all connected clients
5. Indexed with timestamps and user information

These update events form the foundation of the version history system. Each update is stored with:

- A timestamp indicating when the change occurred
- The user ID of the person who made the change
- The specific operations performed (insertions, deletions, etc.)
- The affected cells and content

### Document Snapshots

In addition to storing individual update events, the system periodically creates complete document snapshots that:

- Provide efficient access to the notebook state at specific points in time
- Serve as reference points for comparing versions
- Enable faster restoration of previous states
- Reduce the computational overhead of reconstructing document history

## Using the Version History Viewer

The Version History Viewer is a dedicated interface component that allows you to explore and interact with the notebook's change history.

### Accessing Version History

To access the version history for a notebook:

1. Open a collaborative notebook
2. Click the "History" button in the collaboration toolbar
3. The Version History panel will appear, showing a timeline of changes

### Timeline Navigation

The timeline view displays:

- A chronological list of changes with timestamps
- User information for each change
- Brief descriptions of the modifications made
- Visual indicators for major changes or milestones

You can navigate through the timeline by:

- Scrolling through the list of changes
- Using the time-based filters to focus on specific periods
- Searching for changes by user or content

### Comparing Versions

To compare different versions of the notebook:

1. Select a version from the timeline
2. Click "Compare with Current" or select another version to compare with
3. The diff view will highlight:
   - Added content (typically in green)
   - Removed content (typically in red)
   - Modified cells with detailed change indicators
   - Unchanged content for context

The comparison view provides options to:

- Toggle between side-by-side and inline diff views
- Focus on specific cells or changes
- Filter changes by type (code, markdown, outputs)
- Adjust the level of context shown around changes

### Reverting Changes

The Version History Viewer allows you to restore previous versions in several ways:

1. **Full Notebook Reversion**:
   - Select the version you want to restore
   - Click "Restore This Version"
   - The entire notebook will revert to the selected state

2. **Selective Cell Restoration**:
   - Select the version containing the cell state you want to restore
   - In the diff view, locate the specific cell
   - Click "Restore This Cell" to bring back just that cell

3. **Change Undoing**:
   - Navigate to the specific change you want to undo
   - Click "Undo This Change" to reverse just that modification
   - Other changes made after this point will be preserved

When you revert changes, the system creates a new version that records the restoration action, preserving the complete history of the document.

## Configuration Options

The version history system can be configured through several options:

### Server-Side Configuration

Administrators can configure version history behavior in the Jupyter Server configuration:

```python
# In jupyter_server_config.py

# Enable or disable version history tracking
c.JupyterCollaboration.version_history_enabled = True

# Configure the version history storage backend
c.JupyterCollaboration.version_history_class = "jupyter_ydoc.SQLiteVersionHistory"

# Set storage parameters
c.JupyterCollaboration.version_history_kwargs = {
    "db_path": "/path/to/version_history.db",
    "auto_create_tables": True
}

# Set snapshot frequency (in seconds or by update count)
c.JupyterCollaboration.snapshot_interval_seconds = 300  # Every 5 minutes
c.JupyterCollaboration.snapshot_update_threshold = 50   # Or every 50 updates

# Configure retention policy
c.JupyterCollaboration.history_retention_days = 90  # Keep history for 90 days
```

### Client-Side Settings

Users can adjust their version history experience through settings:

1. Open the Settings menu
2. Navigate to "Collaboration" → "Version History"
3. Adjust available options such as:
   - Default comparison view (side-by-side or inline)
   - Number of changes to display in the timeline
   - Auto-refresh interval for the history panel
   - Display preferences for change indicators

## Server-Side Persistence

The version history system relies on server-side persistence to maintain the history of changes across sessions and user connections.

### Storage Backends

Jupyter Notebook v7 supports multiple storage backends for version history:

1. **SQLite** (default): Stores version history in a SQLite database file
   - Simple setup with no additional dependencies
   - Suitable for single-server deployments
   - Configured with `jupyter_ydoc.SQLiteVersionHistory`

2. **MongoDB**: Stores version history in a MongoDB database
   - Better performance for large-scale deployments
   - Supports distributed access across multiple servers
   - Configured with `jupyter_ydoc.MongoDBVersionHistory`

3. **Redis**: Uses Redis for high-performance history storage
   - Optimized for high-throughput collaborative environments
   - Provides fast access to recent history
   - Configured with `jupyter_ydoc.RedisVersionHistory`

4. **Custom**: Implement your own storage backend
   - Create a class that implements the `IVersionHistory` interface
   - Register it with the collaboration system
   - Configure with your custom class name

### Data Management

Administrators should consider the following aspects of version history data management:

1. **Storage Growth**: Version history data will grow over time as notebooks are edited
   - Monitor storage usage regularly
   - Implement appropriate retention policies
   - Consider database maintenance procedures

2. **Backup Procedures**: Include version history storage in backup routines
   - For SQLite: Back up the database file
   - For MongoDB/Redis: Follow standard database backup procedures
   - Test restoration procedures periodically

3. **Performance Optimization**:
   - Schedule regular database maintenance (reindexing, vacuuming)
   - Consider moving older history to archival storage
   - Adjust snapshot frequency based on usage patterns

## Examples

### Example 1: Viewing Recent Changes

To review recent changes to a collaborative notebook:

1. Open the notebook in collaborative mode
2. Click the "History" button in the collaboration toolbar
3. The Version History panel shows recent changes with user attribution
4. Click on any change to see what was modified
5. Use the timeline to navigate through the history of changes

### Example 2: Comparing with a Previous Version

To compare the current notebook with a previous version:

1. Open the Version History panel
2. Locate the version you want to compare with
3. Click "Compare with Current"
4. Review the highlighted differences:
   - Green highlights show added content
   - Red highlights show removed content
   - Changed cells are marked with a vertical bar
5. Navigate between changes using the diff navigation controls

### Example 3: Restoring a Previous Version

To restore the notebook to a previous state:

1. Open the Version History panel
2. Browse or search for the version you want to restore
3. Click on that version to view its contents
4. Click "Restore This Version"
5. Confirm the restoration when prompted
6. The notebook will revert to the selected version
7. A new entry will appear in the history recording this restoration

### Example 4: Recovering a Deleted Cell

To recover a cell that was accidentally deleted:

1. Open the Version History panel
2. Navigate to a version before the cell was deleted
3. Click to view that version
4. Locate the deleted cell in the content
5. Click "Restore This Cell"
6. The cell will be reinserted into the current notebook
7. Other changes made since then will be preserved

## Limitations and Considerations

When using the version history feature, keep in mind:

1. **Storage Requirements**: Version history can consume significant storage space for frequently edited notebooks

2. **Performance Impact**: Accessing very old versions or notebooks with extensive history may take longer to load

3. **Output Handling**: Cell outputs are included in version history, but may not be perfectly restored in all cases

4. **Large Binary Outputs**: Notebooks with large outputs (images, plots) will have larger version history storage requirements

5. **Offline Limitations**: Version history requires server connectivity to access previous versions

## Troubleshooting

### Common Issues

1. **History Not Available**: If version history is not available, check:
   - The collaboration feature is enabled
   - Version history is enabled in server configuration
   - You have permission to access the history

2. **Missing Changes**: If changes appear to be missing from history:
   - Verify the changes were saved and synchronized
   - Check if retention policies have removed older history
   - Ensure the storage backend is functioning correctly

3. **Slow History Loading**: If history is slow to load:
   - Consider increasing snapshot frequency
   - Check database performance and optimization
   - Limit the date range being viewed

### Getting Help

If you encounter issues with the version history feature:

1. Check the server logs for error messages
2. Verify your configuration settings
3. Consult the Jupyter Notebook documentation
4. Reach out to your system administrator
5. File an issue on the Jupyter Notebook GitHub repository
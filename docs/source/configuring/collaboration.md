# Configuring Collaborative Editing

Jupyter Notebook v7 includes comprehensive real-time collaborative editing capabilities powered by the Yjs CRDT (Conflict-free Replicated Data Type) framework. This guide explains how to configure these collaboration features.

## Enabling Collaboration

Collaborative editing can be enabled or disabled through the Jupyter Server configuration. By default, collaboration is disabled and must be explicitly enabled.

To enable collaboration, add the following to your `jupyter_server_config.py` file:

```python
c.NotebookApp.collaborative = True
```

You can also enable collaboration via command line when starting Jupyter Notebook:

```bash
jupyter notebook --collaborative=True
```

## WebSocket Connection Parameters

The collaborative editing features rely on WebSocket connections for real-time updates. You can configure various WebSocket parameters to optimize performance and reliability.

```python
# Maximum WebSocket message size (in bytes)
c.NotebookApp.collaboration_ws_max_message_size = 10485760  # 10MB

# WebSocket ping interval (in milliseconds)
c.NotebookApp.collaboration_ws_ping_interval = 30000  # 30 seconds

# WebSocket ping timeout (in milliseconds)
c.NotebookApp.collaboration_ws_ping_timeout = 10000  # 10 seconds

# Maximum number of concurrent WebSocket connections per notebook
c.NotebookApp.collaboration_max_connections = 20
```

## Permission System Configuration

The collaboration feature includes a permission system that controls access to shared notebooks. You can configure default permissions and permission enforcement behavior.

```python
# Default permission level for new collaborators
# Options: 'viewer', 'commenter', 'editor', 'admin'
c.NotebookApp.collaboration_default_permission = 'viewer'

# Enable or disable cell-level permissions
c.NotebookApp.collaboration_cell_permissions = True

# Permission enforcement mode
# Options: 'strict' (reject unauthorized operations), 'warn' (allow but log warnings)
c.NotebookApp.collaboration_permission_mode = 'strict'

# Enable or disable JupyterHub integration for permissions
c.NotebookApp.collaboration_jupyterhub_permissions = True
```

## Persistence Configuration

Collaborative editing requires persistent storage for document updates, version history, comments, and permissions. You can configure how this data is stored and managed.

```python
# Storage backend for collaboration data
# Options: 'sqlite', 'postgresql', 'mysql'
c.NotebookApp.collaboration_storage_backend = 'sqlite'

# Connection string for database (if using postgresql or mysql)
c.NotebookApp.collaboration_storage_url = 'postgresql://user:password@localhost/jupyter_collab'

# Path to SQLite database file (if using sqlite)
c.NotebookApp.collaboration_sqlite_path = '/path/to/jupyter_collaboration.db'

# Version history settings
c.NotebookApp.collaboration_max_history = 100  # Maximum number of versions to keep
c.NotebookApp.collaboration_history_snapshot_interval = 300  # Seconds between snapshots
```

## User Presence and Awareness

The collaboration feature includes user presence awareness, showing who is viewing or editing a notebook. You can configure how this information is displayed and updated.

```python
# Enable or disable user presence features
c.NotebookApp.collaboration_presence = True

# User presence update interval (in milliseconds)
c.NotebookApp.collaboration_presence_update_interval = 1000  # 1 second

# User inactivity timeout (in milliseconds)
# After this period of inactivity, a user is marked as idle
c.NotebookApp.collaboration_user_idle_timeout = 300000  # 5 minutes

# User disconnection timeout (in milliseconds)
# After this period without updates, a user is removed from the presence list
c.NotebookApp.collaboration_user_disconnect_timeout = 900000  # 15 minutes
```

## Comment System Configuration

The collaboration feature includes a comment and review system. You can configure how comments are stored, displayed, and managed.

```python
# Enable or disable the comment system
c.NotebookApp.collaboration_comments = True

# Maximum comment length (in characters)
c.NotebookApp.collaboration_max_comment_length = 1000

# Enable or disable email notifications for comments
c.NotebookApp.collaboration_comment_notifications = False

# Email address for sending notifications (if enabled)
c.NotebookApp.collaboration_notification_email = 'jupyter@example.com'
```

## Cell Locking Mechanism

The collaboration feature includes a cell locking mechanism to prevent editing conflicts. You can configure how locks are acquired, released, and managed.

```python
# Enable or disable cell locking
c.NotebookApp.collaboration_cell_locking = True

# Maximum lock duration (in seconds)
# After this period, locks are automatically released
c.NotebookApp.collaboration_lock_expiration = 300  # 5 minutes

# Lock acquisition mode
# Options: 'automatic' (lock on edit), 'manual' (explicit lock/unlock)
c.NotebookApp.collaboration_lock_mode = 'automatic'
```

## Advanced Configuration

For advanced deployments, additional configuration options are available.

```python
# Enable or disable offline editing support
c.NotebookApp.collaboration_offline_support = True

# Maximum size of offline edit queue (in operations)
c.NotebookApp.collaboration_offline_queue_size = 1000

# Collaboration server URL (for external collaboration service)
# If not set, the built-in collaboration service is used
c.NotebookApp.collaboration_server_url = 'https://collab.example.com'

# Authentication token for external collaboration service
c.NotebookApp.collaboration_server_token = 'your-secret-token'
```

## Monitoring and Logging

You can configure logging for the collaboration features to help with monitoring and troubleshooting.

```python
# Collaboration log level
# Options: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
c.NotebookApp.collaboration_log_level = 'INFO'

# Path to collaboration log file
c.NotebookApp.collaboration_log_file = '/path/to/collaboration.log'

# Enable or disable metrics collection
c.NotebookApp.collaboration_metrics = True

# Metrics collection interval (in seconds)
c.NotebookApp.collaboration_metrics_interval = 60
```

## Example Configuration

Here's a complete example configuration for enabling collaborative editing with recommended settings:

```python
# Enable collaboration
c.NotebookApp.collaborative = True

# WebSocket settings
c.NotebookApp.collaboration_ws_max_message_size = 10485760
c.NotebookApp.collaboration_ws_ping_interval = 30000
c.NotebookApp.collaboration_ws_ping_timeout = 10000

# Permission settings
c.NotebookApp.collaboration_default_permission = 'viewer'
c.NotebookApp.collaboration_permission_mode = 'strict'

# Storage settings
c.NotebookApp.collaboration_storage_backend = 'sqlite'
c.NotebookApp.collaboration_sqlite_path = '/path/to/jupyter_collaboration.db'
c.NotebookApp.collaboration_max_history = 100

# Presence settings
c.NotebookApp.collaboration_presence = True
c.NotebookApp.collaboration_user_idle_timeout = 300000

# Comment settings
c.NotebookApp.collaboration_comments = True

# Cell locking settings
c.NotebookApp.collaboration_cell_locking = True
c.NotebookApp.collaboration_lock_mode = 'automatic'

# Logging settings
c.NotebookApp.collaboration_log_level = 'INFO'
```

## Disabling Collaboration

If you need to disable collaboration after it has been enabled, set the following in your configuration:

```python
c.NotebookApp.collaborative = False
```

This will disable all collaborative features, including real-time editing, user presence, comments, and cell locking. Notebooks will function in single-user mode, similar to previous versions of Jupyter Notebook.
# Configuring Collaboration Features

Jupyter Notebook 7 includes comprehensive real-time collaborative editing capabilities powered by the [Yjs CRDT](https://yjs.dev/) framework. This document explains how to configure these collaboration features to suit your deployment needs.

## Overview

The collaboration system in Jupyter Notebook 7 enables multiple users to simultaneously edit notebook documents with the following capabilities:

- Real-time synchronization of notebook content (code cells, markdown cells, outputs)
- User presence awareness showing who is viewing/editing the notebook
- Cursor/selection synchronization to visualize other users' work areas
- Cell-level locking mechanism to prevent editing conflicts
- Change history and versioning system for tracking individual contributions
- Permissions system with fine-grained access control
- Comment and review system for discussing specific cells

This document covers the configuration options for these features.

## Enabling and Disabling Collaboration

Collaboration features can be enabled or disabled at the server level.

### Server Configuration

In your `jupyter_server_config.py` file:

```python
# Enable or disable collaboration features globally
c.JupyterNotebookApp.collaborative_mode = True  # Default: False
```

When disabled, all collaboration-related UI elements will be hidden, and the WebSocket endpoints for collaboration will not be registered.

### Client-Side Configuration

In the Settings Editor (JSON):

```json
{
  "@jupyterlab/notebook-extension:collaborative": {
    "enabled": true
  }
}
```

## WebSocket Connection Parameters

The real-time collaboration features use WebSocket connections to synchronize document changes between clients.

### Server Configuration

In your `jupyter_server_config.py` file:

```python
# WebSocket connection settings for Yjs CRDT synchronization
c.CollaborationManager.websocket_path = "/api/collaboration/yjs"  # Default: "/api/collaboration/yjs"
c.CollaborationManager.ping_interval = 30000  # Milliseconds, Default: 30000 (30 seconds)
c.CollaborationManager.ping_timeout = 10000  # Milliseconds, Default: 10000 (10 seconds)
c.CollaborationManager.max_message_size = 1048576  # Bytes, Default: 1MB
c.CollaborationManager.close_timeout = 5000  # Milliseconds, Default: 5000 (5 seconds)

# Reconnection settings
c.CollaborationManager.reconnect_delay = 1000  # Initial delay in milliseconds, Default: 1000 (1 second)
c.CollaborationManager.max_reconnect_delay = 30000  # Maximum delay in milliseconds, Default: 30000 (30 seconds)
c.CollaborationManager.reconnect_backoff_factor = 1.5  # Exponential backoff factor, Default: 1.5
c.CollaborationManager.max_reconnect_attempts = 10  # Default: 10, set to -1 for unlimited attempts

# Security settings for WebSocket connections
c.CollaborationManager.require_secure_websockets = True  # Default: True, requires WSS protocol
c.CollaborationManager.allowed_origins = []  # Default: [], empty list means same origin only
```

### Client-Side Configuration

In the Settings Editor (JSON):

```json
{
  "@jupyterlab/collaboration-extension:websocket": {
    "reconnectDelay": 1000,
    "maxReconnectDelay": 30000,
    "reconnectBackoffFactor": 1.5,
    "maxReconnectAttempts": 10,
    "showConnectionStatus": true
  }
}
```

## Persistence Configuration

Collaboration data, including document history, comments, and user presence information, needs to be persisted.

### Server Configuration

In your `jupyter_server_config.py` file:

```python
# Persistence settings for collaboration data
c.CollaborationManager.persistence_enabled = True  # Default: True

# Storage backend options: "file", "sqlite", "postgresql", "mysql"
c.CollaborationManager.storage_backend = "file"  # Default: "file"

# File storage settings (when storage_backend = "file")
c.CollaborationManager.file_storage_path = ""  # Default: "", empty means jupyter data dir
c.CollaborationManager.file_storage_prefix = "collab_"  # Default: "collab_"

# Database settings (when storage_backend = "sqlite", "postgresql", or "mysql")
c.CollaborationManager.database_url = ""  # Connection string, required for database backends

# Data retention settings
c.CollaborationManager.update_retention_days = 30  # Default: 30 days
c.CollaborationManager.inactive_document_cleanup_days = 90  # Default: 90 days

# Snapshot settings
c.CollaborationManager.snapshot_interval = 100  # Take snapshot every N updates, Default: 100
c.CollaborationManager.max_snapshots_per_document = 50  # Default: 50
```

### Client-Side Configuration

In the Settings Editor (JSON):

```json
{
  "@jupyterlab/collaboration-extension:persistence": {
    "autoSaveInterval": 60000,  // Milliseconds between auto-saves, Default: 60000 (1 minute)
    "showSaveStatus": true
  }
}
```

## Permission System Configuration

The collaboration features include a comprehensive permission system for controlling access to collaborative notebooks.

### Server Configuration

In your `jupyter_server_config.py` file:

```python
# Permission system settings
c.CollaborationManager.permission_system_enabled = True  # Default: True

# Default role for new collaborators: "viewer", "commenter", "editor", "admin", "owner"
c.CollaborationManager.default_role = "viewer"  # Default: "viewer"

# JupyterHub integration for authentication
c.CollaborationManager.use_jupyterhub_user_identity = True  # Default: True if JupyterHub is detected

# Permission inheritance settings
c.CollaborationManager.cell_permissions_override_document = True  # Default: True
c.CollaborationManager.admin_override_cell_permissions = True  # Default: True

# Permission enforcement points
c.CollaborationManager.enforce_permissions_on_server = True  # Default: True
c.CollaborationManager.enforce_permissions_on_client = True  # Default: True
```

### Client-Side Configuration

In the Settings Editor (JSON):

```json
{
  "@jupyterlab/collaboration-extension:permissions": {
    "showPermissionsUI": true,
    "showRoleIndicators": true,
    "allowCellLevelPermissions": true,
    "defaultCellPermission": "inherit"  // "inherit", "viewer", "commenter", "editor"
  }
}
```

## Cell-Level Locking Mechanism

To prevent editing conflicts, Jupyter Notebook 7 implements a cell-level locking system.

### Server Configuration

In your `jupyter_server_config.py` file:

```python
# Cell locking settings
c.CollaborationManager.cell_locking_enabled = True  # Default: True

# Lock timeout settings
c.CollaborationManager.lock_expiration_time = 300  # Seconds, Default: 300 (5 minutes)
c.CollaborationManager.inactive_lock_timeout = 60  # Seconds of inactivity, Default: 60 (1 minute)

# Lock override settings
c.CollaborationManager.allow_admin_lock_override = True  # Default: True
c.CollaborationManager.notify_on_lock_override = True  # Default: True
```

### Client-Side Configuration

In the Settings Editor (JSON):

```json
{
  "@jupyterlab/collaboration-extension:locks": {
    "showLockIndicators": true,
    "autoLockOnEdit": true,
    "showLockNotifications": true,
    "requestLockOnSelection": false
  }
}
```

## Comment and Review System

The comment and review system allows users to discuss specific cells without modifying the notebook content.

### Server Configuration

In your `jupyter_server_config.py` file:

```python
# Comment system settings
c.CollaborationManager.comments_enabled = True  # Default: True

# Comment notification settings
c.CollaborationManager.comment_notifications_enabled = True  # Default: True
c.CollaborationManager.email_notifications_enabled = False  # Default: False
c.CollaborationManager.email_server_settings = {}  # SMTP server settings if email notifications are enabled

# Comment moderation settings
c.CollaborationManager.comment_moderation_enabled = False  # Default: False
c.CollaborationManager.comment_moderation_roles = ["admin", "owner"]  # Default: ["admin", "owner"]
```

### Client-Side Configuration

In the Settings Editor (JSON):

```json
{
  "@jupyterlab/collaboration-extension:comments": {
    "showCommentIndicators": true,
    "showCommentPanel": true,
    "autoShowNewComments": true,
    "commentPanelPosition": "right"  // "right", "bottom", "left"
  }
}
```

## User Presence and Awareness

The presence system shows which users are currently viewing or editing the notebook.

### Server Configuration

In your `jupyter_server_config.py` file:

```python
# User presence settings
c.CollaborationManager.presence_enabled = True  # Default: True

# Presence update frequency
c.CollaborationManager.presence_update_interval = 5000  # Milliseconds, Default: 5000 (5 seconds)

# Inactivity thresholds
c.CollaborationManager.idle_threshold = 60000  # Milliseconds, Default: 60000 (1 minute)
c.CollaborationManager.away_threshold = 300000  # Milliseconds, Default: 300000 (5 minutes)

# Presence cleanup
c.CollaborationManager.presence_cleanup_delay = 30000  # Milliseconds, Default: 30000 (30 seconds)
```

### Client-Side Configuration

In the Settings Editor (JSON):

```json
{
  "@jupyterlab/collaboration-extension:presence": {
    "showPresencePanel": true,
    "showCursors": true,
    "showSelections": true,
    "showUserStatus": true,
    "condensedPresenceView": false
  }
}
```

## Version History and Change Tracking

The version history system tracks changes to the notebook over time.

### Server Configuration

In your `jupyter_server_config.py` file:

```python
# Version history settings
c.CollaborationManager.version_history_enabled = True  # Default: True

# History granularity
c.CollaborationManager.history_granularity = "cell"  # "cell" or "document", Default: "cell"

# Automatic snapshot settings
c.CollaborationManager.auto_snapshot_enabled = True  # Default: True
c.CollaborationManager.auto_snapshot_interval = 300  # Seconds, Default: 300 (5 minutes)
c.CollaborationManager.max_auto_snapshots = 100  # Default: 100

# Named version settings
c.CollaborationManager.named_versions_enabled = True  # Default: True
c.CollaborationManager.max_named_versions = 50  # Default: 50
```

### Client-Side Configuration

In the Settings Editor (JSON):

```json
{
  "@jupyterlab/collaboration-extension:history": {
    "showHistoryPanel": true,
    "showChangeIndicators": true,
    "autoExpandChanges": false,
    "showAuthorInfo": true
  }
}
```

## Advanced Configuration

### Custom Authentication Integration

For custom authentication systems, you can configure how the collaboration system integrates with your authentication provider.

```python
# Custom authentication integration
c.CollaborationManager.auth_provider_class = "my_module.MyAuthProvider"  # Default: None
c.CollaborationManager.auth_provider_options = {}  # Options passed to the auth provider
```

### Performance Tuning

For deployments with many users or large notebooks, you may need to adjust performance settings.

```python
# WebSocket performance settings
c.CollaborationManager.max_connections_per_document = 50  # Default: 50
c.CollaborationManager.max_documents_per_server = 1000  # Default: 1000

# Update batching settings
c.CollaborationManager.update_batch_size = 10  # Default: 10
c.CollaborationManager.update_batch_delay = 50  # Milliseconds, Default: 50

# Memory management
c.CollaborationManager.document_cache_size = 100  # Default: 100
c.CollaborationManager.document_cache_ttl = 3600  # Seconds, Default: 3600 (1 hour)
```

### Logging and Monitoring

Configure logging and monitoring for collaboration features.

```python
# Collaboration logging settings
c.CollaborationManager.log_level = "INFO"  # "DEBUG", "INFO", "WARNING", "ERROR", Default: "INFO"
c.CollaborationManager.log_file = ""  # Default: "", empty means use Jupyter Server's log

# Metrics collection
c.CollaborationManager.metrics_enabled = True  # Default: True
c.CollaborationManager.metrics_collection_interval = 60  # Seconds, Default: 60 (1 minute)
```

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failures**
   - Ensure your server is properly configured for WebSocket connections
   - Check that your proxy server (if any) is configured to pass WebSocket traffic
   - Verify that SSL/TLS is properly configured if using secure WebSockets (WSS)

2. **Permission Problems**
   - Verify that the JupyterHub integration is properly configured
   - Check the server logs for permission validation errors
   - Ensure users have the appropriate roles assigned

3. **Synchronization Issues**
   - Check the WebSocket connection status in the client
   - Verify that the persistence backend is properly configured and accessible
   - Look for errors in the server logs related to CRDT updates

### Diagnostic Commands

To check the status of the collaboration system:

```bash
jupyter collaboration status
```

To reset the collaboration state for a specific notebook:

```bash
jupyter collaboration reset /path/to/notebook.ipynb
```

## Security Considerations

When configuring collaboration features, consider the following security aspects:

1. **Always use secure WebSockets (WSS)** for production deployments
2. **Configure appropriate authentication** for all users
3. **Set up proper permission roles** to restrict access as needed
4. **Enable audit logging** for security monitoring
5. **Regularly back up** the collaboration persistence store

For more information on security, see the [Security in Jupyter](https://jupyter-server.readthedocs.io/en/stable/operators/security.html) documentation.

## Further Reading

- [Jupyter Server Configuration](https://jupyter-server.readthedocs.io/en/stable/operators/configuring-jupyter-server.html)
- [JupyterHub Integration](https://jupyterhub.readthedocs.io/en/stable/)
- [Yjs Documentation](https://docs.yjs.dev/)
- [Jupyter Notebook 7 Collaboration Architecture](../collaboration/architecture.html)
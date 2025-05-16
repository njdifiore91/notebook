# Collaboration Configuration

This document provides detailed configuration options for the real-time collaborative editing features in Jupyter Notebook v7. These features enable multiple users to simultaneously edit notebook documents with real-time synchronization, user presence awareness, and more.

## Enabling Collaborative Editing

Collaborative editing features can be enabled or disabled at the server level:

```python
# In jupyter_server_config.py
c.NotebookApp.collaborative_mode = "enabled"  # Options: "enabled", "disabled", "opt-in"
```

Available options:
- `"enabled"`: Collaboration features are enabled for all notebooks by default
- `"disabled"`: Collaboration features are completely disabled
- `"opt-in"`: Collaboration features must be explicitly enabled for each notebook

When using the "opt-in" mode, collaboration can be enabled for individual notebooks through the UI or via notebook metadata:

```json
{
  "metadata": {
    "collaboration": {
      "enabled": true
    }
  }
}
```

## WebSocket Connection Configuration

Collaborative editing uses WebSocket connections for real-time synchronization. The following parameters configure the WebSocket connection:

```python
# In jupyter_server_config.py
# Basic WebSocket configuration
c.CollaborationManager.websocket_host = ""  # Host for WebSocket connections
c.CollaborationManager.websocket_port = 8888  # Port for WebSocket connections
c.CollaborationManager.use_wss = True  # Use secure WebSockets (WSS)

# Advanced WebSocket settings
c.CollaborationManager.websocket_path = "/api/collaboration"  # URL path for WebSocket endpoint
c.CollaborationManager.ping_interval = 30000  # WebSocket ping interval in milliseconds
c.CollaborationManager.ping_timeout = 10000  # WebSocket ping timeout in milliseconds
c.CollaborationManager.max_message_size = 1048576  # Maximum message size in bytes (1MB)
c.CollaborationManager.allowed_origins = []  # List of allowed origins, empty for same-origin only
```

### Security Considerations

For production deployments, always enable secure WebSockets (WSS) by setting `use_wss = True`. This requires proper SSL/TLS configuration for your Jupyter Server. Unsecured WebSocket connections should only be used in development environments.

```python
# In jupyter_server_config.py
# SSL/TLS configuration for secure WebSockets
c.ServerApp.certfile = '/path/to/cert.pem'  # Path to SSL certificate file
c.ServerApp.keyfile = '/path/to/key.pem'  # Path to SSL key file
```

## Permission System Configuration

The collaboration permission system controls access levels for users in collaborative sessions:

```python
# In jupyter_server_config.py
# Default permissions
c.CollaborationManager.default_document_permission = "editor"  # Default role for new users
c.CollaborationManager.allow_cell_level_permissions = True  # Enable cell-level permissions
c.CollaborationManager.owner_permission = "owner"  # Permission level for document owner

# Permission enforcement
c.CollaborationManager.enforce_permissions = True  # Enforce permission checks
c.CollaborationManager.permission_cache_ttl = 300  # Permission cache time-to-live in seconds
```

### Available Permission Roles

The following roles are available for document and cell-level permissions:

- `"owner"`: Full control of the document, including permission assignment and deletion rights
- `"admin"`: Can modify content, manage permissions, and control collaborative sessions
- `"editor"`: Can modify notebook content and execute cells
- `"commenter"`: Can add comments but cannot modify notebook content
- `"viewer"`: Read-only access to the notebook

### JupyterHub Integration

When using JupyterHub for authentication, permission roles can be mapped to JupyterHub scopes:

```python
# In jupyter_server_config.py
c.CollaborationManager.jupyterhub_permission_mapping = {
    "notebooks:collaborative:own": "owner",
    "notebooks:collaborative:admin": "admin",
    "notebooks:collaborative:edit": "editor",
    "notebooks:collaborative:comment": "commenter",
    "notebooks:collaborative:read": "viewer"
}
```

## Persistence Configuration

Collaboration data persistence requires database configuration for storing document history, comments, and other collaboration metadata:

```python
# In jupyter_server_config.py
# Database connection
c.CollaborationManager.database_url = "postgresql://user:password@localhost/jupyter_collab"
c.CollaborationManager.persistence_enabled = True

# Connection pool settings
c.CollaborationManager.database_pool_size = 10  # Maximum number of database connections
c.CollaborationManager.database_max_overflow = 20  # Maximum overflow connections
c.CollaborationManager.database_pool_timeout = 30  # Connection timeout in seconds

# History and data retention
c.CollaborationManager.history_retention_days = 30  # Days to retain version history
c.CollaborationManager.snapshot_interval = 50  # Create snapshot every N updates
c.CollaborationManager.max_document_size = 15728640  # Maximum document size in bytes (15MB)
```

### Database Requirements

The collaboration features require a relational database for persistence. PostgreSQL 14+ with JSONB support is recommended for optimal performance. The database must be created before starting the Jupyter Server with collaboration enabled.

Alternatively, an enterprise-grade document database may be used, but it must support ACID transactions for collaboration data integrity.

### Database Schema Migration

Database schema migrations are handled automatically when the server starts. To manually run migrations:

```bash
jupyter collaboration migrate
```

## User Presence Configuration

User presence features show which users are viewing or editing the notebook and their cursor positions:

```python
# In jupyter_server_config.py
# User presence settings
c.CollaborationManager.presence_enabled = True  # Enable user presence features
c.CollaborationManager.presence_update_interval = 1000  # Update interval in milliseconds
c.CollaborationManager.presence_cleanup_delay = 30000  # Cleanup delay for disconnected users

# User information
c.CollaborationManager.user_display_name_source = "jupyterhub"  # Options: "jupyterhub", "system", "config"
c.CollaborationManager.default_user_display_name = "Anonymous"  # Fallback display name
c.CollaborationManager.show_user_status = True  # Show user status indicators
```

## Cell Locking Configuration

Cell locking prevents multiple users from editing the same cell simultaneously:

```python
# In jupyter_server_config.py
# Cell locking settings
c.CollaborationManager.cell_locking_enabled = True  # Enable cell locking
c.CollaborationManager.lock_expiration_time = 300  # Lock expiration time in seconds
c.CollaborationManager.allow_lock_override = True  # Allow admins to override locks
c.CollaborationManager.auto_lock_cells = False  # Automatically lock cells on selection
```

## Comment System Configuration

The comment system allows users to discuss specific cells:

```python
# In jupyter_server_config.py
# Comment system settings
c.CollaborationManager.comments_enabled = True  # Enable comment system
c.CollaborationManager.comments_require_selection = False  # Require text selection for comments
c.CollaborationManager.comments_allow_attachments = True  # Allow file attachments in comments
c.CollaborationManager.comments_max_length = 1000  # Maximum comment length in characters
```

## Version History Configuration

Version history tracks changes to the notebook over time:

```python
# In jupyter_server_config.py
# Version history settings
c.CollaborationManager.history_enabled = True  # Enable version history
c.CollaborationManager.history_granularity = "cell"  # History tracking level: "document" or "cell"
c.CollaborationManager.auto_snapshot_interval = 300  # Auto-snapshot interval in seconds (0 to disable)
c.CollaborationManager.max_history_items = 100  # Maximum history items to keep per document
```

## Advanced Configuration

### Collaboration Server Extension

Advanced settings for the collaboration server extension:

```python
# In jupyter_server_config.py
# Server extension settings
c.CollaborationManager.max_concurrent_sessions = 100  # Maximum concurrent collaborative sessions
c.CollaborationManager.session_timeout = 3600  # Session timeout in seconds
c.CollaborationManager.cleanup_interval = 300  # Background cleanup interval in seconds
c.CollaborationManager.log_collaboration_events = True  # Log collaboration events
```

### Performance Tuning

Settings to optimize performance for different deployment scenarios:

```python
# In jupyter_server_config.py
# Performance settings
c.CollaborationManager.update_throttle_interval = 50  # Minimum time between updates in milliseconds
c.CollaborationManager.batch_updates = True  # Batch multiple updates together
c.CollaborationManager.compression_enabled = True  # Enable message compression
c.CollaborationManager.max_clients_per_document = 20  # Maximum clients per document
```

### Security Settings

Additional security settings for collaborative editing:

```python
# In jupyter_server_config.py
# Security settings
c.CollaborationManager.encrypt_collaboration_data = True  # Encrypt collaboration data at rest
c.CollaborationManager.encryption_key_path = "/path/to/encryption/key"  # Path to encryption key file
c.CollaborationManager.sanitize_user_content = True  # Sanitize user-generated content
c.CollaborationManager.token_expiration = 86400  # Collaboration token expiration in seconds
```

## Environment Variables

Many configuration options can also be set using environment variables:

```bash
# Basic configuration
export JUPYTER_COLLABORATIVE_MODE=enabled

# Database configuration
export JUPYTER_COLLAB_DATABASE_URL=postgresql://user:password@localhost/jupyter_collab

# WebSocket configuration
export JUPYTER_COLLAB_WEBSOCKET_PORT=8888
export JUPYTER_COLLAB_USE_WSS=true

# Security configuration
export JUPYTER_COLLAB_ENCRYPT_DATA=true
export JUPYTER_COLLAB_ENCRYPTION_KEY_PATH=/path/to/encryption/key
```

## Configuration Examples

### Basic Collaboration Setup

```python
# In jupyter_server_config.py
# Enable collaboration features
c.NotebookApp.collaborative_mode = "enabled"

# Configure database connection
c.CollaborationManager.database_url = "postgresql://jupyter:password@localhost/jupyter_collab"
c.CollaborationManager.persistence_enabled = True

# Basic security settings
c.CollaborationManager.use_wss = True
c.ServerApp.certfile = '/path/to/cert.pem'
c.ServerApp.keyfile = '/path/to/key.pem'
```

### Enterprise Deployment

```python
# In jupyter_server_config.py
# Enable collaboration with opt-in mode
c.NotebookApp.collaborative_mode = "opt-in"

# Database configuration with connection pooling
c.CollaborationManager.database_url = "postgresql://app_user:complex_password@db.example.com/jupyter_collab"
c.CollaborationManager.database_pool_size = 20
c.CollaborationManager.database_max_overflow = 30

# Security settings
c.CollaborationManager.use_wss = True
c.CollaborationManager.encrypt_collaboration_data = True
c.CollaborationManager.encryption_key_path = "/etc/jupyter/secrets/collab_key"

# Permission integration with JupyterHub
c.CollaborationManager.jupyterhub_permission_mapping = {
    "notebooks:collaborative:own": "owner",
    "notebooks:collaborative:admin": "admin",
    "notebooks:collaborative:edit": "editor",
    "notebooks:collaborative:comment": "commenter",
    "notebooks:collaborative:read": "viewer"
}

# Performance tuning
c.CollaborationManager.batch_updates = True
c.CollaborationManager.compression_enabled = True
c.CollaborationManager.max_clients_per_document = 50

# Audit logging
c.CollaborationManager.log_collaboration_events = True
```

### Development Environment

```python
# In jupyter_server_config.py
# Enable collaboration for development
c.NotebookApp.collaborative_mode = "enabled"

# Use SQLite for development (not recommended for production)
c.CollaborationManager.database_url = "sqlite:///jupyter_collab.db"
c.CollaborationManager.persistence_enabled = True

# Development settings
c.CollaborationManager.use_wss = False  # Allow unsecured WebSockets for development
c.CollaborationManager.encrypt_collaboration_data = False
c.CollaborationManager.log_collaboration_events = True
```

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failures**
   - Ensure the WebSocket port is accessible and not blocked by firewalls
   - Check SSL/TLS configuration if using WSS
   - Verify allowed origins configuration if connecting from different domains

2. **Database Connection Issues**
   - Verify database credentials and connection string
   - Ensure the database exists and is accessible from the server
   - Check database permissions for the connecting user

3. **Permission Problems**
   - Verify JupyterHub integration settings if using JupyterHub
   - Check permission mapping configuration
   - Ensure the collaboration database contains correct permission records

### Diagnostic Commands

Use the following commands to diagnose collaboration issues:

```bash
# Check collaboration system status
jupyter collaboration status

# Verify database connection
jupyter collaboration db-check

# View collaboration logs
jupyter collaboration logs

# Test WebSocket connectivity
jupyter collaboration test-websocket
```

### Logging

Enable detailed logging for troubleshooting:

```python
# In jupyter_server_config.py
c.Application.log_level = 'DEBUG'
c.CollaborationManager.log_level = 'DEBUG'
```

Collaboration-specific logs will be available in the Jupyter Server log output.
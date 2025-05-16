# Configuration

```{toctree}
:caption: Configuration
:maxdepth: 1

configuring/config_overview
Security <https://jupyter-server.readthedocs.io/en/stable/operators/security.html>
extending/index.rst
configuring/collaboration
```

## Collaborative Editing Features

Jupyter Notebook v7 includes comprehensive real-time collaborative editing capabilities, enabling multiple users to simultaneously edit notebook documents. This section provides an overview of the configuration options for these features. For detailed configuration instructions, see the [Collaboration Configuration](configuring/collaboration.md) section.

### Key Configuration Areas

#### Enabling/Disabling Collaboration

Collaborative editing features can be enabled or disabled at both the server and notebook level:

```python
# In jupyter_server_config.py
c.NotebookApp.collaborative_mode = "enabled"  # Options: "enabled", "disabled", "opt-in"
```

When set to "opt-in", collaboration features must be explicitly enabled for each notebook.

#### WebSocket Connection Parameters

Collaborative editing uses WebSocket connections for real-time synchronization. Key configuration parameters include:

```python
# In jupyter_server_config.py
c.CollaborationManager.websocket_host = ""  # Host for WebSocket connections
c.CollaborationManager.websocket_port = 8888  # Port for WebSocket connections
c.CollaborationManager.use_wss = True  # Use secure WebSockets (WSS)
```

#### Permission System Configuration

The collaboration permission system can be configured to control access levels:

```python
# In jupyter_server_config.py
c.CollaborationManager.default_document_permission = "editor"  # Default role for new users
c.CollaborationManager.allow_cell_level_permissions = True  # Enable cell-level permissions
```

#### Persistence Configuration

Collaboration data persistence requires database configuration:

```python
# In jupyter_server_config.py
c.CollaborationManager.database_url = "postgresql://user:password@localhost/jupyter_collab"
c.CollaborationManager.persistence_enabled = True
c.CollaborationManager.history_retention_days = 30  # Days to retain version history
```

For more detailed configuration options, including security settings, user presence configuration, and advanced database options, see the [Collaboration Configuration](configuring/collaboration.md) documentation.
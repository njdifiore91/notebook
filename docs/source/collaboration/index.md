# Collaboration

```{warning}
Collaborative features in Jupyter Notebook v7 require specific server configuration and are not enabled by default. Please ensure your Jupyter Server is properly configured for collaboration before attempting to use these features.
```

## Introduction to Real-Time Collaboration

Jupyter Notebook v7 introduces comprehensive real-time collaborative editing capabilities, enabling multiple users to simultaneously work on the same notebook document. These features transform Jupyter Notebook from a single-user application into a powerful collaborative environment for team-based data science and research.

Built on the [Yjs](https://yjs.dev/) Conflict-free Replicated Data Type (CRDT) framework, the collaborative features ensure that changes from multiple users are seamlessly merged without conflicts, even during concurrent editing of the same document. This technology eliminates the need for manual conflict resolution and provides a smooth, Google Docs-like collaborative experience within Jupyter notebooks.

## Key Collaboration Features

Jupyter Notebook v7's collaboration capabilities include:

- **Real-time Synchronization**: All notebook content (code cells, markdown cells, outputs) is synchronized in real-time across all connected users.

- **User Presence Awareness**: See who else is viewing or editing the notebook with visual indicators showing each user's activity.

- **Cursor and Selection Tracking**: Visualize where other users are working with real-time cursor positions and text selections.

- **Cell Locking Mechanism**: Prevent editing conflicts with automatic cell-level locking when a user begins editing.

- **Version History**: Track changes over time with a comprehensive history system that shows who made each change.

- **Permissions System**: Control who can view, comment on, or edit your notebook with fine-grained access controls.

- **Comment and Review System**: Discuss specific cells with inline comments and review threads.

## Enabling Collaboration

To enable collaborative features in Jupyter Notebook v7, you need to configure your Jupyter Server with the appropriate settings. The basic steps are:

1. Install the required dependencies:
   ```bash
   pip install jupyter-collaboration
   ```

2. Enable the collaboration extension in your Jupyter Server configuration:
   ```python
   # In jupyter_server_config.py
   c.NotebookApp.collaborative = True
   c.CollaborationManager.storage_path = '/path/to/collaboration/data'
   ```

See the [Collaboration Configuration](./configuration.md) guide for detailed instructions and additional configuration options.

## Collaboration Guides

```{toctree}
:maxdepth: 2

configuration
user_presence
cell_locking
version_history
permissions
comments
troubleshooting
api_reference
```

Each guide provides detailed information about specific collaboration features, including how to use them, configuration options, and troubleshooting tips. The [API Reference](./api_reference.md) provides documentation for developers who want to extend or customize the collaboration features.

## Technical Foundation

Jupyter Notebook v7's collaborative features are built on the following technologies:

- **[Yjs](https://yjs.dev/)**: A high-performance CRDT implementation that enables conflict-free real-time collaboration. Yjs automatically merges changes from multiple users without requiring manual conflict resolution.

- **[y-websocket](https://github.com/yjs/y-websocket)**: A WebSocket provider for Yjs that enables efficient binary update protocol for real-time synchronization. This ensures low-latency updates even with many concurrent users.

- **[y-protocols/awareness](https://github.com/yjs/y-protocols)**: A protocol for tracking and broadcasting user presence information, enabling features like cursor tracking and user status indicators.

These technologies work together to provide a seamless collaborative experience while maintaining the performance and reliability expected from Jupyter Notebook.

## Compatibility Considerations

When using collaborative features, please be aware of the following compatibility considerations:

- All users must be using Jupyter Notebook v7 or later with collaboration support enabled.
- Collaborative editing works best when all users have similar versions of the collaboration extension.
- Some third-party notebook extensions may not be fully compatible with collaborative editing features.
- For optimal performance, a stable network connection is recommended for all participants.

## Integration with JupyterHub

Collaborative features in Jupyter Notebook v7 integrate with JupyterHub for authentication and user identity management. When deployed with JupyterHub, the collaboration system uses JupyterHub's authentication to identify users, enabling features like user-specific presence information, permission assignment, and edit history attribution.
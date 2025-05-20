"""CLI entry point for notebook.

This module serves as the entry point for the Jupyter Notebook application.
It passes command line arguments to the main function, allowing users to
configure the notebook server through command line options.

In addition to standard Jupyter Notebook options, the following 
collaboration-specific options are available:

--enable-collaboration: Enable real-time collaborative editing features (default)
--disable-collaboration: Disable real-time collaborative editing features
--JupyterNotebookApp.collaboration_websocket_max_message_size=<int>: Maximum WebSocket message size in bytes (default: 10MB)
--JupyterNotebookApp.collaboration_ping_interval=<int>: WebSocket ping interval in seconds (default: 30)
--JupyterNotebookApp.collaboration_ping_timeout=<int>: WebSocket ping timeout in seconds (default: 10)
--JupyterNotebookApp.collaboration_max_buffer_size=<int>: Maximum buffer size for messages in bytes (default: 100MB)
--JupyterNotebookApp.collaboration_compression_level=<int>: ZLIB compression level (0-9) (default: 6)
--JupyterNotebookApp.collaboration_lock_timeout=<int>: Timeout for cell locks in seconds (default: 300)
--JupyterNotebookApp.collaboration_user_presence_timeout=<int>: Timeout for user presence in seconds (default: 300)
--JupyterNotebookApp.collaboration_default_permissions=<dict>: Default permissions for collaborative notebooks
"""

import sys

from notebook.app import main

# Pass command line arguments to main function to support collaboration options
sys.exit(main(sys.argv))  # type:ignore[no-untyped-call]
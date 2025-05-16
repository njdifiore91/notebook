# New features in Notebook 7

This document describes the new features in Notebook 7 as originally mentioned in the related Jupyter Enhancement Proposal [JEP 79][jep 79].

```{contents} Table of Contents
:depth: 3
:local:
```

## Debugger

Notebook 7 includes a new debugger that allows you to step through your code cell by cell. You can also set breakpoints and inspect variables.

![a screenshot of the debugger](https://user-images.githubusercontent.com/591645/195543524-e16647a1-a4e0-4832-929d-73d5a77ef001.png)

## Real-Time Collaborative Editing

Notebook 7 now includes built-in comprehensive real-time collaborative editing capabilities, enabling multiple users to simultaneously edit notebook documents with seamless synchronization. This feature is powered by the Yjs CRDT (Conflict-free Replicated Data Type) framework, providing a robust foundation for multi-user editing.

![a screencast showing multiple users collaboratively editing a notebook with synchronized cursors and presence indicators](https://path/to/collaboration-demo.gif)

### Key Collaborative Features

#### Real-Time Synchronization

All notebook content is synchronized in real-time between collaborators, including:
- Code and markdown cell content
- Cell outputs and execution results
- Cell metadata and formatting
- Notebook structure (cell creation, deletion, and reordering)

Changes made by any user are instantly visible to all collaborators, with automatic conflict resolution provided by the Yjs CRDT framework.

#### User Presence Awareness

Collaborative notebooks display who is currently viewing or editing the document:

- User avatars appear in the collaboration panel showing all active participants
- Status indicators show whether users are active, idle, or viewing
- User information includes names and optional profile details

![a screenshot showing the user presence panel with avatars and status indicators](https://path/to/presence-panel.png)

#### Cursor and Selection Synchronization

See exactly where your collaborators are working in real-time:

- Colored cursors show each user's current position
- Text selections are highlighted with user-specific colors
- Cell focus indicators show which cells other users are viewing

This feature makes it easy to follow along with others' work and avoid editing conflicts.

#### Cell-Level Locking Mechanism

To prevent editing conflicts, Notebook 7 implements an intelligent cell locking system:

- When a user begins editing a cell, it's automatically locked for other users
- Visual indicators show which cells are locked and by whom
- Locks are automatically released when the user completes editing
- Administrators can override locks if necessary

![a screenshot showing locked cells with visual indicators](https://path/to/cell-locking.png)

#### Change History and Versioning

Track contributions and changes over time:

- Complete history of all changes made to the notebook
- Attribution of changes to specific users
- Ability to view and restore previous versions
- Diff visualization to compare changes between versions

#### Permissions System

Fine-grained access control allows document owners to manage collaboration:

- Document-level roles (Owner, Editor, Commenter, Viewer)
- Cell-level permissions for restricted content
- Permission management interface for easy configuration
- Integration with JupyterHub authentication

![a screenshot showing the permissions management interface](https://path/to/permissions-ui.png)

#### Comment and Review System

Facilitate discussion and feedback directly within the notebook:

- Add comments to specific cells or selections
- Thread-based discussions with reply functionality
- Comment resolution workflow for tracking addressed feedback
- Notification system for new comments and mentions

![a screenshot showing the comment and review interface](https://path/to/comments-ui.png)

### Enabling Collaborative Editing

Collaborative editing is built into Notebook 7 and can be enabled through server configuration:

1. Enable the collaboration feature in your Jupyter configuration:

```python
# In jupyter_notebook_config.py
c.NotebookApp.collaborative = True
```

2. Start your Jupyter Notebook server:

```bash
jupyter notebook
```

3. Share the notebook URL with collaborators who have access to your Jupyter server

4. For multi-user deployments, configure JupyterHub integration for authentication and user management

### Technical Implementation

The collaborative editing feature is powered by several key technologies:

- **Yjs CRDT Framework**: Provides conflict-free real-time synchronization with automatic merging of concurrent changes
- **Y-WebSocket**: Efficient binary protocol for Yjs updates over WebSocket connections
- **Y-Protocols/Awareness**: Standardized protocol for user presence and cursor tracking

This implementation ensures:

- Low-latency updates even with multiple simultaneous editors
- Offline editing capability with automatic synchronization when reconnected
- Minimal bandwidth usage through efficient binary update protocol
- Deterministic conflict resolution without requiring server-side intervention

### Using Collaborative Features

When you open a notebook with collaboration enabled:

1. The collaboration panel appears showing all connected users
2. Your changes are automatically synchronized with other users
3. You can see others' cursors and selections in real-time
4. Cells being edited by others are locked and visually indicated
5. You can add comments by clicking the comment icon in cell margins
6. Access version history through the History button in the toolbar
7. Manage permissions via the Share button in the collaboration panel

```{note}
Collaborative editing works seamlessly between Notebook 7 and JupyterLab 4+, allowing team members to use their preferred interface while collaborating on the same document.
```

![a screencast showing the full collaborative editing experience with multiple features in action](https://path/to/full-collaboration-demo.gif)

## Table of Contents

Notebook 7 includes a new table of contents extension that allows you to navigate through your notebook using a sidebar. The Table of Contents is built-in and enabled by default, just like in JupyterLab.

![a screenshot of the table of contents](https://user-images.githubusercontent.com/591645/195544813-22e7dec9-846f-4aaa-913a-36a9ed908036.png)

## Theming and Dark Mode

A Dark Theme is now available in the Jupyter Notebook by default. You can also install other themes as JupyterLab extensions.

![a screenshot of the dark theme](https://user-images.githubusercontent.com/591645/229732821-3ab15024-e6d7-414d-94ca-246619da4b67.png)

You can also install many other JupyterLab themes. For example to install the [JupyterLab Night](https://github.com/martinRenou/jupyterlab-night) theme:

```shell
pip install jupyterlab-night
```

Then refresh the page and select the new theme in the settings:

![a screenshot of a custom theme](https://user-images.githubusercontent.com/591645/229733418-db0898b3-7e8c-4db5-98d6-2e9f813ab9e9.png)

## Internationalization

Notebook 7 now provides the ability to set the display language of the user interface.

Users will need to install the language pack as a separate Python package. Language packs are grouped in the [language packs repository on GitHub](https://github.com/jupyterlab/language-packs/), and can be installed with `pip`. For example, it is possible to install the language pack for French (France) using the following command:

```shell
pip install jupyterlab-language-pack-fr-FR
```

After installing the language pack, reload the page and the new language should be available in the settings.

![a screencast showing how to switch the display language in Notebook 7](https://user-images.githubusercontent.com/591645/229734057-e08a2020-58c1-4aa5-b30e-ebb83fcde12c.gif)

```{note}
Notebook 7 and JupyterLab share the same language packs, so it is possible to use the same language pack in both applications.
```

## Accessibility Improvements

The text editor underlying the Jupyter Notebook (CodeMirror 5) had major accessibility issues. Fortunately, this accessibility bottleneck has been unblocked as JupyterLab has been upgraded to use CodeMirror 6, a complete rewrite of the text editor with a strong focus on accessibility. Although this upgrade required extensive codebase modifications, the changes is available with JupyterLab 4. By being built on top of JupyterLab, Jupyter Notebook 7 directly benefits from the CodeMirror 6 upgrade.

## Support for many JupyterLab extensions

Notebook 7 is based on JupyterLab and therefore supports many of the existing JupyterLab extensions.

You can install JupyterLab extensions with `pip` or `conda`. For example to install the LSP (Language Server Protocol) extension for enhanced code completion, you can use the following commands:

```bash
pip install jupyter-lsp
```

```bash
conda install -c conda-forge jupyter-lsp
```

Popular extensions like `nbgrader` and `RISE` have already been ported to work with Notebook 7.

### nbgrader

```{note}
The nbgrader extension is still under active development and a version compatible with Notebook 7 is not yet available on PyPI.
However a version compatible with Notebook 7 will be available before the final release of Notebook 7.
```

![a screenshot showing the nbgrader extension in Notebook 7](https://user-images.githubusercontent.com/32258950/196110653-6556c8d7-b169-4586-b1a1-66b3be05c790.png)

![a second screenshot showing the nbgrader extension in Notebook 7](https://user-images.githubusercontent.com/32258950/196110825-7e3b9237-1064-42be-a629-15a5510a3aee.png)

### RISE

The RISE extension is another popular JupyterLab extension that has been ported to work with Notebook 7. It allows you to turn your Jupyter Notebooks into a slideshow. See the [installation instructions](https://github.com/jupyterlab-contrib/rise#install).

## A document-centric user experience

Despite all the new features and as stated in [JEP 79][jep 79], Notebook 7 keeps the document-centric user experience of the Classic Notebook:

> The Jupyter Notebook application offers a document-centric user experience. That is, in the Notebook application, the landing page that contains a file manager, running tools tab, and a few optional extras, is a launching point into opening standalone, individual documents. This document-centric experience is important for many users, and that is the first key point this proposal aims to preserve. Notebook v7 will be based on a different JavaScript implementation than v6, but it will preserve the document-centric experience, where each individual notebook opens in a separate browser tab and the visible tools and menus are focused on the open document.

[jep 79]: https://jupyter.org/enhancement-proposals/79-notebook-v7/notebook-v7.html

## Compact View on Mobile Devices

Notebook 7 automatically switches to a more compact layout on mobile devices, making it convenient to run code on the go.

![a screenshot of the compact view on mobile devices](https://user-images.githubusercontent.com/591645/101995448-2793f380-3cca-11eb-8971-067dd068ccbe.gif)

## References

This was just a quick overview of the new features in Notebook 7. For more details, you can check out the following resources:

- The [JupyterLab Documentation](https://jupyterlab.readthedocs.io/en/latest/) is a great resource to learn more about JupyterLab and the extensions available. Since Notebook 7 is based on JupyterLab, many of the features and extensions available for JupyterLab are also available for Notebook 7.
- [Migration Guide](./migrate_to_notebook7.md) for Notebook 7, which explains how to migrate from the Classic Notebook to Notebook 7.
- [Collaborative Editing Documentation](./collaboration/index.md) provides detailed information about setting up and using the real-time collaborative features in Notebook 7.
- [Yjs Documentation](https://docs.yjs.dev/) offers technical details about the CRDT framework powering the collaborative editing features.

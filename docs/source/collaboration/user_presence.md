# User Presence Awareness

Jupyter Notebook v7 includes a real-time user presence awareness system that shows who is currently viewing or editing a notebook. This feature helps teams collaborate more effectively by providing visibility into who is working on what part of a document at any given time.

## Overview

The presence awareness system tracks and displays:

- **Active users** currently viewing the notebook
- **Cursor positions** showing where each user is working
- **Text selections** highlighting content being selected by others
- **User status** (active, idle, away)
- **Cell-level indicators** showing which cells are being edited by specific users

![User presence example](../images/collaboration/user_presence_example.png)

## Implementation

The presence awareness system is built on the [y-protocols/awareness](https://github.com/yjs/y-protocols) extension of the Yjs CRDT framework. This implementation:

- Efficiently synchronizes user presence information in real-time
- Automatically handles user disconnections and reconnections
- Provides conflict-free updates even during network interruptions
- Scales to support multiple simultaneous users

### Technical Architecture

The presence system consists of several components working together:

1. **Client-side Awareness Provider**: Tracks local user actions and broadcasts them to other clients
2. **Server-side Awareness Handler**: Relays awareness information between clients
3. **Presence UI Components**: Visualize user presence in the notebook interface

When a user joins a collaborative session, their presence information is automatically shared with all other connected users. As they interact with the notebook (moving the cursor, selecting text, editing cells), these actions are tracked and broadcast in real-time.

## User Identification

When collaborating on a notebook, users are identified by:

- **Username**: Derived from authentication (JupyterHub integration when available)
- **Color**: Automatically assigned unique color for visual identification
- **Avatar**: User profile image or generated placeholder

In multi-user environments with JupyterHub, user identity is automatically synchronized with authentication information. In single-user deployments, the system uses local configuration settings for user identity.

## Presence Visualization

User presence is visualized in several ways throughout the interface:

### Collaboration Bar

The collaboration bar displays all active users with their avatars, names, and status indicators. This provides an at-a-glance view of who is currently working on the notebook.

```python
# Example of how the collaboration bar appears in the UI
# (This is a visual representation, not actual code)
# [Avatar: Alice] [Avatar: Bob] [Avatar: Carol] [+ 2 more]
```

### Cursor Indicators

Remote users' cursors are displayed as colored flags with their names. These indicators move in real-time as users navigate through the document.

### Selection Highlighting

When another user selects text, their selection is highlighted with a semi-transparent overlay in their assigned color. This makes it easy to see what content others are focusing on.

### Cell Attribution

Cells being actively edited show an indicator with the editor's name and color, helping prevent editing conflicts.

## Automatic Cleanup

The presence system includes automatic cleanup mechanisms for disconnected users:

1. When a user closes their browser or navigates away, their WebSocket connection closes
2. The server detects the disconnection and starts a cleanup timer
3. If the user doesn't reconnect within the configured timeout period, their presence information is removed
4. Other users are notified that the user has disconnected

This ensures that the user list stays current and doesn't show stale information about users who are no longer active.

## Configuration

The presence awareness system can be configured through Jupyter's configuration system.

### Server-side Configuration

In your `jupyter_notebook_config.py` file:

```python
c.CollaborationManager.awareness_cleanup_timeout = 120  # seconds until disconnected users are removed
c.CollaborationManager.max_awareness_update_rate = 50    # maximum updates per second per client
```

### Client-side Configuration

In the Advanced Settings Editor (Settings > Advanced Settings Editor), you can customize the presence UI:

```json
{
  "@jupyter-notebook/collaboration-extension:presence": {
    "showCursors": true,
    "showSelections": true,
    "showUserStatus": true,
    "cursorUpdateThrottleMs": 50,
    "maxVisibleUsers": 10
  }
}
```

## JupyterHub Integration

When used with JupyterHub, the presence system automatically integrates with the authentication system to provide accurate user identification. This integration:

- Uses authenticated usernames for consistent identification
- Retrieves user profile information (display name, avatar) when available
- Respects user privacy settings from JupyterHub profiles

To enable JupyterHub integration, ensure that your JupyterHub and Jupyter Notebook v7 installations are properly configured to work together.

## Examples

### Multiple Users Editing Different Cells

When multiple users are editing different cells, each cell shows an indicator of who is currently editing it. This helps prevent accidental concurrent edits to the same content.

![Multiple users editing](../images/collaboration/multiple_editors_example.png)

### Concurrent Text Selection

When users select text in the same cell, all selections are visible with user-specific colors, making it easy to see what different collaborators are focusing on.

![Concurrent selection](../images/collaboration/concurrent_selection_example.png)

### User Status Changes

The collaboration bar shows status changes as users become idle or away, helping teams understand who is actively working at any given time.

![User status](../images/collaboration/user_status_example.png)

## Troubleshooting

### Missing User Presence

If user presence indicators aren't appearing:

1. Verify that collaboration features are enabled in your configuration
2. Check that WebSocket connections are working properly
3. Ensure that no network firewall is blocking WebSocket traffic
4. Confirm that all users have the correct permissions to access the document

### Stale User Indicators

If disconnected users still appear in the interface:

1. The cleanup timeout may be set too high - adjust the `awareness_cleanup_timeout` setting
2. The user may have multiple browser tabs open with the same document
3. Network issues might be preventing proper WebSocket closure notifications

## Related Features

User presence awareness works in conjunction with other collaboration features:

- **[Cell Locking](cell_locking.md)**: Prevents editing conflicts by allowing exclusive access to cells
- **[Comments and Reviews](comments.md)**: Enables discussion about specific notebook content
- **[Permission Management](permissions.md)**: Controls who can view and edit the notebook

## API Reference

For developers extending the presence system, the following interfaces are available:

```typescript
/**
 * Tracks and synchronizes user presence in a collaborative session
 */
interface IPresenceTracker {
  /**
   * Update local user state
   */
  setAwareness(state: IAwarenessState): void;
  
  /**
   * Get current awareness states for all users
   */
  getAwarenessStates(): Map<number, IAwarenessState>;
  
  /**
   * Subscribe to awareness changes
   */
  onAwarenessChange(callback: (states: Map<number, IAwarenessState>) => void): IDisposable;
}

/**
 * Represents user awareness state
 */
interface IAwarenessState {
  /**
   * User identity information
   */
  user: {
    name: string;
    color: string;
    avatar?: string;
  };
  
  /**
   * Current status (active, idle, away)
   */
  status: 'active' | 'idle' | 'away';
  
  /**
   * Current cursor position
   */
  cursor?: {
    cellId: string;
    position: number;
  };
  
  /**
   * Current text selection
   */
  selection?: {
    cellId: string;
    start: number;
    end: number;
  };
}
```
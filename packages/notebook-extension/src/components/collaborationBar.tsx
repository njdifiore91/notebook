// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useEffect, useState } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ICollaborationProvider, ConnectionStatus } from '@jupyterlab/notebook/lib/collab/provider';
import { IPresenceTracker, IUserAwarenessState, UserStatus } from '@jupyterlab/notebook/lib/collab/awareness';
import { NotebookPanel } from '@jupyterlab/notebook';
import { CommandRegistry } from '@lumino/commands';

/**
 * Props for the CollaborationBar component.
 */
export interface ICollaborationBarProps {
  /**
   * The collaboration provider instance.
   */
  collaborationProvider: ICollaborationProvider;

  /**
   * The presence tracker instance.
   */
  presenceTracker: IPresenceTracker;

  /**
   * The notebook panel containing the notebook.
   */
  notebookPanel: NotebookPanel;

  /**
   * The command registry for executing commands.
   */
  commands: CommandRegistry;
}

/**
 * A component that displays the collaboration status bar for Jupyter Notebook.
 * 
 * This component shows active collaborators, connection status, and provides
 * buttons for accessing collaboration features like permissions management,
 * comment viewing, and version history.
 */
export const CollaborationBar: React.FC<ICollaborationBarProps> = ({
  collaborationProvider,
  presenceTracker,
  notebookPanel,
  commands
}) => {
  // State for connection status
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(
    collaborationProvider.connectionStatus
  );

  // State for active users
  const [activeUsers, setActiveUsers] = useState<Map<number, IUserAwarenessState>>(
    new Map()
  );

  // State for showing the user list dropdown
  const [showUserList, setShowUserList] = useState(false);

  // Handle connection status changes
  useEffect(() => {
    const onConnectionStatusChanged = (status: ConnectionStatus) => {
      setConnectionStatus(status);
    };

    collaborationProvider.connectionStatusChanged.connect(onConnectionStatusChanged);

    return () => {
      collaborationProvider.connectionStatusChanged.disconnect(onConnectionStatusChanged);
    };
  }, [collaborationProvider]);

  // Handle awareness changes
  useEffect(() => {
    const onAwarenessChange = () => {
      setActiveUsers(new Map(presenceTracker.getStates()));
    };

    presenceTracker.stateChanged.connect(onAwarenessChange);
    
    // Initial setup
    onAwarenessChange();

    return () => {
      presenceTracker.stateChanged.disconnect(onAwarenessChange);
    };
  }, [presenceTracker]);

  /**
   * Get the connection status icon and text.
   */
  const getConnectionStatusInfo = () => {
    switch (connectionStatus) {
      case ConnectionStatus.Connected:
        return {
          icon: 'jp-CollaborationBar-statusConnected',
          text: 'Connected',
          className: 'jp-CollaborationBar-statusConnected'
        };
      case ConnectionStatus.Connecting:
        return {
          icon: 'jp-CollaborationBar-statusConnecting',
          text: 'Connecting',
          className: 'jp-CollaborationBar-statusConnecting'
        };
      case ConnectionStatus.Disconnected:
        return {
          icon: 'jp-CollaborationBar-statusDisconnected',
          text: 'Disconnected',
          className: 'jp-CollaborationBar-statusDisconnected'
        };
      default:
        return {
          icon: 'jp-CollaborationBar-statusUnknown',
          text: 'Unknown',
          className: 'jp-CollaborationBar-statusUnknown'
        };
    }
  };

  /**
   * Get the user status icon and text.
   */
  const getUserStatusInfo = (status: UserStatus) => {
    switch (status) {
      case UserStatus.Active:
        return {
          icon: 'jp-CollaborationBar-userActive',
          text: 'Active',
          className: 'jp-CollaborationBar-userActive'
        };
      case UserStatus.Viewing:
        return {
          icon: 'jp-CollaborationBar-userViewing',
          text: 'Viewing',
          className: 'jp-CollaborationBar-userViewing'
        };
      case UserStatus.Idle:
        return {
          icon: 'jp-CollaborationBar-userIdle',
          text: 'Idle',
          className: 'jp-CollaborationBar-userIdle'
        };
      case UserStatus.Editing:
        return {
          icon: 'jp-CollaborationBar-userEditing',
          text: 'Editing',
          className: 'jp-CollaborationBar-userEditing'
        };
      default:
        return {
          icon: 'jp-CollaborationBar-userUnknown',
          text: 'Unknown',
          className: 'jp-CollaborationBar-userUnknown'
        };
    }
  };

  /**
   * Open the permissions dialog.
   */
  const openPermissionsDialog = () => {
    if (commands.hasCommand('collaboration:open-permissions')) {
      commands.execute('collaboration:open-permissions');
    }
  };

  /**
   * Open the comments panel.
   */
  const openCommentsPanel = () => {
    if (commands.hasCommand('collaboration:open-comments')) {
      commands.execute('collaboration:open-comments');
    }
  };

  /**
   * Open the history viewer.
   */
  const openHistoryViewer = () => {
    if (commands.hasCommand('collaboration:open-history')) {
      commands.execute('collaboration:open-history');
    }
  };

  /**
   * Toggle the user list dropdown.
   */
  const toggleUserList = () => {
    setShowUserList(!showUserList);
  };

  // Get connection status information
  const connectionStatusInfo = getConnectionStatusInfo();

  // Count active users (excluding the current user)
  const otherUsersCount = activeUsers.size - 1;

  // Get the document ID
  const documentId = collaborationProvider.getDocumentId();

  return (
    <div className="jp-CollaborationBar">
      {/* Connection status indicator */}
      <div 
        className={`jp-CollaborationBar-status ${connectionStatusInfo.className}`}
        title={`Collaboration status: ${connectionStatusInfo.text}`}
      >
        <div className="jp-CollaborationBar-statusIcon" />
        <span className="jp-CollaborationBar-statusText">{connectionStatusInfo.text}</span>
      </div>

      {/* Document ID */}
      <div className="jp-CollaborationBar-documentId" title={`Document ID: ${documentId}`}>
        {documentId}
      </div>

      {/* Collaboration tools */}
      <div className="jp-CollaborationBar-tools">
        {/* Permissions button */}
        <button 
          className="jp-CollaborationBar-button jp-CollaborationBar-permissionsButton"
          onClick={openPermissionsDialog}
          title="Manage access permissions"
          aria-label="Manage access permissions"
        >
          <div className="jp-CollaborationBar-buttonIcon jp-CollaborationBar-permissionsIcon" />
          <span className="jp-CollaborationBar-buttonText">Permissions</span>
        </button>

        {/* Comments button */}
        <button 
          className="jp-CollaborationBar-button jp-CollaborationBar-commentsButton"
          onClick={openCommentsPanel}
          title="View and manage comments"
          aria-label="View and manage comments"
        >
          <div className="jp-CollaborationBar-buttonIcon jp-CollaborationBar-commentsIcon" />
          <span className="jp-CollaborationBar-buttonText">Comments</span>
        </button>

        {/* History button */}
        <button 
          className="jp-CollaborationBar-button jp-CollaborationBar-historyButton"
          onClick={openHistoryViewer}
          title="View version history"
          aria-label="View version history"
        >
          <div className="jp-CollaborationBar-buttonIcon jp-CollaborationBar-historyIcon" />
          <span className="jp-CollaborationBar-buttonText">History</span>
        </button>
      </div>

      {/* User presence */}
      <div className="jp-CollaborationBar-users">
        <button 
          className="jp-CollaborationBar-usersButton"
          onClick={toggleUserList}
          title={`${activeUsers.size} users collaborating`}
          aria-label={`${activeUsers.size} users collaborating`}
          aria-expanded={showUserList}
          aria-haspopup="true"
        >
          <div className="jp-CollaborationBar-usersIcon" />
          <span className="jp-CollaborationBar-usersCount">
            {activeUsers.size}
          </span>
        </button>

        {/* User list dropdown */}
        {showUserList && (
          <div 
            className="jp-CollaborationBar-userList"
            role="menu"
            aria-label="Collaborating users"
          >
            {Array.from(activeUsers.entries()).map(([clientId, user]) => {
              const userStatusInfo = getUserStatusInfo(user.status);
              const isCurrentUser = clientId === presenceTracker.clientId;

              return (
                <div 
                  key={clientId}
                  className={`jp-CollaborationBar-userItem ${isCurrentUser ? 'jp-CollaborationBar-currentUser' : ''}`}
                  role="menuitem"
                >
                  {/* User avatar */}
                  <div 
                    className="jp-CollaborationBar-userAvatar"
                    style={{ backgroundColor: user.color }}
                    title={user.displayName}
                  >
                    {user.displayName.charAt(0).toUpperCase()}
                  </div>

                  {/* User info */}
                  <div className="jp-CollaborationBar-userInfo">
                    <div className="jp-CollaborationBar-userName">
                      {user.displayName}
                      {isCurrentUser && ' (you)'}
                    </div>
                    <div className={`jp-CollaborationBar-userStatus ${userStatusInfo.className}`}>
                      <div className="jp-CollaborationBar-userStatusIcon" />
                      <span className="jp-CollaborationBar-userStatusText">
                        {userStatusInfo.text}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * A namespace for CollaborationBar statics.
 */
export namespace CollaborationBar {
  /**
   * Create a new CollaborationBar component wrapped in a ReactWidget.
   *
   * @param props - The component props.
   * @returns A new CollaborationBar widget.
   */
  export function create(props: ICollaborationBarProps): ReactWidget {
    const widget = ReactWidget.create(<CollaborationBar {...props} />);
    widget.addClass('jp-CollaborationBarWidget');
    return widget;
  }

  /**
   * Create the CSS for the CollaborationBar component.
   * 
   * @returns The CSS for the CollaborationBar component.
   */
  export function createStyle(): HTMLElement {
    const style = document.createElement('style');
    style.textContent = `
      .jp-CollaborationBar {
        display: flex;
        align-items: center;
        padding: 0 10px;
        height: 28px;
        background-color: var(--jp-layout-color1);
        border-bottom: 1px solid var(--jp-border-color1);
        color: var(--jp-ui-font-color1);
        font-size: var(--jp-ui-font-size1);
      }

      .jp-CollaborationBar-status {
        display: flex;
        align-items: center;
        margin-right: 10px;
      }

      .jp-CollaborationBar-statusIcon {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        margin-right: 5px;
      }

      .jp-CollaborationBar-statusConnected .jp-CollaborationBar-statusIcon {
        background-color: #4CAF50; /* Green */
      }

      .jp-CollaborationBar-statusConnecting .jp-CollaborationBar-statusIcon {
        background-color: #FFC107; /* Amber */
        animation: jp-CollaborationBar-pulse 1.5s infinite;
      }

      .jp-CollaborationBar-statusDisconnected .jp-CollaborationBar-statusIcon {
        background-color: #F44336; /* Red */
      }

      .jp-CollaborationBar-statusUnknown .jp-CollaborationBar-statusIcon {
        background-color: #9E9E9E; /* Grey */
      }

      @keyframes jp-CollaborationBar-pulse {
        0% { opacity: 1; }
        50% { opacity: 0.5; }
        100% { opacity: 1; }
      }

      .jp-CollaborationBar-documentId {
        flex: 1;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-right: 10px;
        font-size: var(--jp-ui-font-size0);
        color: var(--jp-ui-font-color2);
      }

      .jp-CollaborationBar-tools {
        display: flex;
        align-items: center;
        margin-right: 10px;
      }

      .jp-CollaborationBar-button {
        display: flex;
        align-items: center;
        background: none;
        border: none;
        padding: 4px 8px;
        margin: 0 2px;
        border-radius: 3px;
        cursor: pointer;
        color: var(--jp-ui-font-color1);
        font-size: var(--jp-ui-font-size1);
      }

      .jp-CollaborationBar-button:hover {
        background-color: var(--jp-layout-color2);
      }

      .jp-CollaborationBar-button:focus {
        outline: 1px solid var(--jp-brand-color1);
      }

      .jp-CollaborationBar-buttonIcon {
        width: 16px;
        height: 16px;
        margin-right: 4px;
        background-size: 16px;
        background-repeat: no-repeat;
        background-position: center;
      }

      .jp-CollaborationBar-permissionsIcon {
        background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>');
      }

      .jp-CollaborationBar-commentsIcon {
        background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>');
      }

      .jp-CollaborationBar-historyIcon {
        background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>');
      }

      /* Hide button text on small screens */
      @media (max-width: 600px) {
        .jp-CollaborationBar-buttonText {
          display: none;
        }
        
        .jp-CollaborationBar-buttonIcon {
          margin-right: 0;
        }
        
        .jp-CollaborationBar-button {
          padding: 4px;
        }
      }

      .jp-CollaborationBar-users {
        position: relative;
      }

      .jp-CollaborationBar-usersButton {
        display: flex;
        align-items: center;
        justify-content: center;
        background: none;
        border: none;
        padding: 4px;
        border-radius: 3px;
        cursor: pointer;
      }

      .jp-CollaborationBar-usersButton:hover {
        background-color: var(--jp-layout-color2);
      }

      .jp-CollaborationBar-usersButton:focus {
        outline: 1px solid var(--jp-brand-color1);
      }

      .jp-CollaborationBar-usersIcon {
        width: 16px;
        height: 16px;
        background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>');
        background-size: 16px;
        background-repeat: no-repeat;
        background-position: center;
      }

      .jp-CollaborationBar-usersCount {
        display: flex;
        align-items: center;
        justify-content: center;
        min-width: 18px;
        height: 18px;
        background-color: var(--jp-brand-color1);
        color: white;
        border-radius: 9px;
        font-size: var(--jp-ui-font-size0);
        margin-left: 4px;
        padding: 0 4px;
      }

      .jp-CollaborationBar-userList {
        position: absolute;
        top: 100%;
        right: 0;
        width: 250px;
        max-height: 300px;
        overflow-y: auto;
        background-color: var(--jp-layout-color1);
        border: 1px solid var(--jp-border-color1);
        border-radius: 3px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        z-index: 1000;
        margin-top: 4px;
      }

      .jp-CollaborationBar-userItem {
        display: flex;
        align-items: center;
        padding: 8px;
        border-bottom: 1px solid var(--jp-border-color1);
      }

      .jp-CollaborationBar-userItem:last-child {
        border-bottom: none;
      }

      .jp-CollaborationBar-userItem.jp-CollaborationBar-currentUser {
        background-color: var(--jp-layout-color2);
      }

      .jp-CollaborationBar-userAvatar {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: bold;
        margin-right: 8px;
      }

      .jp-CollaborationBar-userInfo {
        flex: 1;
        min-width: 0;
      }

      .jp-CollaborationBar-userName {
        font-weight: bold;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .jp-CollaborationBar-userStatus {
        display: flex;
        align-items: center;
        font-size: var(--jp-ui-font-size0);
        color: var(--jp-ui-font-color2);
      }

      .jp-CollaborationBar-userStatusIcon {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 4px;
      }

      .jp-CollaborationBar-userActive .jp-CollaborationBar-userStatusIcon {
        background-color: #4CAF50; /* Green */
      }

      .jp-CollaborationBar-userViewing .jp-CollaborationBar-userStatusIcon {
        background-color: #2196F3; /* Blue */
      }

      .jp-CollaborationBar-userIdle .jp-CollaborationBar-userStatusIcon {
        background-color: #9E9E9E; /* Grey */
      }

      .jp-CollaborationBar-userEditing .jp-CollaborationBar-userStatusIcon {
        background-color: #FF9800; /* Orange */
      }

      .jp-CollaborationBar-userUnknown .jp-CollaborationBar-userStatusIcon {
        background-color: #9E9E9E; /* Grey */
      }
    `;
    return style;
  }
}
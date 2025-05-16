// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useEffect, useState } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ICollaborationProvider, ConnectionStatus } from '@jupyterlab/notebook/lib/collab/provider';
import { IPresenceTracker, UserStatus, IUserAwarenessState } from '@jupyterlab/notebook/lib/collab/awareness';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { NotebookPanel } from '@jupyterlab/notebook';
import { CommandRegistry } from '@jupyterlab/commands';

/**
 * Props for the CollaborationBar component.
 */
interface ICollaborationBarProps {
  /**
   * The collaboration provider instance.
   */
  collaborationProvider: ICollaborationProvider;

  /**
   * The presence tracker instance.
   */
  presenceTracker: IPresenceTracker;

  /**
   * The notebook panel instance.
   */
  notebookPanel: NotebookPanel;

  /**
   * The command registry.
   */
  commands: CommandRegistry;

  /**
   * The translator instance.
   */
  translator?: ITranslator;
}

/**
 * A React component for displaying collaboration status and controls.
 */
export function CollaborationBar(props: ICollaborationBarProps): JSX.Element {
  const {
    collaborationProvider,
    presenceTracker,
    notebookPanel,
    commands,
    translator = nullTranslator
  } = props;

  const trans = translator.load('notebook');

  // State for connection status
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(
    collaborationProvider.connectionStatus
  );

  // State for active users
  const [activeUsers, setActiveUsers] = useState<Map<number, IUserAwarenessState>>(
    new Map()
  );

  // Update connection status when it changes
  useEffect(() => {
    const onConnectionStatusChanged = (sender: any, status: ConnectionStatus) => {
      setConnectionStatus(status);
    };

    collaborationProvider.connectionStatusChanged.connect(
      onConnectionStatusChanged
    );

    return () => {
      collaborationProvider.connectionStatusChanged.disconnect(
        onConnectionStatusChanged
      );
    };
  }, [collaborationProvider]);

  // Update active users when awareness changes
  useEffect(() => {
    const onAwarenessChanged = () => {
      setActiveUsers(new Map(presenceTracker.getStates()));
    };

    presenceTracker.stateChanged.connect(onAwarenessChanged);
    // Initial state
    onAwarenessChanged();

    return () => {
      presenceTracker.stateChanged.disconnect(onAwarenessChanged);
    };
  }, [presenceTracker]);

  // Get connection status class and text
  const getConnectionStatusInfo = () => {
    switch (connectionStatus) {
      case ConnectionStatus.Connected:
        return {
          className: 'jp-CollaborationBar-status-connected',
          text: trans.__('Connected')
        };
      case ConnectionStatus.Connecting:
        return {
          className: 'jp-CollaborationBar-status-connecting',
          text: trans.__('Connecting...')
        };
      case ConnectionStatus.Disconnected:
        return {
          className: 'jp-CollaborationBar-status-disconnected',
          text: trans.__('Disconnected')
        };
      default:
        return {
          className: 'jp-CollaborationBar-status-unknown',
          text: trans.__('Unknown')
        };
    }
  };

  // Get user status text
  const getUserStatusText = (status: UserStatus) => {
    switch (status) {
      case UserStatus.Active:
        return trans.__('Active');
      case UserStatus.Viewing:
        return trans.__('Viewing');
      case UserStatus.Idle:
        return trans.__('Idle');
      case UserStatus.Editing:
        return trans.__('Editing');
      default:
        return trans.__('Unknown');
    }
  };

  // Get user avatar or initials
  const getUserAvatar = (user: IUserAwarenessState) => {
    if (user.avatarUrl) {
      return (
        <img
          src={user.avatarUrl}
          alt={user.displayName}
          className="jp-CollaborationBar-avatar"
        />
      );
    } else {
      // Use initials if no avatar is available
      const initials = user.displayName
        .split(' ')
        .map(name => name[0])
        .join('')
        .substring(0, 2)
        .toUpperCase();

      return (
        <div
          className="jp-CollaborationBar-avatar jp-CollaborationBar-avatar-initials"
          style={{ backgroundColor: user.color }}
        >
          {initials}
        </div>
      );
    }
  };

  // Get status indicator class
  const getStatusIndicatorClass = (status: UserStatus) => {
    switch (status) {
      case UserStatus.Active:
        return 'jp-CollaborationBar-status-indicator-active';
      case UserStatus.Viewing:
        return 'jp-CollaborationBar-status-indicator-viewing';
      case UserStatus.Idle:
        return 'jp-CollaborationBar-status-indicator-idle';
      case UserStatus.Editing:
        return 'jp-CollaborationBar-status-indicator-editing';
      default:
        return 'jp-CollaborationBar-status-indicator-unknown';
    }
  };

  // Handle button clicks
  const handleOpenPermissions = () => {
    commands.execute('collaboration:open-permissions');
  };

  const handleOpenComments = () => {
    commands.execute('collaboration:open-comments');
  };

  const handleOpenHistory = () => {
    commands.execute('collaboration:open-history');
  };

  const connectionStatusInfo = getConnectionStatusInfo();
  const userCount = activeUsers.size;

  return (
    <div className="jp-CollaborationBar">
      {/* Connection status indicator */}
      <div className="jp-CollaborationBar-connection">
        <div className={`jp-CollaborationBar-status ${connectionStatusInfo.className}`}>
          <div className="jp-CollaborationBar-status-indicator"></div>
          <span className="jp-CollaborationBar-status-text">
            {connectionStatusInfo.text}
          </span>
        </div>
      </div>

      {/* Active users */}
      <div className="jp-CollaborationBar-users">
        {userCount > 0 ? (
          <div className="jp-CollaborationBar-user-count">
            {trans.__('%1 collaborators', userCount)}
          </div>
        ) : null}
        <div className="jp-CollaborationBar-avatars">
          {Array.from(activeUsers.values()).map((user) => (
            <div
              key={user.userId}
              className="jp-CollaborationBar-user"
              title={`${user.displayName} (${getUserStatusText(user.status)})`}
            >
              {getUserAvatar(user)}
              <div
                className={`jp-CollaborationBar-status-indicator ${getStatusIndicatorClass(
                  user.status
                )}`}
              ></div>
            </div>
          ))}
        </div>
      </div>

      {/* Collaboration controls */}
      <div className="jp-CollaborationBar-controls">
        <button
          className="jp-CollaborationBar-button jp-CollaborationBar-permissions"
          onClick={handleOpenPermissions}
          title={trans.__('Manage permissions')}
          aria-label={trans.__('Manage permissions')}
        >
          <div className="jp-CollaborationBar-buttonIcon jp-icon-permissions"></div>
        </button>
        <button
          className="jp-CollaborationBar-button jp-CollaborationBar-comments"
          onClick={handleOpenComments}
          title={trans.__('View comments')}
          aria-label={trans.__('View comments')}
        >
          <div className="jp-CollaborationBar-buttonIcon jp-icon-comments"></div>
        </button>
        <button
          className="jp-CollaborationBar-button jp-CollaborationBar-history"
          onClick={handleOpenHistory}
          title={trans.__('View history')}
          aria-label={trans.__('View history')}
        >
          <div className="jp-CollaborationBar-buttonIcon jp-icon-history"></div>
        </button>
      </div>
    </div>
  );
}

/**
 * A namespace for CollaborationBar statics.
 */
export namespace CollaborationBar {
  /**
   * Create a new CollaborationBar widget.
   */
  export function create(options: {
    collaborationProvider: ICollaborationProvider;
    presenceTracker: IPresenceTracker;
    notebookPanel: NotebookPanel;
    commands: CommandRegistry;
    translator?: ITranslator;
  }): ReactWidget {
    const widget = ReactWidget.create(
      <CollaborationBar
        collaborationProvider={options.collaborationProvider}
        presenceTracker={options.presenceTracker}
        notebookPanel={options.notebookPanel}
        commands={options.commands}
        translator={options.translator}
      />
    );
    widget.addClass('jp-CollaborationBar-widget');
    return widget;
  }

  /**
   * Create a style element for the collaboration bar.
   */
  export function createStyle(): HTMLStyleElement {
    const style = document.createElement('style');
    style.textContent = `
      /* Collaboration Bar styles */
      .jp-CollaborationBar-widget {
        display: flex;
        align-items: center;
        height: 28px;
        padding: 0 8px;
      }
      
      .jp-CollaborationBar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        width: 100%;
        height: 100%;
        font-size: var(--jp-ui-font-size1);
        color: var(--jp-ui-font-color1);
      }
      
      /* Connection status styles */
      .jp-CollaborationBar-connection {
        display: flex;
        align-items: center;
        margin-right: 12px;
      }
      
      .jp-CollaborationBar-status {
        display: flex;
        align-items: center;
        padding: 4px 8px;
        border-radius: 12px;
        background-color: var(--jp-layout-color2);
      }
      
      .jp-CollaborationBar-status-indicator {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 6px;
      }
      
      .jp-CollaborationBar-status-connected .jp-CollaborationBar-status-indicator {
        background-color: var(--jp-success-color0);
      }
      
      .jp-CollaborationBar-status-connecting .jp-CollaborationBar-status-indicator {
        background-color: var(--jp-warn-color0);
        animation: jp-CollaborationBar-pulse 1.5s infinite;
      }
      
      .jp-CollaborationBar-status-disconnected .jp-CollaborationBar-status-indicator {
        background-color: var(--jp-error-color0);
      }
      
      .jp-CollaborationBar-status-unknown .jp-CollaborationBar-status-indicator {
        background-color: var(--jp-layout-color3);
      }
      
      @keyframes jp-CollaborationBar-pulse {
        0% {
          opacity: 1;
        }
        50% {
          opacity: 0.4;
        }
        100% {
          opacity: 1;
        }
      }
      
      /* Users and avatars styles */
      .jp-CollaborationBar-users {
        display: flex;
        align-items: center;
        flex: 1;
        margin: 0 12px;
      }
      
      .jp-CollaborationBar-user-count {
        margin-right: 8px;
        white-space: nowrap;
      }
      
      .jp-CollaborationBar-avatars {
        display: flex;
        align-items: center;
        overflow: hidden;
      }
      
      .jp-CollaborationBar-user {
        position: relative;
        margin-right: 4px;
      }
      
      .jp-CollaborationBar-avatar {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        border: 1px solid var(--jp-border-color1);
        background-color: var(--jp-layout-color1);
        overflow: hidden;
      }
      
      .jp-CollaborationBar-avatar-initials {
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 10px;
        font-weight: bold;
        color: white;
      }
      
      .jp-CollaborationBar-status-indicator {
        position: absolute;
        bottom: 0;
        right: 0;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        border: 1px solid var(--jp-layout-color1);
      }
      
      .jp-CollaborationBar-status-indicator-active {
        background-color: var(--jp-success-color0);
      }
      
      .jp-CollaborationBar-status-indicator-viewing {
        background-color: var(--jp-info-color0);
      }
      
      .jp-CollaborationBar-status-indicator-idle {
        background-color: var(--jp-layout-color3);
      }
      
      .jp-CollaborationBar-status-indicator-editing {
        background-color: var(--jp-warn-color0);
      }
      
      /* Controls styles */
      .jp-CollaborationBar-controls {
        display: flex;
        align-items: center;
      }
      
      .jp-CollaborationBar-button {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        margin-left: 4px;
        border-radius: 4px;
        background-color: transparent;
        border: none;
        cursor: pointer;
        transition: background-color 0.2s;
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
        background-size: contain;
        background-repeat: no-repeat;
        background-position: center;
      }
      
      /* Icon placeholders - these would be replaced with actual SVG icons */
      .jp-icon-permissions {
        background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23616161"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>');
      }
      
      .jp-icon-comments {
        background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23616161"><path d="M21 6h-2v9H6v2c0 .55.45 1 1 1h11l4 4V7c0-.55-.45-1-1-1zm-4 6V3c0-.55-.45-1-1-1H3c-.55 0-1 .45-1 1v14l4-4h10c.55 0 1-.45 1-1z"/></svg>');
      }
      
      .jp-icon-history {
        background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23616161"><path d="M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z"/></svg>');
      }
      
      /* Responsive adjustments */
      @media (max-width: 640px) {
        .jp-CollaborationBar-status-text,
        .jp-CollaborationBar-user-count {
          display: none;
        }
        
        .jp-CollaborationBar-connection {
          margin-right: 4px;
        }
        
        .jp-CollaborationBar-users {
          margin: 0 4px;
        }
        
        .jp-CollaborationBar-avatar {
          width: 20px;
          height: 20px;
        }
      }
    `;
    return style;
  }
}
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { NotebookPanel } from '@jupyterlab/notebook';
import { Token } from '@lumino/coreutils';
import { ISignal, Signal } from '@lumino/signaling';
import { Widget } from '@lumino/widgets';

/**
 * The collaboration service token.
 */
export const ICollaborationService = new Token<ICollaborationService>(
  'jupyter-notebook/collaboration:ICollaborationService'
);

/**
 * The presence service token.
 */
export const IPresenceService = new Token<IPresenceService>(
  'jupyter-notebook/collaboration:IPresenceService'
);

/**
 * The lock service token.
 */
export const ILockService = new Token<ILockService>(
  'jupyter-notebook/collaboration:ILockService'
);

/**
 * The history service token.
 */
export const IHistoryService = new Token<IHistoryService>(
  'jupyter-notebook/collaboration:IHistoryService'
);

/**
 * The permissions service token.
 */
export const IPermissionsService = new Token<IPermissionsService>(
  'jupyter-notebook/collaboration:IPermissionsService'
);

/**
 * The comment service token.
 */
export const ICommentService = new Token<ICommentService>(
  'jupyter-notebook/collaboration:ICommentService'
);

/**
 * Interface for the collaboration service.
 */
export interface ICollaborationService {
  /**
   * Whether collaboration is enabled.
   */
  readonly isEnabled: boolean;

  /**
   * Whether the current user is connected to the collaboration server.
   */
  readonly isConnected: boolean;

  /**
   * Connect to the collaboration server.
   */
  connect(): Promise<void>;

  /**
   * Disconnect from the collaboration server.
   */
  disconnect(): Promise<void>;

  /**
   * Signal emitted when the connection status changes.
   */
  readonly connectionStatusChanged: ISignal<ICollaborationService, boolean>;
}

/**
 * Interface for the presence service.
 */
export interface IPresenceService {
  /**
   * The list of active users.
   */
  readonly users: ICollaborator[];

  /**
   * Signal emitted when the user list changes.
   */
  readonly usersChanged: ISignal<IPresenceService, ICollaborator[]>;

  /**
   * Signal emitted when a user's cursor position changes.
   */
  readonly cursorChanged: ISignal<IPresenceService, ICursorPosition>;
}

/**
 * Interface for the lock service.
 */
export interface ILockService {
  /**
   * The list of locked cells.
   */
  readonly lockedCells: ILockedCell[];

  /**
   * Signal emitted when the locked cells list changes.
   */
  readonly lockedCellsChanged: ISignal<ILockService, ILockedCell[]>;

  /**
   * Lock a cell.
   */
  lockCell(cellId: string): Promise<boolean>;

  /**
   * Unlock a cell.
   */
  unlockCell(cellId: string): Promise<boolean>;
}

/**
 * Interface for the history service.
 */
export interface IHistoryService {
  /**
   * The list of document versions.
   */
  readonly versions: IDocumentVersion[];

  /**
   * Signal emitted when the versions list changes.
   */
  readonly versionsChanged: ISignal<IHistoryService, IDocumentVersion[]>;

  /**
   * Restore the document to a specific version.
   */
  restoreVersion(versionId: string): Promise<boolean>;
}

/**
 * Interface for the permissions service.
 */
export interface IPermissionsService {
  /**
   * The current user's permission level.
   */
  readonly currentUserPermission: PermissionLevel;

  /**
   * The list of user permissions.
   */
  readonly userPermissions: IUserPermission[];

  /**
   * Signal emitted when the permissions list changes.
   */
  readonly permissionsChanged: ISignal<IPermissionsService, IUserPermission[]>;

  /**
   * Update a user's permission level.
   */
  updatePermission(userId: string, level: PermissionLevel): Promise<boolean>;
}

/**
 * Interface for the comment service.
 */
export interface ICommentService {
  /**
   * The list of comments.
   */
  readonly comments: IComment[];

  /**
   * Signal emitted when the comments list changes.
   */
  readonly commentsChanged: ISignal<ICommentService, IComment[]>;

  /**
   * Add a comment.
   */
  addComment(cellId: string, text: string): Promise<IComment>;

  /**
   * Resolve a comment.
   */
  resolveComment(commentId: string): Promise<boolean>;
}

/**
 * Interface for a collaborator.
 */
export interface ICollaborator {
  /**
   * The user ID.
   */
  id: string;

  /**
   * The user name.
   */
  name: string;

  /**
   * The user color.
   */
  color: string;

  /**
   * The user avatar URL.
   */
  avatarUrl?: string;

  /**
   * The user's last active timestamp.
   */
  lastActive: number;

  /**
   * The user's current status.
   */
  status: 'active' | 'idle' | 'offline';
}

/**
 * Interface for a cursor position.
 */
export interface ICursorPosition {
  /**
   * The user ID.
   */
  userId: string;

  /**
   * The cell ID.
   */
  cellId: string;

  /**
   * The cursor position within the cell.
   */
  position: number;

  /**
   * The selection range, if any.
   */
  selection?: { start: number; end: number };
}

/**
 * Interface for a locked cell.
 */
export interface ILockedCell {
  /**
   * The cell ID.
   */
  cellId: string;

  /**
   * The user ID who locked the cell.
   */
  userId: string;

  /**
   * The timestamp when the cell was locked.
   */
  timestamp: number;
}

/**
 * Interface for a document version.
 */
export interface IDocumentVersion {
  /**
   * The version ID.
   */
  id: string;

  /**
   * The user ID who created the version.
   */
  userId: string;

  /**
   * The timestamp when the version was created.
   */
  timestamp: number;

  /**
   * The version description.
   */
  description?: string;
}

/**
 * Permission level for a user.
 */
export type PermissionLevel = 'admin' | 'edit' | 'comment' | 'view';

/**
 * Interface for a user permission.
 */
export interface IUserPermission {
  /**
   * The user ID.
   */
  userId: string;

  /**
   * The permission level.
   */
  level: PermissionLevel;
}

/**
 * Interface for a comment.
 */
export interface IComment {
  /**
   * The comment ID.
   */
  id: string;

  /**
   * The cell ID.
   */
  cellId: string;

  /**
   * The user ID who created the comment.
   */
  userId: string;

  /**
   * The timestamp when the comment was created.
   */
  timestamp: number;

  /**
   * The comment text.
   */
  text: string;

  /**
   * Whether the comment is resolved.
   */
  resolved: boolean;

  /**
   * The replies to the comment.
   */
  replies: ICommentReply[];
}

/**
 * Interface for a comment reply.
 */
export interface ICommentReply {
  /**
   * The reply ID.
   */
  id: string;

  /**
   * The user ID who created the reply.
   */
  userId: string;

  /**
   * The timestamp when the reply was created.
   */
  timestamp: number;

  /**
   * The reply text.
   */
  text: string;
}

/**
 * Interface for a notification.
 */
export interface INotification {
  /**
   * The notification ID.
   */
  id: string;

  /**
   * The notification type.
   */
  type: 'info' | 'warning' | 'error' | 'success';

  /**
   * The notification message.
   */
  message: string;

  /**
   * The timestamp when the notification was created.
   */
  timestamp: number;

  /**
   * Whether the notification has been read.
   */
  read: boolean;

  /**
   * The action to perform when the notification is clicked, if any.
   */
  action?: () => void;
}

/**
 * Interface for the collaboration bar props.
 */
interface ICollaborationBarProps {
  /**
   * The notebook panel.
   */
  notebookPanel: NotebookPanel;

  /**
   * The collaboration service.
   */
  collaborationService: ICollaborationService;

  /**
   * The presence service.
   */
  presenceService: IPresenceService;

  /**
   * The lock service.
   */
  lockService: ILockService;

  /**
   * The history service.
   */
  historyService: IHistoryService;

  /**
   * The permissions service.
   */
  permissionsService: IPermissionsService;

  /**
   * The comment service.
   */
  commentService: ICommentService;

  /**
   * The translator.
   */
  translator?: ITranslator;
}

/**
 * CollaborationBar component that provides the main collaboration status bar for collaborative notebooks.
 * It displays the overall collaboration status, active users, and provides access to collaboration features.
 */
export const CollaborationBar: React.FC<ICollaborationBarProps> = ({
  notebookPanel,
  collaborationService,
  presenceService,
  lockService,
  historyService,
  permissionsService,
  commentService,
  translator = nullTranslator
}) => {
  const trans = translator.load('notebook');
  const [isConnected, setIsConnected] = useState(collaborationService.isConnected);
  const [users, setUsers] = useState<ICollaborator[]>(presenceService.users);
  const [lockedCells, setLockedCells] = useState<ILockedCell[]>(lockService.lockedCells);
  const [comments, setComments] = useState<IComment[]>(commentService.comments);
  const [notifications, setNotifications] = useState<INotification[]>([]);
  const [showActivityFeed, setShowActivityFeed] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showHistoryViewer, setShowHistoryViewer] = useState(false);
  const [showPermissionsDialog, setShowPermissionsDialog] = useState(false);
  const [barWidth, setBarWidth] = useState('100%');
  const barRef = useRef<HTMLDivElement>(null);

  // Calculate unread notifications count
  const unreadNotificationsCount = notifications.filter(n => !n.read).length;

  // Update connection status when it changes
  useEffect(() => {
    const onConnectionStatusChanged = (sender: ICollaborationService, connected: boolean) => {
      setIsConnected(connected);
      // Add notification for connection status change
      addNotification({
        id: `connection-${Date.now()}`,
        type: connected ? 'success' : 'error',
        message: connected ? trans.__('Connected to collaboration server') : trans.__('Disconnected from collaboration server'),
        timestamp: Date.now(),
        read: false
      });
    };

    collaborationService.connectionStatusChanged.connect(onConnectionStatusChanged);
    return () => {
      collaborationService.connectionStatusChanged.disconnect(onConnectionStatusChanged);
    };
  }, [collaborationService, trans]);

  // Update users when they change
  useEffect(() => {
    const onUsersChanged = (sender: IPresenceService, updatedUsers: ICollaborator[]) => {
      setUsers(updatedUsers);
      
      // Check for new users and add notifications
      const currentUserIds = users.map(u => u.id);
      const newUsers = updatedUsers.filter(u => !currentUserIds.includes(u.id));
      
      newUsers.forEach(user => {
        addNotification({
          id: `user-joined-${user.id}-${Date.now()}`,
          type: 'info',
          message: trans.__('%1 joined the collaboration', user.name),
          timestamp: Date.now(),
          read: false
        });
      });
    };

    presenceService.usersChanged.connect(onUsersChanged);
    return () => {
      presenceService.usersChanged.disconnect(onUsersChanged);
    };
  }, [presenceService, users, trans]);

  // Update locked cells when they change
  useEffect(() => {
    const onLockedCellsChanged = (sender: ILockService, updatedLockedCells: ILockedCell[]) => {
      setLockedCells(updatedLockedCells);
      
      // Check for newly locked cells and add notifications
      const currentLockedCellIds = lockedCells.map(lc => lc.cellId);
      const newLockedCells = updatedLockedCells.filter(lc => !currentLockedCellIds.includes(lc.cellId));
      
      newLockedCells.forEach(lockedCell => {
        const user = users.find(u => u.id === lockedCell.userId);
        if (user) {
          addNotification({
            id: `cell-locked-${lockedCell.cellId}-${Date.now()}`,
            type: 'info',
            message: trans.__('%1 locked a cell', user.name),
            timestamp: Date.now(),
            read: false
          });
        }
      });
    };

    lockService.lockedCellsChanged.connect(onLockedCellsChanged);
    return () => {
      lockService.lockedCellsChanged.disconnect(onLockedCellsChanged);
    };
  }, [lockService, lockedCells, users, trans]);

  // Update comments when they change
  useEffect(() => {
    const onCommentsChanged = (sender: ICommentService, updatedComments: IComment[]) => {
      setComments(updatedComments);
      
      // Check for new comments and add notifications
      const currentCommentIds = comments.map(c => c.id);
      const newComments = updatedComments.filter(c => !currentCommentIds.includes(c.id));
      
      newComments.forEach(comment => {
        const user = users.find(u => u.id === comment.userId);
        if (user) {
          addNotification({
            id: `comment-added-${comment.id}-${Date.now()}`,
            type: 'info',
            message: trans.__('%1 added a comment', user.name),
            timestamp: Date.now(),
            read: false,
            action: () => {
              // TODO: Scroll to the comment
            }
          });
        }
      });
    };

    commentService.commentsChanged.connect(onCommentsChanged);
    return () => {
      commentService.commentsChanged.disconnect(onCommentsChanged);
    };
  }, [commentService, comments, users, trans]);

  // Handle window resize to update bar width
  useEffect(() => {
    const updateBarWidth = () => {
      if (barRef.current) {
        const notebookContainer = document.querySelector('.jp-NotebookPanel-notebook');
        if (notebookContainer) {
          setBarWidth(`${notebookContainer.clientWidth}px`);
        }
      }
    };

    // Initial update
    updateBarWidth();

    // Update on window resize
    window.addEventListener('resize', updateBarWidth);
    return () => {
      window.removeEventListener('resize', updateBarWidth);
    };
  }, []);

  // Add a notification
  const addNotification = useCallback((notification: INotification) => {
    setNotifications(prev => [notification, ...prev]);
  }, []);

  // Mark a notification as read
  const markNotificationAsRead = useCallback((id: string) => {
    setNotifications(prev => 
      prev.map(n => n.id === id ? { ...n, read: true } : n)
    );
  }, []);

  // Mark all notifications as read
  const markAllNotificationsAsRead = useCallback(() => {
    setNotifications(prev => 
      prev.map(n => ({ ...n, read: true }))
    );
  }, []);

  // Handle connection toggle
  const handleConnectionToggle = async () => {
    if (isConnected) {
      await collaborationService.disconnect();
    } else {
      await collaborationService.connect();
    }
  };

  // Handle history viewer toggle
  const handleHistoryViewerToggle = () => {
    setShowHistoryViewer(!showHistoryViewer);
  };

  // Handle permissions dialog toggle
  const handlePermissionsDialogToggle = () => {
    setShowPermissionsDialog(!showPermissionsDialog);
  };

  // Handle activity feed toggle
  const handleActivityFeedToggle = () => {
    setShowActivityFeed(!showActivityFeed);
  };

  // Handle notifications toggle
  const handleNotificationsToggle = () => {
    setShowNotifications(!showNotifications);
    if (!showNotifications) {
      markAllNotificationsAsRead();
    }
  };

  // Render user avatars
  const renderUserAvatars = () => {
    return users.map(user => (
      <div 
        key={user.id} 
        className="jp-CollaborationBar-userAvatar"
        style={{ 
          backgroundColor: user.color,
          opacity: user.status === 'active' ? 1 : 0.5
        }}
        title={`${user.name} (${user.status})`}
        aria-label={trans.__('%1 is %2', user.name, user.status)}
      >
        {user.avatarUrl ? (
          <img src={user.avatarUrl} alt={user.name} />
        ) : (
          <span>{user.name.charAt(0).toUpperCase()}</span>
        )}
        <span className="jp-CollaborationBar-userStatus" 
              aria-hidden="true"
              data-status={user.status}></span>
      </div>
    ));
  };

  // Render activity feed
  const renderActivityFeed = () => {
    if (!showActivityFeed) return null;

    // Combine and sort activities from different sources
    const activities = [
      // User activities
      ...users.map(user => ({
        id: `user-${user.id}`,
        timestamp: user.lastActive,
        content: trans.__('%1 is %2', user.name, user.status),
        type: 'user'
      })),
      // Locked cell activities
      ...lockedCells.map(lockedCell => {
        const user = users.find(u => u.id === lockedCell.userId);
        return {
          id: `lock-${lockedCell.cellId}`,
          timestamp: lockedCell.timestamp,
          content: trans.__('%1 locked a cell', user?.name || 'Unknown user'),
          type: 'lock'
        };
      }),
      // Comment activities
      ...comments.map(comment => {
        const user = users.find(u => u.id === comment.userId);
        return {
          id: `comment-${comment.id}`,
          timestamp: comment.timestamp,
          content: trans.__('%1 commented: %2', user?.name || 'Unknown user', comment.text.substring(0, 30) + (comment.text.length > 30 ? '...' : '')),
          type: 'comment'
        };
      })
    ].sort((a, b) => b.timestamp - a.timestamp);

    return (
      <div className="jp-CollaborationBar-activityFeed" aria-label={trans.__('Activity Feed')}>
        <div className="jp-CollaborationBar-activityFeedHeader">
          <h3>{trans.__('Activity Feed')}</h3>
          <button 
            className="jp-CollaborationBar-closeButton"
            onClick={handleActivityFeedToggle}
            aria-label={trans.__('Close activity feed')}
          >
            ×
          </button>
        </div>
        <div className="jp-CollaborationBar-activityFeedContent">
          {activities.length > 0 ? (
            <ul>
              {activities.map(activity => (
                <li key={activity.id} className={`jp-CollaborationBar-activity jp-CollaborationBar-activity-${activity.type}`}>
                  <span className="jp-CollaborationBar-activityTime">
                    {new Date(activity.timestamp).toLocaleTimeString()}
                  </span>
                  <span className="jp-CollaborationBar-activityContent">
                    {activity.content}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="jp-CollaborationBar-noActivity">{trans.__('No recent activity')}</p>
          )}
        </div>
      </div>
    );
  };

  // Render notifications panel
  const renderNotifications = () => {
    if (!showNotifications) return null;

    return (
      <div className="jp-CollaborationBar-notifications" aria-label={trans.__('Notifications')}>
        <div className="jp-CollaborationBar-notificationsHeader">
          <h3>{trans.__('Notifications')}</h3>
          <button 
            className="jp-CollaborationBar-closeButton"
            onClick={handleNotificationsToggle}
            aria-label={trans.__('Close notifications')}
          >
            ×
          </button>
        </div>
        <div className="jp-CollaborationBar-notificationsContent">
          {notifications.length > 0 ? (
            <ul>
              {notifications.map(notification => (
                <li 
                  key={notification.id} 
                  className={`jp-CollaborationBar-notification jp-CollaborationBar-notification-${notification.type} ${notification.read ? 'jp-CollaborationBar-notification-read' : ''}`}
                  onClick={() => {
                    markNotificationAsRead(notification.id);
                    if (notification.action) {
                      notification.action();
                    }
                  }}
                >
                  <span className="jp-CollaborationBar-notificationTime">
                    {new Date(notification.timestamp).toLocaleTimeString()}
                  </span>
                  <span className="jp-CollaborationBar-notificationMessage">
                    {notification.message}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="jp-CollaborationBar-noNotifications">{trans.__('No notifications')}</p>
          )}
        </div>
      </div>
    );
  };

  return (
    <div 
      className={`jp-CollaborationBar ${isConnected ? 'jp-CollaborationBar-connected' : 'jp-CollaborationBar-disconnected'}`}
      ref={barRef}
      style={{ width: barWidth }}
      role="region"
      aria-label={trans.__('Collaboration Bar')}
    >
      {/* Connection status */}
      <div className="jp-CollaborationBar-status">
        <button 
          className={`jp-CollaborationBar-connectionButton ${isConnected ? 'jp-CollaborationBar-connectionButton-connected' : 'jp-CollaborationBar-connectionButton-disconnected'}`}
          onClick={handleConnectionToggle}
          aria-label={isConnected ? trans.__('Connected to collaboration server') : trans.__('Disconnected from collaboration server')}
          title={isConnected ? trans.__('Connected to collaboration server') : trans.__('Disconnected from collaboration server')}
        >
          <span className="jp-CollaborationBar-connectionIndicator"></span>
          <span className="jp-CollaborationBar-connectionText">
            {isConnected ? trans.__('Connected') : trans.__('Disconnected')}
          </span>
        </button>
      </div>

      {/* User presence */}
      <div className="jp-CollaborationBar-users" aria-label={trans.__('Active users')}>
        {renderUserAvatars()}
      </div>

      {/* Collaboration tools */}
      <div className="jp-CollaborationBar-tools">
        {/* History button */}
        <button 
          className={`jp-CollaborationBar-toolButton jp-CollaborationBar-historyButton ${showHistoryViewer ? 'jp-CollaborationBar-toolButton-active' : ''}`}
          onClick={handleHistoryViewerToggle}
          aria-label={trans.__('Version History')}
          title={trans.__('Version History')}
          aria-pressed={showHistoryViewer}
          disabled={!isConnected}
        >
          <span className="jp-CollaborationBar-historyIcon"></span>
        </button>

        {/* Permissions button */}
        <button 
          className={`jp-CollaborationBar-toolButton jp-CollaborationBar-permissionsButton ${showPermissionsDialog ? 'jp-CollaborationBar-toolButton-active' : ''}`}
          onClick={handlePermissionsDialogToggle}
          aria-label={trans.__('Permissions')}
          title={trans.__('Permissions')}
          aria-pressed={showPermissionsDialog}
          disabled={!isConnected || permissionsService.currentUserPermission !== 'admin'}
        >
          <span className="jp-CollaborationBar-permissionsIcon"></span>
        </button>

        {/* Activity feed button */}
        <button 
          className={`jp-CollaborationBar-toolButton jp-CollaborationBar-activityButton ${showActivityFeed ? 'jp-CollaborationBar-toolButton-active' : ''}`}
          onClick={handleActivityFeedToggle}
          aria-label={trans.__('Activity Feed')}
          title={trans.__('Activity Feed')}
          aria-pressed={showActivityFeed}
          disabled={!isConnected}
        >
          <span className="jp-CollaborationBar-activityIcon"></span>
        </button>

        {/* Notifications button */}
        <button 
          className={`jp-CollaborationBar-toolButton jp-CollaborationBar-notificationsButton ${showNotifications ? 'jp-CollaborationBar-toolButton-active' : ''}`}
          onClick={handleNotificationsToggle}
          aria-label={trans.__('Notifications')}
          title={trans.__('Notifications')}
          aria-pressed={showNotifications}
        >
          <span className="jp-CollaborationBar-notificationsIcon"></span>
          {unreadNotificationsCount > 0 && (
            <span className="jp-CollaborationBar-notificationsBadge" aria-hidden="true">
              {unreadNotificationsCount}
            </span>
          )}
        </button>
      </div>

      {/* Render activity feed if visible */}
      {renderActivityFeed()}

      {/* Render notifications if visible */}
      {renderNotifications()}

      {/* Render history viewer if visible */}
      {showHistoryViewer && (
        <div className="jp-CollaborationBar-historyViewer">
          {/* This would be replaced with the actual HistoryViewer component */}
          <div className="jp-CollaborationBar-historyViewerHeader">
            <h3>{trans.__('Version History')}</h3>
            <button 
              className="jp-CollaborationBar-closeButton"
              onClick={handleHistoryViewerToggle}
              aria-label={trans.__('Close version history')}
            >
              ×
            </button>
          </div>
          <div className="jp-CollaborationBar-historyViewerContent">
            <p>{trans.__('Version history component will be rendered here')}</p>
          </div>
        </div>
      )}

      {/* Render permissions dialog if visible */}
      {showPermissionsDialog && (
        <div className="jp-CollaborationBar-permissionsDialog">
          {/* This would be replaced with the actual PermissionsDialog component */}
          <div className="jp-CollaborationBar-permissionsDialogHeader">
            <h3>{trans.__('Permissions')}</h3>
            <button 
              className="jp-CollaborationBar-closeButton"
              onClick={handlePermissionsDialogToggle}
              aria-label={trans.__('Close permissions dialog')}
            >
              ×
            </button>
          </div>
          <div className="jp-CollaborationBar-permissionsDialogContent">
            <p>{trans.__('Permissions dialog component will be rendered here')}</p>
          </div>
        </div>
      )}
    </div>
  );
};

/**
 * A namespace for CollaborationBarComponent statics.
 */
export namespace CollaborationBarComponent {
  /**
   * Create a new CollaborationBarComponent.
   *
   * @param options - The options for creating the component.
   * @returns A new CollaborationBarComponent widget.
   */
  export const create = (options: {
    notebookPanel: NotebookPanel;
    collaborationService: ICollaborationService;
    presenceService: IPresenceService;
    lockService: ILockService;
    historyService: IHistoryService;
    permissionsService: IPermissionsService;
    commentService: ICommentService;
    translator?: ITranslator;
  }): ReactWidget => {
    const widget = ReactWidget.create(
      <CollaborationBar
        notebookPanel={options.notebookPanel}
        collaborationService={options.collaborationService}
        presenceService={options.presenceService}
        lockService={options.lockService}
        historyService={options.historyService}
        permissionsService={options.permissionsService}
        commentService={options.commentService}
        translator={options.translator}
      />
    );
    widget.addClass('jp-CollaborationBarWidget');
    return widget;
  };
}
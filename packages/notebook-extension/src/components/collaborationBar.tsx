import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { Awareness } from 'y-protocols/awareness';
import { UserPresence, IUser } from './userPresence';

// Styles will be added when the widget is created

/**
 * CSS styles for the CollaborationBar component
 */
const styles = `
.jp-CollaborationBar {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  padding: var(--jp-collab-spacing-sm);
  background-color: var(--jp-layout-color1);
  border-bottom: 1px solid var(--jp-border-color2);
  height: var(--jp-collab-presence-avatar-size, 40px);
  font-family: var(--jp-ui-font-family);
  position: relative;
  z-index: 10;
}

.jp-CollaborationBar-left {
  display: flex;
  align-items: center;
}

.jp-CollaborationBar-right {
  display: flex;
  align-items: center;
}

.jp-CollaborationBar-status {
  display: flex;
  align-items: center;
  margin-right: var(--jp-collab-spacing-md);
  font-size: var(--jp-ui-font-size1);
  color: var(--jp-ui-font-color1);
}

.jp-CollaborationBar-statusIcon {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: var(--jp-collab-spacing-xs);
}

.jp-CollaborationBar-statusIcon-connected {
  background-color: var(--jp-success-color0);
}

.jp-CollaborationBar-statusIcon-connecting {
  background-color: var(--jp-warn-color0);
  animation: jp-CollaborationBar-pulse 1.5s infinite;
}

.jp-CollaborationBar-statusIcon-disconnected {
  background-color: var(--jp-error-color0);
}

@keyframes jp-CollaborationBar-pulse {
  0% {
    opacity: 0.6;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.6;
  }
}

.jp-CollaborationBar-button {
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: transparent;
  border: none;
  border-radius: var(--jp-border-radius);
  padding: var(--jp-collab-spacing-xs) var(--jp-collab-spacing-sm);
  margin-left: var(--jp-collab-spacing-sm);
  cursor: pointer;
  color: var(--jp-ui-font-color1);
  font-size: var(--jp-ui-font-size1);
  transition: background-color 0.2s ease;
}

.jp-CollaborationBar-button:hover {
  background-color: var(--jp-layout-color2);
}

.jp-CollaborationBar-button:focus {
  outline: 2px solid var(--jp-brand-color1);
  outline-offset: 2px;
}

.jp-CollaborationBar-button svg {
  width: 16px;
  height: 16px;
  margin-right: var(--jp-collab-spacing-xs);
  fill: currentColor;
}

.jp-CollaborationBar-activityFeed {
  position: absolute;
  top: 100%;
  right: 0;
  width: 300px;
  max-height: 400px;
  overflow-y: auto;
  background-color: var(--jp-layout-color1);
  border: 1px solid var(--jp-border-color2);
  border-radius: var(--jp-border-radius);
  box-shadow: var(--jp-elevation-z6);
  z-index: 100;
  display: none;
}

.jp-CollaborationBar-activityFeed.jp-CollaborationBar-activityFeed-visible {
  display: block;
}

.jp-CollaborationBar-activityItem {
  padding: var(--jp-collab-spacing-sm);
  border-bottom: 1px solid var(--jp-border-color2);
  font-size: var(--jp-ui-font-size1);
}

.jp-CollaborationBar-activityItem:last-child {
  border-bottom: none;
}

.jp-CollaborationBar-activityHeader {
  display: flex;
  align-items: center;
  margin-bottom: var(--jp-collab-spacing-xs);
}

.jp-CollaborationBar-activityAvatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  margin-right: var(--jp-collab-spacing-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--jp-ui-inverse-font-color0);
  font-weight: 600;
  font-size: 12px;
}

.jp-CollaborationBar-activityUser {
  font-weight: 600;
  margin-right: var(--jp-collab-spacing-xs);
}

.jp-CollaborationBar-activityTime {
  font-size: var(--jp-ui-font-size0);
  color: var(--jp-ui-font-color2);
}

.jp-CollaborationBar-activityContent {
  color: var(--jp-ui-font-color1);
}

.jp-CollaborationBar-notification {
  position: absolute;
  top: 100%;
  right: 20px;
  width: 300px;
  background-color: var(--jp-layout-color1);
  border: 1px solid var(--jp-border-color2);
  border-radius: var(--jp-border-radius);
  box-shadow: var(--jp-elevation-z6);
  z-index: 100;
  padding: var(--jp-collab-spacing-sm);
  animation: jp-CollaborationBar-notification-slide 0.3s ease-out;
  transform-origin: top right;
}

@keyframes jp-CollaborationBar-notification-slide {
  0% {
    transform: translateY(-20px);
    opacity: 0;
  }
  100% {
    transform: translateY(0);
    opacity: 1;
  }
}

.jp-CollaborationBar-notificationHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--jp-collab-spacing-xs);
}

.jp-CollaborationBar-notificationTitle {
  font-weight: 600;
  font-size: var(--jp-ui-font-size1);
}

.jp-CollaborationBar-notificationClose {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--jp-ui-font-color2);
  padding: 2px;
}

.jp-CollaborationBar-notificationClose:hover {
  color: var(--jp-ui-font-color1);
}

.jp-CollaborationBar-notificationContent {
  font-size: var(--jp-ui-font-size1);
  color: var(--jp-ui-font-color1);
}

/* Responsive styles */
@media (max-width: 768px) {
  .jp-CollaborationBar {
    padding: var(--jp-collab-spacing-xs);
  }
  
  .jp-CollaborationBar-status span {
    display: none;
  }
  
  .jp-CollaborationBar-button span {
    display: none;
  }
  
  .jp-CollaborationBar-button svg {
    margin-right: 0;
  }
  
  .jp-CollaborationBar-activityFeed {
    width: 250px;
  }
}

/* Respect reduced motion preferences */
@media (prefers-reduced-motion: reduce) {
  .jp-CollaborationBar-statusIcon-connecting {
    animation: none;
  }
  
  .jp-CollaborationBar-notification {
    animation: none;
  }
}
`;

/**
 * Connection status type
 */
type ConnectionStatus = 'connected' | 'connecting' | 'disconnected';

/**
 * Activity item type
 */
interface IActivityItem {
  /** Unique ID for the activity item */
  id: string;
  /** User who performed the activity */
  user: IUser;
  /** Type of activity */
  type: 'join' | 'leave' | 'edit' | 'comment' | 'lock' | 'unlock' | 'permission';
  /** Timestamp of the activity */
  timestamp: number;
  /** Additional details about the activity */
  details?: {
    /** Cell ID if applicable */
    cellId?: string;
    /** Comment ID if applicable */
    commentId?: string;
    /** Permission level if applicable */
    permission?: string;
    /** Any other relevant information */
    [key: string]: any;
  };
}

/**
 * Notification type
 */
interface INotification {
  /** Unique ID for the notification */
  id: string;
  /** Title of the notification */
  title: string;
  /** Content of the notification */
  content: string;
  /** Type of notification */
  type: 'info' | 'warning' | 'error' | 'success';
  /** Timestamp of the notification */
  timestamp: number;
  /** Auto-dismiss timeout in milliseconds (0 for no auto-dismiss) */
  timeout: number;
}

/**
 * Props for the CollaborationBar component
 */
export interface ICollaborationBarProps {
  /** The Yjs awareness instance */
  awareness: Awareness;
  /** The translator instance */
  translator?: ITranslator;
  /** Connection status */
  connectionStatus?: ConnectionStatus;
  /** Callback when the history button is clicked */
  onHistoryClick?: () => void;
  /** Callback when the permissions button is clicked */
  onPermissionsClick?: () => void;
  /** Callback when the comments button is clicked */
  onCommentsClick?: () => void;
  /** Callback when a user avatar is clicked */
  onUserClick?: (user: IUser) => void;
}

/**
 * A component that displays the collaboration status bar
 */
export const CollaborationBar: React.FC<ICollaborationBarProps> = ({
  awareness,
  translator = nullTranslator,
  connectionStatus = 'connected',
  onHistoryClick,
  onPermissionsClick,
  onCommentsClick,
  onUserClick
}) => {
  const trans = translator.load('notebook');
  const [activityFeedVisible, setActivityFeedVisible] = useState(false);
  const [activityItems, setActivityItems] = useState<IActivityItem[]>([]);
  const [notifications, setNotifications] = useState<INotification[]>([]);
  const activityFeedRef = useRef<HTMLDivElement>(null);
  const activityButtonRef = useRef<HTMLButtonElement>(null);
  
  // Toggle activity feed visibility
  const toggleActivityFeed = useCallback(() => {
    setActivityFeedVisible(!activityFeedVisible);
  }, [activityFeedVisible]);
  
  // Close activity feed when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        activityFeedRef.current && 
        !activityFeedRef.current.contains(event.target as Node) &&
        activityButtonRef.current &&
        !activityButtonRef.current.contains(event.target as Node)
      ) {
        setActivityFeedVisible(false);
      }
    };
    
    if (activityFeedVisible) {
      document.addEventListener('mousedown', handleClickOutside);
    } else {
      document.removeEventListener('mousedown', handleClickOutside);
    }
    
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [activityFeedVisible]);
  
  // Track user presence changes and update activity feed
  useEffect(() => {
    const handleAwarenessChange = ({ added, updated, removed }: any) => {
      const newActivityItems: IActivityItem[] = [];
      
      // Handle added users (joined)
      added.forEach((clientId: number) => {
        const state = awareness.getStates().get(clientId);
        if (state && state.user) {
          newActivityItems.push({
            id: `join-${clientId}-${Date.now()}`,
            user: {
              id: clientId,
              state: state.user
            },
            type: 'join',
            timestamp: Date.now()
          });
          
          // Show notification for new user
          addNotification({
            id: `join-notification-${clientId}-${Date.now()}`,
            title: trans.__('User joined'),
            content: trans.__('%1 joined the collaboration', state.user.name),
            type: 'info',
            timestamp: Date.now(),
            timeout: 5000
          });
        }
      });
      
      // Handle removed users (left)
      removed.forEach((clientId: number) => {
        // We need to find the user in our activity items since they're already removed from awareness
        const existingItems = activityItems.filter(item => item.user.id === clientId);
        if (existingItems.length > 0) {
          const user = existingItems[0].user;
          newActivityItems.push({
            id: `leave-${clientId}-${Date.now()}`,
            user,
            type: 'leave',
            timestamp: Date.now()
          });
          
          // Show notification for user leaving
          addNotification({
            id: `leave-notification-${clientId}-${Date.now()}`,
            title: trans.__('User left'),
            content: trans.__('%1 left the collaboration', user.state.name),
            type: 'info',
            timestamp: Date.now(),
            timeout: 5000
          });
        }
      });
      
      if (newActivityItems.length > 0) {
        setActivityItems(prevItems => {
          // Keep only the last 50 items to prevent the list from growing too large
          const updatedItems = [...newActivityItems, ...prevItems];
          return updatedItems.slice(0, 50);
        });
      }
    };
    
    // Subscribe to awareness changes
    awareness.on('change', handleAwarenessChange);
    
    // Listen for custom activity events from other components
    const handleCustomActivity = (event: CustomEvent) => {
      const { type, details, timestamp } = event.detail;
      
      // Get the local user from awareness
      const localState = awareness.getLocalState();
      if (localState && localState.user) {
        const user: IUser = {
          id: awareness.clientID,
          state: localState.user
        };
        
        const activityItem: IActivityItem = {
          id: `activity-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          user,
          type,
          timestamp: timestamp || Date.now(),
          details
        };
        
        setActivityItems(prevItems => {
          const updatedItems = [activityItem, ...prevItems];
          return updatedItems.slice(0, 50);
        });
      }
    };
    
    // Listen for custom notification events from other components
    const handleCustomNotification = (event: CustomEvent) => {
      addNotification(event.detail);
    };
    
    // Listen for connection status updates from other components
    const handleConnectionStatus = (event: CustomEvent) => {
      const { status } = event.detail;
      // This would be handled by a parent component that passes connectionStatus as a prop
      // But we're adding the event listener for completeness
    };
    
    document.addEventListener('jp-collaboration-activity', handleCustomActivity as EventListener);
    document.addEventListener('jp-collaboration-notification', handleCustomNotification as EventListener);
    document.addEventListener('jp-collaboration-status', handleConnectionStatus as EventListener);
    
    return () => {
      awareness.off('change', handleAwarenessChange);
      document.removeEventListener('jp-collaboration-activity', handleCustomActivity as EventListener);
      document.removeEventListener('jp-collaboration-notification', handleCustomNotification as EventListener);
      document.removeEventListener('jp-collaboration-status', handleConnectionStatus as EventListener);
    };
  }, [awareness, activityItems, trans, addNotification]);
  
  // Add a notification
  const addNotification = useCallback((notification: INotification) => {
    setNotifications(prevNotifications => [
      notification,
      ...prevNotifications
    ]);
    
    // Set up auto-dismiss if timeout is greater than 0
    if (notification.timeout > 0) {
      setTimeout(() => {
        dismissNotification(notification.id);
      }, notification.timeout);
    }
  }, []);
  
  // Dismiss a notification
  const dismissNotification = useCallback((id: string) => {
    setNotifications(prevNotifications => 
      prevNotifications.filter(notification => notification.id !== id)
    );
  }, []);
  
  // Format timestamp
  const formatTime = (timestamp: number): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };
  
  // Render activity item content
  const renderActivityContent = (item: IActivityItem): string => {
    const { type, user, details } = item;
    const userName = user.state.name;
    
    switch (type) {
      case 'join':
        return trans.__('%1 joined the collaboration', userName);
      case 'leave':
        return trans.__('%1 left the collaboration', userName);
      case 'edit':
        return details?.cellId
          ? trans.__('%1 edited cell %2', userName, details.cellId)
          : trans.__('%1 made an edit', userName);
      case 'comment':
        return trans.__('%1 added a comment', userName);
      case 'lock':
        return details?.cellId
          ? trans.__('%1 locked cell %2', userName, details.cellId)
          : trans.__('%1 locked a cell', userName);
      case 'unlock':
        return details?.cellId
          ? trans.__('%1 unlocked cell %2', userName, details.cellId)
          : trans.__('%1 unlocked a cell', userName);
      case 'permission':
        return details?.permission
          ? trans.__('%1 changed permissions to %2', userName, details.permission)
          : trans.__('%1 changed permissions', userName);
      default:
        return trans.__('%1 performed an action', userName);
    }
  };
  
  // Get status text based on connection status
  const getStatusText = (): string => {
    switch (connectionStatus) {
      case 'connected':
        return trans.__('Connected');
      case 'connecting':
        return trans.__('Connecting...');
      case 'disconnected':
        return trans.__('Disconnected');
      default:
        return trans.__('Unknown status');
    }
  };
  
  // SVG icons
  const historyIcon = (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <path d="M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z" />
    </svg>
  );
  
  const permissionsIcon = (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z" />
    </svg>
  );
  
  const commentsIcon = (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <path d="M21.99 4c0-1.1-.89-2-1.99-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h14l4 4-.01-18zM18 14H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z" />
    </svg>
  );
  
  const activityIcon = (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <path d="M13.5.67s.74 2.65.74 4.8c0 2.06-1.35 3.73-3.41 3.73-2.07 0-3.63-1.67-3.63-3.73l.03-.36C5.21 7.51 4 10.62 4 14c0 4.42 3.58 8 8 8s8-3.58 8-8C20 8.61 17.41 3.8 13.5.67zM11.71 19c-1.78 0-3.22-1.4-3.22-3.14 0-1.62 1.05-2.76 2.81-3.12 1.77-.36 3.6-1.21 4.62-2.58.39 1.29.59 2.65.59 4.04 0 2.65-2.15 4.8-4.8 4.8z" />
    </svg>
  );
  
  return (
    <div className="jp-CollaborationBar" role="region" aria-label={trans.__('Collaboration tools')}>
      <div className="jp-CollaborationBar-left">
        <div className="jp-CollaborationBar-status" aria-live="polite">
          <div 
            className={`jp-CollaborationBar-statusIcon jp-CollaborationBar-statusIcon-${connectionStatus}`}
            aria-hidden="true"
          />
          <span>{getStatusText()}</span>
        </div>
        
        <UserPresence 
          awareness={awareness}
          translator={translator}
          maxAvatars={5}
          showStatus={true}
          onUserClick={onUserClick}
        />
      </div>
      
      <div className="jp-CollaborationBar-right">
        <button 
          className="jp-CollaborationBar-button"
          onClick={onHistoryClick}
          aria-label={trans.__('Version history')}
          title={trans.__('Version history')}
        >
          {historyIcon}
          <span>{trans.__('History')}</span>
        </button>
        
        <button 
          className="jp-CollaborationBar-button"
          onClick={onPermissionsClick}
          aria-label={trans.__('Manage permissions')}
          title={trans.__('Manage permissions')}
        >
          {permissionsIcon}
          <span>{trans.__('Permissions')}</span>
        </button>
        
        <button 
          className="jp-CollaborationBar-button"
          onClick={onCommentsClick}
          aria-label={trans.__('View comments')}
          title={trans.__('View comments')}
        >
          {commentsIcon}
          <span>{trans.__('Comments')}</span>
        </button>
        
        <button 
          className="jp-CollaborationBar-button"
          onClick={toggleActivityFeed}
          aria-label={trans.__('Activity feed')}
          title={trans.__('Activity feed')}
          aria-expanded={activityFeedVisible}
          aria-controls="jp-CollaborationBar-activityFeed"
          ref={activityButtonRef}
        >
          {activityIcon}
          <span>{trans.__('Activity')}</span>
        </button>
        
        <div 
          id="jp-CollaborationBar-activityFeed"
          className={`jp-CollaborationBar-activityFeed ${activityFeedVisible ? 'jp-CollaborationBar-activityFeed-visible' : ''}`}
          ref={activityFeedRef}
          role="log"
          aria-label={trans.__('Collaboration activity feed')}
        >
          {activityItems.length === 0 ? (
            <div className="jp-CollaborationBar-activityItem">
              <div className="jp-CollaborationBar-activityContent">
                {trans.__('No recent activity')}
              </div>
            </div>
          ) : (
            activityItems.map(item => (
              <div key={item.id} className="jp-CollaborationBar-activityItem">
                <div className="jp-CollaborationBar-activityHeader">
                  <div 
                    className="jp-CollaborationBar-activityAvatar"
                    style={{ backgroundColor: item.user.state.color }}
                  >
                    {item.user.state.name.substring(0, 2).toUpperCase()}
                  </div>
                  <div className="jp-CollaborationBar-activityUser">
                    {item.user.state.name}
                  </div>
                  <div className="jp-CollaborationBar-activityTime">
                    {formatTime(item.timestamp)}
                  </div>
                </div>
                <div className="jp-CollaborationBar-activityContent">
                  {renderActivityContent(item)}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
      
      {/* Notifications */}
      {notifications.map(notification => (
        <div 
          key={notification.id} 
          className="jp-CollaborationBar-notification"
          role="alert"
        >
          <div className="jp-CollaborationBar-notificationHeader">
            <div className="jp-CollaborationBar-notificationTitle">
              {notification.title}
            </div>
            <button 
              className="jp-CollaborationBar-notificationClose"
              onClick={() => dismissNotification(notification.id)}
              aria-label={trans.__('Dismiss notification')}
            >
              ×
            </button>
          </div>
          <div className="jp-CollaborationBar-notificationContent">
            {notification.content}
          </div>
        </div>
      ))}
    </div>
  );
};

/**
 * A namespace for CollaborationBar statics.
 */
export namespace CollaborationBar {
  /**
   * Create a new CollaborationBar component
   */
  export function create(options: ICollaborationBarProps): JSX.Element {
    return <CollaborationBar {...options} />;
  }

  /**
   * Create a ReactWidget containing the CollaborationBar component
   * 
   * @param options - The options for the CollaborationBar component
   * @returns A ReactWidget containing the CollaborationBar component
   */
  export function createWidget(options: ICollaborationBarProps): ReactWidget {
    // Add the styles to the document
    const styleElement = document.createElement('style');
    styleElement.textContent = styles;
    document.head.appendChild(styleElement);

    // Create the widget
    const widget = ReactWidget.create(<CollaborationBar {...options} />);
    widget.addClass('jp-CollaborationBar-widget');
    return widget;
  }

  /**
   * Add an activity item to the activity feed
   * 
   * @param awareness - The Yjs awareness instance
   * @param type - The type of activity
   * @param details - Additional details about the activity
   */
  export function addActivity(
    awareness: Awareness,
    type: IActivityItem['type'],
    details?: IActivityItem['details']
  ): void {
    // This is a helper method that can be called from other components
    // It creates a custom event that the CollaborationBar component can listen to
    const event = new CustomEvent('jp-collaboration-activity', {
      detail: {
        type,
        details,
        timestamp: Date.now()
      }
    });
    document.dispatchEvent(event);
  }

  /**
   * Show a notification in the CollaborationBar
   * 
   * @param title - The title of the notification
   * @param content - The content of the notification
   * @param type - The type of notification
   * @param timeout - Auto-dismiss timeout in milliseconds (0 for no auto-dismiss)
   */
  export function showNotification(
    title: string,
    content: string,
    type: INotification['type'] = 'info',
    timeout: number = 5000
  ): void {
    // This is a helper method that can be called from other components
    // It creates a custom event that the CollaborationBar component can listen to
    const event = new CustomEvent('jp-collaboration-notification', {
      detail: {
        id: `notification-${Date.now()}`,
        title,
        content,
        type,
        timestamp: Date.now(),
        timeout
      }
    });
    document.dispatchEvent(event);
  }

  /**
   * Update the connection status in the CollaborationBar
   * 
   * @param status - The new connection status
   */
  export function updateConnectionStatus(status: ConnectionStatus): void {
    // This is a helper method that can be called from other components
    // It creates a custom event that the CollaborationBar component can listen to
    const event = new CustomEvent('jp-collaboration-status', {
      detail: { status }
    });
    document.dispatchEvent(event);
  }
}
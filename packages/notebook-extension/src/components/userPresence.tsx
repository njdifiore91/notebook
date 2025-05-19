import React, { useEffect, useState, useCallback, useRef } from 'react';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { Awareness } from 'y-protocols/awareness';
import { ReactWidget } from '@jupyterlab/apputils';

/**
 * CSS styles for the UserPresence component
 */
const styles = `
.jp-UserPresence {
  display: flex;
  flex-direction: column;
  padding: var(--jp-collab-spacing-sm);
  font-family: var(--jp-ui-font-family);
}

.jp-UserPresence-avatars {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: var(--jp-collab-spacing-xs);
}

.jp-UserPresence-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: calc(-1 * var(--jp-collab-spacing-xs));
  border: 2px solid var(--jp-layout-color1);
  color: var(--jp-ui-inverse-font-color0);
  font-weight: 600;
  font-size: 13px;
  position: relative;
  cursor: pointer;
  transition: transform 0.2s ease;
  background-size: cover;
  background-position: center;
}

.jp-UserPresence-avatar:hover {
  transform: translateY(-2px);
  z-index: 10 !important;
}

.jp-UserPresence-avatar:focus {
  outline: 2px solid var(--jp-brand-color1);
  outline-offset: 2px;
}

.jp-UserPresence-statusIndicator {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--jp-layout-color1);
}

.jp-UserPresence-statusIndicator-active {
  background-color: var(--jp-success-color0);
}

.jp-UserPresence-statusIndicator-idle {
  background-color: var(--jp-warn-color0);
}

.jp-UserPresence-statusIndicator-away {
  background-color: var(--jp-error-color0);
}

.jp-UserPresence-more {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--jp-layout-color3);
  color: var(--jp-ui-font-color1);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  border: 2px solid var(--jp-layout-color1);
  transition: background-color 0.2s ease;
}

.jp-UserPresence-more:hover {
  background-color: var(--jp-layout-color4);
}

.jp-UserPresence-more:focus {
  outline: 2px solid var(--jp-brand-color1);
  outline-offset: 2px;
}

.jp-UserPresence-collapse {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--jp-layout-color3);
  color: var(--jp-ui-font-color1);
  font-weight: 600;
  font-size: 16px;
  cursor: pointer;
  margin-left: var(--jp-collab-spacing-sm);
  border: 2px solid var(--jp-layout-color1);
  transition: background-color 0.2s ease;
}

.jp-UserPresence-collapse:hover {
  background-color: var(--jp-layout-color4);
}

.jp-UserPresence-collapse:focus {
  outline: 2px solid var(--jp-brand-color1);
  outline-offset: 2px;
}

.jp-UserPresence-count {
  font-size: 11px;
  color: var(--jp-ui-font-color2);
  margin-top: var(--jp-collab-spacing-xs);
}

.jp-UserPresence-expanded .jp-UserPresence-avatars {
  flex-wrap: wrap;
  max-width: 300px;
}

.jp-UserPresence-expanded .jp-UserPresence-avatar {
  margin: var(--jp-collab-spacing-xs);
}

/* Responsive styles */
@media (max-width: 524px) {
  .jp-UserPresence-avatars {
    max-width: 100px;
  }
  
  .jp-UserPresence-avatar {
    width: 28px;
    height: 28px;
    font-size: 11px;
  }
  
  .jp-UserPresence-more,
  .jp-UserPresence-collapse {
    width: 28px;
    height: 28px;
  }
  
  .jp-UserPresence-count {
    display: none;
  }
}

/* Respect reduced motion preferences */
@media (prefers-reduced-motion: reduce) {
  .jp-UserPresence-avatar {
    transition: none;
  }
}
`;

/**
 * Interface for user awareness state
 */
export interface IUserAwarenessState {
  /** The user's name */
  name: string;
  /** The user's color */
  color: string;
  /** The user's avatar URL (optional) */
  avatar?: string;
  /** The user's status (active, idle, etc.) */
  status?: 'active' | 'idle' | 'away';
  /** The user's current cell ID (if any) */
  currentCellId?: string;
  /** The user's cursor position */
  cursor?: {
    /** The cell ID where the cursor is located */
    cellId: string;
    /** The position within the cell */
    position: number;
  };
  /** The user's text selection (if any) */
  selection?: {
    /** The cell ID where the selection is located */
    cellId: string;
    /** The start position of the selection */
    start: number;
    /** The end position of the selection */
    end: number;
  };
}

/**
 * Interface for a user in the presence system
 */
export interface IUser {
  /** The user's client ID */
  id: number;
  /** The user's awareness state */
  state: IUserAwarenessState;
}

/**
 * Props for the UserPresence component
 */
export interface IUserPresenceProps {
  /** The Yjs awareness instance */
  awareness: Awareness;
  /** The translator instance */
  translator?: ITranslator;
  /** Maximum number of avatars to show before collapsing */
  maxAvatars?: number;
  /** Whether to show user status indicators */
  showStatus?: boolean;
  /** Callback when a user avatar is clicked */
  onUserClick?: (user: IUser) => void;
}

/**
 * Props for the UserAvatar component
 */
interface IUserAvatarProps {
  /** The user object */
  user: IUser;
  /** The translator instance */
  translator: ITranslator;
  /** Whether to show the user's status */
  showStatus?: boolean;
  /** Callback when the avatar is clicked */
  onClick?: (user: IUser) => void;
  /** The z-index for stacking avatars */
  zIndex?: number;
}

/**
 * A component that displays a user's avatar
 */
const UserAvatar: React.FC<IUserAvatarProps> = ({
  user,
  translator,
  showStatus = true,
  onClick,
  zIndex = 1
}) => {
  const trans = translator.load('notebook');
  const { state } = user;
  const { name, color, avatar, status } = state;
  
  // Generate initials from name
  const initials = name
    .split(' ')
    .map(part => part[0])
    .join('')
    .substring(0, 2)
    .toUpperCase();

  // Status indicator classes
  const statusClass = status ? `jp-UserPresence-status-${status}` : '';
  
  // Handle click event
  const handleClick = useCallback(() => {
    if (onClick) {
      onClick(user);
    }
  }, [onClick, user]);

  // Determine title text based on status
  let titleText = name;
  if (status === 'active' && state.currentCellId) {
    titleText = trans.__('%1 (active in cell %2)', name, state.currentCellId);
  } else if (status === 'idle') {
    titleText = trans.__('%1 (idle)', name);
  } else if (status === 'away') {
    titleText = trans.__('%1 (away)', name);
  }

  return (
    <div 
      className={`jp-UserPresence-avatar ${statusClass}`}
      style={{
        backgroundColor: color,
        zIndex,
        backgroundImage: avatar ? `url(${avatar})` : undefined
      }}
      onClick={handleClick}
      title={titleText}
      role="button"
      aria-label={titleText}
      tabIndex={0}
    >
      {!avatar && initials}
      {showStatus && status && (
        <div 
          className={`jp-UserPresence-statusIndicator jp-UserPresence-statusIndicator-${status}`}
          aria-hidden="true"
        />
      )}
    </div>
  );
};

/**
 * A component that displays user presence information
 */
export const UserPresence: React.FC<IUserPresenceProps> = ({
  awareness,
  translator = nullTranslator,
  maxAvatars = 5,
  showStatus = true,
  onUserClick
}) => {
  const trans = translator.load('notebook');
  const [users, setUsers] = useState<IUser[]>([]);
  const [expanded, setExpanded] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Update users when awareness changes
  useEffect(() => {
    const updateUsers = () => {
      const states = awareness.getStates();
      const userList: IUser[] = [];
      
      // Convert awareness states to user objects
      states.forEach((state: any, id: number) => {
        if (state.user) {
          userList.push({
            id,
            state: state.user as IUserAwarenessState
          });
        }
      });
      
      // Sort users by name
      userList.sort((a, b) => a.state.name.localeCompare(b.state.name));
      
      setUsers(userList);
    };

    // Initial update
    updateUsers();

    // Subscribe to awareness changes
    awareness.on('change', updateUsers);
    
    return () => {
      // Unsubscribe when component unmounts
      awareness.off('change', updateUsers);
    };
  }, [awareness]);

  // Toggle expanded state
  const toggleExpanded = useCallback(() => {
    setExpanded(!expanded);
  }, [expanded]);

  // Handle user click
  const handleUserClick = useCallback((user: IUser) => {
    if (onUserClick) {
      onUserClick(user);
    }
  }, [onUserClick]);

  // Determine which users to display
  const visibleUsers = expanded ? users : users.slice(0, maxAvatars);
  const hiddenCount = users.length - maxAvatars;
  const showMoreButton = !expanded && hiddenCount > 0;

  return (
    <div 
      className={`jp-UserPresence ${expanded ? 'jp-UserPresence-expanded' : ''}`}
      ref={containerRef}
      role="region"
      aria-label={trans.__('User presence')}
    >
      <div className="jp-UserPresence-avatars">
        {visibleUsers.map((user, index) => (
          <UserAvatar
            key={user.id}
            user={user}
            translator={translator}
            showStatus={showStatus}
            onClick={handleUserClick}
            zIndex={users.length - index}
          />
        ))}
        
        {showMoreButton && (
          <div 
            className="jp-UserPresence-more"
            onClick={toggleExpanded}
            role="button"
            aria-label={trans.__('Show %1 more users', hiddenCount)}
            title={trans.__('Show %1 more users', hiddenCount)}
            tabIndex={0}
          >
            +{hiddenCount}
          </div>
        )}

        {expanded && (
          <div 
            className="jp-UserPresence-collapse"
            onClick={toggleExpanded}
            role="button"
            aria-label={trans.__('Collapse user list')}
            title={trans.__('Collapse user list')}
            tabIndex={0}
          >
            <span aria-hidden="true">−</span>
          </div>
        )}
      </div>

      <div className="jp-UserPresence-count" aria-live="polite">
        {users.length > 0 ? (
          <span>{trans.__('%1 users online', users.length)}</span>
        ) : (
          <span>{trans.__('No other users online')}</span>
        )}
      </div>
    </div>
  );
};

/**
 * A namespace for UserPresence statics.
 */
export namespace UserPresence {
  /**
   * Create a new UserPresence component
   */
  export function create(options: IUserPresenceProps): JSX.Element {
    return <UserPresence {...options} />;
  }

  /**
   * Create a ReactWidget containing the UserPresence component
   * 
   * @param options - The options for the UserPresence component
   * @returns A ReactWidget containing the UserPresence component
   */
  export function createWidget(options: IUserPresenceProps): ReactWidget {
    // Add the styles to the document
    const styleElement = document.createElement('style');
    styleElement.textContent = styles;
    document.head.appendChild(styleElement);

    // Create the widget
    const widget = ReactWidget.create(<UserPresence {...options} />);
    widget.addClass('jp-UserPresence-widget');
    return widget;
  }

  /**
   * Set the local user's awareness state
   * 
   * @param awareness - The Yjs awareness instance
   * @param state - The user state to set
   */
  export function setLocalUserState(
    awareness: Awareness,
    state: Partial<IUserAwarenessState>
  ): void {
    const currentState = awareness.getLocalState()?.user || {};
    awareness.setLocalStateField('user', {
      ...currentState,
      ...state
    });
  }

  /**
   * Get the local user's awareness state
   * 
   * @param awareness - The Yjs awareness instance
   * @returns The local user's awareness state
   */
  export function getLocalUserState(
    awareness: Awareness
  ): IUserAwarenessState | undefined {
    return awareness.getLocalState()?.user as IUserAwarenessState;
  }

  /**
   * Get all users from the awareness instance
   * 
   * @param awareness - The Yjs awareness instance
   * @returns Array of users
   */
  export function getAllUsers(awareness: Awareness): IUser[] {
    const states = awareness.getStates();
    const users: IUser[] = [];
    
    states.forEach((state: any, id: number) => {
      if (state.user) {
        users.push({
          id,
          state: state.user as IUserAwarenessState
        });
      }
    });
    
    return users;
  }

  /**
   * Generate a random color for a user
   * 
   * @returns A random color in hex format
   */
  export function generateUserColor(): string {
    // Use the collaboration color palette defined in the design system
    // These are pastel colors that work well with dark text
    const colors = [
      '#FFB6C1', // Light Pink
      '#FFD700', // Gold
      '#98FB98', // Pale Green
      '#87CEFA', // Light Sky Blue
      '#FFA07A', // Light Salmon
      '#DDA0DD', // Plum
      '#FFFACD', // Lemon Chiffon
      '#AFEEEE', // Pale Turquoise
      '#D8BFD8', // Thistle
      '#B0E0E6'  // Powder Blue
    ];
    
    return colors[Math.floor(Math.random() * colors.length)];
  }

  /**
   * Initialize the local user's awareness state with default values
   * 
   * @param awareness - The Yjs awareness instance
   * @param name - The user's name (defaults to 'Anonymous')
   */
  export function initializeLocalUser(
    awareness: Awareness,
    name: string = 'Anonymous'
  ): void {
    setLocalUserState(awareness, {
      name,
      color: generateUserColor(),
      status: 'active'
    });
  }
  
  /**
   * Update the cursor position for the local user
   * 
   * @param awareness - The Yjs awareness instance
   * @param cellId - The ID of the cell where the cursor is located
   * @param position - The position within the cell
   */
  export function updateCursorPosition(
    awareness: Awareness,
    cellId: string,
    position: number
  ): void {
    setLocalUserState(awareness, {
      cursor: {
        cellId,
        position
      }
    });
  }
  
  /**
   * Update the text selection for the local user
   * 
   * @param awareness - The Yjs awareness instance
   * @param cellId - The ID of the cell where the selection is located
   * @param start - The start position of the selection
   * @param end - The end position of the selection
   */
  export function updateTextSelection(
    awareness: Awareness,
    cellId: string,
    start: number,
    end: number
  ): void {
    setLocalUserState(awareness, {
      selection: {
        cellId,
        start,
        end
      }
    });
  }
  
  /**
   * Update the current cell for the local user
   * 
   * @param awareness - The Yjs awareness instance
   * @param cellId - The ID of the current cell
   */
  export function updateCurrentCell(
    awareness: Awareness,
    cellId: string
  ): void {
    setLocalUserState(awareness, {
      currentCellId: cellId
    });
  }
  
  /**
   * Start tracking user activity to automatically update status
   * 
   * @param awareness - The Yjs awareness instance
   * @param idleTimeout - Time in milliseconds before user is considered idle (default: 60000 = 1 minute)
   * @param awayTimeout - Time in milliseconds before user is considered away (default: 300000 = 5 minutes)
   * @returns A function to stop tracking
   */
  export function startActivityTracking(
    awareness: Awareness,
    idleTimeout: number = 60000,
    awayTimeout: number = 300000
  ): () => void {
    let idleTimer: number | null = null;
    let awayTimer: number | null = null;
    let lastActivity = Date.now();
    
    // Set initial status to active
    setLocalUserState(awareness, { status: 'active' });
    
    // Function to handle user activity
    const handleActivity = () => {
      lastActivity = Date.now();
      
      // Clear existing timers
      if (idleTimer !== null) {
        window.clearTimeout(idleTimer);
        idleTimer = null;
      }
      
      if (awayTimer !== null) {
        window.clearTimeout(awayTimer);
        awayTimer = null;
      }
      
      // Get current status
      const currentStatus = getLocalUserState(awareness)?.status;
      
      // Only update if status is not already active
      if (currentStatus !== 'active') {
        setLocalUserState(awareness, { status: 'active' });
      }
      
      // Set new timers
      idleTimer = window.setTimeout(() => {
        setLocalUserState(awareness, { status: 'idle' });
      }, idleTimeout);
      
      awayTimer = window.setTimeout(() => {
        setLocalUserState(awareness, { status: 'away' });
      }, awayTimeout);
    };
    
    // Set up event listeners for user activity
    window.addEventListener('mousemove', handleActivity);
    window.addEventListener('keydown', handleActivity);
    window.addEventListener('click', handleActivity);
    window.addEventListener('scroll', handleActivity);
    window.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        setLocalUserState(awareness, { status: 'away' });
      } else {
        handleActivity();
      }
    });
    
    // Initial activity trigger
    handleActivity();
    
    // Return function to stop tracking
    return () => {
      window.removeEventListener('mousemove', handleActivity);
      window.removeEventListener('keydown', handleActivity);
      window.removeEventListener('click', handleActivity);
      window.removeEventListener('scroll', handleActivity);
      window.removeEventListener('visibilitychange', handleActivity);
      
      if (idleTimer !== null) {
        window.clearTimeout(idleTimer);
      }
      
      if (awayTimer !== null) {
        window.clearTimeout(awayTimer);
      }
    };
  }
}
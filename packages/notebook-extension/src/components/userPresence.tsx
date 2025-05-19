import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { Awareness } from 'y-protocols/awareness';
import { IPresenceService } from '../tokens';

/**
 * Interface for user state in the awareness protocol
 * 
 * This interface defines the structure of user state data that is shared
 * through the Yjs awareness protocol. Each connected client maintains its own
 * state object with this structure, which is then synchronized with all other
 * clients in real-time.
 * 
 * The awareness protocol is a simple CRDT (Conflict-free Replicated Data Type)
 * that manages user status and propagates awareness information like cursor
 * location, username, and other metadata.
 * 
 * @see Technical Specification Section 3.2.2 - Frontend Frameworks
 */
interface IUserState {
  /** User's name or identifier */
  name: string;
  /** User's color for visual identification */
  color: string;
  /** User's avatar URL or placeholder */
  avatar?: string;
  /** User's current status (active, idle, etc.) */
  status?: 'active' | 'idle' | 'viewing' | 'editing';
  /** User's current cursor position */
  cursor?: {
    /** Cell ID where cursor is located */
    cellId: string;
    /** Position within the cell */
    position: number;
  };
  /** User's current selection range */
  selection?: {
    /** Cell ID where selection starts */
    cellId: string;
    /** Start position of selection */
    start: number;
    /** End position of selection */
    end: number;
  };
  /** Timestamp of last activity */
  lastActive?: number;
}

/**
 * Props for the UserPresence component
 */
interface IUserPresenceProps {
  /** The Yjs awareness instance */
  awareness: Awareness;
  /** Optional presence service for additional functionality */
  presenceService?: IPresenceService;
  /** Optional translator for i18n */
  translator?: ITranslator;
  /** Optional maximum number of avatars to display before showing a count */
  maxAvatars?: number;
  /** Optional flag to force collapsed view */
  forceCollapsed?: boolean;
}

/**
 * A React component that displays user presence information in a collaborative notebook.
 * Shows avatars and indicators for users currently viewing or editing the notebook.
 * 
 * This component integrates with the Yjs awareness protocol to track and display real-time
 * user information, including:
 * - User avatars with status indicators
 * - Current editing/viewing status
 * - Cursor positions and selections
 * - Last active timestamps
 * 
 * The component is responsive and adapts to different viewport sizes:
 * - Mobile (<524px): Collapsed view with only current user avatar and count
 * - Tablet (524-800px): Limited number of avatars with overflow indicator
 * - Desktop (>800px): Full presence bar with all active users visible
 * 
 * Accessibility features include:
 * - ARIA attributes for screen readers
 * - Keyboard navigation support
 * - High-contrast visual indicators beyond just color
 * - Reduced motion support via CSS
 * 
 * @see Technical Specification Section 7.1.1.1 - Collaboration Services Architecture
 * @see Technical Specification Section 7.1.1.2 - Collaboration-Specific UI Components
 */
export const UserPresence = (props: IUserPresenceProps): JSX.Element => {
  const { 
    awareness, 
    presenceService,
    translator = nullTranslator,
    maxAvatars = 5,
    forceCollapsed = false
  } = props;
  const trans = translator.load('notebook');
  
  // State to track all users' awareness information
  const [users, setUsers] = useState<Map<number, IUserState>>(new Map());
  // State to track if the component is in a collapsed state (for responsive design)
  const [isCollapsed, setIsCollapsed] = useState(false);

  // Update users when awareness changes
  const handleAwarenessUpdate = useCallback(() => {
    // Get all user states from awareness
    const states = awareness.getStates();
    setUsers(new Map(states));
  }, [awareness]);

  // Set up awareness change listener
  useEffect(() => {
    // Initial update
    handleAwarenessUpdate();
    
    // Listen for awareness changes
    awareness.on('change', handleAwarenessUpdate);
    
    // Clean up listener on unmount
    return () => {
      awareness.off('change', handleAwarenessUpdate);
    };
  }, [awareness, handleAwarenessUpdate]);

  // Set up responsive behavior
  useEffect(() => {
    const handleResize = () => {
      // Collapse on mobile viewports (<524px)
      setIsCollapsed(window.innerWidth < 524 || forceCollapsed);
    };
    
    // Initial check
    handleResize();
    
    // Listen for window resize
    window.addEventListener('resize', handleResize);
    
    // Clean up listener on unmount
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [forceCollapsed]);
  
  // Reference to the container element for focus management
  const containerRef = useRef<HTMLDivElement>(null);

  // Get current user's client ID
  const currentClientId = useMemo(() => awareness.doc.clientID, [awareness]);

  // Filter out current user and sort users by status (active first)
  const otherUsers = useMemo(() => {
    const userArray = Array.from(users.entries())
      .filter(([clientId]) => clientId !== currentClientId)
      .map(([clientId, state]) => ({ clientId, state: state as IUserState }));
    
    // Sort by status: active/editing first, then idle/viewing
    return userArray.sort((a, b) => {
      const statusPriority = (status?: string) => {
        switch (status) {
          case 'editing': return 0;
          case 'active': return 1;
          case 'viewing': return 2;
          case 'idle': return 3;
          default: return 4;
        }
      };
      
      return statusPriority(a.state.status) - statusPriority(b.state.status);
    });
  }, [users, currentClientId]);

  // Get current user's state
  const currentUser = useMemo(() => {
    const state = users.get(currentClientId) as IUserState | undefined;
    return state ? { clientId: currentClientId, state } : undefined;
  }, [users, currentClientId]);

  // Handle click on a user avatar to focus on their cursor position
  const handleAvatarClick = useCallback((clientId: number, state: IUserState) => {
    if (presenceService && state.cursor) {
      presenceService.focusOnUserCursor(clientId);
    }
  }, [presenceService]);

  // Render user avatar with appropriate status indicator
  const renderUserAvatar = (clientId: number, state: IUserState) => {
    const statusClass = `jp-UserPresence-status-${state.status || 'active'}`;
    const avatarStyle = {
      backgroundColor: state.color || '#ccc',
    };
    
    // Get initials from name for avatar placeholder
    const initials = state.name
      ? state.name
          .split(' ')
          .map(part => part.charAt(0))
          .slice(0, 2)
          .join('')
      : '?';
    
    // Determine if this user has cursor/selection information
    const hasCursor = Boolean(state.cursor);
    const hasSelection = Boolean(state.selection);
    const lastActiveTime = state.lastActive ? new Date(state.lastActive).toLocaleTimeString() : '';
    const tooltipText = `${state.name || 'Unknown user'} (${state.status || 'active'})
${hasCursor ? 'Has cursor in document' : ''}
${hasSelection ? 'Has active selection' : ''}
${lastActiveTime ? `Last active: ${lastActiveTime}` : ''}`;

    return (
      <div 
        key={clientId} 
        className={`jp-UserPresence-avatar ${hasCursor ? 'jp-UserPresence-avatar-withCursor' : ''}`}
        style={avatarStyle}
        title={tooltipText}
        aria-label={`${state.name || 'Unknown user'} is ${state.status || 'active'}`}
        onClick={() => handleAvatarClick(clientId, state)}
        tabIndex={0}
        role="button"
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            handleAvatarClick(clientId, state);
            e.preventDefault();
          }
        }}
      >
        {state.avatar ? (
          <img 
            src={state.avatar} 
            alt={state.name || 'User avatar'} 
            className="jp-UserPresence-avatarImg"
          />
        ) : (
          <span className="jp-UserPresence-initials">{initials}</span>
        )}
        <span className={`jp-UserPresence-statusIndicator ${statusClass}`} />
      </div>
    );
  };

  // Render collapsed view (mobile)
  if (isCollapsed) {
    const userCount = otherUsers.length;
    
    return (
      <div 
        ref={containerRef}
        className="jp-UserPresence jp-UserPresence-collapsed" 
        role="region" 
        aria-label={trans.__('Collaborators')}
        aria-live="polite"
      >
        {currentUser && renderUserAvatar(currentUser.clientId, currentUser.state)}
        
        {userCount > 0 && (
          <div 
            className="jp-UserPresence-counter"
            aria-label={trans.__('%1 other collaborators', userCount)}
            role="button"
            tabIndex={0}
            onClick={() => setIsCollapsed(false)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                setIsCollapsed(false);
                e.preventDefault();
              }
            }}
          >
            +{userCount}
          </div>
        )}
      </div>
    );
  }

  // Render expanded view (tablet/desktop)
  return (
    <div 
      ref={containerRef}
      className="jp-UserPresence" 
      role="region" 
      aria-label={trans.__('Collaborators')}
      aria-live="polite"
    >
      <div className="jp-UserPresence-header">
        <span className="jp-UserPresence-title">{trans.__('Collaborators')}</span>
        <button 
          className="jp-UserPresence-collapseButton" 
          onClick={() => setIsCollapsed(true)}
          aria-label={trans.__('Collapse collaborator list')}
          title={trans.__('Collapse')}
        >
          <span className="jp-UserPresence-collapseIcon">⌃</span>
        </button>
      </div>
      
      {/* Current user */}
      {currentUser && (
        <div className="jp-UserPresence-self">
          {renderUserAvatar(currentUser.clientId, currentUser.state)}
          <span className="jp-UserPresence-name jp-UserPresence-selfName">
            {trans.__('You')}
          </span>
        </div>
      )}
      
      {/* Divider */}
      {currentUser && otherUsers.length > 0 && (
        <div className="jp-UserPresence-divider" />
      )}
      
      {/* Other users */}
      {otherUsers.length > 0 ? (
        <div className="jp-UserPresence-others">
          {/* Show limited number of avatars based on maxAvatars prop */}
          {otherUsers.slice(0, maxAvatars).map(({ clientId, state }) => (
            <div key={clientId} className="jp-UserPresence-user">
              {renderUserAvatar(clientId, state)}
              <span 
                className="jp-UserPresence-name"
                style={{ color: state.color }}
              >
                {state.name || trans.__('Unknown user')}
              </span>
            </div>
          ))}
          
          {/* Show count for additional users beyond maxAvatars */}
          {otherUsers.length > maxAvatars && (
            <div className="jp-UserPresence-moreUsers">
              <span className="jp-UserPresence-moreCount">
                {trans.__('+ %1 more', otherUsers.length - maxAvatars)}
              </span>
            </div>
          )}
        </div>
      ) : (
        <div className="jp-UserPresence-empty">
          {trans.__('No other collaborators')}
        </div>
      )}
      
      {/* Accessibility announcement for screen readers */}
      <div 
        className="jp-UserPresence-announcement" 
        aria-live="polite" 
        aria-atomic="true"
        style={{ position: 'absolute', width: '1px', height: '1px', overflow: 'hidden' }}
      >
        {trans.__('%1 collaborators currently active', otherUsers.length + (currentUser ? 1 : 0))}
      </div>
    </div>
  );
};

/**
 * A namespace for UserPresence widget.
 */
export namespace UserPresenceWidget {
  /**
   * Create a new UserPresenceWidget.
   *
   * @param awareness - The Yjs awareness instance
   * @param presenceService - Optional presence service for additional functionality
   * @param translator - The translator
   * @param maxAvatars - Optional maximum number of avatars to display
   * @param forceCollapsed - Optional flag to force collapsed view
   */
  export const create = ({
    awareness,
    presenceService,
    translator,
    maxAvatars,
    forceCollapsed
  }: {
    awareness: Awareness;
    presenceService?: IPresenceService;
    translator: ITranslator;
    maxAvatars?: number;
    forceCollapsed?: boolean;
  }): ReactWidget => {
    const widget = ReactWidget.create(
      <UserPresence 
        awareness={awareness} 
        presenceService={presenceService}
        translator={translator}
        maxAvatars={maxAvatars}
        forceCollapsed={forceCollapsed}
      />
    );
    
    widget.addClass('jp-UserPresenceWidget');
    
    return widget;
  };
}
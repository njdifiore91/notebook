import { Token } from '@lumino/coreutils';
import { ISignal } from '@lumino/signaling';
import { Widget } from '@lumino/widgets';

/**
 * The INotebookPathOpener interface.
 */
export interface INotebookPathOpener {
  /**
   * Open a path in the application.
   *
   * @param options - The options used to open the path.
   */
  open: (options: INotebookPathOpener.IOpenOptions) => WindowProxy | null;
}

export namespace INotebookPathOpener {
  /**
   * The options used to open a path in the application.
   */
  export interface IOpenOptions {
    /**
     * The URL prefix, which should include the base URL
     */
    prefix: string;

    /**
     * The path to open in the application, e.g `setup.py`, or `notebooks/example.ipynb`
     */
    path?: string;

    /**
     * The extra search params to use in the URL.
     */
    searchParams?: URLSearchParams;

    /**
     * Name of the browsing context the resource is being loaded into.
     * See https://developer.mozilla.org/en-US/docs/Web/API/Window/open for more details.
     */
    target?: string;

    /**
     *
     * See https://developer.mozilla.org/en-US/docs/Web/API/Window/open for more details.
     */
    features?: string;

    /**
     * ID of an existing collaboration session to join.
     * If provided, the notebook will be opened in collaborative mode and join the specified session.
     */
    collaborationSessionId?: string;

    /**
     * Whether to start a new collaboration session for this notebook.
     * If true, a new collaborative session will be created when the notebook is opened.
     */
    startCollaboration?: boolean;

    /**
     * The permission level to request when joining a collaboration session.
     * This determines what actions the user can perform in the collaborative session.
     */
    collaborationPermission?: CollaborationPermission;
  }
}

/**
 * The INotebookPathOpener token.
 * The main purpose of this token is to allow other extensions or downstream applications
 * to override the default behavior of opening a notebook in a new tab.
 * It also allows passing the path as a URL search parameter, or other options to the window.open call.
 */
export const INotebookPathOpener = new Token<INotebookPathOpener>(
  '@jupyter-notebook/application:INotebookPathOpener'
);

/**
 * User information for collaboration awareness.
 */
export interface IUserInfo {
  /**
   * Unique identifier for the user.
   */
  id: string;

  /**
   * Display name of the user.
   */
  name: string;

  /**
   * URL to the user's avatar image.
   */
  avatar?: string;

  /**
   * User's current status (active, idle, etc.).
   */
  status?: 'active' | 'idle' | 'viewing' | 'editing';

  /**
   * Additional user metadata.
   */
  metadata?: { [key: string]: any };
}

/**
 * Cursor position information for collaboration awareness.
 */
export interface ICursorPosition {
  /**
   * Cell ID where the cursor is located.
   */
  cellId: string;

  /**
   * Line number within the cell.
   */
  line: number;

  /**
   * Column number within the line.
   */
  column: number;
}

/**
 * Selection range information for collaboration awareness.
 */
export interface ISelectionRange {
  /**
   * Cell ID where the selection starts.
   */
  startCellId: string;

  /**
   * Starting line number within the cell.
   */
  startLine: number;

  /**
   * Starting column number within the line.
   */
  startColumn: number;

  /**
   * Cell ID where the selection ends.
   */
  endCellId: string;

  /**
   * Ending line number within the cell.
   */
  endLine: number;

  /**
   * Ending column number within the line.
   */
  endColumn: number;
}

/**
 * User presence information for collaboration awareness.
 */
export interface IUserPresence {
  /**
   * User information.
   */
  user: IUserInfo;

  /**
   * Current cursor position.
   */
  cursor?: ICursorPosition;

  /**
   * Current selection range.
   */
  selection?: ISelectionRange;

  /**
   * ID of the cell the user is currently active in.
   */
  activeCell?: string;

  /**
   * Timestamp of the last activity.
   */
  lastActivity: number;
}

/**
 * Permission level for collaborative editing.
 */
export enum CollaborationPermission {
  /**
   * View-only access.
   */
  VIEW = 'view',

  /**
   * Can add comments but not edit content.
   */
  COMMENT = 'comment',

  /**
   * Can edit content.
   */
  EDIT = 'edit',

  /**
   * Full administrative access.
   */
  ADMIN = 'admin'
}

/**
 * Interface for the Presence Service that tracks and displays user presence.
 */
export interface IPresenceService {
  /**
   * Signal emitted when the presence information changes.
   */
  readonly presenceChanged: ISignal<IPresenceService, Map<string, IUserPresence>>;

  /**
   * Get all current user presence information.
   */
  getPresence(): Map<string, IUserPresence>;

  /**
   * Get presence information for a specific user.
   * 
   * @param userId - The ID of the user.
   */
  getUserPresence(userId: string): IUserPresence | undefined;

  /**
   * Update the local user's cursor position.
   * 
   * @param position - The new cursor position.
   */
  updateCursor(position: ICursorPosition): void;

  /**
   * Update the local user's selection range.
   * 
   * @param selection - The new selection range.
   */
  updateSelection(selection: ISelectionRange): void;

  /**
   * Update the local user's active cell.
   * 
   * @param cellId - The ID of the active cell.
   */
  updateActiveCell(cellId: string): void;

  /**
   * Update the local user's status.
   * 
   * @param status - The new status.
   */
  updateStatus(status: IUserInfo['status']): void;
}

/**
 * Interface for the Lock Service that manages cell-level locking.
 */
export interface ILockService {
  /**
   * Signal emitted when the lock state changes.
   */
  readonly lockChanged: ISignal<ILockService, { cellId: string; userId: string | null }>;

  /**
   * Check if a cell is currently locked.
   * 
   * @param cellId - The ID of the cell to check.
   */
  isLocked(cellId: string): boolean;

  /**
   * Get the user ID of the user who has locked a cell.
   * 
   * @param cellId - The ID of the cell to check.
   */
  getLockOwner(cellId: string): string | null;

  /**
   * Attempt to acquire a lock on a cell.
   * 
   * @param cellId - The ID of the cell to lock.
   * @returns A promise that resolves to true if the lock was acquired, false otherwise.
   */
  acquireLock(cellId: string): Promise<boolean>;

  /**
   * Release a lock on a cell.
   * 
   * @param cellId - The ID of the cell to unlock.
   */
  releaseLock(cellId: string): void;
}

/**
 * Comment thread attached to a cell or selection.
 */
export interface ICommentThread {
  /**
   * Unique identifier for the comment thread.
   */
  id: string;

  /**
   * ID of the cell the comment is attached to.
   */
  cellId: string;

  /**
   * Optional selection range the comment is attached to.
   */
  selection?: ISelectionRange;

  /**
   * Array of comments in the thread.
   */
  comments: Array<{
    /**
     * Unique identifier for the comment.
     */
    id: string;

    /**
     * User who created the comment.
     */
    user: IUserInfo;

    /**
     * Comment content.
     */
    content: string;

    /**
     * Timestamp when the comment was created.
     */
    timestamp: number;

    /**
     * Whether the comment has been resolved.
     */
    resolved?: boolean;
  }>;

  /**
   * Whether the entire thread has been resolved.
   */
  resolved: boolean;
}

/**
 * Interface for the Comment Service that manages cell comments.
 */
export interface ICommentService {
  /**
   * Signal emitted when comments change.
   */
  readonly commentsChanged: ISignal<ICommentService, ICommentThread[]>;

  /**
   * Get all comment threads.
   */
  getCommentThreads(): ICommentThread[];

  /**
   * Get comment threads for a specific cell.
   * 
   * @param cellId - The ID of the cell.
   */
  getCommentsForCell(cellId: string): ICommentThread[];

  /**
   * Create a new comment thread.
   * 
   * @param cellId - The ID of the cell.
   * @param content - The comment content.
   * @param selection - Optional selection range.
   */
  createCommentThread(cellId: string, content: string, selection?: ISelectionRange): Promise<ICommentThread>;

  /**
   * Add a comment to an existing thread.
   * 
   * @param threadId - The ID of the thread.
   * @param content - The comment content.
   */
  addComment(threadId: string, content: string): Promise<void>;

  /**
   * Resolve or unresolve a comment thread.
   * 
   * @param threadId - The ID of the thread.
   * @param resolved - Whether the thread should be marked as resolved.
   */
  setThreadResolved(threadId: string, resolved: boolean): Promise<void>;

  /**
   * Delete a comment thread.
   * 
   * @param threadId - The ID of the thread to delete.
   */
  deleteThread(threadId: string): Promise<void>;
}

/**
 * Interface for the History Service that tracks document changes.
 */
export interface IHistoryService {
  /**
   * Get the version history of the document.
   */
  getHistory(): Promise<Array<{
    /**
     * Version identifier.
     */
    version: string;

    /**
     * User who made the changes.
     */
    user: IUserInfo;

    /**
     * Timestamp of the version.
     */
    timestamp: number;

    /**
     * Description of the changes.
     */
    description?: string;
  }>>;

  /**
   * Get the changes between two versions.
   * 
   * @param fromVersion - The starting version.
   * @param toVersion - The ending version.
   */
  getDiff(fromVersion: string, toVersion: string): Promise<any>;

  /**
   * Revert to a specific version.
   * 
   * @param version - The version to revert to.
   */
  revertTo(version: string): Promise<void>;
}

/**
 * Interface for the YjsNotebookProvider that integrates Yjs with the notebook model.
 */
export interface IYjsNotebookProvider {
  /**
   * Connect to the collaboration session.
   * 
   * @param documentId - The ID of the document to connect to.
   */
  connect(documentId: string): Promise<void>;

  /**
   * Disconnect from the collaboration session.
   */
  disconnect(): void;

  /**
   * Check if the provider is connected.
   */
  isConnected(): boolean;

  /**
   * Get the underlying Yjs document.
   */
  getYjsDocument(): any; // Using 'any' here as Yjs types would be imported elsewhere

  /**
   * Signal emitted when the connection status changes.
   */
  readonly connectionStatusChanged: ISignal<IYjsNotebookProvider, boolean>;
}

/**
 * Collaboration session information.
 */
export interface ICollaborationSession {
  /**
   * Unique identifier for the session.
   */
  id: string;

  /**
   * Path to the notebook document.
   */
  path: string;

  /**
   * List of connected users.
   */
  users: IUserInfo[];

  /**
   * Current user's permission level.
   */
  permission: CollaborationPermission;

  /**
   * Timestamp when the session was created.
   */
  createdAt: number;

  /**
   * Whether the session is currently active.
   */
  active: boolean;
}

/**
 * Interface for the Collaboration Service that manages collaborative sessions.
 */
export interface ICollaborationService {
  /**
   * Signal emitted when the session status changes.
   */
  readonly sessionStatusChanged: ISignal<ICollaborationService, ICollaborationSession | null>;

  /**
   * Get the current collaboration session.
   */
  getCurrentSession(): ICollaborationSession | null;

  /**
   * Start a new collaboration session.
   * 
   * @param path - The path to the notebook document.
   */
  startSession(path: string): Promise<ICollaborationSession>;

  /**
   * Join an existing collaboration session.
   * 
   * @param sessionId - The ID of the session to join.
   */
  joinSession(sessionId: string): Promise<ICollaborationSession>;

  /**
   * Leave the current collaboration session.
   */
  leaveSession(): Promise<void>;

  /**
   * Set the permission level for a user in the current session.
   * 
   * @param userId - The ID of the user.
   * @param permission - The permission level to set.
   */
  setUserPermission(userId: string, permission: CollaborationPermission): Promise<void>;

  /**
   * Get the presence service for the current session.
   */
  getPresenceService(): IPresenceService;

  /**
   * Get the lock service for the current session.
   */
  getLockService(): ILockService;

  /**
   * Get the comment service for the current session.
   */
  getCommentService(): ICommentService;

  /**
   * Get the history service for the current session.
   */
  getHistoryService(): IHistoryService;

  /**
   * Get the YjsNotebookProvider for the current session.
   */
  getYjsNotebookProvider(): IYjsNotebookProvider;
}

/**
 * The IPresenceService token.
 */
export const IPresenceService = new Token<IPresenceService>(
  '@jupyter-notebook/application:IPresenceService'
);

/**
 * The ILockService token.
 */
export const ILockService = new Token<ILockService>(
  '@jupyter-notebook/application:ILockService'
);

/**
 * The ICommentService token.
 */
export const ICommentService = new Token<ICommentService>(
  '@jupyter-notebook/application:ICommentService'
);

/**
 * The IHistoryService token.
 */
export const IHistoryService = new Token<IHistoryService>(
  '@jupyter-notebook/application:IHistoryService'
);

/**
 * The IYjsNotebookProvider token.
 */
export const IYjsNotebookProvider = new Token<IYjsNotebookProvider>(
  '@jupyter-notebook/application:IYjsNotebookProvider'
);

/**
 * The ICollaborationService token.
 * This is the main service for managing collaborative editing sessions.
 */
export const ICollaborationService = new Token<ICollaborationService>(
  '@jupyter-notebook/application:ICollaborationService'
);
// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { ISignal, Signal } from '@lumino/signaling';
import { Token } from '@lumino/coreutils';
import * as Y from 'yjs';
import { INotebookModel } from '../model';
import { IPermissionManager } from './permissions';

/**
 * The comment manager token.
 *
 * This token is used to provide a comment manager to the notebook.
 * The comment manager is responsible for managing comments and threads
 * for collaborative notebook editing.
 */
export const ICommentManager = new Token<ICommentManager>(
  '@jupyterlab/notebook:ICommentManager'
);

/**
 * The status of a comment.
 */
export enum CommentStatus {
  /**
   * The comment is active and unresolved.
   */
  Active = 'active',

  /**
   * The comment has been resolved.
   */
  Resolved = 'resolved',

  /**
   * The comment has been marked as a question that needs attention.
   */
  Question = 'question',

  /**
   * The comment has been archived.
   */
  Archived = 'archived'
}

/**
 * Interface for a comment in a notebook.
 */
export interface IComment {
  /**
   * The unique ID of the comment.
   */
  id: string;

  /**
   * The ID of the cell this comment is attached to.
   */
  cellId: string;

  /**
   * The ID of the user who created the comment.
   */
  authorId: string;

  /**
   * The display name of the user who created the comment.
   */
  authorName: string;

  /**
   * The content of the comment.
   */
  content: string;

  /**
   * The timestamp when the comment was created.
   */
  createdAt: number;

  /**
   * The timestamp when the comment was last updated.
   */
  updatedAt: number;

  /**
   * The status of the comment.
   */
  status: CommentStatus;

  /**
   * The ID of the thread this comment belongs to.
   * If this is the root comment, threadId will be the same as id.
   */
  threadId: string;

  /**
   * The ID of the parent comment if this is a reply.
   * If this is the root comment, parentId will be null.
   */
  parentId: string | null;

  /**
   * Optional metadata for the comment.
   */
  metadata?: { [key: string]: any };
}

/**
 * Interface for a comment thread in a notebook.
 */
export interface ICommentThread {
  /**
   * The unique ID of the thread (same as the root comment ID).
   */
  id: string;

  /**
   * The ID of the cell this thread is attached to.
   */
  cellId: string;

  /**
   * The root comment of the thread.
   */
  rootComment: IComment;

  /**
   * The replies in the thread.
   */
  replies: IComment[];

  /**
   * The status of the thread (same as the root comment status).
   */
  status: CommentStatus;

  /**
   * The timestamp when the thread was last updated.
   */
  updatedAt: number;
}

/**
 * Interface for comment creation options.
 */
export interface ICommentOptions {
  /**
   * The ID of the cell to attach the comment to.
   */
  cellId: string;

  /**
   * The content of the comment.
   */
  content: string;

  /**
   * The ID of the thread to add this comment to (for replies).
   * If not provided, a new thread will be created.
   */
  threadId?: string;

  /**
   * The ID of the parent comment (for nested replies).
   * If not provided but threadId is, the comment will be a direct reply to the root comment.
   */
  parentId?: string;

  /**
   * Optional metadata for the comment.
   */
  metadata?: { [key: string]: any };
}

/**
 * Interface for comment update options.
 */
export interface ICommentUpdateOptions {
  /**
   * The new content of the comment.
   */
  content?: string;

  /**
   * The new status of the comment.
   */
  status?: CommentStatus;

  /**
   * Optional metadata updates for the comment.
   */
  metadata?: { [key: string]: any };
}

/**
 * Interface for comment notification.
 */
export interface ICommentNotification {
  /**
   * The ID of the comment that triggered the notification.
   */
  commentId: string;

  /**
   * The ID of the thread the comment belongs to.
   */
  threadId: string;

  /**
   * The ID of the cell the comment is attached to.
   */
  cellId: string;

  /**
   * The ID of the user who should receive the notification.
   */
  recipientId: string;

  /**
   * The type of notification.
   */
  type: 'new' | 'reply' | 'mention' | 'resolution' | 'status_change';

  /**
   * Whether the notification has been read.
   */
  read: boolean;

  /**
   * The timestamp when the notification was created.
   */
  createdAt: number;
}

/**
 * Interface for a comment manager.
 */
export interface ICommentManager {
  /**
   * A signal emitted when comments change.
   */
  readonly commentsChanged: ISignal<ICommentManager, IComment[]>;

  /**
   * A signal emitted when a new notification is created.
   */
  readonly notificationAdded: ISignal<ICommentManager, ICommentNotification>;

  /**
   * A signal emitted when a notification is marked as read.
   */
  readonly notificationRead: ISignal<ICommentManager, string>;

  /**
   * Get all comments for a notebook.
   */
  getComments(): IComment[];

  /**
   * Get all comments for a specific cell.
   * 
   * @param cellId - The ID of the cell.
   */
  getCellComments(cellId: string): IComment[];

  /**
   * Get all threads for a notebook.
   */
  getThreads(): ICommentThread[];

  /**
   * Get all threads for a specific cell.
   * 
   * @param cellId - The ID of the cell.
   */
  getCellThreads(cellId: string): ICommentThread[];

  /**
   * Get a specific comment by ID.
   * 
   * @param commentId - The ID of the comment.
   */
  getComment(commentId: string): IComment | undefined;

  /**
   * Get a specific thread by ID.
   * 
   * @param threadId - The ID of the thread.
   */
  getThread(threadId: string): ICommentThread | undefined;

  /**
   * Add a new comment.
   * 
   * @param options - The comment options.
   * @returns The created comment, or undefined if creation failed.
   */
  addComment(options: ICommentOptions): IComment | undefined;

  /**
   * Update an existing comment.
   * 
   * @param commentId - The ID of the comment to update.
   * @param options - The update options.
   * @returns The updated comment, or undefined if update failed.
   */
  updateComment(commentId: string, options: ICommentUpdateOptions): IComment | undefined;

  /**
   * Delete a comment.
   * 
   * @param commentId - The ID of the comment to delete.
   * @returns Whether the deletion was successful.
   */
  deleteComment(commentId: string): boolean;

  /**
   * Resolve a thread.
   * 
   * @param threadId - The ID of the thread to resolve.
   * @returns Whether the resolution was successful.
   */
  resolveThread(threadId: string): boolean;

  /**
   * Reopen a resolved thread.
   * 
   * @param threadId - The ID of the thread to reopen.
   * @returns Whether the reopening was successful.
   */
  reopenThread(threadId: string): boolean;

  /**
   * Get all notifications for the current user.
   */
  getNotifications(): ICommentNotification[];

  /**
   * Get unread notifications for the current user.
   */
  getUnreadNotifications(): ICommentNotification[];

  /**
   * Mark a notification as read.
   * 
   * @param notificationId - The ID of the notification to mark as read.
   */
  markNotificationAsRead(notificationId: string): void;

  /**
   * Mark all notifications as read.
   */
  markAllNotificationsAsRead(): void;

  /**
   * Connect the comment manager to a notebook model.
   * 
   * @param model - The notebook model.
   * @param permissionManager - The permission manager.
   */
  connectNotebook(model: INotebookModel, permissionManager: IPermissionManager): void;

  /**
   * Disconnect the comment manager from a notebook model.
   */
  disconnectNotebook(): void;
}

/**
 * A concrete implementation of ICommentManager.
 */
export class CommentManager implements ICommentManager {
  /**
   * Construct a new CommentManager.
   * 
   * @param options - The options for the comment manager.
   */
  constructor(options: CommentManager.IOptions = {}) {
    this._currentUserId = options.currentUserId || this._getCurrentUserIdFromJupyterHub();
    this._currentUserDisplayName = options.currentUserDisplayName || this._currentUserId;
  }

  /**
   * A signal emitted when comments change.
   */
  get commentsChanged(): ISignal<this, IComment[]> {
    return this._commentsChanged;
  }

  /**
   * A signal emitted when a new notification is created.
   */
  get notificationAdded(): ISignal<this, ICommentNotification> {
    return this._notificationAdded;
  }

  /**
   * A signal emitted when a notification is marked as read.
   */
  get notificationRead(): ISignal<this, string> {
    return this._notificationRead;
  }

  /**
   * Get all comments for a notebook.
   */
  getComments(): IComment[] {
    if (!this._ydoc || !this._ycomments) {
      return [];
    }

    const comments: IComment[] = [];
    this._ycomments.forEach((comment) => {
      comments.push(comment as IComment);
    });

    return comments;
  }

  /**
   * Get all comments for a specific cell.
   * 
   * @param cellId - The ID of the cell.
   */
  getCellComments(cellId: string): IComment[] {
    return this.getComments().filter(comment => comment.cellId === cellId);
  }

  /**
   * Get all threads for a notebook.
   */
  getThreads(): ICommentThread[] {
    const comments = this.getComments();
    const threadMap = new Map<string, ICommentThread>();

    // First pass: create threads for root comments
    comments.forEach(comment => {
      if (comment.parentId === null) {
        threadMap.set(comment.id, {
          id: comment.id,
          cellId: comment.cellId,
          rootComment: comment,
          replies: [],
          status: comment.status,
          updatedAt: comment.updatedAt
        });
      }
    });

    // Second pass: add replies to threads
    comments.forEach(comment => {
      if (comment.parentId !== null) {
        const thread = threadMap.get(comment.threadId);
        if (thread) {
          thread.replies.push(comment);
          // Update thread updatedAt if reply is newer
          if (comment.updatedAt > thread.updatedAt) {
            thread.updatedAt = comment.updatedAt;
          }
        }
      }
    });

    // Sort replies by createdAt
    threadMap.forEach(thread => {
      thread.replies.sort((a, b) => a.createdAt - b.createdAt);
    });

    return Array.from(threadMap.values());
  }

  /**
   * Get all threads for a specific cell.
   * 
   * @param cellId - The ID of the cell.
   */
  getCellThreads(cellId: string): ICommentThread[] {
    return this.getThreads().filter(thread => thread.cellId === cellId);
  }

  /**
   * Get a specific comment by ID.
   * 
   * @param commentId - The ID of the comment.
   */
  getComment(commentId: string): IComment | undefined {
    if (!this._ydoc || !this._ycomments) {
      return undefined;
    }

    return this._ycomments.get(commentId) as IComment | undefined;
  }

  /**
   * Get a specific thread by ID.
   * 
   * @param threadId - The ID of the thread.
   */
  getThread(threadId: string): ICommentThread | undefined {
    return this.getThreads().find(thread => thread.id === threadId);
  }

  /**
   * Add a new comment.
   * 
   * @param options - The comment options.
   * @returns The created comment, or undefined if creation failed.
   */
  addComment(options: ICommentOptions): IComment | undefined {
    if (!this._ydoc || !this._ycomments || !this._permissionManager) {
      return undefined;
    }

    // Check if the user has permission to comment
    if (!this._permissionManager.canCommentOnCell(options.cellId, this._currentUserId)) {
      console.warn('User does not have permission to comment on this cell');
      return undefined;
    }

    const now = Date.now();
    const commentId = this._generateId();
    let threadId = options.threadId || commentId;
    let parentId = options.parentId || null;

    // If this is a reply, verify that the thread and parent exist
    if (options.threadId) {
      const thread = this.getThread(options.threadId);
      if (!thread) {
        console.warn(`Thread with ID ${options.threadId} not found`);
        return undefined;
      }

      // If parentId is provided, verify it exists
      if (options.parentId) {
        const parentComment = this.getComment(options.parentId);
        if (!parentComment) {
          console.warn(`Parent comment with ID ${options.parentId} not found`);
          return undefined;
        }
      } else {
        // If no parentId is provided, use the root comment as parent
        parentId = thread.rootComment.id;
      }
    }

    // Create the comment
    const comment: IComment = {
      id: commentId,
      cellId: options.cellId,
      authorId: this._currentUserId,
      authorName: this._currentUserDisplayName,
      content: options.content,
      createdAt: now,
      updatedAt: now,
      status: CommentStatus.Active,
      threadId,
      parentId,
      metadata: options.metadata || {}
    };

    // Add the comment to the shared map
    this._ycomments.set(commentId, comment);

    // Create notifications for relevant users
    this._createNotificationsForComment(comment);

    return comment;
  }

  /**
   * Update an existing comment.
   * 
   * @param commentId - The ID of the comment to update.
   * @param options - The update options.
   * @returns The updated comment, or undefined if update failed.
   */
  updateComment(commentId: string, options: ICommentUpdateOptions): IComment | undefined {
    if (!this._ydoc || !this._ycomments) {
      return undefined;
    }

    // Get the existing comment
    const comment = this.getComment(commentId);
    if (!comment) {
      console.warn(`Comment with ID ${commentId} not found`);
      return undefined;
    }

    // Check if the user has permission to update the comment
    if (comment.authorId !== this._currentUserId && !this._isAdmin()) {
      console.warn('Only the comment author or an admin can update a comment');
      return undefined;
    }

    // Create the updated comment
    const updatedComment: IComment = {
      ...comment,
      updatedAt: Date.now()
    };

    // Update content if provided
    if (options.content !== undefined) {
      updatedComment.content = options.content;
    }

    // Update status if provided
    if (options.status !== undefined) {
      updatedComment.status = options.status;

      // If this is a root comment, update thread status
      if (comment.parentId === null && options.status === CommentStatus.Resolved) {
        this._createStatusChangeNotifications(comment, options.status);
      }
    }

    // Update metadata if provided
    if (options.metadata !== undefined) {
      updatedComment.metadata = {
        ...comment.metadata,
        ...options.metadata
      };
    }

    // Update the comment in the shared map
    this._ycomments.set(commentId, updatedComment);

    return updatedComment;
  }

  /**
   * Delete a comment.
   * 
   * @param commentId - The ID of the comment to delete.
   * @returns Whether the deletion was successful.
   */
  deleteComment(commentId: string): boolean {
    if (!this._ydoc || !this._ycomments) {
      return false;
    }

    // Get the existing comment
    const comment = this.getComment(commentId);
    if (!comment) {
      console.warn(`Comment with ID ${commentId} not found`);
      return false;
    }

    // Check if the user has permission to delete the comment
    if (comment.authorId !== this._currentUserId && !this._isAdmin()) {
      console.warn('Only the comment author or an admin can delete a comment');
      return false;
    }

    // If this is a root comment, delete all replies
    if (comment.parentId === null) {
      const thread = this.getThread(comment.id);
      if (thread) {
        thread.replies.forEach(reply => {
          this._ycomments.delete(reply.id);
        });
      }
    }

    // Delete the comment from the shared map
    this._ycomments.delete(commentId);

    return true;
  }

  /**
   * Resolve a thread.
   * 
   * @param threadId - The ID of the thread to resolve.
   * @returns Whether the resolution was successful.
   */
  resolveThread(threadId: string): boolean {
    const thread = this.getThread(threadId);
    if (!thread) {
      console.warn(`Thread with ID ${threadId} not found`);
      return false;
    }

    // Update the root comment status to resolved
    const updated = this.updateComment(thread.rootComment.id, {
      status: CommentStatus.Resolved
    });

    return !!updated;
  }

  /**
   * Reopen a resolved thread.
   * 
   * @param threadId - The ID of the thread to reopen.
   * @returns Whether the reopening was successful.
   */
  reopenThread(threadId: string): boolean {
    const thread = this.getThread(threadId);
    if (!thread) {
      console.warn(`Thread with ID ${threadId} not found`);
      return false;
    }

    // Update the root comment status to active
    const updated = this.updateComment(thread.rootComment.id, {
      status: CommentStatus.Active
    });

    return !!updated;
  }

  /**
   * Get all notifications for the current user.
   */
  getNotifications(): ICommentNotification[] {
    if (!this._ydoc || !this._ynotifications) {
      return [];
    }

    const notifications: ICommentNotification[] = [];
    this._ynotifications.forEach((notification, id) => {
      if (notification.recipientId === this._currentUserId) {
        notifications.push(notification as ICommentNotification);
      }
    });

    // Sort by creation time, newest first
    return notifications.sort((a, b) => b.createdAt - a.createdAt);
  }

  /**
   * Get unread notifications for the current user.
   */
  getUnreadNotifications(): ICommentNotification[] {
    return this.getNotifications().filter(notification => !notification.read);
  }

  /**
   * Mark a notification as read.
   * 
   * @param notificationId - The ID of the notification to mark as read.
   */
  markNotificationAsRead(notificationId: string): void {
    if (!this._ydoc || !this._ynotifications) {
      return;
    }

    const notification = this._ynotifications.get(notificationId) as ICommentNotification | undefined;
    if (!notification) {
      console.warn(`Notification with ID ${notificationId} not found`);
      return;
    }

    // Check if this notification is for the current user
    if (notification.recipientId !== this._currentUserId) {
      console.warn('Cannot mark another user\'s notification as read');
      return;
    }

    // Update the notification
    const updatedNotification: ICommentNotification = {
      ...notification,
      read: true
    };

    // Update the notification in the shared map
    this._ynotifications.set(notificationId, updatedNotification);

    // Emit the notification read signal
    this._notificationRead.emit(notificationId);
  }

  /**
   * Mark all notifications as read.
   */
  markAllNotificationsAsRead(): void {
    if (!this._ydoc || !this._ynotifications) {
      return;
    }

    const unreadNotifications = this.getUnreadNotifications();
    unreadNotifications.forEach(notification => {
      this.markNotificationAsRead(notification.commentId);
    });
  }

  /**
   * Connect the comment manager to a notebook model.
   * 
   * @param model - The notebook model.
   * @param permissionManager - The permission manager.
   */
  connectNotebook(model: INotebookModel, permissionManager: IPermissionManager): void {
    if (this._model === model) {
      return;
    }

    // Disconnect from any existing model
    this.disconnectNotebook();

    // Connect to the new model
    this._model = model;
    this._permissionManager = permissionManager;

    // Get the Yjs document from the collaboration provider
    const provider = model.collaborationProvider;
    if (!provider) {
      console.warn('Notebook model does not have a collaboration provider');
      return;
    }

    this._ydoc = provider.ydoc;
    if (!this._ydoc) {
      console.warn('Collaboration provider does not have a Yjs document');
      return;
    }

    // Initialize shared data structures
    this._initSharedData();

    // Set up observation of shared data structures
    this._observeSharedData();
  }

  /**
   * Disconnect the comment manager from a notebook model.
   */
  disconnectNotebook(): void {
    if (!this._model) {
      return;
    }

    // Clean up observation of shared data structures
    this._unobserveSharedData();

    // Clear references
    this._model = null;
    this._permissionManager = null;
    this._ydoc = null;
    this._ycomments = null;
    this._ynotifications = null;
  }

  /**
   * Initialize the shared data structures.
   */
  private _initSharedData(): void {
    if (!this._ydoc) {
      return;
    }

    // Create or get shared data structures
    this._ycomments = this._ydoc.getMap('comments');
    this._ynotifications = this._ydoc.getMap('commentNotifications');
  }

  /**
   * Set up observation of shared data structures.
   */
  private _observeSharedData(): void {
    if (!this._ydoc || !this._ycomments || !this._ynotifications) {
      return;
    }

    // Observe comments
    this._ycomments.observe(this._onCommentsChanged.bind(this));

    // Observe notifications
    this._ynotifications.observe(this._onNotificationsChanged.bind(this));
  }

  /**
   * Clean up observation of shared data structures.
   */
  private _unobserveSharedData(): void {
    if (!this._ydoc) {
      return;
    }

    // Unobserve all shared data structures
    this._ycomments?.unobserve(this._onCommentsChanged.bind(this));
    this._ynotifications?.unobserve(this._onNotificationsChanged.bind(this));
  }

  /**
   * Handle changes to comments.
   */
  private _onCommentsChanged(event: Y.YMapEvent<any>): void {
    // Get all changed comments
    const changedComments: IComment[] = [];
    event.keysChanged.forEach(commentId => {
      const comment = this._ycomments?.get(commentId) as IComment | undefined;
      if (comment) {
        changedComments.push(comment);
      }
    });

    // Emit the comments changed signal
    if (changedComments.length > 0) {
      this._commentsChanged.emit(changedComments);
    }
  }

  /**
   * Handle changes to notifications.
   */
  private _onNotificationsChanged(event: Y.YMapEvent<any>): void {
    // Check for new notifications for the current user
    event.keysChanged.forEach(notificationId => {
      const notification = this._ynotifications?.get(notificationId) as ICommentNotification | undefined;
      if (notification && notification.recipientId === this._currentUserId && !notification.read) {
        // Emit the notification added signal
        this._notificationAdded.emit(notification);
      }
    });
  }

  /**
   * Create notifications for a new comment.
   */
  private _createNotificationsForComment(comment: IComment): void {
    if (!this._ydoc || !this._ynotifications) {
      return;
    }

    const now = Date.now();
    const notificationId = this._generateId();

    // If this is a reply, notify the thread participants
    if (comment.parentId !== null) {
      const thread = this.getThread(comment.threadId);
      if (thread) {
        // Get unique participant IDs (excluding the current user)
        const participantIds = new Set<string>();
        participantIds.add(thread.rootComment.authorId);
        thread.replies.forEach(reply => {
          participantIds.add(reply.authorId);
        });
        participantIds.delete(this._currentUserId); // Don't notify yourself

        // Create a notification for each participant
        participantIds.forEach(participantId => {
          const notification: ICommentNotification = {
            commentId: comment.id,
            threadId: comment.threadId,
            cellId: comment.cellId,
            recipientId: participantId,
            type: 'reply',
            read: false,
            createdAt: now
          };

          this._ynotifications.set(`${notificationId}-${participantId}`, notification);
        });
      }
    }

    // Check for @mentions in the comment content
    this._createMentionNotifications(comment);
  }

  /**
   * Create notifications for @mentions in a comment.
   */
  private _createMentionNotifications(comment: IComment): void {
    if (!this._ydoc || !this._ynotifications || !this._permissionManager) {
      return;
    }

    const now = Date.now();
    const notificationId = this._generateId();

    // Get all users with permission to view this notebook
    const users = this._permissionManager.getUserPermissions();

    // Check for @mentions in the comment content
    users.forEach(user => {
      // Skip the current user
      if (user.userId === this._currentUserId) {
        return;
      }

      // Check if the user is mentioned
      const mentionRegex = new RegExp(`@${user.displayName}\b`, 'i');
      if (mentionRegex.test(comment.content)) {
        const notification: ICommentNotification = {
          commentId: comment.id,
          threadId: comment.threadId,
          cellId: comment.cellId,
          recipientId: user.userId,
          type: 'mention',
          read: false,
          createdAt: now
        };

        this._ynotifications.set(`${notificationId}-${user.userId}`, notification);
      }
    });
  }

  /**
   * Create notifications for status changes.
   */
  private _createStatusChangeNotifications(comment: IComment, newStatus: CommentStatus): void {
    if (!this._ydoc || !this._ynotifications) {
      return;
    }

    const now = Date.now();
    const notificationId = this._generateId();

    // Get the thread
    const thread = this.getThread(comment.threadId);
    if (!thread) {
      return;
    }

    // Get unique participant IDs (excluding the current user)
    const participantIds = new Set<string>();
    participantIds.add(thread.rootComment.authorId);
    thread.replies.forEach(reply => {
      participantIds.add(reply.authorId);
    });
    participantIds.delete(this._currentUserId); // Don't notify yourself

    // Create a notification for each participant
    participantIds.forEach(participantId => {
      const notification: ICommentNotification = {
        commentId: comment.id,
        threadId: comment.threadId,
        cellId: comment.cellId,
        recipientId: participantId,
        type: newStatus === CommentStatus.Resolved ? 'resolution' : 'status_change',
        read: false,
        createdAt: now
      };

      this._ynotifications.set(`${notificationId}-${participantId}`, notification);
    });
  }

  /**
   * Generate a unique ID.
   */
  private _generateId(): string {
    return `comment-${Date.now()}-${Math.random().toString(36).substring(2, 10)}`;
  }

  /**
   * Check if the current user is an admin.
   */
  private _isAdmin(): boolean {
    return this._permissionManager?.isAdmin || false;
  }

  /**
   * Get the current user ID from JupyterHub if available.
   */
  private _getCurrentUserIdFromJupyterHub(): string {
    // Try to get the user ID from the page config
    try {
      // @ts-ignore
      const pageConfig = window.jupyter?.pageConfig;
      if (pageConfig && pageConfig.user) {
        return pageConfig.user;
      }
    } catch (error) {
      console.warn('Error getting user ID from JupyterHub:', error);
    }

    // Fall back to a generated ID if JupyterHub is not available
    return `user-${Math.random().toString(36).substring(2, 10)}`;
  }

  private _model: INotebookModel | null = null;
  private _permissionManager: IPermissionManager | null = null;
  private _ydoc: Y.Doc | null = null;
  private _ycomments: Y.Map<IComment> | null = null;
  private _ynotifications: Y.Map<ICommentNotification> | null = null;

  private _currentUserId: string;
  private _currentUserDisplayName: string;

  private _commentsChanged = new Signal<this, IComment[]>(this);
  private _notificationAdded = new Signal<this, ICommentNotification>(this);
  private _notificationRead = new Signal<this, string>(this);
}

/**
 * The namespace for CommentManager class statics.
 */
export namespace CommentManager {
  /**
   * The options for initializing a comment manager.
   */
  export interface IOptions {
    /**
     * The current user ID.
     */
    currentUserId?: string;

    /**
     * The current user's display name.
     */
    currentUserDisplayName?: string;
  }
}
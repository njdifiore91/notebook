// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { ISignal, Signal } from '@lumino/signaling';
import * as Y from 'yjs';

/**
 * Comment status enum
 */
export enum CommentStatus {
  /**
   * Comment is open and active
   */
  Open = 'open',

  /**
   * Comment has been resolved
   */
  Resolved = 'resolved',

  /**
   * Comment has been archived
   */
  Archived = 'archived'
}

/**
 * Interface for a comment author
 */
export interface ICommentAuthor {
  /**
   * Unique identifier for the author
   */
  id: string;

  /**
   * Display name of the author
   */
  name: string;

  /**
   * Optional URL to the author's avatar
   */
  avatarUrl?: string;
}

/**
 * Interface for a comment
 */
export interface IComment {
  /**
   * Unique identifier for the comment
   */
  id: string;

  /**
   * The content of the comment (supports markdown)
   */
  content: string;

  /**
   * The author of the comment
   */
  author: ICommentAuthor;

  /**
   * Timestamp when the comment was created
   */
  createdAt: number;

  /**
   * Timestamp when the comment was last updated
   */
  updatedAt: number;

  /**
   * Optional ID of the parent comment (for threaded replies)
   */
  parentId?: string;

  /**
   * Status of the comment
   */
  status: CommentStatus;

  /**
   * Optional ID of the user who resolved the comment
   */
  resolvedBy?: ICommentAuthor;

  /**
   * Timestamp when the comment was resolved
   */
  resolvedAt?: number;

  /**
   * Optional metadata for the comment
   */
  metadata?: { [key: string]: any };
}

/**
 * Interface for a comment thread
 */
export interface ICommentThread {
  /**
   * Unique identifier for the thread
   */
  id: string;

  /**
   * ID of the cell this thread is attached to
   */
  cellId: string;

  /**
   * Optional range within the cell (for comments on specific code sections)
   */
  range?: {
    start: number;
    end: number;
  };

  /**
   * Status of the thread
   */
  status: CommentStatus;

  /**
   * Timestamp when the thread was created
   */
  createdAt: number;

  /**
   * Timestamp when the thread was last updated
   */
  updatedAt: number;

  /**
   * Comments in this thread
   */
  comments: IComment[];

  /**
   * Optional metadata for the thread
   */
  metadata?: { [key: string]: any };
}

/**
 * Interface for comment notification
 */
export interface ICommentNotification {
  /**
   * Unique identifier for the notification
   */
  id: string;

  /**
   * Type of notification
   */
  type: 'new_comment' | 'reply' | 'mention' | 'resolution';

  /**
   * ID of the thread this notification is about
   */
  threadId: string;

  /**
   * ID of the comment this notification is about
   */
  commentId: string;

  /**
   * ID of the user who should receive this notification
   */
  recipientId: string;

  /**
   * Whether the notification has been read
   */
  read: boolean;

  /**
   * Timestamp when the notification was created
   */
  createdAt: number;
}

/**
 * Interface for comment manager options
 */
export interface ICommentManagerOptions {
  /**
   * The Yjs document to use for synchronization
   */
  ydoc: Y.Doc;

  /**
   * The current user's information
   */
  currentUser: ICommentAuthor;
}

/**
 * Interface for the comment manager
 */
export interface ICommentManager {
  /**
   * Signal emitted when a comment thread is added
   */
  readonly threadAdded: ISignal<ICommentManager, ICommentThread>;

  /**
   * Signal emitted when a comment thread is updated
   */
  readonly threadUpdated: ISignal<ICommentManager, ICommentThread>;

  /**
   * Signal emitted when a comment thread is deleted
   */
  readonly threadDeleted: ISignal<ICommentManager, string>;

  /**
   * Signal emitted when a comment is added
   */
  readonly commentAdded: ISignal<ICommentManager, IComment>;

  /**
   * Signal emitted when a comment is updated
   */
  readonly commentUpdated: ISignal<ICommentManager, IComment>;

  /**
   * Signal emitted when a comment is deleted
   */
  readonly commentDeleted: ISignal<ICommentManager, string>;

  /**
   * Signal emitted when a notification is added
   */
  readonly notificationAdded: ISignal<ICommentManager, ICommentNotification>;

  /**
   * Signal emitted when a notification is updated
   */
  readonly notificationUpdated: ISignal<ICommentManager, ICommentNotification>;

  /**
   * Signal emitted when a notification is deleted
   */
  readonly notificationDeleted: ISignal<ICommentManager, string>;

  /**
   * Get all comment threads
   */
  getThreads(): ICommentThread[];

  /**
   * Get a specific comment thread by ID
   */
  getThread(threadId: string): ICommentThread | undefined;

  /**
   * Get all comment threads for a specific cell
   */
  getThreadsForCell(cellId: string): ICommentThread[];

  /**
   * Create a new comment thread
   */
  createThread(cellId: string, range?: { start: number; end: number }): ICommentThread;

  /**
   * Update a comment thread
   */
  updateThread(threadId: string, updates: Partial<ICommentThread>): ICommentThread;

  /**
   * Delete a comment thread
   */
  deleteThread(threadId: string): void;

  /**
   * Add a comment to a thread
   */
  addComment(threadId: string, content: string, parentId?: string): IComment;

  /**
   * Update a comment
   */
  updateComment(commentId: string, content: string): IComment;

  /**
   * Delete a comment
   */
  deleteComment(commentId: string): void;

  /**
   * Resolve a comment thread
   */
  resolveThread(threadId: string): ICommentThread;

  /**
   * Reopen a resolved comment thread
   */
  reopenThread(threadId: string): ICommentThread;

  /**
   * Archive a comment thread
   */
  archiveThread(threadId: string): ICommentThread;

  /**
   * Get all notifications for the current user
   */
  getNotifications(): ICommentNotification[];

  /**
   * Mark a notification as read
   */
  markNotificationAsRead(notificationId: string): ICommentNotification;

  /**
   * Mark all notifications as read
   */
  markAllNotificationsAsRead(): void;

  /**
   * Delete a notification
   */
  deleteNotification(notificationId: string): void;

  /**
   * Dispose of the comment manager
   */
  dispose(): void;
}

/**
 * Implementation of the comment manager
 */
export class CommentManager implements ICommentManager {
  /**
   * Constructor
   */
  constructor(options: ICommentManagerOptions) {
    this._ydoc = options.ydoc;
    this._currentUser = options.currentUser;

    // Initialize Yjs shared data structures
    this._yThreads = this._ydoc.getMap<Y.Map<any>>('comments.threads');
    this._yComments = this._ydoc.getMap<Y.Map<any>>('comments.comments');
    this._yNotifications = this._ydoc.getMap<Y.Map<any>>('comments.notifications');

    // Set up observers for Yjs data changes
    this._yThreads.observe(this._onThreadsChanged.bind(this));
    this._yComments.observe(this._onCommentsChanged.bind(this));
    this._yNotifications.observe(this._onNotificationsChanged.bind(this));
  }

  /**
   * Signal emitted when a comment thread is added
   */
  get threadAdded(): ISignal<ICommentManager, ICommentThread> {
    return this._threadAdded;
  }

  /**
   * Signal emitted when a comment thread is updated
   */
  get threadUpdated(): ISignal<ICommentManager, ICommentThread> {
    return this._threadUpdated;
  }

  /**
   * Signal emitted when a comment thread is deleted
   */
  get threadDeleted(): ISignal<ICommentManager, string> {
    return this._threadDeleted;
  }

  /**
   * Signal emitted when a comment is added
   */
  get commentAdded(): ISignal<ICommentManager, IComment> {
    return this._commentAdded;
  }

  /**
   * Signal emitted when a comment is updated
   */
  get commentUpdated(): ISignal<ICommentManager, IComment> {
    return this._commentUpdated;
  }

  /**
   * Signal emitted when a comment is deleted
   */
  get commentDeleted(): ISignal<ICommentManager, string> {
    return this._commentDeleted;
  }

  /**
   * Signal emitted when a notification is added
   */
  get notificationAdded(): ISignal<ICommentManager, ICommentNotification> {
    return this._notificationAdded;
  }

  /**
   * Signal emitted when a notification is updated
   */
  get notificationUpdated(): ISignal<ICommentManager, ICommentNotification> {
    return this._notificationUpdated;
  }

  /**
   * Signal emitted when a notification is deleted
   */
  get notificationDeleted(): ISignal<ICommentManager, string> {
    return this._notificationDeleted;
  }

  /**
   * Get all comment threads
   */
  getThreads(): ICommentThread[] {
    const threads: ICommentThread[] = [];
    this._yThreads.forEach((yThread) => {
      threads.push(this._yThreadToThread(yThread));
    });
    return threads;
  }

  /**
   * Get a specific comment thread by ID
   */
  getThread(threadId: string): ICommentThread | undefined {
    const yThread = this._yThreads.get(threadId);
    if (!yThread) {
      return undefined;
    }
    return this._yThreadToThread(yThread);
  }

  /**
   * Get all comment threads for a specific cell
   */
  getThreadsForCell(cellId: string): ICommentThread[] {
    const threads: ICommentThread[] = [];
    this._yThreads.forEach((yThread) => {
      const thread = this._yThreadToThread(yThread);
      if (thread.cellId === cellId) {
        threads.push(thread);
      }
    });
    return threads;
  }

  /**
   * Create a new comment thread
   */
  createThread(cellId: string, range?: { start: number; end: number }): ICommentThread {
    const threadId = this._generateId();
    const now = Date.now();

    const thread: ICommentThread = {
      id: threadId,
      cellId,
      range,
      status: CommentStatus.Open,
      createdAt: now,
      updatedAt: now,
      comments: []
    };

    // Create Yjs map for the thread
    const yThread = new Y.Map<any>();
    yThread.set('id', thread.id);
    yThread.set('cellId', thread.cellId);
    if (thread.range) {
      yThread.set('range', thread.range);
    }
    yThread.set('status', thread.status);
    yThread.set('createdAt', thread.createdAt);
    yThread.set('updatedAt', thread.updatedAt);
    yThread.set('commentIds', new Y.Array<string>());

    // Add thread to Yjs map
    this._yThreads.set(threadId, yThread);

    return thread;
  }

  /**
   * Update a comment thread
   */
  updateThread(threadId: string, updates: Partial<ICommentThread>): ICommentThread {
    const yThread = this._yThreads.get(threadId);
    if (!yThread) {
      throw new Error(`Thread with ID ${threadId} not found`);
    }

    // Update the thread in Yjs
    this._ydoc.transact(() => {
      if (updates.status !== undefined) {
        yThread.set('status', updates.status);
      }

      if (updates.range !== undefined) {
        yThread.set('range', updates.range);
      }

      if (updates.metadata !== undefined) {
        yThread.set('metadata', updates.metadata);
      }

      // Always update the updatedAt timestamp
      yThread.set('updatedAt', Date.now());
    });

    return this._yThreadToThread(yThread);
  }

  /**
   * Delete a comment thread
   */
  deleteThread(threadId: string): void {
    const yThread = this._yThreads.get(threadId);
    if (!yThread) {
      throw new Error(`Thread with ID ${threadId} not found`);
    }

    // Get all comment IDs in this thread
    const commentIds = yThread.get('commentIds').toArray();

    // Delete all comments in the thread
    this._ydoc.transact(() => {
      commentIds.forEach((commentId: string) => {
        this._yComments.delete(commentId);
      });

      // Delete the thread
      this._yThreads.delete(threadId);
    });
  }

  /**
   * Add a comment to a thread
   */
  addComment(threadId: string, content: string, parentId?: string): IComment {
    const yThread = this._yThreads.get(threadId);
    if (!yThread) {
      throw new Error(`Thread with ID ${threadId} not found`);
    }

    const commentId = this._generateId();
    const now = Date.now();

    const comment: IComment = {
      id: commentId,
      content,
      author: this._currentUser,
      createdAt: now,
      updatedAt: now,
      parentId,
      status: CommentStatus.Open
    };

    // Create Yjs map for the comment
    const yComment = new Y.Map<any>();
    yComment.set('id', comment.id);
    yComment.set('content', comment.content);
    yComment.set('author', comment.author);
    yComment.set('createdAt', comment.createdAt);
    yComment.set('updatedAt', comment.updatedAt);
    yComment.set('status', comment.status);
    if (comment.parentId) {
      yComment.set('parentId', comment.parentId);
    }

    // Add comment to Yjs maps and update the thread
    this._ydoc.transact(() => {
      // Add comment to comments map
      this._yComments.set(commentId, yComment);

      // Add comment ID to thread's comment list
      const commentIds = yThread.get('commentIds') as Y.Array<string>;
      commentIds.push([commentId]);

      // Update thread's updatedAt timestamp
      yThread.set('updatedAt', now);
    });

    // Create notifications for this comment
    this._createCommentNotifications(comment, threadId);

    return comment;
  }

  /**
   * Update a comment
   */
  updateComment(commentId: string, content: string): IComment {
    const yComment = this._yComments.get(commentId);
    if (!yComment) {
      throw new Error(`Comment with ID ${commentId} not found`);
    }

    // Check if the current user is the author of the comment
    const author = yComment.get('author') as ICommentAuthor;
    if (author.id !== this._currentUser.id) {
      throw new Error('You can only edit your own comments');
    }

    const now = Date.now();

    // Update the comment in Yjs
    this._ydoc.transact(() => {
      yComment.set('content', content);
      yComment.set('updatedAt', now);
    });

    return this._yCommentToComment(yComment);
  }

  /**
   * Delete a comment
   */
  deleteComment(commentId: string): void {
    const yComment = this._yComments.get(commentId);
    if (!yComment) {
      throw new Error(`Comment with ID ${commentId} not found`);
    }

    // Check if the current user is the author of the comment
    const author = yComment.get('author') as ICommentAuthor;
    if (author.id !== this._currentUser.id) {
      throw new Error('You can only delete your own comments');
    }

    // Find the thread that contains this comment
    let threadId: string | undefined;
    let commentIndex: number = -1;

    this._yThreads.forEach((yThread, id) => {
      const commentIds = yThread.get('commentIds').toArray();
      const index = commentIds.indexOf(commentId);
      if (index !== -1) {
        threadId = id;
        commentIndex = index;
      }
    });

    if (!threadId || commentIndex === -1) {
      throw new Error(`Could not find thread containing comment ${commentId}`);
    }

    const yThread = this._yThreads.get(threadId)!;

    // Delete the comment and update the thread
    this._ydoc.transact(() => {
      // Remove comment ID from thread's comment list
      const commentIds = yThread.get('commentIds') as Y.Array<string>;
      commentIds.delete(commentIndex, 1);

      // Delete the comment
      this._yComments.delete(commentId);

      // Update thread's updatedAt timestamp
      yThread.set('updatedAt', Date.now());

      // If this was the last comment in the thread, delete the thread
      if (commentIds.length === 0) {
        this._yThreads.delete(threadId!);
      }
    });

    // Delete any notifications related to this comment
    this._deleteNotificationsForComment(commentId);
  }

  /**
   * Resolve a comment thread
   */
  resolveThread(threadId: string): ICommentThread {
    const yThread = this._yThreads.get(threadId);
    if (!yThread) {
      throw new Error(`Thread with ID ${threadId} not found`);
    }

    const now = Date.now();

    // Update the thread in Yjs
    this._ydoc.transact(() => {
      yThread.set('status', CommentStatus.Resolved);
      yThread.set('resolvedBy', this._currentUser);
      yThread.set('resolvedAt', now);
      yThread.set('updatedAt', now);
    });

    // Create resolution notifications
    this._createResolutionNotifications(threadId);

    return this._yThreadToThread(yThread);
  }

  /**
   * Reopen a resolved comment thread
   */
  reopenThread(threadId: string): ICommentThread {
    const yThread = this._yThreads.get(threadId);
    if (!yThread) {
      throw new Error(`Thread with ID ${threadId} not found`);
    }

    // Update the thread in Yjs
    this._ydoc.transact(() => {
      yThread.set('status', CommentStatus.Open);
      yThread.delete('resolvedBy');
      yThread.delete('resolvedAt');
      yThread.set('updatedAt', Date.now());
    });

    return this._yThreadToThread(yThread);
  }

  /**
   * Archive a comment thread
   */
  archiveThread(threadId: string): ICommentThread {
    const yThread = this._yThreads.get(threadId);
    if (!yThread) {
      throw new Error(`Thread with ID ${threadId} not found`);
    }

    // Update the thread in Yjs
    this._ydoc.transact(() => {
      yThread.set('status', CommentStatus.Archived);
      yThread.set('updatedAt', Date.now());
    });

    return this._yThreadToThread(yThread);
  }

  /**
   * Get all notifications for the current user
   */
  getNotifications(): ICommentNotification[] {
    const notifications: ICommentNotification[] = [];
    this._yNotifications.forEach((yNotification) => {
      const notification = this._yNotificationToNotification(yNotification);
      if (notification.recipientId === this._currentUser.id) {
        notifications.push(notification);
      }
    });
    return notifications;
  }

  /**
   * Mark a notification as read
   */
  markNotificationAsRead(notificationId: string): ICommentNotification {
    const yNotification = this._yNotifications.get(notificationId);
    if (!yNotification) {
      throw new Error(`Notification with ID ${notificationId} not found`);
    }

    // Check if this notification is for the current user
    const recipientId = yNotification.get('recipientId');
    if (recipientId !== this._currentUser.id) {
      throw new Error('You can only mark your own notifications as read');
    }

    // Update the notification in Yjs
    this._ydoc.transact(() => {
      yNotification.set('read', true);
    });

    return this._yNotificationToNotification(yNotification);
  }

  /**
   * Mark all notifications as read
   */
  markAllNotificationsAsRead(): void {
    // Update all notifications for the current user
    this._ydoc.transact(() => {
      this._yNotifications.forEach((yNotification) => {
        const recipientId = yNotification.get('recipientId');
        if (recipientId === this._currentUser.id) {
          yNotification.set('read', true);
        }
      });
    });
  }

  /**
   * Delete a notification
   */
  deleteNotification(notificationId: string): void {
    const yNotification = this._yNotifications.get(notificationId);
    if (!yNotification) {
      throw new Error(`Notification with ID ${notificationId} not found`);
    }

    // Check if this notification is for the current user
    const recipientId = yNotification.get('recipientId');
    if (recipientId !== this._currentUser.id) {
      throw new Error('You can only delete your own notifications');
    }

    // Delete the notification in Yjs
    this._ydoc.transact(() => {
      this._yNotifications.delete(notificationId);
    });
  }

  /**
   * Dispose of the comment manager
   */
  dispose(): void {
    // Disconnect observers
    this._yThreads.unobserve(this._onThreadsChanged.bind(this));
    this._yComments.unobserve(this._onCommentsChanged.bind(this));
    this._yNotifications.unobserve(this._onNotificationsChanged.bind(this));

    // Clear signals
    Signal.clearData(this);
  }

  /**
   * Handle changes to the threads map
   */
  private _onThreadsChanged(event: Y.YMapEvent<Y.Map<any>>): void {
    event.keysChanged.forEach((key) => {
      if (event.changes.keys.get(key)?.action === 'add') {
        // Thread added
        const yThread = this._yThreads.get(key)!;
        const thread = this._yThreadToThread(yThread);
        this._threadAdded.emit(thread);
      } else if (event.changes.keys.get(key)?.action === 'update') {
        // Thread updated
        const yThread = this._yThreads.get(key)!;
        const thread = this._yThreadToThread(yThread);
        this._threadUpdated.emit(thread);
      } else if (event.changes.keys.get(key)?.action === 'delete') {
        // Thread deleted
        this._threadDeleted.emit(key);
      }
    });
  }

  /**
   * Handle changes to the comments map
   */
  private _onCommentsChanged(event: Y.YMapEvent<Y.Map<any>>): void {
    event.keysChanged.forEach((key) => {
      if (event.changes.keys.get(key)?.action === 'add') {
        // Comment added
        const yComment = this._yComments.get(key)!;
        const comment = this._yCommentToComment(yComment);
        this._commentAdded.emit(comment);
      } else if (event.changes.keys.get(key)?.action === 'update') {
        // Comment updated
        const yComment = this._yComments.get(key)!;
        const comment = this._yCommentToComment(yComment);
        this._commentUpdated.emit(comment);
      } else if (event.changes.keys.get(key)?.action === 'delete') {
        // Comment deleted
        this._commentDeleted.emit(key);
      }
    });
  }

  /**
   * Handle changes to the notifications map
   */
  private _onNotificationsChanged(event: Y.YMapEvent<Y.Map<any>>): void {
    event.keysChanged.forEach((key) => {
      if (event.changes.keys.get(key)?.action === 'add') {
        // Notification added
        const yNotification = this._yNotifications.get(key)!;
        const notification = this._yNotificationToNotification(yNotification);
        this._notificationAdded.emit(notification);
      } else if (event.changes.keys.get(key)?.action === 'update') {
        // Notification updated
        const yNotification = this._yNotifications.get(key)!;
        const notification = this._yNotificationToNotification(yNotification);
        this._notificationUpdated.emit(notification);
      } else if (event.changes.keys.get(key)?.action === 'delete') {
        // Notification deleted
        this._notificationDeleted.emit(key);
      }
    });
  }

  /**
   * Convert a Yjs thread map to an ICommentThread
   */
  private _yThreadToThread(yThread: Y.Map<any>): ICommentThread {
    const commentIds = yThread.get('commentIds').toArray();
    const comments: IComment[] = [];

    // Get all comments in this thread
    commentIds.forEach((commentId: string) => {
      const yComment = this._yComments.get(commentId);
      if (yComment) {
        comments.push(this._yCommentToComment(yComment));
      }
    });

    // Build thread object
    const thread: ICommentThread = {
      id: yThread.get('id'),
      cellId: yThread.get('cellId'),
      status: yThread.get('status'),
      createdAt: yThread.get('createdAt'),
      updatedAt: yThread.get('updatedAt'),
      comments
    };

    // Add optional properties if they exist
    if (yThread.has('range')) {
      thread.range = yThread.get('range');
    }

    if (yThread.has('metadata')) {
      thread.metadata = yThread.get('metadata');
    }

    return thread;
  }

  /**
   * Convert a Yjs comment map to an IComment
   */
  private _yCommentToComment(yComment: Y.Map<any>): IComment {
    // Build comment object
    const comment: IComment = {
      id: yComment.get('id'),
      content: yComment.get('content'),
      author: yComment.get('author'),
      createdAt: yComment.get('createdAt'),
      updatedAt: yComment.get('updatedAt'),
      status: yComment.get('status')
    };

    // Add optional properties if they exist
    if (yComment.has('parentId')) {
      comment.parentId = yComment.get('parentId');
    }

    if (yComment.has('resolvedBy')) {
      comment.resolvedBy = yComment.get('resolvedBy');
    }

    if (yComment.has('resolvedAt')) {
      comment.resolvedAt = yComment.get('resolvedAt');
    }

    if (yComment.has('metadata')) {
      comment.metadata = yComment.get('metadata');
    }

    return comment;
  }

  /**
   * Convert a Yjs notification map to an ICommentNotification
   */
  private _yNotificationToNotification(yNotification: Y.Map<any>): ICommentNotification {
    return {
      id: yNotification.get('id'),
      type: yNotification.get('type'),
      threadId: yNotification.get('threadId'),
      commentId: yNotification.get('commentId'),
      recipientId: yNotification.get('recipientId'),
      read: yNotification.get('read'),
      createdAt: yNotification.get('createdAt')
    };
  }

  /**
   * Create notifications for a new comment
   */
  private _createCommentNotifications(comment: IComment, threadId: string): void {
    const thread = this.getThread(threadId);
    if (!thread) {
      return;
    }

    // Get all unique authors in this thread (excluding the current user)
    const authorIds = new Set<string>();
    thread.comments.forEach((c) => {
      if (c.author.id !== this._currentUser.id) {
        authorIds.add(c.author.id);
      }
    });

    // Create notifications for each author
    this._ydoc.transact(() => {
      authorIds.forEach((authorId) => {
        const notificationType = comment.parentId ? 'reply' : 'new_comment';
        this._createNotification({
          type: notificationType,
          threadId,
          commentId: comment.id,
          recipientId: authorId
        });
      });

      // Check for @mentions in the comment content and create notifications
      this._createMentionNotifications(comment, threadId);
    });
  }

  /**
   * Create notifications for @mentions in a comment
   */
  private _createMentionNotifications(comment: IComment, threadId: string): void {
    // Simple regex to find @username mentions
    // In a real implementation, this would be more sophisticated
    const mentionRegex = /@([\w-]+)/g;
    const mentions = comment.content.match(mentionRegex);

    if (!mentions) {
      return;
    }

    // For each mention, create a notification
    // This is a simplified implementation - in a real system, you would
    // need to resolve usernames to user IDs
    mentions.forEach((mention) => {
      const username = mention.substring(1); // Remove the @ symbol
      // In a real implementation, you would look up the user ID from the username
      // For now, we'll just use the username as the ID
      const userId = username;

      // Don't notify the current user
      if (userId === this._currentUser.id) {
        return;
      }

      this._createNotification({
        type: 'mention',
        threadId,
        commentId: comment.id,
        recipientId: userId
      });
    });
  }

  /**
   * Create notifications for thread resolution
   */
  private _createResolutionNotifications(threadId: string): void {
    const thread = this.getThread(threadId);
    if (!thread) {
      return;
    }

    // Get all unique authors in this thread (excluding the current user)
    const authorIds = new Set<string>();
    thread.comments.forEach((c) => {
      if (c.author.id !== this._currentUser.id) {
        authorIds.add(c.author.id);
      }
    });

    // Create notifications for each author
    this._ydoc.transact(() => {
      authorIds.forEach((authorId) => {
        this._createNotification({
          type: 'resolution',
          threadId,
          commentId: thread.comments[0].id, // Use the first comment ID
          recipientId: authorId
        });
      });
    });
  }

  /**
   * Create a notification
   */
  private _createNotification(options: {
    type: 'new_comment' | 'reply' | 'mention' | 'resolution';
    threadId: string;
    commentId: string;
    recipientId: string;
  }): ICommentNotification {
    const notificationId = this._generateId();
    const now = Date.now();

    const notification: ICommentNotification = {
      id: notificationId,
      type: options.type,
      threadId: options.threadId,
      commentId: options.commentId,
      recipientId: options.recipientId,
      read: false,
      createdAt: now
    };

    // Create Yjs map for the notification
    const yNotification = new Y.Map<any>();
    yNotification.set('id', notification.id);
    yNotification.set('type', notification.type);
    yNotification.set('threadId', notification.threadId);
    yNotification.set('commentId', notification.commentId);
    yNotification.set('recipientId', notification.recipientId);
    yNotification.set('read', notification.read);
    yNotification.set('createdAt', notification.createdAt);

    // Add notification to Yjs map
    this._yNotifications.set(notificationId, yNotification);

    return notification;
  }

  /**
   * Delete all notifications related to a comment
   */
  private _deleteNotificationsForComment(commentId: string): void {
    // Find all notifications related to this comment
    const notificationsToDelete: string[] = [];

    this._yNotifications.forEach((yNotification, id) => {
      if (yNotification.get('commentId') === commentId) {
        notificationsToDelete.push(id);
      }
    });

    // Delete all found notifications
    this._ydoc.transact(() => {
      notificationsToDelete.forEach((id) => {
        this._yNotifications.delete(id);
      });
    });
  }

  /**
   * Generate a unique ID
   */
  private _generateId(): string {
    return `${Date.now().toString(36)}-${Math.random().toString(36).substr(2, 9)}`;
  }

  private _ydoc: Y.Doc;
  private _currentUser: ICommentAuthor;
  private _yThreads: Y.Map<Y.Map<any>>;
  private _yComments: Y.Map<Y.Map<any>>;
  private _yNotifications: Y.Map<Y.Map<any>>;

  private _threadAdded = new Signal<ICommentManager, ICommentThread>(this);
  private _threadUpdated = new Signal<ICommentManager, ICommentThread>(this);
  private _threadDeleted = new Signal<ICommentManager, string>(this);
  private _commentAdded = new Signal<ICommentManager, IComment>(this);
  private _commentUpdated = new Signal<ICommentManager, IComment>(this);
  private _commentDeleted = new Signal<ICommentManager, string>(this);
  private _notificationAdded = new Signal<ICommentManager, ICommentNotification>(this);
  private _notificationUpdated = new Signal<ICommentManager, ICommentNotification>(this);
  private _notificationDeleted = new Signal<ICommentManager, string>(this);
}
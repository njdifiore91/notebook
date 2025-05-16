// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ICommentManager, IComment, ICommentThread, CommentStatus, ICommentNotification } from '@jupyterlab/notebook/lib/collab/comments';
import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
import { ITranslator, nullTranslator, TranslationBundle } from '@jupyterlab/translation';
import { MarkdownRenderer } from '@jupyterlab/rendermime';
import { IRenderMimeRegistry } from '@jupyterlab/rendermime';
import { ISignal, Signal } from '@lumino/signaling';
import { Widget } from '@lumino/widgets';
import { LabIcon } from '@jupyterlab/ui-components';
import { Time } from '@jupyterlab/coreutils';
import { Cell } from '@jupyterlab/cells';

/**
 * The CSS class for the comment system.
 */
const COMMENT_SYSTEM_CLASS = 'jp-CommentSystem';

/**
 * The CSS class for the comment thread.
 */
const COMMENT_THREAD_CLASS = 'jp-CommentThread';

/**
 * The CSS class for a comment.
 */
const COMMENT_CLASS = 'jp-Comment';

/**
 * The CSS class for a resolved comment thread.
 */
const COMMENT_THREAD_RESOLVED_CLASS = 'jp-CommentThread-resolved';

/**
 * The CSS class for a question comment thread.
 */
const COMMENT_THREAD_QUESTION_CLASS = 'jp-CommentThread-question';

/**
 * The CSS class for the comment form.
 */
const COMMENT_FORM_CLASS = 'jp-CommentForm';

/**
 * The CSS class for the comment system sidebar.
 */
const COMMENT_SIDEBAR_CLASS = 'jp-CommentSidebar';

/**
 * The CSS class for the comment system inline view.
 */
const COMMENT_INLINE_CLASS = 'jp-CommentInline';

/**
 * The CSS class for the comment notification badge.
 */
const COMMENT_NOTIFICATION_BADGE_CLASS = 'jp-CommentNotificationBadge';

/**
 * Interface for the comment system props.
 */
export interface ICommentSystemProps {
  /**
   * The comment manager instance.
   */
  commentManager: ICommentManager;

  /**
   * The notebook tracker.
   */
  notebookTracker: INotebookTracker;

  /**
   * The translator.
   */
  translator?: ITranslator;

  /**
   * The rendermime registry for rendering markdown content.
   */
  rendermime: IRenderMimeRegistry;

  /**
   * The view mode for the comment system.
   * 'inline' shows comments next to cells, 'sidebar' shows them in a sidebar.
   */
  viewMode?: 'inline' | 'sidebar';
}

/**
 * Interface for the comment thread props.
 */
interface ICommentThreadProps {
  /**
   * The comment thread.
   */
  thread: ICommentThread;

  /**
   * The comment manager instance.
   */
  commentManager: ICommentManager;

  /**
   * The translator.
   */
  translator: TranslationBundle;

  /**
   * The rendermime registry for rendering markdown content.
   */
  rendermime: IRenderMimeRegistry;

  /**
   * Whether the thread is expanded to show replies.
   */
  expanded?: boolean;

  /**
   * Whether the reply form is visible.
   */
  showReplyForm?: boolean;

  /**
   * Callback when the thread is resolved or reopened.
   */
  onStatusChange?: (threadId: string, status: CommentStatus) => void;
}

/**
 * Interface for the comment props.
 */
interface ICommentProps {
  /**
   * The comment.
   */
  comment: IComment;

  /**
   * The comment manager instance.
   */
  commentManager: ICommentManager;

  /**
   * The translator.
   */
  translator: TranslationBundle;

  /**
   * The rendermime registry for rendering markdown content.
   */
  rendermime: IRenderMimeRegistry;

  /**
   * Whether the comment is being edited.
   */
  isEditing?: boolean;

  /**
   * Callback when the comment is edited.
   */
  onEdit?: (commentId: string) => void;

  /**
   * Callback when the comment is deleted.
   */
  onDelete?: (commentId: string) => void;
}

/**
 * Interface for the comment form props.
 */
interface ICommentFormProps {
  /**
   * The comment manager instance.
   */
  commentManager: ICommentManager;

  /**
   * The cell ID to attach the comment to.
   */
  cellId: string;

  /**
   * The thread ID if this is a reply.
   */
  threadId?: string;

  /**
   * The parent comment ID if this is a nested reply.
   */
  parentId?: string;

  /**
   * The translator.
   */
  translator: TranslationBundle;

  /**
   * Callback when the form is submitted.
   */
  onSubmit?: (comment: IComment) => void;

  /**
   * Callback when the form is canceled.
   */
  onCancel?: () => void;

  /**
   * Initial content for the comment.
   */
  initialContent?: string;

  /**
   * Whether this is an edit form for an existing comment.
   */
  isEdit?: boolean;

  /**
   * The ID of the comment being edited.
   */
  editCommentId?: string;
}

/**
 * Interface for the comment filter props.
 */
interface ICommentFilterProps {
  /**
   * The current filter settings.
   */
  filters: ICommentFilters;

  /**
   * Callback when filters change.
   */
  onFilterChange: (filters: ICommentFilters) => void;

  /**
   * The translator.
   */
  translator: TranslationBundle;
}

/**
 * Interface for comment filters.
 */
interface ICommentFilters {
  /**
   * Filter by comment status.
   */
  status?: CommentStatus[];

  /**
   * Filter by author ID.
   */
  authorId?: string;

  /**
   * Filter by cell ID.
   */
  cellId?: string;

  /**
   * Search text to filter comments by content.
   */
  searchText?: string;
}

/**
 * Interface for the notification panel props.
 */
interface INotificationPanelProps {
  /**
   * The comment manager instance.
   */
  commentManager: ICommentManager;

  /**
   * The translator.
   */
  translator: TranslationBundle;

  /**
   * Callback when a notification is clicked.
   */
  onNotificationClick?: (notification: ICommentNotification) => void;
}

/**
 * A React component for rendering a single comment.
 */
function Comment(props: ICommentProps): JSX.Element {
  const { comment, commentManager, translator, rendermime, isEditing, onEdit, onDelete } = props;
  const [isEditable, setIsEditable] = useState(false);
  const [showActions, setShowActions] = useState(false);
  const commentRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // Render markdown content when the comment changes
  useEffect(() => {
    if (contentRef.current && !isEditing) {
      // Clear previous content
      contentRef.current.innerHTML = '';
      
      // Create a new markdown widget
      const widget = new MarkdownRenderer({
        mimeType: 'text/markdown',
        resolver: rendermime.resolver,
        sanitizer: rendermime.sanitizer,
        linkHandler: rendermime.linkHandler,
        latexTypesetter: rendermime.latexTypesetter
      });
      
      // Render the comment content
      widget.renderModel({
        data: { 'text/markdown': comment.content },
        metadata: {}
      }).then(() => {
        if (contentRef.current) {
          // Append the rendered content
          Widget.attach(widget, contentRef.current);
        }
      }).catch(error => {
        console.error('Error rendering markdown:', error);
        if (contentRef.current) {
          contentRef.current.textContent = comment.content;
        }
      });
    }
  }, [comment.content, isEditing, rendermime]);

  // Check if the current user can edit this comment
  useEffect(() => {
    // Get the current user ID from the comment manager
    const currentUserId = (commentManager as any)._currentUserId;
    setIsEditable(comment.authorId === currentUserId);
  }, [comment.authorId, commentManager]);

  const handleEdit = useCallback(() => {
    if (onEdit) {
      onEdit(comment.id);
    }
  }, [comment.id, onEdit]);

  const handleDelete = useCallback(() => {
    if (window.confirm(translator.__("Are you sure you want to delete this comment?"))) {
      commentManager.deleteComment(comment.id);
      if (onDelete) {
        onDelete(comment.id);
      }
    }
  }, [comment.id, commentManager, onDelete, translator]);

  return (
    <div 
      className={COMMENT_CLASS} 
      ref={commentRef}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      <div className={`${COMMENT_CLASS}-header`}>
        <div className={`${COMMENT_CLASS}-author`}>
          <span className={`${COMMENT_CLASS}-author-name`}>{comment.authorName}</span>
        </div>
        <div className={`${COMMENT_CLASS}-time`}>
          {Time.formatHuman(new Date(comment.createdAt))}
          {comment.updatedAt > comment.createdAt && 
            <span className={`${COMMENT_CLASS}-edited`}> ({translator.__('edited')})</span>
          }
        </div>
        {isEditable && showActions && (
          <div className={`${COMMENT_CLASS}-actions`}>
            <button 
              className={`${COMMENT_CLASS}-edit-button`}
              onClick={handleEdit}
              aria-label={translator.__('Edit comment')}
            >
              {translator.__('Edit')}
            </button>
            <button 
              className={`${COMMENT_CLASS}-delete-button`}
              onClick={handleDelete}
              aria-label={translator.__('Delete comment')}
            >
              {translator.__('Delete')}
            </button>
          </div>
        )}
      </div>
      {isEditing ? (
        <CommentForm
          commentManager={commentManager}
          cellId={comment.cellId}
          threadId={comment.threadId}
          parentId={comment.parentId || undefined}
          translator={translator}
          initialContent={comment.content}
          isEdit={true}
          editCommentId={comment.id}
          onCancel={() => onEdit && onEdit('')}
        />
      ) : (
        <div 
          className={`${COMMENT_CLASS}-content`}
          ref={contentRef}
        >
          {/* Markdown content will be rendered here */}
        </div>
      )}
    </div>
  );
}

/**
 * A React component for rendering a comment thread.
 */
function CommentThread(props: ICommentThreadProps): JSX.Element {
  const { thread, commentManager, translator, rendermime, onStatusChange } = props;
  const [expanded, setExpanded] = useState(props.expanded ?? true);
  const [showReplyForm, setShowReplyForm] = useState(props.showReplyForm ?? false);
  const [editingCommentId, setEditingCommentId] = useState('');

  const toggleExpanded = useCallback(() => {
    setExpanded(!expanded);
  }, [expanded]);

  const toggleReplyForm = useCallback(() => {
    setShowReplyForm(!showReplyForm);
  }, [showReplyForm]);

  const handleReplySubmit = useCallback(() => {
    setShowReplyForm(false);
  }, []);

  const handleResolve = useCallback(() => {
    if (thread.status === CommentStatus.Resolved) {
      commentManager.reopenThread(thread.id);
      if (onStatusChange) {
        onStatusChange(thread.id, CommentStatus.Active);
      }
    } else {
      commentManager.resolveThread(thread.id);
      if (onStatusChange) {
        onStatusChange(thread.id, CommentStatus.Resolved);
      }
    }
  }, [thread.id, thread.status, commentManager, onStatusChange]);

  const handleStatusChange = useCallback((status: CommentStatus) => {
    commentManager.updateComment(thread.rootComment.id, { status });
    if (onStatusChange) {
      onStatusChange(thread.id, status);
    }
  }, [thread.id, thread.rootComment.id, commentManager, onStatusChange]);

  // Determine the thread class based on status
  let threadClass = COMMENT_THREAD_CLASS;
  if (thread.status === CommentStatus.Resolved) {
    threadClass += ` ${COMMENT_THREAD_RESOLVED_CLASS}`;
  } else if (thread.status === CommentStatus.Question) {
    threadClass += ` ${COMMENT_THREAD_QUESTION_CLASS}`;
  }

  return (
    <div className={threadClass}>
      <div className={`${COMMENT_THREAD_CLASS}-header`}>
        <div className={`${COMMENT_THREAD_CLASS}-status`}>
          {thread.status === CommentStatus.Resolved ? (
            <span className={`${COMMENT_THREAD_CLASS}-resolved-icon`} title={translator.__('Resolved')}>
              ✓
            </span>
          ) : thread.status === CommentStatus.Question ? (
            <span className={`${COMMENT_THREAD_CLASS}-question-icon`} title={translator.__('Question')}>
              ?
            </span>
          ) : null}
        </div>
        <div className={`${COMMENT_THREAD_CLASS}-cell-info`}>
          {translator.__('Cell')} #{thread.cellId.slice(0, 8)}
        </div>
        <div className={`${COMMENT_THREAD_CLASS}-actions`}>
          <button 
            className={`${COMMENT_THREAD_CLASS}-resolve-button`}
            onClick={handleResolve}
            aria-label={thread.status === CommentStatus.Resolved ? 
              translator.__('Reopen thread') : 
              translator.__('Resolve thread')}
          >
            {thread.status === CommentStatus.Resolved ? 
              translator.__('Reopen') : 
              translator.__('Resolve')}
          </button>
          <div className={`${COMMENT_THREAD_CLASS}-status-dropdown`}>
            <select 
              value={thread.status}
              onChange={(e) => handleStatusChange(e.target.value as CommentStatus)}
              aria-label={translator.__('Change thread status')}
            >
              <option value={CommentStatus.Active}>{translator.__('Active')}</option>
              <option value={CommentStatus.Question}>{translator.__('Question')}</option>
              <option value={CommentStatus.Resolved}>{translator.__('Resolved')}</option>
              <option value={CommentStatus.Archived}>{translator.__('Archived')}</option>
            </select>
          </div>
          <button 
            className={`${COMMENT_THREAD_CLASS}-expand-button`}
            onClick={toggleExpanded}
            aria-label={expanded ? 
              translator.__('Collapse thread') : 
              translator.__('Expand thread')}
          >
            {expanded ? '▼' : '►'}
          </button>
        </div>
      </div>
      
      {expanded && (
        <div className={`${COMMENT_THREAD_CLASS}-content`}>
          <Comment 
            comment={thread.rootComment} 
            commentManager={commentManager} 
            translator={translator} 
            rendermime={rendermime}
            isEditing={editingCommentId === thread.rootComment.id}
            onEdit={setEditingCommentId}
          />
          
          {thread.replies.length > 0 && (
            <div className={`${COMMENT_THREAD_CLASS}-replies`}>
              {thread.replies.map(reply => (
                <Comment 
                  key={reply.id} 
                  comment={reply} 
                  commentManager={commentManager} 
                  translator={translator} 
                  rendermime={rendermime}
                  isEditing={editingCommentId === reply.id}
                  onEdit={setEditingCommentId}
                />
              ))}
            </div>
          )}
          
          {showReplyForm ? (
            <CommentForm 
              commentManager={commentManager}
              cellId={thread.cellId}
              threadId={thread.id}
              parentId={thread.rootComment.id}
              translator={translator}
              onSubmit={handleReplySubmit}
              onCancel={() => setShowReplyForm(false)}
            />
          ) : (
            <button 
              className={`${COMMENT_THREAD_CLASS}-reply-button`}
              onClick={toggleReplyForm}
              aria-label={translator.__('Reply to thread')}
            >
              {translator.__('Reply')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * A React component for the comment form.
 */
function CommentForm(props: ICommentFormProps): JSX.Element {
  const { 
    commentManager, 
    cellId, 
    threadId, 
    parentId, 
    translator, 
    onSubmit, 
    onCancel,
    initialContent = '',
    isEdit = false,
    editCommentId
  } = props;
  
  const [content, setContent] = useState(initialContent);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Focus the textarea when the form is shown
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  }, []);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    
    if (!content.trim()) {
      return;
    }

    let comment: IComment | undefined;

    if (isEdit && editCommentId) {
      // Update existing comment
      comment = commentManager.updateComment(editCommentId, { content });
    } else {
      // Create new comment
      comment = commentManager.addComment({
        cellId,
        content,
        threadId,
        parentId
      });
    }

    if (comment && onSubmit) {
      onSubmit(comment);
    }

    // Clear the form
    setContent('');
  }, [cellId, commentManager, content, isEdit, editCommentId, onSubmit, parentId, threadId]);

  const handleCancel = useCallback(() => {
    if (onCancel) {
      onCancel();
    }
  }, [onCancel]);

  // Handle keyboard shortcuts
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    // Submit on Ctrl+Enter or Cmd+Enter
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      const form = e.currentTarget.closest('form') as HTMLFormElement;
      if (form) {
        form.requestSubmit();
      }
    }
    // Cancel on Escape
    else if (e.key === 'Escape') {
      e.preventDefault();
      handleCancel();
    }
  }, [handleCancel]);

  return (
    <form className={COMMENT_FORM_CLASS} onSubmit={handleSubmit}>
      <textarea 
        className={`${COMMENT_FORM_CLASS}-textarea`}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={translator.__('Add a comment... (Markdown supported)')}
        ref={textareaRef}
        rows={4}
      />
      <div className={`${COMMENT_FORM_CLASS}-buttons`}>
        <button 
          type="button" 
          className={`${COMMENT_FORM_CLASS}-cancel`}
          onClick={handleCancel}
        >
          {translator.__('Cancel')}
        </button>
        <button 
          type="submit" 
          className={`${COMMENT_FORM_CLASS}-submit`}
          disabled={!content.trim()}
        >
          {isEdit ? translator.__('Update') : translator.__('Comment')}
        </button>
      </div>
      <div className={`${COMMENT_FORM_CLASS}-help`}>
        {translator.__('Tip: Use Markdown for formatting. Ctrl+Enter to submit.')}
      </div>
    </form>
  );
}

/**
 * A React component for filtering comments.
 */
function CommentFilter(props: ICommentFilterProps): JSX.Element {
  const { filters, onFilterChange, translator } = props;
  const [localFilters, setLocalFilters] = useState<ICommentFilters>(filters);

  // Update local filters when props change
  useEffect(() => {
    setLocalFilters(filters);
  }, [filters]);

  const handleStatusChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    let statusFilters: CommentStatus[] | undefined;
    
    if (value === 'all') {
      statusFilters = undefined;
    } else if (value === 'active') {
      statusFilters = [CommentStatus.Active, CommentStatus.Question];
    } else if (value === 'resolved') {
      statusFilters = [CommentStatus.Resolved];
    } else if (value === 'archived') {
      statusFilters = [CommentStatus.Archived];
    } else {
      statusFilters = [value as CommentStatus];
    }
    
    const newFilters = { ...localFilters, status: statusFilters };
    setLocalFilters(newFilters);
    onFilterChange(newFilters);
  }, [localFilters, onFilterChange]);

  const handleSearchChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const searchText = e.target.value || undefined;
    const newFilters = { ...localFilters, searchText };
    setLocalFilters(newFilters);
    onFilterChange(newFilters);
  }, [localFilters, onFilterChange]);

  const handleClearFilters = useCallback(() => {
    const newFilters: ICommentFilters = {};
    setLocalFilters(newFilters);
    onFilterChange(newFilters);
  }, [onFilterChange]);

  return (
    <div className="jp-CommentFilter">
      <div className="jp-CommentFilter-status">
        <label htmlFor="comment-status-filter">{translator.__('Status:')}</label>
        <select 
          id="comment-status-filter"
          value={localFilters.status ? 
            (localFilters.status.length === 1 ? localFilters.status[0] : 
              (localFilters.status.includes(CommentStatus.Active) ? 'active' : 'resolved')) : 
            'all'}
          onChange={handleStatusChange}
        >
          <option value="all">{translator.__('All')}</option>
          <option value="active">{translator.__('Active')}</option>
          <option value={CommentStatus.Question}>{translator.__('Questions')}</option>
          <option value={CommentStatus.Resolved}>{translator.__('Resolved')}</option>
          <option value={CommentStatus.Archived}>{translator.__('Archived')}</option>
        </select>
      </div>
      
      <div className="jp-CommentFilter-search">
        <input 
          type="text" 
          placeholder={translator.__('Search comments...')}
          value={localFilters.searchText || ''}
          onChange={handleSearchChange}
        />
      </div>
      
      {(localFilters.status || localFilters.searchText) && (
        <button 
          className="jp-CommentFilter-clear"
          onClick={handleClearFilters}
        >
          {translator.__('Clear Filters')}
        </button>
      )}
    </div>
  );
}

/**
 * A React component for displaying notifications.
 */
function NotificationPanel(props: INotificationPanelProps): JSX.Element {
  const { commentManager, translator, onNotificationClick } = props;
  const [notifications, setNotifications] = useState<ICommentNotification[]>([]);

  // Get notifications when the component mounts and when they change
  useEffect(() => {
    const updateNotifications = () => {
      setNotifications(commentManager.getNotifications());
    };

    // Initial load
    updateNotifications();

    // Subscribe to notification changes
    const notificationAddedListener = (sender: any, notification: ICommentNotification) => {
      updateNotifications();
    };

    const notificationReadListener = (sender: any, notificationId: string) => {
      updateNotifications();
    };

    commentManager.notificationAdded.connect(notificationAddedListener);
    commentManager.notificationRead.connect(notificationReadListener);

    return () => {
      commentManager.notificationAdded.disconnect(notificationAddedListener);
      commentManager.notificationRead.disconnect(notificationReadListener);
    };
  }, [commentManager]);

  const handleNotificationClick = useCallback((notification: ICommentNotification) => {
    // Mark as read
    commentManager.markNotificationAsRead(notification.commentId);
    
    // Call the callback if provided
    if (onNotificationClick) {
      onNotificationClick(notification);
    }
  }, [commentManager, onNotificationClick]);

  const handleMarkAllAsRead = useCallback(() => {
    commentManager.markAllNotificationsAsRead();
  }, [commentManager]);

  // Group notifications by thread
  const notificationsByThread = notifications.reduce((acc, notification) => {
    if (!acc[notification.threadId]) {
      acc[notification.threadId] = [];
    }
    acc[notification.threadId].push(notification);
    return acc;
  }, {} as Record<string, ICommentNotification[]>);

  return (
    <div className="jp-NotificationPanel">
      <div className="jp-NotificationPanel-header">
        <h3>{translator.__('Notifications')}</h3>
        {notifications.some(n => !n.read) && (
          <button 
            className="jp-NotificationPanel-mark-all-read"
            onClick={handleMarkAllAsRead}
          >
            {translator.__('Mark all as read')}
          </button>
        )}
      </div>
      
      {notifications.length === 0 ? (
        <div className="jp-NotificationPanel-empty">
          {translator.__('No notifications')}
        </div>
      ) : (
        <div className="jp-NotificationPanel-list">
          {Object.entries(notificationsByThread).map(([threadId, threadNotifications]) => (
            <div key={threadId} className="jp-NotificationPanel-thread">
              {threadNotifications.map(notification => (
                <div 
                  key={notification.commentId} 
                  className={`jp-NotificationPanel-item ${notification.read ? 'jp-NotificationPanel-item-read' : 'jp-NotificationPanel-item-unread'}`}
                  onClick={() => handleNotificationClick(notification)}
                >
                  <div className="jp-NotificationPanel-item-type">
                    {notification.type === 'new' && translator.__('New comment')}
                    {notification.type === 'reply' && translator.__('Reply')}
                    {notification.type === 'mention' && translator.__('Mention')}
                    {notification.type === 'resolution' && translator.__('Thread resolved')}
                    {notification.type === 'status_change' && translator.__('Status changed')}
                  </div>
                  <div className="jp-NotificationPanel-item-time">
                    {Time.formatHuman(new Date(notification.createdAt))}
                  </div>
                  {!notification.read && (
                    <div className="jp-NotificationPanel-item-unread-indicator" />
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * A React component for the comment system.
 */
export function CommentSystem(props: ICommentSystemProps): JSX.Element {
  const { 
    commentManager, 
    notebookTracker, 
    translator: translatorProp, 
    rendermime,
    viewMode = 'sidebar'
  } = props;
  
  const translator = translatorProp || nullTranslator;
  const trans = translator.load('notebook');
  
  const [activeNotebook, setActiveNotebook] = useState<NotebookPanel | null>(null);
  const [threads, setThreads] = useState<ICommentThread[]>([]);
  const [filters, setFilters] = useState<ICommentFilters>({});
  const [showNewCommentForm, setShowNewCommentForm] = useState(false);
  const [activeCellId, setActiveCellId] = useState<string | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showNotifications, setShowNotifications] = useState(false);
  
  // Update active notebook when the tracker changes
  useEffect(() => {
    const updateActiveNotebook = () => {
      setActiveNotebook(notebookTracker.currentWidget);
    };
    
    // Initial update
    updateActiveNotebook();
    
    // Subscribe to changes
    notebookTracker.currentChanged.connect(updateActiveNotebook);
    
    return () => {
      notebookTracker.currentChanged.disconnect(updateActiveNotebook);
    };
  }, [notebookTracker]);
  
  // Update active cell when it changes
  useEffect(() => {
    if (!activeNotebook) {
      return;
    }
    
    const updateActiveCell = () => {
      const activeCell = activeNotebook.content.activeCell;
      setActiveCellId(activeCell?.model.id || null);
    };
    
    // Initial update
    updateActiveCell();
    
    // Subscribe to changes
    activeNotebook.content.activeCellChanged.connect(updateActiveCell);
    
    return () => {
      activeNotebook.content.activeCellChanged.disconnect(updateActiveCell);
    };
  }, [activeNotebook]);
  
  // Update threads when comments change
  useEffect(() => {
    const updateThreads = () => {
      let allThreads = commentManager.getThreads();
      
      // Apply filters
      if (filters.status) {
        allThreads = allThreads.filter(thread => 
          filters.status!.includes(thread.status)
        );
      }
      
      if (filters.cellId) {
        allThreads = allThreads.filter(thread => 
          thread.cellId === filters.cellId
        );
      }
      
      if (filters.authorId) {
        allThreads = allThreads.filter(thread => 
          thread.rootComment.authorId === filters.authorId || 
          thread.replies.some(reply => reply.authorId === filters.authorId)
        );
      }
      
      if (filters.searchText) {
        const searchLower = filters.searchText.toLowerCase();
        allThreads = allThreads.filter(thread => 
          thread.rootComment.content.toLowerCase().includes(searchLower) ||
          thread.replies.some(reply => 
            reply.content.toLowerCase().includes(searchLower)
          )
        );
      }
      
      // Sort threads by last update time (newest first)
      allThreads.sort((a, b) => b.updatedAt - a.updatedAt);
      
      setThreads(allThreads);
    };
    
    // Initial update
    updateThreads();
    
    // Subscribe to comment changes
    const commentsChangedListener = () => {
      updateThreads();
    };
    
    commentManager.commentsChanged.connect(commentsChangedListener);
    
    return () => {
      commentManager.commentsChanged.disconnect(commentsChangedListener);
    };
  }, [commentManager, filters]);
  
  // Update unread notification count
  useEffect(() => {
    const updateUnreadCount = () => {
      setUnreadCount(commentManager.getUnreadNotifications().length);
    };
    
    // Initial update
    updateUnreadCount();
    
    // Subscribe to notification changes
    const notificationAddedListener = () => {
      updateUnreadCount();
    };
    
    const notificationReadListener = () => {
      updateUnreadCount();
    };
    
    commentManager.notificationAdded.connect(notificationAddedListener);
    commentManager.notificationRead.connect(notificationReadListener);
    
    return () => {
      commentManager.notificationAdded.disconnect(notificationAddedListener);
      commentManager.notificationRead.disconnect(notificationReadListener);
    };
  }, [commentManager]);
  
  const handleFilterChange = useCallback((newFilters: ICommentFilters) => {
    setFilters(newFilters);
  }, []);
  
  const handleNewCommentSubmit = useCallback(() => {
    setShowNewCommentForm(false);
  }, []);
  
  const handleNotificationClick = useCallback((notification: ICommentNotification) => {
    // Find the cell and scroll to it
    if (activeNotebook) {
      const cells = activeNotebook.content.widgets;
      const cell = cells.find(cell => cell.model.id === notification.cellId);
      if (cell) {
        // Scroll to the cell
        cell.node.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        // Highlight the cell briefly
        cell.node.classList.add('jp-mod-highlighted');
        setTimeout(() => {
          cell.node.classList.remove('jp-mod-highlighted');
        }, 2000);
        
        // Set the cell as active
        activeNotebook.content.activeCellIndex = cells.indexOf(cell);
        
        // Filter to show only comments for this cell
        setFilters({ ...filters, cellId: notification.cellId });
      }
    }
    
    // Hide notifications panel
    setShowNotifications(false);
  }, [activeNotebook, filters]);
  
  // Render the comment system based on view mode
  if (viewMode === 'inline') {
    // Inline view shows comments next to cells
    return (
      <div className={`${COMMENT_SYSTEM_CLASS} ${COMMENT_INLINE_CLASS}`}>
        {activeNotebook && activeCellId && (
          <div className="jp-CommentInline-cell">
            <div className="jp-CommentInline-header">
              <h3>{trans.__('Comments')}</h3>
              <div className="jp-CommentInline-actions">
                {unreadCount > 0 && (
                  <div 
                    className={COMMENT_NOTIFICATION_BADGE_CLASS}
                    onClick={() => setShowNotifications(!showNotifications)}
                  >
                    {unreadCount}
                  </div>
                )}
                <button 
                  className="jp-CommentInline-new-button"
                  onClick={() => setShowNewCommentForm(!showNewCommentForm)}
                >
                  {showNewCommentForm ? trans.__('Cancel') : trans.__('New Comment')}
                </button>
              </div>
            </div>
            
            {showNotifications && (
              <NotificationPanel 
                commentManager={commentManager}
                translator={trans}
                onNotificationClick={handleNotificationClick}
              />
            )}
            
            {showNewCommentForm && (
              <CommentForm 
                commentManager={commentManager}
                cellId={activeCellId}
                translator={trans}
                onSubmit={handleNewCommentSubmit}
                onCancel={() => setShowNewCommentForm(false)}
              />
            )}
            
            <CommentFilter 
              filters={filters}
              onFilterChange={handleFilterChange}
              translator={trans}
            />
            
            <div className="jp-CommentInline-threads">
              {threads
                .filter(thread => !filters.cellId || thread.cellId === activeCellId)
                .map(thread => (
                  <CommentThread 
                    key={thread.id}
                    thread={thread}
                    commentManager={commentManager}
                    translator={trans}
                    rendermime={rendermime}
                  />
                ))}
              
              {threads.filter(thread => !filters.cellId || thread.cellId === activeCellId).length === 0 && (
                <div className="jp-CommentInline-empty">
                  {trans.__('No comments for this cell')}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    );
  } else {
    // Sidebar view shows all comments in a sidebar
    return (
      <div className={`${COMMENT_SYSTEM_CLASS} ${COMMENT_SIDEBAR_CLASS}`}>
        <div className="jp-CommentSidebar-header">
          <h3>{trans.__('Comments')}</h3>
          <div className="jp-CommentSidebar-actions">
            {unreadCount > 0 && (
              <div 
                className={COMMENT_NOTIFICATION_BADGE_CLASS}
                onClick={() => setShowNotifications(!showNotifications)}
              >
                {unreadCount}
              </div>
            )}
            {activeCellId && (
              <button 
                className="jp-CommentSidebar-new-button"
                onClick={() => setShowNewCommentForm(!showNewCommentForm)}
              >
                {showNewCommentForm ? trans.__('Cancel') : trans.__('New Comment')}
              </button>
            )}
          </div>
        </div>
        
        {showNotifications && (
          <NotificationPanel 
            commentManager={commentManager}
            translator={trans}
            onNotificationClick={handleNotificationClick}
          />
        )}
        
        {showNewCommentForm && activeCellId && (
          <CommentForm 
            commentManager={commentManager}
            cellId={activeCellId}
            translator={trans}
            onSubmit={handleNewCommentSubmit}
            onCancel={() => setShowNewCommentForm(false)}
          />
        )}
        
        <CommentFilter 
          filters={filters}
          onFilterChange={handleFilterChange}
          translator={trans}
        />
        
        <div className="jp-CommentSidebar-threads">
          {threads.length > 0 ? (
            threads.map(thread => (
              <CommentThread 
                key={thread.id}
                thread={thread}
                commentManager={commentManager}
                translator={trans}
                rendermime={rendermime}
              />
            ))
          ) : (
            <div className="jp-CommentSidebar-empty">
              {trans.__('No comments in this notebook')}
            </div>
          )}
        </div>
      </div>
    );
  }
}

/**
 * A namespace for CommentSystem statics.
 */
export namespace CommentSystem {
  /**
   * Create a new CommentSystem widget.
   */
  export function createWidget(options: ICommentSystemProps): ReactWidget {
    return ReactWidget.create(
      <CommentSystem 
        commentManager={options.commentManager}
        notebookTracker={options.notebookTracker}
        translator={options.translator}
        rendermime={options.rendermime}
        viewMode={options.viewMode}
      />
    );
  }
}
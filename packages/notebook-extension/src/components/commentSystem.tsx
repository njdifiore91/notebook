// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ICommentManager, ICommentThread, IComment, CommentStatus, ICommentAuthor } from '@jupyterlab/notebook';
import { NotebookPanel, INotebookModel } from '@jupyterlab/notebook';
import { MarkdownCell, CodeCell } from '@jupyterlab/cells';
import { IObservableList } from '@jupyterlab/observables';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { Notebook } from '@jupyterlab/notebook';
import { LabIcon } from '@jupyterlab/ui-components';
import { Signal } from '@lumino/signaling';
import { Widget } from '@lumino/widgets';
import { Message } from '@lumino/messaging';
import { marked } from 'marked';
import { sanitize } from 'dompurify';

/**
 * Comment view mode enum
 */
enum CommentViewMode {
  /**
   * Inline mode - comments appear next to cells
   */
  Inline = 'inline',

  /**
   * Sidebar mode - comments appear in a sidebar
   */
  Sidebar = 'sidebar'
}

/**
 * Comment filter options
 */
interface ICommentFilterOptions {
  /**
   * Filter by comment status
   */
  status?: CommentStatus;

  /**
   * Filter by author ID
   */
  authorId?: string;

  /**
   * Filter by cell ID
   */
  cellId?: string;

  /**
   * Search text
   */
  searchText?: string;
}

/**
 * Props for the CommentSystem component
 */
interface ICommentSystemProps {
  /**
   * The notebook panel
   */
  notebookPanel: NotebookPanel;

  /**
   * The comment manager
   */
  commentManager: ICommentManager;

  /**
   * The current user
   */
  currentUser: ICommentAuthor;

  /**
   * The translator
   */
  translator?: ITranslator;

  /**
   * The initial view mode
   */
  initialViewMode?: CommentViewMode;
}

/**
 * Props for the CommentThread component
 */
interface ICommentThreadProps {
  /**
   * The comment thread
   */
  thread: ICommentThread;

  /**
   * The comment manager
   */
  commentManager: ICommentManager;

  /**
   * The current user
   */
  currentUser: ICommentAuthor;

  /**
   * The translator
   */
  translator: ITranslator;

  /**
   * Whether the thread is expanded
   */
  expanded?: boolean;

  /**
   * Callback when the thread is toggled
   */
  onToggle?: () => void;
}

/**
 * Props for the Comment component
 */
interface ICommentProps {
  /**
   * The comment
   */
  comment: IComment;

  /**
   * The comment manager
   */
  commentManager: ICommentManager;

  /**
   * The current user
   */
  currentUser: ICommentAuthor;

  /**
   * The translator
   */
  translator: ITranslator;

  /**
   * Callback when reply is clicked
   */
  onReply?: () => void;
}

/**
 * Props for the CommentEditor component
 */
interface ICommentEditorProps {
  /**
   * The initial content
   */
  initialContent?: string;

  /**
   * The placeholder text
   */
  placeholder?: string;

  /**
   * The submit button text
   */
  submitText?: string;

  /**
   * Callback when the comment is submitted
   */
  onSubmit: (content: string) => void;

  /**
   * Callback when the editor is canceled
   */
  onCancel?: () => void;

  /**
   * The translator
   */
  translator: ITranslator;
}

/**
 * Props for the CommentNotifications component
 */
interface ICommentNotificationsProps {
  /**
   * The comment manager
   */
  commentManager: ICommentManager;

  /**
   * The translator
   */
  translator: ITranslator;
}

/**
 * A React component for editing a comment
 */
function CommentEditor({
  initialContent = '',
  placeholder,
  submitText,
  onSubmit,
  onCancel,
  translator
}: ICommentEditorProps): JSX.Element {
  const trans = translator.load('notebook');
  const [content, setContent] = useState(initialContent);
  const [isPreview, setIsPreview] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (content.trim()) {
      onSubmit(content);
      setContent('');
    }
  };

  const renderedContent = useMemo(() => {
    if (!content) {
      return '';
    }
    return sanitize(marked.parse(content));
  }, [content]);

  return (
    <div className="jp-CommentEditor">
      <div className="jp-CommentEditor-tabs">
        <button
          className={`jp-CommentEditor-tab ${!isPreview ? 'jp-mod-active' : ''}`}
          onClick={() => setIsPreview(false)}
        >
          {trans.__('Write')}
        </button>
        <button
          className={`jp-CommentEditor-tab ${isPreview ? 'jp-mod-active' : ''}`}
          onClick={() => setIsPreview(true)}
        >
          {trans.__('Preview')}
        </button>
      </div>

      <form onSubmit={handleSubmit}>
        {isPreview ? (
          <div
            className="jp-CommentEditor-preview"
            dangerouslySetInnerHTML={{ __html: renderedContent }}
          />
        ) : (
          <textarea
            className="jp-CommentEditor-textarea"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={placeholder || trans.__('Add a comment...')}
            rows={4}
          />
        )}

        <div className="jp-CommentEditor-buttons">
          {onCancel && (
            <button
              type="button"
              className="jp-CommentEditor-cancel"
              onClick={onCancel}
            >
              {trans.__('Cancel')}
            </button>
          )}
          <button
            type="submit"
            className="jp-CommentEditor-submit"
            disabled={!content.trim()}
          >
            {submitText || trans.__('Comment')}
          </button>
        </div>
      </form>

      <div className="jp-CommentEditor-help">
        <span>{trans.__('Supports markdown')}</span>
        <a
          href="https://www.markdownguide.org/basic-syntax/"
          target="_blank"
          rel="noopener noreferrer"
        >
          {trans.__('Markdown help')}
        </a>
      </div>
    </div>
  );
}

/**
 * A React component for displaying a single comment
 */
function Comment({
  comment,
  commentManager,
  currentUser,
  translator,
  onReply
}: ICommentProps): JSX.Element {
  const trans = translator.load('notebook');
  const [isEditing, setIsEditing] = useState(false);
  const [showOptions, setShowOptions] = useState(false);

  const isAuthor = comment.author.id === currentUser.id;
  const formattedDate = new Date(comment.updatedAt).toLocaleString();

  const handleEdit = (content: string) => {
    commentManager.updateComment(comment.id, content);
    setIsEditing(false);
  };

  const handleDelete = () => {
    if (window.confirm(trans.__('Are you sure you want to delete this comment?'))) {
      commentManager.deleteComment(comment.id);
    }
  };

  const renderedContent = useMemo(() => {
    return sanitize(marked.parse(comment.content));
  }, [comment.content]);

  if (isEditing) {
    return (
      <div className="jp-Comment jp-mod-editing">
        <CommentEditor
          initialContent={comment.content}
          onSubmit={handleEdit}
          onCancel={() => setIsEditing(false)}
          submitText={trans.__('Save')}
          translator={translator}
        />
      </div>
    );
  }

  return (
    <div className="jp-Comment">
      <div className="jp-Comment-header">
        <div className="jp-Comment-author">
          {comment.author.avatarUrl ? (
            <img
              src={comment.author.avatarUrl}
              alt={comment.author.name}
              className="jp-Comment-avatar"
            />
          ) : (
            <div className="jp-Comment-avatar jp-Comment-avatarPlaceholder">
              {comment.author.name.charAt(0).toUpperCase()}
            </div>
          )}
          <span className="jp-Comment-authorName">{comment.author.name}</span>
        </div>
        <div className="jp-Comment-date">{formattedDate}</div>
        <div className="jp-Comment-options">
          <button
            className="jp-Comment-optionsButton"
            onClick={() => setShowOptions(!showOptions)}
            aria-label={trans.__('Comment options')}
          >
            ⋮
          </button>
          {showOptions && (
            <div className="jp-Comment-optionsMenu">
              {isAuthor && (
                <>
                  <button
                    className="jp-Comment-optionsMenuItem"
                    onClick={() => {
                      setIsEditing(true);
                      setShowOptions(false);
                    }}
                  >
                    {trans.__('Edit')}
                  </button>
                  <button
                    className="jp-Comment-optionsMenuItem"
                    onClick={() => {
                      handleDelete();
                      setShowOptions(false);
                    }}
                  >
                    {trans.__('Delete')}
                  </button>
                </>
              )}
              <button
                className="jp-Comment-optionsMenuItem"
                onClick={() => {
                  if (onReply) {
                    onReply();
                  }
                  setShowOptions(false);
                }}
              >
                {trans.__('Reply')}
              </button>
            </div>
          )}
        </div>
      </div>
      <div
        className="jp-Comment-content"
        dangerouslySetInnerHTML={{ __html: renderedContent }}
      />
    </div>
  );
}

/**
 * A React component for displaying a comment thread
 */
function CommentThread({
  thread,
  commentManager,
  currentUser,
  translator,
  expanded = true,
  onToggle
}: ICommentThreadProps): JSX.Element {
  const trans = translator.load('notebook');
  const [isReplying, setIsReplying] = useState(false);
  const [replyToId, setReplyToId] = useState<string | undefined>(undefined);

  // Group comments into a tree structure
  const commentTree = useMemo(() => {
    const tree: { [key: string]: IComment[] } = {
      root: []
    };

    // First pass: create entries for all comments
    thread.comments.forEach(comment => {
      if (!comment.parentId) {
        tree.root.push(comment);
      } else {
        if (!tree[comment.parentId]) {
          tree[comment.parentId] = [];
        }
        tree[comment.parentId].push(comment);
      }
    });

    return tree;
  }, [thread.comments]);

  const handleAddComment = (content: string) => {
    commentManager.addComment(thread.id, content, replyToId);
    setIsReplying(false);
    setReplyToId(undefined);
  };

  const handleReplyToComment = (commentId: string) => {
    setReplyToId(commentId);
    setIsReplying(true);
  };

  const handleResolveThread = () => {
    commentManager.resolveThread(thread.id);
  };

  const handleReopenThread = () => {
    commentManager.reopenThread(thread.id);
  };

  const renderCommentTree = (comments: IComment[], depth = 0) => {
    return comments.map(comment => (
      <div key={comment.id} style={{ marginLeft: `${depth * 20}px` }}>
        <Comment
          comment={comment}
          commentManager={commentManager}
          currentUser={currentUser}
          translator={translator}
          onReply={() => handleReplyToComment(comment.id)}
        />
        {commentTree[comment.id] && renderCommentTree(commentTree[comment.id], depth + 1)}
      </div>
    ));
  };

  return (
    <div className={`jp-CommentThread ${expanded ? 'jp-mod-expanded' : ''}`}>
      <div className="jp-CommentThread-header">
        <button
          className="jp-CommentThread-toggle"
          onClick={onToggle}
          aria-label={expanded ? trans.__('Collapse thread') : trans.__('Expand thread')}
        >
          {expanded ? '▼' : '►'}
        </button>
        <div className="jp-CommentThread-status">
          {thread.status === CommentStatus.Open ? (
            <span className="jp-CommentThread-statusOpen">{trans.__('Open')}</span>
          ) : thread.status === CommentStatus.Resolved ? (
            <span className="jp-CommentThread-statusResolved">{trans.__('Resolved')}</span>
          ) : (
            <span className="jp-CommentThread-statusArchived">{trans.__('Archived')}</span>
          )}
        </div>
        <div className="jp-CommentThread-actions">
          {thread.status === CommentStatus.Open ? (
            <button
              className="jp-CommentThread-resolve"
              onClick={handleResolveThread}
              aria-label={trans.__('Resolve thread')}
            >
              {trans.__('Resolve')}
            </button>
          ) : thread.status === CommentStatus.Resolved ? (
            <button
              className="jp-CommentThread-reopen"
              onClick={handleReopenThread}
              aria-label={trans.__('Reopen thread')}
            >
              {trans.__('Reopen')}
            </button>
          ) : null}
        </div>
      </div>

      {expanded && (
        <div className="jp-CommentThread-content">
          {renderCommentTree(commentTree.root)}

          {isReplying && (
            <div className="jp-CommentThread-reply">
              <CommentEditor
                onSubmit={handleAddComment}
                onCancel={() => {
                  setIsReplying(false);
                  setReplyToId(undefined);
                }}
                placeholder={trans.__('Write a reply...')}
                translator={translator}
              />
            </div>
          )}

          {!isReplying && thread.status === CommentStatus.Open && (
            <button
              className="jp-CommentThread-addReply"
              onClick={() => {
                setReplyToId(undefined);
                setIsReplying(true);
              }}
            >
              {trans.__('Add a reply')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * A React component for displaying comment notifications
 */
function CommentNotifications({
  commentManager,
  translator
}: ICommentNotificationsProps): JSX.Element {
  const trans = translator.load('notebook');
  const [notifications, setNotifications] = useState(commentManager.getNotifications());
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const updateNotifications = () => {
      setNotifications(commentManager.getNotifications());
    };

    const notificationAddedHandler = () => {
      updateNotifications();
    };

    const notificationUpdatedHandler = () => {
      updateNotifications();
    };

    const notificationDeletedHandler = () => {
      updateNotifications();
    };

    commentManager.notificationAdded.connect(notificationAddedHandler);
    commentManager.notificationUpdated.connect(notificationUpdatedHandler);
    commentManager.notificationDeleted.connect(notificationDeletedHandler);

    return () => {
      commentManager.notificationAdded.disconnect(notificationAddedHandler);
      commentManager.notificationUpdated.disconnect(notificationUpdatedHandler);
      commentManager.notificationDeleted.disconnect(notificationDeletedHandler);
    };
  }, [commentManager]);

  const unreadCount = notifications.filter(n => !n.read).length;

  const handleMarkAllAsRead = () => {
    commentManager.markAllNotificationsAsRead();
  };

  const handleMarkAsRead = (notificationId: string) => {
    commentManager.markNotificationAsRead(notificationId);
  };

  const handleDeleteNotification = (notificationId: string) => {
    commentManager.deleteNotification(notificationId);
  };

  const getNotificationText = (notification: any) => {
    switch (notification.type) {
      case 'new_comment':
        return trans.__('New comment in thread');
      case 'reply':
        return trans.__('New reply to a comment');
      case 'mention':
        return trans.__('You were mentioned in a comment');
      case 'resolution':
        return trans.__('Thread was resolved');
      default:
        return trans.__('New notification');
    }
  };

  return (
    <div className="jp-CommentNotifications">
      <button
        className="jp-CommentNotifications-toggle"
        onClick={() => setIsOpen(!isOpen)}
        aria-label={trans.__('Comment notifications')}
      >
        🔔
        {unreadCount > 0 && (
          <span className="jp-CommentNotifications-badge">{unreadCount}</span>
        )}
      </button>

      {isOpen && (
        <div className="jp-CommentNotifications-dropdown">
          <div className="jp-CommentNotifications-header">
            <h3>{trans.__('Notifications')}</h3>
            {notifications.length > 0 && (
              <button
                className="jp-CommentNotifications-markAllRead"
                onClick={handleMarkAllAsRead}
              >
                {trans.__('Mark all as read')}
              </button>
            )}
          </div>

          <div className="jp-CommentNotifications-list">
            {notifications.length === 0 ? (
              <div className="jp-CommentNotifications-empty">
                {trans.__('No notifications')}
              </div>
            ) : (
              notifications.map(notification => (
                <div
                  key={notification.id}
                  className={`jp-CommentNotifications-item ${!notification.read ? 'jp-mod-unread' : ''}`}
                >
                  <div className="jp-CommentNotifications-itemContent">
                    <div className="jp-CommentNotifications-itemText">
                      {getNotificationText(notification)}
                    </div>
                    <div className="jp-CommentNotifications-itemDate">
                      {new Date(notification.createdAt).toLocaleString()}
                    </div>
                  </div>
                  <div className="jp-CommentNotifications-itemActions">
                    {!notification.read && (
                      <button
                        className="jp-CommentNotifications-markRead"
                        onClick={() => handleMarkAsRead(notification.id)}
                        aria-label={trans.__('Mark as read')}
                      >
                        ✓
                      </button>
                    )}
                    <button
                      className="jp-CommentNotifications-delete"
                      onClick={() => handleDeleteNotification(notification.id)}
                      aria-label={trans.__('Delete notification')}
                    >
                      ×
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * A React component for the comment system
 */
function CommentSystemComponent({
  notebookPanel,
  commentManager,
  currentUser,
  translator = nullTranslator,
  initialViewMode = CommentViewMode.Inline
}: ICommentSystemProps): JSX.Element {
  const trans = translator.load('notebook');
  const [viewMode, setViewMode] = useState<CommentViewMode>(initialViewMode);
  const [filterOptions, setFilterOptions] = useState<ICommentFilterOptions>({});
  const [threads, setThreads] = useState<ICommentThread[]>([]);
  const [expandedThreads, setExpandedThreads] = useState<Set<string>>(new Set());
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [isAddingComment, setIsAddingComment] = useState(false);

  // Update threads when they change in the comment manager
  useEffect(() => {
    const updateThreads = () => {
      setThreads(commentManager.getThreads());
    };

    const threadAddedHandler = () => {
      updateThreads();
    };

    const threadUpdatedHandler = () => {
      updateThreads();
    };

    const threadDeletedHandler = () => {
      updateThreads();
    };

    commentManager.threadAdded.connect(threadAddedHandler);
    commentManager.threadUpdated.connect(threadUpdatedHandler);
    commentManager.threadDeleted.connect(threadDeletedHandler);

    // Initial load
    updateThreads();

    return () => {
      commentManager.threadAdded.disconnect(threadAddedHandler);
      commentManager.threadUpdated.disconnect(threadUpdatedHandler);
      commentManager.threadDeleted.disconnect(threadDeletedHandler);
    };
  }, [commentManager]);

  // Track active cell changes
  useEffect(() => {
    const notebook = notebookPanel.content;

    const onActiveCellChanged = () => {
      const activeCell = notebook.activeCell;
      if (activeCell) {
        setSelectedCellId(activeCell.model.id);
      } else {
        setSelectedCellId(null);
      }
    };

    notebook.activeCellChanged.connect(onActiveCellChanged);
    onActiveCellChanged(); // Initial call

    return () => {
      notebook.activeCellChanged.disconnect(onActiveCellChanged);
    };
  }, [notebookPanel]);

  // Filter threads based on current filter options
  const filteredThreads = useMemo(() => {
    return threads.filter(thread => {
      // Filter by status
      if (filterOptions.status && thread.status !== filterOptions.status) {
        return false;
      }

      // Filter by cell ID
      if (filterOptions.cellId && thread.cellId !== filterOptions.cellId) {
        return false;
      }

      // Filter by author ID
      if (filterOptions.authorId) {
        const hasAuthor = thread.comments.some(
          comment => comment.author.id === filterOptions.authorId
        );
        if (!hasAuthor) {
          return false;
        }
      }

      // Filter by search text
      if (filterOptions.searchText) {
        const searchText = filterOptions.searchText.toLowerCase();
        const hasMatch = thread.comments.some(comment =>
          comment.content.toLowerCase().includes(searchText)
        );
        if (!hasMatch) {
          return false;
        }
      }

      return true;
    });
  }, [threads, filterOptions]);

  // Toggle thread expansion
  const toggleThread = useCallback((threadId: string) => {
    setExpandedThreads(prev => {
      const newSet = new Set(prev);
      if (newSet.has(threadId)) {
        newSet.delete(threadId);
      } else {
        newSet.add(threadId);
      }
      return newSet;
    });
  }, []);

  // Create a new comment thread for the selected cell
  const handleAddThread = (content: string) => {
    if (!selectedCellId) {
      return;
    }

    const thread = commentManager.createThread(selectedCellId);
    commentManager.addComment(thread.id, content);
    setIsAddingComment(false);

    // Expand the new thread
    setExpandedThreads(prev => {
      const newSet = new Set(prev);
      newSet.add(thread.id);
      return newSet;
    });
  };

  // Group threads by cell ID for inline view
  const threadsByCellId = useMemo(() => {
    const result: { [key: string]: ICommentThread[] } = {};
    filteredThreads.forEach(thread => {
      if (!result[thread.cellId]) {
        result[thread.cellId] = [];
      }
      result[thread.cellId].push(thread);
    });
    return result;
  }, [filteredThreads]);

  // Render the filter controls
  const renderFilterControls = () => {
    return (
      <div className="jp-CommentSystem-filters">
        <select
          className="jp-CommentSystem-filterStatus"
          value={filterOptions.status || ''}
          onChange={e => {
            const value = e.target.value as CommentStatus | '';
            setFilterOptions(prev => ({
              ...prev,
              status: value || undefined
            }));
          }}
        >
          <option value="">{trans.__('All statuses')}</option>
          <option value={CommentStatus.Open}>{trans.__('Open')}</option>
          <option value={CommentStatus.Resolved}>{trans.__('Resolved')}</option>
          <option value={CommentStatus.Archived}>{trans.__('Archived')}</option>
        </select>

        <input
          type="text"
          className="jp-CommentSystem-filterSearch"
          placeholder={trans.__('Search comments...')}
          value={filterOptions.searchText || ''}
          onChange={e => {
            setFilterOptions(prev => ({
              ...prev,
              searchText: e.target.value || undefined
            }));
          }}
        />

        <select
          className="jp-CommentSystem-viewMode"
          value={viewMode}
          onChange={e => {
            setViewMode(e.target.value as CommentViewMode);
          }}
        >
          <option value={CommentViewMode.Inline}>{trans.__('Inline view')}</option>
          <option value={CommentViewMode.Sidebar}>{trans.__('Sidebar view')}</option>
        </select>
      </div>
    );
  };

  // Render the inline view (comments next to cells)
  const renderInlineView = () => {
    return (
      <div className="jp-CommentSystem-inlineView">
        {selectedCellId && (
          <div className="jp-CommentSystem-addComment">
            {isAddingComment ? (
              <CommentEditor
                onSubmit={handleAddThread}
                onCancel={() => setIsAddingComment(false)}
                placeholder={trans.__('Add a comment to the selected cell...')}
                translator={translator}
              />
            ) : (
              <button
                className="jp-CommentSystem-addCommentButton"
                onClick={() => setIsAddingComment(true)}
              >
                {trans.__('Add comment to selected cell')}
              </button>
            )}
          </div>
        )}

        {Object.keys(threadsByCellId).length === 0 ? (
          <div className="jp-CommentSystem-empty">
            {trans.__('No comments match the current filters')}
          </div>
        ) : null}
      </div>
    );
  };

  // Render the sidebar view (all comments in a list)
  const renderSidebarView = () => {
    return (
      <div className="jp-CommentSystem-sidebarView">
        {selectedCellId && (
          <div className="jp-CommentSystem-addComment">
            {isAddingComment ? (
              <CommentEditor
                onSubmit={handleAddThread}
                onCancel={() => setIsAddingComment(false)}
                placeholder={trans.__('Add a comment to the selected cell...')}
                translator={translator}
              />
            ) : (
              <button
                className="jp-CommentSystem-addCommentButton"
                onClick={() => setIsAddingComment(true)}
              >
                {trans.__('Add comment to selected cell')}
              </button>
            )}
          </div>
        )}

        {filteredThreads.length === 0 ? (
          <div className="jp-CommentSystem-empty">
            {trans.__('No comments match the current filters')}
          </div>
        ) : (
          <div className="jp-CommentSystem-threadList">
            {filteredThreads.map(thread => (
              <CommentThread
                key={thread.id}
                thread={thread}
                commentManager={commentManager}
                currentUser={currentUser}
                translator={translator}
                expanded={expandedThreads.has(thread.id)}
                onToggle={() => toggleThread(thread.id)}
              />
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="jp-CommentSystem">
      <div className="jp-CommentSystem-header">
        <h2 className="jp-CommentSystem-title">{trans.__('Comments')}</h2>
        <CommentNotifications
          commentManager={commentManager}
          translator={translator}
        />
      </div>

      {renderFilterControls()}

      {viewMode === CommentViewMode.Inline ? renderInlineView() : renderSidebarView()}
    </div>
  );
}

/**
 * A widget that hosts the comment system component
 */
export class CommentSystemWidget extends ReactWidget {
  /**
   * Construct a new comment system widget.
   */
  constructor(options: {
    notebookPanel: NotebookPanel;
    commentManager: ICommentManager;
    currentUser: ICommentAuthor;
    translator?: ITranslator;
  }) {
    super();
    this.addClass('jp-CommentSystemWidget');
    this._notebookPanel = options.notebookPanel;
    this._commentManager = options.commentManager;
    this._currentUser = options.currentUser;
    this._translator = options.translator || nullTranslator;
  }

  /**
   * Render the comment system component.
   */
  protected render(): JSX.Element {
    return (
      <CommentSystemComponent
        notebookPanel={this._notebookPanel}
        commentManager={this._commentManager}
        currentUser={this._currentUser}
        translator={this._translator}
      />
    );
  }

  private _notebookPanel: NotebookPanel;
  private _commentManager: ICommentManager;
  private _currentUser: ICommentAuthor;
  private _translator: ITranslator;
}

/**
 * A namespace for CommentSystemWidget statics.
 */
export namespace CommentSystemWidget {
  /**
   * Create a comment system widget.
   */
  export function createNode(options: {
    notebookPanel: NotebookPanel;
    commentManager: ICommentManager;
    currentUser: ICommentAuthor;
    translator?: ITranslator;
  }): CommentSystemWidget {
    return new CommentSystemWidget(options);
  }
}
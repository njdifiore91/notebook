// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { NotebookPanel, Notebook } from '@jupyterlab/notebook';
import { Cell } from '@jupyterlab/cells';
import { IObservableList } from '@jupyterlab/observables';
import { Message } from '@lumino/messaging';
import { Widget } from '@lumino/widgets';
import { UUID } from '@lumino/coreutils';

/**
 * Interface for a comment author
 */
export interface ICommentAuthor {
  id: string;
  name: string;
  avatarUrl?: string;
  color?: string;
}

/**
 * Comment status enum
 */
export enum CommentStatus {
  Open = 'open',
  Resolved = 'resolved'
}

/**
 * Interface for a single comment
 */
export interface IComment {
  id: string;
  author: ICommentAuthor;
  content: string;
  timestamp: number;
  cellId?: string;
  selectionRange?: {
    start: number;
    end: number;
  };
  parentId?: string;
  edited?: boolean;
  editTimestamp?: number;
  mentions?: string[]; // Array of user IDs mentioned in the comment
}

/**
 * Interface for a comment thread
 */
export interface ICommentThread {
  id: string;
  comments: IComment[];
  status: CommentStatus;
  cellId: string;
  selectionRange?: {
    start: number;
    end: number;
  };
  createdAt: number;
  updatedAt: number;
  resolvedBy?: string; // User ID who resolved the thread
  resolvedAt?: number; // Timestamp when the thread was resolved
}

/**
 * Interface for the comment service
 */
export interface ICommentService {
  /**
   * Get all comment threads for a notebook
   */
  getThreads(): ICommentThread[];

  /**
   * Add a new comment thread
   */
  addThread(cellId: string, comment: Omit<IComment, 'id' | 'parentId'>, selectionRange?: { start: number; end: number }): Promise<ICommentThread>;

  /**
   * Add a reply to an existing thread
   */
  addReply(threadId: string, comment: Omit<IComment, 'id' | 'cellId' | 'selectionRange'>): Promise<IComment>;

  /**
   * Update the status of a thread
   */
  updateThreadStatus(threadId: string, status: CommentStatus): Promise<ICommentThread>;

  /**
   * Delete a comment thread
   */
  deleteThread(threadId: string): Promise<void>;

  /**
   * Delete a comment
   */
  deleteComment(commentId: string): Promise<void>;

  /**
   * Get threads for a specific cell
   */
  getThreadsForCell(cellId: string): ICommentThread[];

  /**
   * Subscribe to comment changes
   */
  subscribe(callback: (threads: ICommentThread[]) => void): void;

  /**
   * Unsubscribe from comment changes
   */
  unsubscribe(callback: (threads: ICommentThread[]) => void): void;
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
   * The comment service
   */
  commentService: ICommentService;

  /**
   * The translator
   */
  translator?: ITranslator;

  /**
   * The current user
   */
  currentUser: ICommentAuthor;
}

/**
 * Props for the CommentThread component
 */
interface ICommentThreadProps {
  thread: ICommentThread;
  commentService: ICommentService;
  currentUser: ICommentAuthor;
  translator: ITranslator;
  onThreadResolved: (threadId: string) => void;
  onThreadReopened: (threadId: string) => void;
}

/**
 * Props for the Comment component
 */
interface ICommentProps {
  comment: IComment;
  translator: ITranslator;
}

/**
 * Props for the CommentEditor component
 */
interface ICommentEditorProps {
  onSubmit: (content: string) => void;
  placeholder?: string;
  initialContent?: string;
  translator: ITranslator;
  buttonLabel?: string;
}

/**
 * Format a timestamp as a relative time string
 */
export const formatRelativeTime = (timestamp: number, translator: ITranslator): string => {
  const trans = translator.load('notebook');
  const now = Date.now();
  const diff = now - timestamp;
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (seconds < 60) {
    return trans.__('just now');
  } else if (minutes < 60) {
    return trans.__('%1 minutes ago', minutes);
  } else if (hours < 24) {
    return trans.__('%1 hours ago', hours);
  } else if (days < 30) {
    return trans.__('%1 days ago', days);
  } else {
    const date = new Date(timestamp);
    return date.toLocaleDateString();
  }
};

/**
 * Process comment text to highlight mentions
 */
const processCommentText = (text: string): React.ReactNode => {
  // Simple regex to find @mentions
  const mentionRegex = /@([\w-]+)/g;
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = mentionRegex.exec(text)) !== null) {
    // Add text before the mention
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }
    
    // Add the mention with special styling
    parts.push(
      <span key={`mention-${match.index}`} className="jp-CommentSystem-mention">
        {match[0]}
      </span>
    );
    
    lastIndex = match.index + match[0].length;
  }
  
  // Add any remaining text
  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }
  
  return parts.length > 0 ? parts : text;
};

/**
 * Component for rendering a single comment
 */
export const Comment: React.FC<ICommentProps> = ({ comment, translator }) => {
  return (
    <div className="jp-CommentSystem-comment">
      <div className="jp-CommentSystem-commentHeader">
        <div 
          className="jp-CommentSystem-commentAvatar"
          style={{ backgroundColor: comment.author.color || '#1976d2' }}
        >
          {comment.author.avatarUrl ? (
            <img src={comment.author.avatarUrl} alt={comment.author.name} />
          ) : (
            comment.author.name.charAt(0).toUpperCase()
          )}
        </div>
        <div className="jp-CommentSystem-commentAuthor">
          {comment.author.name}
        </div>
        <div className="jp-CommentSystem-commentTime">
          {formatRelativeTime(comment.timestamp, translator)}
          {comment.edited && (
            <span className="jp-CommentSystem-commentEdited">
              {' • '}{translator.load('notebook').__('edited')}
            </span>
          )}
        </div>
      </div>
      <div className="jp-CommentSystem-commentContent">
        {processCommentText(comment.content)}
      </div>
    </div>
  );
};

/**
 * Component for editing or creating a comment
 */
export const CommentEditor: React.FC<ICommentEditorProps> = ({ 
  onSubmit, 
  placeholder, 
  initialContent = '', 
  translator,
  buttonLabel
}) => {
  const trans = translator.load('notebook');
  const [content, setContent] = useState(initialContent);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize the textarea as content changes
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [content]);

  // Focus the textarea when the component mounts
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  }, []);

  const handleSubmit = () => {
    if (content.trim()) {
      onSubmit(content);
      setContent('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Submit on Ctrl+Enter or Cmd+Enter
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="jp-CommentSystem-editor">
      <textarea
        ref={textareaRef}
        className="jp-CommentSystem-editorTextarea"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder={placeholder || trans.__('Add a comment...')}
        onKeyDown={handleKeyDown}
        aria-label={trans.__('Comment text')}
      />
      <div className="jp-CommentSystem-editorControls">
        <button
          className="jp-CommentSystem-editorSubmit"
          onClick={handleSubmit}
          disabled={!content.trim()}
          aria-label={buttonLabel || trans.__('Submit comment')}
        >
          {buttonLabel || trans.__('Comment')}
        </button>
        <div className="jp-CommentSystem-editorHint">
          {trans.__('Press Ctrl+Enter to submit')}
        </div>
      </div>
    </div>
  );
};

/**
 * Component for rendering a comment thread
 */
export const CommentThread: React.FC<ICommentThreadProps> = ({ 
  thread, 
  commentService, 
  currentUser, 
  translator,
  onThreadResolved,
  onThreadReopened
}) => {
  const trans = translator.load('notebook');
  const [isReplying, setIsReplying] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);

  const handleReply = async (content: string) => {
    try {
      await commentService.addReply(thread.id, {
        author: currentUser,
        content,
        timestamp: Date.now(),
      });
      setIsReplying(false);
    } catch (error) {
      console.error('Failed to add reply:', error);
    }
  };

  const handleResolve = async () => {
    try {
      await commentService.updateThreadStatus(thread.id, CommentStatus.Resolved);
      onThreadResolved(thread.id);
    } catch (error) {
      console.error('Failed to resolve thread:', error);
    }
  };

  const handleReopen = async () => {
    try {
      await commentService.updateThreadStatus(thread.id, CommentStatus.Open);
      onThreadReopened(thread.id);
    } catch (error) {
      console.error('Failed to reopen thread:', error);
    }
  };

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <div 
      className={`jp-CommentSystem-thread ${thread.status === CommentStatus.Resolved ? 'jp-CommentSystem-threadResolved' : ''}`}
      data-cell-id={thread.cellId}
    >
      <div className="jp-CommentSystem-threadHeader">
        <button 
          className="jp-CommentSystem-threadToggle"
          onClick={toggleExpanded}
          aria-expanded={isExpanded}
          aria-label={isExpanded ? trans.__('Collapse thread') : trans.__('Expand thread')}
        >
          <span className={`jp-CommentSystem-threadToggleIcon ${isExpanded ? 'jp-CommentSystem-threadToggleIconExpanded' : ''}`}>
            ▶
          </span>
        </button>
        <div className="jp-CommentSystem-threadTitle">
          {thread.status === CommentStatus.Resolved ? 
            trans.__('Resolved comment') : 
            trans.__('Comment thread')}
        </div>
        <div className="jp-CommentSystem-threadActions">
          {thread.status === CommentStatus.Open ? (
            <button 
              className="jp-CommentSystem-threadResolve"
              onClick={handleResolve}
              aria-label={trans.__('Resolve thread')}
            >
              {trans.__('Resolve')}
            </button>
          ) : (
            <button 
              className="jp-CommentSystem-threadReopen"
              onClick={handleReopen}
              aria-label={trans.__('Reopen thread')}
            >
              {trans.__('Reopen')}
            </button>
          )}
        </div>
      </div>
      {isExpanded && (
        <div className="jp-CommentSystem-threadContent">
          {thread.comments.map(comment => (
            <Comment 
              key={comment.id} 
              comment={comment} 
              translator={translator} 
            />
          ))}
          {thread.status === CommentStatus.Open && (
            <div className="jp-CommentSystem-threadReplyArea">
              {isReplying ? (
                <CommentEditor 
                  onSubmit={handleReply}
                  translator={translator}
                  placeholder={trans.__('Add a reply...')}
                  buttonLabel={trans.__('Reply')}
                />
              ) : (
                <button 
                  className="jp-CommentSystem-threadReplyButton"
                  onClick={() => setIsReplying(true)}
                  aria-label={trans.__('Add a reply')}
                >
                  {trans.__('Reply')}
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/**
 * Main comment system component
 */
export const CommentSystem: React.FC<ICommentSystemProps> = ({ 
  notebookPanel, 
  commentService, 
  translator = nullTranslator,
  currentUser
}) => {
  const trans = translator.load('notebook');
  const [threads, setThreads] = useState<ICommentThread[]>([]);
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [isAddingComment, setIsAddingComment] = useState(false);
  const [showResolved, setShowResolved] = useState(false);

  // Update threads when they change
  useEffect(() => {
    const handleThreadsChanged = (updatedThreads: ICommentThread[]) => {
      setThreads(updatedThreads);
    };

    // Initial load
    setThreads(commentService.getThreads());

    // Subscribe to changes
    commentService.subscribe(handleThreadsChanged);

    return () => {
      commentService.unsubscribe(handleThreadsChanged);
    };
  }, [commentService]);

  // Track selected cell
  useEffect(() => {
    const notebook = notebookPanel.content;
    
    const handleActiveCellChanged = (_: Notebook, cell: Cell | null) => {
      if (cell) {
        setSelectedCellId(cell.model.id);
      } else {
        setSelectedCellId(null);
      }
    };

    // Initial selection
    if (notebook.activeCell) {
      setSelectedCellId(notebook.activeCell.model.id);
    }

    // Listen for changes
    notebook.activeCellChanged.connect(handleActiveCellChanged);

    return () => {
      notebook.activeCellChanged.disconnect(handleActiveCellChanged);
    };
  }, [notebookPanel]);

  // Handle adding a new comment
  const handleAddComment = async (content: string) => {
    if (!selectedCellId) {
      return;
    }

    try {
      await commentService.addThread(
        selectedCellId,
        {
          author: currentUser,
          content,
          timestamp: Date.now()
        }
      );
      setIsAddingComment(false);
    } catch (error) {
      console.error('Failed to add comment:', error);
    }
  };

  // Filter threads based on selected cell and resolved status
  const filteredThreads = threads.filter(thread => {
    const isForSelectedCell = selectedCellId && thread.cellId === selectedCellId;
    const matchesResolvedFilter = 
      (showResolved && thread.status === CommentStatus.Resolved) || 
      (!showResolved && thread.status === CommentStatus.Open);
    
    return isForSelectedCell && matchesResolvedFilter;
  });
  
  // Sort threads by creation time (newest first)
  filteredThreads.sort((a, b) => b.createdAt - a.createdAt);

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Alt+C to add a comment
      if (event.altKey && event.key === 'c') {
        event.preventDefault();
        setIsAddingComment(true);
      }
      
      // Alt+R to toggle showing resolved comments
      if (event.altKey && event.key === 'r') {
        event.preventDefault();
        setShowResolved(!showResolved);
      }
      
      // Escape to cancel adding a comment
      if (event.key === 'Escape' && isAddingComment) {
        event.preventDefault();
        setIsAddingComment(false);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isAddingComment, showResolved]);

  return (
    <div className="jp-CommentSystem">
      <div className="jp-CommentSystem-header">
        <h3 className="jp-CommentSystem-title">
          {trans.__('Comments')}
        </h3>
        <div className="jp-CommentSystem-controls">
          <label className="jp-CommentSystem-showResolvedLabel">
            <input
              type="checkbox"
              checked={showResolved}
              onChange={() => setShowResolved(!showResolved)}
              className="jp-CommentSystem-showResolvedCheckbox"
              aria-label={trans.__('Show resolved comments')}
            />
            {trans.__('Show resolved (Alt+R)')}
          </label>
        </div>
      </div>

      <div className="jp-CommentSystem-content">
        {selectedCellId ? (
          <>
            {filteredThreads.length > 0 ? (
              <div className="jp-CommentSystem-threads">
                {filteredThreads.map(thread => (
                  <CommentThread
                    key={thread.id}
                    thread={thread}
                    commentService={commentService}
                    currentUser={currentUser}
                    translator={translator}
                    onThreadResolved={(threadId) => {
                      // This is handled by the subscription, but we could add UI feedback here
                    }}
                    onThreadReopened={(threadId) => {
                      // This is handled by the subscription, but we could add UI feedback here
                    }}
                  />
                ))}
              </div>
            ) : (
              <div className="jp-CommentSystem-empty">
                {showResolved ? 
                  trans.__('No resolved comments for this cell') : 
                  trans.__('No comments for this cell')}
              </div>
            )}

            {!isAddingComment ? (
              <button
                className="jp-CommentSystem-addButton"
                onClick={() => setIsAddingComment(true)}
                aria-label={trans.__('Add comment')}
              >
                {trans.__('Add comment (Alt+C)')}
              </button>
            ) : (
              <div className="jp-CommentSystem-addCommentArea">
                <CommentEditor
                  onSubmit={handleAddComment}
                  translator={translator}
                />
                <button
                  className="jp-CommentSystem-cancelButton"
                  onClick={() => setIsAddingComment(false)}
                  aria-label={trans.__('Cancel')}
                >
                  {trans.__('Cancel')}
                </button>
              </div>
            )}
          </>
        ) : (
          <div className="jp-CommentSystem-empty">
            {trans.__('Select a cell to view or add comments')}
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * A Lumino widget that wraps the CommentSystem React component.
 * This widget can be added to the right sidebar of the notebook interface.
 */
export class CommentSystemWidget extends ReactWidget {
  /**
   * Construct a new CommentSystemWidget.
   */
  constructor(options: CommentSystemWidget.IOptions) {
    super();
    this._notebookPanel = options.notebookPanel;
    this._commentService = options.commentService;
    this._translator = options.translator || nullTranslator;
    this._currentUser = options.currentUser;
    this.addClass('jp-CommentSystemWidget');
    this.id = `comment-system-${UUID.uuid4()}`;
    this.title.label = this._translator.load('notebook').__('Comments');
    this.title.caption = this._translator.load('notebook').__('Notebook Comments');
    this.title.iconClass = 'jp-CommentsIcon';
    this.title.closable = true;
  }

  /**
   * Handle `'activate-request'` messages.
   */
  protected onActivateRequest(msg: Message): void {
    super.onActivateRequest(msg);
    this.node.tabIndex = -1;
    this.node.focus();
  }
  
  /**
   * Handle `'after-attach'` messages.
   */
  protected onAfterAttach(msg: Message): void {
    super.onAfterAttach(msg);
    // Add the styles when the widget is attached
    addCommentSystemStyles();
  }

  /**
   * Render the CommentSystem component.
   */
  protected render(): JSX.Element {
    return (
      <CommentSystem
        notebookPanel={this._notebookPanel}
        commentService={this._commentService}
        translator={this._translator}
        currentUser={this._currentUser}
      />
    );
  }

  private _notebookPanel: NotebookPanel;
  private _commentService: ICommentService;
  private _translator: ITranslator;
  private _currentUser: ICommentAuthor;
}

/**
 * A namespace for CommentSystemWidget statics.
 */
export namespace CommentSystemWidget {
  /**
   * Options for creating a CommentSystemWidget.
   */
  export interface IOptions {
    /**
     * The notebook panel that this comment system is associated with.
     */
    notebookPanel: NotebookPanel;

    /**
     * The comment service to use.
     */
    commentService: ICommentService;

    /**
     * The translator to use.
     */
    translator?: ITranslator;

    /**
     * The current user.
     */
    currentUser: ICommentAuthor;
  }

  /**
   * Create a new CommentSystemWidget.
   */
  export function createNode(options: IOptions): CommentSystemWidget {
    return new CommentSystemWidget(options);
  }
  
  /**
   * Create a comment button for the cell toolbar.
   * 
   * @param cell - The cell to create the button for
   * @param commentService - The comment service to use
   * @param translator - The translator to use
   * @returns A button widget that can be added to the cell toolbar
   */
  export function createCellButton(
    cell: Cell,
    commentService: ICommentService,
    translator: ITranslator = nullTranslator
  ): Widget {
    const trans = translator.load('notebook');
    const button = new Widget();
    button.addClass('jp-CommentSystem-cellButton');
    button.node.title = trans.__('Add comment to this cell');
    button.node.setAttribute('aria-label', trans.__('Add comment to this cell'));
    
    // Add click handler to open the comment sidebar and focus on this cell
    button.node.addEventListener('click', () => {
      // This would need to be implemented in the plugin that uses this component
      // to open the comment sidebar and focus on this cell
    });
    
    // Update the button appearance based on whether there are comments for this cell
    const updateButton = () => {
      const threads = commentService.getThreadsForCell(cell.model.id);
      const hasComments = threads.length > 0;
      const hasOpenComments = threads.some(t => t.status === CommentStatus.Open);
      
      button.node.classList.toggle('jp-CommentSystem-cellButtonHasComments', hasComments);
      button.node.classList.toggle('jp-CommentSystem-cellButtonHasOpenComments', hasOpenComments);
      
      // Update the tooltip to show the comment count
      if (hasComments) {
        const openCount = threads.filter(t => t.status === CommentStatus.Open).length;
        const resolvedCount = threads.filter(t => t.status === CommentStatus.Resolved).length;
        
        if (openCount > 0 && resolvedCount > 0) {
          button.node.title = trans.__('%1 open comments, %2 resolved', openCount, resolvedCount);
        } else if (openCount > 0) {
          button.node.title = trans.__('%1 open comments', openCount);
        } else {
          button.node.title = trans.__('%1 resolved comments', resolvedCount);
        }
      } else {
        button.node.title = trans.__('Add comment to this cell');
      }
    };
    
    // Initial update
    updateButton();
    
    // Subscribe to comment changes
    commentService.subscribe(() => {
      updateButton();
    });
    
    return button;
  }
}

/**
 * Add the default styles to the document.
 */
export function addCommentSystemStyles(): void {
  // Don't add styles if they already exist
  if (document.getElementById('jp-CommentSystem-styles')) {
    return;
  }
  
  const style = document.createElement('style');
  style.id = 'jp-CommentSystem-styles';
  style.textContent = `
    .jp-CommentSystem {
      display: flex;
      flex-direction: column;
      height: 100%;
      overflow: hidden;
      background-color: var(--jp-layout-color1);
      color: var(--jp-ui-font-color1);
    }

    .jp-CommentSystem-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 12px;
      border-bottom: 1px solid var(--jp-border-color2);
    }

    .jp-CommentSystem-title {
      font-size: var(--jp-ui-font-size2);
      font-weight: 600;
      margin: 0;
    }

    .jp-CommentSystem-controls {
      display: flex;
      align-items: center;
    }

    .jp-CommentSystem-showResolvedLabel {
      display: flex;
      align-items: center;
      font-size: var(--jp-ui-font-size1);
      cursor: pointer;
    }

    .jp-CommentSystem-showResolvedCheckbox {
      margin-right: 4px;
    }

    .jp-CommentSystem-content {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
    }

    .jp-CommentSystem-empty {
      display: flex;
      justify-content: center;
      align-items: center;
      height: 100px;
      color: var(--jp-ui-font-color2);
      font-style: italic;
    }

    .jp-CommentSystem-threads {
      display: flex;
      flex-direction: column;
      gap: 16px;
      margin-bottom: 16px;
    }

    .jp-CommentSystem-thread {
      border: 1px solid var(--jp-border-color2);
      border-radius: 4px;
      overflow: hidden;
    }

    .jp-CommentSystem-threadResolved {
      opacity: 0.7;
    }

    .jp-CommentSystem-threadHeader {
      display: flex;
      align-items: center;
      padding: 8px 12px;
      background-color: var(--jp-layout-color2);
      border-bottom: 1px solid var(--jp-border-color2);
    }

    .jp-CommentSystem-threadToggle {
      background: none;
      border: none;
      cursor: pointer;
      padding: 0;
      margin-right: 8px;
      color: var(--jp-ui-font-color1);
    }

    .jp-CommentSystem-threadToggleIcon {
      display: inline-block;
      transition: transform 0.15s ease-in-out;
    }

    .jp-CommentSystem-threadToggleIconExpanded {
      transform: rotate(90deg);
    }

    .jp-CommentSystem-threadTitle {
      flex: 1;
      font-weight: 500;
    }

    .jp-CommentSystem-threadActions {
      display: flex;
      gap: 8px;
    }

    .jp-CommentSystem-threadResolve,
    .jp-CommentSystem-threadReopen {
      background-color: var(--jp-layout-color3);
      border: none;
      border-radius: 4px;
      padding: 4px 8px;
      font-size: var(--jp-ui-font-size1);
      cursor: pointer;
      color: var(--jp-ui-font-color1);
    }

    .jp-CommentSystem-threadResolve:hover,
    .jp-CommentSystem-threadReopen:hover {
      background-color: var(--jp-layout-color4);
    }

    .jp-CommentSystem-threadContent {
      padding: 12px;
    }

    .jp-CommentSystem-comment {
      margin-bottom: 12px;
    }

    .jp-CommentSystem-commentHeader {
      display: flex;
      align-items: center;
      margin-bottom: 4px;
    }

    .jp-CommentSystem-commentAvatar {
      width: 24px;
      height: 24px;
      border-radius: 50%;
      display: flex;
      justify-content: center;
      align-items: center;
      color: white;
      font-weight: 500;
      margin-right: 8px;
      overflow: hidden;
    }

    .jp-CommentSystem-commentAvatar img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .jp-CommentSystem-commentAuthor {
      font-weight: 500;
      margin-right: 8px;
    }

    .jp-CommentSystem-commentTime {
      font-size: var(--jp-ui-font-size0);
      color: var(--jp-ui-font-color2);
    }
    
    .jp-CommentSystem-commentEdited {
      font-size: var(--jp-ui-font-size0);
      color: var(--jp-ui-font-color2);
      font-style: italic;
    }

    .jp-CommentSystem-commentContent {
      font-size: 13px;
      line-height: 18px;
      font-weight: 400;
      white-space: pre-wrap;
      word-break: break-word;
      padding-left: 32px;
    }
    
    /* Highlight user mentions in comments */
    .jp-CommentSystem-commentContent .jp-CommentSystem-mention {
      background-color: rgba(var(--jp-brand-color1-rgb), 0.1);
      border-radius: 2px;
      padding: 0 2px;
      font-weight: 500;
    }

    .jp-CommentSystem-threadReplyArea {
      margin-top: 12px;
    }

    .jp-CommentSystem-threadReplyButton {
      background: none;
      border: 1px solid var(--jp-border-color2);
      border-radius: 4px;
      padding: 6px 12px;
      font-size: var(--jp-ui-font-size1);
      cursor: pointer;
      color: var(--jp-ui-font-color1);
    }

    .jp-CommentSystem-threadReplyButton:hover {
      background-color: var(--jp-layout-color2);
    }

    .jp-CommentSystem-editor {
      margin-bottom: 8px;
    }

    .jp-CommentSystem-editorTextarea {
      width: 100%;
      min-height: 80px;
      padding: 8px;
      border: 1px solid var(--jp-border-color2);
      border-radius: 4px;
      resize: vertical;
      font-family: var(--jp-ui-font-family);
      font-size: 13px;
      line-height: 18px;
      background-color: var(--jp-layout-color1);
      color: var(--jp-ui-font-color1);
    }

    .jp-CommentSystem-editorTextarea:focus {
      outline: none;
      border-color: var(--jp-brand-color1);
    }

    .jp-CommentSystem-editorControls {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 8px;
    }

    .jp-CommentSystem-editorSubmit {
      background-color: var(--jp-brand-color1);
      color: white;
      border: none;
      border-radius: 4px;
      padding: 6px 12px;
      font-size: var(--jp-ui-font-size1);
      cursor: pointer;
    }

    .jp-CommentSystem-editorSubmit:disabled {
      background-color: var(--jp-layout-color3);
      color: var(--jp-ui-font-color2);
      cursor: not-allowed;
    }

    .jp-CommentSystem-editorHint {
      font-size: var(--jp-ui-font-size0);
      color: var(--jp-ui-font-color2);
    }

    .jp-CommentSystem-addButton {
      background-color: var(--jp-brand-color1);
      color: white;
      border: none;
      border-radius: 4px;
      padding: 8px 16px;
      font-size: var(--jp-ui-font-size1);
      cursor: pointer;
      width: 100%;
      margin-top: 16px;
    }

    .jp-CommentSystem-addButton:hover {
      background-color: var(--jp-brand-color0);
    }

    .jp-CommentSystem-addCommentArea {
      margin-top: 16px;
    }

    .jp-CommentSystem-cancelButton {
      background: none;
      border: none;
      color: var(--jp-ui-font-color2);
      cursor: pointer;
      padding: 4px 8px;
      font-size: var(--jp-ui-font-size1);
      margin-top: 8px;
    }

    .jp-CommentSystem-cancelButton:hover {
      text-decoration: underline;
    }

    /* Icon for the comment system tab */
    .jp-CommentsIcon {
      background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>');
      background-size: 16px;
      background-repeat: no-repeat;
      background-position: center;
    }
    
    /* Cell comment button styles */
    .jp-CommentSystem-cellButton {
      width: 16px;
      height: 16px;
      background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>');
      background-size: 16px;
      background-repeat: no-repeat;
      background-position: center;
      opacity: 0.5;
      cursor: pointer;
      margin: 0 4px;
    }
    
    .jp-CommentSystem-cellButton:hover {
      opacity: 1;
    }
    
    .jp-CommentSystem-cellButtonHasComments {
      opacity: 0.8;
    }
    
    .jp-CommentSystem-cellButtonHasOpenComments {
      opacity: 1;
      background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="%231976d2" stroke="%231976d2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>');
    }
  `;
  document.head.appendChild(style);
}
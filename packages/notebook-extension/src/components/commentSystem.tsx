// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { Cell } from '@jupyterlab/cells';
import { Avatar, Button, IconButton, Tooltip } from '@jupyterlab/ui-components';

/**
 * CSS styles for the comment system.
 */
const COMMENT_SYSTEM_CLASS = 'jp-CommentSystem';
const COMMENT_THREAD_CLASS = 'jp-CommentThread';
const COMMENT_ITEM_CLASS = 'jp-CommentItem';
const COMMENT_FORM_CLASS = 'jp-CommentForm';

/**
 * Style definitions for the comment system.
 * 
 * These styles will be added to a separate CSS file in a real implementation,
 * but are included here for completeness.
 * 
 * ```css
 * .jp-CommentSystem {
 *   display: flex;
 *   flex-direction: column;
 *   height: 100%;
 *   overflow: hidden;
 *   background-color: var(--jp-layout-color1);
 *   color: var(--jp-ui-font-color1);
 *   font-size: 13px;
 *   line-height: 18px;
 *   font-weight: 400;
 * }
 * 
 * .jp-CommentSystem-header {
 *   display: flex;
 *   justify-content: space-between;
 *   align-items: center;
 *   padding: 8px 12px;
 *   border-bottom: 1px solid var(--jp-border-color2);
 * }
 * 
 * .jp-CommentSystem-header h3 {
 *   margin: 0;
 *   font-size: 14px;
 *   font-weight: 600;
 * }
 * 
 * .jp-CommentSystem-content {
 *   flex: 1;
 *   overflow-y: auto;
 *   padding: 12px;
 * }
 * 
 * .jp-CommentSystem-error {
 *   padding: 8px 12px;
 *   color: var(--jp-error-color1);
 *   background-color: var(--jp-error-color3);
 *   border-radius: 2px;
 *   margin-bottom: 8px;
 * }
 * 
 * .jp-CommentSystem-loading,
 * .jp-CommentSystem-empty {
 *   display: flex;
 *   justify-content: center;
 *   align-items: center;
 *   padding: 24px;
 *   color: var(--jp-ui-font-color2);
 * }
 * 
 * .jp-CommentSystem-threads {
 *   display: flex;
 *   flex-direction: column;
 *   gap: 16px;
 * }
 * 
 * .jp-CommentThread {
 *   display: flex;
 *   flex-direction: column;
 *   border: 1px solid var(--jp-border-color2);
 *   border-radius: 4px;
 *   overflow: hidden;
 * }
 * 
 * .jp-CommentThread-replies {
 *   display: flex;
 *   flex-direction: column;
 *   padding-left: 24px;
 *   border-top: 1px solid var(--jp-border-color1);
 * }
 * 
 * .jp-CommentItem {
 *   display: flex;
 *   flex-direction: column;
 *   padding: 12px;
 *   background-color: var(--jp-layout-color1);
 * }
 * 
 * .jp-CommentItem-reply {
 *   border-top: 1px solid var(--jp-border-color1);
 * }
 * 
 * .jp-CommentItem-resolved {
 *   opacity: 0.7;
 *   background-color: var(--jp-layout-color2);
 * }
 * 
 * .jp-CommentItem-header {
 *   display: flex;
 *   justify-content: space-between;
 *   align-items: center;
 *   margin-bottom: 8px;
 * }
 * 
 * .jp-CommentItem-author {
 *   display: flex;
 *   align-items: center;
 *   gap: 8px;
 * }
 * 
 * .jp-CommentItem-avatar-placeholder {
 *   display: flex;
 *   justify-content: center;
 *   align-items: center;
 *   width: 24px;
 *   height: 24px;
 *   border-radius: 50%;
 *   background-color: var(--jp-brand-color1);
 *   color: white;
 *   font-weight: 600;
 * }
 * 
 * .jp-CommentItem-author-name {
 *   font-weight: 600;
 * }
 * 
 * .jp-CommentItem-timestamp {
 *   font-size: 12px;
 *   color: var(--jp-ui-font-color2);
 * }
 * 
 * .jp-CommentItem-content {
 *   margin-bottom: 8px;
 * }
 * 
 * .jp-CommentItem-content p {
 *   margin: 0;
 *   white-space: pre-wrap;
 *   word-break: break-word;
 * }
 * 
 * .jp-CommentItem-actions {
 *   display: flex;
 *   gap: 8px;
 *   align-items: center;
 * }
 * 
 * .jp-CommentItem-resolved-info {
 *   margin-top: 8px;
 *   font-size: 12px;
 *   color: var(--jp-success-color1);
 * }
 * 
 * .jp-CommentForm {
 *   display: flex;
 *   flex-direction: column;
 *   gap: 8px;
 *   padding: 12px;
 *   background-color: var(--jp-layout-color1);
 * }
 * 
 * .jp-CommentForm-textarea {
 *   width: 100%;
 *   min-height: 80px;
 *   padding: 8px;
 *   border: 1px solid var(--jp-border-color1);
 *   border-radius: 4px;
 *   background-color: var(--jp-layout-color0);
 *   color: var(--jp-ui-font-color1);
 *   resize: vertical;
 * }
 * 
 * .jp-CommentForm-textarea:focus {
 *   outline: none;
 *   border-color: var(--jp-brand-color1);
 * }
 * 
 * .jp-CommentForm-actions {
 *   display: flex;
 *   justify-content: flex-end;
 *   gap: 8px;
 * }
 * ```
 */

/**
 * Interface for a comment in the comment system
 */
export interface IComment {
  /**
   * Unique identifier for the comment
   */
  id: string;

  /**
   * The cell ID this comment is attached to
   */
  cellId: string;

  /**
   * Optional selection range within the cell
   */
  range?: {
    start: number;
    end: number;
  };

  /**
   * The comment text content
   */
  text: string;

  /**
   * The user who created the comment
   */
  author: {
    id: string;
    name: string;
    avatarUrl?: string;
  };

  /**
   * Creation timestamp
   */
  createdAt: Date;

  /**
   * Last update timestamp
   */
  updatedAt: Date;

  /**
   * Whether the comment has been resolved
   */
  resolved: boolean;

  /**
   * The user who resolved the comment, if any
   */
  resolvedBy?: {
    id: string;
    name: string;
    avatarUrl?: string;
  };

  /**
   * Resolution timestamp, if resolved
   */
  resolvedAt?: Date;

  /**
   * Parent comment ID for replies
   */
  parentId?: string;
}

/**
 * Interface for the comment service
 */
export interface ICommentService {
  /**
   * Get all comments for a specific cell
   * 
   * @param cellId - The cell ID to get comments for
   * @returns A promise that resolves to an array of comments
   */
  getCommentsForCell(cellId: string): Promise<IComment[]>;

  /**
   * Add a new comment to a cell
   * 
   * @param cellId - The cell ID to add the comment to
   * @param text - The comment text
   * @param range - Optional selection range within the cell
   * @returns A promise that resolves to the created comment
   */
  addComment(cellId: string, text: string, range?: { start: number; end: number }): Promise<IComment>;

  /**
   * Add a reply to an existing comment
   * 
   * @param parentId - The parent comment ID
   * @param text - The reply text
   * @returns A promise that resolves to the created reply
   */
  addReply(parentId: string, text: string): Promise<IComment>;

  /**
   * Update an existing comment
   * 
   * @param commentId - The comment ID to update
   * @param text - The new comment text
   * @returns A promise that resolves to the updated comment
   */
  updateComment(commentId: string, text: string): Promise<IComment>;

  /**
   * Delete a comment
   * 
   * @param commentId - The comment ID to delete
   * @returns A promise that resolves when the comment is deleted
   */
  deleteComment(commentId: string): Promise<void>;

  /**
   * Resolve a comment
   * 
   * @param commentId - The comment ID to resolve
   * @returns A promise that resolves to the resolved comment
   */
  resolveComment(commentId: string): Promise<IComment>;

  /**
   * Unresolve a comment
   * 
   * @param commentId - The comment ID to unresolve
   * @returns A promise that resolves to the unresolved comment
   */
  unresolveComment(commentId: string): Promise<IComment>;

  /**
   * Subscribe to comment changes for a cell
   * 
   * @param cellId - The cell ID to subscribe to
   * @param callback - The callback to call when comments change
   * @returns A function to unsubscribe
   */
  subscribeToComments(cellId: string, callback: (comments: IComment[]) => void): () => void;
}

/**
 * Props for the CommentItem component
 */
interface ICommentItemProps {
  /**
   * The comment to display
   */
  comment: IComment;

  /**
   * Whether this comment is a reply
   */
  isReply?: boolean;

  /**
   * Callback for when the reply button is clicked
   */
  onReply: (commentId: string) => void;

  /**
   * Callback for when the resolve button is clicked
   */
  onResolve: (commentId: string) => void;

  /**
   * Callback for when the unresolve button is clicked
   */
  onUnresolve: (commentId: string) => void;

  /**
   * Callback for when the edit button is clicked
   */
  onEdit: (commentId: string) => void;

  /**
   * Callback for when the delete button is clicked
   */
  onDelete: (commentId: string) => void;

  /**
   * The translation service
   */
  translator: ITranslator;
}

/**
 * Component for displaying a single comment
 */
const CommentItem: React.FC<ICommentItemProps> = ({
  comment,
  isReply = false,
  onReply,
  onResolve,
  onUnresolve,
  onEdit,
  onDelete,
  translator
}) => {
  const trans = translator.load('notebook');
  const formatDate = (date: Date): string => {
    // Format the date as a relative time (e.g., "2 hours ago")
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffDay > 0) {
      return diffDay === 1
        ? trans.__('Yesterday')
        : trans.__('%1 days ago', diffDay.toString());
    }
    if (diffHour > 0) {
      return trans.__('%1 hours ago', diffHour.toString());
    }
    if (diffMin > 0) {
      return trans.__('%1 minutes ago', diffMin.toString());
    }
    return trans.__('Just now');
  };

  return (
    <div 
      className={`${COMMENT_ITEM_CLASS} ${isReply ? `${COMMENT_ITEM_CLASS}-reply` : ''} ${comment.resolved ? `${COMMENT_ITEM_CLASS}-resolved` : ''}`}
      data-comment-id={comment.id}
    >
      <div className={`${COMMENT_ITEM_CLASS}-header`}>
        <div className={`${COMMENT_ITEM_CLASS}-author`}>
          {comment.author.avatarUrl ? (
            <Avatar src={comment.author.avatarUrl} alt={comment.author.name} size="small" />
          ) : (
            <div className={`${COMMENT_ITEM_CLASS}-avatar-placeholder`}>
              {comment.author.name.charAt(0).toUpperCase()}
            </div>
          )}
          <span className={`${COMMENT_ITEM_CLASS}-author-name`}>{comment.author.name}</span>
        </div>
        <div className={`${COMMENT_ITEM_CLASS}-timestamp`} title={comment.createdAt.toLocaleString()}>
          {formatDate(comment.createdAt)}
        </div>
      </div>
      <div className={`${COMMENT_ITEM_CLASS}-content`}>
        <p style={{ fontSize: '13px', lineHeight: '18px', fontWeight: 400 }}>{comment.text}</p>
      </div>
      <div className={`${COMMENT_ITEM_CLASS}-actions`}>
        {!isReply && !comment.resolved && (
          <Button 
            className={`${COMMENT_ITEM_CLASS}-reply-button`} 
            onClick={() => onReply(comment.id)}
            aria-label={trans.__('Reply to comment')}
          >
            {trans.__('Reply')}
          </Button>
        )}
        {!comment.resolved ? (
          <Button 
            className={`${COMMENT_ITEM_CLASS}-resolve-button`} 
            onClick={() => onResolve(comment.id)}
            aria-label={trans.__('Resolve comment')}
          >
            {trans.__('Resolve')}
          </Button>
        ) : (
          <Button 
            className={`${COMMENT_ITEM_CLASS}-unresolve-button`} 
            onClick={() => onUnresolve(comment.id)}
            aria-label={trans.__('Unresolve comment')}
          >
            {trans.__('Unresolve')}
          </Button>
        )}
        <Tooltip title={trans.__('Edit')}>
          <IconButton 
            className={`${COMMENT_ITEM_CLASS}-edit-button`} 
            onClick={() => onEdit(comment.id)}
            aria-label={trans.__('Edit comment')}
          >
            <span className="jp-icon-edit" />
          </IconButton>
        </Tooltip>
        <Tooltip title={trans.__('Delete')}>
          <IconButton 
            className={`${COMMENT_ITEM_CLASS}-delete-button`} 
            onClick={() => onDelete(comment.id)}
            aria-label={trans.__('Delete comment')}
          >
            <span className="jp-icon-delete" />
          </IconButton>
        </Tooltip>
      </div>
      {comment.resolved && (
        <div className={`${COMMENT_ITEM_CLASS}-resolved-info`}>
          {trans.__('Resolved by %1 on %2', 
            comment.resolvedBy?.name || '', 
            comment.resolvedAt?.toLocaleString() || '')}
        </div>
      )}
    </div>
  );
};

/**
 * Props for the CommentForm component
 */
interface ICommentFormProps {
  /**
   * The cell ID to add the comment to
   */
  cellId: string;

  /**
   * The parent comment ID for replies
   */
  parentId?: string;

  /**
   * The comment ID for editing
   */
  editingCommentId?: string;

  /**
   * Initial text for the comment form
   */
  initialText?: string;

  /**
   * Callback for when the form is submitted
   */
  onSubmit: (text: string) => void;

  /**
   * Callback for when the form is cancelled
   */
  onCancel: () => void;

  /**
   * The translation service
   */
  translator: ITranslator;
}

/**
 * Component for adding or editing a comment
 */
const CommentForm: React.FC<ICommentFormProps> = ({
  cellId,
  parentId,
  editingCommentId,
  initialText = '',
  onSubmit,
  onCancel,
  translator
}) => {
  const trans = translator.load('notebook');
  const [text, setText] = useState(initialText);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // Focus the textarea when the component mounts
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim()) {
      onSubmit(text);
      setText('');
    }
  };

  const isEditing = !!editingCommentId;
  const isReply = !!parentId;

  return (
    <form className={COMMENT_FORM_CLASS} onSubmit={handleSubmit}>
      <textarea
        ref={textareaRef}
        className={`${COMMENT_FORM_CLASS}-textarea`}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={isReply 
          ? trans.__('Write a reply...') 
          : isEditing 
            ? trans.__('Edit comment...') 
            : trans.__('Write a comment...')}
        aria-label={isReply 
          ? trans.__('Reply text') 
          : isEditing 
            ? trans.__('Edit comment text') 
            : trans.__('Comment text')}
        style={{ 
          fontSize: '13px', 
          lineHeight: '18px',
          fontWeight: 400 
        }}
      />
      <div className={`${COMMENT_FORM_CLASS}-actions`}>
        <Button 
          className={`${COMMENT_FORM_CLASS}-cancel`} 
          onClick={onCancel}
          aria-label={trans.__('Cancel')}
        >
          {trans.__('Cancel')}
        </Button>
        <Button 
          className={`${COMMENT_FORM_CLASS}-submit`} 
          type="submit"
          disabled={!text.trim()}
          aria-label={isReply 
            ? trans.__('Submit reply') 
            : isEditing 
              ? trans.__('Update comment') 
              : trans.__('Submit comment')}
        >
          {isReply 
            ? trans.__('Reply') 
            : isEditing 
              ? trans.__('Update') 
              : trans.__('Comment')}
        </Button>
      </div>
    </form>
  );
};

/**
 * Props for the CommentThread component
 */
interface ICommentThreadProps {
  /**
   * The root comment of the thread
   */
  rootComment: IComment;

  /**
   * The replies to the root comment
   */
  replies: IComment[];

  /**
   * The ID of the comment being replied to, if any
   */
  replyingToId: string | null;

  /**
   * The ID of the comment being edited, if any
   */
  editingCommentId: string | null;

  /**
   * Callback for when a reply is submitted
   */
  onReplySubmit: (parentId: string, text: string) => void;

  /**
   * Callback for when the reply button is clicked
   */
  onReplyClick: (commentId: string) => void;

  /**
   * Callback for when the resolve button is clicked
   */
  onResolve: (commentId: string) => void;

  /**
   * Callback for when the unresolve button is clicked
   */
  onUnresolve: (commentId: string) => void;

  /**
   * Callback for when the edit button is clicked
   */
  onEditClick: (commentId: string) => void;

  /**
   * Callback for when an edit is submitted
   */
  onEditSubmit: (commentId: string, text: string) => void;

  /**
   * Callback for when the delete button is clicked
   */
  onDelete: (commentId: string) => void;

  /**
   * Callback for when a form is cancelled
   */
  onCancel: () => void;

  /**
   * The translation service
   */
  translator: ITranslator;
}

/**
 * Component for displaying a thread of comments
 */
const CommentThread: React.FC<ICommentThreadProps> = ({
  rootComment,
  replies,
  replyingToId,
  editingCommentId,
  onReplySubmit,
  onReplyClick,
  onResolve,
  onUnresolve,
  onEditClick,
  onEditSubmit,
  onDelete,
  onCancel,
  translator
}) => {
  // Find the comment being edited in this thread
  const editingComment = editingCommentId === rootComment.id 
    ? rootComment 
    : replies.find(reply => reply.id === editingCommentId);

  return (
    <div className={COMMENT_THREAD_CLASS} data-thread-id={rootComment.id}>
      {editingCommentId === rootComment.id ? (
        <CommentForm
          cellId={rootComment.cellId}
          editingCommentId={rootComment.id}
          initialText={rootComment.text}
          onSubmit={(text) => onEditSubmit(rootComment.id, text)}
          onCancel={onCancel}
          translator={translator}
        />
      ) : (
        <CommentItem
          comment={rootComment}
          onReply={onReplyClick}
          onResolve={onResolve}
          onUnresolve={onUnresolve}
          onEdit={onEditClick}
          onDelete={onDelete}
          translator={translator}
        />
      )}

      {replies.length > 0 && (
        <div className={`${COMMENT_THREAD_CLASS}-replies`}>
          {replies.map(reply => (
            editingCommentId === reply.id ? (
              <CommentForm
                key={reply.id}
                cellId={reply.cellId}
                parentId={rootComment.id}
                editingCommentId={reply.id}
                initialText={reply.text}
                onSubmit={(text) => onEditSubmit(reply.id, text)}
                onCancel={onCancel}
                translator={translator}
              />
            ) : (
              <CommentItem
                key={reply.id}
                comment={reply}
                isReply={true}
                onReply={onReplyClick}
                onResolve={onResolve}
                onUnresolve={onUnresolve}
                onEdit={onEditClick}
                onDelete={onDelete}
                translator={translator}
              />
            )
          ))}
        </div>
      )}

      {replyingToId === rootComment.id && (
        <div className={`${COMMENT_THREAD_CLASS}-reply-form`}>
          <CommentForm
            cellId={rootComment.cellId}
            parentId={rootComment.id}
            onSubmit={(text) => onReplySubmit(rootComment.id, text)}
            onCancel={onCancel}
            translator={translator}
          />
        </div>
      )}
    </div>
  );
};

/**
 * Props for the CommentSystem component
 */
export interface ICommentSystemProps {
  /**
   * The cell to display comments for
   */
  cell: Cell;

  /**
   * The comment service
   */
  commentService: ICommentService;

  /**
   * The translation service
   */
  translator?: ITranslator;
}

/**
 * Main component for the comment system
 */
export const CommentSystem: React.FC<ICommentSystemProps> = ({
  cell,
  commentService,
  translator = nullTranslator
}) => {
  const trans = translator.load('notebook');
  const [comments, setComments] = useState<IComment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddComment, setShowAddComment] = useState(false);
  const [replyingToId, setReplyingToId] = useState<string | null>(null);
  const [editingCommentId, setEditingCommentId] = useState<string | null>(null);

  // Load comments for the cell
  useEffect(() => {
    const loadComments = async () => {
      try {
        setLoading(true);
        setError(null);
        const cellComments = await commentService.getCommentsForCell(cell.model.id);
        setComments(cellComments);
      } catch (err) {
        console.error('Error loading comments:', err);
        setError(trans.__('Failed to load comments'));
      } finally {
        setLoading(false);
      }
    };

    loadComments();

    // Subscribe to comment updates
    const unsubscribe = commentService.subscribeToComments(cell.model.id, (updatedComments) => {
      setComments(updatedComments);
    });

    return () => {
      unsubscribe();
    };
  }, [cell.model.id, commentService, trans]);

  // Group comments into threads (root comments and their replies)
  const commentThreads = useMemo(() => {
    // Find root comments (those without a parentId)
    const rootComments = comments.filter(comment => !comment.parentId);
    
    // Create threads with root comments and their replies
    return rootComments.map(rootComment => {
      const replies = comments.filter(comment => comment.parentId === rootComment.id);
      return {
        rootComment,
        replies
      };
    });
  }, [comments]);

  // Handle adding a new comment
  const handleAddComment = async (text: string) => {
    try {
      await commentService.addComment(cell.model.id, text);
      setShowAddComment(false);
    } catch (err) {
      console.error('Error adding comment:', err);
      setError(trans.__('Failed to add comment'));
    }
  };

  // Handle adding a reply to a comment
  const handleAddReply = async (parentId: string, text: string) => {
    try {
      await commentService.addReply(parentId, text);
      setReplyingToId(null);
    } catch (err) {
      console.error('Error adding reply:', err);
      setError(trans.__('Failed to add reply'));
    }
  };

  // Handle updating a comment
  const handleUpdateComment = async (commentId: string, text: string) => {
    try {
      await commentService.updateComment(commentId, text);
      setEditingCommentId(null);
    } catch (err) {
      console.error('Error updating comment:', err);
      setError(trans.__('Failed to update comment'));
    }
  };

  // Handle resolving a comment
  const handleResolveComment = async (commentId: string) => {
    try {
      await commentService.resolveComment(commentId);
    } catch (err) {
      console.error('Error resolving comment:', err);
      setError(trans.__('Failed to resolve comment'));
    }
  };

  // Handle unresolving a comment
  const handleUnresolveComment = async (commentId: string) => {
    try {
      await commentService.unresolveComment(commentId);
    } catch (err) {
      console.error('Error unresolving comment:', err);
      setError(trans.__('Failed to unresolve comment'));
    }
  };

  // Handle deleting a comment
  const handleDeleteComment = async (commentId: string) => {
    try {
      await commentService.deleteComment(commentId);
    } catch (err) {
      console.error('Error deleting comment:', err);
      setError(trans.__('Failed to delete comment'));
    }
  };

  // Cancel any active forms
  const handleCancel = () => {
    setShowAddComment(false);
    setReplyingToId(null);
    setEditingCommentId(null);
  };

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Escape key cancels any active forms
      if (event.key === 'Escape') {
        handleCancel();
      }

      // Ctrl+Enter or Cmd+Enter submits the active form
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        // Find the active form and submit it
        const activeForm = document.querySelector('.jp-CommentForm');
        if (activeForm) {
          const submitButton = activeForm.querySelector('.jp-CommentForm-submit') as HTMLButtonElement;
          if (submitButton && !submitButton.disabled) {
            submitButton.click();
          }
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  return (
    <div className={COMMENT_SYSTEM_CLASS} role="region" aria-label={trans.__('Comments')}>
      <div className={`${COMMENT_SYSTEM_CLASS}-header`}>
        <h3>{trans.__('Comments')}</h3>
        {!showAddComment && (
          <Button 
            className={`${COMMENT_SYSTEM_CLASS}-add-button`} 
            onClick={() => setShowAddComment(true)}
            aria-label={trans.__('Add comment')}
          >
            {trans.__('Add Comment')}
          </Button>
        )}
      </div>

      {error && (
        <div className={`${COMMENT_SYSTEM_CLASS}-error`} role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <div className={`${COMMENT_SYSTEM_CLASS}-loading`}>
          {trans.__('Loading comments...')}
        </div>
      ) : (
        <div className={`${COMMENT_SYSTEM_CLASS}-content`}>
          {showAddComment && (
            <div className={`${COMMENT_SYSTEM_CLASS}-add-form`}>
              <CommentForm
                cellId={cell.model.id}
                onSubmit={handleAddComment}
                onCancel={handleCancel}
                translator={translator}
              />
            </div>
          )}

          {commentThreads.length > 0 ? (
            <div className={`${COMMENT_SYSTEM_CLASS}-threads`}>
              {commentThreads.map(({ rootComment, replies }) => (
                <CommentThread
                  key={rootComment.id}
                  rootComment={rootComment}
                  replies={replies}
                  replyingToId={replyingToId}
                  editingCommentId={editingCommentId}
                  onReplyClick={setReplyingToId}
                  onReplySubmit={handleAddReply}
                  onResolve={handleResolveComment}
                  onUnresolve={handleUnresolveComment}
                  onEditClick={setEditingCommentId}
                  onEditSubmit={handleUpdateComment}
                  onDelete={handleDeleteComment}
                  onCancel={handleCancel}
                  translator={translator}
                />
              ))}
            </div>
          ) : (
            <div className={`${COMMENT_SYSTEM_CLASS}-empty`}>
              {trans.__('No comments yet. Add a comment to start a discussion.')}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/**
 * A namespace for CommentSystem statics.
 */
export namespace CommentSystemComponent {
  /**
   * Create a new CommentSystem widget.
   *
   * @param options - The options for creating the comment system.
   * @returns A widget containing the comment system.
   */
  export const create = (options: {
    cell: Cell;
    commentService: ICommentService;
    translator?: ITranslator;
  }): ReactWidget => {
    const { cell, commentService, translator = nullTranslator } = options;
    
    return ReactWidget.create(
      <CommentSystem 
        cell={cell} 
        commentService={commentService} 
        translator={translator} 
      />
    );
  };
}
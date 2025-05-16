// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { ISessionContext, SessionContext } from '@jupyterlab/apputils';
import { Cell, ICellModel } from '@jupyterlab/cells';
import { CodeEditor } from '@jupyterlab/codeeditor';
import { IChangedArgs } from '@jupyterlab/coreutils';
import {
  DocumentRegistry,
  IDocumentWidget,
  DocumentWidget
} from '@jupyterlab/docregistry';
import { IRenderMimeRegistry } from '@jupyterlab/rendermime';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { Message } from '@lumino/messaging';
import { ISignal, Signal } from '@lumino/signaling';
import { Widget } from '@lumino/widgets';

import { StaticNotebook } from './notebook';
import { NotebookModel } from './model';

// Import Yjs collaboration components
import { ICollaborationProvider } from './collab/provider';
import { IPresenceTracker } from './collab/awareness';
import { IPermissionManager } from './collab/permissions';
import { ICommentManager } from './collab/comments';
import { IVersionHistory } from './collab/history';
import { ICellLockManager } from './collab/locks';

/**
 * A widget for notebooks.
 *
 * #### Notes
 * The widget model must be a `NotebookModel`.
 */
export class NotebookPanel extends DocumentWidget<
  StaticNotebook,
  NotebookModel
> {
  /**
   * Construct a notebook panel.
   */
  constructor(options: NotebookPanel.IOptions) {
    super({
      content: new StaticNotebook({
        rendermime: options.rendermime,
        contentFactory: options.contentFactory,
        mimeTypeService: options.mimeTypeService,
        translator: options.translator || nullTranslator
      }),
      context: options.context,
      translator: options.translator || nullTranslator
    });

    // Set up collaboration components if provided
    this._collaborationProvider = options.collaborationProvider || null;
    this._presenceTracker = options.presenceTracker || null;
    this._permissionManager = options.permissionManager || null;
    this._commentManager = options.commentManager || null;
    this._versionHistory = options.versionHistory || null;
    this._cellLockManager = options.cellLockManager || null;

    this.translator = options.translator || nullTranslator;
    this.content.activeCellChanged.connect(this._onActiveCellChanged, this);
    this.content.selectionChanged.connect(this._onSelectionChanged, this);

    // Initialize collaboration features if provider is available
    if (this._collaborationProvider) {
      this._initializeCollaboration();
    }
  }

  /**
   * The session context used by the panel.
   */
  get sessionContext(): ISessionContext {
    return this.context.sessionContext;
  }

  /**
   * The model for the widget.
   */
  get model(): NotebookModel {
    return this.content.model as NotebookModel;
  }

  /**
   * The collaboration provider used by this notebook panel.
   */
  get collaborationProvider(): ICollaborationProvider | null {
    return this._collaborationProvider;
  }

  /**
   * The presence tracker used by this notebook panel.
   */
  get presenceTracker(): IPresenceTracker | null {
    return this._presenceTracker;
  }

  /**
   * The permission manager used by this notebook panel.
   */
  get permissionManager(): IPermissionManager | null {
    return this._permissionManager;
  }

  /**
   * The comment manager used by this notebook panel.
   */
  get commentManager(): ICommentManager | null {
    return this._commentManager;
  }

  /**
   * The version history manager used by this notebook panel.
   */
  get versionHistory(): IVersionHistory | null {
    return this._versionHistory;
  }

  /**
   * The cell lock manager used by this notebook panel.
   */
  get cellLockManager(): ICellLockManager | null {
    return this._cellLockManager;
  }

  /**
   * A signal emitted when the active cell changes.
   */
  get activeCellChanged(): ISignal<this, Cell<ICellModel> | null> {
    return this._activeCellChanged;
  }

  /**
   * A signal emitted when the selection state changes.
   */
  get selectionChanged(): ISignal<this, void> {
    return this._selectionChanged;
  }

  /**
   * A signal emitted when a user presence changes.
   */
  get userPresenceChanged(): ISignal<this, void> {
    return this._userPresenceChanged;
  }

  /**
   * A signal emitted when a cell lock state changes.
   */
  get cellLockChanged(): ISignal<this, string> {
    return this._cellLockChanged;
  }

  /**
   * A signal emitted when a comment is added or updated.
   */
  get commentChanged(): ISignal<this, void> {
    return this._commentChanged;
  }

  /**
   * The active cell widget.
   */
  get activeCell(): Cell<ICellModel> | null {
    return this.content.activeCell;
  }

  /**
   * Handle `'activate-request'` messages.
   */
  protected onActivateRequest(msg: Message): void {
    super.onActivateRequest(msg);
    this.content.activate();
  }

  /**
   * Handle a change to the notebook content.
   */
  protected onModelContentChanged(sender: StaticNotebook): void {
    if (!this.model || !this.model.modelDB.isCollaborative) {
      return;
    }

    // If the change was from a collaborative update, ensure the UI is updated
    if (this._collaborationProvider?.isRemoteChange) {
      this.update();
    }
  }

  /**
   * Initialize collaboration features for the notebook panel.
   */
  private _initializeCollaboration(): void {
    if (!this._collaborationProvider || !this.model) {
      return;
    }

    // Connect the collaboration provider to the notebook model
    this._collaborationProvider.connectDocument(this.model);

    // Set up presence tracking for cursor positions and selections
    if (this._presenceTracker) {
      this._setupPresenceTracking();
    }

    // Set up cell locking mechanism
    if (this._cellLockManager) {
      this._setupCellLocking();
    }

    // Set up comment overlay system
    if (this._commentManager) {
      this._setupCommentSystem();
    }

    // Set up version history integration
    if (this._versionHistory) {
      this._setupVersionHistory();
    }

    // Listen for remote changes to update the UI
    this._collaborationProvider.remoteChangesSignal.connect(() => {
      this.update();
    });

    // Update the UI to show collaboration status
    this._updateCollaborationUI();
  }

  /**
   * Set up presence tracking for cursor positions and selections.
   */
  private _setupPresenceTracking(): void {
    if (!this._presenceTracker || !this.content) {
      return;
    }

    // Track active cell changes for presence
    this.content.activeCellChanged.connect((_, cell) => {
      if (cell && this._presenceTracker) {
        this._presenceTracker.setActiveCell(cell.model.id);
      }
    });

    // Track selection changes for presence
    this.content.selectionChanged.connect(() => {
      if (this._presenceTracker) {
        const selectedIds = this.content.widgets
          .filter((cell, index) => this.content.isSelected(index))
          .map(cell => cell.model.id);
        this._presenceTracker.setSelectedCells(selectedIds);
      }
    });

    // Track cursor position changes in cells
    this.content.widgets.forEach(cell => {
      if (cell.editor) {
        cell.editor.model.value.changed.connect(() => {
          if (cell.editor && this._presenceTracker) {
            const position = cell.editor.getCursorPosition();
            const selection = cell.editor.getSelection();
            this._presenceTracker.setCursorPosition(cell.model.id, position, selection);
          }
        });
      }
    });

    // Listen for presence updates from other users
    this._presenceTracker.presenceChanged.connect(() => {
      this._renderPresenceIndicators();
      this._userPresenceChanged.emit(void 0);
    });
  }

  /**
   * Set up cell locking mechanism to prevent editing conflicts.
   */
  private _setupCellLocking(): void {
    if (!this._cellLockManager || !this.content) {
      return;
    }

    // Add lock acquisition when a cell is focused for editing
    this.content.widgets.forEach(cell => {
      if (cell.editor) {
        cell.editor.focus.connect(() => {
          if (this._cellLockManager && !this._cellLockManager.isLocked(cell.model.id)) {
            this._cellLockManager.acquireLock(cell.model.id);
          }
        });
      }
    });

    // Listen for lock state changes
    this._cellLockManager.lockChanged.connect((_, cellId) => {
      this._updateCellLockIndicators();
      this._cellLockChanged.emit(cellId);
    });

    // Update lock indicators initially
    this._updateCellLockIndicators();
  }

  /**
   * Set up comment system for cell-level discussions.
   */
  private _setupCommentSystem(): void {
    if (!this._commentManager || !this.content) {
      return;
    }

    // Listen for comment changes
    this._commentManager.commentsChanged.connect(() => {
      this._updateCommentIndicators();
      this._commentChanged.emit(void 0);
    });

    // Update comment indicators initially
    this._updateCommentIndicators();
  }

  /**
   * Set up version history integration.
   */
  private _setupVersionHistory(): void {
    if (!this._versionHistory || !this.model) {
      return;
    }

    // Connect version history to the notebook model
    this._versionHistory.connectDocument(this.model);
  }

  /**
   * Update the UI to show collaboration status.
   */
  private _updateCollaborationUI(): void {
    if (!this._collaborationProvider) {
      return;
    }

    // Add collaboration status class to the widget
    this.addClass('jp-CollaborativeNotebook');

    // Update the title to show collaboration status
    const docTitle = this.title.label;
    this.title.caption = `${docTitle} (Collaborative)`;
  }

  /**
   * Render presence indicators for all users.
   */
  private _renderPresenceIndicators(): void {
    if (!this._presenceTracker || !this.content) {
      return;
    }

    // Clear existing indicators
    this.content.widgets.forEach(cell => {
      const indicators = cell.node.querySelectorAll('.jp-CollabPresence-indicator');
      indicators.forEach(indicator => indicator.remove());
    });

    // Get current presence data
    const presenceData = this._presenceTracker.getPresenceData();

    // Render indicators for each user's cursor/selection
    for (const userId in presenceData) {
      const userData = presenceData[userId];
      if (userData.activeCell) {
        this._renderUserPresence(userId, userData);
      }
    }
  }

  /**
   * Render presence indicators for a specific user.
   */
  private _renderUserPresence(userId: string, userData: any): void {
    if (!this.content) {
      return;
    }

    // Find the cell this user is active in
    const cellId = userData.activeCell;
    const cellIndex = this.content.widgets.findIndex(cell => cell.model.id === cellId);
    
    if (cellIndex === -1) {
      return;
    }

    const cell = this.content.widgets[cellIndex];

    // Create presence indicator
    const indicator = document.createElement('div');
    indicator.className = 'jp-CollabPresence-indicator';
    indicator.style.backgroundColor = userData.color || '#3F51B5';
    indicator.setAttribute('data-user-id', userId);
    indicator.setAttribute('title', `${userData.displayName || 'User'} is viewing this cell`);

    // Add user avatar/initials
    const avatar = document.createElement('div');
    avatar.className = 'jp-CollabPresence-avatar';
    avatar.textContent = (userData.displayName || 'U').charAt(0);
    avatar.style.backgroundColor = userData.color || '#3F51B5';
    indicator.appendChild(avatar);

    // Add indicator to cell header
    const header = cell.node.querySelector('.jp-Cell-header');
    if (header) {
      header.appendChild(indicator);
    } else {
      cell.node.insertBefore(indicator, cell.node.firstChild);
    }

    // If this user has cursor position data, render cursor indicator in editor
    if (userData.cursorPosition && cell.editor) {
      this._renderCursorIndicator(cell, userData);
    }
  }

  /**
   * Render cursor indicator in a cell editor.
   */
  private _renderCursorIndicator(cell: Cell<ICellModel>, userData: any): void {
    if (!cell.editor) {
      return;
    }

    // Use CodeMirror's addWidget to show cursor position
    const position = userData.cursorPosition;
    const cursorElement = document.createElement('div');
    cursorElement.className = 'jp-CollabPresence-cursor';
    cursorElement.style.backgroundColor = userData.color || '#3F51B5';
    cursorElement.setAttribute('data-user-id', userData.userId);
    
    // Add user name to cursor
    const nameTag = document.createElement('div');
    nameTag.className = 'jp-CollabPresence-name';
    nameTag.textContent = userData.displayName || 'User';
    nameTag.style.backgroundColor = userData.color || '#3F51B5';
    cursorElement.appendChild(nameTag);

    // Add cursor to editor
    cell.editor.addWidget(position, cursorElement);

    // If user has a selection, highlight it
    if (userData.selection) {
      this._renderSelectionHighlight(cell, userData);
    }
  }

  /**
   * Render selection highlight in a cell editor.
   */
  private _renderSelectionHighlight(cell: Cell<ICellModel>, userData: any): void {
    if (!cell.editor) {
      return;
    }

    // Use CodeMirror's markText to highlight selection
    const selection = userData.selection;
    const from = selection.start;
    const to = selection.end;

    // Apply selection highlight
    const marker = cell.editor.markText(from, to, {
      className: 'jp-CollabPresence-selection',
      css: `background-color: ${userData.color}33;` // Add transparency to color
    });

    // Store marker for later removal
    this._selectionMarkers.push(marker);
  }

  /**
   * Update cell lock indicators based on current lock state.
   */
  private _updateCellLockIndicators(): void {
    if (!this._cellLockManager || !this.content) {
      return;
    }

    // Clear existing lock indicators
    this.content.widgets.forEach(cell => {
      const indicators = cell.node.querySelectorAll('.jp-CellLock-indicator');
      indicators.forEach(indicator => indicator.remove());

      // Remove locked class
      cell.removeClass('jp-mod-locked');
      cell.removeClass('jp-mod-lockedByCurrentUser');
    });

    // Get current locks
    const locks = this._cellLockManager.getAllLocks();

    // Add indicators for each locked cell
    for (const cellId in locks) {
      const lockInfo = locks[cellId];
      const cellIndex = this.content.widgets.findIndex(cell => cell.model.id === cellId);
      
      if (cellIndex === -1) {
        continue;
      }

      const cell = this.content.widgets[cellIndex];

      // Add locked class to cell
      cell.addClass('jp-mod-locked');
      
      // If locked by current user, add special class
      if (lockInfo.isCurrentUser) {
        cell.addClass('jp-mod-lockedByCurrentUser');
      }

      // Create lock indicator
      const indicator = document.createElement('div');
      indicator.className = 'jp-CellLock-indicator';
      indicator.setAttribute('title', `Locked by ${lockInfo.userName || 'another user'}`);

      // Add lock icon
      const lockIcon = document.createElement('div');
      lockIcon.className = 'jp-CellLock-icon';
      indicator.appendChild(lockIcon);

      // Add user name
      const userName = document.createElement('div');
      userName.className = 'jp-CellLock-userName';
      userName.textContent = lockInfo.userName || 'User';
      indicator.appendChild(userName);

      // Add indicator to cell header
      const header = cell.node.querySelector('.jp-Cell-header');
      if (header) {
        header.appendChild(indicator);
      } else {
        cell.node.insertBefore(indicator, cell.node.firstChild);
      }

      // Disable editing if locked by another user
      if (!lockInfo.isCurrentUser && cell.editor) {
        cell.editor.setOption('readOnly', true);
      }
    }
  }

  /**
   * Update comment indicators based on current comments.
   */
  private _updateCommentIndicators(): void {
    if (!this._commentManager || !this.content) {
      return;
    }

    // Clear existing comment indicators
    this.content.widgets.forEach(cell => {
      const indicators = cell.node.querySelectorAll('.jp-Comment-indicator');
      indicators.forEach(indicator => indicator.remove());
    });

    // Get comments for all cells
    const comments = this._commentManager.getAllComments();

    // Add indicators for cells with comments
    for (const cellId in comments) {
      const cellComments = comments[cellId];
      if (cellComments.length === 0) {
        continue;
      }

      const cellIndex = this.content.widgets.findIndex(cell => cell.model.id === cellId);
      if (cellIndex === -1) {
        continue;
      }

      const cell = this.content.widgets[cellIndex];

      // Create comment indicator
      const indicator = document.createElement('div');
      indicator.className = 'jp-Comment-indicator';
      indicator.setAttribute('title', `${cellComments.length} comment${cellComments.length !== 1 ? 's' : ''}`);
      indicator.textContent = cellComments.length.toString();

      // Add click handler to show comments
      indicator.addEventListener('click', (event) => {
        event.stopPropagation();
        this._showCommentsForCell(cellId);
      });

      // Add indicator to cell header
      const header = cell.node.querySelector('.jp-Cell-header');
      if (header) {
        header.appendChild(indicator);
      } else {
        cell.node.insertBefore(indicator, cell.node.firstChild);
      }
    }
  }

  /**
   * Show comments for a specific cell.
   */
  private _showCommentsForCell(cellId: string): void {
    if (!this._commentManager) {
      return;
    }

    // Trigger comment display through the comment manager
    this._commentManager.showCommentsForCell(cellId);
  }

  /**
   * Handle a change to the active cell.
   */
  private _onActiveCellChanged(sender: StaticNotebook, args: Cell<ICellModel> | null): void {
    this._activeCellChanged.emit(args);

    // Update presence information if tracking is enabled
    if (args && this._presenceTracker) {
      this._presenceTracker.setActiveCell(args.model.id);
    }

    // Release lock on previously active cell if we're moving to a new cell
    if (this._cellLockManager && this._previousActiveCell && args && this._previousActiveCell !== args) {
      const prevCellId = this._previousActiveCell.model.id;
      if (this._cellLockManager.isLockedByCurrentUser(prevCellId)) {
        this._cellLockManager.releaseLock(prevCellId);
      }
    }

    // Store reference to current active cell
    this._previousActiveCell = args;
  }

  /**
   * Handle a change to the selection.
   */
  private _onSelectionChanged(sender: StaticNotebook): void {
    this._selectionChanged.emit(void 0);

    // Update presence information if tracking is enabled
    if (this._presenceTracker) {
      const selectedIds = this.content.widgets
        .filter((cell, index) => this.content.isSelected(index))
        .map(cell => cell.model.id);
      this._presenceTracker.setSelectedCells(selectedIds);
    }
  }

  private _collaborationProvider: ICollaborationProvider | null = null;
  private _presenceTracker: IPresenceTracker | null = null;
  private _permissionManager: IPermissionManager | null = null;
  private _commentManager: ICommentManager | null = null;
  private _versionHistory: IVersionHistory | null = null;
  private _cellLockManager: ICellLockManager | null = null;
  private _previousActiveCell: Cell<ICellModel> | null = null;
  private _selectionMarkers: any[] = [];
  private _activeCellChanged = new Signal<this, Cell<ICellModel> | null>(this);
  private _selectionChanged = new Signal<this, void>(this);
  private _userPresenceChanged = new Signal<this, void>(this);
  private _cellLockChanged = new Signal<this, string>(this);
  private _commentChanged = new Signal<this, void>(this);
}

/**
 * A namespace for notebook panel statics.
 */
export namespace NotebookPanel {
  /**
   * An options interface for notebook panels.
   */
  export interface IOptions {
    /**
     * The rendermime instance used by the panel.
     */
    rendermime: IRenderMimeRegistry;

    /**
     * The content factory for the panel.
     */
    contentFactory: StaticNotebook.IContentFactory;

    /**
     * The service used to look up mime types.
     */
    mimeTypeService: CodeEditor.IMimeTypeService;

    /**
     * The document context for the notebook.
     */
    context: DocumentRegistry.IContext<NotebookModel>;

    /**
     * The application language translator.
     */
    translator?: ITranslator;

    /**
     * The collaboration provider for real-time updates.
     */
    collaborationProvider?: ICollaborationProvider;

    /**
     * The presence tracker for user awareness.
     */
    presenceTracker?: IPresenceTracker;

    /**
     * The permission manager for access control.
     */
    permissionManager?: IPermissionManager;

    /**
     * The comment manager for discussion threads.
     */
    commentManager?: ICommentManager;

    /**
     * The version history manager for document history.
     */
    versionHistory?: IVersionHistory;

    /**
     * The cell lock manager for preventing editing conflicts.
     */
    cellLockManager?: ICellLockManager;
  }

  /**
   * A content factory interface for NotebookPanel.
   */
  export interface IContentFactory extends StaticNotebook.IContentFactory {}

  /**
   * The default implementation of an `IContentFactory`.
   */
  export class ContentFactory extends StaticNotebook.ContentFactory {}
}

/**
 * A namespace for private data.
 */
namespace Private {
  /**
   * An attached property for the selected state of a cell.
   */
  export const selectedProperty = new AttachedProperty<Cell, boolean>({
    name: 'selected',
    create: () => false
  });
}
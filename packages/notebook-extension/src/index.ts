// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin,
  ILabShell,
  ILayoutRestorer,
  IRouter
} from '@jupyterlab/application';

import {
  ISessionContext,
  DOMUtils,
  IToolbarWidgetRegistry,
  ICommandPalette,
  Dialog,
  showDialog,
  WidgetTracker,
  ReactWidget
} from '@jupyterlab/apputils';

import { Cell, CodeCell } from '@jupyterlab/cells';

import { PageConfig, Text, Time, URLExt } from '@jupyterlab/coreutils';

import { IDocumentManager } from '@jupyterlab/docmanager';

import { IMainMenu } from '@jupyterlab/mainmenu';

import {
  NotebookPanel,
  INotebookTracker,
  INotebookTools,
} from '@jupyterlab/notebook';

import { ISettingRegistry } from '@jupyterlab/settingregistry';

import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import { INotebookShell } from '@jupyter-notebook/application';

import { Poll } from '@lumino/polling';

import { Widget } from '@lumino/widgets';

import { TrustedComponent } from './trusted';

// Import collaboration components
import { CollaborationBar } from './components/collaborationBar';
import { UserPresence } from './components/userPresence';
import { CellLockIndicator } from './components/cellLockIndicator';
import { HistoryViewer } from './components/historyViewer';
import { PermissionsDialog } from './components/permissionsDialog';
import { CommentSystem } from './components/commentSystem';

// Import Yjs and related libraries
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { awareness } from 'y-protocols/awareness';

// Define token interfaces for collaboration services
import { Token } from '@lumino/coreutils';

/**
 * The token for the collaboration service.
 */
export const ICollaborationService = new Token<ICollaborationService>(
  'jupyter-notebook/collaboration:ICollaborationService'
);

/**
 * The interface for the collaboration service.
 */
export interface ICollaborationService {
  /**
   * Whether collaboration is enabled.
   */
  readonly enabled: boolean;

  /**
   * Whether the document is currently connected to the collaboration server.
   */
  readonly connected: boolean;

  /**
   * The Yjs document provider.
   */
  readonly provider: WebsocketProvider | null;

  /**
   * The Yjs document.
   */
  readonly document: Y.Doc | null;

  /**
   * Initialize the collaboration service.
   */
  initialize(): void;

  /**
   * Toggle collaboration on/off.
   */
  toggleCollaboration(): Promise<boolean>;

  /**
   * Connect to the collaboration server.
   */
  connect(): Promise<boolean>;

  /**
   * Disconnect from the collaboration server.
   */
  disconnect(): Promise<void>;
}

/**
 * The token for the presence service.
 */
export const IPresenceService = new Token<IPresenceService>(
  'jupyter-notebook/collaboration:IPresenceService'
);

/**
 * The interface for the presence service.
 */
export interface IPresenceService {
  /**
   * Whether presence features are enabled.
   */
  readonly enabled: boolean;

  /**
   * The list of active users.
   */
  readonly users: ReadonlyArray<ICollaborator>;

  /**
   * The current user's information.
   */
  readonly localUser: ICollaborator;

  /**
   * Update the current user's cursor position.
   */
  updateCursor(position: ICursorPosition): void;

  /**
   * Update the current user's selection range.
   */
  updateSelection(selection: ISelectionRange): void;

  /**
   * Update the current user's active cell.
   */
  updateActiveCell(cellId: string): void;
}

/**
 * The token for the lock service.
 */
export const ILockService = new Token<ILockService>(
  'jupyter-notebook/collaboration:ILockService'
);

/**
 * The interface for the lock service.
 */
export interface ILockService {
  /**
   * Whether cell locking is enabled.
   */
  readonly enabled: boolean;

  /**
   * The list of currently locked cells.
   */
  readonly lockedCells: ReadonlyMap<string, ILock>;

  /**
   * Acquire a lock on a cell.
   */
  acquireLock(cellId: string): Promise<boolean>;

  /**
   * Release a lock on a cell.
   */
  releaseLock(cellId: string): Promise<boolean>;

  /**
   * Check if a cell is locked by the current user.
   */
  isLockedByMe(cellId: string): boolean;

  /**
   * Check if a cell is locked by another user.
   */
  isLockedByOther(cellId: string): boolean;

  /**
   * Get the lock information for a cell.
   */
  getLock(cellId: string): ILock | null;
}

/**
 * The token for the history service.
 */
export const IHistoryService = new Token<IHistoryService>(
  'jupyter-notebook/collaboration:IHistoryService'
);

/**
 * The interface for the history service.
 */
export interface IHistoryService {
  /**
   * Whether version history is enabled.
   */
  readonly enabled: boolean;

  /**
   * The list of available versions.
   */
  readonly versions: ReadonlyArray<IVersion>;

  /**
   * Get the changes between two versions.
   */
  getDiff(fromVersion: string, toVersion: string): Promise<IDiff>;

  /**
   * Restore the document to a specific version.
   */
  restore(version: string): Promise<boolean>;

  /**
   * Create a new snapshot of the current document state.
   */
  createSnapshot(name?: string): Promise<IVersion>;
}

/**
 * The token for the permissions service.
 */
export const IPermissionsService = new Token<IPermissionsService>(
  'jupyter-notebook/collaboration:IPermissionsService'
);

/**
 * The interface for the permissions service.
 */
export interface IPermissionsService {
  /**
   * Whether permissions are enabled.
   */
  readonly enabled: boolean;

  /**
   * The current user's role.
   */
  readonly currentRole: string;

  /**
   * The list of users with their roles.
   */
  readonly userRoles: ReadonlyMap<string, string>;

  /**
   * Check if the current user has a specific permission.
   */
  hasPermission(permission: string): boolean;

  /**
   * Set a user's role.
   */
  setUserRole(userId: string, role: string): Promise<boolean>;

  /**
   * Get the available roles.
   */
  getRoles(): ReadonlyArray<IRole>;
}

/**
 * The token for the comment service.
 */
export const ICommentService = new Token<ICommentService>(
  'jupyter-notebook/collaboration:ICommentService'
);

/**
 * The interface for the comment service.
 */
export interface ICommentService {
  /**
   * Whether comments are enabled.
   */
  readonly enabled: boolean;

  /**
   * The list of comments for the current document.
   */
  readonly comments: ReadonlyArray<IComment>;

  /**
   * Add a comment to a cell.
   */
  addComment(cellId: string, text: string, range?: ISelectionRange): Promise<IComment>;

  /**
   * Reply to a comment.
   */
  replyToComment(commentId: string, text: string): Promise<IComment>;

  /**
   * Resolve a comment.
   */
  resolveComment(commentId: string): Promise<boolean>;

  /**
   * Delete a comment.
   */
  deleteComment(commentId: string): Promise<boolean>;

  /**
   * Get comments for a specific cell.
   */
  getCommentsForCell(cellId: string): ReadonlyArray<IComment>;
}

/**
 * Interface for a collaborator.
 */
export interface ICollaborator {
  /**
   * The user's ID.
   */
  readonly id: string;

  /**
   * The user's name.
   */
  readonly name: string;

  /**
   * The user's color.
   */
  readonly color: string;

  /**
   * The user's avatar URL.
   */
  readonly avatarUrl?: string;

  /**
   * The user's cursor position.
   */
  readonly cursor?: ICursorPosition;

  /**
   * The user's selection range.
   */
  readonly selection?: ISelectionRange;

  /**
   * The ID of the user's active cell.
   */
  readonly activeCell?: string;

  /**
   * The user's last activity timestamp.
   */
  readonly lastActivity: number;
}

/**
 * Interface for a cursor position.
 */
export interface ICursorPosition {
  /**
   * The cell ID.
   */
  readonly cellId: string;

  /**
   * The line number.
   */
  readonly line: number;

  /**
   * The column number.
   */
  readonly column: number;
}

/**
 * Interface for a selection range.
 */
export interface ISelectionRange {
  /**
   * The cell ID.
   */
  readonly cellId: string;

  /**
   * The start line number.
   */
  readonly startLine: number;

  /**
   * The start column number.
   */
  readonly startColumn: number;

  /**
   * The end line number.
   */
  readonly endLine: number;

  /**
   * The end column number.
   */
  readonly endColumn: number;
}

/**
 * Interface for a cell lock.
 */
export interface ILock {
  /**
   * The cell ID.
   */
  readonly cellId: string;

  /**
   * The user who holds the lock.
   */
  readonly userId: string;

  /**
   * The timestamp when the lock was acquired.
   */
  readonly timestamp: number;

  /**
   * The lock expiration time in milliseconds.
   */
  readonly expiresIn: number;
}

/**
 * Interface for a document version.
 */
export interface IVersion {
  /**
   * The version ID.
   */
  readonly id: string;

  /**
   * The user who created the version.
   */
  readonly userId: string;

  /**
   * The timestamp when the version was created.
   */
  readonly timestamp: number;

  /**
   * The version name.
   */
  readonly name?: string;
}

/**
 * Interface for a diff between two versions.
 */
export interface IDiff {
  /**
   * The from version ID.
   */
  readonly fromVersion: string;

  /**
   * The to version ID.
   */
  readonly toVersion: string;

  /**
   * The list of changes.
   */
  readonly changes: ReadonlyArray<IChange>;
}

/**
 * Interface for a change in a diff.
 */
export interface IChange {
  /**
   * The type of change.
   */
  readonly type: 'add' | 'remove' | 'modify';

  /**
   * The cell ID.
   */
  readonly cellId: string;

  /**
   * The user who made the change.
   */
  readonly userId: string;

  /**
   * The timestamp when the change was made.
   */
  readonly timestamp: number;

  /**
   * The old content (for remove and modify).
   */
  readonly oldContent?: string;

  /**
   * The new content (for add and modify).
   */
  readonly newContent?: string;
}

/**
 * Interface for a role in the permissions system.
 */
export interface IRole {
  /**
   * The role ID.
   */
  readonly id: string;

  /**
   * The role name.
   */
  readonly name: string;

  /**
   * The role description.
   */
  readonly description: string;

  /**
   * The role permissions.
   */
  readonly permissions: ReadonlyArray<string>;
}

/**
 * Interface for a comment.
 */
export interface IComment {
  /**
   * The comment ID.
   */
  readonly id: string;

  /**
   * The cell ID.
   */
  readonly cellId: string;

  /**
   * The user who created the comment.
   */
  readonly userId: string;

  /**
   * The timestamp when the comment was created.
   */
  readonly timestamp: number;

  /**
   * The comment text.
   */
  readonly text: string;

  /**
   * The selection range (optional).
   */
  readonly range?: ISelectionRange;

  /**
   * The parent comment ID (for replies).
   */
  readonly parentId?: string;

  /**
   * Whether the comment is resolved.
   */
  readonly resolved: boolean;

  /**
   * The user who resolved the comment.
   */
  readonly resolvedBy?: string;

  /**
   * The timestamp when the comment was resolved.
   */
  readonly resolvedAt?: number;

  /**
   * The list of replies to this comment.
   */
  readonly replies: ReadonlyArray<IComment>;
}

/**
 * The class for kernel status errors.
 */
const KERNEL_STATUS_ERROR_CLASS = 'jp-NotebookKernelStatus-error';

/**
 * The class for kernel status warnings.
 */
const KERNEL_STATUS_WARN_CLASS = 'jp-NotebookKernelStatus-warn';

/**
 * The class for kernel status infos.
 */
const KERNEL_STATUS_INFO_CLASS = 'jp-NotebookKernelStatus-info';

/**
 * The class to fade out the kernel status.
 */
const KERNEL_STATUS_FADE_OUT_CLASS = 'jp-NotebookKernelStatus-fade';

/**
 * The class for scrolled outputs
 */
const SCROLLED_OUTPUTS_CLASS = 'jp-mod-outputsScrolled';

/**
 * The class for the full width notebook
 */
const FULL_WIDTH_NOTEBOOK_CLASS = 'jp-mod-fullwidth';

/**
 * The command IDs used by the notebook plugins.
 */
namespace CommandIDs {
  /**
   * A command to open right sidebar for Editing Notebook Metadata
   */
  export const openEditNotebookMetadata = 'notebook:edit-metadata';

  /**
   * A command to toggle full width of the notebook
   */
  export const toggleFullWidth = 'notebook:toggle-full-width';

  /**
   * A command to toggle collaboration features
   */
  export const toggleCollaboration = 'notebook:toggle-collaboration';

  /**
   * A command to show the collaboration sidebar
   */
  export const showCollaborationSidebar = 'notebook:show-collaboration-sidebar';

  /**
   * A command to show the permissions dialog
   */
  export const showPermissionsDialog = 'notebook:show-permissions-dialog';

  /**
   * A command to show the history viewer
   */
  export const showHistoryViewer = 'notebook:show-history-viewer';

  /**
   * A command to add a comment to the current cell
   */
  export const addComment = 'notebook:add-comment';

  /**
   * A command to toggle cell locking
   */
  export const toggleCellLock = 'notebook:toggle-cell-lock';
}

/**
 * A plugin for the checkpoint indicator
 */
const checkpoints: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:checkpoints',
  description: 'A plugin for the checkpoint indicator.',
  autoStart: true,
  requires: [IDocumentManager, ITranslator],
  optional: [INotebookShell, IToolbarWidgetRegistry],
  activate: (
    app: JupyterFrontEnd,
    docManager: IDocumentManager,
    translator: ITranslator,
    notebookShell: INotebookShell | null,
    toolbarRegistry: IToolbarWidgetRegistry | null
  ) => {
    const { shell } = app;
    const trans = translator.load('notebook');
    const node = document.createElement('div');

    if (toolbarRegistry) {
      toolbarRegistry.addFactory('TopBar', 'checkpoint', (toolbar) => {
        const widget = new Widget({ node });
        widget.id = DOMUtils.createDomID();
        widget.addClass('jp-NotebookCheckpoint');
        return widget;
      });
    }

    const onChange = async () => {
      const current = shell.currentWidget;
      if (!current) {
        return;
      }
      const context = docManager.contextForWidget(current);

      context?.fileChanged.disconnect(onChange);
      context?.fileChanged.connect(onChange);

      const checkpoints = await context?.listCheckpoints();
      if (!checkpoints || !checkpoints.length) {
        return;
      }
      const checkpoint = checkpoints[checkpoints.length - 1];
      node.textContent = trans.__(
        'Last Checkpoint: %1',
        Time.formatHuman(new Date(checkpoint.last_modified))
      );
    };

    if (notebookShell) {
      notebookShell.currentChanged.connect(onChange);
    }

    new Poll({
      auto: true,
      factory: () => onChange(),
      frequency: {
        interval: 2000,
        backoff: false,
      },
      standby: 'when-hidden',
    });
  },
};

/**
 * Add a command to close the browser tab when clicking on "Close and Shut Down"
 */
const closeTab: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:close-tab',
  description:
    'Add a command to close the browser tab when clicking on "Close and Shut Down".',
  autoStart: true,
  requires: [IMainMenu],
  optional: [ITranslator],
  activate: (
    app: JupyterFrontEnd,
    menu: IMainMenu,
    translator: ITranslator | null
  ) => {
    const { commands } = app;
    translator = translator ?? nullTranslator;
    const trans = translator.load('notebook');

    const id = 'notebook:close-and-halt';
    commands.addCommand(id, {
      label: trans.__('Close and Shut Down Notebook'),
      execute: async () => {
        // Shut the kernel down, without confirmation
        await commands.execute('notebook:shutdown-kernel', { activate: false });
        window.close();
      },
    });
    menu.fileMenu.closeAndCleaners.add({
      id,
      // use a small rank to it takes precedence over the default
      // shut down action for the notebook
      rank: 0,
    });
  },
};

/**
 * Add a command to open the tree view from the notebook view
 */
const openTreeTab: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:open-tree-tab',
  description:
    'Add a command to open a browser tab on the tree view when clicking "Open...".',
  autoStart: true,
  optional: [ITranslator],
  activate: (app: JupyterFrontEnd, translator: ITranslator | null) => {
    const { commands } = app;
    translator = translator ?? nullTranslator;
    const trans = translator.load('notebook');

    const id = 'notebook:open-tree-tab';
    commands.addCommand(id, {
      label: trans.__('Open\u2026'),
      execute: async () => {
        const url = URLExt.join(PageConfig.getBaseUrl(), 'tree');
        window.open(url);
      },
    });
  },
};

/**
 * A plugin to set the notebook to full width.
 */
const fullWidthNotebook: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:full-width-notebook',
  description: 'A plugin to set the notebook to full width.',
  autoStart: true,
  requires: [INotebookTracker],
  optional: [ICommandPalette, ISettingRegistry, ITranslator],
  activate: (
    app: JupyterFrontEnd,
    tracker: INotebookTracker,
    palette: ICommandPalette | null,
    settingRegistry: ISettingRegistry | null,
    translator: ITranslator | null
  ) => {
    const trans = (translator ?? nullTranslator).load('notebook');

    let fullWidth = false;

    const toggleFullWidth = () => {
      const current = tracker.currentWidget;
      fullWidth = !fullWidth;
      if (!current) {
        return;
      }
      const content = current;
      content.toggleClass(FULL_WIDTH_NOTEBOOK_CLASS, fullWidth);
    };

    let notebookSettings: ISettingRegistry.ISettings;

    if (settingRegistry) {
      const loadSettings = settingRegistry.load(fullWidthNotebook.id);

      const updateSettings = (settings: ISettingRegistry.ISettings): void => {
        const newFullWidth = settings.get('fullWidthNotebook')
          .composite as boolean;
        if (newFullWidth !== fullWidth) {
          toggleFullWidth();
        }
      };

      Promise.all([loadSettings, app.restored])
        .then(([settings]) => {
          notebookSettings = settings;
          updateSettings(settings);
          settings.changed.connect((settings) => {
            updateSettings(settings);
          });
        })
        .catch((reason: Error) => {
          console.error(reason.message);
        });
    }

    app.commands.addCommand(CommandIDs.toggleFullWidth, {
      label: trans.__('Enable Full Width Notebook'),
      execute: () => {
        toggleFullWidth();
        if (notebookSettings) {
          notebookSettings.set('fullWidthNotebook', fullWidth);
        }
      },
      isEnabled: () => tracker.currentWidget !== null,
      isToggled: () => fullWidth,
    });

    if (palette) {
      palette.addItem({
        command: CommandIDs.toggleFullWidth,
        category: 'Notebook Operations',
      });
    }
  },
};

/**
 * The kernel logo plugin.
 */
const kernelLogo: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:kernel-logo',
  description: 'The kernel logo plugin.',
  autoStart: true,
  requires: [INotebookShell],
  optional: [IToolbarWidgetRegistry],
  activate: (
    app: JupyterFrontEnd,
    shell: INotebookShell,
    toolbarRegistry: IToolbarWidgetRegistry | null
  ) => {
    const { serviceManager } = app;

    const node = document.createElement('div');
    const img = document.createElement('img');

    const onChange = async () => {
      const current = shell.currentWidget;
      if (!(current instanceof NotebookPanel)) {
        return;
      }

      if (!node.hasChildNodes()) {
        node.appendChild(img);
      }

      await current.sessionContext.ready;
      current.sessionContext.kernelChanged.disconnect(onChange);
      current.sessionContext.kernelChanged.connect(onChange);

      const name = current.sessionContext.session?.kernel?.name ?? '';
      const spec = serviceManager.kernelspecs?.specs?.kernelspecs[name];
      if (!spec) {
        node.childNodes[0].remove();
        return;
      }

      const kernelIconUrl = spec.resources['logo-64x64'];
      if (!kernelIconUrl) {
        node.childNodes[0].remove();
        return;
      }

      img.src = kernelIconUrl;
      img.title = spec.display_name;
    };

    if (toolbarRegistry) {
      toolbarRegistry.addFactory('TopBar', 'kernelLogo', (toolbar) => {
        const widget = new Widget({ node });
        widget.addClass('jp-NotebookKernelLogo');
        return widget;
      });
    }

    app.started.then(() => {
      shell.currentChanged.connect(onChange);
    });
  },
};

/**
 * A plugin to display the kernel status;
 */
const kernelStatus: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:kernel-status',
  description: 'A plugin to display the kernel status.',
  autoStart: true,
  requires: [INotebookShell, ITranslator],
  activate: (
    app: JupyterFrontEnd,
    shell: INotebookShell,
    translator: ITranslator
  ) => {
    const trans = translator.load('notebook');
    const widget = new Widget();
    widget.addClass('jp-NotebookKernelStatus');
    app.shell.add(widget, 'menu', { rank: 10_010 });

    const removeClasses = () => {
      widget.removeClass(KERNEL_STATUS_ERROR_CLASS);
      widget.removeClass(KERNEL_STATUS_WARN_CLASS);
      widget.removeClass(KERNEL_STATUS_INFO_CLASS);
      widget.removeClass(KERNEL_STATUS_FADE_OUT_CLASS);
    };

    const onStatusChanged = (sessionContext: ISessionContext) => {
      const status = sessionContext.kernelDisplayStatus;
      let text = `Kernel ${Text.titleCase(status)}`;
      removeClasses();
      switch (status) {
        case 'busy':
        case 'idle':
          text = '';
          widget.addClass(KERNEL_STATUS_FADE_OUT_CLASS);
          break;
        case 'dead':
        case 'terminating':
          widget.addClass(KERNEL_STATUS_ERROR_CLASS);
          break;
        case 'unknown':
          widget.addClass(KERNEL_STATUS_WARN_CLASS);
          break;
        default:
          widget.addClass(KERNEL_STATUS_INFO_CLASS);
          widget.addClass(KERNEL_STATUS_FADE_OUT_CLASS);
          break;
      }
      widget.node.textContent = trans.__(text);
    };

    const onChange = async () => {
      const current = shell.currentWidget;
      if (!(current instanceof NotebookPanel)) {
        return;
      }
      const sessionContext = current.sessionContext;
      sessionContext.statusChanged.connect(onStatusChanged);
    };

    shell.currentChanged.connect(onChange);
  },
};

/**
 * A plugin to enable scrolling for outputs by default.
 * Mimic the logic from the classic notebook, as found here:
 * https://github.com/jupyter/notebook/blob/a9a31c096eeffe1bff4e9164c6a0442e0e13cdb3/notebook/static/notebook/js/outputarea.js#L96-L120
 */
const scrollOutput: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:scroll-output',
  description: 'A plugin to enable scrolling for outputs by default.',
  autoStart: true,
  requires: [INotebookTracker],
  optional: [ISettingRegistry],
  activate: async (
    app: JupyterFrontEnd,
    tracker: INotebookTracker,
    settingRegistry: ISettingRegistry | null
  ) => {
    const autoScrollThreshold = 100;
    let autoScrollOutputs = true;

    // decide whether to scroll the output of the cell based on some heuristics
    const autoScroll = (cell: CodeCell) => {
      if (!autoScrollOutputs) {
        // bail if disabled via the settings
        cell.removeClass(SCROLLED_OUTPUTS_CLASS);
        return;
      }
      const { outputArea } = cell;
      // respect cells with an explicit scrolled state
      const scrolled = cell.model.getMetadata('scrolled');
      if (scrolled !== undefined) {
        return;
      }
      const { node } = outputArea;
      const height = node.scrollHeight;
      const fontSize = parseFloat(node.style.fontSize.replace('px', ''));
      const lineHeight = (fontSize || 14) * 1.3;
      // do not set via cell.outputScrolled = true, as this would
      // otherwise synchronize the scrolled state to the notebook metadata
      const scroll = height > lineHeight * autoScrollThreshold;
      cell.toggleClass(SCROLLED_OUTPUTS_CLASS, scroll);
    };

    const handlers: { [id: string]: () => void } = {};

    const setAutoScroll = (cell: Cell) => {
      if (cell.model.type === 'code') {
        const codeCell = cell as CodeCell;
        const id = codeCell.model.id;
        autoScroll(codeCell);
        if (handlers[id]) {
          codeCell.outputArea.model.changed.disconnect(handlers[id]);
        }
        handlers[id] = () => autoScroll(codeCell);
        codeCell.outputArea.model.changed.connect(handlers[id]);
      }
    };

    tracker.widgetAdded.connect((sender, notebook) => {
      // when the notebook widget is created, process all the cells
      notebook.sessionContext.ready.then(() => {
        notebook.content.widgets.forEach(setAutoScroll);
      });

      notebook.model?.cells.changed.connect((sender, args) => {
        notebook.content.widgets.forEach(setAutoScroll);
      });
    });

    if (settingRegistry) {
      const loadSettings = settingRegistry.load(scrollOutput.id);
      const updateSettings = (settings: ISettingRegistry.ISettings): void => {
        autoScrollOutputs = settings.get('autoScrollOutputs')
          .composite as boolean;
      };

      Promise.all([loadSettings, app.restored])
        .then(([settings]) => {
          updateSettings(settings);
          settings.changed.connect((settings) => {
            updateSettings(settings);
          });
        })
        .catch((reason: Error) => {
          console.error(reason.message);
        });
    }
  },
};

/**
 * A plugin to add the NotebookTools to the side panel;
 */
const notebookToolsWidget: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:notebook-tools',
  description: 'A plugin to add the NotebookTools to the side panel.',
  autoStart: true,
  requires: [INotebookShell],
  optional: [INotebookTools],
  activate: (
    app: JupyterFrontEnd,
    shell: INotebookShell,
    notebookTools: INotebookTools | null
  ) => {
    const onChange = async () => {
      const current = shell.currentWidget;
      if (!(current instanceof NotebookPanel)) {
        return;
      }

      // Add the notebook tools in right area.
      if (notebookTools) {
        shell.add(notebookTools, 'right', { type: 'Property Inspector' });
      }
    };
    shell.currentChanged.connect(onChange);
  },
};

/**
 * A plugin to update the tab icon based on the kernel status.
 */
const tabIcon: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:tab-icon',
  description: 'A plugin to update the tab icon based on the kernel status.',
  autoStart: true,
  requires: [INotebookTracker],
  activate: (app: JupyterFrontEnd, tracker: INotebookTracker) => {
    // the favicons are provided by Jupyter Server
    const baseURL = PageConfig.getBaseUrl();
    const notebookIcon = URLExt.join(
      baseURL,
      'static/favicons/favicon-notebook.ico'
    );
    const busyIcon = URLExt.join(baseURL, 'static/favicons/favicon-busy-1.ico');

    const updateBrowserFavicon = (
      status: ISessionContext.KernelDisplayStatus
    ) => {
      const link = document.querySelector(
        "link[rel*='icon']"
      ) as HTMLLinkElement;
      switch (status) {
        case 'busy':
          link.href = busyIcon;
          break;
        case 'idle':
          link.href = notebookIcon;
          break;
      }
    };

    const onChange = async () => {
      const current = tracker.currentWidget;
      const sessionContext = current?.sessionContext;
      if (!sessionContext) {
        return;
      }

      sessionContext.statusChanged.connect(() => {
        const status = sessionContext.kernelDisplayStatus;
        updateBrowserFavicon(status);
      });
    };

    tracker.currentChanged.connect(onChange);
  },
};

/**
 * A plugin that adds a Trusted indicator to the menu area
 */
const trusted: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:trusted',
  description: 'A plugin that adds a Trusted indicator to the menu area.',
  autoStart: true,
  requires: [INotebookShell, ITranslator],
  activate: (
    app: JupyterFrontEnd,
    notebookShell: INotebookShell,
    translator: ITranslator
  ): void => {
    const onChange = async () => {
      const current = notebookShell.currentWidget;
      if (!(current instanceof NotebookPanel)) {
        return;
      }

      const notebook = current.content;
      await current.context.ready;

      const widget = TrustedComponent.create({ notebook, translator });
      notebookShell.add(widget, 'menu', {
        rank: 11_000,
      });
    };

    notebookShell.currentChanged.connect(onChange);
  },
};

/**
 * Add a command to open right sidebar for Editing Notebook Metadata when clicking on "Edit Notebook Metadata" under Edit menu
 */
const editNotebookMetadata: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:edit-notebook-metadata',
  description:
    'Add a command to open right sidebar for Editing Notebook Metadata when clicking on "Edit Notebook Metadata" under Edit menu',
  autoStart: true,
  optional: [ICommandPalette, ITranslator, INotebookTools],
  activate: (
    app: JupyterFrontEnd,
    palette: ICommandPalette | null,
    translator: ITranslator | null,
    notebookTools: INotebookTools | null
  ) => {
    const { commands, shell } = app;
    translator = translator ?? nullTranslator;
    const trans = translator.load('notebook');

    commands.addCommand(CommandIDs.openEditNotebookMetadata, {
      label: trans.__('Edit Notebook Metadata'),
      execute: async () => {
        const command = 'application:toggle-panel';
        const args = {
          side: 'right',
          title: 'Show Notebook Tools',
          id: 'notebook-tools',
        };

        // Check if Show Notebook Tools (Right Sidebar) is open (expanded)
        if (!commands.isToggled(command, args)) {
          await commands.execute(command, args).then((_) => {
            // For expanding the 'Advanced Tools' section (default: collapsed)
            if (notebookTools) {
              const tools = (notebookTools?.layout as any).widgets;
              tools.forEach((tool: any) => {
                if (
                  tool.widget.title.label === trans.__('Advanced Tools') &&
                  tool.collapsed
                ) {
                  tool.toggle();
                }
              });
            }
          });
        }
      },
      isVisible: () =>
        shell.currentWidget !== null &&
        shell.currentWidget instanceof NotebookPanel,
    });

    if (palette) {
      palette.addItem({
        command: CommandIDs.openEditNotebookMetadata,
        category: 'Notebook Operations',
      });
    }
  },
};

/**
 * A plugin that provides the core collaboration service.
 */
const collaborationCore: JupyterFrontEndPlugin<ICollaborationService> = {
  id: '@jupyter-notebook/notebook-extension:collaboration-core',
  description: 'A plugin that provides the core collaboration service.',
  autoStart: true,
  requires: [INotebookShell, ITranslator, INotebookTracker],
  optional: [ICommandPalette, ISettingRegistry, IToolbarWidgetRegistry],
  provides: ICollaborationService,
  activate: (
    app: JupyterFrontEnd,
    shell: INotebookShell,
    translator: ITranslator,
    tracker: INotebookTracker,
    palette: ICommandPalette | null,
    settingRegistry: ISettingRegistry | null,
    toolbarRegistry: IToolbarWidgetRegistry | null
  ): ICollaborationService => {
    const trans = translator.load('notebook');
    const { commands } = app;

    // Create a class that implements the ICollaborationService interface
    class CollaborationService implements ICollaborationService {
      private _enabled = true;
      private _connected = false;
      private _provider: WebsocketProvider | null = null;
      private _document: Y.Doc | null = null;

      constructor() {
        // Initialize the service
      }

      get enabled(): boolean {
        return this._enabled;
      }

      get connected(): boolean {
        return this._connected;
      }

      get provider(): WebsocketProvider | null {
        return this._provider;
      }

      get document(): Y.Doc | null {
        return this._document;
      }

      initialize(): void {
        // Initialize the collaboration service
        console.log('Initializing collaboration service');
      }

      async toggleCollaboration(): Promise<boolean> {
        this._enabled = !this._enabled;
        if (this._enabled) {
          return this.connect();
        } else {
          await this.disconnect();
          return false;
        }
      }

      async connect(): Promise<boolean> {
        // Connect to the collaboration server
        console.log('Connecting to collaboration server');
        this._connected = true;
        return true;
      }

      async disconnect(): Promise<void> {
        // Disconnect from the collaboration server
        console.log('Disconnecting from collaboration server');
        this._connected = false;
      }
    }

    // Create an instance of the service
    const service = new CollaborationService();

    // Register commands
    commands.addCommand(CommandIDs.toggleCollaboration, {
      label: trans.__('Toggle Collaboration'),
      execute: () => service.toggleCollaboration(),
      isEnabled: () => tracker.currentWidget !== null,
      isToggled: () => service.enabled && service.connected
    });

    commands.addCommand(CommandIDs.showCollaborationSidebar, {
      label: trans.__('Show Collaboration Sidebar'),
      execute: () => {
        const command = 'application:toggle-panel';
        const args = {
          side: 'right',
          title: 'Collaboration',
          id: 'collaboration-sidebar'
        };
        return commands.execute(command, args);
      },
      isEnabled: () => tracker.currentWidget !== null && service.enabled
    });

    // Add to command palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.toggleCollaboration,
        category: 'Collaboration'
      });
      palette.addItem({
        command: CommandIDs.showCollaborationSidebar,
        category: 'Collaboration'
      });
    }

    // Add collaboration status to toolbar
    if (toolbarRegistry) {
      toolbarRegistry.addFactory('TopBar', 'collaboration', (toolbar) => {
        const collaborationBarWidget = ReactWidget.create(
          <CollaborationBar 
            collaborationService={service}
            translator={translator}
          />
        );
        collaborationBarWidget.addClass('jp-NotebookCollaborationBar');
        return collaborationBarWidget;
      });
    }

    // Load settings
    if (settingRegistry) {
      settingRegistry.load(collaborationCore.id)
        .then(settings => {
          // Apply settings
          const enabled = settings.get('enabled').composite as boolean;
          if (service.enabled !== enabled) {
            service.toggleCollaboration().catch(console.error);
          }

          // Listen for setting changes
          settings.changed.connect(() => {
            const newEnabled = settings.get('enabled').composite as boolean;
            if (service.enabled !== newEnabled) {
              service.toggleCollaboration().catch(console.error);
            }
          });
        })
        .catch(console.error);
    }

    // Initialize the service
    service.initialize();

    return service;
  }
};

/**
 * A plugin that provides the presence service for collaboration.
 */
const presencePlugin: JupyterFrontEndPlugin<IPresenceService> = {
  id: '@jupyter-notebook/notebook-extension:collaboration-presence',
  description: 'A plugin that provides the presence service for collaboration.',
  autoStart: true,
  requires: [ICollaborationService, INotebookTracker, ITranslator],
  optional: [ISettingRegistry],
  provides: IPresenceService,
  activate: (
    app: JupyterFrontEnd,
    collaborationService: ICollaborationService,
    tracker: INotebookTracker,
    translator: ITranslator,
    settingRegistry: ISettingRegistry | null
  ): IPresenceService => {
    const trans = translator.load('notebook');

    // Create a class that implements the IPresenceService interface
    class PresenceService implements IPresenceService {
      private _enabled = true;
      private _users: ICollaborator[] = [];
      private _localUser: ICollaborator;

      constructor() {
        // Create a local user
        this._localUser = {
          id: 'local-user',
          name: 'You',
          color: '#3498db',
          lastActivity: Date.now()
        };

        // Add the local user to the users list
        this._users.push(this._localUser);
      }

      get enabled(): boolean {
        return this._enabled && collaborationService.enabled && collaborationService.connected;
      }

      get users(): ReadonlyArray<ICollaborator> {
        return this._users;
      }

      get localUser(): ICollaborator {
        return this._localUser;
      }

      updateCursor(position: ICursorPosition): void {
        // Update the local user's cursor position
        console.log('Updating cursor position', position);
      }

      updateSelection(selection: ISelectionRange): void {
        // Update the local user's selection range
        console.log('Updating selection range', selection);
      }

      updateActiveCell(cellId: string): void {
        // Update the local user's active cell
        console.log('Updating active cell', cellId);
      }
    }

    // Create an instance of the service
    const service = new PresenceService();

    // Load settings
    if (settingRegistry) {
      settingRegistry.load(presencePlugin.id)
        .then(settings => {
          // Apply settings
          const enabled = settings.get('presence.enabled').composite as boolean;
          service['_enabled'] = enabled;

          // Listen for setting changes
          settings.changed.connect(() => {
            const newEnabled = settings.get('presence.enabled').composite as boolean;
            service['_enabled'] = newEnabled;
          });
        })
        .catch(console.error);
    }

    return service;
  }
};

/**
 * A plugin that provides the lock service for collaboration.
 */
const lockPlugin: JupyterFrontEndPlugin<ILockService> = {
  id: '@jupyter-notebook/notebook-extension:collaboration-locks',
  description: 'A plugin that provides the lock service for collaboration.',
  autoStart: true,
  requires: [ICollaborationService, INotebookTracker, ITranslator],
  optional: [ISettingRegistry, ICommandPalette],
  provides: ILockService,
  activate: (
    app: JupyterFrontEnd,
    collaborationService: ICollaborationService,
    tracker: INotebookTracker,
    translator: ITranslator,
    settingRegistry: ISettingRegistry | null,
    palette: ICommandPalette | null
  ): ILockService => {
    const trans = translator.load('notebook');
    const { commands } = app;

    // Create a class that implements the ILockService interface
    class LockService implements ILockService {
      private _enabled = true;
      private _lockedCells = new Map<string, ILock>();

      constructor() {
        // Initialize the service
      }

      get enabled(): boolean {
        return this._enabled && collaborationService.enabled && collaborationService.connected;
      }

      get lockedCells(): ReadonlyMap<string, ILock> {
        return this._lockedCells;
      }

      async acquireLock(cellId: string): Promise<boolean> {
        // Acquire a lock on a cell
        console.log('Acquiring lock on cell', cellId);
        if (!this.enabled) {
          return false;
        }

        // Check if the cell is already locked by another user
        if (this.isLockedByOther(cellId)) {
          return false;
        }

        // Create a lock
        const lock: ILock = {
          cellId,
          userId: 'local-user',
          timestamp: Date.now(),
          expiresIn: 5 * 60 * 1000 // 5 minutes
        };

        // Add the lock to the map
        this._lockedCells.set(cellId, lock);

        return true;
      }

      async releaseLock(cellId: string): Promise<boolean> {
        // Release a lock on a cell
        console.log('Releasing lock on cell', cellId);
        if (!this.enabled) {
          return false;
        }

        // Check if the cell is locked by the current user
        if (!this.isLockedByMe(cellId)) {
          return false;
        }

        // Remove the lock from the map
        this._lockedCells.delete(cellId);

        return true;
      }

      isLockedByMe(cellId: string): boolean {
        // Check if a cell is locked by the current user
        const lock = this._lockedCells.get(cellId);
        return !!lock && lock.userId === 'local-user';
      }

      isLockedByOther(cellId: string): boolean {
        // Check if a cell is locked by another user
        const lock = this._lockedCells.get(cellId);
        return !!lock && lock.userId !== 'local-user';
      }

      getLock(cellId: string): ILock | null {
        // Get the lock information for a cell
        return this._lockedCells.get(cellId) || null;
      }
    }

    // Create an instance of the service
    const service = new LockService();

    // Register commands
    commands.addCommand(CommandIDs.toggleCellLock, {
      label: trans.__('Toggle Cell Lock'),
      execute: async () => {
        const current = tracker.currentWidget;
        if (!current) {
          return;
        }

        const activeCell = current.content.activeCell;
        if (!activeCell) {
          return;
        }

        const cellId = activeCell.model.id;

        if (service.isLockedByMe(cellId)) {
          return service.releaseLock(cellId);
        } else {
          return service.acquireLock(cellId);
        }
      },
      isEnabled: () => tracker.currentWidget !== null && 
                     tracker.currentWidget.content.activeCell !== null && 
                     service.enabled,
      isToggled: () => {
        const current = tracker.currentWidget;
        if (!current) {
          return false;
        }

        const activeCell = current.content.activeCell;
        if (!activeCell) {
          return false;
        }

        return service.isLockedByMe(activeCell.model.id);
      }
    });

    // Add to command palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.toggleCellLock,
        category: 'Collaboration'
      });
    }

    // Load settings
    if (settingRegistry) {
      settingRegistry.load(lockPlugin.id)
        .then(settings => {
          // Apply settings
          const enabled = settings.get('locks.enabled').composite as boolean;
          service['_enabled'] = enabled;

          // Listen for setting changes
          settings.changed.connect(() => {
            const newEnabled = settings.get('locks.enabled').composite as boolean;
            service['_enabled'] = newEnabled;
          });
        })
        .catch(console.error);
    }

    return service;
  }
};

/**
 * A plugin that provides the history service for collaboration.
 */
const historyPlugin: JupyterFrontEndPlugin<IHistoryService> = {
  id: '@jupyter-notebook/notebook-extension:collaboration-history',
  description: 'A plugin that provides the history service for collaboration.',
  autoStart: true,
  requires: [ICollaborationService, INotebookTracker, ITranslator],
  optional: [ISettingRegistry, ICommandPalette],
  provides: IHistoryService,
  activate: (
    app: JupyterFrontEnd,
    collaborationService: ICollaborationService,
    tracker: INotebookTracker,
    translator: ITranslator,
    settingRegistry: ISettingRegistry | null,
    palette: ICommandPalette | null
  ): IHistoryService => {
    const trans = translator.load('notebook');
    const { commands } = app;

    // Create a class that implements the IHistoryService interface
    class HistoryService implements IHistoryService {
      private _enabled = true;
      private _versions: IVersion[] = [];

      constructor() {
        // Initialize with a single version
        this._versions.push({
          id: 'initial',
          userId: 'system',
          timestamp: Date.now(),
          name: 'Initial Version'
        });
      }

      get enabled(): boolean {
        return this._enabled && collaborationService.enabled && collaborationService.connected;
      }

      get versions(): ReadonlyArray<IVersion> {
        return this._versions;
      }

      async getDiff(fromVersion: string, toVersion: string): Promise<IDiff> {
        // Get the changes between two versions
        console.log('Getting diff between versions', fromVersion, toVersion);

        // Return an empty diff for now
        return {
          fromVersion,
          toVersion,
          changes: []
        };
      }

      async restore(version: string): Promise<boolean> {
        // Restore the document to a specific version
        console.log('Restoring to version', version);
        return true;
      }

      async createSnapshot(name?: string): Promise<IVersion> {
        // Create a new snapshot of the current document state
        console.log('Creating snapshot', name);

        const version: IVersion = {
          id: `snapshot-${Date.now()}`,
          userId: 'local-user',
          timestamp: Date.now(),
          name: name || `Snapshot ${this._versions.length}`
        };

        this._versions.push(version);

        return version;
      }
    }

    // Create an instance of the service
    const service = new HistoryService();

    // Register commands
    commands.addCommand(CommandIDs.showHistoryViewer, {
      label: trans.__('Show Version History'),
      execute: () => {
        // Show the history viewer dialog
        const historyViewerWidget = ReactWidget.create(
          <HistoryViewer 
            historyService={service}
            translator={translator}
          />
        );

        return showDialog({
          title: trans.__('Version History'),
          body: historyViewerWidget,
          buttons: [Dialog.okButton({ label: trans.__('Close') })]
        });
      },
      isEnabled: () => tracker.currentWidget !== null && service.enabled
    });

    // Add to command palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.showHistoryViewer,
        category: 'Collaboration'
      });
    }

    // Load settings
    if (settingRegistry) {
      settingRegistry.load(historyPlugin.id)
        .then(settings => {
          // Apply settings
          const enabled = settings.get('enabled').composite as boolean;
          service['_enabled'] = enabled;

          // Listen for setting changes
          settings.changed.connect(() => {
            const newEnabled = settings.get('enabled').composite as boolean;
            service['_enabled'] = newEnabled;
          });
        })
        .catch(console.error);
    }

    return service;
  }
};

/**
 * A plugin that provides the permissions service for collaboration.
 */
const permissionsPlugin: JupyterFrontEndPlugin<IPermissionsService> = {
  id: '@jupyter-notebook/notebook-extension:collaboration-permissions',
  description: 'A plugin that provides the permissions service for collaboration.',
  autoStart: true,
  requires: [ICollaborationService, INotebookTracker, ITranslator],
  optional: [ISettingRegistry, ICommandPalette],
  provides: IPermissionsService,
  activate: (
    app: JupyterFrontEnd,
    collaborationService: ICollaborationService,
    tracker: INotebookTracker,
    translator: ITranslator,
    settingRegistry: ISettingRegistry | null,
    palette: ICommandPalette | null
  ): IPermissionsService => {
    const trans = translator.load('notebook');
    const { commands } = app;

    // Create a class that implements the IPermissionsService interface
    class PermissionsService implements IPermissionsService {
      private _enabled = true;
      private _currentRole = 'admin';
      private _userRoles = new Map<string, string>();
      private _roles: IRole[] = [
        {
          id: 'viewer',
          name: 'Viewer',
          description: 'Can view the notebook but not edit',
          permissions: ['view']
        },
        {
          id: 'editor',
          name: 'Editor',
          description: 'Can edit and execute cells',
          permissions: ['view', 'edit', 'execute']
        },
        {
          id: 'admin',
          name: 'Admin',
          description: 'Can manage users and permissions',
          permissions: ['view', 'edit', 'execute', 'manage']
        }
      ];

      constructor() {
        // Initialize with the local user as admin
        this._userRoles.set('local-user', 'admin');
      }

      get enabled(): boolean {
        return this._enabled && collaborationService.enabled && collaborationService.connected;
      }

      get currentRole(): string {
        return this._currentRole;
      }

      get userRoles(): ReadonlyMap<string, string> {
        return this._userRoles;
      }

      hasPermission(permission: string): boolean {
        // Check if the current user has a specific permission
        const role = this._roles.find(r => r.id === this._currentRole);
        return role ? role.permissions.includes(permission) : false;
      }

      async setUserRole(userId: string, role: string): Promise<boolean> {
        // Set a user's role
        console.log('Setting user role', userId, role);

        // Check if the role exists
        if (!this._roles.some(r => r.id === role)) {
          return false;
        }

        // Set the role
        this._userRoles.set(userId, role);

        return true;
      }

      getRoles(): ReadonlyArray<IRole> {
        return this._roles;
      }
    }

    // Create an instance of the service
    const service = new PermissionsService();

    // Register commands
    commands.addCommand(CommandIDs.showPermissionsDialog, {
      label: trans.__('Manage Permissions'),
      execute: () => {
        // Show the permissions dialog
        const permissionsDialogWidget = ReactWidget.create(
          <PermissionsDialog 
            permissionsService={service}
            translator={translator}
          />
        );

        return showDialog({
          title: trans.__('Manage Permissions'),
          body: permissionsDialogWidget,
          buttons: [Dialog.okButton({ label: trans.__('Close') })]
        });
      },
      isEnabled: () => tracker.currentWidget !== null && 
                     service.enabled && 
                     service.hasPermission('manage')
    });

    // Add to command palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.showPermissionsDialog,
        category: 'Collaboration'
      });
    }

    // Load settings
    if (settingRegistry) {
      settingRegistry.load(permissionsPlugin.id)
        .then(settings => {
          // Apply settings
          const enabled = settings.get('enabled').composite as boolean;
          service['_enabled'] = enabled;

          // Listen for setting changes
          settings.changed.connect(() => {
            const newEnabled = settings.get('enabled').composite as boolean;
            service['_enabled'] = newEnabled;
          });
        })
        .catch(console.error);
    }

    return service;
  }
};

/**
 * A plugin that provides the comment service for collaboration.
 */
const commentPlugin: JupyterFrontEndPlugin<ICommentService> = {
  id: '@jupyter-notebook/notebook-extension:collaboration-comments',
  description: 'A plugin that provides the comment service for collaboration.',
  autoStart: true,
  requires: [ICollaborationService, INotebookTracker, ITranslator],
  optional: [ISettingRegistry, ICommandPalette],
  provides: ICommentService,
  activate: (
    app: JupyterFrontEnd,
    collaborationService: ICollaborationService,
    tracker: INotebookTracker,
    translator: ITranslator,
    settingRegistry: ISettingRegistry | null,
    palette: ICommandPalette | null
  ): ICommentService => {
    const trans = translator.load('notebook');
    const { commands } = app;

    // Create a class that implements the ICommentService interface
    class CommentService implements ICommentService {
      private _enabled = true;
      private _comments: IComment[] = [];

      constructor() {
        // Initialize the service
      }

      get enabled(): boolean {
        return this._enabled && collaborationService.enabled && collaborationService.connected;
      }

      get comments(): ReadonlyArray<IComment> {
        return this._comments;
      }

      async addComment(cellId: string, text: string, range?: ISelectionRange): Promise<IComment> {
        // Add a comment to a cell
        console.log('Adding comment to cell', cellId, text, range);

        const comment: IComment = {
          id: `comment-${Date.now()}`,
          cellId,
          userId: 'local-user',
          timestamp: Date.now(),
          text,
          range,
          resolved: false,
          replies: []
        };

        this._comments.push(comment);

        return comment;
      }

      async replyToComment(commentId: string, text: string): Promise<IComment> {
        // Reply to a comment
        console.log('Replying to comment', commentId, text);

        // Find the parent comment
        const parentComment = this._comments.find(c => c.id === commentId);
        if (!parentComment) {
          throw new Error(`Comment with ID ${commentId} not found`);
        }

        const reply: IComment = {
          id: `comment-${Date.now()}`,
          cellId: parentComment.cellId,
          userId: 'local-user',
          timestamp: Date.now(),
          text,
          parentId: commentId,
          resolved: false,
          replies: []
        };

        // Add the reply to the parent comment's replies
        (parentComment.replies as IComment[]).push(reply);

        return reply;
      }

      async resolveComment(commentId: string): Promise<boolean> {
        // Resolve a comment
        console.log('Resolving comment', commentId);

        // Find the comment
        const comment = this._findComment(commentId);
        if (!comment) {
          return false;
        }

        // Mark the comment as resolved
        (comment as any).resolved = true;
        (comment as any).resolvedBy = 'local-user';
        (comment as any).resolvedAt = Date.now();

        return true;
      }

      async deleteComment(commentId: string): Promise<boolean> {
        // Delete a comment
        console.log('Deleting comment', commentId);

        // Find the comment
        const comment = this._findComment(commentId);
        if (!comment) {
          return false;
        }

        // If it's a top-level comment, remove it from the comments array
        if (!comment.parentId) {
          const index = this._comments.findIndex(c => c.id === commentId);
          if (index !== -1) {
            this._comments.splice(index, 1);
          }
        } else {
          // If it's a reply, remove it from the parent's replies
          const parentComment = this._findComment(comment.parentId);
          if (parentComment) {
            const index = (parentComment.replies as IComment[]).findIndex(c => c.id === commentId);
            if (index !== -1) {
              (parentComment.replies as IComment[]).splice(index, 1);
            }
          }
        }

        return true;
      }

      getCommentsForCell(cellId: string): ReadonlyArray<IComment> {
        // Get comments for a specific cell
        return this._comments.filter(c => c.cellId === cellId && !c.parentId);
      }

      private _findComment(commentId: string): IComment | undefined {
        // Find a comment by ID (including replies)
        const topLevelComment = this._comments.find(c => c.id === commentId);
        if (topLevelComment) {
          return topLevelComment;
        }

        // Search in replies
        for (const comment of this._comments) {
          const reply = comment.replies.find(r => r.id === commentId);
          if (reply) {
            return reply;
          }
        }

        return undefined;
      }
    }

    // Create an instance of the service
    const service = new CommentService();

    // Register commands
    commands.addCommand(CommandIDs.addComment, {
      label: trans.__('Add Comment'),
      execute: async () => {
        const current = tracker.currentWidget;
        if (!current) {
          return;
        }

        const activeCell = current.content.activeCell;
        if (!activeCell) {
          return;
        }

        const cellId = activeCell.model.id;

        // Show a dialog to get the comment text
        const result = await showDialog({
          title: trans.__('Add Comment'),
          body: new Widget({ node: document.createElement('textarea') }),
          buttons: [Dialog.cancelButton(), Dialog.okButton({ label: trans.__('Add') })]
        });

        if (result.button.accept) {
          const textarea = result.value.node as HTMLTextAreaElement;
          const text = textarea.value.trim();
          if (text) {
            return service.addComment(cellId, text);
          }
        }
      },
      isEnabled: () => tracker.currentWidget !== null && 
                     tracker.currentWidget.content.activeCell !== null && 
                     service.enabled
    });

    // Add to command palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.addComment,
        category: 'Collaboration'
      });
    }

    // Load settings
    if (settingRegistry) {
      settingRegistry.load(commentPlugin.id)
        .then(settings => {
          // Apply settings
          const enabled = settings.get('enabled').composite as boolean;
          service['_enabled'] = enabled;

          // Listen for setting changes
          settings.changed.connect(() => {
            const newEnabled = settings.get('enabled').composite as boolean;
            service['_enabled'] = newEnabled;
          });
        })
        .catch(console.error);
    }

    return service;
  }
};

/**
 * Export the plugins as default.
 */
const plugins: JupyterFrontEndPlugin<any>[] = [
  checkpoints,
  closeTab,
  openTreeTab,
  editNotebookMetadata,
  fullWidthNotebook,
  kernelLogo,
  kernelStatus,
  notebookToolsWidget,
  scrollOutput,
  tabIcon,
  trusted,
  // Add collaboration plugins
  collaborationCore,
  presencePlugin,
  lockPlugin,
  historyPlugin,
  permissionsPlugin,
  commentPlugin
];

export default plugins;
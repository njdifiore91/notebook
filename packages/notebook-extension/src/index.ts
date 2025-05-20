// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin,
} from '@jupyterlab/application';

import {
  ISessionContext,
  DOMUtils,
  IToolbarWidgetRegistry,
  ICommandPalette,
  Dialog,
  showDialog,
  ToolbarButton,
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

import { Token } from '@lumino/coreutils';

import { Widget } from '@lumino/widgets';

import { TrustedComponent } from './trusted';

// Import Yjs and related libraries
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { awareness } from 'y-protocols/awareness';

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
 * The token for the collaboration service.
 */
export const ICollaborationService = new Token<ICollaborationService>(
  '@jupyter-notebook/notebook-extension:ICollaborationService'
);

/**
 * The token for the presence service.
 */
export const IPresenceService = new Token<IPresenceService>(
  '@jupyter-notebook/notebook-extension:IPresenceService'
);

/**
 * The token for the lock service.
 */
export const ILockService = new Token<ILockService>(
  '@jupyter-notebook/notebook-extension:ILockService'
);

/**
 * The token for the history service.
 */
export const IHistoryService = new Token<IHistoryService>(
  '@jupyter-notebook/notebook-extension:IHistoryService'
);

/**
 * The token for the permissions service.
 */
export const IPermissionsService = new Token<IPermissionsService>(
  '@jupyter-notebook/notebook-extension:IPermissionsService'
);

/**
 * The token for the comment service.
 */
export const ICommentService = new Token<ICommentService>(
  '@jupyter-notebook/notebook-extension:ICommentService'
);

/**
 * Interface for the collaboration service.
 */
export interface ICollaborationService {
  /**
   * Initialize collaboration for a notebook panel.
   */
  initialize(panel: NotebookPanel): void;

  /**
   * Get the Yjs document for a notebook panel.
   */
  getYjsDocument(panel: NotebookPanel): Y.Doc | null;

  /**
   * Get the WebSocket provider for a notebook panel.
   */
  getProvider(panel: NotebookPanel): WebsocketProvider | null;

  /**
   * Check if collaboration is enabled for a notebook panel.
   */
  isEnabled(panel: NotebookPanel): boolean;

  /**
   * Enable or disable collaboration for a notebook panel.
   */
  setEnabled(panel: NotebookPanel, enabled: boolean): void;

  /**
   * Signal emitted when collaboration status changes.
   */
  readonly statusChanged: ISignal<ICollaborationService, { panel: NotebookPanel, status: 'connected' | 'disconnected' | 'error' }>;
}

/**
 * Interface for the presence service.
 */
export interface IPresenceService {
  /**
   * Initialize presence for a notebook panel.
   */
  initialize(panel: NotebookPanel): void;

  /**
   * Get the list of active users for a notebook panel.
   */
  getActiveUsers(panel: NotebookPanel): Array<{ id: string, name: string, color: string, avatar?: string }>;

  /**
   * Get the awareness instance for a notebook panel.
   */
  getAwareness(panel: NotebookPanel): any | null;

  /**
   * Signal emitted when user presence changes.
   */
  readonly presenceChanged: ISignal<IPresenceService, { panel: NotebookPanel, users: Array<{ id: string, name: string, color: string, avatar?: string }> }>;
}

/**
 * Interface for the lock service.
 */
export interface ILockService {
  /**
   * Initialize locks for a notebook panel.
   */
  initialize(panel: NotebookPanel): void;

  /**
   * Lock a cell in a notebook panel.
   */
  lockCell(panel: NotebookPanel, cellId: string): Promise<boolean>;

  /**
   * Unlock a cell in a notebook panel.
   */
  unlockCell(panel: NotebookPanel, cellId: string): Promise<boolean>;

  /**
   * Check if a cell is locked in a notebook panel.
   */
  isCellLocked(panel: NotebookPanel, cellId: string): boolean;

  /**
   * Get the user who locked a cell in a notebook panel.
   */
  getCellLockOwner(panel: NotebookPanel, cellId: string): string | null;

  /**
   * Signal emitted when cell lock status changes.
   */
  readonly lockChanged: ISignal<ILockService, { panel: NotebookPanel, cellId: string, locked: boolean, owner: string | null }>;
}

/**
 * Interface for the history service.
 */
export interface IHistoryService {
  /**
   * Initialize history for a notebook panel.
   */
  initialize(panel: NotebookPanel): void;

  /**
   * Get the history for a notebook panel.
   */
  getHistory(panel: NotebookPanel): Array<{ id: string, timestamp: number, author: string, changes: any }>;

  /**
   * Restore a notebook panel to a specific history point.
   */
  restoreToVersion(panel: NotebookPanel, versionId: string): Promise<boolean>;

  /**
   * Signal emitted when history changes.
   */
  readonly historyChanged: ISignal<IHistoryService, { panel: NotebookPanel, history: Array<{ id: string, timestamp: number, author: string, changes: any }> }>;
}

/**
 * Interface for the permissions service.
 */
export interface IPermissionsService {
  /**
   * Initialize permissions for a notebook panel.
   */
  initialize(panel: NotebookPanel): void;

  /**
   * Get the permissions for a notebook panel.
   */
  getPermissions(panel: NotebookPanel): { [userId: string]: 'view' | 'comment' | 'edit' | 'admin' };

  /**
   * Set the permissions for a user in a notebook panel.
   */
  setUserPermission(
    panel: NotebookPanel,
    userId: string,
    permission: 'view' | 'comment' | 'edit' | 'admin'
  ): Promise<boolean>;

  /**
   * Check if the current user has a specific permission for a notebook panel.
   */
  hasPermission(panel: NotebookPanel, permission: 'view' | 'comment' | 'edit' | 'admin'): boolean;

  /**
   * Signal emitted when permissions change.
   */
  readonly permissionsChanged: ISignal<IPermissionsService, { panel: NotebookPanel, permissions: { [userId: string]: 'view' | 'comment' | 'edit' | 'admin' } }>;
}

/**
 * Interface for the comment service.
 */
export interface ICommentService {
  /**
   * Initialize comments for a notebook panel.
   */
  initialize(panel: NotebookPanel): void;

  /**
   * Add a comment to a cell in a notebook panel.
   */
  addComment(panel: NotebookPanel, cellId: string, text: string, range?: { start: number, end: number }): Promise<string>;

  /**
   * Edit a comment in a notebook panel.
   */
  editComment(panel: NotebookPanel, commentId: string, text: string): Promise<boolean>;

  /**
   * Delete a comment from a notebook panel.
   */
  deleteComment(panel: NotebookPanel, commentId: string): Promise<boolean>;

  /**
   * Resolve a comment in a notebook panel.
   */
  resolveComment(panel: NotebookPanel, commentId: string): Promise<boolean>;

  /**
   * Get all comments for a notebook panel.
   */
  getComments(panel: NotebookPanel): Array<{ id: string, cellId: string, author: string, text: string, timestamp: number, resolved: boolean, range?: { start: number, end: number } }>;

  /**
   * Signal emitted when comments change.
   */
  readonly commentsChanged: ISignal<ICommentService, { panel: NotebookPanel, comments: Array<{ id: string, cellId: string, author: string, text: string, timestamp: number, resolved: boolean, range?: { start: number, end: number } }> }>;
}

/**
 * Import the ISignal interface from @lumino/signaling.
 */
import { ISignal } from '@lumino/signaling';

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
   * A command to toggle collaboration mode
   */
  export const toggleCollaboration = 'notebook:toggle-collaboration';

  /**
   * A command to show the collaboration history
   */
  export const showCollaborationHistory = 'notebook:show-collaboration-history';

  /**
   * A command to show the permissions dialog
   */
  export const showPermissionsDialog = 'notebook:show-permissions-dialog';

  /**
   * A command to show the comments panel
   */
  export const showCommentsPanel = 'notebook:show-comments-panel';

  /**
   * A command to lock the current cell
   */
  export const lockCurrentCell = 'notebook:lock-current-cell';

  /**
   * A command to unlock the current cell
   */
  export const unlockCurrentCell = 'notebook:unlock-current-cell';
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
  requires: [INotebookTracker, ITranslator],
  optional: [ISettingRegistry, IToolbarWidgetRegistry, ICommandPalette, IMainMenu],
  provides: ICollaborationService,
  activate: (
    app: JupyterFrontEnd,
    tracker: INotebookTracker,
    translator: ITranslator,
    settingRegistry: ISettingRegistry | null,
    toolbarRegistry: IToolbarWidgetRegistry | null,
    palette: ICommandPalette | null,
    mainMenu: IMainMenu | null
  ): ICollaborationService => {
    const trans = translator.load('notebook');
    const { commands } = app;
    
    // Create the collaboration service
    const service = new CollaborationService(translator);
    
    // Add collaboration toggle command
    commands.addCommand(CommandIDs.toggleCollaboration, {
      label: trans.__('Enable Collaboration'),
      execute: () => {
        const panel = tracker.currentWidget;
        if (!panel) {
          return;
        }
        
        const enabled = service.isEnabled(panel);
        service.setEnabled(panel, !enabled);
        
        // Show a dialog when enabling collaboration
        if (!enabled) {
          showDialog({
            title: trans.__('Collaboration Enabled'),
            body: trans.__('Real-time collaboration is now enabled for this notebook. Other users with access can now edit simultaneously.'),
            buttons: [Dialog.okButton({ label: trans.__('OK') })]
          });
        }
      },
      isEnabled: () => tracker.currentWidget !== null,
      isToggled: () => {
        const panel = tracker.currentWidget;
        return panel ? service.isEnabled(panel) : false;
      }
    });
    
    // Add collaboration toggle button to toolbar
    if (toolbarRegistry) {
      toolbarRegistry.addFactory('TopBar', 'collaboration', (toolbar) => {
        const button = new ToolbarButton({
          icon: 'ui-components:users',
          onClick: () => {
            commands.execute(CommandIDs.toggleCollaboration);
          },
          tooltip: trans.__('Toggle Collaboration')
        });
        
        // Update button state when collaboration status changes
        service.statusChanged.connect((_, args) => {
          if (args.panel === tracker.currentWidget) {
            button.addClass('jp-mod-active');
          }
        });
        
        return button;
      });
    }
    
    // Add collaboration toggle to command palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.toggleCollaboration,
        category: 'Collaboration'
      });
    }
    
    // Add collaboration menu to main menu
    if (mainMenu) {
      mainMenu.addMenu({
        rank: 40,
        id: 'collaboration',
        label: trans.__('Collaboration')
      });
      
      mainMenu.menus.find(menu => menu.id === 'collaboration')?.addItem({
        command: CommandIDs.toggleCollaboration
      });
    }
    
    // Load settings
    if (settingRegistry) {
      const loadSettings = settingRegistry.load(collaborationCore.id);
      loadSettings
        .then(settings => {
          // Update settings when they change
          settings.changed.connect(() => {
            const autoEnable = settings.get('autoEnableCollaboration').composite as boolean;
            if (autoEnable) {
              // Auto-enable collaboration for new notebooks
              tracker.widgetAdded.connect((_, panel) => {
                service.setEnabled(panel, true);
              });
            }
          });
        })
        .catch((reason: Error) => {
          console.error(`Failed to load settings for ${collaborationCore.id}`, reason);
        });
    }
    
    return service;
  }
};

/**
 * Implementation of the CollaborationService.
 */
class CollaborationService implements ICollaborationService {
  constructor(translator: ITranslator) {
    this._translator = translator;
    this._yjsDocs = new Map<string, Y.Doc>();
    this._providers = new Map<string, WebsocketProvider>();
    this._enabled = new Set<string>();
    this._statusChanged = new Signal<ICollaborationService, { panel: NotebookPanel, status: 'connected' | 'disconnected' | 'error' }>(this);
  }
  
  initialize(panel: NotebookPanel): void {
    const id = panel.id;
    
    // Create Yjs document if it doesn't exist
    if (!this._yjsDocs.has(id)) {
      const doc = new Y.Doc();
      this._yjsDocs.set(id, doc);
      
      // Create WebSocket provider
      const baseUrl = PageConfig.getBaseUrl();
      const wsUrl = URLExt.join(baseUrl, 'api/collaboration', panel.context.path);
      const provider = new WebsocketProvider(wsUrl, id, doc);
      this._providers.set(id, provider);
      
      // Handle connection status changes
      provider.on('status', (event: { status: 'connecting' | 'connected' | 'disconnected' }) => {
        if (event.status === 'connected') {
          this._statusChanged.emit({ panel, status: 'connected' });
        } else if (event.status === 'disconnected') {
          this._statusChanged.emit({ panel, status: 'disconnected' });
        }
      });
      
      provider.on('connection-error', () => {
        this._statusChanged.emit({ panel, status: 'error' });
      });
    }
  }
  
  getYjsDocument(panel: NotebookPanel): Y.Doc | null {
    return this._yjsDocs.get(panel.id) || null;
  }
  
  getProvider(panel: NotebookPanel): WebsocketProvider | null {
    return this._providers.get(panel.id) || null;
  }
  
  isEnabled(panel: NotebookPanel): boolean {
    return this._enabled.has(panel.id);
  }
  
  setEnabled(panel: NotebookPanel, enabled: boolean): void {
    const id = panel.id;
    
    if (enabled && !this._enabled.has(id)) {
      // Initialize if not already initialized
      this.initialize(panel);
      
      // Connect the provider
      const provider = this._providers.get(id);
      if (provider) {
        provider.connect();
      }
      
      this._enabled.add(id);
    } else if (!enabled && this._enabled.has(id)) {
      // Disconnect the provider
      const provider = this._providers.get(id);
      if (provider) {
        provider.disconnect();
      }
      
      this._enabled.delete(id);
    }
  }
  
  get statusChanged(): ISignal<ICollaborationService, { panel: NotebookPanel, status: 'connected' | 'disconnected' | 'error' }> {
    return this._statusChanged;
  }
  
  private _translator: ITranslator;
  private _yjsDocs: Map<string, Y.Doc>;
  private _providers: Map<string, WebsocketProvider>;
  private _enabled: Set<string>;
  private _statusChanged: Signal<ICollaborationService, { panel: NotebookPanel, status: 'connected' | 'disconnected' | 'error' }>;
}

/**
 * A plugin that provides the presence service.
 */
const presenceService: JupyterFrontEndPlugin<IPresenceService> = {
  id: '@jupyter-notebook/notebook-extension:presence-service',
  description: 'A plugin that provides the presence service.',
  autoStart: true,
  requires: [ICollaborationService, INotebookTracker, ITranslator],
  optional: [IToolbarWidgetRegistry],
  provides: IPresenceService,
  activate: (
    app: JupyterFrontEnd,
    collaborationService: ICollaborationService,
    tracker: INotebookTracker,
    translator: ITranslator,
    toolbarRegistry: IToolbarWidgetRegistry | null
  ): IPresenceService => {
    const trans = translator.load('notebook');
    
    // Create the presence service
    const service = new PresenceService(collaborationService, translator);
    
    // Add presence indicator to toolbar
    if (toolbarRegistry) {
      toolbarRegistry.addFactory('TopBar', 'presence', (toolbar) => {
        const node = document.createElement('div');
        node.className = 'jp-NotebookPresence';
        
        const widget = new Widget({ node });
        widget.id = DOMUtils.createDomID();
        
        // Update presence indicator when users change
        service.presenceChanged.connect((_, args) => {
          if (args.panel === tracker.currentWidget) {
            const users = args.users;
            node.innerHTML = '';
            
            if (users.length > 0) {
              // Create avatar elements for up to 3 users
              const maxVisible = Math.min(users.length, 3);
              for (let i = 0; i < maxVisible; i++) {
                const user = users[i];
                const avatar = document.createElement('div');
                avatar.className = 'jp-NotebookPresence-avatar';
                avatar.style.backgroundColor = user.color;
                avatar.title = user.name;
                avatar.textContent = user.name.substring(0, 1).toUpperCase();
                node.appendChild(avatar);
              }
              
              // Add count if there are more users
              if (users.length > 3) {
                const count = document.createElement('div');
                count.className = 'jp-NotebookPresence-count';
                count.textContent = `+${users.length - 3}`;
                count.title = trans.__('and %1 more users', users.length - 3);
                node.appendChild(count);
              }
            }
          }
        });
        
        return widget;
      });
    }
    
    return service;
  }
};

/**
 * Implementation of the PresenceService.
 */
class PresenceService implements IPresenceService {
  constructor(collaborationService: ICollaborationService, translator: ITranslator) {
    this._collaborationService = collaborationService;
    this._translator = translator;
    this._awareness = new Map<string, any>();
    this._presenceChanged = new Signal<IPresenceService, { panel: NotebookPanel, users: Array<{ id: string, name: string, color: string, avatar?: string }> }>(this);
  }
  
  initialize(panel: NotebookPanel): void {
    const id = panel.id;
    
    // Get the provider from the collaboration service
    const provider = this._collaborationService.getProvider(panel);
    if (!provider) {
      return;
    }
    
    // Get the awareness instance from the provider
    const awareness = provider.awareness;
    this._awareness.set(id, awareness);
    
    // Set local user state
    awareness.setLocalState({
      user: {
        id: PageConfig.getOption('userId') || `user-${Math.floor(Math.random() * 1000)}`,
        name: PageConfig.getOption('userName') || 'Anonymous',
        color: `hsl(${Math.floor(Math.random() * 360)}, 70%, 50%)`,
      }
    });
    
    // Listen for awareness changes
    awareness.on('change', () => {
      this._presenceChanged.emit({
        panel,
        users: this.getActiveUsers(panel)
      });
    });
  }
  
  getActiveUsers(panel: NotebookPanel): Array<{ id: string, name: string, color: string, avatar?: string }> {
    const awareness = this._awareness.get(panel.id);
    if (!awareness) {
      return [];
    }
    
    const users: Array<{ id: string, name: string, color: string, avatar?: string }> = [];
    awareness.getStates().forEach((state: any, clientId: number) => {
      if (state.user) {
        users.push({
          id: state.user.id,
          name: state.user.name,
          color: state.user.color,
          avatar: state.user.avatar
        });
      }
    });
    
    return users;
  }
  
  getAwareness(panel: NotebookPanel): any | null {
    return this._awareness.get(panel.id) || null;
  }
  
  get presenceChanged(): ISignal<IPresenceService, { panel: NotebookPanel, users: Array<{ id: string, name: string, color: string, avatar?: string }> }> {
    return this._presenceChanged;
  }
  
  private _collaborationService: ICollaborationService;
  private _translator: ITranslator;
  private _awareness: Map<string, any>;
  private _presenceChanged: Signal<IPresenceService, { panel: NotebookPanel, users: Array<{ id: string, name: string, color: string, avatar?: string }> }>;
}

/**
 * A plugin that provides the lock service.
 */
const lockService: JupyterFrontEndPlugin<ILockService> = {
  id: '@jupyter-notebook/notebook-extension:lock-service',
  description: 'A plugin that provides the lock service.',
  autoStart: true,
  requires: [ICollaborationService, INotebookTracker, ITranslator],
  optional: [ICommandPalette, IMainMenu],
  provides: ILockService,
  activate: (
    app: JupyterFrontEnd,
    collaborationService: ICollaborationService,
    tracker: INotebookTracker,
    translator: ITranslator,
    palette: ICommandPalette | null,
    mainMenu: IMainMenu | null
  ): ILockService => {
    const trans = translator.load('notebook');
    const { commands } = app;
    
    // Create the lock service
    const service = new LockService(collaborationService, translator);
    
    // Add lock/unlock commands
    commands.addCommand(CommandIDs.lockCurrentCell, {
      label: trans.__('Lock Current Cell'),
      execute: async () => {
        const panel = tracker.currentWidget;
        if (!panel) {
          return;
        }
        
        const activeCell = panel.content.activeCell;
        if (!activeCell) {
          return;
        }
        
        await service.lockCell(panel, activeCell.model.id);
      },
      isEnabled: () => {
        const panel = tracker.currentWidget;
        if (!panel || !collaborationService.isEnabled(panel)) {
          return false;
        }
        
        const activeCell = panel.content.activeCell;
        if (!activeCell) {
          return false;
        }
        
        return !service.isCellLocked(panel, activeCell.model.id);
      }
    });
    
    commands.addCommand(CommandIDs.unlockCurrentCell, {
      label: trans.__('Unlock Current Cell'),
      execute: async () => {
        const panel = tracker.currentWidget;
        if (!panel) {
          return;
        }
        
        const activeCell = panel.content.activeCell;
        if (!activeCell) {
          return;
        }
        
        await service.unlockCell(panel, activeCell.model.id);
      },
      isEnabled: () => {
        const panel = tracker.currentWidget;
        if (!panel || !collaborationService.isEnabled(panel)) {
          return false;
        }
        
        const activeCell = panel.content.activeCell;
        if (!activeCell) {
          return false;
        }
        
        const owner = service.getCellLockOwner(panel, activeCell.model.id);
        // Can only unlock if you're the owner
        return owner === PageConfig.getOption('userId');
      }
    });
    
    // Add commands to palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.lockCurrentCell,
        category: 'Collaboration'
      });
      
      palette.addItem({
        command: CommandIDs.unlockCurrentCell,
        category: 'Collaboration'
      });
    }
    
    // Add commands to collaboration menu
    if (mainMenu) {
      const menu = mainMenu.menus.find(menu => menu.id === 'collaboration');
      if (menu) {
        menu.addItem({ type: 'separator' });
        menu.addItem({ command: CommandIDs.lockCurrentCell });
        menu.addItem({ command: CommandIDs.unlockCurrentCell });
      }
    }
    
    return service;
  }
};

/**
 * Implementation of the LockService.
 */
class LockService implements ILockService {
  constructor(collaborationService: ICollaborationService, translator: ITranslator) {
    this._collaborationService = collaborationService;
    this._translator = translator;
    this._locks = new Map<string, Map<string, string>>();
    this._lockChanged = new Signal<ILockService, { panel: NotebookPanel, cellId: string, locked: boolean, owner: string | null }>(this);
  }
  
  initialize(panel: NotebookPanel): void {
    const id = panel.id;
    
    // Get the Yjs document from the collaboration service
    const doc = this._collaborationService.getYjsDocument(panel);
    if (!doc) {
      return;
    }
    
    // Create a shared map for locks if it doesn't exist
    if (!doc.getMap('locks')) {
      doc.getMap('locks');
    }
    
    // Initialize locks map for this panel
    if (!this._locks.has(id)) {
      this._locks.set(id, new Map<string, string>());
    }
    
    // Listen for changes to the locks map
    doc.getMap('locks').observe(event => {
      const locks = this._locks.get(id)!;
      
      // Update local locks map
      event.changes.keys.forEach((change, key) => {
        if (change.action === 'add' || change.action === 'update') {
          const owner = doc.getMap('locks').get(key);
          locks.set(key, owner);
          this._lockChanged.emit({
            panel,
            cellId: key,
            locked: true,
            owner
          });
        } else if (change.action === 'delete') {
          locks.delete(key);
          this._lockChanged.emit({
            panel,
            cellId: key,
            locked: false,
            owner: null
          });
        }
      });
    });
  }
  
  async lockCell(panel: NotebookPanel, cellId: string): Promise<boolean> {
    const doc = this._collaborationService.getYjsDocument(panel);
    if (!doc) {
      return false;
    }
    
    // Check if cell is already locked
    const locksMap = doc.getMap('locks');
    if (locksMap.has(cellId)) {
      return false;
    }
    
    // Lock the cell with current user ID
    const userId = PageConfig.getOption('userId') || `user-${Math.floor(Math.random() * 1000)}`;
    locksMap.set(cellId, userId);
    
    return true;
  }
  
  async unlockCell(panel: NotebookPanel, cellId: string): Promise<boolean> {
    const doc = this._collaborationService.getYjsDocument(panel);
    if (!doc) {
      return false;
    }
    
    // Check if cell is locked by current user
    const locksMap = doc.getMap('locks');
    const owner = locksMap.get(cellId);
    const userId = PageConfig.getOption('userId') || `user-${Math.floor(Math.random() * 1000)}`;
    
    if (owner !== userId) {
      return false;
    }
    
    // Unlock the cell
    locksMap.delete(cellId);
    
    return true;
  }
  
  isCellLocked(panel: NotebookPanel, cellId: string): boolean {
    const locks = this._locks.get(panel.id);
    if (!locks) {
      return false;
    }
    
    return locks.has(cellId);
  }
  
  getCellLockOwner(panel: NotebookPanel, cellId: string): string | null {
    const locks = this._locks.get(panel.id);
    if (!locks) {
      return null;
    }
    
    return locks.get(cellId) || null;
  }
  
  get lockChanged(): ISignal<ILockService, { panel: NotebookPanel, cellId: string, locked: boolean, owner: string | null }> {
    return this._lockChanged;
  }
  
  private _collaborationService: ICollaborationService;
  private _translator: ITranslator;
  private _locks: Map<string, Map<string, string>>;
  private _lockChanged: Signal<ILockService, { panel: NotebookPanel, cellId: string, locked: boolean, owner: string | null }>;
}

/**
 * A plugin that provides the history service.
 */
const historyService: JupyterFrontEndPlugin<IHistoryService> = {
  id: '@jupyter-notebook/notebook-extension:history-service',
  description: 'A plugin that provides the history service.',
  autoStart: true,
  requires: [ICollaborationService, INotebookTracker, ITranslator],
  optional: [ICommandPalette, IMainMenu],
  provides: IHistoryService,
  activate: (
    app: JupyterFrontEnd,
    collaborationService: ICollaborationService,
    tracker: INotebookTracker,
    translator: ITranslator,
    palette: ICommandPalette | null,
    mainMenu: IMainMenu | null
  ): IHistoryService => {
    const trans = translator.load('notebook');
    const { commands } = app;
    
    // Create the history service
    const service = new HistoryService(collaborationService, translator);
    
    // Add history command
    commands.addCommand(CommandIDs.showCollaborationHistory, {
      label: trans.__('Show Collaboration History'),
      execute: () => {
        const panel = tracker.currentWidget;
        if (!panel) {
          return;
        }
        
        // Show history viewer dialog
        const history = service.getHistory(panel);
        showDialog({
          title: trans.__('Collaboration History'),
          body: trans.__('This feature will show the full history of changes to this notebook.'),
          buttons: [Dialog.okButton({ label: trans.__('OK') })]
        });
      },
      isEnabled: () => {
        const panel = tracker.currentWidget;
        return panel !== null && collaborationService.isEnabled(panel);
      }
    });
    
    // Add command to palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.showCollaborationHistory,
        category: 'Collaboration'
      });
    }
    
    // Add command to collaboration menu
    if (mainMenu) {
      const menu = mainMenu.menus.find(menu => menu.id === 'collaboration');
      if (menu) {
        menu.addItem({ type: 'separator' });
        menu.addItem({ command: CommandIDs.showCollaborationHistory });
      }
    }
    
    return service;
  }
};

/**
 * Implementation of the HistoryService.
 */
class HistoryService implements IHistoryService {
  constructor(collaborationService: ICollaborationService, translator: ITranslator) {
    this._collaborationService = collaborationService;
    this._translator = translator;
    this._history = new Map<string, Array<{ id: string, timestamp: number, author: string, changes: any }>>(); 
    this._historyChanged = new Signal<IHistoryService, { panel: NotebookPanel, history: Array<{ id: string, timestamp: number, author: string, changes: any }> }>(this);
  }
  
  initialize(panel: NotebookPanel): void {
    const id = panel.id;
    
    // Get the Yjs document from the collaboration service
    const doc = this._collaborationService.getYjsDocument(panel);
    if (!doc) {
      return;
    }
    
    // Initialize history for this panel
    if (!this._history.has(id)) {
      this._history.set(id, []);
    }
    
    // Listen for document updates to track history
    doc.on('update', (update: Uint8Array, origin: any) => {
      // Skip updates that originated from this client
      if (origin === 'local') {
        return;
      }
      
      // Add update to history
      const history = this._history.get(id)!;
      const entry = {
        id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        timestamp: Date.now(),
        author: origin?.user?.name || 'Unknown',
        changes: update
      };
      
      history.push(entry);
      
      // Emit history changed event
      this._historyChanged.emit({
        panel,
        history: this.getHistory(panel)
      });
    });
  }
  
  getHistory(panel: NotebookPanel): Array<{ id: string, timestamp: number, author: string, changes: any }> {
    return this._history.get(panel.id) || [];
  }
  
  async restoreToVersion(panel: NotebookPanel, versionId: string): Promise<boolean> {
    // This is a placeholder implementation
    // In a real implementation, we would apply the Yjs updates to restore to a specific version
    return false;
  }
  
  get historyChanged(): ISignal<IHistoryService, { panel: NotebookPanel, history: Array<{ id: string, timestamp: number, author: string, changes: any }> }> {
    return this._historyChanged;
  }
  
  private _collaborationService: ICollaborationService;
  private _translator: ITranslator;
  private _history: Map<string, Array<{ id: string, timestamp: number, author: string, changes: any }>>;
  private _historyChanged: Signal<IHistoryService, { panel: NotebookPanel, history: Array<{ id: string, timestamp: number, author: string, changes: any }> }>;
}

/**
 * A plugin that provides the permissions service.
 */
const permissionsService: JupyterFrontEndPlugin<IPermissionsService> = {
  id: '@jupyter-notebook/notebook-extension:permissions-service',
  description: 'A plugin that provides the permissions service.',
  autoStart: true,
  requires: [ICollaborationService, INotebookTracker, ITranslator],
  optional: [ICommandPalette, IMainMenu],
  provides: IPermissionsService,
  activate: (
    app: JupyterFrontEnd,
    collaborationService: ICollaborationService,
    tracker: INotebookTracker,
    translator: ITranslator,
    palette: ICommandPalette | null,
    mainMenu: IMainMenu | null
  ): IPermissionsService => {
    const trans = translator.load('notebook');
    const { commands } = app;
    
    // Create the permissions service
    const service = new PermissionsService(collaborationService, translator);
    
    // Add permissions command
    commands.addCommand(CommandIDs.showPermissionsDialog, {
      label: trans.__('Manage Collaboration Permissions'),
      execute: () => {
        const panel = tracker.currentWidget;
        if (!panel) {
          return;
        }
        
        // Show permissions dialog
        const permissions = service.getPermissions(panel);
        showDialog({
          title: trans.__('Collaboration Permissions'),
          body: trans.__('This feature will allow you to manage who can view, comment on, or edit this notebook.'),
          buttons: [Dialog.okButton({ label: trans.__('OK') })]
        });
      },
      isEnabled: () => {
        const panel = tracker.currentWidget;
        if (!panel || !collaborationService.isEnabled(panel)) {
          return false;
        }
        
        // Only users with admin permission can manage permissions
        return service.hasPermission(panel, 'admin');
      }
    });
    
    // Add command to palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.showPermissionsDialog,
        category: 'Collaboration'
      });
    }
    
    // Add command to collaboration menu
    if (mainMenu) {
      const menu = mainMenu.menus.find(menu => menu.id === 'collaboration');
      if (menu) {
        menu.addItem({ type: 'separator' });
        menu.addItem({ command: CommandIDs.showPermissionsDialog });
      }
    }
    
    return service;
  }
};

/**
 * Implementation of the PermissionsService.
 */
class PermissionsService implements IPermissionsService {
  constructor(collaborationService: ICollaborationService, translator: ITranslator) {
    this._collaborationService = collaborationService;
    this._translator = translator;
    this._permissions = new Map<string, { [userId: string]: 'view' | 'comment' | 'edit' | 'admin' }>(); 
    this._permissionsChanged = new Signal<IPermissionsService, { panel: NotebookPanel, permissions: { [userId: string]: 'view' | 'comment' | 'edit' | 'admin' } }>(this);
  }
  
  initialize(panel: NotebookPanel): void {
    const id = panel.id;
    
    // Get the Yjs document from the collaboration service
    const doc = this._collaborationService.getYjsDocument(panel);
    if (!doc) {
      return;
    }
    
    // Create a shared map for permissions if it doesn't exist
    if (!doc.getMap('permissions')) {
      doc.getMap('permissions');
    }
    
    // Initialize permissions for this panel
    if (!this._permissions.has(id)) {
      this._permissions.set(id, {});
      
      // Set current user as admin by default
      const userId = PageConfig.getOption('userId') || `user-${Math.floor(Math.random() * 1000)}`;
      this._permissions.get(id)![userId] = 'admin';
      doc.getMap('permissions').set(userId, 'admin');
    }
    
    // Listen for changes to the permissions map
    doc.getMap('permissions').observe(event => {
      const permissions = this._permissions.get(id)!;
      
      // Update local permissions map
      event.changes.keys.forEach((change, key) => {
        if (change.action === 'add' || change.action === 'update') {
          const permission = doc.getMap('permissions').get(key) as 'view' | 'comment' | 'edit' | 'admin';
          permissions[key] = permission;
        } else if (change.action === 'delete') {
          delete permissions[key];
        }
      });
      
      // Emit permissions changed event
      this._permissionsChanged.emit({
        panel,
        permissions: { ...permissions }
      });
    });
  }
  
  getPermissions(panel: NotebookPanel): { [userId: string]: 'view' | 'comment' | 'edit' | 'admin' } {
    return { ...this._permissions.get(panel.id) } || {};
  }
  
  async setUserPermission(
    panel: NotebookPanel,
    userId: string,
    permission: 'view' | 'comment' | 'edit' | 'admin'
  ): Promise<boolean> {
    const doc = this._collaborationService.getYjsDocument(panel);
    if (!doc) {
      return false;
    }
    
    // Check if current user has admin permission
    const currentUserId = PageConfig.getOption('userId') || `user-${Math.floor(Math.random() * 1000)}`;
    const permissions = this._permissions.get(panel.id) || {};
    
    if (permissions[currentUserId] !== 'admin') {
      return false;
    }
    
    // Set permission for user
    doc.getMap('permissions').set(userId, permission);
    
    return true;
  }
  
  hasPermission(panel: NotebookPanel, permission: 'view' | 'comment' | 'edit' | 'admin'): boolean {
    const userId = PageConfig.getOption('userId') || `user-${Math.floor(Math.random() * 1000)}`;
    const permissions = this._permissions.get(panel.id) || {};
    const userPermission = permissions[userId] || 'view';
    
    // Check if user has the required permission or higher
    switch (permission) {
      case 'view':
        return true; // Everyone has view permission
      case 'comment':
        return userPermission === 'comment' || userPermission === 'edit' || userPermission === 'admin';
      case 'edit':
        return userPermission === 'edit' || userPermission === 'admin';
      case 'admin':
        return userPermission === 'admin';
      default:
        return false;
    }
  }
  
  get permissionsChanged(): ISignal<IPermissionsService, { panel: NotebookPanel, permissions: { [userId: string]: 'view' | 'comment' | 'edit' | 'admin' } }> {
    return this._permissionsChanged;
  }
  
  private _collaborationService: ICollaborationService;
  private _translator: ITranslator;
  private _permissions: Map<string, { [userId: string]: 'view' | 'comment' | 'edit' | 'admin' }>;
  private _permissionsChanged: Signal<IPermissionsService, { panel: NotebookPanel, permissions: { [userId: string]: 'view' | 'comment' | 'edit' | 'admin' } }>;
}

/**
 * A plugin that provides the comment service.
 */
const commentService: JupyterFrontEndPlugin<ICommentService> = {
  id: '@jupyter-notebook/notebook-extension:comment-service',
  description: 'A plugin that provides the comment service.',
  autoStart: true,
  requires: [ICollaborationService, INotebookTracker, ITranslator],
  optional: [ICommandPalette, IMainMenu],
  provides: ICommentService,
  activate: (
    app: JupyterFrontEnd,
    collaborationService: ICollaborationService,
    tracker: INotebookTracker,
    translator: ITranslator,
    palette: ICommandPalette | null,
    mainMenu: IMainMenu | null
  ): ICommentService => {
    const trans = translator.load('notebook');
    const { commands } = app;
    
    // Create the comment service
    const service = new CommentService(collaborationService, translator);
    
    // Add comments command
    commands.addCommand(CommandIDs.showCommentsPanel, {
      label: trans.__('Show Comments Panel'),
      execute: () => {
        const panel = tracker.currentWidget;
        if (!panel) {
          return;
        }
        
        // Show comments panel
        showDialog({
          title: trans.__('Notebook Comments'),
          body: trans.__('This feature will show a panel with all comments on this notebook.'),
          buttons: [Dialog.okButton({ label: trans.__('OK') })]
        });
      },
      isEnabled: () => {
        const panel = tracker.currentWidget;
        return panel !== null && collaborationService.isEnabled(panel);
      }
    });
    
    // Add command to palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.showCommentsPanel,
        category: 'Collaboration'
      });
    }
    
    // Add command to collaboration menu
    if (mainMenu) {
      const menu = mainMenu.menus.find(menu => menu.id === 'collaboration');
      if (menu) {
        menu.addItem({ type: 'separator' });
        menu.addItem({ command: CommandIDs.showCommentsPanel });
      }
    }
    
    return service;
  }
};

/**
 * Implementation of the CommentService.
 */
class CommentService implements ICommentService {
  constructor(collaborationService: ICollaborationService, translator: ITranslator) {
    this._collaborationService = collaborationService;
    this._translator = translator;
    this._comments = new Map<string, Array<{ id: string, cellId: string, author: string, text: string, timestamp: number, resolved: boolean, range?: { start: number, end: number } }>>(); 
    this._commentsChanged = new Signal<ICommentService, { panel: NotebookPanel, comments: Array<{ id: string, cellId: string, author: string, text: string, timestamp: number, resolved: boolean, range?: { start: number, end: number } }> }>(this);
  }
  
  initialize(panel: NotebookPanel): void {
    const id = panel.id;
    
    // Get the Yjs document from the collaboration service
    const doc = this._collaborationService.getYjsDocument(panel);
    if (!doc) {
      return;
    }
    
    // Create a shared array for comments if it doesn't exist
    if (!doc.getArray('comments')) {
      doc.getArray('comments');
    }
    
    // Initialize comments for this panel
    if (!this._comments.has(id)) {
      this._comments.set(id, []);
    }
    
    // Listen for changes to the comments array
    doc.getArray('comments').observe(event => {
      // Rebuild the comments array from the Yjs array
      const comments = this._comments.get(id)!;
      comments.length = 0;
      
      doc.getArray('comments').forEach((item: any) => {
        comments.push({
          id: item.id,
          cellId: item.cellId,
          author: item.author,
          text: item.text,
          timestamp: item.timestamp,
          resolved: item.resolved,
          range: item.range
        });
      });
      
      // Emit comments changed event
      this._commentsChanged.emit({
        panel,
        comments: [...comments]
      });
    });
  }
  
  async addComment(panel: NotebookPanel, cellId: string, text: string, range?: { start: number, end: number }): Promise<string> {
    const doc = this._collaborationService.getYjsDocument(panel);
    if (!doc) {
      return '';
    }
    
    // Check if user has comment permission
    const permissionsService = app.serviceManager.services.get(IPermissionsService) as IPermissionsService;
    if (permissionsService && !permissionsService.hasPermission(panel, 'comment')) {
      throw new Error('You do not have permission to add comments');
    }
    
    // Create comment object
    const id = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const userId = PageConfig.getOption('userId') || `user-${Math.floor(Math.random() * 1000)}`;
    const userName = PageConfig.getOption('userName') || 'Anonymous';
    
    const comment = {
      id,
      cellId,
      author: userName,
      authorId: userId,
      text,
      timestamp: Date.now(),
      resolved: false,
      range
    };
    
    // Add comment to the shared array
    doc.getArray('comments').push([comment]);
    
    return id;
  }
  
  async editComment(panel: NotebookPanel, commentId: string, text: string): Promise<boolean> {
    const doc = this._collaborationService.getYjsDocument(panel);
    if (!doc) {
      return false;
    }
    
    // Find the comment in the shared array
    const commentsArray = doc.getArray('comments');
    let index = -1;
    
    commentsArray.forEach((item: any, idx: number) => {
      if (item.id === commentId) {
        index = idx;
      }
    });
    
    if (index === -1) {
      return false;
    }
    
    // Check if user is the author of the comment
    const comment = commentsArray.get(index);
    const userId = PageConfig.getOption('userId') || `user-${Math.floor(Math.random() * 1000)}`;
    
    if (comment.authorId !== userId) {
      // Check if user has admin permission
      const permissionsService = app.serviceManager.services.get(IPermissionsService) as IPermissionsService;
      if (!permissionsService || !permissionsService.hasPermission(panel, 'admin')) {
        return false;
      }
    }
    
    // Update the comment
    const updatedComment = { ...comment, text };
    commentsArray.delete(index, 1);
    commentsArray.insert(index, [updatedComment]);
    
    return true;
  }
  
  async deleteComment(panel: NotebookPanel, commentId: string): Promise<boolean> {
    const doc = this._collaborationService.getYjsDocument(panel);
    if (!doc) {
      return false;
    }
    
    // Find the comment in the shared array
    const commentsArray = doc.getArray('comments');
    let index = -1;
    
    commentsArray.forEach((item: any, idx: number) => {
      if (item.id === commentId) {
        index = idx;
      }
    });
    
    if (index === -1) {
      return false;
    }
    
    // Check if user is the author of the comment
    const comment = commentsArray.get(index);
    const userId = PageConfig.getOption('userId') || `user-${Math.floor(Math.random() * 1000)}`;
    
    if (comment.authorId !== userId) {
      // Check if user has admin permission
      const permissionsService = app.serviceManager.services.get(IPermissionsService) as IPermissionsService;
      if (!permissionsService || !permissionsService.hasPermission(panel, 'admin')) {
        return false;
      }
    }
    
    // Delete the comment
    commentsArray.delete(index, 1);
    
    return true;
  }
  
  async resolveComment(panel: NotebookPanel, commentId: string): Promise<boolean> {
    const doc = this._collaborationService.getYjsDocument(panel);
    if (!doc) {
      return false;
    }
    
    // Find the comment in the shared array
    const commentsArray = doc.getArray('comments');
    let index = -1;
    
    commentsArray.forEach((item: any, idx: number) => {
      if (item.id === commentId) {
        index = idx;
      }
    });
    
    if (index === -1) {
      return false;
    }
    
    // Check if user has edit permission
    const permissionsService = app.serviceManager.services.get(IPermissionsService) as IPermissionsService;
    if (!permissionsService || !permissionsService.hasPermission(panel, 'edit')) {
      return false;
    }
    
    // Update the comment to mark it as resolved
    const comment = commentsArray.get(index);
    const updatedComment = { ...comment, resolved: true };
    commentsArray.delete(index, 1);
    commentsArray.insert(index, [updatedComment]);
    
    return true;
  }
  
  getComments(panel: NotebookPanel): Array<{ id: string, cellId: string, author: string, text: string, timestamp: number, resolved: boolean, range?: { start: number, end: number } }> {
    return [...this._comments.get(panel.id) || []];
  }
  
  get commentsChanged(): ISignal<ICommentService, { panel: NotebookPanel, comments: Array<{ id: string, cellId: string, author: string, text: string, timestamp: number, resolved: boolean, range?: { start: number, end: number } }> }> {
    return this._commentsChanged;
  }
  
  private _collaborationService: ICollaborationService;
  private _translator: ITranslator;
  private _comments: Map<string, Array<{ id: string, cellId: string, author: string, text: string, timestamp: number, resolved: boolean, range?: { start: number, end: number } }>>;
  private _commentsChanged: Signal<ICommentService, { panel: NotebookPanel, comments: Array<{ id: string, cellId: string, author: string, text: string, timestamp: number, resolved: boolean, range?: { start: number, end: number } }> }>;
}

// Import the history plugin
import historyPlugin from './historyPlugin';

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
  presenceService,
  lockService,
  historyService,
  permissionsService,
  commentService,
  historyPlugin
];

export default plugins;
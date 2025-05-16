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

// Import collaboration interfaces
import {
  ICollaborationProvider,
  YjsNotebookProvider
} from '@jupyterlab/notebook/lib/collab/provider';

import {
  IPresenceTracker,
  PresenceTracker,
  UserStatus
} from '@jupyterlab/notebook/lib/collab/awareness';

import {
  IPermissionManager,
  PermissionManager,
  DocumentRole
} from '@jupyterlab/notebook/lib/collab/permissions';

import {
  ICommentManager,
  CommentManager
} from '@jupyterlab/notebook/lib/collab/comments';

import {
  IVersionHistory,
  HistoryTracker
} from '@jupyterlab/notebook/lib/collab/history';

import { CellLockManager } from '@jupyterlab/notebook/lib/collab/locks';

// Import UI components
import { TrustedComponent } from './trusted';
// Import collaboration UI components
import { historyViewerPlugin } from './historyViewerPlugin';

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
   * A command to toggle collaboration mode
   */
  export const toggleCollaboration = 'notebook:toggle-collaboration';

  /**
   * A command to show the collaboration panel
   */
  export const showCollaborationPanel = 'notebook:show-collaboration-panel';

  /**
   * A command to create a version checkpoint
   */
  export const createVersionCheckpoint = 'notebook:create-version-checkpoint';

  /**
   * A command to show version history
   */
  export const showVersionHistory = 'notebook:show-version-history';

  /**
   * A command to restore a previous version
   */
  export const restoreVersion = 'notebook:restore-version';

  /**
   * A command to manage permissions
   */
  export const managePermissions = 'notebook:manage-permissions';

  /**
   * A command to lock a cell
   */
  export const lockCell = 'notebook:lock-cell';

  /**
   * A command to unlock a cell
   */
  export const unlockCell = 'notebook:unlock-cell';

  /**
   * A command to add a comment to a cell
   */
  export const addComment = 'notebook:add-comment';

  /**
   * A command to show comments for a cell
   */
  export const showComments = 'notebook:show-comments';
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
      label: trans.__('Open…'),
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
 * A plugin that provides the collaboration provider for notebooks.
 */
const collaborationProvider: JupyterFrontEndPlugin<ICollaborationProvider> = {
  id: '@jupyter-notebook/notebook-extension:collaboration-provider',
  description: 'A plugin that provides the collaboration provider for notebooks.',
  autoStart: true,
  provides: ICollaborationProvider,
  requires: [ISettingRegistry, ITranslator],
  optional: [INotebookShell],
  activate: (
    app: JupyterFrontEnd,
    settingRegistry: ISettingRegistry,
    translator: ITranslator,
    notebookShell: INotebookShell | null
  ): ICollaborationProvider => {
    const trans = translator.load('notebook');
    console.log(trans.__('Activating Jupyter Notebook Collaboration Provider'));

    // Create the collaboration provider
    const provider = new YjsNotebookProvider();

    // Load settings
    settingRegistry
      .load(collaborationProvider.id)
      .then(settings => {
        console.log('Loaded collaboration settings:', settings.composite);
        // Apply settings to the provider
      })
      .catch(error => {
        console.error('Failed to load collaboration settings:', error);
      });

    return provider;
  }
};

/**
 * A plugin that provides user presence tracking for collaborative notebooks.
 */
const presenceTracker: JupyterFrontEndPlugin<IPresenceTracker> = {
  id: '@jupyter-notebook/notebook-extension:presence-tracker',
  description: 'A plugin that provides user presence tracking for collaborative notebooks.',
  autoStart: true,
  provides: IPresenceTracker,
  requires: [ICollaborationProvider, ITranslator],
  optional: [INotebookShell],
  activate: (
    app: JupyterFrontEnd,
    collaborationProvider: ICollaborationProvider,
    translator: ITranslator,
    notebookShell: INotebookShell | null
  ): IPresenceTracker => {
    const trans = translator.load('notebook');
    console.log(trans.__('Activating Jupyter Notebook Presence Tracker'));

    // Create the presence tracker
    const tracker = new PresenceTracker(collaborationProvider.ydoc);

    // Set up user information
    // In a real implementation, this would get user info from JupyterHub
    const userName = 'User ' + Math.floor(Math.random() * 1000);
    const userColor = '#' + Math.floor(Math.random() * 16777215).toString(16);

    tracker.setLocalState({
      userId: collaborationProvider.ydoc.clientID.toString(),
      displayName: userName,
      status: UserStatus.Active,
      color: userColor,
      lastActivity: Date.now()
    });

    // Set up activity tracking
    const trackActivity = () => {
      tracker.markActive();
    };

    // Track user activity
    document.addEventListener('mousemove', trackActivity, { passive: true });
    document.addEventListener('keydown', trackActivity, { passive: true });

    // Clean up when the app is disposed
    app.disposed.connect(() => {
      document.removeEventListener('mousemove', trackActivity);
      document.removeEventListener('keydown', trackActivity);
      tracker.destroy();
    });

    return tracker;
  }
};

/**
 * A plugin that provides permission management for collaborative notebooks.
 */
const permissionManager: JupyterFrontEndPlugin<IPermissionManager> = {
  id: '@jupyter-notebook/notebook-extension:permission-manager',
  description: 'A plugin that provides permission management for collaborative notebooks.',
  autoStart: true,
  provides: IPermissionManager,
  requires: [ICollaborationProvider, ITranslator],
  optional: [INotebookShell],
  activate: (
    app: JupyterFrontEnd,
    collaborationProvider: ICollaborationProvider,
    translator: ITranslator,
    notebookShell: INotebookShell | null
  ): IPermissionManager => {
    const trans = translator.load('notebook');
    console.log(trans.__('Activating Jupyter Notebook Permission Manager'));

    // Create the permission manager
    const manager = new PermissionManager({
      // In a real implementation, this would get user info from JupyterHub
      currentUserId: collaborationProvider.ydoc.clientID.toString(),
      currentUserDisplayName: 'User ' + Math.floor(Math.random() * 1000),
      defaultRole: DocumentRole.Editor
    });

    // Clean up when the app is disposed
    app.disposed.connect(() => {
      manager.disconnectNotebook();
    });

    return manager;
  }
};

/**
 * A plugin that provides comment management for collaborative notebooks.
 */
const commentManager: JupyterFrontEndPlugin<ICommentManager> = {
  id: '@jupyter-notebook/notebook-extension:comment-manager',
  description: 'A plugin that provides comment management for collaborative notebooks.',
  autoStart: true,
  provides: ICommentManager,
  requires: [ICollaborationProvider, ITranslator],
  optional: [INotebookShell],
  activate: (
    app: JupyterFrontEnd,
    collaborationProvider: ICollaborationProvider,
    translator: ITranslator,
    notebookShell: INotebookShell | null
  ): ICommentManager => {
    const trans = translator.load('notebook');
    console.log(trans.__('Activating Jupyter Notebook Comment Manager'));

    // Create the comment manager
    const manager = new CommentManager({
      ydoc: collaborationProvider.ydoc,
      currentUser: {
        // In a real implementation, this would get user info from JupyterHub
        id: collaborationProvider.ydoc.clientID.toString(),
        name: 'User ' + Math.floor(Math.random() * 1000)
      }
    });

    // Clean up when the app is disposed
    app.disposed.connect(() => {
      manager.dispose();
    });

    return manager;
  }
};

/**
 * A plugin that provides version history tracking for collaborative notebooks.
 */
const versionHistory: JupyterFrontEndPlugin<IVersionHistory> = {
  id: '@jupyter-notebook/notebook-extension:version-history',
  description: 'A plugin that provides version history tracking for collaborative notebooks.',
  autoStart: true,
  provides: IVersionHistory,
  requires: [ICollaborationProvider, ITranslator],
  optional: [INotebookShell],
  activate: (
    app: JupyterFrontEnd,
    collaborationProvider: ICollaborationProvider,
    translator: ITranslator,
    notebookShell: INotebookShell | null
  ): IVersionHistory => {
    const trans = translator.load('notebook');
    console.log(trans.__('Activating Jupyter Notebook Version History'));

    // Create the history tracker
    const tracker = new HistoryTracker({
      currentUser: {
        // In a real implementation, this would get user info from JupyterHub
        id: collaborationProvider.ydoc.clientID.toString(),
        name: 'User ' + Math.floor(Math.random() * 1000)
      },
      autoSnapshot: true,
      snapshotInterval: 60000 // 1 minute
    });

    // Clean up when the app is disposed
    app.disposed.connect(() => {
      tracker.disconnectDocument(null);
    });

    return tracker;
  }
};

/**
 * A plugin that provides cell locking for collaborative notebooks.
 */
const cellLocking: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:cell-locking',
  description: 'A plugin that provides cell locking for collaborative notebooks.',
  autoStart: true,
  requires: [ICollaborationProvider, IPermissionManager, INotebookTracker, ITranslator],
  optional: [INotebookShell],
  activate: (
    app: JupyterFrontEnd,
    collaborationProvider: ICollaborationProvider,
    permissionManager: IPermissionManager,
    notebookTracker: INotebookTracker,
    translator: ITranslator,
    notebookShell: INotebookShell | null
  ): void => {
    const trans = translator.load('notebook');
    console.log(trans.__('Activating Jupyter Notebook Cell Locking'));

    // Create a map to store lock managers for each notebook
    const lockManagers = new Map<string, CellLockManager>();

    // Function to create a lock manager for a notebook
    const createLockManager = (panel: NotebookPanel) => {
      if (!panel.model || !panel.model.isCollaborative) {
        return null;
      }

      const lockManager = new CellLockManager({
        doc: collaborationProvider.ydoc,
        permissionManager: permissionManager
      });

      // Store the lock manager
      lockManagers.set(panel.id, lockManager);

      // Set up lock event handling
      lockManager.onLockEvent(event => {
        console.log('Lock event:', event);
        // Update UI to reflect lock state
      });

      return lockManager;
    };

    // Track notebook changes
    notebookTracker.widgetAdded.connect((sender, panel) => {
      // Create a lock manager for this notebook
      const lockManager = createLockManager(panel);

      // Clean up when the panel is disposed
      panel.disposed.connect(() => {
        const manager = lockManagers.get(panel.id);
        if (manager) {
          manager.dispose();
          lockManagers.delete(panel.id);
        }
      });
    });

    // Add commands for locking/unlocking cells
    app.commands.addCommand(CommandIDs.lockCell, {
      label: trans.__('Lock Cell'),
      execute: () => {
        const panel = notebookTracker.currentWidget;
        if (!panel) {
          return;
        }

        const activeCell = panel.content.activeCell;
        if (!activeCell) {
          return;
        }

        const lockManager = lockManagers.get(panel.id);
        if (!lockManager) {
          return;
        }

        lockManager.acquireLock(
          activeCell.model.id,
          permissionManager.currentUserId,
          permissionManager.currentUserDisplayName
        );
      },
      isEnabled: () => {
        const panel = notebookTracker.currentWidget;
        if (!panel || !panel.model || !panel.model.isCollaborative) {
          return false;
        }
        return true;
      }
    });

    app.commands.addCommand(CommandIDs.unlockCell, {
      label: trans.__('Unlock Cell'),
      execute: () => {
        const panel = notebookTracker.currentWidget;
        if (!panel) {
          return;
        }

        const activeCell = panel.content.activeCell;
        if (!activeCell) {
          return;
        }

        const lockManager = lockManagers.get(panel.id);
        if (!lockManager) {
          return;
        }

        lockManager.releaseLock(
          activeCell.model.id,
          permissionManager.currentUserId
        );
      },
      isEnabled: () => {
        const panel = notebookTracker.currentWidget;
        if (!panel || !panel.model || !panel.model.isCollaborative) {
          return false;
        }

        const activeCell = panel.content.activeCell;
        if (!activeCell) {
          return false;
        }

        const lockManager = lockManagers.get(panel.id);
        if (!lockManager) {
          return false;
        }

        return lockManager.isLockedByUser(
          activeCell.model.id,
          permissionManager.currentUserId
        );
      }
    });
  }
};

/**
 * A plugin that adds collaboration UI components to the notebook.
 */
const collaborationUI: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:collaboration-ui',
  description: 'A plugin that adds collaboration UI components to the notebook.',
  autoStart: true,
  requires: [
    ICollaborationProvider,
    IPresenceTracker,
    IPermissionManager,
    ICommentManager,
    IVersionHistory,
    INotebookTracker,
    ITranslator
  ],
  optional: [INotebookShell, ICommandPalette],
  activate: (
    app: JupyterFrontEnd,
    collaborationProvider: ICollaborationProvider,
    presenceTracker: IPresenceTracker,
    permissionManager: IPermissionManager,
    commentManager: ICommentManager,
    versionHistory: IVersionHistory,
    notebookTracker: INotebookTracker,
    translator: ITranslator,
    notebookShell: INotebookShell | null,
    palette: ICommandPalette | null
  ): void => {
    const trans = translator.load('notebook');
    console.log(trans.__('Activating Jupyter Notebook Collaboration UI'));

    // Add commands for collaboration features
    app.commands.addCommand(CommandIDs.toggleCollaboration, {
      label: trans.__('Toggle Collaboration Mode'),
      execute: () => {
        const panel = notebookTracker.currentWidget;
        if (!panel) {
          return;
        }

        // Toggle collaboration mode
        // This would need to be implemented in the notebook model
        console.log('Toggling collaboration mode');
      },
      isEnabled: () => notebookTracker.currentWidget !== null
    });

    app.commands.addCommand(CommandIDs.showCollaborationPanel, {
      label: trans.__('Show Collaboration Panel'),
      execute: () => {
        // Show the collaboration panel
        console.log('Showing collaboration panel');
      },
      isEnabled: () => {
        const panel = notebookTracker.currentWidget;
        return panel !== null && panel.model?.isCollaborative === true;
      }
    });

    app.commands.addCommand(CommandIDs.createVersionCheckpoint, {
      label: trans.__('Create Version Checkpoint'),
      execute: async () => {
        // Create a version checkpoint
        const panel = notebookTracker.currentWidget;
        if (!panel || !panel.model || !panel.model.isCollaborative) {
          return;
        }

        await versionHistory.createVersion(
          'Manual checkpoint',
          true,
          { source: 'user' }
        );
        console.log('Created version checkpoint');
      },
      isEnabled: () => {
        const panel = notebookTracker.currentWidget;
        return panel !== null && panel.model?.isCollaborative === true;
      }
    });

    app.commands.addCommand(CommandIDs.showVersionHistory, {
      label: trans.__('Show Version History'),
      execute: () => {
        // Show version history
        console.log('Showing version history');
      },
      isEnabled: () => {
        const panel = notebookTracker.currentWidget;
        return panel !== null && panel.model?.isCollaborative === true;
      }
    });

    app.commands.addCommand(CommandIDs.managePermissions, {
      label: trans.__('Manage Collaboration Permissions'),
      execute: () => {
        // Show permissions dialog
        console.log('Managing permissions');
      },
      isEnabled: () => {
        const panel = notebookTracker.currentWidget;
        if (!panel || !panel.model || !panel.model.isCollaborative) {
          return false;
        }
        return permissionManager.isAdmin;
      }
    });

    app.commands.addCommand(CommandIDs.addComment, {
      label: trans.__('Add Comment to Cell'),
      execute: () => {
        const panel = notebookTracker.currentWidget;
        if (!panel) {
          return;
        }

        const activeCell = panel.content.activeCell;
        if (!activeCell) {
          return;
        }

        // Create a new comment thread for this cell
        const thread = commentManager.createThread(activeCell.model.id);
        commentManager.addComment(thread.id, 'New comment');
        console.log('Added comment to cell');
      },
      isEnabled: () => {
        const panel = notebookTracker.currentWidget;
        if (!panel || !panel.model || !panel.model.isCollaborative) {
          return false;
        }
        return panel.content.activeCell !== null && permissionManager.canComment;
      }
    });

    app.commands.addCommand(CommandIDs.showComments, {
      label: trans.__('Show Cell Comments'),
      execute: () => {
        const panel = notebookTracker.currentWidget;
        if (!panel) {
          return;
        }

        const activeCell = panel.content.activeCell;
        if (!activeCell) {
          return;
        }

        // Show comments for this cell
        const threads = commentManager.getThreadsForCell(activeCell.model.id);
        console.log('Cell comments:', threads);
      },
      isEnabled: () => {
        const panel = notebookTracker.currentWidget;
        if (!panel || !panel.model || !panel.model.isCollaborative) {
          return false;
        }
        return panel.content.activeCell !== null;
      }
    });

    // Add commands to palette
    if (palette) {
      const category = 'Notebook Collaboration';
      palette.addItem({ command: CommandIDs.toggleCollaboration, category });
      palette.addItem({ command: CommandIDs.showCollaborationPanel, category });
      palette.addItem({ command: CommandIDs.createVersionCheckpoint, category });
      palette.addItem({ command: CommandIDs.showVersionHistory, category });
      palette.addItem({ command: CommandIDs.managePermissions, category });
      palette.addItem({ command: CommandIDs.lockCell, category });
      palette.addItem({ command: CommandIDs.unlockCell, category });
      palette.addItem({ command: CommandIDs.addComment, category });
      palette.addItem({ command: CommandIDs.showComments, category });
    }

    // Connect to notebook tracker to add UI components when a notebook is opened
    notebookTracker.widgetAdded.connect((sender, panel) => {
      // When a notebook is opened, connect it to the collaboration provider
      panel.sessionContext.ready.then(() => {
        if (panel.model && collaborationProvider) {
          // Connect the notebook model to the collaboration provider
          collaborationProvider.connectDocument(panel.model);
          
          // Connect the notebook model to other collaboration services
          permissionManager.connectNotebook(panel.model);
          versionHistory.connectDocument(panel.model);

          // Add UI components for collaboration
          // These would be implemented in separate files
          // addCollaborationUI(panel, collaborationProvider, presenceTracker, permissionManager, commentManager, versionHistory);
        }
      });

      // Clean up when the panel is disposed
      panel.disposed.connect(() => {
        if (panel.model && collaborationProvider) {
          collaborationProvider.disconnectDocument(panel.model);
          permissionManager.disconnectNotebook();
          versionHistory.disconnectDocument(panel.model);
        }
      });
    });
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
  collaborationProvider,
  presenceTracker,
  permissionManager,
  commentManager,
  versionHistory,
  cellLocking,
  collaborationUI,
  historyViewerPlugin
];

export default plugins;

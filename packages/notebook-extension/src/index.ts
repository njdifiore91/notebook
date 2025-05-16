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

import {
  ICollaborationProvider,
  YjsNotebookProvider
} from '@jupyterlab/notebook/lib/collab/provider';

import {
  IPresenceTracker,
  PresenceTracker
} from '@jupyterlab/notebook/lib/collab/awareness';

import {
  IPermissionManager,
  PermissionManager
} from '@jupyterlab/notebook/lib/collab/permissions';

import {
  ICommentManager,
  CommentManager
} from '@jupyterlab/notebook/lib/collab/comments';

import {
  IVersionHistory,
  HistoryTracker
} from '@jupyterlab/notebook/lib/collab/history';

import {
  ICellLockManager,
  CellLockManager
} from '@jupyterlab/notebook/lib/collab/locks';

import { ISettingRegistry } from '@jupyterlab/settingregistry';

import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import { INotebookShell } from '@jupyter-notebook/application';

import { Poll } from '@lumino/polling';

import { Widget } from '@lumino/widgets';

import { TrustedComponent } from './trusted';

// Import collaboration UI components
import { CollaborationBar } from './components/collaborationBar';
import { UserPresence } from './components/userPresence';

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
   * Commands for collaboration features
   */
  export const openPermissions = 'collaboration:open-permissions';
  export const openComments = 'collaboration:open-comments';
  export const openHistory = 'collaboration:open-history';
  export const toggleCollaboration = 'collaboration:toggle';
  export const acquireCellLock = 'collaboration:acquire-cell-lock';
  export const releaseCellLock = 'collaboration:release-cell-lock';
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
  activate: (app: JupyterFrontEnd): ICollaborationProvider => {
    console.log('Activating Collaboration Provider');
    
    // Create the collaboration provider
    const provider = new YjsNotebookProvider();
    
    return provider;
  }
};

/**
 * A plugin that provides the presence tracker for collaborative editing.
 */
const presenceTracker: JupyterFrontEndPlugin<IPresenceTracker> = {
  id: '@jupyter-notebook/notebook-extension:presence-tracker',
  description: 'A plugin that provides the presence tracker for collaborative editing.',
  autoStart: true,
  provides: IPresenceTracker,
  requires: [ICollaborationProvider],
  activate: (app: JupyterFrontEnd, collaborationProvider: ICollaborationProvider): IPresenceTracker => {
    console.log('Activating Presence Tracker');
    
    // Create the presence tracker
    const tracker = new PresenceTracker(collaborationProvider.ydoc);
    
    return tracker;
  }
};

/**
 * A plugin that provides the permission manager for collaborative editing.
 */
const permissionManager: JupyterFrontEndPlugin<IPermissionManager> = {
  id: '@jupyter-notebook/notebook-extension:permission-manager',
  description: 'A plugin that provides the permission manager for collaborative editing.',
  autoStart: true,
  provides: IPermissionManager,
  activate: (app: JupyterFrontEnd): IPermissionManager => {
    console.log('Activating Permission Manager');
    
    // Create the permission manager
    const manager = new PermissionManager();
    
    return manager;
  }
};

/**
 * A plugin that provides the comment manager for collaborative editing.
 */
const commentManager: JupyterFrontEndPlugin<ICommentManager> = {
  id: '@jupyter-notebook/notebook-extension:comment-manager',
  description: 'A plugin that provides the comment manager for collaborative editing.',
  autoStart: true,
  provides: ICommentManager,
  activate: (app: JupyterFrontEnd): ICommentManager => {
    console.log('Activating Comment Manager');
    
    // Create the comment manager
    const manager = new CommentManager();
    
    return manager;
  }
};

/**
 * A plugin that provides the version history tracker for collaborative editing.
 */
const versionHistory: JupyterFrontEndPlugin<IVersionHistory> = {
  id: '@jupyter-notebook/notebook-extension:version-history',
  description: 'A plugin that provides the version history tracker for collaborative editing.',
  autoStart: true,
  provides: IVersionHistory,
  requires: [ICollaborationProvider, INotebookTracker],
  activate: (app: JupyterFrontEnd, collaborationProvider: ICollaborationProvider, notebookTracker: INotebookTracker): IVersionHistory => {
    console.log('Activating Version History');
    
    // Create the history tracker with the current notebook model
    const currentNotebook = notebookTracker.currentWidget?.content.model || null;
    const tracker = new HistoryTracker({
      collaborationProvider,
      notebookModel: currentNotebook
    });
    
    // Update the notebook model when the current notebook changes
    notebookTracker.currentChanged.connect((_, notebook) => {
      if (notebook) {
        (tracker as any)._notebookModel = notebook.content.model;
      }
    });
    
    return tracker;
  }
};

/**
 * A plugin that provides the cell lock manager for collaborative editing.
 */
const cellLockManager: JupyterFrontEndPlugin<ICellLockManager> = {
  id: '@jupyter-notebook/notebook-extension:cell-lock-manager',
  description: 'A plugin that provides the cell lock manager for collaborative editing.',
  autoStart: true,
  provides: ICellLockManager,
  activate: (app: JupyterFrontEnd): ICellLockManager => {
    console.log('Activating Cell Lock Manager');
    
    // Create the cell lock manager
    const manager = new CellLockManager();
    
    return manager;
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
    INotebookTracker,
    ICollaborationProvider,
    IPresenceTracker,
    IPermissionManager,
    ICommentManager,
    IVersionHistory,
    ICellLockManager
  ],
  optional: [INotebookShell, ICommandPalette],
  activate: (
    app: JupyterFrontEnd,
    notebookTracker: INotebookTracker,
    collaborationProvider: ICollaborationProvider,
    presenceTracker: IPresenceTracker,
    permissionManager: IPermissionManager,
    commentManager: ICommentManager,
    versionHistory: IVersionHistory,
    cellLockManager: ICellLockManager,
    notebookShell: INotebookShell | null,
    palette: ICommandPalette | null
  ) => {
    console.log('Activating Collaboration UI');
    
    // Add the collaboration bar style to the document
    document.head.appendChild(CollaborationBar.createStyle());
    
    // Add the user presence style to the document
    document.head.appendChild(UserPresence.createStyle());
    
    // Import and add the permissions dialog style to the document
    import('./components/permissionsDialog').then(module => {
      document.head.appendChild(module.PermissionsDialog.createStyle());
    });
    
    // Register commands for collaboration features
    app.commands.addCommand(CommandIDs.openPermissions, {
      label: 'Manage Collaboration Permissions',
      execute: () => {
        const current = notebookTracker.currentWidget;
        if (!current) {
          return;
        }
        
        // Import the PermissionsDialog dynamically to avoid circular dependencies
        import('./components/permissionsDialog').then(module => {
          module.PermissionsDialog.showDialog({
            permissionManager,
            notebookPanel: current,
            translator: app.translator
          });
        });
      },
      isEnabled: () => notebookTracker.currentWidget !== null
    });
    
    app.commands.addCommand(CommandIDs.openComments, {
      label: 'View Comments',
      execute: () => {
        // Implementation will be added when the comments panel component is created
        console.log('Open comments panel');
      },
      isEnabled: () => notebookTracker.currentWidget !== null
    });
    
    app.commands.addCommand(CommandIDs.openHistory, {
      label: 'View Version History',
      execute: () => {
        // Implementation will be added when the history viewer component is created
        console.log('Open history viewer');
      },
      isEnabled: () => notebookTracker.currentWidget !== null
    });
    
    app.commands.addCommand(CommandIDs.toggleCollaboration, {
      label: 'Enable Collaborative Editing',
      execute: () => {
        const current = notebookTracker.currentWidget;
        if (!current) {
          return;
        }
        
        // Toggle collaboration on the current notebook
        const model = current.content.model;
        if (model.collaborationProvider) {
          // Disconnect if already connected
          model.collaborationProvider.disconnectDocument(model);
        } else {
          // Connect if not already connected
          collaborationProvider.connectDocument(model);
        }
      },
      isEnabled: () => notebookTracker.currentWidget !== null,
      isToggled: () => {
        const current = notebookTracker.currentWidget;
        return current ? !!current.content.model.collaborationProvider : false;
      }
    });
    
    app.commands.addCommand(CommandIDs.acquireCellLock, {
      label: 'Acquire Cell Lock',
      execute: async () => {
        const current = notebookTracker.currentWidget;
        if (!current) {
          return;
        }
        
        const activeCell = current.content.activeCell;
        if (!activeCell) {
          return;
        }
        
        // Acquire lock on the active cell
        await cellLockManager.acquireLock(activeCell.model.id);
      },
      isEnabled: () => {
        const current = notebookTracker.currentWidget;
        const activeCell = current?.content.activeCell;
        return !!activeCell && !cellLockManager.isLockedByCurrentUser(activeCell.model.id);
      }
    });
    
    app.commands.addCommand(CommandIDs.releaseCellLock, {
      label: 'Release Cell Lock',
      execute: async () => {
        const current = notebookTracker.currentWidget;
        if (!current) {
          return;
        }
        
        const activeCell = current.content.activeCell;
        if (!activeCell) {
          return;
        }
        
        // Release lock on the active cell
        await cellLockManager.releaseLock(activeCell.model.id);
      },
      isEnabled: () => {
        const current = notebookTracker.currentWidget;
        const activeCell = current?.content.activeCell;
        return !!activeCell && cellLockManager.isLockedByCurrentUser(activeCell.model.id);
      }
    });
    
    // Add commands to the palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.toggleCollaboration,
        category: 'Collaboration'
      });
      
      palette.addItem({
        command: CommandIDs.openPermissions,
        category: 'Collaboration'
      });
      
      palette.addItem({
        command: CommandIDs.openComments,
        category: 'Collaboration'
      });
      
      palette.addItem({
        command: CommandIDs.openHistory,
        category: 'Collaboration'
      });
      
      palette.addItem({
        command: CommandIDs.acquireCellLock,
        category: 'Collaboration'
      });
      
      palette.addItem({
        command: CommandIDs.releaseCellLock,
        category: 'Collaboration'
      });
    }
    
    // Add collaboration UI components when a notebook is opened
    notebookTracker.widgetAdded.connect((_, notebook) => {
      // Connect the collaboration provider to the notebook model
      notebook.context.ready.then(() => {
        // Create and add the collaboration bar
        if (notebookShell) {
          const collaborationBarWidget = CollaborationBar.create({
            collaborationProvider,
            presenceTracker,
            notebookPanel: notebook,
            commands: app.commands
          });
          
          notebookShell.add(collaborationBarWidget, 'top', {
            rank: 10_000
          });
        }
        
        // Create and add the user presence visualization
        const userPresenceWidget = UserPresence.create({
          presenceTracker,
          notebookPanel: notebook
        });
        
        notebook.content.node.appendChild(userPresenceWidget.node);
        
        // Connect the permission manager to the notebook model
        permissionManager.connectNotebook(notebook.content.model);
        
        // Connect the comment manager to the notebook model
        commentManager.connectNotebook(notebook.content.model, permissionManager);
        
        // Connect the cell lock manager to the notebook model
        cellLockManager.connectNotebook(
          notebook.content.model,
          permissionManager,
          presenceTracker
        );
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
  cellLockManager,
  collaborationUI
];

export default plugins;

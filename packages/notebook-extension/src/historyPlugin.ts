// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ICommandPalette, IToolbarWidgetRegistry } from '@jupyterlab/apputils';

import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';

import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import { INotebookShell } from '@jupyter-notebook/application';

import { Widget } from '@lumino/widgets';

import { HistoryViewer } from './components/historyViewer';
import { IHistoryService } from './services/history';

/**
 * The command IDs used by the history plugin.
 */
namespace CommandIDs {
  export const showHistory = 'notebook:show-history';
}

/**
 * A plugin that provides the history viewer for collaborative notebooks.
 */
const historyPlugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:history',
  description: 'A plugin that provides the history viewer for collaborative notebooks.',
  autoStart: true,
  requires: [INotebookTracker, IHistoryService],
  optional: [ICommandPalette, IToolbarWidgetRegistry, ITranslator, INotebookShell],
  activate: (
    app: JupyterFrontEnd,
    notebookTracker: INotebookTracker,
    historyService: IHistoryService,
    palette?: ICommandPalette,
    toolbarRegistry?: IToolbarWidgetRegistry,
    translator?: ITranslator,
    notebookShell?: INotebookShell
  ) => {
    const trans = (translator ?? nullTranslator).load('notebook');
    let historyWidget: Widget | null = null;

    /**
     * Create and show the history viewer for the current notebook.
     */
    const showHistoryViewer = (notebookPanel: NotebookPanel) => {
      // If the history viewer is already open, close it
      if (historyWidget) {
        historyWidget.dispose();
        historyWidget = null;
        return;
      }

      // Create the history viewer widget
      historyWidget = HistoryViewer.createWidget({
        notebookPanel,
        historyService,
        translator,
        onClose: () => {
          if (historyWidget) {
            historyWidget.dispose();
            historyWidget = null;
          }
        }
      });

      // Add the history viewer to the shell
      if (notebookShell) {
        notebookShell.add(historyWidget, 'main', {
          mode: 'split-right',
          rank: 1000
        });
      } else {
        app.shell.add(historyWidget, 'main', {
          mode: 'split-right',
          rank: 1000
        });
      }

      // Activate the history viewer
      if (notebookShell) {
        notebookShell.activateById(historyWidget.id);
      } else {
        app.shell.activateById(historyWidget.id);
      }
    };

    // Add the command to show the history viewer
    app.commands.addCommand(CommandIDs.showHistory, {
      label: trans.__('Show Version History'),
      execute: () => {
        const current = notebookTracker.currentWidget;
        if (current) {
          showHistoryViewer(current);
        }
      },
      isEnabled: () => notebookTracker.currentWidget !== null
    });

    // Add the command to the palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.showHistory,
        category: 'Notebook Collaboration'
      });
    }

    // Add a button to the toolbar
    if (toolbarRegistry) {
      toolbarRegistry.addFactory('Notebook', 'history', (toolbar) => {
        const button = new Widget();
        button.node.className = 'jp-HistoryButton jp-Toolbar-item';
        button.node.title = trans.__('Show Version History');
        button.node.innerHTML = '<span class="jp-HistoryButtonIcon"></span>';
        button.node.onclick = () => {
          app.commands.execute(CommandIDs.showHistory);
        };
        return button;
      });
    }
  }
};

export default historyPlugin;
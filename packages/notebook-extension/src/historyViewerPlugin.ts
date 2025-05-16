// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import {
  ICommandPalette,
  IToolbarWidgetRegistry,
  WidgetTracker
} from '@jupyterlab/apputils';

import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';

import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import { IVersionHistory } from '@jupyterlab/notebook';

import { INotebookShell } from '@jupyter-notebook/application';

import { HistoryViewer } from './components/historyViewer';

/**
 * The command IDs used by the history viewer plugin.
 */
namespace CommandIDs {
  export const openHistoryViewer = 'notebook:open-history-viewer';
}

/**
 * A plugin for the notebook version history viewer.
 */
export const historyViewerPlugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-notebook/notebook-extension:history-viewer',
  description: 'A plugin for viewing notebook version history.',
  autoStart: true,
  requires: [INotebookTracker],
  optional: [ICommandPalette, IToolbarWidgetRegistry, ITranslator, INotebookShell, IVersionHistory],
  activate: (
    app: JupyterFrontEnd,
    notebookTracker: INotebookTracker,
    palette: ICommandPalette | null,
    toolbarRegistry: IToolbarWidgetRegistry | null,
    translator: ITranslator | null,
    notebookShell: INotebookShell | null,
    versionHistory: IVersionHistory | null
  ) => {
    const trans = (translator ?? nullTranslator).load('jupyterlab');
    
    // Track history viewer widgets
    const historyViewerTracker = new WidgetTracker<HistoryViewer.ReactWidget>({
      namespace: 'history-viewer'
    });

    // Add command to open history viewer
    app.commands.addCommand(CommandIDs.openHistoryViewer, {
      label: trans.__('Version History'),
      execute: () => {
        // Get the current notebook panel
        const current = notebookTracker.currentWidget;
        if (!current) {
          return;
        }

        // Check if version history service is available
        if (!versionHistory) {
          console.warn('Version history service is not available');
          return;
        }

        // Create a unique ID for the history viewer
        const id = `history-viewer-${current.id}`;

        // Check if a history viewer is already open for this notebook
        const existingWidget = historyViewerTracker.find(widget => widget.id === id);
        if (existingWidget) {
          // If it exists, activate it
          if (notebookShell) {
            notebookShell.activateById(existingWidget.id);
          } else {
            app.shell.activateById(existingWidget.id);
          }
          return;
        }

        // Create a new history viewer widget
        const historyViewerWidget = HistoryViewer.createWidget({
          notebookPanel: current,
          versionHistory,
          translator: translator || undefined,
          onClose: () => {
            // Close the widget when the close button is clicked
            if (notebookShell) {
              notebookShell.remove(historyViewerWidget);
            } else {
              app.shell.remove(historyViewerWidget);
            }
          }
        });

        // Set the widget ID and add it to the tracker
        historyViewerWidget.id = id;
        historyViewerWidget.title.label = trans.__('Version History');
        historyViewerWidget.title.closable = true;

        // Add the widget to the shell
        if (notebookShell) {
          notebookShell.add(historyViewerWidget, 'main', { mode: 'split-right' });
          notebookShell.activateById(historyViewerWidget.id);
        } else {
          app.shell.add(historyViewerWidget, 'main', { mode: 'split-right' });
          app.shell.activateById(historyViewerWidget.id);
        }

        // Add the widget to the tracker
        void historyViewerTracker.add(historyViewerWidget);
      },
      isEnabled: () => {
        // Only enable if a notebook is active and version history is available
        return !!notebookTracker.currentWidget && !!versionHistory;
      }
    });

    // Add the command to the palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.openHistoryViewer,
        category: 'Notebook Operations'
      });
    }

    // Add a button to the notebook toolbar
    if (toolbarRegistry) {
      toolbarRegistry.addFactory('Notebook', 'historyViewer', (toolbar) => {
        const button = document.createElement('button');
        button.className = 'jp-HistoryViewer-toolbarButton jp-Button';
        button.title = trans.__('View Version History');
        button.onclick = () => {
          app.commands.execute(CommandIDs.openHistoryViewer);
        };
        
        // Add an icon to the button
        const icon = document.createElement('span');
        icon.className = 'jp-HistoryViewerIcon jp-Icon jp-Icon-16';
        button.appendChild(icon);
        
        return button;
      });
    }
  }
};

export default historyViewerPlugin;
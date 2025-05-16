// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { INotebookModel } from '../model';
import { ISignal, Signal } from '@lumino/signaling';
import { Token } from '@lumino/coreutils';
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { awareness } from 'y-protocols/awareness';
import { PageConfig } from '@jupyterlab/coreutils';
import { ICellModel, ICodeCellModel } from '@jupyterlab/cells';

/**
 * The collaboration provider token.
 *
 * This token is used to provide a collaboration provider to the notebook.
 * The collaboration provider is responsible for synchronizing the notebook
 * content between multiple clients using the Yjs CRDT framework.
 */
export const ICollaborationProvider = new Token<ICollaborationProvider>(
  '@jupyterlab/notebook:ICollaborationProvider'
);

/**
 * An interface for a collaboration provider.
 *
 * The collaboration provider is responsible for synchronizing the notebook
 * content between multiple clients using the Yjs CRDT framework. It provides
 * methods for connecting to a collaborative session, managing user presence,
 * and handling document synchronization.
 */
export interface ICollaborationProvider {
  /**
   * A signal emitted when remote changes are received.
   */
  readonly remoteChangesSignal: ISignal<ICollaborationProvider, void>;

  /**
   * A signal emitted when the connection status changes.
   */
  readonly connectionStatusChanged: ISignal<
    ICollaborationProvider,
    ConnectionStatus
  >;

  /**
   * The current connection status.
   */
  readonly connectionStatus: ConnectionStatus;

  /**
   * The Yjs document used for collaboration.
   */
  readonly ydoc: Y.Doc;

  /**
   * The awareness instance for tracking user presence.
   */
  readonly awareness: awareness.Awareness;

  /**
   * Connect to a collaborative session for the given document.
   *
   * @param document - The notebook model to connect.
   */
  connectDocument(document: INotebookModel): void;

  /**
   * Disconnect from a collaborative session.
   *
   * @param document - The notebook model to disconnect.
   */
  disconnectDocument(document: INotebookModel): void;

  /**
   * Set the user's awareness state.
   *
   * @param state - The awareness state to set.
   */
  setAwarenessState(state: Record<string, any>): void;

  /**
   * Get the awareness states of all users.
   *
   * @returns A map of user IDs to awareness states.
   */
  getAwarenessStates(): Map<number, Record<string, any>>;

  /**
   * Get the document ID for the current session.
   *
   * @returns The document ID.
   */
  getDocumentId(): string;

  /**
   * Destroy the provider and clean up resources.
   */
  destroy(): void;
}

/**
 * The connection status for a collaboration session.
 *
 * This enum represents the possible connection states of the collaboration
 * provider's WebSocket connection to the server.
 */
export enum ConnectionStatus {
  /**
   * The session is disconnected.
   */
  Disconnected = 'disconnected',

  /**
   * The session is connecting.
   */
  Connecting = 'connecting',

  /**
   * The session is connected.
   */
  Connected = 'connected',
}

/**
 * Options for the YjsNotebookProvider.
 *
 * These options configure the behavior of the YjsNotebookProvider, including
 * the WebSocket URL, document ID, and user information for awareness.
 */
export interface IYjsNotebookProviderOptions {
  /**
   * The WebSocket URL to connect to.
   */
  websocketUrl?: string;

  /**
   * The document ID to use for the session.
   */
  documentId?: string;

  /**
   * The user name to use for awareness.
   */
  userName?: string;

  /**
   * The user color to use for awareness.
   */
  userColor?: string;
}

/**
 * A Yjs-based implementation of a collaboration provider for Jupyter Notebook.
 *
 * This class implements the ICollaborationProvider interface using the Yjs CRDT
 * framework. It provides real-time synchronization of notebook content between
 * multiple clients, including:
 *
 * - Cell content (code, markdown, raw)
 * - Cell outputs
 * - Cell metadata
 * - Notebook metadata
 * - User presence and awareness
 *
 * The provider establishes a WebSocket connection to the server for real-time
 * updates and handles the synchronization of changes between the notebook model
 * and the Yjs document.
 *
 * Example usage:
 *
 * ```typescript
 * // Create a new provider
 * const provider = new YjsNotebookProvider({
 *   documentId: 'my-notebook',
 *   userName: 'John Doe'
 * });
 *
 * // Connect to a notebook model
 * provider.connectDocument(notebookModel);
 *
 * // Set user awareness state
 * provider.setAwarenessState({
 *   cursor: { path: [0], offset: 10 }
 * });
 *
 * // Get awareness states of all users
 * const states = provider.getAwarenessStates();
 *
 * // Disconnect when done
 * provider.disconnectDocument(notebookModel);
 * provider.destroy();
 * ```
 */
export class YjsNotebookProvider implements ICollaborationProvider {
  /**
   * Construct a new YjsNotebookProvider.
   *
   * @param options - The options for the provider.
   */
  constructor(options: IYjsNotebookProviderOptions = {}) {
    // Create a new Yjs document
    this._ydoc = new Y.Doc();

    // Create awareness instance for user presence
    this._awareness = new awareness.Awareness(this._ydoc);

    // Set up document ID
    this._documentId = options.documentId || this._generateDocumentId();

    // Set up WebSocket URL
    const websocketUrl = options.websocketUrl || this._getDefaultWebsocketUrl();

    // Create WebSocket provider
    this._websocketProvider = new WebsocketProvider(
      websocketUrl,
      this._documentId,
      this._ydoc,
      { awareness: this._awareness }
    );

    // Set up connection status handling
    this._websocketProvider.on('status', (event: { status: string }) => {
      let status: ConnectionStatus;
      switch (event.status) {
        case 'connected':
          status = ConnectionStatus.Connected;
          break;
        case 'connecting':
          status = ConnectionStatus.Connecting;
          break;
        case 'disconnected':
          status = ConnectionStatus.Disconnected;
          break;
        default:
          status = ConnectionStatus.Disconnected;
      }
      this._connectionStatus = status;
      this._connectionStatusChanged.emit(status);
    });

    // Set up awareness state
    const userName = options.userName || 'Anonymous';
    const userColor = options.userColor || this._getRandomColor();

    this._awareness.setLocalStateField('user', {
      name: userName,
      color: userColor,
    });

    // Set up document change handling
    this._ydoc.on('update', (update: Uint8Array, origin: any) => {
      // Only emit signal for remote changes
      if (origin !== this) {
        this._remoteChangesSignal.emit(void 0);
      }
    });

    // Set up awareness change handling
    this._awareness.on('change', () => {
      // Handle awareness changes if needed
    });

    // Initialize shared data structures
    this._initializeSharedTypes();

    // Set up Yjs document observation
    this._ydoc.on('afterTransaction', (transaction: Y.Transaction) => {
      // Only process remote changes
      if (transaction.origin !== this) {
        const events = Array.from(transaction.changed.keys()).map(type => {
          return {
            target: type,
            changes: transaction.changed.get(type)
          };
        });
        this._onYDocChanged(events);
      }
    });
  }

  /**
   * A signal emitted when remote changes are received.
   */
  get remoteChangesSignal(): ISignal<ICollaborationProvider, void> {
    return this._remoteChangesSignal;
  }

  /**
   * A signal emitted when the connection status changes.
   */
  get connectionStatusChanged(): ISignal<
    ICollaborationProvider,
    ConnectionStatus
  > {
    return this._connectionStatusChanged;
  }

  /**
   * The current connection status.
   */
  get connectionStatus(): ConnectionStatus {
    return this._connectionStatus;
  }

  /**
   * The Yjs document used for collaboration.
   */
  get ydoc(): Y.Doc {
    return this._ydoc;
  }

  /**
   * The awareness instance for tracking user presence.
   */
  get awareness(): awareness.Awareness {
    return this._awareness;
  }

  /**
   * Connect to a collaborative session for the given document.
   *
   * @param document - The notebook model to connect.
   */
  connectDocument(document: INotebookModel): void {
    if (this._connectedDocument === document) {
      return;
    }

    // Disconnect any existing document
    this.disconnectDocument(this._connectedDocument);

    // Connect to the new document
    this._connectedDocument = document;

    // Initialize shared data structures if not already done
    this._initializeSharedTypes();

    // Connect the document to the provider
    if (document) {
      // The NotebookModel will handle the actual connection to the Yjs document
      // through its connectCollaborationProvider method
      document.connectCollaborationProvider(this);

      // Set up initial synchronization
      this._syncDocumentToYjs(document);

      // Set up cell change listeners
      this._setupCellListeners(document);
    }
  }

  /**
   * Disconnect from a collaborative session.
   *
   * @param document - The notebook model to disconnect.
   */
  disconnectDocument(document: INotebookModel | null): void {
    if (!document || this._connectedDocument !== document) {
      return;
    }

    // Remove cell change listeners
    this._removeCellListeners(document);

    // Disconnect the document from the provider
    document.disconnectCollaborationProvider();
    this._connectedDocument = null;
  }

  /**
   * Set the user's awareness state.
   *
   * @param state - The awareness state to set.
   */
  setAwarenessState(state: Record<string, any>): void {
    // Get the current user state
    const currentState = this._awareness.getLocalState() || {};

    // Merge the new state with the current state
    this._awareness.setLocalState({ ...currentState, ...state });
  }

  /**
   * Get the awareness states of all users.
   *
   * @returns A map of user IDs to awareness states.
   */
  getAwarenessStates(): Map<number, Record<string, any>> {
    return this._awareness.getStates();
  }

  /**
   * Get the document ID for the current session.
   *
   * @returns The document ID.
   */
  getDocumentId(): string {
    return this._documentId;
  }

  /**
   * Destroy the provider and clean up resources.
   */
  destroy(): void {
    // Disconnect any connected document
    this.disconnectDocument(this._connectedDocument);

    // Disconnect the WebSocket provider
    if (this._websocketProvider) {
      this._websocketProvider.disconnect();
      this._websocketProvider.destroy();
    }

    // Destroy the Yjs document
    if (this._ydoc) {
      this._ydoc.destroy();
    }

    // Clear signals
    Signal.clearData(this);
  }

  /**
   * Generate a random document ID.
   *
   * @returns A random document ID.
   */
  private _generateDocumentId(): string {
    // Use the current path as the document ID
    const path = PageConfig.getOption('notebookPath') || '';
    if (path) {
      return `jupyter-notebook-${path}`;
    }

    // Fallback to a random ID
    return `jupyter-notebook-${Math.random().toString(36).substring(2, 15)}`;
  }

  /**
   * Get the default WebSocket URL for the collaboration server.
   *
   * @returns The default WebSocket URL.
   */
  private _getDefaultWebsocketUrl(): string {
    const baseUrl = PageConfig.getBaseUrl();
    const wsUrl = baseUrl.replace(/^http/, 'ws');
    return `${wsUrl}api/yjs`;
  }

  /**
   * Generate a random color for user awareness.
   *
   * @returns A random color in hex format.
   */
  private _getRandomColor(): string {
    const colors = [
      '#2196F3', // Blue
      '#4CAF50', // Green
      '#FFC107', // Amber
      '#F44336', // Red
      '#9C27B0', // Purple
      '#00BCD4', // Cyan
      '#FF9800', // Orange
      '#795548', // Brown
      '#607D8B', // Blue Grey
      '#E91E63', // Pink
    ];
    return colors[Math.floor(Math.random() * colors.length)];
  }

  /**
   * Initialize the shared data types for the Yjs document.
   */
  private _initializeSharedTypes(): void {
    // Create shared data structures if they don't exist
    if (!this._ydoc.getMap('notebook')) {
      this._ydoc.getMap('notebook');
    }
    if (!this._ydoc.getArray('cells')) {
      this._ydoc.getArray('cells');
    }
    if (!this._ydoc.getMap('metadata')) {
      this._ydoc.getMap('metadata');
    }
  }

  /**
   * Synchronize the notebook document to the Yjs document.
   *
   * @param document - The notebook model to synchronize.
   */
  private _syncDocumentToYjs(document: INotebookModel): void {
    if (!document) {
      return;
    }

    // Get shared data structures
    const ynotebook = this._ydoc.getMap('notebook');
    const ycells = this._ydoc.getArray('cells');
    const ymetadata = this._ydoc.getMap('metadata');

    // Set transaction origin to identify local changes
    this._ydoc.transact(() => {
      // Update notebook metadata
      ynotebook.set('nbformat', document.nbformat);
      ynotebook.set('nbformat_minor', document.nbformatMinor);

      // Clear and update cells
      ycells.delete(0, ycells.length);
      for (let i = 0; i < document.cells.length; i++) {
        const cell = document.cells.get(i);
        if (cell) {
          const ycell = this._createYCell(cell);
          ycells.push([ycell]);
        }
      }

      // Clear and update metadata
      ymetadata.clear();
      const metadata = document.metadata;
      for (const key in metadata) {
        if (Object.prototype.hasOwnProperty.call(metadata, key)) {
          ymetadata.set(key, metadata[key]);
        }
      }
    }, this);
  }

  /**
   * Create a Yjs cell map from a cell model.
   *
   * @param cell - The cell model to convert.
   * @returns A Yjs map representing the cell.
   */
  private _createYCell(cell: ICellModel): Y.Map<any> {
    const ycell = new Y.Map<any>();
    const cellJSON = cell.toJSON();

    // Set cell type
    ycell.set('cell_type', cellJSON.cell_type);

    // Set cell ID
    ycell.set('id', cell.id);

    // Set cell metadata
    const metadata = cellJSON.metadata || {};
    const ymetadata = new Y.Map<any>();
    for (const key in metadata) {
      if (Object.prototype.hasOwnProperty.call(metadata, key)) {
        ymetadata.set(key, metadata[key]);
      }
    }
    ycell.set('metadata', ymetadata);

    // Handle cell-type specific properties
    if (cellJSON.cell_type === 'code') {
      // Set execution count
      ycell.set('execution_count', cellJSON.execution_count);

      // Set outputs
      const outputs = cellJSON.outputs || [];
      const youtputs = new Y.Array<any>();
      for (const output of outputs) {
        const youtput = new Y.Map<any>();
        for (const key in output) {
          if (Object.prototype.hasOwnProperty.call(output, key)) {
            youtput.set(key, output[key]);
          }
        }
        youtputs.push([youtput]);
      }
      ycell.set('outputs', youtputs);
    }

    // Set source
    const source = cellJSON.source || '';
    const ysource = new Y.Text(source);
    ycell.set('source', ysource);

    return ycell;
  }

  /**
   * Set up cell change listeners for the notebook model.
   *
   * @param document - The notebook model to listen to.
   */
  private _setupCellListeners(document: INotebookModel): void {
    if (!document) {
      return;
    }

    // Listen for cell changes
    document.cells.changed.connect(this._onCellsChanged, this);
    document.stateChanged.connect(this._onDocumentStateChanged, this);

    // Listen for changes to individual cells
    for (let i = 0; i < document.cells.length; i++) {
      const cell = document.cells.get(i);
      if (cell) {
        cell.contentChanged.connect(this._onCellContentChanged, this);
        cell.stateChanged.connect(this._onCellStateChanged, this);
      }
    }
  }

  /**
   * Remove cell change listeners from the notebook model.
   *
   * @param document - The notebook model to remove listeners from.
   */
  private _removeCellListeners(document: INotebookModel): void {
    if (!document) {
      return;
    }

    // Remove cell list change listeners
    document.cells.changed.disconnect(this._onCellsChanged, this);
    document.stateChanged.disconnect(this._onDocumentStateChanged, this);

    // Remove individual cell change listeners
    for (let i = 0; i < document.cells.length; i++) {
      const cell = document.cells.get(i);
      if (cell) {
        cell.contentChanged.disconnect(this._onCellContentChanged, this);
        cell.stateChanged.disconnect(this._onCellStateChanged, this);
      }
    }
  }

  /**
   * Handle changes to the cells list.
   */
  private _onCellsChanged(sender: any, args: any): void {
    if (!this._connectedDocument || this._updatingFromYjs) {
      return;
    }

    const ycells = this._ydoc.getArray('cells');

    this._ydoc.transact(() => {
      switch (args.type) {
        case 'add':
          {
            const index = args.newIndex;
            const cell = args.newValues[0];
            const ycell = this._createYCell(cell);
            ycells.insert(index, [ycell]);

            // Add listeners to the new cell
            cell.contentChanged.connect(this._onCellContentChanged, this);
            cell.stateChanged.connect(this._onCellStateChanged, this);
          }
          break;
        case 'remove':
          {
            const index = args.oldIndex;
            const cell = args.oldValues[0];
            ycells.delete(index, 1);

            // Remove listeners from the removed cell
            cell.contentChanged.disconnect(this._onCellContentChanged, this);
            cell.stateChanged.disconnect(this._onCellStateChanged, this);
          }
          break;
        case 'move':
          {
            const fromIndex = args.oldIndex;
            const toIndex = args.newIndex;
            // Move the cell in the Yjs array
            const [ycell] = ycells.delete(fromIndex, 1);
            ycells.insert(toIndex, [ycell]);
          }
          break;
        case 'set':
          {
            const index = args.newIndex;
            const oldCell = args.oldValues[0];
            const newCell = args.newValues[0];
            const ycell = this._createYCell(newCell);
            ycells.delete(index, 1);
            ycells.insert(index, [ycell]);

            // Update listeners
            oldCell.contentChanged.disconnect(this._onCellContentChanged, this);
            oldCell.stateChanged.disconnect(this._onCellStateChanged, this);
            newCell.contentChanged.connect(this._onCellContentChanged, this);
            newCell.stateChanged.connect(this._onCellStateChanged, this);
          }
          break;
      }
    }, this);
  }

  /**
   * Handle changes to a cell's content.
   */
  private _onCellContentChanged(cell: ICellModel): void {
    if (!this._connectedDocument || this._updatingFromYjs) {
      return;
    }

    const index = this._connectedDocument.cells.indexOf(cell);
    if (index === -1) {
      return;
    }

    const ycells = this._ydoc.getArray('cells');
    const ycell = ycells.get(index) as Y.Map<any>;
    if (!ycell) {
      return;
    }

    this._ydoc.transact(() => {
      // Update source
      const cellJSON = cell.toJSON();
      const source = cellJSON.source || '';
      const ysource = ycell.get('source') as Y.Text;
      if (ysource) {
        ysource.delete(0, ysource.length);
        ysource.insert(0, source);
      } else {
        ycell.set('source', new Y.Text(source));
      }

      // Update outputs for code cells
      if (cell.type === 'code') {
        const codeCell = cell as ICodeCellModel;
        const outputs = codeCell.outputs.toJSON();
        const youtputs = ycell.get('outputs') as Y.Array<any> || new Y.Array<any>();
        youtputs.delete(0, youtputs.length);

        for (const output of outputs) {
          const youtput = new Y.Map<any>();
          for (const key in output) {
            if (Object.prototype.hasOwnProperty.call(output, key)) {
              youtput.set(key, output[key]);
            }
          }
          youtputs.push([youtput]);
        }

        ycell.set('outputs', youtputs);
        ycell.set('execution_count', codeCell.executionCount);
      }
    }, this);
  }

  /**
   * Handle changes to a cell's state.
   */
  private _onCellStateChanged(cell: ICellModel, args: any): void {
    if (!this._connectedDocument || this._updatingFromYjs) {
      return;
    }

    const index = this._connectedDocument.cells.indexOf(cell);
    if (index === -1) {
      return;
    }

    const ycells = this._ydoc.getArray('cells');
    const ycell = ycells.get(index) as Y.Map<any>;
    if (!ycell) {
      return;
    }

    this._ydoc.transact(() => {
      // Update metadata
      const cellJSON = cell.toJSON();
      const metadata = cellJSON.metadata || {};
      const ymetadata = ycell.get('metadata') as Y.Map<any> || new Y.Map<any>();
      ymetadata.clear();
      for (const key in metadata) {
        if (Object.prototype.hasOwnProperty.call(metadata, key)) {
          ymetadata.set(key, metadata[key]);
        }
      }
      ycell.set('metadata', ymetadata);
    }, this);
  }

  /**
   * Handle changes to the document state.
   */
  private _onDocumentStateChanged(sender: INotebookModel, args: any): void {
    if (!this._connectedDocument || this._updatingFromYjs) {
      return;
    }

    const ynotebook = this._ydoc.getMap('notebook');
    const ymetadata = this._ydoc.getMap('metadata');

    this._ydoc.transact(() => {
      // Update nbformat and nbformatMinor if changed
      if (args.name === 'nbformat') {
        ynotebook.set('nbformat', args.newValue);
      } else if (args.name === 'nbformatMinor') {
        ynotebook.set('nbformat_minor', args.newValue);
      } else if (args.name === 'metadata') {
        // Update metadata
        ymetadata.clear();
        const metadata = this._connectedDocument!.metadata;
        for (const key in metadata) {
          if (Object.prototype.hasOwnProperty.call(metadata, key)) {
            ymetadata.set(key, metadata[key]);
          }
        }
      }
    }, this);
  }

  /**
   * Handle changes to the Yjs document.
   */
  private _onYDocChanged(event: Y.YEvent<any>[]): void {
    if (!this._connectedDocument || this._updatingToYjs) {
      return;
    }

    this._updatingFromYjs = true;

    try {
      // Process each event
      for (const e of event) {
        if (e.target === this._ydoc.getMap('notebook')) {
          this._handleYNotebookChanged(e as Y.YMapEvent<any>);
        } else if (e.target === this._ydoc.getArray('cells')) {
          this._handleYCellsChanged(e as Y.YArrayEvent<any>);
        } else if (e.target === this._ydoc.getMap('metadata')) {
          this._handleYMetadataChanged(e as Y.YMapEvent<any>);
        }
      }
    } finally {
      this._updatingFromYjs = false;
    }
  }

  /**
   * Handle changes to the Yjs notebook map.
   */
  private _handleYNotebookChanged(event: Y.YMapEvent<any>): void {
    if (!this._connectedDocument) {
      return;
    }

    // Update nbformat and nbformatMinor if changed
    const ynotebook = event.target as Y.Map<any>;
    if (event.keysChanged.has('nbformat')) {
      this._connectedDocument.nbformat = ynotebook.get('nbformat') as number || 4;
    }
    if (event.keysChanged.has('nbformat_minor')) {
      this._connectedDocument.nbformatMinor = ynotebook.get('nbformat_minor') as number || 0;
    }
  }

  /**
   * Handle changes to the Yjs cells array.
   */
  private _handleYCellsChanged(event: Y.YArrayEvent<any>): void {
    if (!this._connectedDocument) {
      return;
    }

    const ycells = event.target as Y.Array<any>;
    const document = this._connectedDocument;
    const factory = document.contentFactory;

    // Process deletions
    let deletionCount = 0;
    event.changes.delete.forEach(del => {
      for (let i = 0; i < del.length; i++) {
        document.cells.removeAt(del.index - deletionCount);
        deletionCount++;
      }
    });

    // Process insertions
    event.changes.insert.forEach(ins => {
      const cells: ICellModel[] = [];
      for (let i = 0; i < ins.values.length; i++) {
        const ycell = ins.values[i] as Y.Map<any>;
        const cellType = ycell.get('cell_type') as string;
        let cell: ICellModel | undefined;

        const cellData = this._ycellToJSON(ycell);
        switch (cellType) {
          case 'code':
            cell = factory.createCodeCell({ cell: cellData });
            break;
          case 'markdown':
            cell = factory.createMarkdownCell({ cell: cellData });
            break;
          case 'raw':
            cell = factory.createRawCell({ cell: cellData });
            break;
          default:
            console.warn(`Ignoring unknown cell type: ${cellType}`);
            break;
        }

        if (cell) {
          cells.push(cell);
        }
      }

      if (cells.length > 0) {
        document.cells.insertAll(ins.index, cells);
      }
    });

    // Process updates to existing cells
    event.changes.update.forEach(update => {
      for (let i = 0; i < update.length; i++) {
        const index = update.index + i;
        const ycell = ycells.get(index) as Y.Map<any>;
        const cell = document.cells.get(index);

        if (cell && ycell) {
          this._updateCellFromYCell(cell, ycell);
        }
      }
    });
  }

  /**
   * Handle changes to the Yjs metadata map.
   */
  private _handleYMetadataChanged(event: Y.YMapEvent<any>): void {
    if (!this._connectedDocument) {
      return;
    }

    // Update the metadata object
    const ymetadata = event.target as Y.Map<any>;
    this._connectedDocument.metadata = ymetadata.toJSON();
  }

  /**
   * Convert a Yjs cell map to a JSON object.
   */
  private _ycellToJSON(ycell: Y.Map<any>): any {
    const cellType = ycell.get('cell_type') as string;
    const result: any = {
      cell_type: cellType,
      id: ycell.get('id') as string,
      metadata: {}
    };

    // Get metadata
    const ymetadata = ycell.get('metadata') as Y.Map<any>;
    if (ymetadata) {
      result.metadata = ymetadata.toJSON();
    }

    // Get source
    const ysource = ycell.get('source') as Y.Text;
    if (ysource) {
      result.source = ysource.toString();
    } else {
      result.source = '';
    }

    // Handle cell-type specific properties
    if (cellType === 'code') {
      result.execution_count = ycell.get('execution_count') as number || null;

      // Get outputs
      const youtputs = ycell.get('outputs') as Y.Array<any>;
      if (youtputs) {
        result.outputs = [];
        for (let i = 0; i < youtputs.length; i++) {
          const youtput = youtputs.get(i) as Y.Map<any>;
          if (youtput) {
            result.outputs.push(youtput.toJSON());
          }
        }
      } else {
        result.outputs = [];
      }
    }

    return result;
  }

  /**
   * Update a cell model from a Yjs cell map.
   */
  private _updateCellFromYCell(cell: ICellModel, ycell: Y.Map<any>): void {
    const cellJSON = this._ycellToJSON(ycell);
    cell.fromJSON(cellJSON);
  }

  private _ydoc: Y.Doc;
  private _awareness: awareness.Awareness;
  private _websocketProvider: WebsocketProvider;
  private _documentId: string;
  private _connectedDocument: INotebookModel | null = null;
  private _connectionStatus: ConnectionStatus = ConnectionStatus.Disconnected;
  private _remoteChangesSignal = new Signal<ICollaborationProvider, void>(this);
  private _connectionStatusChanged = new Signal<
    ICollaborationProvider,
    ConnectionStatus
  >(this);
  
  // Flags to prevent update loops
  private _updatingToYjs = false;
  private _updatingFromYjs = false;
}
// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { DocumentRegistry } from '@jupyterlab/docregistry';
import { IChangedArgs } from '@jupyterlab/coreutils';
import { IObservableList, ObservableList } from '@jupyterlab/observables';
import { ICellModel, ICodeCellModel, IMarkdownCellModel, IRawCellModel, CellModel, CodeCellModel, MarkdownCellModel, RawCellModel } from '@jupyterlab/cells';
import { IModelDB } from '@jupyterlab/observables';
import { ISignal, Signal } from '@lumino/signaling';
import * as Y from 'yjs';

import { ICollaborationProvider } from './collab/provider';
import { IVersionHistory } from './collab/history';

/**
 * The definition of a model object for a notebook widget.
 */
export interface INotebookModel extends DocumentRegistry.IModel {
  /**
   * The list of cells in the notebook.
   */
  readonly cells: IObservableList<ICellModel>;

  /**
   * The cell model factory for the notebook.
   */
  readonly contentFactory: NotebookModel.IContentFactory;

  /**
   * The major version number of the nbformat.
   */
  readonly nbformat: number;

  /**
   * The minor version number of the nbformat.
   */
  readonly nbformatMinor: number;

  /**
   * The metadata associated with the notebook.
   */
  readonly metadata: any;

  /**
   * Whether the model is collaborative.
   */
  readonly isCollaborative: boolean;

  /**
   * The collaboration provider for the notebook model.
   */
  readonly collaborationProvider: ICollaborationProvider | null;

  /**
   * The version history for the notebook model.
   */
  readonly versionHistory: IVersionHistory | null;

  /**
   * A signal emitted when the state of the model changes.
   */
  readonly stateChanged: ISignal<INotebookModel, IChangedArgs<any>>;

  /**
   * A signal emitted when the model state becomes dirty.
   */
  readonly contentChanged: ISignal<INotebookModel, void>;

  /**
   * A signal emitted when a cell is added to the model.
   */
  readonly cellAdded: ISignal<INotebookModel, { index: number; cell: ICellModel }>;

  /**
   * A signal emitted when a cell is removed from the model.
   */
  readonly cellRemoved: ISignal<INotebookModel, { index: number; cell: ICellModel }>;

  /**
   * A signal emitted when a cell is moved in the model.
   */
  readonly cellMoved: ISignal<INotebookModel, { fromIndex: number; toIndex: number; cell: ICellModel }>;

  /**
   * A signal emitted when a cell's state changes.
   */
  readonly cellChanged: ISignal<INotebookModel, { index: number; cell: ICellModel }>;

  /**
   * A signal emitted when a collaborative update is received.
   */
  readonly collaborativeUpdate: ISignal<INotebookModel, void>;

  /**
   * The default kernel name of the document.
   */
  readonly defaultKernelName: string;

  /**
   * The default kernel language of the document.
   */
  readonly defaultKernelLanguage: string;

  /**
   * Serialize the model to a string.
   */
  toString(): string;

  /**
   * Deserialize the model from a string.
   *
   * #### Notes
   * Should emit a [contentChanged] signal.
   */
  fromString(value: string): void;

  /**
   * Serialize the model to JSON.
   */
  toJSON(): any;

  /**
   * Deserialize the model from JSON.
   *
   * #### Notes
   * Should emit a [contentChanged] signal.
   */
  fromJSON(value: any): void;

  /**
   * Initialize a new cell by cell type.
   */
  createCell(type: string, options?: any): ICellModel;

  /**
   * Initialize a new code cell.
   */
  createCodeCell(options?: any): ICodeCellModel;

  /**
   * Initialize a new markdown cell.
   */
  createMarkdownCell(options?: any): IMarkdownCellModel;

  /**
   * Initialize a new raw cell.
   */
  createRawCell(options?: any): IRawCellModel;

  /**
   * Initialize a new cell by cell type and insert it at the given index.
   */
  insertCell(index: number, type: string, options?: any): ICellModel;

  /**
   * Initialize a new code cell and insert it at the given index.
   */
  insertCodeCell(index: number, options?: any): ICodeCellModel;

  /**
   * Initialize a new markdown cell and insert it at the given index.
   */
  insertMarkdownCell(index: number, options?: any): IMarkdownCellModel;

  /**
   * Initialize a new raw cell and insert it at the given index.
   */
  insertRawCell(index: number, options?: any): IRawCellModel;

  /**
   * Move a cell from one index to another.
   */
  moveCell(fromIndex: number, toIndex: number): void;

  /**
   * Remove a cell by index.
   */
  removeCell(index: number): ICellModel;

  /**
   * Get a cell by index.
   */
  getCell(index: number): ICellModel | undefined;

  /**
   * Get the index of a cell by cell id.
   */
  indexOfCell(cellId: string): number;

  /**
   * Connect to a collaboration provider.
   */
  connectCollaborationProvider(provider: ICollaborationProvider): void;

  /**
   * Disconnect from a collaboration provider.
   */
  disconnectCollaborationProvider(): void;

  /**
   * Connect to a version history provider.
   */
  connectVersionHistory(history: IVersionHistory): void;

  /**
   * Disconnect from a version history provider.
   */
  disconnectVersionHistory(): void;

  /**
   * Create a snapshot of the current notebook state.
   */
  createSnapshot(): any;

  /**
   * Restore the notebook state from a snapshot.
   */
  restoreSnapshot(snapshot: any): void;
}

/**
 * An implementation of a notebook Model.
 */
export class NotebookModel implements INotebookModel {
  /**
   * Construct a new notebook model.
   */
  constructor(options: NotebookModel.IOptions = {}) {
    const contentFactory =
      options.contentFactory || NotebookModel.defaultContentFactory;
    this.contentFactory = contentFactory;
    this._cells = new ObservableList<ICellModel>();
    this._cells.changed.connect(this._onCellsChanged, this);

    // Initialize the modelDB if available
    this._modelDB = options.modelDB || null;
    if (this._modelDB) {
      const cells = this._modelDB.get('cells');
      if (cells) {
        cells.changed.connect(this._onModelDBCellsChanged, this);
      }
    }

    // Initialize the Yjs document if collaborative
    this._isCollaborative = !!options.collaborative;
    if (this._isCollaborative) {
      this._initializeCollaboration();
    }
  }

  /**
   * A signal emitted when the state of the model changes.
   */
  get stateChanged(): ISignal<this, IChangedArgs<any>> {
    return this._stateChanged;
  }

  /**
   * A signal emitted when the model state becomes dirty.
   */
  get contentChanged(): ISignal<this, void> {
    return this._contentChanged;
  }

  /**
   * A signal emitted when a cell is added to the model.
   */
  get cellAdded(): ISignal<this, { index: number; cell: ICellModel }> {
    return this._cellAdded;
  }

  /**
   * A signal emitted when a cell is removed from the model.
   */
  get cellRemoved(): ISignal<this, { index: number; cell: ICellModel }> {
    return this._cellRemoved;
  }

  /**
   * A signal emitted when a cell is moved in the model.
   */
  get cellMoved(): ISignal<this, { fromIndex: number; toIndex: number; cell: ICellModel }> {
    return this._cellMoved;
  }

  /**
   * A signal emitted when a cell's state changes.
   */
  get cellChanged(): ISignal<this, { index: number; cell: ICellModel }> {
    return this._cellChanged;
  }

  /**
   * A signal emitted when a collaborative update is received.
   */
  get collaborativeUpdate(): ISignal<this, void> {
    return this._collaborativeUpdate;
  }

  /**
   * Get the observable list of notebook cells.
   */
  get cells(): IObservableList<ICellModel> {
    return this._cells;
  }

  /**
   * The dirty state of the notebook.
   *
   * #### Notes
   * This is determined by the dirty state of the cells.
   */
  get dirty(): boolean {
    return this._dirty;
  }
  set dirty(newValue: boolean) {
    const oldValue = this._dirty;
    if (newValue === oldValue) {
      return;
    }
    this._dirty = newValue;
    this.triggerStateChange({
      name: 'dirty',
      oldValue,
      newValue
    });
  }

  /**
   * The metadata associated with the notebook.
   */
  get metadata(): any {
    return this._metadata;
  }
  set metadata(newValue: any) {
    const oldValue = this._metadata;
    this._metadata = newValue;
    this.triggerStateChange({
      name: 'metadata',
      oldValue,
      newValue
    });
    this.setDirty(true);
  }

  /**
   * Get the major version number of the nbformat.
   */
  get nbformat(): number {
    return this._nbformat;
  }
  set nbformat(newValue: number) {
    const oldValue = this._nbformat;
    this._nbformat = newValue;
    this.triggerStateChange({
      name: 'nbformat',
      oldValue,
      newValue
    });
    this.setDirty(true);
  }

  /**
   * Get the minor version number of the nbformat.
   */
  get nbformatMinor(): number {
    return this._nbformatMinor;
  }
  set nbformatMinor(newValue: number) {
    const oldValue = this._nbformatMinor;
    this._nbformatMinor = newValue;
    this.triggerStateChange({
      name: 'nbformatMinor',
      oldValue,
      newValue
    });
    this.setDirty(true);
  }

  /**
   * Whether the model is collaborative.
   */
  get isCollaborative(): boolean {
    return this._isCollaborative;
  }

  /**
   * The collaboration provider for the notebook model.
   */
  get collaborationProvider(): ICollaborationProvider | null {
    return this._collaborationProvider;
  }

  /**
   * The version history for the notebook model.
   */
  get versionHistory(): IVersionHistory | null {
    return this._versionHistory;
  }

  /**
   * The default kernel name of the document.
   */
  get defaultKernelName(): string {
    return this._defaultKernelName;
  }
  set defaultKernelName(newValue: string) {
    const oldValue = this._defaultKernelName;
    this._defaultKernelName = newValue;
    this.triggerStateChange({
      name: 'defaultKernelName',
      oldValue,
      newValue
    });
  }

  /**
   * The default kernel language of the document.
   */
  get defaultKernelLanguage(): string {
    return this._defaultKernelLanguage;
  }
  set defaultKernelLanguage(newValue: string) {
    const oldValue = this._defaultKernelLanguage;
    this._defaultKernelLanguage = newValue;
    this.triggerStateChange({
      name: 'defaultKernelLanguage',
      oldValue,
      newValue
    });
  }

  /**
   * Dispose of the resources held by the model.
   */
  dispose(): void {
    // Do nothing if already disposed.
    if (this.isDisposed) {
      return;
    }
    this._isDisposed = true;
    this._cells.dispose();
    this.disconnectCollaborationProvider();
    this.disconnectVersionHistory();
    Signal.clearData(this);
  }

  /**
   * Serialize the model to a string.
   */
  toString(): string {
    return JSON.stringify(this.toJSON());
  }

  /**
   * Deserialize the model from a string.
   *
   * #### Notes
   * Should emit a [contentChanged] signal.
   */
  fromString(value: string): void {
    this.fromJSON(JSON.parse(value));
  }

  /**
   * Serialize the model to JSON.
   */
  toJSON(): any {
    const cells: any[] = [];
    for (let i = 0; i < this.cells.length; i++) {
      const cell = this.cells.get(i);
      if (cell) {
        cells.push(cell.toJSON());
      }
    }
    return {
      cells,
      metadata: this._metadata,
      nbformat: this._nbformat,
      nbformat_minor: this._nbformatMinor
    };
  }

  /**
   * Deserialize the model from JSON.
   *
   * #### Notes
   * Should emit a [contentChanged] signal.
   */
  fromJSON(value: any): void {
    const cells: ICellModel[] = [];
    const factory = this.contentFactory;

    // Extract the cells from the JSON
    if (Array.isArray(value.cells)) {
      for (const cellData of value.cells) {
        let cell: ICellModel | undefined;

        switch (cellData.cell_type) {
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
            console.warn(`Ignoring unknown cell type: ${cellData.cell_type}`);
            break;
        }

        if (cell) {
          cells.push(cell);
        }
      }
    }

    // Extract other fields from the notebook
    this._metadata = value.metadata || {};
    this._nbformat = value.nbformat || 4;
    this._nbformatMinor = value.nbformat_minor || 0;

    // Update the cells list
    this._cells.clear();
    if (cells.length) {
      this._cells.pushAll(cells);
    }

    // If collaborative, sync with Yjs document
    if (this._isCollaborative && this._ydoc) {
      this._syncToYDoc();
    }

    this.dirty = false;
    this._contentChanged.emit(void 0);
  }

  /**
   * Initialize a new cell by cell type.
   */
  createCell(type: string, options: any = {}): ICellModel {
    switch (type) {
      case 'code':
        return this.createCodeCell(options);
      case 'markdown':
        return this.createMarkdownCell(options);
      case 'raw':
        return this.createRawCell(options);
      default:
        throw new Error(`Invalid cell type: ${type}`);
    }
  }

  /**
   * Initialize a new code cell.
   */
  createCodeCell(options: any = {}): ICodeCellModel {
    return this.contentFactory.createCodeCell(options);
  }

  /**
   * Initialize a new markdown cell.
   */
  createMarkdownCell(options: any = {}): IMarkdownCellModel {
    return this.contentFactory.createMarkdownCell(options);
  }

  /**
   * Initialize a new raw cell.
   */
  createRawCell(options: any = {}): IRawCellModel {
    return this.contentFactory.createRawCell(options);
  }

  /**
   * Initialize a new cell by cell type and insert it at the given index.
   */
  insertCell(index: number, type: string, options: any = {}): ICellModel {
    const cell = this.createCell(type, options);
    this.cells.insert(index, cell);
    return cell;
  }

  /**
   * Initialize a new code cell and insert it at the given index.
   */
  insertCodeCell(index: number, options: any = {}): ICodeCellModel {
    const cell = this.createCodeCell(options);
    this.cells.insert(index, cell);
    return cell;
  }

  /**
   * Initialize a new markdown cell and insert it at the given index.
   */
  insertMarkdownCell(index: number, options: any = {}): IMarkdownCellModel {
    const cell = this.createMarkdownCell(options);
    this.cells.insert(index, cell);
    return cell;
  }

  /**
   * Initialize a new raw cell and insert it at the given index.
   */
  insertRawCell(index: number, options: any = {}): IRawCellModel {
    const cell = this.createRawCell(options);
    this.cells.insert(index, cell);
    return cell;
  }

  /**
   * Move a cell from one index to another.
   */
  moveCell(fromIndex: number, toIndex: number): void {
    this.cells.move(fromIndex, toIndex);
  }

  /**
   * Remove a cell by index.
   */
  removeCell(index: number): ICellModel {
    return this.cells.removeAt(index);
  }

  /**
   * Get a cell by index.
   */
  getCell(index: number): ICellModel | undefined {
    return this.cells.get(index);
  }

  /**
   * Get the index of a cell by cell id.
   */
  indexOfCell(cellId: string): number {
    for (let i = 0; i < this.cells.length; i++) {
      const cell = this.cells.get(i);
      if (cell && cell.id === cellId) {
        return i;
      }
    }
    return -1;
  }

  /**
   * Connect to a collaboration provider.
   */
  connectCollaborationProvider(provider: ICollaborationProvider): void {
    if (this._collaborationProvider === provider) {
      return;
    }

    // Disconnect from any existing provider
    this.disconnectCollaborationProvider();

    // Connect to the new provider
    this._collaborationProvider = provider;
    this._isCollaborative = true;

    // Initialize Yjs document if not already done
    if (!this._ydoc) {
      this._initializeCollaboration();
    }

    // Connect the provider to the Yjs document
    if (this._ydoc) {
      provider.connectDocument(this);
      provider.remoteChangesSignal.connect(this._onRemoteChanges, this);

      // Sync current notebook state to Yjs document
      this._syncToYDoc();
    }
  }

  /**
   * Disconnect from a collaboration provider.
   */
  disconnectCollaborationProvider(): void {
    if (!this._collaborationProvider) {
      return;
    }

    // Disconnect signals
    this._collaborationProvider.remoteChangesSignal.disconnect(this._onRemoteChanges, this);

    // Disconnect the provider
    this._collaborationProvider.disconnectDocument(this);
    this._collaborationProvider = null;
  }

  /**
   * Connect to a version history provider.
   */
  connectVersionHistory(history: IVersionHistory): void {
    if (this._versionHistory === history) {
      return;
    }

    // Disconnect from any existing history provider
    this.disconnectVersionHistory();

    // Connect to the new history provider
    this._versionHistory = history;
    history.connectDocument(this);
  }

  /**
   * Disconnect from a version history provider.
   */
  disconnectVersionHistory(): void {
    if (!this._versionHistory) {
      return;
    }

    this._versionHistory.disconnectDocument(this);
    this._versionHistory = null;
  }

  /**
   * Create a snapshot of the current notebook state.
   */
  createSnapshot(): any {
    return this.toJSON();
  }

  /**
   * Restore the notebook state from a snapshot.
   */
  restoreSnapshot(snapshot: any): void {
    this.fromJSON(snapshot);
  }

  /**
   * Set the dirty state of the model.
   */
  setDirty(dirty: boolean): void {
    if (this._dirty === dirty) {
      return;
    }
    this._dirty = dirty;
    this.triggerStateChange({
      name: 'dirty',
      oldValue: !dirty,
      newValue: dirty
    });
  }

  /**
   * Trigger a state change signal.
   */
  protected triggerStateChange(args: IChangedArgs<any>): void {
    this._stateChanged.emit(args);
  }

  /**
   * Trigger a content changed signal.
   */
  protected triggerContentChange(): void {
    this.setDirty(true);
    this._contentChanged.emit(void 0);
  }

  /**
   * Handle a change to the cells list.
   */
  private _onCellsChanged(list: IObservableList<ICellModel>, change: IObservableList.IChangedArgs<ICellModel>): void {
    let index = 0;
    let cell: ICellModel | undefined;

    switch (change.type) {
      case 'add':
        index = change.newIndex;
        cell = change.newValues[0];
        this._cellAdded.emit({ index, cell });
        cell.contentChanged.connect(this._onCellContentChanged, this);
        cell.stateChanged.connect(this._onCellStateChanged, this);
        break;
      case 'remove':
        index = change.oldIndex;
        cell = change.oldValues[0];
        this._cellRemoved.emit({ index, cell });
        cell.contentChanged.disconnect(this._onCellContentChanged, this);
        cell.stateChanged.disconnect(this._onCellStateChanged, this);
        break;
      case 'move':
        const fromIndex = change.oldIndex;
        const toIndex = change.newIndex;
        cell = change.newValues[0];
        this._cellMoved.emit({ fromIndex, toIndex, cell });
        break;
      case 'set':
        index = change.newIndex;
        const oldCell = change.oldValues[0];
        const newCell = change.newValues[0];
        oldCell.contentChanged.disconnect(this._onCellContentChanged, this);
        oldCell.stateChanged.disconnect(this._onCellStateChanged, this);
        newCell.contentChanged.connect(this._onCellContentChanged, this);
        newCell.stateChanged.connect(this._onCellStateChanged, this);
        break;
      default:
        break;
    }

    // If collaborative, sync changes to Yjs document
    if (this._isCollaborative && this._ydoc && !this._updatingFromYjs) {
      this._syncToYDoc();
    }

    this.triggerContentChange();
  }

  /**
   * Handle a change to the cells in the model DB.
   */
  private _onModelDBCellsChanged(sender: any, args: any): void {
    // TODO: Implement model DB cell changes
  }

  /**
   * Handle a change to a cell's content.
   */
  private _onCellContentChanged(cell: ICellModel): void {
    const index = this.cells.indexOf(cell);
    if (index !== -1) {
      this._cellChanged.emit({ index, cell });

      // If collaborative, sync changes to Yjs document
      if (this._isCollaborative && this._ydoc && !this._updatingFromYjs) {
        this._syncCellToYDoc(index, cell);
      }

      this.triggerContentChange();
    }
  }

  /**
   * Handle a change to a cell's state.
   */
  private _onCellStateChanged(cell: ICellModel, args: IChangedArgs<any>): void {
    const index = this.cells.indexOf(cell);
    if (index !== -1) {
      this._cellChanged.emit({ index, cell });

      // If collaborative, sync changes to Yjs document
      if (this._isCollaborative && this._ydoc && !this._updatingFromYjs) {
        this._syncCellToYDoc(index, cell);
      }

      this.triggerContentChange();
    }
  }

  /**
   * Handle remote changes from the collaboration provider.
   */
  private _onRemoteChanges(): void {
    if (!this._ydoc) {
      return;
    }

    // Update the notebook model from the Yjs document
    this._syncFromYDoc();

    // Emit the collaborative update signal
    this._collaborativeUpdate.emit(void 0);
  }

  /**
   * Initialize the Yjs document and shared data structures.
   */
  private _initializeCollaboration(): void {
    // Create a new Yjs document
    this._ydoc = new Y.Doc();

    // Create shared data structures for the notebook
    this._ynotebook = this._ydoc.getMap('notebook');
    this._ycells = this._ydoc.getArray('cells');
    this._ymetadata = this._ydoc.getMap('metadata');

    // Set up observation of Yjs document changes
    this._ynotebook.observe(this._onYNotebookChanged.bind(this));
    this._ycells.observe(this._onYCellsChanged.bind(this));
    this._ymetadata.observe(this._onYMetadataChanged.bind(this));
  }

  /**
   * Handle changes to the Yjs notebook map.
   */
  private _onYNotebookChanged(event: Y.YMapEvent<any>): void {
    if (this._updatingToYjs) {
      return;
    }

    this._updatingFromYjs = true;

    // Update nbformat and nbformatMinor if changed
    if (event.keysChanged.has('nbformat')) {
      this._nbformat = this._ynotebook.get('nbformat') as number || 4;
    }
    if (event.keysChanged.has('nbformat_minor')) {
      this._nbformatMinor = this._ynotebook.get('nbformat_minor') as number || 0;
    }

    this._updatingFromYjs = false;
  }

  /**
   * Handle changes to the Yjs cells array.
   */
  private _onYCellsChanged(event: Y.YArrayEvent<any>): void {
    if (this._updatingToYjs) {
      return;
    }

    this._updatingFromYjs = true;

    // Process each change to the cells array
    let index = 0;
    const factory = this.contentFactory;

    // Handle deletions
    event.changes.delete.forEach(del => {
      for (let i = 0; i < del.length; i++) {
        this._cells.removeAt(del.index);
      }
    });

    // Handle insertions
    event.changes.insert.forEach(ins => {
      const cells: ICellModel[] = [];
      for (let i = 0; i < ins.values.length; i++) {
        const ycell = ins.values[i] as Y.Map<any>;
        const cellType = ycell.get('cell_type') as string;
        let cell: ICellModel | undefined;

        switch (cellType) {
          case 'code':
            cell = factory.createCodeCell({ cell: this._ycellToJSON(ycell) });
            break;
          case 'markdown':
            cell = factory.createMarkdownCell({ cell: this._ycellToJSON(ycell) });
            break;
          case 'raw':
            cell = factory.createRawCell({ cell: this._ycellToJSON(ycell) });
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
        this._cells.insertAll(ins.index, cells);
      }
    });

    // Handle updates to existing cells
    event.changes.update.forEach(update => {
      for (let i = 0; i < update.length; i++) {
        const index = update.index + i;
        const ycell = this._ycells.get(index) as Y.Map<any>;
        const cell = this._cells.get(index);

        if (cell && ycell) {
          this._updateCellFromYCell(cell, ycell);
        }
      }
    });

    this._updatingFromYjs = false;
  }

  /**
   * Handle changes to the Yjs metadata map.
   */
  private _onYMetadataChanged(event: Y.YMapEvent<any>): void {
    if (this._updatingToYjs) {
      return;
    }

    this._updatingFromYjs = true;

    // Update the metadata object
    this._metadata = this._ymetadata.toJSON();

    this._updatingFromYjs = false;
  }

  /**
   * Synchronize the notebook model to the Yjs document.
   */
  private _syncToYDoc(): void {
    if (!this._ydoc || !this._ynotebook || !this._ycells || !this._ymetadata) {
      return;
    }

    this._updatingToYjs = true;

    // Update notebook metadata
    this._ynotebook.set('nbformat', this._nbformat);
    this._ynotebook.set('nbformat_minor', this._nbformatMinor);

    // Update cells
    this._ycells.delete(0, this._ycells.length);
    for (let i = 0; i < this._cells.length; i++) {
      const cell = this._cells.get(i);
      if (cell) {
        const ycell = this._createYCell(cell);
        this._ycells.push([ycell]);
      }
    }

    // Update metadata
    this._ymetadata.clear();
    for (const key in this._metadata) {
      if (Object.prototype.hasOwnProperty.call(this._metadata, key)) {
        this._ymetadata.set(key, this._metadata[key]);
      }
    }

    this._updatingToYjs = false;
  }

  /**
   * Synchronize a specific cell to the Yjs document.
   */
  private _syncCellToYDoc(index: number, cell: ICellModel): void {
    if (!this._ydoc || !this._ycells || this._updatingFromYjs) {
      return;
    }

    this._updatingToYjs = true;

    // Update the cell in the Yjs document
    if (index >= 0 && index < this._ycells.length) {
      const ycell = this._ycells.get(index) as Y.Map<any>;
      if (ycell) {
        this._updateYCellFromCell(ycell, cell);
      } else {
        const newYCell = this._createYCell(cell);
        this._ycells.delete(index, 1);
        this._ycells.insert(index, [newYCell]);
      }
    }

    this._updatingToYjs = false;
  }

  /**
   * Synchronize the notebook model from the Yjs document.
   */
  private _syncFromYDoc(): void {
    if (!this._ydoc || !this._ynotebook || !this._ycells || !this._ymetadata) {
      return;
    }

    this._updatingFromYjs = true;

    // Update nbformat and nbformatMinor
    this._nbformat = this._ynotebook.get('nbformat') as number || 4;
    this._nbformatMinor = this._ynotebook.get('nbformat_minor') as number || 0;

    // Update cells
    const factory = this.contentFactory;
    const cells: ICellModel[] = [];

    for (let i = 0; i < this._ycells.length; i++) {
      const ycell = this._ycells.get(i) as Y.Map<any>;
      const cellType = ycell.get('cell_type') as string;
      let cell: ICellModel | undefined;

      switch (cellType) {
        case 'code':
          cell = factory.createCodeCell({ cell: this._ycellToJSON(ycell) });
          break;
        case 'markdown':
          cell = factory.createMarkdownCell({ cell: this._ycellToJSON(ycell) });
          break;
        case 'raw':
          cell = factory.createRawCell({ cell: this._ycellToJSON(ycell) });
          break;
        default:
          console.warn(`Ignoring unknown cell type: ${cellType}`);
          break;
      }

      if (cell) {
        cells.push(cell);
      }
    }

    // Update the cells list
    this._cells.clear();
    if (cells.length) {
      this._cells.pushAll(cells);
    }

    // Update metadata
    this._metadata = this._ymetadata.toJSON();

    this._updatingFromYjs = false;
    this.triggerContentChange();
  }

  /**
   * Create a Yjs cell map from a cell model.
   */
  private _createYCell(cell: ICellModel): Y.Map<any> {
    const ycell = new Y.Map<any>();
    this._updateYCellFromCell(ycell, cell);
    return ycell;
  }

  /**
   * Update a Yjs cell map from a cell model.
   */
  private _updateYCellFromCell(ycell: Y.Map<any>, cell: ICellModel): void {
    const cellJSON = cell.toJSON();

    // Set cell type
    ycell.set('cell_type', cellJSON.cell_type);

    // Set cell ID
    ycell.set('id', cell.id);

    // Set cell metadata
    const metadata = cellJSON.metadata || {};
    const ymetadata = ycell.get('metadata') as Y.Map<any> || new Y.Map<any>();
    ymetadata.clear();
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
    }

    // Set source
    const source = cellJSON.source || '';
    const ysource = ycell.get('source') as Y.Text || new Y.Text();
    ysource.delete(0, ysource.length);
    ysource.insert(0, source);
    ycell.set('source', ysource);
  }

  /**
   * Update a cell model from a Yjs cell map.
   */
  private _updateCellFromYCell(cell: ICellModel, ycell: Y.Map<any>): void {
    const cellJSON = this._ycellToJSON(ycell);
    cell.fromJSON(cellJSON);
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
   * Whether the model has been disposed.
   */
  get isDisposed(): boolean {
    return this._isDisposed;
  }

  readonly contentFactory: NotebookModel.IContentFactory;

  private _cells: IObservableList<ICellModel>;
  private _dirty = false;
  private _metadata: any = {};
  private _nbformat = 4;
  private _nbformatMinor = 0;
  private _defaultKernelName = '';
  private _defaultKernelLanguage = '';
  private _isDisposed = false;
  private _modelDB: IModelDB | null = null;
  private _isCollaborative = false;
  private _collaborationProvider: ICollaborationProvider | null = null;
  private _versionHistory: IVersionHistory | null = null;

  // Yjs document and shared data structures
  private _ydoc: Y.Doc | null = null;
  private _ynotebook: Y.Map<any> | null = null;
  private _ycells: Y.Array<any> | null = null;
  private _ymetadata: Y.Map<any> | null = null;

  // Flags to prevent update loops
  private _updatingToYjs = false;
  private _updatingFromYjs = false;

  // Signals
  private _stateChanged = new Signal<this, IChangedArgs<any>>(this);
  private _contentChanged = new Signal<this, void>(this);
  private _cellAdded = new Signal<this, { index: number; cell: ICellModel }>(this);
  private _cellRemoved = new Signal<this, { index: number; cell: ICellModel }>(this);
  private _cellMoved = new Signal<this, { fromIndex: number; toIndex: number; cell: ICellModel }>(this);
  private _cellChanged = new Signal<this, { index: number; cell: ICellModel }>(this);
  private _collaborativeUpdate = new Signal<this, void>(this);
}

/**
 * The namespace for the `NotebookModel` class statics.
 */
export namespace NotebookModel {
  /**
   * An options object for initializing a notebook model.
   */
  export interface IOptions {
    /**
     * The language preference for the model.
     */
    languagePreference?: string;

    /**
     * A factory for creating cell models.
     */
    contentFactory?: IContentFactory;

    /**
     * A modelDB for storing notebook data.
     */
    modelDB?: IModelDB;

    /**
     * Whether the model is collaborative.
     */
    collaborative?: boolean;
  }

  /**
   * A factory for creating notebook model content.
   */
  export interface IContentFactory {
    /**
     * Create a new code cell.
     *
     * @param options - The options used to create the cell.
     *
     * @returns A new code cell in the notebook model.
     */
    createCodeCell(options: any): ICodeCellModel;

    /**
     * Create a new markdown cell.
     *
     * @param options - The options used to create the cell.
     *
     * @returns A new markdown cell in the notebook model.
     */
    createMarkdownCell(options: any): IMarkdownCellModel;

    /**
     * Create a new raw cell.
     *
     * @param options - The options used to create the cell.
     *
     * @returns A new raw cell in the notebook model.
     */
    createRawCell(options: any): IRawCellModel;
  }

  /**
   * The default implementation of an `IContentFactory`.
   */
  export class ContentFactory implements IContentFactory {
    /**
     * Create a new code cell.
     *
     * @param options - The options used to create the cell.
     *
     * @returns A new code cell in the notebook model.
     */
    createCodeCell(options: any): ICodeCellModel {
      return new CodeCellModel(options);
    }

    /**
     * Create a new markdown cell.
     *
     * @param options - The options used to create the cell.
     *
     * @returns A new markdown cell in the notebook model.
     */
    createMarkdownCell(options: any): IMarkdownCellModel {
      return new MarkdownCellModel(options);
    }

    /**
     * Create a new raw cell.
     *
     * @param options - The options used to create the cell.
     *
     * @returns A new raw cell in the notebook model.
     */
    createRawCell(options: any): IRawCellModel {
      return new RawCellModel(options);
    }
  }

  /**
   * The default `ContentFactory` instance.
   */
  export const defaultContentFactory = new ContentFactory();
}
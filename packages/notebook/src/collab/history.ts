// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { INotebookModel } from '../model';
import { ISignal, Signal } from '@lumino/signaling';
import { Token } from '@lumino/coreutils';
import * as Y from 'yjs';
import { ICollaborationProvider } from './provider';

/**
 * The version history token.
 *
 * This token is used to provide a version history service for collaborative notebooks.
 * The version history service tracks changes to the notebook and allows users to
 * view, compare, and restore previous versions.
 */
export const IVersionHistory = new Token<IVersionHistory>(
  '@jupyterlab/notebook:IVersionHistory'
);

/**
 * Interface for a version snapshot.
 *
 * A version snapshot represents the state of a notebook at a specific point in time.
 * It includes metadata about the version (timestamp, author) and the state of the
 * document at that time.
 */
export interface IVersionSnapshot {
  /**
   * The unique identifier for this version.
   */
  id: string;

  /**
   * The timestamp when this version was created.
   */
  timestamp: number;

  /**
   * The user who created this version.
   */
  author: {
    /**
     * The user ID.
     */
    id: string;

    /**
     * The user name.
     */
    name: string;

    /**
     * The user color.
     */
    color: string;
  };

  /**
   * A description of the changes in this version.
   */
  description: string;

  /**
   * The Yjs document state vector at this version.
   */
  stateVector: Uint8Array;

  /**
   * The Yjs document update that led to this version.
   */
  update: Uint8Array;

  /**
   * Whether this version is a major version (e.g., explicitly saved by a user).
   */
  isMajorVersion: boolean;

  /**
   * Cell-specific changes in this version.
   */
  cellChanges: ICellChange[];
}

/**
 * Interface for a cell change.
 */
export interface ICellChange {
  /**
   * The cell ID.
   */
  cellId: string;

  /**
   * The type of change.
   */
  changeType: 'added' | 'modified' | 'removed' | 'moved';

  /**
   * The previous index of the cell (for moves).
   */
  previousIndex?: number;

  /**
   * The new index of the cell (for moves).
   */
  newIndex?: number;

  /**
   * The previous content of the cell (for modifications).
   */
  previousContent?: string;

  /**
   * The new content of the cell (for modifications).
   */
  newContent?: string;
}

/**
 * Interface for a version comparison result.
 */
export interface IVersionComparison {
  /**
   * The older version being compared.
   */
  oldVersion: IVersionSnapshot;

  /**
   * The newer version being compared.
   */
  newVersion: IVersionSnapshot;

  /**
   * The differences between the versions.
   */
  differences: {
    /**
     * Cells that were added.
     */
    added: ICellDiff[];

    /**
     * Cells that were removed.
     */
    removed: ICellDiff[];

    /**
     * Cells that were modified.
     */
    modified: ICellDiff[];

    /**
     * Cells that were moved.
     */
    moved: ICellDiff[];

    /**
     * Changes to notebook metadata.
     */
    metadataChanges: IMetadataDiff[];
  };
}

/**
 * Interface for a cell difference.
 */
export interface ICellDiff {
  /**
   * The cell ID.
   */
  cellId: string;

  /**
   * The cell type.
   */
  cellType: string;

  /**
   * The index of the cell in the old version.
   */
  oldIndex?: number;

  /**
   * The index of the cell in the new version.
   */
  newIndex?: number;

  /**
   * The content of the cell in the old version.
   */
  oldContent?: string;

  /**
   * The content of the cell in the new version.
   */
  newContent?: string;

  /**
   * The line-by-line differences in the cell content.
   */
  contentDiff?: ILineDiff[];

  /**
   * The metadata of the cell in the old version.
   */
  oldMetadata?: any;

  /**
   * The metadata of the cell in the new version.
   */
  newMetadata?: any;

  /**
   * The metadata differences.
   */
  metadataDiff?: IMetadataDiff[];

  /**
   * The outputs of the cell in the old version (for code cells).
   */
  oldOutputs?: any[];

  /**
   * The outputs of the cell in the new version (for code cells).
   */
  newOutputs?: any[];
}

/**
 * Interface for a line difference.
 */
export interface ILineDiff {
  /**
   * The type of difference.
   */
  type: 'added' | 'removed' | 'unchanged';

  /**
   * The line content.
   */
  content: string;

  /**
   * The line number in the old version.
   */
  oldLineNumber?: number;

  /**
   * The line number in the new version.
   */
  newLineNumber?: number;
}

/**
 * Interface for a metadata difference.
 */
export interface IMetadataDiff {
  /**
   * The key of the metadata property.
   */
  key: string;

  /**
   * The old value of the metadata property.
   */
  oldValue?: any;

  /**
   * The new value of the metadata property.
   */
  newValue?: any;

  /**
   * The type of change.
   */
  changeType: 'added' | 'removed' | 'modified';
}

/**
 * Interface for a version history service.
 *
 * The version history service tracks changes to a collaborative notebook and
 * allows users to view, compare, and restore previous versions.
 */
export interface IVersionHistory {
  /**
   * A signal emitted when a new version is created.
   */
  readonly versionCreated: ISignal<IVersionHistory, IVersionSnapshot>;

  /**
   * Get all versions of the document.
   *
   * @returns A promise that resolves to an array of version snapshots.
   */
  getVersions(): Promise<IVersionSnapshot[]>;

  /**
   * Get a specific version of the document.
   *
   * @param versionId - The ID of the version to retrieve.
   * @returns A promise that resolves to the version snapshot, or undefined if not found.
   */
  getVersion(versionId: string): Promise<IVersionSnapshot | undefined>;

  /**
   * Create a new version snapshot.
   *
   * @param description - A description of the changes in this version.
   * @param isMajorVersion - Whether this is a major version (e.g., explicitly saved by a user).
   * @returns A promise that resolves to the created version snapshot.
   */
  createVersion(description: string, isMajorVersion?: boolean): Promise<IVersionSnapshot>;

  /**
   * Compare two versions of the document.
   *
   * @param oldVersionId - The ID of the older version.
   * @param newVersionId - The ID of the newer version.
   * @returns A promise that resolves to the version comparison result.
   */
  compareVersions(oldVersionId: string, newVersionId: string): Promise<IVersionComparison>;

  /**
   * Restore the document to a previous version.
   *
   * @param versionId - The ID of the version to restore.
   * @returns A promise that resolves when the restoration is complete.
   */
  restoreVersion(versionId: string): Promise<void>;

  /**
   * Get the changes made to a specific cell across versions.
   *
   * @param cellId - The ID of the cell.
   * @returns A promise that resolves to an array of cell changes.
   */
  getCellHistory(cellId: string): Promise<ICellChange[]>;

  /**
   * Get the document state at a specific version.
   *
   * @param versionId - The ID of the version.
   * @returns A promise that resolves to a Yjs document with the state at that version.
   */
  getDocumentAtVersion(versionId: string): Promise<Y.Doc>;
}

/**
 * Implementation of the version history service for collaborative notebooks.
 *
 * This class tracks changes to a collaborative notebook using Yjs update events
 * and provides methods to view, compare, and restore previous versions.
 */
export class HistoryTracker implements IVersionHistory {
  /**
   * Construct a new HistoryTracker.
   *
   * @param options - The options for the history tracker.
   */
  constructor(options: HistoryTracker.IOptions) {
    this._collaborationProvider = options.collaborationProvider;
    this._notebookModel = options.notebookModel;
    this._maxVersions = options.maxVersions || 100;
    this._snapshotInterval = options.snapshotInterval || 60000; // 1 minute by default

    // Initialize the version history
    this._initializeHistory();

    // Set up update listeners
    this._setupListeners();

    // Start the snapshot timer
    this._startSnapshotTimer();
  }

  /**
   * A signal emitted when a new version is created.
   */
  get versionCreated(): ISignal<IVersionHistory, IVersionSnapshot> {
    return this._versionCreated;
  }

  /**
   * Get all versions of the document.
   *
   * @returns A promise that resolves to an array of version snapshots.
   */
  async getVersions(): Promise<IVersionSnapshot[]> {
    return [...this._versions];
  }

  /**
   * Get a specific version of the document.
   *
   * @param versionId - The ID of the version to retrieve.
   * @returns A promise that resolves to the version snapshot, or undefined if not found.
   */
  async getVersion(versionId: string): Promise<IVersionSnapshot | undefined> {
    return this._versions.find(version => version.id === versionId);
  }

  /**
   * Create a new version snapshot.
   *
   * @param description - A description of the changes in this version.
   * @param isMajorVersion - Whether this is a major version (e.g., explicitly saved by a user).
   * @returns A promise that resolves to the created version snapshot.
   */
  async createVersion(description: string, isMajorVersion = false): Promise<IVersionSnapshot> {
    const ydoc = this._collaborationProvider.ydoc;
    const awareness = this._collaborationProvider.awareness;
    const localState = awareness.getLocalState() || {};
    const user = localState.user || { id: 'unknown', name: 'Unknown User', color: '#000000' };

    // Create a state vector for this version
    const stateVector = Y.encodeStateVector(ydoc);

    // Create an update for this version
    const update = Y.encodeStateAsUpdate(ydoc);

    // Detect cell changes since the last version
    const cellChanges = this._detectCellChanges();

    // Create the version snapshot
    const version: IVersionSnapshot = {
      id: this._generateVersionId(),
      timestamp: Date.now(),
      author: {
        id: user.id,
        name: user.name,
        color: user.color
      },
      description,
      stateVector,
      update,
      isMajorVersion,
      cellChanges
    };

    // Add the version to the history
    this._versions.push(version);

    // Limit the number of versions
    if (this._versions.length > this._maxVersions) {
      this._versions = this._versions.slice(this._versions.length - this._maxVersions);
    }

    // Update the last state for future change detection
    this._updateLastState();

    // Emit the version created signal
    this._versionCreated.emit(version);

    return version;
  }

  /**
   * Compare two versions of the document.
   *
   * @param oldVersionId - The ID of the older version.
   * @param newVersionId - The ID of the newer version.
   * @returns A promise that resolves to the version comparison result.
   */
  async compareVersions(oldVersionId: string, newVersionId: string): Promise<IVersionComparison> {
    // Get the versions
    const oldVersion = await this.getVersion(oldVersionId);
    const newVersion = await this.getVersion(newVersionId);

    if (!oldVersion || !newVersion) {
      throw new Error('Version not found');
    }

    // Get the document states at these versions
    const oldDoc = await this.getDocumentAtVersion(oldVersionId);
    const newDoc = await this.getDocumentAtVersion(newVersionId);

    // Compare the documents
    const differences = this._compareDocuments(oldDoc, newDoc);

    return {
      oldVersion,
      newVersion,
      differences
    };
  }

  /**
   * Restore the document to a previous version.
   *
   * @param versionId - The ID of the version to restore.
   * @returns A promise that resolves when the restoration is complete.
   */
  async restoreVersion(versionId: string): Promise<void> {
    const version = await this.getVersion(versionId);
    if (!version) {
      throw new Error('Version not found');
    }

    const ydoc = this._collaborationProvider.ydoc;
    const restoredDoc = await this.getDocumentAtVersion(versionId);

    // Apply the state from the restored document to the current document
    const update = Y.encodeStateAsUpdate(restoredDoc);
    Y.applyUpdate(ydoc, update);

    // Create a new version to mark the restoration
    await this.createVersion(`Restored to version from ${new Date(version.timestamp).toLocaleString()}`, true);
  }

  /**
   * Get the changes made to a specific cell across versions.
   *
   * @param cellId - The ID of the cell.
   * @returns A promise that resolves to an array of cell changes.
   */
  async getCellHistory(cellId: string): Promise<ICellChange[]> {
    const cellChanges: ICellChange[] = [];

    // Collect all changes to this cell from all versions
    for (const version of this._versions) {
      const changes = version.cellChanges.filter(change => change.cellId === cellId);
      cellChanges.push(...changes);
    }

    return cellChanges;
  }

  /**
   * Get the document state at a specific version.
   *
   * @param versionId - The ID of the version.
   * @returns A promise that resolves to a Yjs document with the state at that version.
   */
  async getDocumentAtVersion(versionId: string): Promise<Y.Doc> {
    const version = await this.getVersion(versionId);
    if (!version) {
      throw new Error('Version not found');
    }

    // Create a new document with the state at this version
    const doc = new Y.Doc();
    Y.applyUpdate(doc, version.update);

    return doc;
  }

  /**
   * Initialize the version history.
   */
  private _initializeHistory(): void {
    // Create an initial version
    this._versions = [];
    this._lastState = {
      cells: new Map(),
      metadata: {}
    };

    // Create the initial version asynchronously
    setTimeout(() => {
      this.createVersion('Initial version', true).catch(error => {
        console.error('Failed to create initial version:', error);
      });
    }, 0);
  }

  /**
   * Set up listeners for document changes.
   */
  private _setupListeners(): void {
    const ydoc = this._collaborationProvider.ydoc;

    // Listen for Yjs document updates
    ydoc.on('update', (update: Uint8Array, origin: any) => {
      // Only track remote changes or local changes that aren't from this tracker
      if (origin !== this) {
        this._pendingChanges = true;
        this._scheduleVersionCreation();
      }
    });

    // Listen for notebook model changes
    if (this._notebookModel) {
      this._notebookModel.stateChanged.connect(this._onNotebookStateChanged, this);
      this._notebookModel.cells.changed.connect(this._onCellsChanged, this);
    }
  }

  /**
   * Handle changes to the notebook state.
   */
  private _onNotebookStateChanged(sender: any, args: any): void {
    this._pendingChanges = true;
    this._scheduleVersionCreation();
  }

  /**
   * Handle changes to the cells list.
   */
  private _onCellsChanged(sender: any, args: any): void {
    this._pendingChanges = true;
    this._scheduleVersionCreation();
  }

  /**
   * Schedule the creation of a new version.
   */
  private _scheduleVersionCreation(): void {
    if (this._versionCreationTimeout) {
      clearTimeout(this._versionCreationTimeout);
    }

    // Create a version after a short delay to batch changes
    this._versionCreationTimeout = setTimeout(() => {
      if (this._pendingChanges) {
        this._pendingChanges = false;
        this.createVersion('Auto-saved changes').catch(error => {
          console.error('Failed to create version:', error);
        });
      }
    }, 2000); // 2 seconds delay
  }

  /**
   * Start the timer for periodic snapshots.
   */
  private _startSnapshotTimer(): void {
    this._snapshotTimer = setInterval(() => {
      // Only create a snapshot if there have been changes
      if (this._pendingChanges) {
        this._pendingChanges = false;
        this.createVersion('Periodic snapshot').catch(error => {
          console.error('Failed to create snapshot:', error);
        });
      }
    }, this._snapshotInterval);
  }

  /**
   * Generate a unique version ID.
   *
   * @returns A unique version ID.
   */
  private _generateVersionId(): string {
    return `version-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  }

  /**
   * Detect changes to cells since the last version.
   *
   * @returns An array of cell changes.
   */
  private _detectCellChanges(): ICellChange[] {
    if (!this._notebookModel) {
      return [];
    }

    const changes: ICellChange[] = [];
    const currentCells = this._notebookModel.cells;
    const lastCells = this._lastState.cells;

    // Check for added, removed, and modified cells
    const currentCellIds = new Set<string>();
    for (let i = 0; i < currentCells.length; i++) {
      const cell = currentCells.get(i);
      if (!cell) continue;

      const cellId = cell.id;
      currentCellIds.add(cellId);

      if (!lastCells.has(cellId)) {
        // Cell was added
        changes.push({
          cellId,
          changeType: 'added',
          newContent: cell.value.text
        });
      } else {
        const lastCell = lastCells.get(cellId)!;
        const lastIndex = lastCell.index;

        if (i !== lastIndex) {
          // Cell was moved
          changes.push({
            cellId,
            changeType: 'moved',
            previousIndex: lastIndex,
            newIndex: i
          });
        }

        if (cell.value.text !== lastCell.content) {
          // Cell content was modified
          changes.push({
            cellId,
            changeType: 'modified',
            previousContent: lastCell.content,
            newContent: cell.value.text
          });
        }
      }
    }

    // Check for removed cells
    for (const [cellId, cellInfo] of lastCells.entries()) {
      if (!currentCellIds.has(cellId)) {
        changes.push({
          cellId,
          changeType: 'removed',
          previousContent: cellInfo.content
        });
      }
    }

    return changes;
  }

  /**
   * Update the last state for future change detection.
   */
  private _updateLastState(): void {
    if (!this._notebookModel) {
      return;
    }

    const cells = new Map<string, { index: number; content: string; type: string; metadata: any }>(
    );

    // Store the current state of cells
    for (let i = 0; i < this._notebookModel.cells.length; i++) {
      const cell = this._notebookModel.cells.get(i);
      if (cell) {
        cells.set(cell.id, {
          index: i,
          content: cell.value.text,
          type: cell.type,
          metadata: { ...cell.metadata.toJSON() }
        });
      }
    }

    // Store the current metadata
    const metadata = { ...this._notebookModel.metadata };

    this._lastState = { cells, metadata };
  }

  /**
   * Compare two Yjs documents to find differences.
   *
   * @param oldDoc - The older document.
   * @param newDoc - The newer document.
   * @returns The differences between the documents.
   */
  private _compareDocuments(oldDoc: Y.Doc, newDoc: Y.Doc): IVersionComparison['differences'] {
    const oldCells = oldDoc.getArray('cells');
    const newCells = newDoc.getArray('cells');
    const oldMetadata = oldDoc.getMap('metadata');
    const newMetadata = newDoc.getMap('metadata');

    const added: ICellDiff[] = [];
    const removed: ICellDiff[] = [];
    const modified: ICellDiff[] = [];
    const moved: ICellDiff[] = [];
    const metadataChanges: IMetadataDiff[] = [];

    // Find added, modified, and moved cells
    const oldCellIds = new Map<string, number>();
    for (let i = 0; i < oldCells.length; i++) {
      const cell = oldCells.get(i) as Y.Map<any>;
      const cellId = cell.get('id') as string;
      oldCellIds.set(cellId, i);
    }

    const newCellIds = new Set<string>();
    for (let i = 0; i < newCells.length; i++) {
      const cell = newCells.get(i) as Y.Map<any>;
      const cellId = cell.get('id') as string;
      newCellIds.add(cellId);

      if (!oldCellIds.has(cellId)) {
        // Cell was added
        added.push(this._createCellDiff(cell, undefined, i));
      } else {
        const oldIndex = oldCellIds.get(cellId)!;
        const oldCell = oldCells.get(oldIndex) as Y.Map<any>;

        if (i !== oldIndex) {
          // Cell was moved
          moved.push(this._createCellDiff(cell, oldCell, i, oldIndex));
        }

        // Check if cell was modified
        if (this._isCellModified(oldCell, cell)) {
          modified.push(this._createCellDiff(cell, oldCell, i, oldIndex));
        }
      }
    }

    // Find removed cells
    for (let i = 0; i < oldCells.length; i++) {
      const cell = oldCells.get(i) as Y.Map<any>;
      const cellId = cell.get('id') as string;

      if (!newCellIds.has(cellId)) {
        // Cell was removed
        removed.push(this._createCellDiff(undefined, cell, undefined, i));
      }
    }

    // Compare metadata
    const oldMetadataKeys = new Set(oldMetadata.keys());
    const newMetadataKeys = new Set(newMetadata.keys());

    // Find added and modified metadata
    for (const key of newMetadataKeys) {
      const newValue = newMetadata.get(key);

      if (!oldMetadataKeys.has(key)) {
        // Metadata was added
        metadataChanges.push({
          key,
          newValue,
          changeType: 'added'
        });
      } else {
        const oldValue = oldMetadata.get(key);
        if (JSON.stringify(oldValue) !== JSON.stringify(newValue)) {
          // Metadata was modified
          metadataChanges.push({
            key,
            oldValue,
            newValue,
            changeType: 'modified'
          });
        }
      }
    }

    // Find removed metadata
    for (const key of oldMetadataKeys) {
      if (!newMetadataKeys.has(key)) {
        // Metadata was removed
        metadataChanges.push({
          key,
          oldValue: oldMetadata.get(key),
          changeType: 'removed'
        });
      }
    }

    return {
      added,
      removed,
      modified,
      moved,
      metadataChanges
    };
  }

  /**
   * Check if a cell was modified.
   *
   * @param oldCell - The old cell.
   * @param newCell - The new cell.
   * @returns Whether the cell was modified.
   */
  private _isCellModified(oldCell: Y.Map<any>, newCell: Y.Map<any>): boolean {
    // Check if cell type changed
    if (oldCell.get('cell_type') !== newCell.get('cell_type')) {
      return true;
    }

    // Check if source changed
    const oldSource = oldCell.get('source') as Y.Text;
    const newSource = newCell.get('source') as Y.Text;
    if (oldSource.toString() !== newSource.toString()) {
      return true;
    }

    // Check if metadata changed
    const oldMetadata = oldCell.get('metadata') as Y.Map<any>;
    const newMetadata = newCell.get('metadata') as Y.Map<any>;
    if (JSON.stringify(oldMetadata.toJSON()) !== JSON.stringify(newMetadata.toJSON())) {
      return true;
    }

    // For code cells, check if outputs changed
    if (oldCell.get('cell_type') === 'code') {
      const oldOutputs = oldCell.get('outputs') as Y.Array<any>;
      const newOutputs = newCell.get('outputs') as Y.Array<any>;

      if (oldOutputs.length !== newOutputs.length) {
        return true;
      }

      for (let i = 0; i < oldOutputs.length; i++) {
        const oldOutput = oldOutputs.get(i) as Y.Map<any>;
        const newOutput = newOutputs.get(i) as Y.Map<any>;

        if (JSON.stringify(oldOutput.toJSON()) !== JSON.stringify(newOutput.toJSON())) {
          return true;
        }
      }
    }

    return false;
  }

  /**
   * Create a cell diff object.
   *
   * @param newCell - The new cell, or undefined if the cell was removed.
   * @param oldCell - The old cell, or undefined if the cell was added.
   * @param newIndex - The index of the cell in the new document, or undefined if the cell was removed.
   * @param oldIndex - The index of the cell in the old document, or undefined if the cell was added.
   * @returns The cell diff object.
   */
  private _createCellDiff(
    newCell: Y.Map<any> | undefined,
    oldCell: Y.Map<any> | undefined,
    newIndex?: number,
    oldIndex?: number
  ): ICellDiff {
    const cellId = (newCell?.get('id') || oldCell?.get('id')) as string;
    const cellType = (newCell?.get('cell_type') || oldCell?.get('cell_type')) as string;

    const diff: ICellDiff = {
      cellId,
      cellType,
      oldIndex,
      newIndex
    };

    // Add content information
    if (oldCell) {
      const oldSource = oldCell.get('source') as Y.Text;
      diff.oldContent = oldSource.toString();
    }

    if (newCell) {
      const newSource = newCell.get('source') as Y.Text;
      diff.newContent = newSource.toString();
    }

    // Add content diff if both old and new content exist
    if (diff.oldContent && diff.newContent) {
      diff.contentDiff = this._createLineDiff(diff.oldContent, diff.newContent);
    }

    // Add metadata information
    if (oldCell) {
      const oldMetadata = oldCell.get('metadata') as Y.Map<any>;
      diff.oldMetadata = oldMetadata.toJSON();
    }

    if (newCell) {
      const newMetadata = newCell.get('metadata') as Y.Map<any>;
      diff.newMetadata = newMetadata.toJSON();
    }

    // Add metadata diff if both old and new metadata exist
    if (diff.oldMetadata && diff.newMetadata) {
      diff.metadataDiff = this._createMetadataDiff(diff.oldMetadata, diff.newMetadata);
    }

    // Add outputs for code cells
    if (cellType === 'code') {
      if (oldCell) {
        const oldOutputs = oldCell.get('outputs') as Y.Array<any>;
        diff.oldOutputs = [];
        for (let i = 0; i < oldOutputs.length; i++) {
          const output = oldOutputs.get(i) as Y.Map<any>;
          diff.oldOutputs.push(output.toJSON());
        }
      }

      if (newCell) {
        const newOutputs = newCell.get('outputs') as Y.Array<any>;
        diff.newOutputs = [];
        for (let i = 0; i < newOutputs.length; i++) {
          const output = newOutputs.get(i) as Y.Map<any>;
          diff.newOutputs.push(output.toJSON());
        }
      }
    }

    return diff;
  }

  /**
   * Create a line-by-line diff of two strings.
   *
   * @param oldContent - The old content.
   * @param newContent - The new content.
   * @returns The line-by-line diff.
   */
  private _createLineDiff(oldContent: string, newContent: string): ILineDiff[] {
    const oldLines = oldContent.split('\n');
    const newLines = newContent.split('\n');
    const diff: ILineDiff[] = [];

    // Simple line-by-line diff implementation
    // For a real implementation, you would use a more sophisticated diff algorithm
    // like Myers diff algorithm or a library like diff-match-patch

    // Find common prefix
    let commonPrefixLength = 0;
    const minLength = Math.min(oldLines.length, newLines.length);
    while (
      commonPrefixLength < minLength &&
      oldLines[commonPrefixLength] === newLines[commonPrefixLength]
    ) {
      diff.push({
        type: 'unchanged',
        content: oldLines[commonPrefixLength],
        oldLineNumber: commonPrefixLength + 1,
        newLineNumber: commonPrefixLength + 1
      });
      commonPrefixLength++;
    }

    // Find common suffix
    let commonSuffixLength = 0;
    while (
      commonSuffixLength < minLength - commonPrefixLength &&
      oldLines[oldLines.length - 1 - commonSuffixLength] ===
        newLines[newLines.length - 1 - commonSuffixLength]
    ) {
      commonSuffixLength++;
    }

    // Add removed lines
    for (
      let i = commonPrefixLength;
      i < oldLines.length - commonSuffixLength;
      i++
    ) {
      diff.push({
        type: 'removed',
        content: oldLines[i],
        oldLineNumber: i + 1
      });
    }

    // Add added lines
    for (
      let i = commonPrefixLength;
      i < newLines.length - commonSuffixLength;
      i++
    ) {
      diff.push({
        type: 'added',
        content: newLines[i],
        newLineNumber: i + 1
      });
    }

    // Add common suffix
    for (let i = 0; i < commonSuffixLength; i++) {
      const oldIndex = oldLines.length - commonSuffixLength + i;
      const newIndex = newLines.length - commonSuffixLength + i;
      diff.push({
        type: 'unchanged',
        content: oldLines[oldIndex],
        oldLineNumber: oldIndex + 1,
        newLineNumber: newIndex + 1
      });
    }

    // Sort by line numbers
    diff.sort((a, b) => {
      const aLine = a.oldLineNumber || a.newLineNumber || 0;
      const bLine = b.oldLineNumber || b.newLineNumber || 0;
      return aLine - bLine;
    });

    return diff;
  }

  /**
   * Create a metadata diff.
   *
   * @param oldMetadata - The old metadata.
   * @param newMetadata - The new metadata.
   * @returns The metadata diff.
   */
  private _createMetadataDiff(oldMetadata: any, newMetadata: any): IMetadataDiff[] {
    const diff: IMetadataDiff[] = [];

    // Find added and modified metadata
    for (const key in newMetadata) {
      if (!(key in oldMetadata)) {
        // Metadata was added
        diff.push({
          key,
          newValue: newMetadata[key],
          changeType: 'added'
        });
      } else if (JSON.stringify(oldMetadata[key]) !== JSON.stringify(newMetadata[key])) {
        // Metadata was modified
        diff.push({
          key,
          oldValue: oldMetadata[key],
          newValue: newMetadata[key],
          changeType: 'modified'
        });
      }
    }

    // Find removed metadata
    for (const key in oldMetadata) {
      if (!(key in newMetadata)) {
        // Metadata was removed
        diff.push({
          key,
          oldValue: oldMetadata[key],
          changeType: 'removed'
        });
      }
    }

    return diff;
  }

  private _collaborationProvider: ICollaborationProvider;
  private _notebookModel: INotebookModel | null;
  private _versions: IVersionSnapshot[] = [];
  private _lastState: {
    cells: Map<string, { index: number; content: string; type: string; metadata: any }>;
    metadata: any;
  };
  private _maxVersions: number;
  private _snapshotInterval: number;
  private _snapshotTimer: any;
  private _pendingChanges = false;
  private _versionCreationTimeout: any;
  private _versionCreated = new Signal<IVersionHistory, IVersionSnapshot>(this);
}

/**
 * Namespace for HistoryTracker.
 */
export namespace HistoryTracker {
  /**
   * Options for the HistoryTracker.
   */
  export interface IOptions {
    /**
     * The collaboration provider.
     */
    collaborationProvider: ICollaborationProvider;

    /**
     * The notebook model.
     */
    notebookModel: INotebookModel | null;

    /**
     * The maximum number of versions to keep.
     */
    maxVersions?: number;

    /**
     * The interval between automatic snapshots, in milliseconds.
     */
    snapshotInterval?: number;
  }
}
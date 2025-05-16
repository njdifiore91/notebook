// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { ISignal, Signal } from '@lumino/signaling';
import { INotebookModel } from '../model';
import * as Y from 'yjs';
import { ICellModel } from '@jupyterlab/cells';

/**
 * Interface for a version history entry.
 */
export interface IVersionEntry {
  /**
   * The unique identifier for this version.
   */
  readonly id: string;

  /**
   * The timestamp when this version was created.
   */
  readonly timestamp: number;

  /**
   * The user who created this version.
   */
  readonly user: {
    id: string;
    name: string;
    color?: string;
    avatar?: string;
  };

  /**
   * A description of the changes in this version.
   */
  readonly description: string;

  /**
   * The encoded snapshot of the document at this version.
   */
  readonly snapshot: Uint8Array;

  /**
   * The encoded snapshot of the document before this version.
   */
  readonly prevSnapshot?: Uint8Array;

  /**
   * Whether this version is a named checkpoint.
   */
  readonly isCheckpoint: boolean;

  /**
   * Optional metadata for this version.
   */
  readonly metadata?: { [key: string]: any };
}

/**
 * Interface for a cell change in the diff.
 */
export interface ICellDiff {
  /**
   * The cell ID.
   */
  readonly cellId: string;

  /**
   * The cell type.
   */
  readonly cellType: 'code' | 'markdown' | 'raw';

  /**
   * The type of change.
   */
  readonly changeType: 'added' | 'removed' | 'modified' | 'unchanged';

  /**
   * The index of the cell in the previous version.
   */
  readonly prevIndex?: number;

  /**
   * The index of the cell in the current version.
   */
  readonly currentIndex?: number;

  /**
   * The previous content of the cell.
   */
  readonly prevContent?: string;

  /**
   * The current content of the cell.
   */
  readonly currentContent?: string;

  /**
   * The user who made the change.
   */
  readonly user?: {
    id: string;
    name: string;
    color?: string;
    avatar?: string;
  };

  /**
   * The timestamp of the change.
   */
  readonly timestamp?: number;

  /**
   * For code cells, the changes in outputs.
   */
  readonly outputChanges?: {
    changeType: 'added' | 'removed' | 'modified' | 'unchanged';
    prevOutput?: any;
    currentOutput?: any;
  }[];

  /**
   * For code cells, the change in execution count.
   */
  readonly executionCountChange?: {
    prev: number | null;
    current: number | null;
  };

  /**
   * Changes in cell metadata.
   */
  readonly metadataChanges?: {
    key: string;
    changeType: 'added' | 'removed' | 'modified';
    prevValue?: any;
    currentValue?: any;
  }[];
}

/**
 * Interface for a document diff between two versions.
 */
export interface IVersionDiff {
  /**
   * The ID of the previous version.
   */
  readonly prevVersionId: string;

  /**
   * The ID of the current version.
   */
  readonly currentVersionId: string;

  /**
   * The timestamp of the previous version.
   */
  readonly prevTimestamp: number;

  /**
   * The timestamp of the current version.
   */
  readonly currentTimestamp: number;

  /**
   * The user who created the current version.
   */
  readonly user: {
    id: string;
    name: string;
    color?: string;
    avatar?: string;
  };

  /**
   * The cell changes in this diff.
   */
  readonly cellDiffs: ICellDiff[];

  /**
   * Changes in notebook metadata.
   */
  readonly metadataChanges: {
    key: string;
    changeType: 'added' | 'removed' | 'modified';
    prevValue?: any;
    currentValue?: any;
  }[];

  /**
   * A summary of the changes.
   */
  readonly summary: string;
}

/**
 * Interface for version history options.
 */
export interface IVersionHistoryOptions {
  /**
   * The maximum number of versions to keep.
   * If not specified, all versions are kept.
   */
  maxVersions?: number;

  /**
   * The minimum time interval (in milliseconds) between automatic snapshots.
   * Default is 60000 (1 minute).
   */
  snapshotInterval?: number;

  /**
   * Whether to automatically create snapshots when changes occur.
   * Default is true.
   */
  autoSnapshot?: boolean;

  /**
   * Whether to track cell-level changes.
   * Default is true.
   */
  trackCellChanges?: boolean;

  /**
   * The current user information.
   */
  currentUser?: {
    id: string;
    name: string;
    color?: string;
    avatar?: string;
  };
}

/**
 * Interface for the version history service.
 */
export interface IVersionHistory {
  /**
   * A signal emitted when a new version is created.
   */
  readonly versionCreated: ISignal<IVersionHistory, IVersionEntry>;

  /**
   * A signal emitted when the current version changes.
   */
  readonly currentVersionChanged: ISignal<IVersionHistory, IVersionEntry>;

  /**
   * A signal emitted when versions are loaded.
   */
  readonly versionsLoaded: ISignal<IVersionHistory, IVersionEntry[]>;

  /**
   * The current version entry.
   */
  readonly currentVersion: IVersionEntry | null;

  /**
   * The list of all version entries.
   */
  readonly versions: ReadonlyArray<IVersionEntry>;

  /**
   * Connect this history tracker to a notebook document.
   */
  connectDocument(document: INotebookModel): void;

  /**
   * Disconnect this history tracker from a notebook document.
   */
  disconnectDocument(document: INotebookModel): void;

  /**
   * Create a new version snapshot.
   * 
   * @param description - A description of the changes in this version.
   * @param isCheckpoint - Whether this version is a named checkpoint.
   * @param metadata - Optional metadata for this version.
   * @returns The created version entry.
   */
  createVersion(description: string, isCheckpoint?: boolean, metadata?: { [key: string]: any }): Promise<IVersionEntry>;

  /**
   * Get a specific version by ID.
   * 
   * @param versionId - The ID of the version to get.
   * @returns The version entry, or null if not found.
   */
  getVersion(versionId: string): IVersionEntry | null;

  /**
   * Restore the document to a specific version.
   * 
   * @param versionId - The ID of the version to restore to.
   * @returns A promise that resolves when the restoration is complete.
   */
  restoreVersion(versionId: string): Promise<void>;

  /**
   * Get the diff between two versions.
   * 
   * @param currentVersionId - The ID of the current version.
   * @param prevVersionId - The ID of the previous version.
   * @returns The diff between the two versions.
   */
  getDiff(currentVersionId: string, prevVersionId: string): IVersionDiff | null;

  /**
   * Get the diff between the current version and the previous version.
   * 
   * @returns The diff between the current and previous versions, or null if there is no previous version.
   */
  getCurrentDiff(): IVersionDiff | null;

  /**
   * Get the cell-level changes for a specific cell between two versions.
   * 
   * @param cellId - The ID of the cell.
   * @param currentVersionId - The ID of the current version.
   * @param prevVersionId - The ID of the previous version.
   * @returns The cell diff, or null if the cell doesn't exist in either version.
   */
  getCellDiff(cellId: string, currentVersionId: string, prevVersionId: string): ICellDiff | null;

  /**
   * Load versions from storage.
   * 
   * @returns A promise that resolves when versions are loaded.
   */
  loadVersions(): Promise<IVersionEntry[]>;

  /**
   * Save versions to storage.
   * 
   * @returns A promise that resolves when versions are saved.
   */
  saveVersions(): Promise<void>;

  /**
   * Clear all versions.
   * 
   * @returns A promise that resolves when versions are cleared.
   */
  clearVersions(): Promise<void>;
}

/**
 * A class that implements version history tracking for collaborative notebooks.
 */
export class HistoryTracker implements IVersionHistory {
  /**
   * Create a new HistoryTracker.
   * 
   * @param options - The options for the history tracker.
   */
  constructor(options: IVersionHistoryOptions = {}) {
    this._options = {
      maxVersions: options.maxVersions,
      snapshotInterval: options.snapshotInterval || 60000, // Default: 1 minute
      autoSnapshot: options.autoSnapshot !== false, // Default: true
      trackCellChanges: options.trackCellChanges !== false, // Default: true
      currentUser: options.currentUser || {
        id: 'anonymous',
        name: 'Anonymous'
      }
    };
  }

  /**
   * A signal emitted when a new version is created.
   */
  get versionCreated(): ISignal<this, IVersionEntry> {
    return this._versionCreated;
  }

  /**
   * A signal emitted when the current version changes.
   */
  get currentVersionChanged(): ISignal<this, IVersionEntry> {
    return this._currentVersionChanged;
  }

  /**
   * A signal emitted when versions are loaded.
   */
  get versionsLoaded(): ISignal<this, IVersionEntry[]> {
    return this._versionsLoaded;
  }

  /**
   * The current version entry.
   */
  get currentVersion(): IVersionEntry | null {
    return this._currentVersion;
  }

  /**
   * The list of all version entries.
   */
  get versions(): ReadonlyArray<IVersionEntry> {
    return this._versions;
  }

  /**
   * Connect this history tracker to a notebook document.
   */
  connectDocument(document: INotebookModel): void {
    if (this._document === document) {
      return;
    }

    // Disconnect from any existing document
    this.disconnectDocument(this._document);

    // Connect to the new document
    this._document = document;

    // Get the Yjs document from the collaboration provider
    if (document.isCollaborative && document.collaborationProvider) {
      this._ydoc = document.collaborationProvider.ydoc;

      if (this._ydoc) {
        // Listen for Yjs document updates
        this._ydoc.on('update', this._onYDocUpdate.bind(this));

        // Create an initial snapshot if no versions exist
        if (this._versions.length === 0) {
          this._createInitialSnapshot();
        }

        // Set up auto-snapshot timer if enabled
        if (this._options.autoSnapshot) {
          this._setupAutoSnapshot();
        }
      }
    }

    // Load existing versions
    this.loadVersions().catch(error => {
      console.error('Failed to load versions:', error);
    });
  }

  /**
   * Disconnect this history tracker from a notebook document.
   */
  disconnectDocument(document: INotebookModel | null): void {
    if (!document || this._document !== document) {
      return;
    }

    // Clear the auto-snapshot timer
    if (this._autoSnapshotTimer) {
      clearTimeout(this._autoSnapshotTimer);
      this._autoSnapshotTimer = null;
    }

    // Remove Yjs document update listener
    if (this._ydoc) {
      this._ydoc.off('update', this._onYDocUpdate);
      this._ydoc = null;
    }

    this._document = null;
  }

  /**
   * Create a new version snapshot.
   * 
   * @param description - A description of the changes in this version.
   * @param isCheckpoint - Whether this version is a named checkpoint.
   * @param metadata - Optional metadata for this version.
   * @returns The created version entry.
   */
  async createVersion(
    description: string,
    isCheckpoint: boolean = false,
    metadata: { [key: string]: any } = {}
  ): Promise<IVersionEntry> {
    if (!this._document || !this._ydoc) {
      throw new Error('No document connected to history tracker');
    }

    // Create a snapshot of the current document state
    const snapshot = Y.encodeStateAsUpdate(this._ydoc);
    
    // Get the previous snapshot if available
    const prevSnapshot = this._currentVersion?.snapshot;

    // Create a new version entry
    const versionEntry: IVersionEntry = {
      id: `v-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: Date.now(),
      user: this._options.currentUser!,
      description,
      snapshot,
      prevSnapshot,
      isCheckpoint,
      metadata
    };

    // Add the version to the list
    this._versions.push(versionEntry);
    this._currentVersion = versionEntry;

    // Enforce maximum versions limit if specified
    if (this._options.maxVersions && this._versions.length > this._options.maxVersions) {
      // Keep all checkpoint versions and remove oldest non-checkpoint versions
      const checkpointVersions = this._versions.filter(v => v.isCheckpoint);
      const nonCheckpointVersions = this._versions.filter(v => !v.isCheckpoint);
      
      const versionsToKeep = this._options.maxVersions - checkpointVersions.length;
      if (versionsToKeep > 0 && nonCheckpointVersions.length > versionsToKeep) {
        // Sort by timestamp (newest first) and keep only the newest ones
        nonCheckpointVersions.sort((a, b) => b.timestamp - a.timestamp);
        const versionsToRemove = nonCheckpointVersions.slice(versionsToKeep);
        
        // Update the versions list
        this._versions = [
          ...checkpointVersions,
          ...nonCheckpointVersions.slice(0, versionsToKeep)
        ].sort((a, b) => a.timestamp - b.timestamp);
      }
    }

    // Save versions to storage
    await this.saveVersions();

    // Emit the version created signal
    this._versionCreated.emit(versionEntry);
    this._currentVersionChanged.emit(versionEntry);

    return versionEntry;
  }

  /**
   * Get a specific version by ID.
   * 
   * @param versionId - The ID of the version to get.
   * @returns The version entry, or null if not found.
   */
  getVersion(versionId: string): IVersionEntry | null {
    return this._versions.find(v => v.id === versionId) || null;
  }

  /**
   * Restore the document to a specific version.
   * 
   * @param versionId - The ID of the version to restore to.
   * @returns A promise that resolves when the restoration is complete.
   */
  async restoreVersion(versionId: string): Promise<void> {
    if (!this._document || !this._ydoc) {
      throw new Error('No document connected to history tracker');
    }

    const version = this.getVersion(versionId);
    if (!version) {
      throw new Error(`Version with ID ${versionId} not found`);
    }

    // Create a snapshot of the current state before restoration
    await this.createVersion(
      `Snapshot before restoring to version ${version.description}`,
      false,
      { restorationPoint: true }
    );

    // Apply the snapshot to restore the document state
    Y.applyUpdate(this._ydoc, version.snapshot);

    // Create a new version entry for the restored state
    const restoredVersion = await this.createVersion(
      `Restored to: ${version.description}`,
      false,
      { restoredFrom: version.id }
    );

    // Update the current version
    this._currentVersion = restoredVersion;
    this._currentVersionChanged.emit(restoredVersion);
  }

  /**
   * Get the diff between two versions.
   * 
   * @param currentVersionId - The ID of the current version.
   * @param prevVersionId - The ID of the previous version.
   * @returns The diff between the two versions.
   */
  getDiff(currentVersionId: string, prevVersionId: string): IVersionDiff | null {
    const currentVersion = this.getVersion(currentVersionId);
    const prevVersion = this.getVersion(prevVersionId);

    if (!currentVersion || !prevVersion) {
      return null;
    }

    // Create temporary Yjs documents to compute the diff
    const currentDoc = new Y.Doc();
    const prevDoc = new Y.Doc();

    // Apply the snapshots to the temporary documents
    Y.applyUpdate(currentDoc, currentVersion.snapshot);
    Y.applyUpdate(prevDoc, prevVersion.snapshot);

    // Get the notebook data from both documents
    const currentNotebook = this._getNotebookDataFromYDoc(currentDoc);
    const prevNotebook = this._getNotebookDataFromYDoc(prevDoc);

    if (!currentNotebook || !prevNotebook) {
      return null;
    }

    // Compute cell diffs
    const cellDiffs: ICellDiff[] = [];

    // Track cells that have been processed
    const processedCellIds = new Set<string>();

    // First, process cells in the current version
    for (let i = 0; i < currentNotebook.cells.length; i++) {
      const currentCell = currentNotebook.cells[i];
      const cellId = currentCell.id;
      processedCellIds.add(cellId);

      // Find the cell in the previous version
      const prevCellIndex = prevNotebook.cells.findIndex(cell => cell.id === cellId);
      
      if (prevCellIndex === -1) {
        // Cell was added
        cellDiffs.push({
          cellId,
          cellType: currentCell.cell_type as any,
          changeType: 'added',
          currentIndex: i,
          currentContent: currentCell.source,
          user: currentVersion.user,
          timestamp: currentVersion.timestamp,
          metadataChanges: this._computeMetadataChanges(undefined, currentCell.metadata)
        });
      } else {
        // Cell exists in both versions
        const prevCell = prevNotebook.cells[prevCellIndex];
        const contentChanged = prevCell.source !== currentCell.source;
        const metadataChanges = this._computeMetadataChanges(prevCell.metadata, currentCell.metadata);
        
        // For code cells, check output changes
        let outputChanges;
        let executionCountChange;
        
        if (currentCell.cell_type === 'code' && prevCell.cell_type === 'code') {
          outputChanges = this._computeOutputChanges(prevCell.outputs, currentCell.outputs);
          
          if (prevCell.execution_count !== currentCell.execution_count) {
            executionCountChange = {
              prev: prevCell.execution_count,
              current: currentCell.execution_count
            };
          }
        }

        // Determine if the cell was modified
        const isModified = contentChanged || 
                          (metadataChanges && metadataChanges.length > 0) ||
                          (outputChanges && outputChanges.some(change => change.changeType !== 'unchanged')) ||
                          executionCountChange !== undefined;

        if (isModified) {
          cellDiffs.push({
            cellId,
            cellType: currentCell.cell_type as any,
            changeType: 'modified',
            prevIndex: prevCellIndex,
            currentIndex: i,
            prevContent: prevCell.source,
            currentContent: currentCell.source,
            user: currentVersion.user,
            timestamp: currentVersion.timestamp,
            outputChanges,
            executionCountChange,
            metadataChanges
          });
        } else {
          cellDiffs.push({
            cellId,
            cellType: currentCell.cell_type as any,
            changeType: 'unchanged',
            prevIndex: prevCellIndex,
            currentIndex: i
          });
        }
      }
    }

    // Then, find cells that were in the previous version but not in the current version
    for (let i = 0; i < prevNotebook.cells.length; i++) {
      const prevCell = prevNotebook.cells[i];
      const cellId = prevCell.id;
      
      if (!processedCellIds.has(cellId)) {
        // Cell was removed
        cellDiffs.push({
          cellId,
          cellType: prevCell.cell_type as any,
          changeType: 'removed',
          prevIndex: i,
          prevContent: prevCell.source,
          user: currentVersion.user,
          timestamp: currentVersion.timestamp,
          metadataChanges: this._computeMetadataChanges(prevCell.metadata, undefined)
        });
      }
    }

    // Compute metadata changes
    const metadataChanges = this._computeMetadataChanges(prevNotebook.metadata, currentNotebook.metadata);

    // Generate a summary of the changes
    const summary = this._generateDiffSummary(cellDiffs, metadataChanges);

    return {
      prevVersionId,
      currentVersionId,
      prevTimestamp: prevVersion.timestamp,
      currentTimestamp: currentVersion.timestamp,
      user: currentVersion.user,
      cellDiffs,
      metadataChanges,
      summary
    };
  }

  /**
   * Get the diff between the current version and the previous version.
   * 
   * @returns The diff between the current and previous versions, or null if there is no previous version.
   */
  getCurrentDiff(): IVersionDiff | null {
    if (!this._currentVersion || this._versions.length < 2) {
      return null;
    }

    // Find the index of the current version
    const currentIndex = this._versions.findIndex(v => v.id === this._currentVersion!.id);
    if (currentIndex <= 0) {
      return null;
    }

    // Get the previous version
    const prevVersion = this._versions[currentIndex - 1];

    return this.getDiff(this._currentVersion.id, prevVersion.id);
  }

  /**
   * Get the cell-level changes for a specific cell between two versions.
   * 
   * @param cellId - The ID of the cell.
   * @param currentVersionId - The ID of the current version.
   * @param prevVersionId - The ID of the previous version.
   * @returns The cell diff, or null if the cell doesn't exist in either version.
   */
  getCellDiff(cellId: string, currentVersionId: string, prevVersionId: string): ICellDiff | null {
    const diff = this.getDiff(currentVersionId, prevVersionId);
    if (!diff) {
      return null;
    }

    return diff.cellDiffs.find(cellDiff => cellDiff.cellId === cellId) || null;
  }

  /**
   * Load versions from storage.
   * 
   * @returns A promise that resolves when versions are loaded.
   */
  async loadVersions(): Promise<IVersionEntry[]> {
    // In a real implementation, this would load versions from a database or file system
    // For now, we'll just return the in-memory versions
    this._versionsLoaded.emit(this._versions);
    return this._versions;
  }

  /**
   * Save versions to storage.
   * 
   * @returns A promise that resolves when versions are saved.
   */
  async saveVersions(): Promise<void> {
    // In a real implementation, this would save versions to a database or file system
    // For now, we'll just do nothing
    return;
  }

  /**
   * Clear all versions.
   * 
   * @returns A promise that resolves when versions are cleared.
   */
  async clearVersions(): Promise<void> {
    this._versions = [];
    this._currentVersion = null;
    await this.saveVersions();
    this._versionsLoaded.emit([]);
    return;
  }

  /**
   * Handle Yjs document updates.
   */
  private _onYDocUpdate(update: Uint8Array, origin: any): void {
    // Skip updates that originated from this history tracker
    if (origin === this) {
      return;
    }

    // Reset the auto-snapshot timer if enabled
    if (this._options.autoSnapshot && this._autoSnapshotTimer) {
      clearTimeout(this._autoSnapshotTimer);
      this._setupAutoSnapshot();
    }

    // Track the update for potential future snapshot
    this._pendingUpdates.push({
      update,
      timestamp: Date.now(),
      origin
    });

    // If we have accumulated enough updates or enough time has passed,
    // create a new snapshot automatically
    const timeSinceLastSnapshot = Date.now() - (this._lastSnapshotTime || 0);
    const updateCountThreshold = 10; // Create snapshot after 10 updates

    if (this._options.autoSnapshot && 
        (this._pendingUpdates.length >= updateCountThreshold || 
         timeSinceLastSnapshot >= this._options.snapshotInterval)) {
      this._createAutomaticSnapshot();
    }
  }

  /**
   * Set up the auto-snapshot timer.
   */
  private _setupAutoSnapshot(): void {
    if (this._autoSnapshotTimer) {
      clearTimeout(this._autoSnapshotTimer);
    }

    this._autoSnapshotTimer = setTimeout(() => {
      this._createAutomaticSnapshot();
    }, this._options.snapshotInterval);
  }

  /**
   * Create an automatic snapshot if there are pending updates.
   */
  private _createAutomaticSnapshot(): void {
    if (this._pendingUpdates.length === 0) {
      return;
    }

    // Determine the origin of the updates for attribution
    let origin = this._pendingUpdates[this._pendingUpdates.length - 1].origin;
    let user = this._options.currentUser!;

    // If the origin contains user information, use it
    if (origin && typeof origin === 'object' && origin.user) {
      user = origin.user;
    }

    // Create a description based on the number of updates
    const description = `Automatic snapshot after ${this._pendingUpdates.length} update${this._pendingUpdates.length !== 1 ? 's' : ''}`;

    // Create a new version
    this.createVersion(description, false, { automatic: true }).catch(error => {
      console.error('Failed to create automatic snapshot:', error);
    });

    // Clear pending updates and update last snapshot time
    this._pendingUpdates = [];
    this._lastSnapshotTime = Date.now();
  }

  /**
   * Create an initial snapshot of the document.
   */
  private _createInitialSnapshot(): void {
    if (!this._ydoc) {
      return;
    }

    this.createVersion('Initial version', true).catch(error => {
      console.error('Failed to create initial snapshot:', error);
    });
  }

  /**
   * Extract notebook data from a Yjs document.
   */
  private _getNotebookDataFromYDoc(ydoc: Y.Doc): any {
    try {
      // Get the notebook map from the Yjs document
      const ynotebook = ydoc.getMap('notebook');
      const ycells = ydoc.getArray('cells');
      const ymetadata = ydoc.getMap('metadata');

      // Extract notebook metadata
      const metadata = ymetadata.toJSON();

      // Extract cells
      const cells: any[] = [];
      for (let i = 0; i < ycells.length; i++) {
        const ycell = ycells.get(i) as Y.Map<any>;
        if (!ycell) continue;

        const cellType = ycell.get('cell_type') as string;
        const cellId = ycell.get('id') as string;
        const ymetadata = ycell.get('metadata') as Y.Map<any>;
        const ysource = ycell.get('source') as Y.Text;

        const cell: any = {
          id: cellId,
          cell_type: cellType,
          metadata: ymetadata ? ymetadata.toJSON() : {},
          source: ysource ? ysource.toString() : ''
        };

        // Handle code cell specific properties
        if (cellType === 'code') {
          cell.execution_count = ycell.get('execution_count') as number | null;
          
          // Extract outputs
          const youtputs = ycell.get('outputs') as Y.Array<any>;
          if (youtputs) {
            cell.outputs = [];
            for (let j = 0; j < youtputs.length; j++) {
              const youtput = youtputs.get(j) as Y.Map<any>;
              if (youtput) {
                cell.outputs.push(youtput.toJSON());
              }
            }
          } else {
            cell.outputs = [];
          }
        }

        cells.push(cell);
      }

      return {
        metadata,
        cells,
        nbformat: ynotebook.get('nbformat') as number || 4,
        nbformat_minor: ynotebook.get('nbformat_minor') as number || 0
      };
    } catch (error) {
      console.error('Error extracting notebook data from Yjs document:', error);
      return null;
    }
  }

  /**
   * Compute the changes between two metadata objects.
   */
  private _computeMetadataChanges(prevMetadata: any = {}, currentMetadata: any = {}): {
    key: string;
    changeType: 'added' | 'removed' | 'modified';
    prevValue?: any;
    currentValue?: any;
  }[] {
    const changes: {
      key: string;
      changeType: 'added' | 'removed' | 'modified';
      prevValue?: any;
      currentValue?: any;
    }[] = [];

    // Check for added or modified keys
    for (const key in currentMetadata) {
      if (!Object.prototype.hasOwnProperty.call(currentMetadata, key)) {
        continue;
      }

      if (!(key in prevMetadata)) {
        // Key was added
        changes.push({
          key,
          changeType: 'added',
          currentValue: currentMetadata[key]
        });
      } else if (JSON.stringify(prevMetadata[key]) !== JSON.stringify(currentMetadata[key])) {
        // Key was modified
        changes.push({
          key,
          changeType: 'modified',
          prevValue: prevMetadata[key],
          currentValue: currentMetadata[key]
        });
      }
    }

    // Check for removed keys
    for (const key in prevMetadata) {
      if (!Object.prototype.hasOwnProperty.call(prevMetadata, key)) {
        continue;
      }

      if (!(key in currentMetadata)) {
        // Key was removed
        changes.push({
          key,
          changeType: 'removed',
          prevValue: prevMetadata[key]
        });
      }
    }

    return changes;
  }

  /**
   * Compute the changes between two sets of outputs.
   */
  private _computeOutputChanges(prevOutputs: any[] = [], currentOutputs: any[] = []): {
    changeType: 'added' | 'removed' | 'modified' | 'unchanged';
    prevOutput?: any;
    currentOutput?: any;
  }[] {
    const changes: {
      changeType: 'added' | 'removed' | 'modified' | 'unchanged';
      prevOutput?: any;
      currentOutput?: any;
    }[] = [];

    // Use a simple approach for now: compare outputs by index
    // A more sophisticated approach would be to use a diff algorithm
    const maxLength = Math.max(prevOutputs.length, currentOutputs.length);

    for (let i = 0; i < maxLength; i++) {
      const prevOutput = i < prevOutputs.length ? prevOutputs[i] : undefined;
      const currentOutput = i < currentOutputs.length ? currentOutputs[i] : undefined;

      if (prevOutput === undefined) {
        // Output was added
        changes.push({
          changeType: 'added',
          currentOutput
        });
      } else if (currentOutput === undefined) {
        // Output was removed
        changes.push({
          changeType: 'removed',
          prevOutput
        });
      } else if (JSON.stringify(prevOutput) !== JSON.stringify(currentOutput)) {
        // Output was modified
        changes.push({
          changeType: 'modified',
          prevOutput,
          currentOutput
        });
      } else {
        // Output is unchanged
        changes.push({
          changeType: 'unchanged',
          prevOutput,
          currentOutput
        });
      }
    }

    return changes;
  }

  /**
   * Generate a summary of the changes in a diff.
   */
  private _generateDiffSummary(
    cellDiffs: ICellDiff[],
    metadataChanges: {
      key: string;
      changeType: 'added' | 'removed' | 'modified';
      prevValue?: any;
      currentValue?: any;
    }[]
  ): string {
    const addedCells = cellDiffs.filter(diff => diff.changeType === 'added').length;
    const removedCells = cellDiffs.filter(diff => diff.changeType === 'removed').length;
    const modifiedCells = cellDiffs.filter(diff => diff.changeType === 'modified').length;
    const metadataChangeCount = metadataChanges.length;

    const parts: string[] = [];

    if (addedCells > 0) {
      parts.push(`${addedCells} cell${addedCells !== 1 ? 's' : ''} added`);
    }

    if (removedCells > 0) {
      parts.push(`${removedCells} cell${removedCells !== 1 ? 's' : ''} removed`);
    }

    if (modifiedCells > 0) {
      parts.push(`${modifiedCells} cell${modifiedCells !== 1 ? 's' : ''} modified`);
    }

    if (metadataChangeCount > 0) {
      parts.push(`${metadataChangeCount} metadata change${metadataChangeCount !== 1 ? 's' : ''}`);
    }

    if (parts.length === 0) {
      return 'No changes';
    }

    return parts.join(', ');
  }

  private _document: INotebookModel | null = null;
  private _ydoc: Y.Doc | null = null;
  private _versions: IVersionEntry[] = [];
  private _currentVersion: IVersionEntry | null = null;
  private _options: Required<Omit<IVersionHistoryOptions, 'maxVersions'>> & { maxVersions?: number };
  private _autoSnapshotTimer: any = null;
  private _lastSnapshotTime: number | null = null;
  private _pendingUpdates: { update: Uint8Array; timestamp: number; origin: any }[] = [];

  private _versionCreated = new Signal<this, IVersionEntry>(this);
  private _currentVersionChanged = new Signal<this, IVersionEntry>(this);
  private _versionsLoaded = new Signal<this, IVersionEntry[]>(this);
}
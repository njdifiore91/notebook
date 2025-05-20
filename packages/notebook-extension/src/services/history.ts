// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

/**
 * Interface for a version in the history of a document.
 */
export interface IHistoryVersion {
  /**
   * Unique identifier for the version.
   */
  id: string;

  /**
   * Timestamp when the version was created.
   */
  timestamp: string;

  /**
   * Author of the version.
   */
  author: string;

  /**
   * Optional description of the changes in this version.
   */
  description?: string;
}

/**
 * Interface for a change in a cell diff.
 */
export interface IVersionChange {
  /**
   * Type of change: addition, deletion, or unchanged.
   */
  type: 'addition' | 'deletion' | 'unchanged';

  /**
   * Content of the change.
   */
  content: string;

  /**
   * Line number in the original version (for deletions and unchanged).
   */
  oldLineNumber?: number;

  /**
   * Line number in the new version (for additions and unchanged).
   */
  newLineNumber?: number;
}

/**
 * Interface for a cell diff between two versions.
 */
export interface ICellDiff {
  /**
   * Type of the cell.
   */
  cellType: 'code' | 'markdown' | 'raw';

  /**
   * Index of the cell in the original version.
   */
  oldIndex?: number;

  /**
   * Index of the cell in the new version.
   */
  newIndex?: number;

  /**
   * List of changes in the cell content.
   */
  changes: IVersionChange[];
}

/**
 * Interface for a diff between two versions of a document.
 */
export interface IVersionDiff {
  /**
   * ID of the first version (newer).
   */
  fromVersionId: string;

  /**
   * ID of the second version (older).
   */
  toVersionId: string;

  /**
   * List of cell diffs.
   */
  cells: ICellDiff[];

  /**
   * Summary of changes.
   */
  summary: {
    /**
     * Number of cells added.
     */
    cellsAdded: number;

    /**
     * Number of cells deleted.
     */
    cellsDeleted: number;

    /**
     * Number of cells modified.
     */
    cellsModified: number;
  };
}

/**
 * Interface for the history service.
 */
export interface IHistoryService {
  /**
   * Get the version history for a document.
   *
   * @param documentId - The ID of the document.
   * @returns A promise that resolves to an array of versions.
   */
  getVersionHistory(documentId: string): Promise<IHistoryVersion[]>;

  /**
   * Get a specific version of a document.
   *
   * @param documentId - The ID of the document.
   * @param versionId - The ID of the version.
   * @returns A promise that resolves to the document content at the specified version.
   */
  getVersion(documentId: string, versionId: string): Promise<any>;

  /**
   * Get a diff between two versions of a document.
   *
   * @param documentId - The ID of the document.
   * @param fromVersionId - The ID of the first version (newer).
   * @param toVersionId - The ID of the second version (older).
   * @param diffType - The type of diff visualization to generate.
   * @returns A promise that resolves to a diff between the two versions.
   */
  getVersionDiff(
    documentId: string,
    fromVersionId: string,
    toVersionId: string,
    diffType?: 'inline' | 'side-by-side' | 'unified'
  ): Promise<IVersionDiff>;

  /**
   * Restore a document to a specific version.
   *
   * @param documentId - The ID of the document.
   * @param versionId - The ID of the version to restore to.
   * @returns A promise that resolves when the document has been restored.
   */
  restoreVersion(documentId: string, versionId: string): Promise<void>;

  /**
   * Create a new version of a document.
   *
   * @param documentId - The ID of the document.
   * @param description - Optional description of the changes.
   * @returns A promise that resolves to the new version.
   */
  createVersion(documentId: string, description?: string): Promise<IHistoryVersion>;
}

/**
 * Token for the history service.
 */
export const IHistoryService = Symbol('jupyter.services.history');
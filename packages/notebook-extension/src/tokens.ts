// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { Token } from '@lumino/coreutils';
import { ISignal } from '@lumino/signaling';
import { Widget } from '@lumino/widgets';

/**
 * The token for the history service.
 */
export const IHistoryService = new Token<IHistoryService>(
  'jupyter-notebook/collaboration:IHistoryService'
);

/**
 * Interface for the history service.
 */
export interface IHistoryService {
  /**
   * Signal emitted when a new version is added to the history.
   */
  readonly versionAdded: ISignal<IHistoryService, VersionInfo>;

  /**
   * Get the version history for a notebook.
   *
   * @param path - The path to the notebook.
   * @returns A promise that resolves to an array of version information.
   */
  getVersionHistory(path: string): Promise<VersionInfo[]>;

  /**
   * Get a specific version of a notebook.
   *
   * @param path - The path to the notebook.
   * @param versionId - The ID of the version to retrieve.
   * @returns A promise that resolves to the notebook content at that version.
   */
  getVersion(path: string, versionId: string): Promise<any>;

  /**
   * Restore a notebook to a specific version.
   *
   * @param path - The path to the notebook.
   * @param versionId - The ID of the version to restore to.
   * @returns A promise that resolves when the restore is complete.
   */
  restoreVersion(path: string, versionId: string): Promise<void>;

  /**
   * Render a diff between two versions.
   *
   * @param oldVersion - The older version.
   * @param newVersion - The newer version.
   * @param diffType - The type of diff visualization to use.
   * @returns A widget containing the rendered diff.
   */
  renderDiff(oldVersion: VersionInfo, newVersion: VersionInfo, diffType: DiffType): Widget;

  /**
   * Create a snapshot of the current notebook state.
   *
   * @param path - The path to the notebook.
   * @param message - An optional commit message.
   * @returns A promise that resolves to the created version information.
   */
  createSnapshot(path: string, message?: string): Promise<VersionInfo>;
}

/**
 * Information about a version in the history.
 */
export interface VersionInfo {
  /**
   * The unique identifier for the version.
   */
  id: string;

  /**
   * The timestamp when the version was created.
   */
  timestamp: number;

  /**
   * The author of the version.
   */
  author: string;

  /**
   * An optional message associated with the version.
   */
  message?: string;

  /**
   * The number of cells changed in this version.
   */
  cellsChanged?: number;

  /**
   * The number of lines added in this version.
   */
  linesAdded?: number;

  /**
   * The number of lines deleted in this version.
   */
  linesDeleted?: number;
}

/**
 * The type of diff visualization to use.
 */
export type DiffType = 'unified' | 'side-by-side' | 'inline';
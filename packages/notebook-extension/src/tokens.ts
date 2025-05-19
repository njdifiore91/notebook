// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { Token } from '@lumino/coreutils';

/**
 * Interface for the presence service that manages user awareness
 */
export interface IPresenceService {
  /**
   * Focus the view on a specific user's cursor position
   * 
   * @param clientId - The client ID of the user to focus on
   */
  focusOnUserCursor(clientId: number): void;

  /**
   * Update the local user's status
   * 
   * @param status - The new status to set
   */
  updateStatus(status: 'active' | 'idle' | 'viewing' | 'editing'): void;

  /**
   * Update the local user's cursor position
   * 
   * @param cellId - The ID of the cell where the cursor is located
   * @param position - The position within the cell
   */
  updateCursorPosition(cellId: string, position: number): void;

  /**
   * Update the local user's selection range
   * 
   * @param cellId - The ID of the cell where the selection is located
   * @param start - The start position of the selection
   * @param end - The end position of the selection
   */
  updateSelectionRange(cellId: string, start: number, end: number): void;
}

/**
 * Token for the presence service
 */
export const IPresenceService = new Token<IPresenceService>(
  'jupyter-notebook/collaboration:IPresenceService'
);
// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { ISignal, Signal } from '@lumino/signaling';
import { Awareness } from 'y-protocols/awareness';
import * as Y from 'yjs';

/**
 * User status types for awareness.
 */
export enum UserStatus {
  /**
   * User is actively editing or interacting with the notebook.
   */
  Active = 'active',

  /**
   * User is viewing but not editing the notebook.
   */
  Viewing = 'viewing',

  /**
   * User is connected but idle (no activity for some time).
   */
  Idle = 'idle',

  /**
   * User is editing a specific cell.
   */
  Editing = 'editing'
}

/**
 * Interface for cursor position information.
 */
export interface ICursorPosition {
  /**
   * The cell ID where the cursor is located.
   */
  cellId: string;

  /**
   * The character offset within the cell.
   */
  offset: number;
}

/**
 * Interface for selection range information.
 */
export interface ISelectionRange {
  /**
   * The cell ID where the selection starts.
   */
  startCellId: string;

  /**
   * The character offset where the selection starts.
   */
  startOffset: number;

  /**
   * The cell ID where the selection ends.
   */
  endCellId: string;

  /**
   * The character offset where the selection ends.
   */
  endOffset: number;
}

/**
 * Interface for user awareness state.
 */
export interface IUserAwarenessState {
  /**
   * The user's unique identifier.
   */
  userId: string;

  /**
   * The user's display name.
   */
  displayName: string;

  /**
   * The user's avatar URL (optional).
   */
  avatarUrl?: string;

  /**
   * The user's current status.
   */
  status: UserStatus;

  /**
   * The user's cursor position (optional).
   */
  cursor?: ICursorPosition;

  /**
   * The user's selection range (optional).
   */
  selection?: ISelectionRange;

  /**
   * The user's color for UI elements.
   */
  color: string;

  /**
   * The timestamp of the last activity.
   */
  lastActivity: number;
}

/**
 * Interface for awareness change events.
 */
export interface IAwarenessChanges {
  /**
   * Array of client IDs that were added.
   */
  added: number[];

  /**
   * Array of client IDs that were updated.
   */
  updated: number[];

  /**
   * Array of client IDs that were removed.
   */
  removed: number[];
}

/**
 * Interface for the presence tracker.
 */
export interface IPresenceTracker {
  /**
   * Signal emitted when the awareness state changes.
   */
  readonly stateChanged: ISignal<IPresenceTracker, IAwarenessChanges>;

  /**
   * Get the local client ID.
   */
  readonly clientId: number;

  /**
   * Set the local user's awareness state.
   *
   * @param state - The user awareness state to set.
   */
  setLocalState(state: IUserAwarenessState): void;

  /**
   * Update a specific field in the local user's awareness state.
   *
   * @param field - The field to update.
   * @param value - The new value for the field.
   */
  updateLocalState(field: string, value: any): void;

  /**
   * Get the local user's awareness state.
   *
   * @returns The local user's awareness state, or null if not set.
   */
  getLocalState(): IUserAwarenessState | null;

  /**
   * Get all users' awareness states.
   *
   * @returns A map of client IDs to awareness states.
   */
  getStates(): Map<number, IUserAwarenessState>;

  /**
   * Set the user's cursor position.
   *
   * @param position - The cursor position information.
   */
  setCursorPosition(position: ICursorPosition): void;

  /**
   * Set the user's selection range.
   *
   * @param range - The selection range information.
   */
  setSelectionRange(range: ISelectionRange): void;

  /**
   * Set the user's status.
   *
   * @param status - The user status to set.
   */
  setStatus(status: UserStatus): void;

  /**
   * Mark the user as active, updating the lastActivity timestamp.
   */
  markActive(): void;

  /**
   * Check if a user is currently editing a specific cell.
   *
   * @param cellId - The cell ID to check.
   * @returns The client ID of the user editing the cell, or null if no one is editing.
   */
  isEditingCell(cellId: string): number | null;

  /**
   * Destroy the presence tracker and clean up resources.
   */
  destroy(): void;
}

/**
 * Implementation of the presence tracker using Yjs awareness.
 */
export class PresenceTracker implements IPresenceTracker {
  /**
   * Create a new PresenceTracker instance.
   *
   * @param doc - The Yjs document to associate with this tracker.
   * @param options - Configuration options.
   */
  constructor(
    doc: Y.Doc,
    options: PresenceTracker.IOptions = {}
  ) {
    this._awareness = new Awareness(doc);
    this._clientId = doc.clientID;
    this._idleTimeout = options.idleTimeout ?? 60000; // Default: 1 minute
    this._cleanupInterval = options.cleanupInterval ?? 30000; // Default: 30 seconds

    // Set up event handlers
    this._awareness.on('change', this._onAwarenessChange.bind(this));

    // Set up automatic cleanup of disconnected users
    this._cleanupTimer = setInterval(() => {
      this._cleanupDisconnectedUsers();
    }, this._cleanupInterval);
  }

  /**
   * Signal emitted when the awareness state changes.
   */
  get stateChanged(): ISignal<IPresenceTracker, IAwarenessChanges> {
    return this._stateChanged;
  }

  /**
   * Get the local client ID.
   */
  get clientId(): number {
    return this._clientId;
  }

  /**
   * Set the local user's awareness state.
   *
   * @param state - The user awareness state to set.
   */
  setLocalState(state: IUserAwarenessState): void {
    // Ensure lastActivity is set
    const updatedState = {
      ...state,
      lastActivity: Date.now()
    };

    this._awareness.setLocalState(updatedState);
  }

  /**
   * Update a specific field in the local user's awareness state.
   *
   * @param field - The field to update.
   * @param value - The new value for the field.
   */
  updateLocalState(field: string, value: any): void {
    const currentState = this.getLocalState();
    if (!currentState) {
      return;
    }

    const updatedState = {
      ...currentState,
      [field]: value,
      lastActivity: Date.now()
    };

    this._awareness.setLocalState(updatedState);
  }

  /**
   * Get the local user's awareness state.
   *
   * @returns The local user's awareness state, or null if not set.
   */
  getLocalState(): IUserAwarenessState | null {
    return this._awareness.getLocalState() as IUserAwarenessState | null;
  }

  /**
   * Get all users' awareness states.
   *
   * @returns A map of client IDs to awareness states.
   */
  getStates(): Map<number, IUserAwarenessState> {
    return this._awareness.getStates() as Map<number, IUserAwarenessState>;
  }

  /**
   * Set the user's cursor position.
   *
   * @param position - The cursor position information.
   */
  setCursorPosition(position: ICursorPosition): void {
    this.updateLocalState('cursor', position);
  }

  /**
   * Set the user's selection range.
   *
   * @param range - The selection range information.
   */
  setSelectionRange(range: ISelectionRange): void {
    this.updateLocalState('selection', range);
  }

  /**
   * Set the user's status.
   *
   * @param status - The user status to set.
   */
  setStatus(status: UserStatus): void {
    this.updateLocalState('status', status);
  }

  /**
   * Mark the user as active, updating the lastActivity timestamp.
   */
  markActive(): void {
    const currentState = this.getLocalState();
    if (!currentState) {
      return;
    }

    // Only update if the current status is not 'editing'
    if (currentState.status !== UserStatus.Editing) {
      this.setStatus(UserStatus.Active);
    }

    // Always update the lastActivity timestamp
    this.updateLocalState('lastActivity', Date.now());
  }

  /**
   * Check if a user is currently editing a specific cell.
   *
   * @param cellId - The cell ID to check.
   * @returns The client ID of the user editing the cell, or null if no one is editing.
   */
  isEditingCell(cellId: string): number | null {
    const states = this.getStates();
    for (const [clientId, state] of states.entries()) {
      if (
        state.status === UserStatus.Editing &&
        state.cursor?.cellId === cellId
      ) {
        return clientId;
      }
    }
    return null;
  }

  /**
   * Destroy the presence tracker and clean up resources.
   */
  destroy(): void {
    if (this._cleanupTimer) {
      clearInterval(this._cleanupTimer);
      this._cleanupTimer = null;
    }

    // Clear local state to indicate we're offline
    this._awareness.setLocalState(null);
    this._awareness.destroy();
  }

  /**
   * Handle awareness change events.
   *
   * @param changes - The awareness changes.
   * @param origin - The origin of the changes.
   */
  private _onAwarenessChange(
    changes: IAwarenessChanges,
    origin: any
  ): void {
    // Check for idle users based on lastActivity
    this._checkIdleUsers();

    // Emit the stateChanged signal
    this._stateChanged.emit(changes);
  }

  /**
   * Check for idle users and update their status.
   */
  private _checkIdleUsers(): void {
    const now = Date.now();
    const states = this.getStates();

    for (const [clientId, state] of states.entries()) {
      // Skip if this is not the local client
      if (clientId !== this._clientId) {
        continue;
      }

      // Check if the user has been inactive for longer than the idle timeout
      if (
        state.status !== UserStatus.Idle &&
        state.status !== UserStatus.Viewing &&
        now - state.lastActivity > this._idleTimeout
      ) {
        this.setStatus(UserStatus.Idle);
      }
    }
  }

  /**
   * Clean up disconnected users.
   * This is already handled by the Awareness implementation,
   * but we keep this method for potential custom cleanup logic.
   */
  private _cleanupDisconnectedUsers(): void {
    // The Awareness class already handles cleanup of disconnected users
    // after 30 seconds by default. We can add additional custom logic here if needed.
  }

  private _awareness: Awareness;
  private _clientId: number;
  private _idleTimeout: number;
  private _cleanupInterval: number;
  private _cleanupTimer: any;
  private _stateChanged = new Signal<IPresenceTracker, IAwarenessChanges>(this);
}

/**
 * Namespace for PresenceTracker.
 */
export namespace PresenceTracker {
  /**
   * Options for configuring the PresenceTracker.
   */
  export interface IOptions {
    /**
     * Timeout in milliseconds after which a user is considered idle.
     * Default: 60000 (1 minute)
     */
    idleTimeout?: number;

    /**
     * Interval in milliseconds for cleaning up disconnected users.
     * Default: 30000 (30 seconds)
     */
    cleanupInterval?: number;
  }
}
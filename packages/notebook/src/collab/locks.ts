// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { ISignal, Signal } from '@lumino/signaling';
import { INotebookModel } from '../model';
import { ICollaborationProvider } from './provider';
import { IPermissionManager } from './permissions';
import { IPresenceTracker, UserStatus } from './awareness';
import { Token } from '@lumino/coreutils';
import * as Y from 'yjs';

/**
 * The cell lock manager token.
 */
export const ICellLockManager = new Token<ICellLockManager>(
  '@jupyterlab/notebook:ICellLockManager'
);

/**
 * Interface for a lock on a cell.
 */
export interface ICellLock {
  /**
   * The ID of the cell that is locked.
   */
  cellId: string;

  /**
   * The ID of the user who holds the lock.
   */
  userId: string;

  /**
   * The display name of the user who holds the lock.
   */
  userDisplayName: string;

  /**
   * The time when the lock was acquired (milliseconds since epoch).
   */
  timestamp: number;

  /**
   * The time when the lock will automatically expire (milliseconds since epoch).
   */
  expiresAt: number;
}

/**
 * Interface for lock state change events.
 */
export interface ILockStateChange {
  /**
   * The ID of the cell whose lock state changed.
   */
  cellId: string;

  /**
   * The previous lock state, if any.
   */
  previousLock?: ICellLock;

  /**
   * The new lock state, if any.
   */
  newLock?: ICellLock;

  /**
   * Whether the lock was forcibly released by an administrator.
   */
  wasForced: boolean;
}

/**
 * Interface for the cell lock manager.
 */
export interface ICellLockManager {
  /**
   * A signal emitted when a cell's lock state changes.
   */
  readonly lockChanged: ISignal<ICellLockManager, ILockStateChange>;

  /**
   * The default lock duration in milliseconds.
   */
  readonly defaultLockDuration: number;

  /**
   * Set the default lock duration.
   * 
   * @param duration - The duration in milliseconds.
   */
  setDefaultLockDuration(duration: number): void;

  /**
   * Acquire a lock on a cell.
   * 
   * @param cellId - The ID of the cell to lock.
   * @param duration - Optional custom duration for this lock in milliseconds.
   * @returns A promise that resolves to true if the lock was acquired, false otherwise.
   */
  acquireLock(cellId: string, duration?: number): Promise<boolean>;

  /**
   * Release a lock on a cell.
   * 
   * @param cellId - The ID of the cell to unlock.
   * @returns A promise that resolves to true if the lock was released, false otherwise.
   */
  releaseLock(cellId: string): Promise<boolean>;

  /**
   * Force release a lock on a cell (admin only).
   * 
   * @param cellId - The ID of the cell to unlock.
   * @returns A promise that resolves to true if the lock was force-released, false otherwise.
   */
  forceReleaseLock(cellId: string): Promise<boolean>;

  /**
   * Check if a cell is locked.
   * 
   * @param cellId - The ID of the cell to check.
   * @returns True if the cell is locked, false otherwise.
   */
  isLocked(cellId: string): boolean;

  /**
   * Check if a cell is locked by the current user.
   * 
   * @param cellId - The ID of the cell to check.
   * @returns True if the cell is locked by the current user, false otherwise.
   */
  isLockedByCurrentUser(cellId: string): boolean;

  /**
   * Get the lock for a cell.
   * 
   * @param cellId - The ID of the cell to get the lock for.
   * @returns The lock object, or undefined if the cell is not locked.
   */
  getLock(cellId: string): ICellLock | undefined;

  /**
   * Get all active locks.
   * 
   * @returns A map of cell IDs to lock objects.
   */
  getAllLocks(): Map<string, ICellLock>;

  /**
   * Connect the lock manager to a notebook model.
   * 
   * @param model - The notebook model to connect to.
   * @param permissionManager - The permission manager to use for access control.
   * @param presenceTracker - The presence tracker to use for user awareness.
   */
  connectNotebook(
    model: INotebookModel,
    permissionManager: IPermissionManager,
    presenceTracker: IPresenceTracker
  ): void;

  /**
   * Disconnect the lock manager from the notebook model.
   */
  disconnectNotebook(): void;
}

/**
 * Implementation of the cell lock manager.
 */
export class CellLockManager implements ICellLockManager {
  /**
   * Construct a new CellLockManager.
   * 
   * @param options - The options for the lock manager.
   */
  constructor(options: CellLockManager.IOptions = {}) {
    this._defaultLockDuration = options.defaultLockDuration || 5 * 60 * 1000; // 5 minutes by default
    this._lockExpirationCheckInterval = options.lockExpirationCheckInterval || 10 * 1000; // 10 seconds by default
  }

  /**
   * A signal emitted when a cell's lock state changes.
   */
  get lockChanged(): ISignal<ICellLockManager, ILockStateChange> {
    return this._lockChanged;
  }

  /**
   * The default lock duration in milliseconds.
   */
  get defaultLockDuration(): number {
    return this._defaultLockDuration;
  }

  /**
   * Set the default lock duration.
   * 
   * @param duration - The duration in milliseconds.
   */
  setDefaultLockDuration(duration: number): void {
    if (duration <= 0) {
      console.warn('Lock duration must be positive, ignoring');
      return;
    }
    this._defaultLockDuration = duration;
  }

  /**
   * Acquire a lock on a cell.
   * 
   * @param cellId - The ID of the cell to lock.
   * @param duration - Optional custom duration for this lock in milliseconds.
   * @returns A promise that resolves to true if the lock was acquired, false otherwise.
   */
  async acquireLock(cellId: string, duration?: number): Promise<boolean> {
    if (!this._ydoc || !this._ylocks || !this._permissionManager || !this._presenceTracker) {
      console.warn('Lock manager not connected to a notebook');
      return false;
    }

    // Check if the user has permission to edit the cell
    const userId = this._permissionManager.currentUserId;
    if (!this._permissionManager.canEditCell(cellId, userId)) {
      console.warn('User does not have permission to edit this cell');
      return false;
    }

    // Check if the cell is already locked
    const existingLock = this.getLock(cellId);
    if (existingLock) {
      // If the cell is already locked by this user, extend the lock
      if (existingLock.userId === userId) {
        return this._extendLock(cellId, duration);
      }

      // If the cell is locked by someone else, check if the lock has expired
      if (existingLock.expiresAt <= Date.now()) {
        // Lock has expired, release it and acquire a new one
        await this.releaseLock(cellId);
      } else {
        // Cell is locked by someone else and the lock is still valid
        console.warn('Cell is locked by another user');
        return false;
      }
    }

    // Acquire the lock
    const lockDuration = duration || this._defaultLockDuration;
    const now = Date.now();
    const newLock: ICellLock = {
      cellId,
      userId,
      userDisplayName: this._permissionManager.currentUserDisplayName,
      timestamp: now,
      expiresAt: now + lockDuration
    };

    // Update the shared data structure
    this._ydoc.transact(() => {
      this._ylocks.set(cellId, newLock);
    }, this);

    // Update the user's awareness state to indicate they are editing this cell
    this._presenceTracker.updateLocalState('status', UserStatus.Editing);
    this._presenceTracker.setCursorPosition({ cellId, offset: 0 });

    return true;
  }

  /**
   * Release a lock on a cell.
   * 
   * @param cellId - The ID of the cell to unlock.
   * @returns A promise that resolves to true if the lock was released, false otherwise.
   */
  async releaseLock(cellId: string): Promise<boolean> {
    if (!this._ydoc || !this._ylocks || !this._permissionManager || !this._presenceTracker) {
      console.warn('Lock manager not connected to a notebook');
      return false;
    }

    // Check if the cell is locked
    const existingLock = this.getLock(cellId);
    if (!existingLock) {
      // Cell is not locked, nothing to do
      return true;
    }

    // Check if the user has permission to release the lock
    const userId = this._permissionManager.currentUserId;
    if (existingLock.userId !== userId && !this._permissionManager.isAdmin) {
      console.warn('Only the lock owner or an admin can release a lock');
      return false;
    }

    // Release the lock
    const previousLock = existingLock;
    this._ydoc.transact(() => {
      this._ylocks.delete(cellId);
    }, this);

    // Update the user's awareness state if they were editing this cell
    const localState = this._presenceTracker.getLocalState();
    if (localState?.status === UserStatus.Editing && localState?.cursor?.cellId === cellId) {
      this._presenceTracker.setStatus(UserStatus.Active);
    }

    return true;
  }

  /**
   * Force release a lock on a cell (admin only).
   * 
   * @param cellId - The ID of the cell to unlock.
   * @returns A promise that resolves to true if the lock was force-released, false otherwise.
   */
  async forceReleaseLock(cellId: string): Promise<boolean> {
    if (!this._ydoc || !this._ylocks || !this._permissionManager) {
      console.warn('Lock manager not connected to a notebook');
      return false;
    }

    // Check if the user is an admin
    if (!this._permissionManager.isAdmin) {
      console.warn('Only admins can force-release locks');
      return false;
    }

    // Check if the cell is locked
    const existingLock = this.getLock(cellId);
    if (!existingLock) {
      // Cell is not locked, nothing to do
      return true;
    }

    // Force release the lock
    const previousLock = existingLock;
    this._ydoc.transact(() => {
      this._ylocks.delete(cellId);
    }, this);

    // Emit the lock changed signal with wasForced flag
    this._lockChanged.emit({
      cellId,
      previousLock,
      newLock: undefined,
      wasForced: true
    });

    return true;
  }

  /**
   * Check if a cell is locked.
   * 
   * @param cellId - The ID of the cell to check.
   * @returns True if the cell is locked, false otherwise.
   */
  isLocked(cellId: string): boolean {
    if (!this._ylocks) {
      return false;
    }

    const lock = this.getLock(cellId);
    if (!lock) {
      return false;
    }

    // Check if the lock has expired
    if (lock.expiresAt <= Date.now()) {
      // Lock has expired, but it hasn't been cleaned up yet
      // We'll return false and let the cleanup process handle it
      return false;
    }

    return true;
  }

  /**
   * Check if a cell is locked by the current user.
   * 
   * @param cellId - The ID of the cell to check.
   * @returns True if the cell is locked by the current user, false otherwise.
   */
  isLockedByCurrentUser(cellId: string): boolean {
    if (!this._ylocks || !this._permissionManager) {
      return false;
    }

    const lock = this.getLock(cellId);
    if (!lock) {
      return false;
    }

    // Check if the lock has expired
    if (lock.expiresAt <= Date.now()) {
      return false;
    }

    return lock.userId === this._permissionManager.currentUserId;
  }

  /**
   * Get the lock for a cell.
   * 
   * @param cellId - The ID of the cell to get the lock for.
   * @returns The lock object, or undefined if the cell is not locked.
   */
  getLock(cellId: string): ICellLock | undefined {
    if (!this._ylocks) {
      return undefined;
    }

    return this._ylocks.get(cellId) as ICellLock | undefined;
  }

  /**
   * Get all active locks.
   * 
   * @returns A map of cell IDs to lock objects.
   */
  getAllLocks(): Map<string, ICellLock> {
    const locks = new Map<string, ICellLock>();
    if (!this._ylocks) {
      return locks;
    }

    const now = Date.now();
    this._ylocks.forEach((lock, cellId) => {
      const typedLock = lock as ICellLock;
      // Only include non-expired locks
      if (typedLock.expiresAt > now) {
        locks.set(cellId, typedLock);
      }
    });

    return locks;
  }

  /**
   * Connect the lock manager to a notebook model.
   * 
   * @param model - The notebook model to connect to.
   * @param permissionManager - The permission manager to use for access control.
   * @param presenceTracker - The presence tracker to use for user awareness.
   */
  connectNotebook(
    model: INotebookModel,
    permissionManager: IPermissionManager,
    presenceTracker: IPresenceTracker
  ): void {
    if (this._model === model) {
      return;
    }

    // Disconnect from any existing notebook
    this.disconnectNotebook();

    // Connect to the new notebook
    this._model = model;
    this._permissionManager = permissionManager;
    this._presenceTracker = presenceTracker;

    // Get the Yjs document from the collaboration provider
    const provider = model.collaborationProvider;
    if (!provider) {
      console.warn('Notebook model does not have a collaboration provider');
      return;
    }

    this._ydoc = provider.ydoc;
    if (!this._ydoc) {
      console.warn('Collaboration provider does not have a Yjs document');
      return;
    }

    // Initialize the shared locks map
    this._ylocks = this._ydoc.getMap('cellLocks');

    // Set up observation of the locks map
    this._ylocks.observe(this._onLocksChanged.bind(this));

    // Set up the lock expiration check interval
    this._startLockExpirationChecker();

    // Set up presence change handler to auto-release locks when users disconnect
    provider.awareness.on('change', this._onAwarenessChange.bind(this));
  }

  /**
   * Disconnect the lock manager from the notebook model.
   */
  disconnectNotebook(): void {
    if (!this._model) {
      return;
    }

    // Stop the lock expiration checker
    this._stopLockExpirationChecker();

    // Release all locks held by the current user
    this._releaseAllUserLocks();

    // Clean up observation of the locks map
    if (this._ylocks) {
      this._ylocks.unobserve(this._onLocksChanged.bind(this));
    }

    // Clean up awareness change handler
    if (this._model.collaborationProvider) {
      this._model.collaborationProvider.awareness.off('change', this._onAwarenessChange.bind(this));
    }

    // Clear references
    this._model = null;
    this._ydoc = null;
    this._ylocks = null;
    this._permissionManager = null;
    this._presenceTracker = null;
  }

  /**
   * Extend an existing lock.
   * 
   * @param cellId - The ID of the cell whose lock to extend.
   * @param duration - Optional custom duration for the extended lock in milliseconds.
   * @returns A promise that resolves to true if the lock was extended, false otherwise.
   */
  private async _extendLock(cellId: string, duration?: number): Promise<boolean> {
    if (!this._ydoc || !this._ylocks || !this._permissionManager) {
      return false;
    }

    const existingLock = this.getLock(cellId);
    if (!existingLock) {
      return false;
    }

    // Check if this is the current user's lock
    const userId = this._permissionManager.currentUserId;
    if (existingLock.userId !== userId) {
      return false;
    }

    // Extend the lock
    const lockDuration = duration || this._defaultLockDuration;
    const now = Date.now();
    const updatedLock: ICellLock = {
      ...existingLock,
      timestamp: now,
      expiresAt: now + lockDuration
    };

    // Update the shared data structure
    this._ydoc.transact(() => {
      this._ylocks.set(cellId, updatedLock);
    }, this);

    return true;
  }

  /**
   * Handle changes to the locks map.
   * 
   * @param event - The Y.js map event.
   */
  private _onLocksChanged(event: Y.YMapEvent<any>): void {
    // Process each changed key
    event.keysChanged.forEach(cellId => {
      const previousLock = event.changes.keys.get(cellId)?.oldValue as ICellLock | undefined;
      const newLock = this._ylocks?.get(cellId) as ICellLock | undefined;

      // Emit the lock changed signal
      this._lockChanged.emit({
        cellId,
        previousLock,
        newLock,
        wasForced: false
      });
    });
  }

  /**
   * Handle awareness changes to auto-release locks when users disconnect.
   * 
   * @param changes - The awareness changes.
   */
  private _onAwarenessChange(changes: { added: number[], updated: number[], removed: number[] }): void {
    if (!this._ydoc || !this._ylocks || !this._model || !this._model.collaborationProvider) {
      return;
    }

    // When users are removed (disconnected), release their locks
    if (changes.removed.length > 0) {
      const awareness = this._model.collaborationProvider.awareness;
      const now = Date.now();

      // Find all locks held by disconnected users
      const locksToRelease: string[] = [];
      this._ylocks.forEach((lock, cellId) => {
        const typedLock = lock as ICellLock;
        // Check if the lock holder is in the removed list
        const clientId = this._findClientIdByUserId(awareness, typedLock.userId);
        if (clientId && changes.removed.includes(clientId)) {
          locksToRelease.push(cellId);
        }
      });

      // Release the locks
      if (locksToRelease.length > 0) {
        this._ydoc.transact(() => {
          for (const cellId of locksToRelease) {
            const previousLock = this._ylocks?.get(cellId) as ICellLock | undefined;
            this._ylocks?.delete(cellId);

            // Emit the lock changed signal
            this._lockChanged.emit({
              cellId,
              previousLock,
              newLock: undefined,
              wasForced: false
            });
          }
        }, this);
      }
    }
  }

  /**
   * Find a client ID by user ID in the awareness states.
   * 
   * @param awareness - The awareness instance.
   * @param userId - The user ID to find.
   * @returns The client ID, or undefined if not found.
   */
  private _findClientIdByUserId(awareness: any, userId: string): number | undefined {
    const states = awareness.getStates() as Map<number, any>;
    for (const [clientId, state] of states.entries()) {
      if (state.userId === userId) {
        return clientId;
      }
    }
    return undefined;
  }

  /**
   * Start the lock expiration checker interval.
   */
  private _startLockExpirationChecker(): void {
    this._stopLockExpirationChecker();
    this._lockExpirationCheckerId = setInterval(
      this._checkExpiredLocks.bind(this),
      this._lockExpirationCheckInterval
    );
  }

  /**
   * Stop the lock expiration checker interval.
   */
  private _stopLockExpirationChecker(): void {
    if (this._lockExpirationCheckerId !== null) {
      clearInterval(this._lockExpirationCheckerId);
      this._lockExpirationCheckerId = null;
    }
  }

  /**
   * Check for and clean up expired locks.
   */
  private _checkExpiredLocks(): void {
    if (!this._ydoc || !this._ylocks) {
      return;
    }

    const now = Date.now();
    const expiredLocks: string[] = [];

    // Find all expired locks
    this._ylocks.forEach((lock, cellId) => {
      const typedLock = lock as ICellLock;
      if (typedLock.expiresAt <= now) {
        expiredLocks.push(cellId);
      }
    });

    // Release the expired locks
    if (expiredLocks.length > 0) {
      this._ydoc.transact(() => {
        for (const cellId of expiredLocks) {
          const previousLock = this._ylocks?.get(cellId) as ICellLock | undefined;
          this._ylocks?.delete(cellId);

          // Emit the lock changed signal
          this._lockChanged.emit({
            cellId,
            previousLock,
            newLock: undefined,
            wasForced: false
          });
        }
      }, this);
    }
  }

  /**
   * Release all locks held by the current user.
   */
  private _releaseAllUserLocks(): void {
    if (!this._ydoc || !this._ylocks || !this._permissionManager) {
      return;
    }

    const userId = this._permissionManager.currentUserId;
    const userLocks: string[] = [];

    // Find all locks held by the current user
    this._ylocks.forEach((lock, cellId) => {
      const typedLock = lock as ICellLock;
      if (typedLock.userId === userId) {
        userLocks.push(cellId);
      }
    });

    // Release the user's locks
    if (userLocks.length > 0) {
      this._ydoc.transact(() => {
        for (const cellId of userLocks) {
          const previousLock = this._ylocks?.get(cellId) as ICellLock | undefined;
          this._ylocks?.delete(cellId);

          // Emit the lock changed signal
          this._lockChanged.emit({
            cellId,
            previousLock,
            newLock: undefined,
            wasForced: false
          });
        }
      }, this);
    }
  }

  private _model: INotebookModel | null = null;
  private _ydoc: Y.Doc | null = null;
  private _ylocks: Y.Map<ICellLock> | null = null;
  private _permissionManager: IPermissionManager | null = null;
  private _presenceTracker: IPresenceTracker | null = null;

  private _defaultLockDuration: number;
  private _lockExpirationCheckInterval: number;
  private _lockExpirationCheckerId: any = null;

  private _lockChanged = new Signal<ICellLockManager, ILockStateChange>(this);
}

/**
 * Namespace for CellLockManager.
 */
export namespace CellLockManager {
  /**
   * Options for the CellLockManager.
   */
  export interface IOptions {
    /**
     * The default duration for cell locks in milliseconds.
     * Default: 5 minutes (300000 ms)
     */
    defaultLockDuration?: number;

    /**
     * The interval for checking expired locks in milliseconds.
     * Default: 10 seconds (10000 ms)
     */
    lockExpirationCheckInterval?: number;
  }
}
/**
 * Cell locking mechanism for collaborative notebooks
 *
 * This module implements a cell locking system that prevents editing conflicts
 * by ensuring that only one user can edit a cell at a time. It manages the
 * acquisition and release of locks, broadcasts lock state to all connected clients,
 * and provides visual indicators for locked cells.
 */

import { EventEmitter } from '@lumino/signaling';
import * as Y from 'yjs';

import { IPermissionManager, UserPermission } from './permissions';

/**
 * Interface for cell lock data
 */
export interface ICellLock {
  /** ID of the locked cell */
  cellId: string;
  /** ID of the user who owns the lock */
  userId: string;
  /** User display name for UI */
  userName: string;
  /** Timestamp when the lock was acquired */
  timestamp: number;
  /** Optional timeout in milliseconds (0 means no timeout) */
  timeout: number;
}

/**
 * Lock event types
 */
export enum LockEventType {
  /** Lock was acquired */
  Acquired = 'acquired',
  /** Lock was released */
  Released = 'released',
  /** Lock timed out */
  TimedOut = 'timedout',
  /** Lock was forcibly released by admin */
  ForceReleased = 'forcereleased'
}

/**
 * Interface for lock events
 */
export interface ICellLockEvent {
  /** Type of lock event */
  type: LockEventType;
  /** The lock data */
  lock: ICellLock;
}

/**
 * Options for the CellLockManager
 */
export interface ICellLockManagerOptions {
  /** The Yjs document */
  doc: Y.Doc;
  /** The permission manager for access control */
  permissionManager: IPermissionManager;
  /** Default lock timeout in milliseconds (default: 5 minutes) */
  defaultTimeout?: number;
  /** Cleanup interval for checking expired locks in milliseconds (default: 30 seconds) */
  cleanupInterval?: number;
}

/**
 * Manager for cell locks in collaborative notebooks
 */
export class CellLockManager {
  /**
   * Constructor
   * 
   * @param options - The options for the lock manager
   */
  constructor(options: ICellLockManagerOptions) {
    this._doc = options.doc;
    this._permissionManager = options.permissionManager;
    this._defaultTimeout = options.defaultTimeout || 5 * 60 * 1000; // 5 minutes default
    this._cleanupInterval = options.cleanupInterval || 30 * 1000; // 30 seconds default
    
    // Initialize the shared locks map
    this._locks = this._doc.getMap<ICellLock>('cell-locks');
    
    // Set up lock observation
    this._locks.observe(this._onLocksChanged.bind(this));
    
    // Set up cleanup interval
    this._cleanupTimer = setInterval(() => {
      this._cleanupExpiredLocks();
    }, this._cleanupInterval);
  }

  /**
   * Acquire a lock on a cell
   * 
   * @param cellId - The ID of the cell to lock
   * @param userId - The ID of the user acquiring the lock
   * @param userName - The display name of the user
   * @param timeout - Optional custom timeout in milliseconds
   * @returns True if the lock was acquired, false otherwise
   */
  acquireLock(cellId: string, userId: string, userName: string, timeout?: number): boolean {
    // Check if the cell is already locked
    if (this.isLocked(cellId)) {
      const currentLock = this._locks.get(cellId);
      
      // If the same user already has the lock, refresh it
      if (currentLock && currentLock.userId === userId) {
        return this._refreshLock(cellId, userId, userName, timeout);
      }
      
      // Cell is locked by another user
      return false;
    }
    
    // Check if the user has permission to edit this cell
    if (!this._hasEditPermission(userId, cellId)) {
      return false;
    }
    
    // Create the lock
    const lock: ICellLock = {
      cellId,
      userId,
      userName,
      timestamp: Date.now(),
      timeout: timeout !== undefined ? timeout : this._defaultTimeout
    };
    
    // Add the lock to the shared map
    this._doc.transact(() => {
      this._locks.set(cellId, lock);
    });
    
    return true;
  }

  /**
   * Release a lock on a cell
   * 
   * @param cellId - The ID of the cell
   * @param userId - The ID of the user releasing the lock
   * @returns True if the lock was released, false otherwise
   */
  releaseLock(cellId: string, userId: string): boolean {
    const lock = this._locks.get(cellId);
    
    // Check if the cell is locked and the user owns the lock
    if (!lock || lock.userId !== userId) {
      // Check if the user has admin permission to force release
      if (this._hasAdminPermission(userId)) {
        return this.forceReleaseLock(cellId, userId);
      }
      return false;
    }
    
    // Remove the lock
    this._doc.transact(() => {
      this._locks.delete(cellId);
    });
    
    return true;
  }

  /**
   * Force release a lock (admin only)
   * 
   * @param cellId - The ID of the cell
   * @param adminUserId - The ID of the admin user
   * @returns True if the lock was force released, false otherwise
   */
  forceReleaseLock(cellId: string, adminUserId: string): boolean {
    // Check if the user has admin permission
    if (!this._hasAdminPermission(adminUserId)) {
      return false;
    }
    
    const lock = this._locks.get(cellId);
    if (!lock) {
      return false;
    }
    
    // Store the lock for the event
    const lockCopy = { ...lock };
    
    // Remove the lock
    this._doc.transact(() => {
      this._locks.delete(cellId);
    });
    
    // Emit force release event
    this._emitLockEvent({
      type: LockEventType.ForceReleased,
      lock: lockCopy
    });
    
    return true;
  }

  /**
   * Check if a cell is locked
   * 
   * @param cellId - The ID of the cell
   * @returns True if the cell is locked, false otherwise
   */
  isLocked(cellId: string): boolean {
    return this._locks.has(cellId);
  }

  /**
   * Check if a cell is locked by a specific user
   * 
   * @param cellId - The ID of the cell
   * @param userId - The ID of the user
   * @returns True if the cell is locked by the user, false otherwise
   */
  isLockedByUser(cellId: string, userId: string): boolean {
    const lock = this._locks.get(cellId);
    return !!lock && lock.userId === userId;
  }

  /**
   * Get the lock for a cell
   * 
   * @param cellId - The ID of the cell
   * @returns The lock data or null if the cell is not locked
   */
  getLock(cellId: string): ICellLock | null {
    const lock = this._locks.get(cellId);
    return lock || null;
  }

  /**
   * Get all locked cells
   * 
   * @returns An array of all locks
   */
  getAllLocks(): ICellLock[] {
    const locks: ICellLock[] = [];
    this._locks.forEach((lock) => {
      locks.push(lock);
    });
    return locks;
  }

  /**
   * Get all cells locked by a specific user
   * 
   * @param userId - The ID of the user
   * @returns An array of locks owned by the user
   */
  getUserLocks(userId: string): ICellLock[] {
    const locks: ICellLock[] = [];
    this._locks.forEach((lock) => {
      if (lock.userId === userId) {
        locks.push(lock);
      }
    });
    return locks;
  }

  /**
   * Release all locks owned by a user (useful when a user disconnects)
   * 
   * @param userId - The ID of the user
   * @returns The number of locks released
   */
  releaseUserLocks(userId: string): number {
    const userLocks = this.getUserLocks(userId);
    let count = 0;
    
    this._doc.transact(() => {
      userLocks.forEach(lock => {
        this._locks.delete(lock.cellId);
        count++;
      });
    });
    
    return count;
  }

  /**
   * Connect to lock events
   * 
   * @param callback - The callback function to call when a lock event occurs
   * @returns A function to disconnect from lock events
   */
  onLockEvent(callback: (event: ICellLockEvent) => void): () => void {
    return this._lockEvents.connect(callback);
  }

  /**
   * Dispose of the lock manager
   */
  dispose(): void {
    if (this._cleanupTimer) {
      clearInterval(this._cleanupTimer);
      this._cleanupTimer = null;
    }
    
    this._lockEvents.disconnect();
  }

  /**
   * Refresh a lock with a new timestamp
   * 
   * @private
   * @param cellId - The ID of the cell
   * @param userId - The ID of the user
   * @param userName - The display name of the user
   * @param timeout - Optional custom timeout in milliseconds
   * @returns True if the lock was refreshed, false otherwise
   */
  private _refreshLock(cellId: string, userId: string, userName: string, timeout?: number): boolean {
    const currentLock = this._locks.get(cellId);
    if (!currentLock || currentLock.userId !== userId) {
      return false;
    }
    
    // Update the lock with a new timestamp
    const updatedLock: ICellLock = {
      ...currentLock,
      timestamp: Date.now(),
      userName, // Update the name in case it changed
      timeout: timeout !== undefined ? timeout : currentLock.timeout
    };
    
    this._doc.transact(() => {
      this._locks.set(cellId, updatedLock);
    });
    
    return true;
  }

  /**
   * Clean up expired locks
   * 
   * @private
   */
  private _cleanupExpiredLocks(): void {
    const now = Date.now();
    const expiredLocks: ICellLock[] = [];
    
    // Find all expired locks
    this._locks.forEach((lock) => {
      // Skip locks with no timeout
      if (lock.timeout === 0) {
        return;
      }
      
      if (now - lock.timestamp > lock.timeout) {
        expiredLocks.push(lock);
      }
    });
    
    // Remove expired locks
    if (expiredLocks.length > 0) {
      this._doc.transact(() => {
        expiredLocks.forEach(lock => {
          this._locks.delete(lock.cellId);
          
          // Emit timeout event
          this._emitLockEvent({
            type: LockEventType.TimedOut,
            lock
          });
        });
      });
    }
  }

  /**
   * Handle changes to the locks map
   * 
   * @private
   * @param event - The Y.MapEvent
   */
  private _onLocksChanged(event: Y.YMapEvent<ICellLock>): void {
    // Process added or updated locks
    event.keysChanged.forEach(cellId => {
      if (this._locks.has(cellId)) {
        // Lock was added or updated
        const lock = this._locks.get(cellId)!;
        this._emitLockEvent({
          type: LockEventType.Acquired,
          lock
        });
      } else {
        // Lock was removed
        // We need to get the old value from the event
        const oldLock = event.changes.keys.get(cellId)?.oldValue as ICellLock;
        if (oldLock) {
          this._emitLockEvent({
            type: LockEventType.Released,
            lock: oldLock
          });
        }
      }
    });
  }

  /**
   * Emit a lock event
   * 
   * @private
   * @param event - The lock event
   */
  private _emitLockEvent(event: ICellLockEvent): void {
    this._lockEvents.emit(event);
  }

  /**
   * Check if a user has edit permission for a cell
   * 
   * @private
   * @param userId - The ID of the user
   * @param cellId - The ID of the cell
   * @returns True if the user has edit permission, false otherwise
   */
  private _hasEditPermission(userId: string, cellId: string): boolean {
    return this._permissionManager.hasPermission(userId, cellId, UserPermission.Edit);
  }

  /**
   * Check if a user has admin permission
   * 
   * @private
   * @param userId - The ID of the user
   * @returns True if the user has admin permission, false otherwise
   */
  private _hasAdminPermission(userId: string): boolean {
    return this._permissionManager.hasPermission(userId, null, UserPermission.Admin);
  }

  /** The Yjs document */
  private _doc: Y.Doc;
  
  /** The permission manager */
  private _permissionManager: IPermissionManager;
  
  /** The shared locks map */
  private _locks: Y.Map<ICellLock>;
  
  /** Default lock timeout in milliseconds */
  private _defaultTimeout: number;
  
  /** Cleanup interval in milliseconds */
  private _cleanupInterval: number;
  
  /** Timer for cleanup */
  private _cleanupTimer: any;
  
  /** Event emitter for lock events */
  private _lockEvents = new EventEmitter<ICellLockEvent>();
}
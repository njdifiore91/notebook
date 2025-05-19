import React, { useState, useEffect, useCallback } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import '../../style/cellLockIndicator.css';

/**
 * Interface for the lock service that manages cell locks
 */
export interface ILockService {
  /**
   * Acquire a lock on a cell
   * @param cellId - The ID of the cell to lock
   * @returns A promise that resolves to true if the lock was acquired, false otherwise
   */
  acquireLock: (cellId: string) => Promise<boolean>;

  /**
   * Release a lock on a cell
   * @param cellId - The ID of the cell to unlock
   * @returns A promise that resolves to true if the lock was released, false otherwise
   */
  releaseLock: (cellId: string) => Promise<boolean>;

  /**
   * Check if a cell is locked
   * @param cellId - The ID of the cell to check
   * @returns A promise that resolves to the user ID of the lock owner, or null if the cell is not locked
   */
  isLocked: (cellId: string) => Promise<string | null>;

  /**
   * Subscribe to lock state changes
   * @param callback - The callback to call when the lock state changes
   * @returns A function to unsubscribe from lock state changes
   */
  subscribe: (callback: (cellId: string, userId: string | null) => void) => () => void;
}

/**
 * Interface for the user information
 */
export interface IUserInfo {
  /**
   * The user's ID
   */
  id: string;

  /**
   * The user's display name
   */
  name: string;

  /**
   * The user's avatar URL
   */
  avatarUrl?: string;

  /**
   * The user's color (for visual identification)
   */
  color: string;
}

/**
 * Interface for the user service that provides user information
 */
export interface IUserService {
  /**
   * Get information about a user
   * @param userId - The ID of the user
   * @returns A promise that resolves to the user information, or null if the user is not found
   */
  getUserInfo: (userId: string) => Promise<IUserInfo | null>;

  /**
   * Get the current user's ID
   * @returns The current user's ID
   */
  getCurrentUserId: () => string;
}

/**
 * Props for the CellLockIndicator component
 */
export interface ICellLockIndicatorProps {
  /**
   * The ID of the cell
   */
  cellId: string;

  /**
   * The lock service
   */
  lockService: ILockService;

  /**
   * The user service
   */
  userService: IUserService;

  /**
   * The translator
   */
  translator?: ITranslator;
}

/**
 * A component that displays the lock status of a cell and provides controls for acquiring and releasing locks
 */
export const CellLockIndicator: React.FC<ICellLockIndicatorProps> = ({
  cellId,
  lockService,
  userService,
  translator = nullTranslator
}) => {
  const trans = translator.load('notebook');
  const [lockOwner, setLockOwner] = useState<string | null>(null);
  const [lockOwnerInfo, setLockOwnerInfo] = useState<IUserInfo | null>(null);
  const [isAcquiringLock, setIsAcquiringLock] = useState(false);
  const [isReleasingLock, setIsReleasingLock] = useState(false);
  const currentUserId = userService.getCurrentUserId();
  const isLockedByCurrentUser = lockOwner === currentUserId;

  // Check if the cell is locked when the component mounts
  useEffect(() => {
    const checkLockStatus = async () => {
      const owner = await lockService.isLocked(cellId);
      setLockOwner(owner);

      if (owner) {
        const info = await userService.getUserInfo(owner);
        setLockOwnerInfo(info);
      } else {
        setLockOwnerInfo(null);
      }
    };

    checkLockStatus();

    // Subscribe to lock state changes
    const unsubscribe = lockService.subscribe(async (updatedCellId, userId) => {
      if (updatedCellId === cellId) {
        setLockOwner(userId);

        if (userId) {
          const info = await userService.getUserInfo(userId);
          setLockOwnerInfo(info);
        } else {
          setLockOwnerInfo(null);
        }
      }
    });

    return unsubscribe;
  }, [cellId, lockService, userService]);

  // Handle acquiring a lock
  const handleAcquireLock = useCallback(async () => {
    if (lockOwner || isAcquiringLock) return;

    setIsAcquiringLock(true);
    try {
      const success = await lockService.acquireLock(cellId);
      if (success) {
        setLockOwner(currentUserId);
        const info = await userService.getUserInfo(currentUserId);
        setLockOwnerInfo(info);
      }
    } catch (error) {
      console.error('Failed to acquire lock:', error);
    } finally {
      setIsAcquiringLock(false);
    }
  }, [cellId, lockOwner, lockService, currentUserId, userService, isAcquiringLock]);

  // Handle releasing a lock
  const handleReleaseLock = useCallback(async () => {
    if (!isLockedByCurrentUser || isReleasingLock) return;

    setIsReleasingLock(true);
    try {
      const success = await lockService.releaseLock(cellId);
      if (success) {
        setLockOwner(null);
        setLockOwnerInfo(null);
      }
    } catch (error) {
      console.error('Failed to release lock:', error);
    } finally {
      setIsReleasingLock(false);
    }
  }, [cellId, isLockedByCurrentUser, lockService, isReleasingLock]);

  // Handle keyboard shortcut (Alt+L) for toggling lock
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.altKey && event.key === 'l') {
        event.preventDefault();
        if (isLockedByCurrentUser) {
          handleReleaseLock();
        } else if (!lockOwner) {
          handleAcquireLock();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleAcquireLock, handleReleaseLock, isLockedByCurrentUser, lockOwner]);

  // Determine the appropriate aria-label based on lock state
  const getAriaLabel = () => {
    if (!lockOwner) {
      return trans.__('Cell is unlocked. Press to lock.');
    } else if (isLockedByCurrentUser) {
      return trans.__('Cell is locked by you. Press to unlock.');
    } else if (lockOwnerInfo) {
      return trans.__('Cell is locked by %1', lockOwnerInfo.name);
    } else {
      return trans.__('Cell is locked by another user');
    }
  };

  // Determine the appropriate title based on lock state
  const getTitle = () => {
    if (!lockOwner) {
      return trans.__('Lock cell (Alt+L)');
    } else if (isLockedByCurrentUser) {
      return trans.__('Unlock cell (Alt+L)');
    } else if (lockOwnerInfo) {
      return trans.__('Locked by %1', lockOwnerInfo.name);
    } else {
      return trans.__('Locked by another user');
    }
  };

  return (
    <div className="jp-CellLockIndicator" role="region" aria-label={trans.__('Cell lock controls')}>
      {lockOwner ? (
        <div 
          className={`jp-CellLockIndicator-locked ${isLockedByCurrentUser ? 'jp-CellLockIndicator-locked-by-me' : 'jp-CellLockIndicator-locked-by-other'}`}
          style={lockOwnerInfo ? { borderColor: lockOwnerInfo.color } : undefined}
        >
          {lockOwnerInfo && lockOwnerInfo.avatarUrl ? (
            <img 
              src={lockOwnerInfo.avatarUrl} 
              alt={trans.__('Avatar of %1', lockOwnerInfo.name)}
              className="jp-CellLockIndicator-avatar"
            />
          ) : (
            <div 
              className="jp-CellLockIndicator-avatar-placeholder"
              style={lockOwnerInfo ? { backgroundColor: lockOwnerInfo.color } : undefined}
            >
              {lockOwnerInfo ? lockOwnerInfo.name.charAt(0).toUpperCase() : '?'}
            </div>
          )}
          <span className="jp-CellLockIndicator-text">
            {isLockedByCurrentUser ? (
              trans.__('Locked by you')
            ) : (
              lockOwnerInfo ? trans.__('Locked by %1', lockOwnerInfo.name) : trans.__('Locked')
            )}
          </span>
          {isLockedByCurrentUser && (
            <button
              className="jp-CellLockIndicator-button jp-CellLockIndicator-unlock"
              onClick={handleReleaseLock}
              disabled={isReleasingLock}
              aria-label={trans.__('Unlock cell')}
              title={trans.__('Unlock cell (Alt+L)')}
            >
              <span className="jp-CellLockIndicator-icon jp-CellLockIndicator-unlock-icon" aria-hidden="true">
                🔓
              </span>
              <span className="jp-CellLockIndicator-sr-only">{trans.__('Unlock')}</span>
            </button>
          )}
        </div>
      ) : (
        <button
          className="jp-CellLockIndicator-button jp-CellLockIndicator-lock"
          onClick={handleAcquireLock}
          disabled={isAcquiringLock}
          aria-label={trans.__('Lock cell')}
          title={trans.__('Lock cell (Alt+L)')}
        >
          <span className="jp-CellLockIndicator-icon jp-CellLockIndicator-lock-icon" aria-hidden="true">
            🔒
          </span>
          <span className="jp-CellLockIndicator-text">{trans.__('Lock')}</span>
        </button>
      )}
    </div>
  );
};

/**
 * A namespace for CellLockIndicator statics.
 */
export namespace CellLockIndicator {
  /**
   * Create a new CellLockIndicator widget.
   */
  export const createWidget = ({
    cellId,
    lockService,
    userService,
    translator = nullTranslator
  }: {
    cellId: string;
    lockService: ILockService;
    userService: IUserService;
    translator?: ITranslator;
  }): ReactWidget => {
    return ReactWidget.create(
      <CellLockIndicator
        cellId={cellId}
        lockService={lockService}
        userService={userService}
        translator={translator}
      />
    );
  };
}
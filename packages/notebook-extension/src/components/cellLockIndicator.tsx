import React, { useEffect, useState, useCallback } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { Cell } from '@jupyterlab/cells';
import { ITranslator } from '@jupyterlab/translation';

/**
 * Interface for the lock service that manages cell locks
 */
export interface ILockService {
  /**
   * Request a lock for a specific cell
   * @param cellId The ID of the cell to lock
   * @returns Promise that resolves to true if lock was acquired, false otherwise
   */
  requestLock: (cellId: string) => Promise<boolean>;

  /**
   * Release a lock for a specific cell
   * @param cellId The ID of the cell to release
   * @returns Promise that resolves when the lock is released
   */
  releaseLock: (cellId: string) => Promise<void>;

  /**
   * Check if a cell is currently locked
   * @param cellId The ID of the cell to check
   * @returns True if the cell is locked, false otherwise
   */
  isLocked: (cellId: string) => boolean;

  /**
   * Check if the current user holds the lock for a cell
   * @param cellId The ID of the cell to check
   * @returns True if the current user holds the lock, false otherwise
   */
  hasLock: (cellId: string) => boolean;

  /**
   * Get information about the user who holds the lock for a cell
   * @param cellId The ID of the cell to check
   * @returns User information or null if the cell is not locked
   */
  getLockHolder: (cellId: string) => { id: string; name: string; color: string } | null;

  /**
   * Subscribe to lock state changes
   * @param callback Function to call when lock state changes
   * @returns Function to unsubscribe
   */
  subscribe: (callback: () => void) => () => void;
}

/**
 * Props for the CellLockIndicator component
 */
interface ICellLockIndicatorProps {
  /**
   * The cell this lock indicator is associated with
   */
  cell: Cell;

  /**
   * The lock service to use for managing locks
   */
  lockService: ILockService;

  /**
   * The translation service
   */
  translator: ITranslator;
}

/**
 * A React component to display the lock status of a cell and provide controls
 * for acquiring and releasing locks.
 */
export const CellLockIndicator: React.FC<ICellLockIndicatorProps> = ({
  cell,
  lockService,
  translator
}) => {
  const trans = translator.load('notebook');
  const cellId = cell.model.id;
  
  // State to track lock status
  const [isLocked, setIsLocked] = useState(lockService.isLocked(cellId));
  const [hasLock, setHasLock] = useState(lockService.hasLock(cellId));
  const [lockHolder, setLockHolder] = useState(lockService.getLockHolder(cellId));
  const [isRequesting, setIsRequesting] = useState(false);
  const [showAnimation, setShowAnimation] = useState(false);

  // Update lock state when it changes
  const updateLockState = useCallback(() => {
    setIsLocked(lockService.isLocked(cellId));
    setHasLock(lockService.hasLock(cellId));
    setLockHolder(lockService.getLockHolder(cellId));
  }, [lockService, cellId]);

  // Request a lock for this cell
  const requestLock = async () => {
    if (isLocked && !hasLock) {
      return; // Already locked by someone else
    }
    
    setIsRequesting(true);
    try {
      const acquired = await lockService.requestLock(cellId);
      if (acquired) {
        setShowAnimation(true);
        setTimeout(() => setShowAnimation(false), 1000);
      }
    } finally {
      setIsRequesting(false);
    }
  };

  // Release a lock for this cell
  const releaseLock = async () => {
    if (!hasLock) {
      return; // Don't have the lock
    }
    
    try {
      await lockService.releaseLock(cellId);
    } catch (error) {
      console.error('Error releasing lock:', error);
    }
  };

  // Subscribe to lock state changes
  useEffect(() => {
    const unsubscribe = lockService.subscribe(updateLockState);
    updateLockState(); // Initial state update
    
    // Set up keyboard shortcut (Alt+L) for lock toggle
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.altKey && event.key === 'l' && cell.node.contains(document.activeElement)) {
        event.preventDefault();
        if (hasLock) {
          releaseLock();
        } else if (!isLocked) {
          requestLock();
        }
      }
    };
    
    document.addEventListener('keydown', handleKeyDown);
    
    return () => {
      unsubscribe();
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [lockService, cellId, hasLock, isLocked, cell.node]);

  // Determine the appropriate button text and aria labels
  let buttonText = '';
  let ariaLabel = '';
  let buttonTitle = '';
  
  if (isRequesting) {
    buttonText = trans.__('Requesting...');
    ariaLabel = trans.__('Requesting lock for this cell');
    buttonTitle = trans.__('Requesting lock for this cell');
  } else if (hasLock) {
    buttonText = trans.__('Unlock');
    ariaLabel = trans.__('Release lock for this cell');
    buttonTitle = trans.__('You have locked this cell. Click to release the lock (Alt+L)');
  } else if (isLocked && lockHolder) {
    buttonText = trans.__('Locked');
    ariaLabel = trans.__(`This cell is locked by ${lockHolder.name}`);
    buttonTitle = trans.__(`This cell is locked by ${lockHolder.name} and cannot be edited`);
  } else {
    buttonText = trans.__('Lock');
    ariaLabel = trans.__('Acquire lock for this cell');
    buttonTitle = trans.__('Click to lock this cell for editing (Alt+L)');
  }

  // Determine the appropriate CSS classes
  const lockClasses = [
    'jp-CellLockIndicator',
    isLocked ? 'jp-mod-locked' : '',
    hasLock ? 'jp-mod-hasLock' : '',
    showAnimation ? 'jp-mod-animating' : '',
    isRequesting ? 'jp-mod-requesting' : ''
  ].filter(Boolean).join(' ');

  // Determine the lock indicator style (color from lock holder)
  const lockStyle = lockHolder && isLocked && !hasLock ? 
    { borderColor: lockHolder.color } : {};

  return (
    <div className={lockClasses} style={lockStyle}>
      <button
        className="jp-CellLockIndicator-button"
        onClick={hasLock ? releaseLock : requestLock}
        disabled={isRequesting || (isLocked && !hasLock)}
        aria-label={ariaLabel}
        title={buttonTitle}
        role="button"
        tabIndex={0}
      >
        {buttonText}
        {lockHolder && isLocked && !hasLock && (
          <span 
            className="jp-CellLockIndicator-lockHolder"
            style={{ backgroundColor: lockHolder.color }}
            aria-hidden="true"
          >
            {lockHolder.name.charAt(0).toUpperCase()}
          </span>
        )}
      </button>
      {/* Screen reader only text for additional context */}
      <span className="jp-CellLockIndicator-srOnly" aria-live="polite">
        {isLocked && lockHolder && !hasLock ? 
          trans.__(`Cell locked by ${lockHolder.name}`) : 
          hasLock ? trans.__('You have locked this cell') : 
          trans.__('Cell is unlocked')}
      </span>
    </div>
  );
};

/**
 * A namespace for CellLockIndicatorComponent static methods.
 */
export namespace CellLockIndicatorComponent {
  /**
   * Create a new CellLockIndicatorComponent
   *
   * @param cell The cell
   * @param lockService The lock service
   * @param translator The translator
   */
  export const create = ({
    cell,
    lockService,
    translator,
  }: {
    cell: Cell;
    lockService: ILockService;
    translator: ITranslator;
  }): ReactWidget => {
    return ReactWidget.create(
      <CellLockIndicator 
        cell={cell} 
        lockService={lockService} 
        translator={translator} 
      />
    );
  };
}
// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useEffect, useRef, useState } from 'react';
import { IPresenceTracker, IAwarenessChanges, IUserAwarenessState, UserStatus, ICursorPosition, ISelectionRange } from '@jupyterlab/notebook/lib/collab/awareness';
import { NotebookPanel } from '@jupyterlab/notebook';
import { ReactWidget } from '@jupyterlab/apputils';

/**
 * Props for the UserPresence component.
 */
export interface IUserPresenceProps {
  /**
   * The presence tracker instance.
   */
  presenceTracker: IPresenceTracker;

  /**
   * The notebook panel containing the notebook.
   */
  notebookPanel: NotebookPanel;
}

/**
 * A component that visualizes other users' cursor positions and selections within the notebook.
 */
export const UserPresence: React.FC<IUserPresenceProps> = ({
  presenceTracker,
  notebookPanel
}) => {
  // Container ref for positioning cursors relative to the notebook
  const containerRef = useRef<HTMLDivElement>(null);
  
  // State to track other users' awareness states
  const [otherUsers, setOtherUsers] = useState<Map<number, IUserAwarenessState>>(new Map());

  // Handle awareness changes
  useEffect(() => {
    const onAwarenessChange = (changes: IAwarenessChanges) => {
      // Get all current states
      const states = presenceTracker.getStates();
      
      // Filter out the local user
      const filteredStates = new Map<number, IUserAwarenessState>();
      states.forEach((state, clientId) => {
        if (clientId !== presenceTracker.clientId) {
          filteredStates.set(clientId, state);
        }
      });
      
      setOtherUsers(filteredStates);
    };

    // Subscribe to awareness changes
    presenceTracker.stateChanged.connect(onAwarenessChange);
    
    // Initial setup
    onAwarenessChange({ added: [], updated: [], removed: [] });

    return () => {
      // Clean up subscription
      presenceTracker.stateChanged.disconnect(onAwarenessChange);
    };
  }, [presenceTracker]);
  
  // Update positions when users move their cursors
  useEffect(() => {
    // Set up an interval to refresh positions (helps with smooth animations)
    const intervalId = setInterval(() => {
      if (otherUsers.size > 0) {
        // Force re-render to update positions
        setOtherUsers(new Map(otherUsers));
      }
    }, 100); // Update every 100ms for smooth animations
    
    return () => clearInterval(intervalId);
  }, [otherUsers]);

  /**
   * Calculate the position of a cursor within a cell
   * 
   * @param cursor - The cursor position information
   * @param cellWidget - The cell widget containing the cursor
   * @param containerRect - The bounding rectangle of the container
   * @returns The calculated position or null if it cannot be determined
   */
  const calculateCursorPosition = (
    cursor: ICursorPosition,
    cellWidget: any,
    containerRect: DOMRect
  ): { top: number; left: number } | null => {
    // Get the cell's editor node
    const editorNode = cellWidget.node.querySelector('.CodeMirror') || 
                       cellWidget.node.querySelector('.jp-Editor');
    
    if (!editorNode) {
      return null;
    }

    const editorRect = editorNode.getBoundingClientRect();
    
    // In a real implementation, we would use the CodeMirror API to get the exact
    // position based on line and character offset. This is a simplified calculation.
    const lineHeight = 20; // Approximate line height
    const charWidth = 8;   // Approximate character width
    
    // Calculate line and character from offset (simplified)
    // In a real implementation, this would come from the editor's API
    const line = Math.floor(cursor.offset / 80); // Assume 80 chars per line
    const ch = cursor.offset % 80;
    
    return {
      top: editorRect.top - containerRect.top + (line * lineHeight),
      left: editorRect.left - containerRect.left + (ch * charWidth)
    };
  };
  
  /**
   * Calculate the position and dimensions of a selection within a cell
   * 
   * @param selection - The selection range information
   * @param cellWidgets - All cell widgets in the notebook
   * @param containerRect - The bounding rectangle of the container
   * @returns The calculated selection rectangles or empty array if they cannot be determined
   */
  const calculateSelectionRects = (
    selection: ISelectionRange,
    cellWidgets: any[],
    containerRect: DOMRect
  ): Array<{ top: number; left: number; width: number; height: number }> => {
    // This is a simplified implementation
    // In a real implementation, we would calculate multiple rectangles for multi-line selections
    
    // Find start and end cells
    const startCellWidget = cellWidgets.find(widget => widget.model.id === selection.startCellId);
    const endCellWidget = cellWidgets.find(widget => widget.model.id === selection.endCellId);
    
    if (!startCellWidget || !endCellWidget) {
      return [];
    }
    
    // If selection is within the same cell
    if (selection.startCellId === selection.endCellId) {
      const editorNode = startCellWidget.node.querySelector('.CodeMirror') || 
                         startCellWidget.node.querySelector('.jp-Editor');
      
      if (!editorNode) {
        return [];
      }
      
      const editorRect = editorNode.getBoundingClientRect();
      const lineHeight = 20; // Approximate line height
      const charWidth = 8;   // Approximate character width
      
      // Calculate start and end positions (simplified)
      const startLine = Math.floor(selection.startOffset / 80);
      const startCh = selection.startOffset % 80;
      const endLine = Math.floor(selection.endOffset / 80);
      const endCh = selection.endOffset % 80;
      
      // If selection is on a single line
      if (startLine === endLine) {
        return [{
          top: editorRect.top - containerRect.top + (startLine * lineHeight),
          left: editorRect.left - containerRect.left + (startCh * charWidth),
          width: (endCh - startCh) * charWidth,
          height: lineHeight
        }];
      }
      
      // If selection spans multiple lines (simplified - just create one big rectangle)
      return [{
        top: editorRect.top - containerRect.top + (startLine * lineHeight),
        left: editorRect.left - containerRect.left,
        width: editorRect.width,
        height: (endLine - startLine + 1) * lineHeight
      }];
    }
    
    // If selection spans multiple cells (simplified - just highlight the cells)
    const rects: Array<{ top: number; left: number; width: number; height: number }> = [];
    let inSelection = false;
    
    for (const widget of cellWidgets) {
      if (widget.model.id === selection.startCellId) {
        inSelection = true;
      }
      
      if (inSelection) {
        const editorNode = widget.node.querySelector('.CodeMirror') || 
                          widget.node.querySelector('.jp-Editor');
        
        if (editorNode) {
          const editorRect = editorNode.getBoundingClientRect();
          rects.push({
            top: editorRect.top - containerRect.top,
            left: editorRect.left - containerRect.left,
            width: editorRect.width,
            height: editorRect.height
          });
        }
      }
      
      if (widget.model.id === selection.endCellId) {
        break;
      }
    }
    
    return rects;
  };

  // Calculate cursor and selection positions
  const calculatePositions = () => {
    if (!containerRef.current || !notebookPanel.content.widgets.length) {
      return [];
    }

    const positions: React.ReactNode[] = [];
    const containerRect = containerRef.current.getBoundingClientRect();
    const cellWidgets = notebookPanel.content.widgets;

    otherUsers.forEach((user, clientId) => {
      // Skip users without cursor position
      if (!user.cursor) {
        return;
      }

      // Find the cell element by ID
      const cellWidget = cellWidgets.find(
        widget => widget.model.id === user.cursor?.cellId
      );

      if (!cellWidget) {
        return;
      }

      // Calculate cursor position
      const cursorPos = calculateCursorPosition(user.cursor, cellWidget, containerRect);
      if (!cursorPos) {
        return;
      }

      // Create cursor element
      positions.push(
        <div 
          key={`cursor-${clientId}`}
          className="jp-UserPresence-cursor"
          style={{
            position: 'absolute',
            top: `${cursorPos.top}px`,
            left: `${cursorPos.left}px`,
            height: '20px', // Approximate line height
            width: '2px',
            backgroundColor: user.color,
            transition: 'all 100ms ease',
            zIndex: 1000
          }}
        >
          {/* User label */}
          <div 
            className="jp-UserPresence-userLabel"
            style={{
              position: 'absolute',
              top: '-20px',
              left: '0',
              backgroundColor: user.color,
              color: '#fff',
              padding: '2px 6px',
              borderRadius: '3px',
              fontSize: '12px',
              whiteSpace: 'nowrap',
              pointerEvents: 'none',
              transform: 'translateY(-100%)',
              maxWidth: '150px',
              overflow: 'hidden',
              textOverflow: 'ellipsis'
            }}
          >
            {user.displayName}
            {user.status === UserStatus.Editing && ' (editing)'}
            {user.status === UserStatus.Idle && ' (idle)'}
          </div>
        </div>
      );

      // Render selection if present
      if (user.selection) {
        const selectionRects = calculateSelectionRects(
          user.selection, 
          cellWidgets, 
          containerRect
        );
        
        selectionRects.forEach((rect, index) => {
          positions.push(
            <div
              key={`selection-${clientId}-${index}`}
              className="jp-UserPresence-selection"
              style={{
                position: 'absolute',
                top: `${rect.top}px`,
                left: `${rect.left}px`,
                width: `${rect.width}px`,
                height: `${rect.height}px`,
                backgroundColor: user.color,
                opacity: 0.2,
                pointerEvents: 'none',
                zIndex: 999
              }}
            />
          );
        });
      }
    });

    return positions;
  };

  // Recalculate positions when notebook content changes
  useEffect(() => {
    const onContentChanged = () => {
      // Force re-render to recalculate positions
      setOtherUsers(new Map(otherUsers));
    };

    // Listen for notebook model changes
    notebookPanel.content.modelChanged.connect(onContentChanged);
    
    // Listen for active cell changes
    notebookPanel.content.activeCellChanged.connect(onContentChanged);
    
    // Listen for cell content changes
    const onCellsChanged = () => {
      onContentChanged();
    };
    
    if (notebookPanel.content.model) {
      notebookPanel.content.model.cells.changed.connect(onCellsChanged);
    }
    
    // Listen for notebook scrolling
    const onScroll = () => {
      onContentChanged();
    };
    
    notebookPanel.content.node.addEventListener('scroll', onScroll, { passive: true });
    
    // Listen for window resize
    window.addEventListener('resize', onContentChanged);
    
    return () => {
      notebookPanel.content.modelChanged.disconnect(onContentChanged);
      notebookPanel.content.activeCellChanged.disconnect(onContentChanged);
      
      if (notebookPanel.content.model) {
        notebookPanel.content.model.cells.changed.disconnect(onCellsChanged);
      }
      
      notebookPanel.content.node.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onContentChanged);
    };
  }, [notebookPanel, otherUsers]);

  return (
    <div 
      ref={containerRef} 
      className="jp-UserPresence-container"
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        pointerEvents: 'none', // Allow clicking through to the notebook
        zIndex: 10, // Above notebook content but below dialogs
        overflow: 'hidden'
      }}
      aria-hidden="true" // Hide from screen readers since this is visual only
    >
      {calculatePositions()}
    </div>
  );
};

/**
 * A namespace for UserPresence statics.
 */
export namespace UserPresence {
  /**
   * Create a new UserPresence component wrapped in a ReactWidget.
   *
   * @param props - The component props.
   * @returns A new UserPresence widget.
   */
  export function create(props: IUserPresenceProps): ReactWidget {
    const widget = ReactWidget.create(<UserPresence {...props} />);
    widget.addClass('jp-UserPresence');
    return widget;
  }

  /**
   * Create the CSS for the UserPresence component.
   * 
   * @returns The CSS for the UserPresence component.
   */
  export function createStyle(): HTMLElement {
    const style = document.createElement('style');
    style.textContent = `
      .jp-UserPresence-container {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        pointer-events: none;
        z-index: 10;
        overflow: hidden;
      }

      .jp-UserPresence-cursor {
        position: absolute;
        width: 2px;
        height: 20px;
        background-color: #4285F4;
        transition: all 100ms ease;
        z-index: 1000;
      }

      .jp-UserPresence-userLabel {
        position: absolute;
        top: -20px;
        left: 0;
        background-color: inherit;
        color: white;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 12px;
        white-space: nowrap;
        pointer-events: none;
        transform: translateY(-100%);
        max-width: 150px;
        overflow: hidden;
        text-overflow: ellipsis;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
      }

      .jp-UserPresence-selection {
        position: absolute;
        background-color: #4285F4;
        opacity: 0.2;
        pointer-events: none;
        z-index: 999;
      }

      /* Animation for cursor blinking */
      @keyframes jp-UserPresence-blink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0; }
      }

      /* Apply animation only when cursor is not moving */
      .jp-UserPresence-cursor:not(:hover) {
        animation: jp-UserPresence-blink 1s step-end infinite;
      }
    `;
    return style;
  }
}
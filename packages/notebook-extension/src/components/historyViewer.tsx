// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { NotebookPanel } from '@jupyterlab/notebook';
import { IHistoryService, IHistoryVersion, IVersionDiff } from '../services/history';

/**
 * CSS classes for the History Viewer component.
 */
const HISTORY_VIEWER_CLASS = 'jp-HistoryViewer';
const HISTORY_VIEWER_HEADER_CLASS = 'jp-HistoryViewer-header';
const HISTORY_VIEWER_BODY_CLASS = 'jp-HistoryViewer-body';
const HISTORY_VIEWER_TIMELINE_CLASS = 'jp-HistoryViewer-timeline';
const HISTORY_VIEWER_TIMELINE_ITEM_CLASS = 'jp-HistoryViewer-timelineItem';
const HISTORY_VIEWER_TIMELINE_ITEM_SELECTED_CLASS = 'jp-HistoryViewer-timelineItem-selected';
const HISTORY_VIEWER_DIFF_CLASS = 'jp-HistoryViewer-diff';
const HISTORY_VIEWER_DIFF_HEADER_CLASS = 'jp-HistoryViewer-diffHeader';
const HISTORY_VIEWER_DIFF_CONTENT_CLASS = 'jp-HistoryViewer-diffContent';
const HISTORY_VIEWER_DIFF_ADDITION_CLASS = 'jp-HistoryViewer-diffAddition';
const HISTORY_VIEWER_DIFF_DELETION_CLASS = 'jp-HistoryViewer-diffDeletion';
const HISTORY_VIEWER_CONTROLS_CLASS = 'jp-HistoryViewer-controls';
const HISTORY_VIEWER_BUTTON_CLASS = 'jp-HistoryViewer-button';
const HISTORY_VIEWER_RESTORE_BUTTON_CLASS = 'jp-HistoryViewer-restoreButton';
const HISTORY_VIEWER_CLOSE_BUTTON_CLASS = 'jp-HistoryViewer-closeButton';

/**
 * Interface for the History Viewer component props.
 */
interface IHistoryViewerProps {
  /**
   * The notebook panel containing the notebook to show history for.
   */
  notebookPanel: NotebookPanel;

  /**
   * The history service for accessing version history.
   */
  historyService: IHistoryService;

  /**
   * The translator for internationalization.
   */
  translator?: ITranslator;

  /**
   * Callback to close the history viewer.
   */
  onClose: () => void;
}

/**
 * A React component for viewing and navigating notebook version history.
 */
export function HistoryViewer(props: IHistoryViewerProps): JSX.Element {
  const { notebookPanel, historyService, onClose } = props;
  const translator = props.translator || nullTranslator;
  const trans = translator.load('notebook');

  // State for the component
  const [versions, setVersions] = useState<IHistoryVersion[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<IHistoryVersion | null>(null);
  const [comparisonVersion, setComparisonVersion] = useState<IHistoryVersion | null>(null);
  const [diff, setDiff] = useState<IVersionDiff | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [diffVisualization, setDiffVisualization] = useState<'inline' | 'side-by-side' | 'unified'>('inline');

  // Refs for keyboard navigation
  const timelineRef = useRef<HTMLDivElement>(null);

  /**
   * Load the version history when the component mounts.
   */
  useEffect(() => {
    const loadHistory = async () => {
      try {
        setIsLoading(true);
        setError(null);
        
        // Get the document ID from the notebook panel
        const documentId = notebookPanel.context.path;
        
        // Load the version history from the history service
        const history = await historyService.getVersionHistory(documentId);
        setVersions(history);
        
        // Select the most recent version by default
        if (history.length > 0) {
          setSelectedVersion(history[0]);
          // Set comparison version to the previous version if available
          if (history.length > 1) {
            setComparisonVersion(history[1]);
          }
        }
      } catch (err) {
        console.error('Failed to load version history:', err);
        setError(trans.__('Failed to load version history. Please try again.'));
      } finally {
        setIsLoading(false);
      }
    };
    
    loadHistory();
  }, [notebookPanel, historyService, trans]);

  /**
   * Update the diff when selected or comparison versions change.
   */
  useEffect(() => {
    const updateDiff = async () => {
      if (selectedVersion && comparisonVersion) {
        try {
          setIsLoading(true);
          const documentId = notebookPanel.context.path;
          const versionDiff = await historyService.getVersionDiff(
            documentId,
            selectedVersion.id,
            comparisonVersion.id,
            diffVisualization
          );
          setDiff(versionDiff);
        } catch (err) {
          console.error('Failed to load version diff:', err);
          setError(trans.__('Failed to load version comparison. Please try again.'));
        } finally {
          setIsLoading(false);
        }
      } else {
        setDiff(null);
      }
    };
    
    updateDiff();
  }, [selectedVersion, comparisonVersion, diffVisualization, notebookPanel, historyService, trans]);

  /**
   * Handle selecting a version from the timeline.
   */
  const handleSelectVersion = useCallback((version: IHistoryVersion) => {
    if (version.id === selectedVersion?.id) {
      return;
    }
    
    // If selecting a version that was the comparison version,
    // swap the selected and comparison versions
    if (version.id === comparisonVersion?.id) {
      setComparisonVersion(selectedVersion);
      setSelectedVersion(version);
      return;
    }
    
    // Otherwise, set the selected version and update the comparison version
    setSelectedVersion(version);
    
    // If the selected version is newer than the current comparison version,
    // or if there is no comparison version, set the comparison version to the next older version
    const versionIndex = versions.findIndex(v => v.id === version.id);
    if (versionIndex < versions.length - 1) {
      setComparisonVersion(versions[versionIndex + 1]);
    } else {
      // If this is the oldest version, compare with the next newer version
      if (versionIndex > 0) {
        setComparisonVersion(versions[versionIndex - 1]);
      } else {
        setComparisonVersion(null);
      }
    }
  }, [selectedVersion, comparisonVersion, versions]);

  /**
   * Handle restoring to a selected version.
   */
  const handleRestore = useCallback(async () => {
    if (!selectedVersion) {
      return;
    }
    
    try {
      setIsLoading(true);
      const documentId = notebookPanel.context.path;
      await historyService.restoreVersion(documentId, selectedVersion.id);
      // Reload the notebook content
      await notebookPanel.context.save();
      await notebookPanel.context.revert();
      onClose();
    } catch (err) {
      console.error('Failed to restore version:', err);
      setError(trans.__('Failed to restore version. Please try again.'));
    } finally {
      setIsLoading(false);
    }
  }, [selectedVersion, notebookPanel, historyService, onClose, trans]);

  /**
   * Handle keyboard navigation in the timeline.
   */
  const handleTimelineKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (!selectedVersion || versions.length === 0) {
      return;
    }
    
    const currentIndex = versions.findIndex(v => v.id === selectedVersion.id);
    let newIndex = currentIndex;
    
    switch (event.key) {
      case 'ArrowUp':
      case 'ArrowLeft':
        newIndex = Math.max(0, currentIndex - 1);
        event.preventDefault();
        break;
      case 'ArrowDown':
      case 'ArrowRight':
        newIndex = Math.min(versions.length - 1, currentIndex + 1);
        event.preventDefault();
        break;
      case 'Home':
        newIndex = 0;
        event.preventDefault();
        break;
      case 'End':
        newIndex = versions.length - 1;
        event.preventDefault();
        break;
      default:
        return;
    }
    
    if (newIndex !== currentIndex) {
      handleSelectVersion(versions[newIndex]);
      // Scroll the selected item into view
      const timelineItems = timelineRef.current?.querySelectorAll(`.${HISTORY_VIEWER_TIMELINE_ITEM_CLASS}`);
      timelineItems?.[newIndex]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [selectedVersion, versions, handleSelectVersion]);

  /**
   * Format a timestamp for display.
   */
  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  /**
   * Render the timeline of versions.
   */
  const renderTimeline = () => {
    if (versions.length === 0) {
      return (
        <div className={HISTORY_VIEWER_TIMELINE_CLASS}>
          <p>{trans.__('No version history available.')}</p>
        </div>
      );
    }
    
    return (
      <div 
        className={HISTORY_VIEWER_TIMELINE_CLASS} 
        ref={timelineRef}
        tabIndex={0}
        role="listbox"
        aria-label={trans.__('Version history timeline')}
        onKeyDown={handleTimelineKeyDown}
      >
        {versions.map(version => (
          <div
            key={version.id}
            className={`${HISTORY_VIEWER_TIMELINE_ITEM_CLASS} ${
              version.id === selectedVersion?.id ? HISTORY_VIEWER_TIMELINE_ITEM_SELECTED_CLASS : ''
            }`}
            onClick={() => handleSelectVersion(version)}
            role="option"
            aria-selected={version.id === selectedVersion?.id}
            tabIndex={version.id === selectedVersion?.id ? 0 : -1}
          >
            <div className="jp-HistoryViewer-timelineItemHeader">
              <span className="jp-HistoryViewer-timelineItemTimestamp">
                {formatTimestamp(version.timestamp)}
              </span>
              <span className="jp-HistoryViewer-timelineItemAuthor">
                {version.author}
              </span>
            </div>
            <div className="jp-HistoryViewer-timelineItemDescription">
              {version.description || trans.__('No description')}
            </div>
          </div>
        ))}
      </div>
    );
  };

  /**
   * Render the diff visualization.
   */
  const renderDiff = () => {
    if (!diff) {
      return (
        <div className={HISTORY_VIEWER_DIFF_CLASS}>
          <p>{trans.__('Select two versions to compare.')}</p>
        </div>
      );
    }
    
    return (
      <div className={HISTORY_VIEWER_DIFF_CLASS}>
        <div className={HISTORY_VIEWER_DIFF_HEADER_CLASS}>
          <h3>
            {trans.__('Comparing versions: %1 and %2', 
              formatTimestamp(selectedVersion?.timestamp || ''), 
              formatTimestamp(comparisonVersion?.timestamp || '')
            )}
          </h3>
          <div className="jp-HistoryViewer-diffControls">
            <select 
              value={diffVisualization} 
              onChange={(e) => setDiffVisualization(e.target.value as any)}
              aria-label={trans.__('Diff visualization mode')}
            >
              <option value="inline">{trans.__('Inline')}</option>
              <option value="side-by-side">{trans.__('Side by Side')}</option>
              <option value="unified">{trans.__('Unified')}</option>
            </select>
          </div>
        </div>
        <div className={HISTORY_VIEWER_DIFF_CONTENT_CLASS}>
          {diff.cells.map((cellDiff, index) => (
            <div key={index} className="jp-HistoryViewer-diffCell">
              <div className="jp-HistoryViewer-diffCellHeader">
                <span>{trans.__('Cell %1', index + 1)}</span>
                <span className="jp-HistoryViewer-diffCellType">{cellDiff.cellType}</span>
              </div>
              <div className="jp-HistoryViewer-diffCellContent">
                {cellDiff.changes.map((change, changeIndex) => (
                  <pre 
                    key={changeIndex} 
                    className={`jp-HistoryViewer-diffLine ${
                      change.type === 'addition' ? HISTORY_VIEWER_DIFF_ADDITION_CLASS : 
                      change.type === 'deletion' ? HISTORY_VIEWER_DIFF_DELETION_CLASS : ''
                    }`}
                  >
                    <code>{change.content}</code>
                  </pre>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className={HISTORY_VIEWER_CLASS} role="dialog" aria-modal="true" aria-labelledby="history-viewer-title">
      <div className={HISTORY_VIEWER_HEADER_CLASS}>
        <h2 id="history-viewer-title">{trans.__('Version History')}</h2>
        <button 
          className={HISTORY_VIEWER_CLOSE_BUTTON_CLASS}
          onClick={onClose}
          aria-label={trans.__('Close')}
        >
          <span className="jp-HistoryViewer-closeButtonIcon" aria-hidden="true">×</span>
        </button>
      </div>
      
      {error && <div className="jp-HistoryViewer-error">{error}</div>}
      
      {isLoading ? (
        <div className="jp-HistoryViewer-loading">
          <div className="jp-Spinner"></div>
          <p>{trans.__('Loading...')}</p>
        </div>
      ) : (
        <div className={HISTORY_VIEWER_BODY_CLASS}>
          {renderTimeline()}
          {renderDiff()}
        </div>
      )}
      
      <div className={HISTORY_VIEWER_CONTROLS_CLASS}>
        <button 
          className={`${HISTORY_VIEWER_BUTTON_CLASS} ${HISTORY_VIEWER_RESTORE_BUTTON_CLASS}`}
          onClick={handleRestore}
          disabled={!selectedVersion || isLoading}
          aria-label={trans.__('Restore to selected version')}
        >
          {trans.__('Restore This Version')}
        </button>
      </div>
    </div>
  );
}

/**
 * A namespace for HistoryViewer statics.
 */
export namespace HistoryViewer {
  /**
   * Create a new HistoryViewer widget.
   */
  export function createWidget(options: {
    notebookPanel: NotebookPanel;
    historyService: IHistoryService;
    translator?: ITranslator;
    onClose: () => void;
  }): ReactWidget {
    const widget = ReactWidget.create(
      <HistoryViewer
        notebookPanel={options.notebookPanel}
        historyService={options.historyService}
        translator={options.translator}
        onClose={options.onClose}
      />
    );
    widget.addClass('jp-HistoryViewer-widget');
    return widget;
  }
}
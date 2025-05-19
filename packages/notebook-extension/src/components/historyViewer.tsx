// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { NotebookPanel } from '@jupyterlab/notebook';
import { Notebook } from '@jupyterlab/notebook';
import { IHistoryService, VersionInfo, DiffType } from '../tokens';

/**
 * Interface for the HistoryViewer props
 */
interface IHistoryViewerProps {
  /**
   * The notebook panel containing the notebook
   */
  notebookPanel: NotebookPanel;

  /**
   * The history service
   */
  historyService: IHistoryService;

  /**
   * The translator
   */
  translator?: ITranslator;
}

/**
 * Interface for the version comparison state
 */
interface IComparisonState {
  /**
   * The older version to compare
   */
  oldVersion: VersionInfo | null;

  /**
   * The newer version to compare
   */
  newVersion: VersionInfo | null;

  /**
   * The type of diff visualization to use
   */
  diffType: DiffType;
}

/**
 * A React component for viewing and navigating notebook version history.
 */
export function HistoryViewer(props: IHistoryViewerProps): JSX.Element {
  const { notebookPanel, historyService, translator = nullTranslator } = props;
  const trans = translator.load('notebook');
  
  // State for the list of versions
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  
  // State for the comparison view
  const [comparison, setComparison] = useState<IComparisonState>({
    oldVersion: null,
    newVersion: null,
    diffType: 'unified'
  });
  
  // State for the restore confirmation
  const [showRestoreConfirm, setShowRestoreConfirm] = useState<boolean>(false);
  const [versionToRestore, setVersionToRestore] = useState<VersionInfo | null>(null);
  
  // Refs for keyboard navigation
  const timelineRef = useRef<HTMLDivElement>(null);
  const diffViewRef = useRef<HTMLDivElement>(null);
  
  /**
   * Load the version history when the component mounts
   */
  useEffect(() => {
    const loadVersions = async () => {
      try {
        setLoading(true);
        const history = await historyService.getVersionHistory(notebookPanel.context.path);
        setVersions(history);
        setError(null);
        
        // Set the current version as the new version for comparison by default
        if (history.length > 0) {
          setComparison({
            oldVersion: history.length > 1 ? history[1] : null,
            newVersion: history[0],
            diffType: 'unified'
          });
        }
      } catch (err) {
        console.error('Failed to load version history:', err);
        setError(trans.__('Failed to load version history. Please try again.'));
      } finally {
        setLoading(false);
      }
    };
    
    loadVersions();
    
    // Subscribe to version changes
    const onVersionAdded = () => {
      loadVersions();
    };
    
    historyService.versionAdded.connect(onVersionAdded);
    
    return () => {
      historyService.versionAdded.disconnect(onVersionAdded);
    };
  }, [historyService, notebookPanel.context.path, trans]);
  
  /**
   * Handle selecting a version for comparison
   */
  const handleSelectVersion = useCallback((version: VersionInfo, isOld: boolean) => {
    setComparison(prev => {
      // If selecting the old version
      if (isOld) {
        // Don't allow selecting a version newer than the current new version
        if (prev.newVersion && version.timestamp >= prev.newVersion.timestamp) {
          return prev;
        }
        return { ...prev, oldVersion: version };
      } 
      // If selecting the new version
      else {
        // Don't allow selecting a version older than the current old version
        if (prev.oldVersion && version.timestamp <= prev.oldVersion.timestamp) {
          return prev;
        }
        return { ...prev, newVersion: version };
      }
    });
  }, []);
  
  /**
   * Handle changing the diff visualization type
   */
  const handleChangeDiffType = useCallback((type: DiffType) => {
    setComparison(prev => ({ ...prev, diffType: type }));
  }, []);
  
  /**
   * Handle restoring to a previous version
   */
  const handleRestore = useCallback(async () => {
    if (!versionToRestore) {
      return;
    }
    
    try {
      await historyService.restoreVersion(notebookPanel.context.path, versionToRestore.id);
      setShowRestoreConfirm(false);
      setVersionToRestore(null);
    } catch (err) {
      console.error('Failed to restore version:', err);
      setError(trans.__('Failed to restore version. Please try again.'));
    }
  }, [historyService, notebookPanel.context.path, versionToRestore, trans]);
  
  /**
   * Handle keyboard navigation
   */
  const handleKeyDown = useCallback((event: React.KeyboardEvent) => {
    // Handle keyboard navigation in the timeline
    if (timelineRef.current === document.activeElement || 
        timelineRef.current?.contains(document.activeElement)) {
      if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
        event.preventDefault();
        const focusableElements = timelineRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        const currentIndex = Array.from(focusableElements).findIndex(
          el => el === document.activeElement
        );
        
        let nextIndex;
        if (event.key === 'ArrowUp') {
          nextIndex = currentIndex > 0 ? currentIndex - 1 : focusableElements.length - 1;
        } else {
          nextIndex = currentIndex < focusableElements.length - 1 ? currentIndex + 1 : 0;
        }
        
        focusableElements[nextIndex]?.focus();
      }
    }
  }, []);
  
  /**
   * Render the version timeline
   */
  const renderTimeline = () => {
    if (loading) {
      return <div className="jp-HistoryViewer-loading">{trans.__('Loading history...')}</div>;
    }
    
    if (error) {
      return <div className="jp-HistoryViewer-error">{error}</div>;
    }
    
    if (versions.length === 0) {
      return (
        <div className="jp-HistoryViewer-empty">
          {trans.__('No version history available.')}
        </div>
      );
    }
    
    return (
      <div 
        className="jp-HistoryViewer-timeline" 
        ref={timelineRef}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        role="listbox"
        aria-label={trans.__('Version history timeline')}
      >
        {versions.map((version, index) => {
          const isSelected = 
            comparison.oldVersion?.id === version.id || 
            comparison.newVersion?.id === version.id;
          
          const isOldVersion = comparison.oldVersion?.id === version.id;
          const isNewVersion = comparison.newVersion?.id === version.id;
          
          const date = new Date(version.timestamp);
          const formattedDate = date.toLocaleDateString();
          const formattedTime = date.toLocaleTimeString();
          
          return (
            <div 
              key={version.id}
              className={`jp-HistoryViewer-version ${isSelected ? 'jp-mod-selected' : ''}`}
              role="option"
              aria-selected={isSelected}
            >
              <div className="jp-HistoryViewer-version-header">
                <div className="jp-HistoryViewer-version-title">
                  {index === 0 ? trans.__('Current Version') : trans.__('Version %1', index)}
                </div>
                <div className="jp-HistoryViewer-version-date">
                  {formattedDate} {formattedTime}
                </div>
              </div>
              
              <div className="jp-HistoryViewer-version-info">
                <div className="jp-HistoryViewer-version-author">
                  {version.author ? version.author : trans.__('Unknown')}
                </div>
                {version.message && (
                  <div className="jp-HistoryViewer-version-message">
                    {version.message}
                  </div>
                )}
              </div>
              
              <div className="jp-HistoryViewer-version-actions">
                <button
                  className={`jp-HistoryViewer-version-select-old ${isOldVersion ? 'jp-mod-selected' : ''}`}
                  onClick={() => handleSelectVersion(version, true)}
                  disabled={comparison.newVersion && version.timestamp >= comparison.newVersion.timestamp}
                  aria-label={trans.__('Select as older version for comparison')}
                  title={trans.__('Select as older version for comparison')}
                >
                  {trans.__('Older')}
                </button>
                
                <button
                  className={`jp-HistoryViewer-version-select-new ${isNewVersion ? 'jp-mod-selected' : ''}`}
                  onClick={() => handleSelectVersion(version, false)}
                  disabled={comparison.oldVersion && version.timestamp <= comparison.oldVersion.timestamp}
                  aria-label={trans.__('Select as newer version for comparison')}
                  title={trans.__('Select as newer version for comparison')}
                >
                  {trans.__('Newer')}
                </button>
                
                <button
                  className="jp-HistoryViewer-version-restore"
                  onClick={() => {
                    setVersionToRestore(version);
                    setShowRestoreConfirm(true);
                  }}
                  aria-label={trans.__('Restore to this version')}
                  title={trans.__('Restore to this version')}
                >
                  {trans.__('Restore')}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    );
  };
  
  /**
   * Render the diff view
   */
  const renderDiffView = () => {
    const { oldVersion, newVersion, diffType } = comparison;
    
    if (!oldVersion || !newVersion) {
      return (
        <div className="jp-HistoryViewer-diff-empty">
          {trans.__('Select two versions to compare')}
        </div>
      );
    }
    
    return (
      <div 
        className="jp-HistoryViewer-diff" 
        ref={diffViewRef}
      >
        <div className="jp-HistoryViewer-diff-header">
          <div className="jp-HistoryViewer-diff-title">
            {trans.__('Comparing versions')}
          </div>
          
          <div className="jp-HistoryViewer-diff-controls">
            <select
              className="jp-HistoryViewer-diff-type"
              value={diffType}
              onChange={(e) => handleChangeDiffType(e.target.value as DiffType)}
              aria-label={trans.__('Diff visualization type')}
            >
              <option value="unified">{trans.__('Unified')}</option>
              <option value="side-by-side">{trans.__('Side by Side')}</option>
              <option value="inline">{trans.__('Inline')}</option>
            </select>
          </div>
        </div>
        
        <div className="jp-HistoryViewer-diff-content">
          {/* This would be populated with the actual diff content from the history service */}
          {historyService.renderDiff(
            oldVersion, 
            newVersion, 
            diffType
          )}
        </div>
      </div>
    );
  };
  
  /**
   * Render the restore confirmation dialog
   */
  const renderRestoreConfirm = () => {
    if (!showRestoreConfirm || !versionToRestore) {
      return null;
    }
    
    const date = new Date(versionToRestore.timestamp);
    const formattedDate = date.toLocaleDateString();
    const formattedTime = date.toLocaleTimeString();
    
    return (
      <div className="jp-HistoryViewer-restore-confirm-overlay">
        <div className="jp-HistoryViewer-restore-confirm">
          <div className="jp-HistoryViewer-restore-confirm-header">
            {trans.__('Restore Version')}
          </div>
          
          <div className="jp-HistoryViewer-restore-confirm-content">
            <p>
              {trans.__('Are you sure you want to restore the notebook to the version from %1 at %2?', 
                formattedDate, 
                formattedTime
              )}
            </p>
            <p className="jp-HistoryViewer-restore-confirm-warning">
              {trans.__('This will overwrite the current version of the notebook. This action cannot be undone.')}
            </p>
          </div>
          
          <div className="jp-HistoryViewer-restore-confirm-actions">
            <button
              className="jp-HistoryViewer-restore-confirm-cancel"
              onClick={() => {
                setShowRestoreConfirm(false);
                setVersionToRestore(null);
              }}
            >
              {trans.__('Cancel')}
            </button>
            
            <button
              className="jp-HistoryViewer-restore-confirm-ok"
              onClick={handleRestore}
            >
              {trans.__('Restore')}
            </button>
          </div>
        </div>
      </div>
    );
  };
  
  return (
    <div className="jp-HistoryViewer">
      <div className="jp-HistoryViewer-header">
        <h2 className="jp-HistoryViewer-title">
          {trans.__('Version History')}
        </h2>
      </div>
      
      <div className="jp-HistoryViewer-content">
        <div className="jp-HistoryViewer-split">
          <div className="jp-HistoryViewer-timeline-container">
            <h3 className="jp-HistoryViewer-section-title">
              {trans.__('Timeline')}
            </h3>
            {renderTimeline()}
          </div>
          
          <div className="jp-HistoryViewer-diff-container">
            <h3 className="jp-HistoryViewer-section-title">
              {trans.__('Changes')}
            </h3>
            {renderDiffView()}
          </div>
        </div>
      </div>
      
      {renderRestoreConfirm()}
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
  }): ReactWidget {
    const { notebookPanel, historyService, translator } = options;
    
    return ReactWidget.create(
      <HistoryViewer 
        notebookPanel={notebookPanel}
        historyService={historyService}
        translator={translator}
      />
    );
  }
}
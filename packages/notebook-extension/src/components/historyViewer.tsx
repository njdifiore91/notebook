// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { IVersionHistory, IVersionSnapshot, IVersionComparison, ICellDiff } from '@jupyterlab/notebook/lib/collab/history';
import { NotebookPanel, INotebookTracker } from '@jupyterlab/notebook';
import { Time } from '@jupyterlab/coreutils';
import ReactDiffViewer from 'react-diff-viewer';
import { CommandRegistry } from '@lumino/commands';

/**
 * Props for the HistoryViewer component.
 */
export interface IHistoryViewerProps {
  /**
   * The version history service instance.
   */
  versionHistory: IVersionHistory;

  /**
   * The notebook panel containing the notebook.
   */
  notebookPanel: NotebookPanel;

  /**
   * The notebook tracker.
   */
  notebookTracker: INotebookTracker;

  /**
   * The command registry for executing commands.
   */
  commands: CommandRegistry;
}

/**
 * A component that displays the version history of a notebook.
 * 
 * This component shows a timeline of notebook edits with user attribution,
 * timestamps, and change summaries. It allows users to view past versions,
 * compare changes, and restore previous states.
 */
export const HistoryViewer: React.FC<IHistoryViewerProps> = ({
  versionHistory,
  notebookPanel,
  notebookTracker,
  commands
}) => {
  // State for versions
  const [versions, setVersions] = useState<IVersionSnapshot[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [comparisonVersion, setComparisonVersion] = useState<string | null>(null);
  const [comparison, setComparison] = useState<IVersionComparison | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'timeline' | 'diff' | 'cell-history'>('timeline');
  const [selectedCell, setSelectedCell] = useState<string | null>(null);
  const [cellHistory, setCellHistory] = useState<any[]>([]);
  
  // Filters
  const [userFilter, setUserFilter] = useState<string>('');
  const [timeRangeFilter, setTimeRangeFilter] = useState<{start: number | null, end: number | null}>({start: null, end: null});
  const [showMajorVersionsOnly, setShowMajorVersionsOnly] = useState<boolean>(false);

  // Load versions
  useEffect(() => {
    const loadVersions = async () => {
      try {
        setLoading(true);
        setError(null);
        const allVersions = await versionHistory.getVersions();
        // Sort versions by timestamp (newest first)
        allVersions.sort((a, b) => b.timestamp - a.timestamp);
        setVersions(allVersions);
        
        // Select the most recent version by default
        if (allVersions.length > 0 && !selectedVersion) {
          setSelectedVersion(allVersions[0].id);
          // Compare with the second most recent version if available
          if (allVersions.length > 1) {
            setComparisonVersion(allVersions[1].id);
          }
        }
      } catch (err) {
        console.error('Failed to load versions:', err);
        setError('Failed to load version history. Please try again.');
      } finally {
        setLoading(false);
      }
    };

    loadVersions();

    // Listen for new versions
    const onVersionCreated = (sender: any, version: IVersionSnapshot) => {
      setVersions(prevVersions => {
        const newVersions = [version, ...prevVersions];
        // Sort by timestamp (newest first)
        newVersions.sort((a, b) => b.timestamp - a.timestamp);
        return newVersions;
      });
    };

    versionHistory.versionCreated.connect(onVersionCreated);

    return () => {
      versionHistory.versionCreated.disconnect(onVersionCreated);
    };
  }, [versionHistory, selectedVersion]);

  // Load comparison when selected versions change
  useEffect(() => {
    const loadComparison = async () => {
      if (selectedVersion && comparisonVersion && selectedVersion !== comparisonVersion) {
        try {
          setLoading(true);
          setError(null);
          const result = await versionHistory.compareVersions(comparisonVersion, selectedVersion);
          setComparison(result);
        } catch (err) {
          console.error('Failed to compare versions:', err);
          setError('Failed to compare versions. Please try again.');
          setComparison(null);
        } finally {
          setLoading(false);
        }
      } else {
        setComparison(null);
      }
    };

    if (viewMode === 'diff') {
      loadComparison();
    }
  }, [versionHistory, selectedVersion, comparisonVersion, viewMode]);

  // Load cell history when selected cell changes
  useEffect(() => {
    const loadCellHistory = async () => {
      if (selectedCell) {
        try {
          setLoading(true);
          setError(null);
          const history = await versionHistory.getCellHistory(selectedCell);
          setCellHistory(history);
        } catch (err) {
          console.error('Failed to load cell history:', err);
          setError('Failed to load cell history. Please try again.');
          setCellHistory([]);
        } finally {
          setLoading(false);
        }
      } else {
        setCellHistory([]);
      }
    };

    if (viewMode === 'cell-history') {
      loadCellHistory();
    }
  }, [versionHistory, selectedCell, viewMode]);

  // Filter versions based on user filters
  const filteredVersions = useMemo(() => {
    return versions.filter(version => {
      // Filter by user
      if (userFilter && !version.author.name.toLowerCase().includes(userFilter.toLowerCase())) {
        return false;
      }

      // Filter by time range
      if (timeRangeFilter.start && version.timestamp < timeRangeFilter.start) {
        return false;
      }
      if (timeRangeFilter.end && version.timestamp > timeRangeFilter.end) {
        return false;
      }

      // Filter by major versions
      if (showMajorVersionsOnly && !version.isMajorVersion) {
        return false;
      }

      return true;
    });
  }, [versions, userFilter, timeRangeFilter, showMajorVersionsOnly]);

  // Get unique users for filter dropdown
  const uniqueUsers = useMemo(() => {
    const users = new Set<string>();
    versions.forEach(version => {
      users.add(version.author.name);
    });
    return Array.from(users).sort();
  }, [versions]);

  // Handle version selection
  const handleVersionSelect = (versionId: string) => {
    setSelectedVersion(versionId);
  };

  // Handle comparison version selection
  const handleComparisonSelect = (versionId: string) => {
    setComparisonVersion(versionId);
  };

  // Handle cell selection
  const handleCellSelect = (cellId: string) => {
    setSelectedCell(cellId);
    setViewMode('cell-history');
  };

  // Handle restore version
  const handleRestoreVersion = async () => {
    if (!selectedVersion) return;

    try {
      setLoading(true);
      setError(null);
      await versionHistory.restoreVersion(selectedVersion);
      // Show success message or notification
    } catch (err) {
      console.error('Failed to restore version:', err);
      setError('Failed to restore version. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Handle restore cell
  const handleRestoreCell = async (cellId: string, versionId: string) => {
    try {
      setLoading(true);
      setError(null);
      // Get the document at the selected version
      const doc = await versionHistory.getDocumentAtVersion(versionId);
      
      // Find the cell in the document
      const cells = doc.getArray('cells');
      let cellContent = null;
      
      for (let i = 0; i < cells.length; i++) {
        const cell = cells.get(i);
        if (cell.get('id') === cellId) {
          const source = cell.get('source');
          cellContent = source.toString();
          break;
        }
      }
      
      if (cellContent !== null) {
        // Find the cell in the current notebook
        const notebook = notebookPanel.content;
        const currentCells = notebook.widgets;
        
        for (let i = 0; i < currentCells.length; i++) {
          const cell = currentCells[i];
          if (cell.model.id === cellId) {
            // Update the cell content
            cell.model.value.text = cellContent;
            break;
          }
        }
      }
    } catch (err) {
      console.error('Failed to restore cell:', err);
      setError('Failed to restore cell. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Export version history as JSON
  const handleExportHistory = () => {
    const historyData = {
      documentId: notebookPanel.context.path,
      versions: versions
    };
    
    const blob = new Blob([JSON.stringify(historyData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `${notebookPanel.context.path.split('/').pop()}-history.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Render the timeline view
  const renderTimeline = () => {
    if (filteredVersions.length === 0) {
      return (
        <div className="jp-HistoryViewer-empty">
          {loading ? 'Loading versions...' : 'No versions found matching the current filters.'}
        </div>
      );
    }

    return (
      <div className="jp-HistoryViewer-timeline">
        {filteredVersions.map(version => (
          <div 
            key={version.id} 
            className={`jp-HistoryViewer-timelineItem ${selectedVersion === version.id ? 'jp-HistoryViewer-timelineItem-selected' : ''}`}
            onClick={() => handleVersionSelect(version.id)}
          >
            <div 
              className="jp-HistoryViewer-timelineItemAvatar"
              style={{ backgroundColor: version.author.color }}
              title={version.author.name}
            >
              {version.author.name.charAt(0).toUpperCase()}
            </div>
            <div className="jp-HistoryViewer-timelineItemContent">
              <div className="jp-HistoryViewer-timelineItemHeader">
                <span className="jp-HistoryViewer-timelineItemAuthor">{version.author.name}</span>
                <span className="jp-HistoryViewer-timelineItemTime" title={new Date(version.timestamp).toLocaleString()}>
                  {Time.formatHuman(new Date(version.timestamp))}
                </span>
              </div>
              <div className="jp-HistoryViewer-timelineItemDescription">
                {version.description}
                {version.isMajorVersion && (
                  <span className="jp-HistoryViewer-majorVersionBadge" title="Major version">Major</span>
                )}
              </div>
              <div className="jp-HistoryViewer-timelineItemChanges">
                {version.cellChanges.length > 0 ? (
                  <>
                    <span className="jp-HistoryViewer-changesSummary">
                      {version.cellChanges.length} cell change{version.cellChanges.length !== 1 ? 's' : ''}
                    </span>
                    <div className="jp-HistoryViewer-changesDetail">
                      {version.cellChanges.map((change, index) => (
                        <div key={index} className="jp-HistoryViewer-changeItem">
                          <span className={`jp-HistoryViewer-changeType jp-HistoryViewer-changeType-${change.changeType}`}>
                            {change.changeType}
                          </span>
                          <span 
                            className="jp-HistoryViewer-cellId"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCellSelect(change.cellId);
                            }}
                          >
                            Cell {change.cellId.substring(0, 8)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <span className="jp-HistoryViewer-noChanges">No cell changes</span>
                )}
              </div>
              <div className="jp-HistoryViewer-timelineItemActions">
                <button 
                  className="jp-HistoryViewer-actionButton jp-HistoryViewer-compareButton"
                  onClick={(e) => {
                    e.stopPropagation();
                    setComparisonVersion(selectedVersion);
                    setSelectedVersion(version.id);
                    setViewMode('diff');
                  }}
                  title="Compare with selected version"
                >
                  Compare
                </button>
                <button 
                  className="jp-HistoryViewer-actionButton jp-HistoryViewer-restoreButton"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedVersion(version.id);
                    handleRestoreVersion();
                  }}
                  title="Restore this version"
                >
                  Restore
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  // Render the diff view
  const renderDiff = () => {
    if (!comparison) {
      return (
        <div className="jp-HistoryViewer-empty">
          {loading ? 'Loading comparison...' : 'Select two versions to compare.'}
        </div>
      );
    }

    const { oldVersion, newVersion, differences } = comparison;
    
    return (
      <div className="jp-HistoryViewer-diff">
        <div className="jp-HistoryViewer-diffHeader">
          <div className="jp-HistoryViewer-diffVersion">
            <div className="jp-HistoryViewer-diffVersionLabel">Old Version:</div>
            <div className="jp-HistoryViewer-diffVersionInfo">
              <span className="jp-HistoryViewer-diffVersionAuthor">{oldVersion.author.name}</span>
              <span className="jp-HistoryViewer-diffVersionTime">{Time.formatHuman(new Date(oldVersion.timestamp))}</span>
            </div>
          </div>
          <div className="jp-HistoryViewer-diffVersion">
            <div className="jp-HistoryViewer-diffVersionLabel">New Version:</div>
            <div className="jp-HistoryViewer-diffVersionInfo">
              <span className="jp-HistoryViewer-diffVersionAuthor">{newVersion.author.name}</span>
              <span className="jp-HistoryViewer-diffVersionTime">{Time.formatHuman(new Date(newVersion.timestamp))}</span>
            </div>
          </div>
        </div>
        
        <div className="jp-HistoryViewer-diffSummary">
          <div className="jp-HistoryViewer-diffStat">
            <span className="jp-HistoryViewer-diffStatLabel jp-HistoryViewer-diffStatAdded">Added:</span>
            <span className="jp-HistoryViewer-diffStatValue">{differences.added.length}</span>
          </div>
          <div className="jp-HistoryViewer-diffStat">
            <span className="jp-HistoryViewer-diffStatLabel jp-HistoryViewer-diffStatRemoved">Removed:</span>
            <span className="jp-HistoryViewer-diffStatValue">{differences.removed.length}</span>
          </div>
          <div className="jp-HistoryViewer-diffStat">
            <span className="jp-HistoryViewer-diffStatLabel jp-HistoryViewer-diffStatModified">Modified:</span>
            <span className="jp-HistoryViewer-diffStatValue">{differences.modified.length}</span>
          </div>
          <div className="jp-HistoryViewer-diffStat">
            <span className="jp-HistoryViewer-diffStatLabel jp-HistoryViewer-diffStatMoved">Moved:</span>
            <span className="jp-HistoryViewer-diffStatValue">{differences.moved.length}</span>
          </div>
        </div>
        
        <div className="jp-HistoryViewer-diffContent">
          {/* Render modified cells */}
          {differences.modified.length > 0 && (
            <div className="jp-HistoryViewer-diffSection">
              <h3 className="jp-HistoryViewer-diffSectionTitle">Modified Cells</h3>
              {differences.modified.map((diff: ICellDiff) => renderCellDiff(diff))}
            </div>
          )}
          
          {/* Render added cells */}
          {differences.added.length > 0 && (
            <div className="jp-HistoryViewer-diffSection">
              <h3 className="jp-HistoryViewer-diffSectionTitle">Added Cells</h3>
              {differences.added.map((diff: ICellDiff) => renderCellDiff(diff))}
            </div>
          )}
          
          {/* Render removed cells */}
          {differences.removed.length > 0 && (
            <div className="jp-HistoryViewer-diffSection">
              <h3 className="jp-HistoryViewer-diffSectionTitle">Removed Cells</h3>
              {differences.removed.map((diff: ICellDiff) => renderCellDiff(diff))}
            </div>
          )}
          
          {/* Render moved cells */}
          {differences.moved.length > 0 && (
            <div className="jp-HistoryViewer-diffSection">
              <h3 className="jp-HistoryViewer-diffSectionTitle">Moved Cells</h3>
              {differences.moved.map((diff: ICellDiff) => renderCellDiff(diff))}
            </div>
          )}
          
          {/* Render metadata changes */}
          {differences.metadataChanges.length > 0 && (
            <div className="jp-HistoryViewer-diffSection">
              <h3 className="jp-HistoryViewer-diffSectionTitle">Metadata Changes</h3>
              <div className="jp-HistoryViewer-metadataDiff">
                {differences.metadataChanges.map((change, index) => (
                  <div key={index} className="jp-HistoryViewer-metadataChange">
                    <div className="jp-HistoryViewer-metadataChangeKey">{change.key}</div>
                    <div className="jp-HistoryViewer-metadataChangeType">{change.changeType}</div>
                    {change.oldValue !== undefined && (
                      <div className="jp-HistoryViewer-metadataChangeOld">
                        <div className="jp-HistoryViewer-metadataChangeLabel">Old:</div>
                        <pre className="jp-HistoryViewer-metadataChangeValue">
                          {JSON.stringify(change.oldValue, null, 2)}
                        </pre>
                      </div>
                    )}
                    {change.newValue !== undefined && (
                      <div className="jp-HistoryViewer-metadataChangeNew">
                        <div className="jp-HistoryViewer-metadataChangeLabel">New:</div>
                        <pre className="jp-HistoryViewer-metadataChangeValue">
                          {JSON.stringify(change.newValue, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  // Render a cell diff
  const renderCellDiff = (diff: ICellDiff) => {
    return (
      <div key={diff.cellId} className="jp-HistoryViewer-cellDiff">
        <div className="jp-HistoryViewer-cellDiffHeader">
          <div className="jp-HistoryViewer-cellDiffInfo">
            <span className="jp-HistoryViewer-cellDiffType">{diff.cellType}</span>
            <span className="jp-HistoryViewer-cellDiffId">{diff.cellId.substring(0, 8)}</span>
            {diff.oldIndex !== undefined && diff.newIndex !== undefined && diff.oldIndex !== diff.newIndex && (
              <span className="jp-HistoryViewer-cellDiffMove">
                Moved from position {diff.oldIndex} to {diff.newIndex}
              </span>
            )}
          </div>
          <div className="jp-HistoryViewer-cellDiffActions">
            <button 
              className="jp-HistoryViewer-actionButton jp-HistoryViewer-cellHistoryButton"
              onClick={() => handleCellSelect(diff.cellId)}
              title="View cell history"
            >
              History
            </button>
            {diff.newContent && (
              <button 
                className="jp-HistoryViewer-actionButton jp-HistoryViewer-restoreCellButton"
                onClick={() => handleRestoreCell(diff.cellId, comparison!.newVersion.id)}
                title="Restore this cell"
              >
                Restore
              </button>
            )}
          </div>
        </div>
        
        {diff.oldContent !== undefined && diff.newContent !== undefined ? (
          <div className="jp-HistoryViewer-cellDiffContent">
            <ReactDiffViewer
              oldValue={diff.oldContent}
              newValue={diff.newContent}
              splitView={true}
              disableWordDiff={false}
              showDiffOnly={false}
              useDarkTheme={document.body.dataset.jpThemeLight !== 'true'}
            />
          </div>
        ) : diff.oldContent !== undefined ? (
          <div className="jp-HistoryViewer-cellDiffContent jp-HistoryViewer-cellDiffRemoved">
            <pre className="jp-HistoryViewer-cellDiffText">{diff.oldContent}</pre>
          </div>
        ) : diff.newContent !== undefined ? (
          <div className="jp-HistoryViewer-cellDiffContent jp-HistoryViewer-cellDiffAdded">
            <pre className="jp-HistoryViewer-cellDiffText">{diff.newContent}</pre>
          </div>
        ) : null}
      </div>
    );
  };

  // Render the cell history view
  const renderCellHistory = () => {
    if (!selectedCell) {
      return (
        <div className="jp-HistoryViewer-empty">
          Select a cell to view its history.
        </div>
      );
    }

    if (loading) {
      return (
        <div className="jp-HistoryViewer-empty">
          Loading cell history...
        </div>
      );
    }

    if (cellHistory.length === 0) {
      return (
        <div className="jp-HistoryViewer-empty">
          No history found for this cell.
        </div>
      );
    }

    return (
      <div className="jp-HistoryViewer-cellHistory">
        <div className="jp-HistoryViewer-cellHistoryHeader">
          <h3 className="jp-HistoryViewer-cellHistoryTitle">History for Cell {selectedCell.substring(0, 8)}</h3>
          <button 
            className="jp-HistoryViewer-actionButton jp-HistoryViewer-backButton"
            onClick={() => setViewMode('timeline')}
          >
            Back to Timeline
          </button>
        </div>
        
        <div className="jp-HistoryViewer-cellHistoryContent">
          {cellHistory.map((change, index) => {
            // Find the version that contains this change
            const version = versions.find(v => 
              v.cellChanges.some(c => c.cellId === selectedCell && 
                ((change.changeType === 'modified' && c.newContent === change.newContent) ||
                 (change.changeType === c.changeType))
              )
            );
            
            return (
              <div key={index} className="jp-HistoryViewer-cellHistoryItem">
                <div className="jp-HistoryViewer-cellHistoryItemHeader">
                  {version && (
                    <>
                      <div 
                        className="jp-HistoryViewer-cellHistoryItemAvatar"
                        style={{ backgroundColor: version.author.color }}
                        title={version.author.name}
                      >
                        {version.author.name.charAt(0).toUpperCase()}
                      </div>
                      <div className="jp-HistoryViewer-cellHistoryItemInfo">
                        <span className="jp-HistoryViewer-cellHistoryItemAuthor">{version.author.name}</span>
                        <span className="jp-HistoryViewer-cellHistoryItemTime">
                          {Time.formatHuman(new Date(version.timestamp))}
                        </span>
                      </div>
                    </>
                  )}
                  <div className="jp-HistoryViewer-cellHistoryItemType">
                    <span className={`jp-HistoryViewer-changeType jp-HistoryViewer-changeType-${change.changeType}`}>
                      {change.changeType}
                    </span>
                  </div>
                </div>
                
                {change.changeType === 'modified' && change.previousContent && change.newContent && (
                  <div className="jp-HistoryViewer-cellHistoryItemDiff">
                    <ReactDiffViewer
                      oldValue={change.previousContent}
                      newValue={change.newContent}
                      splitView={true}
                      disableWordDiff={false}
                      showDiffOnly={false}
                      useDarkTheme={document.body.dataset.jpThemeLight !== 'true'}
                    />
                  </div>
                )}
                
                {change.changeType === 'added' && change.newContent && (
                  <div className="jp-HistoryViewer-cellHistoryItemContent jp-HistoryViewer-cellHistoryItemAdded">
                    <pre className="jp-HistoryViewer-cellHistoryItemText">{change.newContent}</pre>
                  </div>
                )}
                
                {change.changeType === 'removed' && change.previousContent && (
                  <div className="jp-HistoryViewer-cellHistoryItemContent jp-HistoryViewer-cellHistoryItemRemoved">
                    <pre className="jp-HistoryViewer-cellHistoryItemText">{change.previousContent}</pre>
                  </div>
                )}
                
                {change.changeType === 'moved' && (
                  <div className="jp-HistoryViewer-cellHistoryItemMove">
                    Moved from position {change.previousIndex} to {change.newIndex}
                  </div>
                )}
                
                {version && change.newContent && (
                  <div className="jp-HistoryViewer-cellHistoryItemActions">
                    <button 
                      className="jp-HistoryViewer-actionButton jp-HistoryViewer-restoreCellButton"
                      onClick={() => handleRestoreCell(selectedCell, version.id)}
                      title="Restore this version of the cell"
                    >
                      Restore
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="jp-HistoryViewer">
      {/* Header */}
      <div className="jp-HistoryViewer-header">
        <h2 className="jp-HistoryViewer-title">Version History</h2>
        <div className="jp-HistoryViewer-controls">
          <div className="jp-HistoryViewer-viewControls">
            <button 
              className={`jp-HistoryViewer-viewButton ${viewMode === 'timeline' ? 'jp-HistoryViewer-viewButton-active' : ''}`}
              onClick={() => setViewMode('timeline')}
              title="View timeline"
            >
              Timeline
            </button>
            <button 
              className={`jp-HistoryViewer-viewButton ${viewMode === 'diff' ? 'jp-HistoryViewer-viewButton-active' : ''}`}
              onClick={() => setViewMode('diff')}
              title="Compare versions"
              disabled={!selectedVersion || !comparisonVersion}
            >
              Compare
            </button>
          </div>
          <button 
            className="jp-HistoryViewer-actionButton jp-HistoryViewer-exportButton"
            onClick={handleExportHistory}
            title="Export version history"
          >
            Export
          </button>
        </div>
      </div>
      
      {/* Filters */}
      <div className="jp-HistoryViewer-filters">
        <div className="jp-HistoryViewer-filter">
          <label className="jp-HistoryViewer-filterLabel" htmlFor="user-filter">User:</label>
          <select 
            id="user-filter"
            className="jp-HistoryViewer-filterSelect"
            value={userFilter}
            onChange={(e) => setUserFilter(e.target.value)}
          >
            <option value="">All Users</option>
            {uniqueUsers.map(user => (
              <option key={user} value={user}>{user}</option>
            ))}
          </select>
        </div>
        
        <div className="jp-HistoryViewer-filter">
          <label className="jp-HistoryViewer-filterLabel">
            <input 
              type="checkbox"
              checked={showMajorVersionsOnly}
              onChange={(e) => setShowMajorVersionsOnly(e.target.checked)}
              className="jp-HistoryViewer-filterCheckbox"
            />
            Major Versions Only
          </label>
        </div>
      </div>
      
      {/* Error message */}
      {error && (
        <div className="jp-HistoryViewer-error">
          {error}
        </div>
      )}
      
      {/* Loading indicator */}
      {loading && (
        <div className="jp-HistoryViewer-loading">
          Loading...
        </div>
      )}
      
      {/* Content based on view mode */}
      <div className="jp-HistoryViewer-content">
        {viewMode === 'timeline' && renderTimeline()}
        {viewMode === 'diff' && renderDiff()}
        {viewMode === 'cell-history' && renderCellHistory()}
      </div>
    </div>
  );
};

/**
 * A namespace for HistoryViewer statics.
 */
export namespace HistoryViewer {
  /**
   * Create a new HistoryViewer component wrapped in a ReactWidget.
   *
   * @param props - The component props.
   * @returns A new HistoryViewer widget.
   */
  export function create(props: IHistoryViewerProps): ReactWidget {
    const widget = ReactWidget.create(<HistoryViewer {...props} />);
    widget.addClass('jp-HistoryViewerWidget');
    return widget;
  }

  /**
   * Create the CSS for the HistoryViewer component.
   * 
   * @returns The CSS for the HistoryViewer component.
   */
  export function createStyle(): HTMLElement {
    const style = document.createElement('style');
    style.textContent = `
      .jp-HistoryViewer {
        display: flex;
        flex-direction: column;
        height: 100%;
        overflow: hidden;
        background-color: var(--jp-layout-color1);
        color: var(--jp-ui-font-color1);
      }

      .jp-HistoryViewer-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        border-bottom: 1px solid var(--jp-border-color1);
      }

      .jp-HistoryViewer-title {
        margin: 0;
        font-size: var(--jp-ui-font-size2);
        font-weight: 600;
      }

      .jp-HistoryViewer-controls {
        display: flex;
        align-items: center;
      }

      .jp-HistoryViewer-viewControls {
        display: flex;
        margin-right: 8px;
      }

      .jp-HistoryViewer-viewButton {
        background: none;
        border: 1px solid var(--jp-border-color1);
        padding: 4px 8px;
        font-size: var(--jp-ui-font-size1);
        cursor: pointer;
        color: var(--jp-ui-font-color1);
      }

      .jp-HistoryViewer-viewButton:first-child {
        border-radius: 3px 0 0 3px;
      }

      .jp-HistoryViewer-viewButton:last-child {
        border-radius: 0 3px 3px 0;
      }

      .jp-HistoryViewer-viewButton-active {
        background-color: var(--jp-brand-color1);
        color: var(--jp-ui-inverse-font-color1);
        border-color: var(--jp-brand-color1);
      }

      .jp-HistoryViewer-actionButton {
        background-color: var(--jp-layout-color2);
        border: 1px solid var(--jp-border-color1);
        border-radius: 3px;
        padding: 4px 8px;
        font-size: var(--jp-ui-font-size1);
        cursor: pointer;
        color: var(--jp-ui-font-color1);
      }

      .jp-HistoryViewer-actionButton:hover {
        background-color: var(--jp-layout-color3);
      }

      .jp-HistoryViewer-filters {
        display: flex;
        padding: 8px 12px;
        border-bottom: 1px solid var(--jp-border-color1);
        background-color: var(--jp-layout-color2);
      }

      .jp-HistoryViewer-filter {
        margin-right: 16px;
        display: flex;
        align-items: center;
      }

      .jp-HistoryViewer-filterLabel {
        margin-right: 8px;
        font-size: var(--jp-ui-font-size1);
        display: flex;
        align-items: center;
      }

      .jp-HistoryViewer-filterSelect {
        padding: 4px;
        border: 1px solid var(--jp-border-color1);
        border-radius: 3px;
        background-color: var(--jp-layout-color1);
        color: var(--jp-ui-font-color1);
        font-size: var(--jp-ui-font-size1);
      }

      .jp-HistoryViewer-filterCheckbox {
        margin-right: 4px;
      }

      .jp-HistoryViewer-error {
        padding: 8px 12px;
        color: var(--jp-error-color1);
        background-color: var(--jp-error-color3);
        border-bottom: 1px solid var(--jp-error-color2);
      }

      .jp-HistoryViewer-loading {
        padding: 8px 12px;
        color: var(--jp-info-color1);
        background-color: var(--jp-info-color3);
        border-bottom: 1px solid var(--jp-info-color2);
      }

      .jp-HistoryViewer-content {
        flex: 1;
        overflow: auto;
        padding: 12px;
      }

      .jp-HistoryViewer-empty {
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100%;
        color: var(--jp-ui-font-color2);
        font-style: italic;
      }

      /* Timeline View */
      .jp-HistoryViewer-timeline {
        display: flex;
        flex-direction: column;
      }

      .jp-HistoryViewer-timelineItem {
        display: flex;
        padding: 12px;
        border: 1px solid var(--jp-border-color1);
        border-radius: 4px;
        margin-bottom: 12px;
        cursor: pointer;
        transition: background-color 0.2s;
      }

      .jp-HistoryViewer-timelineItem:hover {
        background-color: var(--jp-layout-color2);
      }

      .jp-HistoryViewer-timelineItem-selected {
        background-color: var(--jp-brand-color3);
        border-color: var(--jp-brand-color1);
      }

      .jp-HistoryViewer-timelineItem-selected:hover {
        background-color: var(--jp-brand-color3);
      }

      .jp-HistoryViewer-timelineItemAvatar {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: bold;
        margin-right: 12px;
        flex-shrink: 0;
      }

      .jp-HistoryViewer-timelineItemContent {
        flex: 1;
      }

      .jp-HistoryViewer-timelineItemHeader {
        display: flex;
        justify-content: space-between;
        margin-bottom: 4px;
      }

      .jp-HistoryViewer-timelineItemAuthor {
        font-weight: bold;
      }

      .jp-HistoryViewer-timelineItemTime {
        color: var(--jp-ui-font-color2);
        font-size: var(--jp-ui-font-size0);
      }

      .jp-HistoryViewer-timelineItemDescription {
        margin-bottom: 8px;
        display: flex;
        align-items: center;
      }

      .jp-HistoryViewer-majorVersionBadge {
        background-color: var(--jp-brand-color1);
        color: white;
        font-size: var(--jp-ui-font-size0);
        padding: 2px 6px;
        border-radius: 10px;
        margin-left: 8px;
      }

      .jp-HistoryViewer-timelineItemChanges {
        margin-bottom: 8px;
      }

      .jp-HistoryViewer-changesSummary {
        font-size: var(--jp-ui-font-size0);
        color: var(--jp-ui-font-color2);
      }

      .jp-HistoryViewer-changesDetail {
        margin-top: 4px;
        display: flex;
        flex-wrap: wrap;
      }

      .jp-HistoryViewer-changeItem {
        margin-right: 8px;
        margin-bottom: 4px;
        font-size: var(--jp-ui-font-size0);
        display: flex;
        align-items: center;
      }

      .jp-HistoryViewer-changeType {
        padding: 2px 4px;
        border-radius: 3px;
        margin-right: 4px;
        font-size: var(--jp-ui-font-size0);
      }

      .jp-HistoryViewer-changeType-added {
        background-color: var(--jp-success-color3);
        color: var(--jp-success-color1);
      }

      .jp-HistoryViewer-changeType-removed {
        background-color: var(--jp-error-color3);
        color: var(--jp-error-color1);
      }

      .jp-HistoryViewer-changeType-modified {
        background-color: var(--jp-warn-color3);
        color: var(--jp-warn-color1);
      }

      .jp-HistoryViewer-changeType-moved {
        background-color: var(--jp-info-color3);
        color: var(--jp-info-color1);
      }

      .jp-HistoryViewer-cellId {
        color: var(--jp-brand-color1);
        cursor: pointer;
      }

      .jp-HistoryViewer-cellId:hover {
        text-decoration: underline;
      }

      .jp-HistoryViewer-noChanges {
        font-style: italic;
        color: var(--jp-ui-font-color2);
        font-size: var(--jp-ui-font-size0);
      }

      .jp-HistoryViewer-timelineItemActions {
        display: flex;
        justify-content: flex-end;
      }

      .jp-HistoryViewer-compareButton {
        margin-right: 8px;
      }

      /* Diff View */
      .jp-HistoryViewer-diff {
        display: flex;
        flex-direction: column;
      }

      .jp-HistoryViewer-diffHeader {
        display: flex;
        justify-content: space-between;
        margin-bottom: 16px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--jp-border-color1);
      }

      .jp-HistoryViewer-diffVersion {
        flex: 1;
      }

      .jp-HistoryViewer-diffVersionLabel {
        font-weight: bold;
        margin-bottom: 4px;
      }

      .jp-HistoryViewer-diffVersionInfo {
        display: flex;
        align-items: center;
      }

      .jp-HistoryViewer-diffVersionAuthor {
        margin-right: 8px;
      }

      .jp-HistoryViewer-diffVersionTime {
        color: var(--jp-ui-font-color2);
        font-size: var(--jp-ui-font-size0);
      }

      .jp-HistoryViewer-diffSummary {
        display: flex;
        margin-bottom: 16px;
        padding: 8px;
        background-color: var(--jp-layout-color2);
        border-radius: 4px;
      }

      .jp-HistoryViewer-diffStat {
        margin-right: 16px;
        display: flex;
        align-items: center;
      }

      .jp-HistoryViewer-diffStatLabel {
        margin-right: 4px;
        font-weight: bold;
      }

      .jp-HistoryViewer-diffStatAdded {
        color: var(--jp-success-color1);
      }

      .jp-HistoryViewer-diffStatRemoved {
        color: var(--jp-error-color1);
      }

      .jp-HistoryViewer-diffStatModified {
        color: var(--jp-warn-color1);
      }

      .jp-HistoryViewer-diffStatMoved {
        color: var(--jp-info-color1);
      }

      .jp-HistoryViewer-diffSection {
        margin-bottom: 24px;
      }

      .jp-HistoryViewer-diffSectionTitle {
        margin-top: 0;
        margin-bottom: 12px;
        font-size: var(--jp-ui-font-size2);
        font-weight: 600;
        padding-bottom: 4px;
        border-bottom: 1px solid var(--jp-border-color1);
      }

      .jp-HistoryViewer-cellDiff {
        margin-bottom: 16px;
        border: 1px solid var(--jp-border-color1);
        border-radius: 4px;
        overflow: hidden;
      }

      .jp-HistoryViewer-cellDiffHeader {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        background-color: var(--jp-layout-color2);
        border-bottom: 1px solid var(--jp-border-color1);
      }

      .jp-HistoryViewer-cellDiffInfo {
        display: flex;
        align-items: center;
      }

      .jp-HistoryViewer-cellDiffType {
        font-weight: bold;
        margin-right: 8px;
      }

      .jp-HistoryViewer-cellDiffId {
        color: var(--jp-ui-font-color2);
        margin-right: 8px;
      }

      .jp-HistoryViewer-cellDiffMove {
        font-style: italic;
        color: var(--jp-info-color1);
        font-size: var(--jp-ui-font-size0);
      }

      .jp-HistoryViewer-cellDiffActions {
        display: flex;
      }

      .jp-HistoryViewer-cellHistoryButton {
        margin-right: 8px;
      }

      .jp-HistoryViewer-cellDiffContent {
        padding: 8px;
        background-color: var(--jp-layout-color1);
        overflow: auto;
      }

      .jp-HistoryViewer-cellDiffRemoved {
        background-color: var(--jp-error-color3);
      }

      .jp-HistoryViewer-cellDiffAdded {
        background-color: var(--jp-success-color3);
      }

      .jp-HistoryViewer-cellDiffText {
        margin: 0;
        white-space: pre-wrap;
        font-family: var(--jp-code-font-family);
        font-size: var(--jp-code-font-size);
        line-height: var(--jp-code-line-height);
      }

      .jp-HistoryViewer-metadataDiff {
        display: flex;
        flex-direction: column;
      }

      .jp-HistoryViewer-metadataChange {
        margin-bottom: 12px;
        padding: 8px;
        border: 1px solid var(--jp-border-color1);
        border-radius: 4px;
      }

      .jp-HistoryViewer-metadataChangeKey {
        font-weight: bold;
        margin-bottom: 4px;
      }

      .jp-HistoryViewer-metadataChangeType {
        display: inline-block;
        padding: 2px 4px;
        border-radius: 3px;
        margin-bottom: 8px;
        font-size: var(--jp-ui-font-size0);
      }

      .jp-HistoryViewer-metadataChangeLabel {
        font-weight: bold;
        margin-bottom: 4px;
      }

      .jp-HistoryViewer-metadataChangeValue {
        margin: 0;
        padding: 8px;
        background-color: var(--jp-layout-color2);
        border-radius: 3px;
        font-family: var(--jp-code-font-family);
        font-size: var(--jp-code-font-size);
        white-space: pre-wrap;
      }

      /* Cell History View */
      .jp-HistoryViewer-cellHistory {
        display: flex;
        flex-direction: column;
      }

      .jp-HistoryViewer-cellHistoryHeader {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--jp-border-color1);
      }

      .jp-HistoryViewer-cellHistoryTitle {
        margin: 0;
        font-size: var(--jp-ui-font-size2);
        font-weight: 600;
      }

      .jp-HistoryViewer-backButton {
        background-color: var(--jp-layout-color2);
      }

      .jp-HistoryViewer-cellHistoryContent {
        display: flex;
        flex-direction: column;
      }

      .jp-HistoryViewer-cellHistoryItem {
        margin-bottom: 16px;
        border: 1px solid var(--jp-border-color1);
        border-radius: 4px;
        overflow: hidden;
      }

      .jp-HistoryViewer-cellHistoryItemHeader {
        display: flex;
        align-items: center;
        padding: 8px 12px;
        background-color: var(--jp-layout-color2);
        border-bottom: 1px solid var(--jp-border-color1);
      }

      .jp-HistoryViewer-cellHistoryItemAvatar {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: bold;
        margin-right: 8px;
        flex-shrink: 0;
      }

      .jp-HistoryViewer-cellHistoryItemInfo {
        flex: 1;
        display: flex;
        flex-direction: column;
        margin-right: 8px;
      }

      .jp-HistoryViewer-cellHistoryItemAuthor {
        font-weight: bold;
      }

      .jp-HistoryViewer-cellHistoryItemTime {
        color: var(--jp-ui-font-color2);
        font-size: var(--jp-ui-font-size0);
      }

      .jp-HistoryViewer-cellHistoryItemType {
        display: flex;
        align-items: center;
      }

      .jp-HistoryViewer-cellHistoryItemDiff {
        padding: 8px;
        background-color: var(--jp-layout-color1);
        overflow: auto;
      }

      .jp-HistoryViewer-cellHistoryItemContent {
        padding: 8px;
        background-color: var(--jp-layout-color1);
        overflow: auto;
      }

      .jp-HistoryViewer-cellHistoryItemAdded {
        background-color: var(--jp-success-color3);
      }

      .jp-HistoryViewer-cellHistoryItemRemoved {
        background-color: var(--jp-error-color3);
      }

      .jp-HistoryViewer-cellHistoryItemText {
        margin: 0;
        white-space: pre-wrap;
        font-family: var(--jp-code-font-family);
        font-size: var(--jp-code-font-size);
        line-height: var(--jp-code-line-height);
      }

      .jp-HistoryViewer-cellHistoryItemMove {
        padding: 8px;
        font-style: italic;
        color: var(--jp-info-color1);
      }

      .jp-HistoryViewer-cellHistoryItemActions {
        padding: 8px;
        display: flex;
        justify-content: flex-end;
        border-top: 1px solid var(--jp-border-color1);
        background-color: var(--jp-layout-color2);
      }
    `;
    return style;
  }
}
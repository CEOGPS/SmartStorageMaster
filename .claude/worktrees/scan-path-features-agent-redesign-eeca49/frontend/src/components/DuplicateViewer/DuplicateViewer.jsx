import React, { useState, useEffect } from 'react';
import './DuplicateViewer.css';
import { getDuplicates, selectForCleanup } from '../../services/api';

/**
 * DuplicateViewer Component
 * Displays and manages duplicate files with selection for cleanup
 */
export default function DuplicateViewer() {
  const [duplicates, setDuplicates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [filterType, setFilterType] = useState('all');
  const [sortBy, setSortBy] = useState('size');

  useEffect(() => {
    loadDuplicates();
  }, [filterType]);

  const loadDuplicates = async () => {
    try {
      setLoading(true);
      const data = await getDuplicates(filterType);
      setDuplicates(data);
    } catch (error) {
      console.error('Failed to load duplicates:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelectFile = (fileId) => {
    const newSelected = new Set(selected);
    if (newSelected.has(fileId)) {
      newSelected.delete(fileId);
    } else {
      newSelected.add(fileId);
    }
    setSelected(newSelected);
  };

  const toggleSelectGroup = (groupId) => {
    const newSelected = new Set(selected);
    const group = duplicates.find((g) => g.id === groupId);
    if (!group) return;

    // Toggle all files in group except the primary one
    group.files.forEach((file) => {
      if (!file.isPrimary) {
        if (newSelected.has(file.id)) {
          newSelected.delete(file.id);
        } else {
          newSelected.add(file.id);
        }
      }
    });
    setSelected(newSelected);
  };

  const handleCleanup = async () => {
    if (selected.size === 0) {
      alert('No files selected');
      return;
    }

    if (!confirm(`Delete ${selected.size} files?`)) {
      return;
    }

    try {
      await selectForCleanup(Array.from(selected));
      alert('Files marked for cleanup');
      setSelected(new Set());
      loadDuplicates();
    } catch (error) {
      console.error('Cleanup failed:', error);
      alert('Cleanup failed: ' + error.message);
    }
  };

  const totalSize = Array.from(selected).reduce((sum, fileId) => {
    let size = 0;
    duplicates.forEach((group) => {
      group.files.forEach((file) => {
        if (file.id === fileId) size = file.size;
      });
    });
    return sum + size;
  }, 0);

  if (loading) {
    return <div className="duplicate-viewer-loading">Loading duplicates...</div>;
  }

  return (
    <div className="duplicate-viewer">
      <div className="viewer-header">
        <h2>🔍 Duplicate Files</h2>
        <div className="header-controls">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Duplicates</option>
            <option value="images">Images Only</option>
            <option value="videos">Videos Only</option>
            <option value="documents">Documents Only</option>
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="sort-select"
          >
            <option value="size">Sort by Size</option>
            <option value="name">Sort by Name</option>
            <option value="date">Sort by Date</option>
            <option value="count">Sort by Count</option>
          </select>
        </div>
      </div>

      <div className="viewer-content">
        {duplicates.length === 0 ? (
          <div className="no-duplicates">
            <p>✨ No duplicates found!</p>
            <small>Your storage is clean</small>
          </div>
        ) : (
          <>
            {duplicates.map((group) => (
              <div key={group.id} className="duplicate-group">
                <div className="group-header">
                  <div className="group-info">
                    <label className="select-checkbox">
                      <input
                        type="checkbox"
                        onChange={() => toggleSelectGroup(group.id)}
                      />
                      <span>Select all duplicates</span>
                    </label>
                    <span className="group-summary">
                      {group.files.length} files • {group.totalSizeFormatted}
                    </span>
                  </div>
                  <span className="group-type">{group.type}</span>
                </div>

                <div className="files-list">
                  {group.files.map((file) => (
                    <div
                      key={file.id}
                      className={`file-item ${
                        file.isPrimary ? 'primary' : ''
                      } ${selected.has(file.id) ? 'selected' : ''}`}
                    >
                      <label className="file-checkbox">
                        <input
                          type="checkbox"
                          checked={selected.has(file.id)}
                          onChange={() => toggleSelectFile(file.id)}
                          disabled={file.isPrimary}
                        />
                        <span className="checkbox-custom"></span>
                      </label>

                      <div className="file-details">
                        <div className="file-name">
                          {file.name}
                          {file.isPrimary && (
                            <span className="badge primary-badge">
                              Primary
                            </span>
                          )}
                        </div>
                        <div className="file-meta">
                          <span className="meta-item">{file.sizeFormatted}</span>
                          <span className="meta-item">
                            Modified: {file.modifiedDate}
                          </span>
                          <span className="meta-item truncate">
                            {file.path}
                          </span>
                        </div>
                      </div>

                      <div className="file-actions">
                        <button className="action-icon" title="Preview">
                          👁️
                        </button>
                        <button className="action-icon" title="Open">
                          📂
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      {duplicates.length > 0 && (
        <div className="viewer-footer">
          <div className="selection-info">
            <span className="count">
              {selected.size} file{selected.size !== 1 ? 's' : ''} selected
            </span>
            <span className="saving">
              Will save: <strong>{formatBytes(totalSize)}</strong>
            </span>
          </div>
          <button
            className="cleanup-btn"
            onClick={handleCleanup}
            disabled={selected.size === 0}
          >
            🗑️ Delete Selected ({selected.size})
          </button>
        </div>
      )}
    </div>
  );
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

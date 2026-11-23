import React, { useState, useEffect } from 'react';
import './CleanupManager.css';
import { getBackups, restoreFile, clearBackups } from '../../services/api';

/**
 * CleanupManager Component
 * Manages backup, restore, and cleanup operations
 */
export default function CleanupManager() {
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    loadBackups();
  }, []);

  const loadBackups = async () => {
    try {
      setLoading(true);
      const data = await getBackups();
      setBackups(data.files);
      setStats(data.stats);
    } catch (error) {
      console.error('Failed to load backups:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = async (backupId) => {
    if (!confirm('Restore this file to its original location?')) return;

    try {
      await restoreFile(backupId);
      alert('File restored successfully');
      loadBackups();
    } catch (error) {
      console.error('Restore failed:', error);
      alert('Restore failed: ' + error.message);
    }
  };

  const handleClearOldBackups = async () => {
    const days = prompt('Delete backups older than (days):', '30');
    if (days === null) return;

    try {
      await clearBackups(parseInt(days));
      alert('Old backups cleared');
      loadBackups();
    } catch (error) {
      console.error('Clear failed:', error);
      alert('Clear failed: ' + error.message);
    }
  };

  const filteredBackups = backups.filter((backup) => {
    if (filter === 'all') return true;
    const ext = backup.originalPath.split('.').pop().toLowerCase();
    if (filter === 'images')
      return ['jpg', 'png', 'gif', 'webp'].includes(ext);
    if (filter === 'videos')
      return ['mp4', 'avi', 'mkv', 'mov'].includes(ext);
    if (filter === 'documents')
      return ['pdf', 'doc', 'docx', 'xls', 'xlsx'].includes(ext);
    return true;
  });

  if (loading) {
    return <div className="cleanup-loading">Loading backups...</div>;
  }

  return (
    <div className="cleanup-manager">
      <div className="manager-header">
        <h2>🗑️ Cleanup & Backups</h2>
        <button className="refresh-btn" onClick={loadBackups}>
          Refresh
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="cleanup-stats">
          <div className="stat-card">
            <span className="stat-label">Backed-up Files</span>
            <span className="stat-value">{stats.backupCount}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Backup Storage</span>
            <span className="stat-value">{stats.totalSizeFormatted}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Space Freed</span>
            <span className="stat-value highlight">{stats.spaceFreeFormatted}</span>
          </div>
        </div>
      )}

      <div className="manager-content">
        <div className="content-header">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Files</option>
            <option value="images">Images</option>
            <option value="videos">Videos</option>
            <option value="documents">Documents</option>
          </select>

          <div className="action-buttons">
            <button
              className="action-btn secondary"
              onClick={handleClearOldBackups}
            >
              🧹 Clear Old Backups
            </button>
            <button className="action-btn danger">
              ⚠️ Permanently Delete All
            </button>
          </div>
        </div>

        {filteredBackups.length === 0 ? (
          <div className="no-backups">
            <p>📦 No backed-up files</p>
            <small>Files you delete will appear here</small>
          </div>
        ) : (
          <div className="backups-list">
            {filteredBackups.map((backup) => (
              <div key={backup.id} className="backup-item">
                <div className="backup-icon">
                  {getFileIcon(backup.originalPath)}
                </div>

                <div className="backup-details">
                  <div className="backup-name">
                    {backup.originalPath.split('/').pop() ||
                      backup.originalPath.split('\\').pop()}
                  </div>
                  <div className="backup-meta">
                    <span className="meta-item">{backup.sizeFormatted}</span>
                    <span className="meta-item">
                      Deleted: {backup.backedUpAt}
                    </span>
                    {backup.restored && (
                      <span className="meta-item restored-badge">Restored</span>
                    )}
                  </div>
                  <div className="backup-path">
                    <span className="path-label">Original:</span>
                    <span className="path-value">{backup.originalPath}</span>
                  </div>
                </div>

                <div className="backup-actions">
                  {!backup.restored && (
                    <button
                      className="restore-btn"
                      onClick={() => handleRestore(backup.id)}
                    >
                      ↩️ Restore
                    </button>
                  )}
                  <button className="delete-btn">🗑️</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Safety Info */}
      <div className="safety-info">
        <p>
          💡 <strong>Tip:</strong> Backed-up files are stored in a safe
          location and can be restored anytime. They will be permanently deleted
          after 30 days of inactivity.
        </p>
      </div>
    </div>
  );
}

function getFileIcon(path) {
  const ext = path.split('.').pop().toLowerCase();
  const icons = {
    jpg: '🖼️',
    png: '🖼️',
    gif: '🖼️',
    webp: '🖼️',
    mp4: '🎬',
    avi: '🎬',
    mkv: '🎬',
    pdf: '📄',
    doc: '📄',
    docx: '📄',
    xls: '📊',
    xlsx: '📊',
    zip: '📦',
    exe: '⚙️',
  };
  return icons[ext] || '📁';
}

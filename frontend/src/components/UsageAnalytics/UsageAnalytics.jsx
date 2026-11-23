import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './UsageAnalytics.css';
import { getUsageSummary, getUsageRecommendations, selectForCleanup, backupFiles } from '../../services/api';
import ConfirmModal from '../UI/ConfirmModal';

/**
 * Usage Analytics Component
 * Displays file usage patterns and cleanup recommendations
 */
export default function UsageAnalytics({ showRecommendations = false }) {
  const [summary, setSummary] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterPriority, setFilterPriority] = useState(0.7);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);
  const navigate = useNavigate();
  const [confirmVisible, setConfirmVisible] = useState(false);
  const [confirmTarget, setConfirmTarget] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [selectAll, setSelectAll] = useState(false);
  const [bulkActionType, setBulkActionType] = useState(null); // 'stage' | 'backup'

  useEffect(() => {
    loadUsageData();
  }, [showRecommendations, filterPriority]);

  const loadUsageData = async () => {
    try {
      setLoading(true);
      const summaryData = await getUsageSummary();
      setSummary(summaryData);

      if (showRecommendations) {
        const recsData = await getUsageRecommendations(100, filterPriority);
        setRecommendations(recsData.recommendations || []);
      }

      setError(null);
    } catch (err) {
      setError('Failed to load usage data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="usage-loading">Loading usage data...</div>;
  }

  return (
    <div className="usage-analytics-container">
      <ConfirmModal
        visible={confirmVisible}
        title={
          bulkActionType
            ? (bulkActionType === 'stage' ? 'Stage selected files for cleanup?' : 'Backup selected files?')
            : (confirmTarget ? 'Stage file for cleanup?' : 'Stage file for cleanup?')
        }
        message={
          bulkActionType
            ? (bulkActionType === 'stage' ? `Stage ${selectedIds.size} files for cleanup?` : `Backup ${selectedIds.size} files before cleanup?`)
            : (confirmTarget ? `${confirmTarget.path}\n\nReason: ${confirmTarget.reason}` : '')
        }
        confirmLabel={bulkActionType ? (bulkActionType === 'stage' ? 'Stage' : 'Backup') : 'Stage'}
        cancelLabel="Cancel"
        loading={actionLoading}
        onCancel={() => { setConfirmVisible(false); setConfirmTarget(null); setBulkActionType(null); }}
        onConfirm={async () => {
          try {
            setActionLoading(true);
            if (bulkActionType) {
              const ids = Array.from(selectedIds);
              if (bulkActionType === 'stage') {
                await selectForCleanup(ids);
              } else {
                await backupFiles(ids);
              }
              setActionMessage('✓ Action completed');
              setTimeout(() => setActionMessage(null), 2500);
              setSelectedIds(new Set());
              setSelectAll(false);
              setBulkActionType(null);
              setConfirmVisible(false);
              navigate('/cleanup');
            } else if (confirmTarget) {
              await selectForCleanup([confirmTarget.id]);
              setActionMessage('✓ Sent to cleanup staging');
              setTimeout(() => setActionMessage(null), 2500);
              setConfirmVisible(false);
              setConfirmTarget(null);
              navigate('/cleanup');
            }
          } catch (err) {
            console.error('Confirm action failed', err);
            setActionMessage('Action failed');
            setTimeout(() => setActionMessage(null), 3000);
          } finally {
            setActionLoading(false);
          }
        }}
      />
      {error && <div className="error-message">{error}</div>}

      {!showRecommendations && summary && (
        <div className="usage-grid">
          {/* Category Breakdown */}
          <div className="usage-card">
            <h2>📊 File Categories</h2>
            <div className="category-breakdown">
              <div className="category-item">
                <div className="category-header">
                  <span className="category-name">Recently Used</span>
                  <span className="category-count">
                    {summary.summary?.RECENTLY_USED?.count || 0} files
                  </span>
                </div>
                <div className="category-bar">
                  <div className="bar-fill recently-used"></div>
                </div>
                <div className="category-size">
                  {((summary.summary?.RECENTLY_USED?.size_mb || 0) / 1024).toFixed(2)} GB
                </div>
              </div>

              <div className="category-item">
                <div className="category-header">
                  <span className="category-name">Rarely Used</span>
                  <span className="category-count">
                    {summary.summary?.RARELY_USED?.count || 0} files
                  </span>
                </div>
                <div className="category-bar">
                  <div className="bar-fill rarely-used"></div>
                </div>
                <div className="category-size">
                  {((summary.summary?.RARELY_USED?.size_mb || 0) / 1024).toFixed(2)} GB
                </div>
              </div>

              <div className="category-item">
                <div className="category-header">
                  <span className="category-name">Not Used</span>
                  <span className="category-count">
                    {summary.summary?.NOT_USED?.count || 0} files
                  </span>
                </div>
                <div className="category-bar">
                  <div className="bar-fill not-used"></div>
                </div>
                <div className="category-size">
                  {((summary.summary?.NOT_USED?.size_mb || 0) / 1024).toFixed(2)} GB
                </div>
              </div>
            </div>
          </div>

          {/* Cleanup Potential */}
          <div className="usage-card highlight">
            <h2>💾 Cleanup Potential</h2>
            <div className="cleanup-stats">
              <div className="cleanup-main">
                <span className="cleanup-value">
                  {(summary.potential_cleanup_mb / 1024).toFixed(2)} GB
                </span>
                <span className="cleanup-label">can be freed</span>
              </div>
              <div className="cleanup-details">
                <p>Scanning identified {summary.total_files} files</p>
                <p className="cleanup-percentage">
                  {summary.potential_cleanup_mb > 0
                    ? ((summary.potential_cleanup_mb / (summary.potential_cleanup_mb + 1)) * 100).toFixed(1)
                    : 0}% of unused files can be removed
                </p>
              </div>
            </div>
          </div>

          {/* Time Analysis */}
          <div className="usage-card">
            <h2>⏱️ Time Distribution</h2>
            <div className="time-stats">
              <div className="time-item">
                <span className="time-label">Last 30 Days</span>
                <span className="time-value">
                  {summary.summary?.RECENTLY_USED?.count || 0}
                </span>
              </div>
              <div className="time-divider"></div>
              <div className="time-item">
                <span className="time-label">30-180 Days</span>
                <span className="time-value">
                  {summary.summary?.RARELY_USED?.count || 0}
                </span>
              </div>
              <div className="time-divider"></div>
              <div className="time-item">
                <span className="time-label">180+ Days</span>
                <span className="time-value">
                  {summary.summary?.NOT_USED?.count || 0}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {showRecommendations && (
        <div className="recommendations-section">
          <div className="recommendations-header">
            <h2>💡 Cleanup Recommendations</h2>
            <div className="filter-controls">
              <label htmlFor="priority-filter">Priority Threshold:</label>
              <input
                id="priority-filter"
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={filterPriority}
                onChange={(e) => setFilterPriority(parseFloat(e.target.value))}
              />
              <span className="priority-value">{filterPriority.toFixed(1)}</span>
              <div className="bulk-controls">
                <label className="select-all">
                  <input
                    type="checkbox"
                    checked={selectAll}
                    onChange={(e) => {
                      const checked = e.target.checked;
                      setSelectAll(checked);
                      if (checked) {
                        setSelectedIds(new Set(recommendations.map(r => r.id)));
                      } else {
                        setSelectedIds(new Set());
                      }
                    }}
                  />
                  Select All
                </label>
                <button
                  className="action-btn small"
                  disabled={selectedIds.size === 0}
                  onClick={() => { setBulkActionType('stage'); setConfirmVisible(true); }}
                >
                  Stage Selected
                </button>
                <button
                  className="action-btn small outline"
                  disabled={selectedIds.size === 0}
                  onClick={() => { setBulkActionType('backup'); setConfirmVisible(true); }}
                >
                  Backup Selected
                </button>
              </div>
            </div>
          </div>

          {recommendations.length === 0 ? (
            <div className="no-recommendations">
              <p>✓ No files match the cleanup criteria</p>
            </div>
          ) : (
            <div className="recommendations-list">
              {recommendations.slice(0, 50).map((rec, index) => (
                <div key={index} className="recommendation-item">
                  <label className="rec-select">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(rec.id)}
                      onChange={(e) => {
                        const next = new Set(selectedIds);
                        if (e.target.checked) next.add(rec.id); else next.delete(rec.id);
                        setSelectedIds(next);
                        if (next.size !== recommendations.length) setSelectAll(false);
                      }}
                    />
                  </label>
                  <div className="rec-priority-badge">
                    <span className="priority-score">
                      {(rec.priority * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="rec-details">
                    <p className="rec-path">{rec.path}</p>
                    <p className="rec-reason">{rec.reason}</p>
                    <div className="rec-meta">
                      <span className="rec-size">
                        {(rec.size_mb / 1024).toFixed(2)} GB
                      </span>
                      <span className="rec-days">
                        {rec.days_since_access} days inactive
                      </span>
                    </div>
                  </div>
                  <button
                    className="rec-action-btn"
                    onClick={() => { setConfirmTarget(rec); setConfirmVisible(true); }}
                  >
                    🗑️ Review
                  </button>
                </div>
              ))}
              <p className="rec-count">
                Showing {Math.min(50, recommendations.length)} of {recommendations.length} recommendations
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

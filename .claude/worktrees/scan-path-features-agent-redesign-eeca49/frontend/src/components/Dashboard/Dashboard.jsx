import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './Dashboard.css';
import StorageChart from '../Charts/StorageChart';
import DuplicatesSummary from '../Charts/DuplicatesSummary';
import { getStorageStats, getDuplicateStats, getUsageSummary } from '../../services/api';

/**
 * Dashboard Component
 * Displays overview of storage status, duplicates, and key metrics
 */
export default function Dashboard() {
  const [storageStats, setStorageStats] = useState(null);
  const [duplicateStats, setDuplicateStats] = useState(null);
  const [usageSummary, setUsageSummary] = useState(null);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      const storage = await getStorageStats();
      const duplicates = await getDuplicateStats();
      const usage = await getUsageSummary();
      setStorageStats(storage);
      setDuplicateStats(duplicates);
      setUsageSummary(usage);
      setError(null);
    } catch (err) {
      setError('Failed to load dashboard data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="dashboard-loading">Loading dashboard...</div>;
  }

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <h1>Storage Dashboard</h1>
        <button className="refresh-btn" onClick={loadDashboardData}>
          Refresh
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="dashboard-grid">
        {/* Storage Overview */}
        <div className="dashboard-card">
          <h2>Storage Overview</h2>
          {storageStats && (
            <div className="stats-content">
              <StorageChart data={storageStats} />
              <div className="stats-details">
                <div className="stat-item">
                  <span className="stat-label">Total Used:</span>
                  <span className="stat-value">{storageStats.totalFormatted}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Available:</span>
                  <span className="stat-value">{storageStats.availableFormatted}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Files Scanned:</span>
                  <span className="stat-value">{storageStats.fileCount}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Usage Summary */}
        <div className="dashboard-card">
          <h2>Usage Analysis</h2>
          {usageSummary ? (
            <div className="usage-summary">
              <div className="stat-item">
                <span className="stat-label">Potential Cleanup</span>
                <span className="stat-value">{(usageSummary.potential_cleanup_mb/1024).toFixed(2)} GB</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Not Used</span>
                <span className="stat-value">{usageSummary.summary?.NOT_USED?.count || 0} files</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Rarely Used</span>
                <span className="stat-value">{usageSummary.summary?.RARELY_USED?.count || 0} files</span>
              </div>
            </div>
          ) : (
            <div>Loading usage summary...</div>
          )}
        </div>

        {/* Duplicates Summary */}
        <div className="dashboard-card">
          <h2>Duplicates Found</h2>
          {duplicateStats && (
            <div className="stats-content">
              <DuplicatesSummary data={duplicateStats} />
              <div className="stats-details">
                <div className="stat-item">
                  <span className="stat-label">Duplicate Groups:</span>
                  <span className="stat-value">{duplicateStats.groupCount}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Redundant Files:</span>
                  <span className="stat-value">{duplicateStats.fileCount}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Can Save:</span>
                  <span className="stat-value highlight">{duplicateStats.savingFormatted}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Quick Actions */}
        <div className="dashboard-card full-width">
          <h2>Quick Actions</h2>
          <div className="quick-actions">
            <button className="action-btn primary" onClick={() => navigate('/scan')}>
              <span className="icon">📁</span>
              Start New Scan
            </button>
            <button className="action-btn" onClick={() => navigate('/duplicates')}>
              <span className="icon">🔍</span>
              Find Duplicates
            </button>
            <button className="action-btn" onClick={() => navigate('/cleanup')}>
              <span className="icon">🗑️</span>
              Clean Up
            </button>
            <button className="action-btn" onClick={() => navigate('/settings')}>
              <span className="icon">⚙️</span>
              Settings
            </button>
          </div>
        </div>

        {/* Recent Activity */}
        <div className="dashboard-card full-width">
          <h2>Recent Activity</h2>
          <div className="activity-list">
            <div className="activity-item">
              <span className="time">2 hours ago</span>
              <span className="action">Scan completed: 15,243 files found</span>
            </div>
            <div className="activity-item">
              <span className="time">1 day ago</span>
              <span className="action">Cleaned up 234 MB of duplicates</span>
            </div>
            <div className="activity-item">
              <span className="time">3 days ago</span>
              <span className="action">System backup created</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

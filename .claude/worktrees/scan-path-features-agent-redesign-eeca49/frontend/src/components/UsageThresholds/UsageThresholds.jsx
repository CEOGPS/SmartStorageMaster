import React, { useState, useEffect } from 'react';
import './UsageThresholds.css';
import { getUsageThresholds, updateUsageThresholds } from '../../services/api';

/**
 * Usage Thresholds Component
 * Configure file usage analysis thresholds
 */
export default function UsageThresholds() {
  const [thresholds, setThresholds] = useState({
    recently_used_days: 30,
    rarely_used_days: 180,
    not_used_days: 180,
    min_priority_size_mb: 100,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    loadThresholds();
  }, []);

  const loadThresholds = async () => {
    try {
      setLoading(true);
      const data = await getUsageThresholds();
      setThresholds(data);
      setError(null);
    } catch (err) {
      setError('Failed to load thresholds');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (key, value) => {
    setThresholds(prev => ({
      ...prev,
      [key]: parseInt(value),
    }));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await updateUsageThresholds(thresholds);
      setSuccess('✓ Thresholds updated successfully');
      setTimeout(() => setSuccess(null), 3000);
      setError(null);
    } catch (err) {
      setError('Failed to save thresholds');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="threshold-loading">Loading thresholds...</div>;
  }

  return (
    <div className="usage-thresholds-container">
      <div className="threshold-card">
        <h2>⚙️ File Usage Categories</h2>
        <p className="card-description">
          Define how files are categorized based on the number of days since they were last accessed.
        </p>

        <div className="threshold-grid">
          <div className="threshold-item">
            <div className="threshold-header">
              <h3>Recently Used</h3>
              <span className="category-badge recent">Active</span>
            </div>
            <p className="threshold-desc">Files accessed within the last N days</p>
            <div className="threshold-input-group">
              <label htmlFor="recently-used">Days Since Access</label>
              <input
                id="recently-used"
                type="number"
                value={thresholds.recently_used_days}
                onChange={(e) => handleChange('recently_used_days', e.target.value)}
                min="1"
                max="90"
              />
              <span className="unit">days</span>
            </div>
            <div className="example-text">
              Example: Files accessed in the last {thresholds.recently_used_days} days
            </div>
          </div>

          <div className="threshold-item">
            <div className="threshold-header">
              <h3>Rarely Used</h3>
              <span className="category-badge rare">Infrequent</span>
            </div>
            <p className="threshold-desc">Files accessed between Recently Used and Not Used</p>
            <div className="threshold-input-group">
              <label htmlFor="rarely-used">Days Since Access</label>
              <input
                id="rarely-used"
                type="number"
                value={thresholds.rarely_used_days}
                onChange={(e) => handleChange('rarely_used_days', e.target.value)}
                min={thresholds.recently_used_days}
                max="365"
              />
              <span className="unit">days</span>
            </div>
            <div className="example-text">
              Example: Files accessed {thresholds.recently_used_days}+ to {thresholds.rarely_used_days} days ago
            </div>
          </div>

          <div className="threshold-item">
            <div className="threshold-header">
              <h3>Not Used</h3>
              <span className="category-badge notused">Inactive</span>
            </div>
            <p className="threshold-desc">Files not accessed for N or more days</p>
            <div className="threshold-input-group">
              <label htmlFor="not-used">Days Since Access</label>
              <input
                id="not-used"
                type="number"
                value={thresholds.not_used_days}
                onChange={(e) => handleChange('not_used_days', e.target.value)}
                min={thresholds.rarely_used_days}
                max="1095"
              />
              <span className="unit">days</span>
            </div>
            <div className="example-text">
              Example: Files not accessed for {thresholds.not_used_days}+ days
            </div>
          </div>
        </div>
      </div>

      <div className="threshold-card">
        <h2>🎯 Cleanup Priority Settings</h2>
        <p className="card-description">
          Configure which files should be prioritized for cleanup recommendations.
        </p>

        <div className="priority-settings">
          <div className="priority-item">
            <label htmlFor="min-priority">Minimum File Size for Cleanup (MB)</label>
            <p className="item-desc">Only files larger than this size will appear in cleanup recommendations</p>
            <div className="input-with-unit">
              <input
                id="min-priority"
                type="number"
                value={thresholds.min_priority_size_mb}
                onChange={(e) => handleChange('min_priority_size_mb', e.target.value)}
                min="10"
                max="1000"
              />
              <span className="unit">MB</span>
            </div>
            <div className="priority-hint">
              This helps focus on larger files that can free up significant space.
            </div>
          </div>
        </div>
      </div>

      <div className="threshold-preview">
        <h3>📊 Current Categorization Logic</h3>
        <div className="logic-flow">
          <div className="logic-step">
            <span className="step-icon">1️⃣</span>
            <div className="step-content">
              <strong>RECENTLY_USED</strong>
              <p>Last access: 0 - {thresholds.recently_used_days} days ago</p>
            </div>
          </div>
          <div className="arrow">↓</div>
          <div className="logic-step">
            <span className="step-icon">2️⃣</span>
            <div className="step-content">
              <strong>RARELY_USED</strong>
              <p>Last access: {thresholds.recently_used_days} - {thresholds.rarely_used_days} days ago</p>
            </div>
          </div>
          <div className="arrow">↓</div>
          <div className="logic-step">
            <span className="step-icon">3️⃣</span>
            <div className="step-content">
              <strong>NOT_USED</strong>
              <p>Last access: {thresholds.not_used_days}+ days ago</p>
            </div>
          </div>
        </div>
      </div>

      <div className="threshold-actions">
        {error && <div className="error-message">{error}</div>}
        {success && <div className="success-message">{success}</div>}
        <button
          className="btn-save"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? '💾 Saving...' : '💾 Save Thresholds'}
        </button>
        <button className="btn-reset" onClick={loadThresholds}>
          ↺ Reset
        </button>
      </div>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import './Settings.css';
import { getUsageThresholds, updateUsageThresholds } from '../services/api';
import { setTheme, getTheme } from '../utils/theme';
import ProtectedFolders from '../components/ProtectedFolders/ProtectedFolders';

/**
 * Settings Page
 * Application configuration
 */
export default function Settings() {
  const [settings, setSettings] = useState({
    autoScan: false,
    autoDelete: false,
    backupDays: 30,
    batchSize: 500,
    theme: 'light',
  });

  const [saved, setSaved] = useState(false);
  const [loadingThresholds, setLoadingThresholds] = useState(false);
  const [theme, setThemeState] = useState(getTheme());

  const handleChange = (key, value) => {
    setSettings(prev => ({
      ...prev,
      [key]: value,
    }));
    setSaved(false);
  };

  const handleSave = async () => {
    try {
      // Save general settings (placeholder for future API)
      setSaved(true);
      // Save usage thresholds if present
      if (
        settings.recentlyUsedDays ||
        settings.rarelyUsedDays ||
        settings.notUsedDays ||
        settings.minPrioritySizeMb
      ) {
        const payload = {
          recently_used_days: settings.recentlyUsedDays,
          rarely_used_days: settings.rarelyUsedDays,
          not_used_days: settings.notUsedDays,
          min_priority_size_mb: settings.minPrioritySizeMb,
        };
        try {
          setLoadingThresholds(true);
          await updateUsageThresholds(payload);
        } finally {
          setLoadingThresholds(false);
        }
      }
      setTimeout(() => setSaved(false), 3000);
    } catch (error) {
      console.error('Failed to save settings:', error);
    }
  };

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        setLoadingThresholds(true);
        const data = await getUsageThresholds();
        if (!mounted) return;
        setSettings(prev => ({
          ...prev,
          recentlyUsedDays: data.recently_used_days,
          rarelyUsedDays: data.rarely_used_days,
          notUsedDays: data.not_used_days,
          minPrioritySizeMb: data.min_priority_size_mb,
        }));
      } catch (err) {
        console.error('Failed to load thresholds:', err);
      } finally {
        setLoadingThresholds(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    // apply theme when changed in UI
    try {
      setTheme(theme);
    } catch (e) {
      console.warn('Failed to apply theme', e);
    }
  }, [theme]);

  return (
    <div className="settings-page">
      <div className="settings-container">
        <h1>⚙️ Settings</h1>

        <div className="settings-section">
          <h2>Scanning</h2>
          <div className="setting-item">
            <label htmlFor="batch-size">Batch Size (files)</label>
            <input
              id="batch-size"
              type="number"
              value={settings.batchSize}
              onChange={(e) => handleChange('batchSize', parseInt(e.target.value))}
              min="100"
              max="2000"
            />
          </div>
        </div>

        <div className="settings-section">
          <h2>Cleanup</h2>
          <div className="setting-item">
            <label htmlFor="backup-days">Keep Backups For (days)</label>
            <input
              id="backup-days"
              type="number"
              value={settings.backupDays}
              onChange={(e) => handleChange('backupDays', parseInt(e.target.value))}
              min="7"
              max="365"
            />
          </div>
          <div className="setting-item checkbox">
            <input
              id="auto-delete"
              type="checkbox"
              checked={settings.autoDelete}
              onChange={(e) => handleChange('autoDelete', e.target.checked)}
            />
            <label htmlFor="auto-delete">Auto-delete old backups</label>
          </div>
        </div>

          <div className="settings-section">
            <h2>File Usage Analysis</h2>
            <p className="section-description">Configure thresholds for file usage categorization</p>
            <div className="setting-item">
              <label htmlFor="recently-used">Recently Used (days)</label>
              <input
                id="recently-used"
                type="number"
                value={settings.recentlyUsedDays || 30}
                onChange={(e) => handleChange('recentlyUsedDays', parseInt(e.target.value))}
                min="1"
                max="90"
              />
            </div>
            <div className="setting-item">
              <label htmlFor="rarely-used">Rarely Used (days)</label>
              <input
                id="rarely-used"
                type="number"
                value={settings.rarelyUsedDays || 180}
                onChange={(e) => handleChange('rarelyUsedDays', parseInt(e.target.value))}
                min="30"
                max="365"
              />
            </div>
            <div className="setting-item">
              <label htmlFor="not-used">Not Used (days)</label>
              <input
                id="not-used"
                type="number"
                value={settings.notUsedDays || 180}
                onChange={(e) => handleChange('notUsedDays', parseInt(e.target.value))}
                min="90"
                max="1095"
              />
            </div>
          </div>
        <div className="settings-section">
          <h2>General</h2>
          <div className="setting-item">
            <label htmlFor="theme">Theme</label>
            <div className="theme-controls">
              <label className="theme-option">
                <input
                  type="radio"
                  name="theme"
                  value="light"
                  checked={theme === 'light'}
                  onChange={() => { setThemeState('light'); handleChange('theme', 'light'); }}
                />
                Light
              </label>
              <label className="theme-option">
                <input
                  type="radio"
                  name="theme"
                  value="dark"
                  checked={theme === 'dark'}
                  onChange={() => { setThemeState('dark'); handleChange('theme', 'dark'); }}
                />
                Dark
              </label>
            </div>
          </div>
        </div>

        <ProtectedFolders />

        <div className="settings-actions">
          <button className="btn-save" onClick={handleSave}>
            💾 Save Settings
          </button>
          {saved && <p className="success-message">✓ Settings saved successfully</p>}
        </div>
      </div>
    </div>
  );
}

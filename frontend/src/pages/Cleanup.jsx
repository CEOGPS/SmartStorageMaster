import React from 'react';
import CleanupManager from '../components/CleanupManager/CleanupManager';
import './Cleanup.css';

/**
 * Cleanup Page
 * Manage backups and deleted files
 */
export default function Cleanup() {
  return (
    <div className="cleanup-page">
      <div className="cleanup-header">
        <h1>🗑️ Cleanup & Backups</h1>
        <p className="description">
          Restore deleted files from backups or permanently delete them to free up space.
        </p>
      </div>
      <CleanupManager />
    </div>
  );
}

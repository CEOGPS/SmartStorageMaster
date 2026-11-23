import React from 'react';
import DuplicateViewer from '../components/DuplicateViewer/DuplicateViewer';
import './Duplicates.css';

/**
 * Duplicates Page
 * View and manage duplicate files
 */
export default function Duplicates() {
  return (
    <div className="duplicates-page">
      <div className="duplicates-header">
        <h1>🔄 Find Duplicates</h1>
        <p className="description">
          View and manage duplicate files. Select files to delete and free up storage space.
        </p>
      </div>
      <DuplicateViewer />
    </div>
  );
}

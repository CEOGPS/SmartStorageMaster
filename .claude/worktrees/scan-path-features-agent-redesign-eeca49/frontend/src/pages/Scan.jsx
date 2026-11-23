import React from 'react';
import FileScanner from '../components/FileScanner/FileScanner';
import './Scan.css';

/**
 * Scan Page
 * File scanning interface
 */
export default function Scan() {
  return (
    <div className="scan-page">
      <div className="scan-container">
        <h1>📁 Scan Files</h1>
        <p className="description">
          Select a directory to scan for files. The scanner will analyze your storage and identify duplicates.
        </p>
        <FileScanner />
      </div>
    </div>
  );
}

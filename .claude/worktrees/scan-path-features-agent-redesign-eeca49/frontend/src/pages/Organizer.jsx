import React from 'react';
import FileOrganizer from '../components/FileOrganizer/FileOrganizer';
import './Organizer.css';

/**
 * Organizer Page
 * Browse, move, and tidy up indexed files
 */
export default function Organizer() {
  return (
    <div className="organizer-page">
      <div className="organizer-container">
        <h1>🗂️ Organize Files</h1>
        <p className="description">
          Browse your indexed files by folder or type, move them into place, and clean up empty folders left behind.
        </p>
        <FileOrganizer />
      </div>
    </div>
  );
}

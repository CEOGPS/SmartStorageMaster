import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { browseFolders } from '../../services/api';

/**
 * In-app folder picker used when the native Electron dialog is not
 * available (running the UI in a normal browser). Lists folders through the
 * backend, so it shows exactly what the scanner can see.
 */
export default function FolderPicker({ initialPath = '', onPick, onClose }) {
  const [listing, setListing] = useState({ path: '', parent: null, folders: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const open = async (path) => {
    setLoading(true);
    setError(null);
    try {
      setListing(await browseFolders(path));
    } catch (err) {
      setError(err.message);
      if (path) {
        // Fall back to the drive/home list rather than a dead end
        try {
          setListing(await browseFolders(''));
        } catch {
          /* keep the error */
        }
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    open(initialPath);
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const atRoots = !listing.path;

  // Portal to <body>: the scanner card uses backdrop-filter, which would
  // otherwise trap this position:fixed overlay inside the card.
  return createPortal(
    <div className="folder-picker-backdrop" onMouseDown={onClose}>
      <div
        className="folder-picker"
        role="dialog"
        aria-modal="true"
        aria-label="Choose a folder"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="folder-picker-head">
          <h3>Choose a folder</h3>
          <button type="button" className="folder-picker-x" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="folder-picker-crumb">
          <button
            type="button"
            disabled={atRoots}
            onClick={() => open(listing.parent || '')}
            title="Up one level"
          >
            ↑ Up
          </button>
          <span className="truncate">{listing.path || 'This computer'}</span>
        </div>

        {error && <p className="folder-picker-error">{error}</p>}

        <ul className="folder-picker-list">
          {loading && <li className="folder-picker-empty">Loading…</li>}
          {!loading && listing.folders.length === 0 && (
            <li className="folder-picker-empty">No subfolders here</li>
          )}
          {!loading &&
            listing.folders.map((f) => (
              <li key={f.path}>
                <button type="button" onClick={() => open(f.path)} title={f.path}>
                  <span aria-hidden>{f.kind === 'drive' ? '💽' : '📁'}</span>
                  <span className="truncate">{f.name}</span>
                </button>
              </li>
            ))}
          {listing.truncated && (
            <li className="folder-picker-empty">Showing the first 500 folders</li>
          )}
        </ul>

        <div className="folder-picker-foot">
          <button type="button" className="scan-btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="scan-btn primary"
            disabled={atRoots}
            onClick={() => onPick(listing.path)}
          >
            Use this folder
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

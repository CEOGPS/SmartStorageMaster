import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  listOrganizerFiles,
  listOrganizerFolders,
  createFolder,
  moveFiles,
  deleteEmptyFolders,
  deleteOrganizerFiles,
  formatBytes,
  getThumbnailUrl,
} from '../../services/api';
import './FileOrganizer.css';

// Shows the first frame of a video as a lightweight "thumbnail" without
// server-side thumbnail generation: seek a hair past 0 once metadata loads,
// since browsers don't paint a frame until something is decoded.
function VideoThumb({ fileId, name }) {
  const handleLoadedMetadata = (e) => {
    try {
      e.target.currentTime = Math.min(0.5, (e.target.duration || 1) / 4);
    } catch {
      /* ignore */
    }
  };
  return (
    <video
      className="thumb-media"
      src={getThumbnailUrl(fileId)}
      muted
      playsInline
      preload="metadata"
      onLoadedMetadata={handleLoadedMetadata}
      title={name}
    />
  );
}

const FILE_TYPES = [
  { key: 'all', label: 'All', icon: '🗂️' },
  { key: 'image', label: 'Images', icon: '🖼️' },
  { key: 'document', label: 'Documents', icon: '📝' },
  { key: 'video', label: 'Video', icon: '🎬' },
  { key: 'audio', label: 'Audio', icon: '🎵' },
  { key: 'archive', label: 'Archives', icon: '🗜️' },
  { key: 'other', label: 'Other', icon: '📦' },
];

const TYPE_ICONS = {
  image: '🖼️',
  document: '📝',
  video: '🎬',
  audio: '🎵',
  archive: '🗜️',
  other: '📦',
};

function guessType(mimeType, name) {
  if (mimeType) {
    if (mimeType.startsWith('image/')) return 'image';
    if (mimeType.startsWith('video/')) return 'video';
    if (mimeType.startsWith('audio/')) return 'audio';
    if (
      mimeType === 'application/pdf' ||
      mimeType.startsWith('text/') ||
      mimeType.includes('msword') ||
      mimeType.includes('officedocument') ||
      mimeType.includes('spreadsheet') ||
      mimeType.includes('presentation')
    ) {
      return 'document';
    }
    if (mimeType.includes('zip') || mimeType.includes('compressed')) return 'archive';
  }
  const ext = (name.split('.').pop() || '').toLowerCase();
  if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'heic'].includes(ext)) return 'image';
  if (['mp4', 'mov', 'avi', 'mkv', 'wmv', 'webm'].includes(ext)) return 'video';
  if (['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'].includes(ext)) return 'audio';
  if (['pdf', 'doc', 'docx', 'txt', 'rtf', 'xls', 'xlsx', 'ppt', 'pptx', 'csv'].includes(ext)) return 'document';
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return 'archive';
  return 'other';
}

const PAGE_SIZE = 25;

export default function FileOrganizer() {
  const [folders, setFolders] = useState([]);
  const [activeFolder, setActiveFolder] = useState('');
  const [activeType, setActiveType] = useState('all');
  const [files, setFiles] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [destination, setDestination] = useState('');
  const [newFolderName, setNewFolderName] = useState('');
  const [banner, setBanner] = useState(null); // { type: 'success'|'error', message }
  const [cleanupResult, setCleanupResult] = useState(null);
  const [viewMode, setViewMode] = useState('list'); // 'list' | 'grid'

  const showBanner = (type, message) => {
    setBanner({ type, message });
    setTimeout(() => setBanner(null), 5000);
  };

  const refreshFolders = useCallback(async () => {
    try {
      const data = await listOrganizerFolders();
      setFolders(data?.folders || []);
    } catch (err) {
      console.error('Failed to load folders:', err);
    }
  }, []);

  const refreshFiles = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listOrganizerFiles(activeFolder || undefined, activeType, PAGE_SIZE, offset);
      setFiles(data?.files || []);
      setTotal(data?.total || 0);
    } catch (err) {
      console.error('Failed to load files:', err);
      showBanner('error', `Failed to load files: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [activeFolder, activeType, offset]);

  useEffect(() => {
    refreshFolders();
  }, [refreshFolders]);

  useEffect(() => {
    refreshFiles();
  }, [refreshFiles]);

  useEffect(() => {
    setOffset(0);
    setSelected(new Set());
    setViewMode(activeType === 'image' || activeType === 'video' ? 'grid' : 'list');
  }, [activeFolder, activeType]);

  const allVisibleSelected = files.length > 0 && files.every((f) => selected.has(f.id));

  const toggleSelectAll = () => {
    const next = new Set(selected);
    if (allVisibleSelected) {
      files.forEach((f) => next.delete(f.id));
    } else {
      files.forEach((f) => next.add(f.id));
    }
    setSelected(next);
  };

  const toggleSelect = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const handleBrowseDestination = async () => {
    try {
      const api = window.electron;
      const path = api?.openFileDialog
        ? await api.openFileDialog()
        : api?.ipcRenderer?.invoke
          ? await api.ipcRenderer.invoke('select-folder')
          : null;
      if (path) setDestination(path);
    } catch (err) {
      console.error('Browse failed:', err);
    }
  };

  const handleCreateFolder = async () => {
    if (!destination || !newFolderName.trim()) return;
    const sep = destination.includes('/') && !destination.includes('\\') ? '/' : '\\';
    const fullPath = `${destination.replace(/[\\/]+$/, '')}${sep}${newFolderName.trim()}`;
    try {
      const result = await createFolder(fullPath);
      if (result?.success) {
        showBanner('success', `Created folder: ${result.path}`);
        setDestination(result.path);
        setNewFolderName('');
        await refreshFolders();
      } else {
        showBanner('error', result?.error || 'Failed to create folder');
      }
    } catch (err) {
      showBanner('error', `Failed to create folder: ${err.message}`);
    }
  };

  const handleMoveSelected = async () => {
    if (selected.size === 0 || !destination) return;
    try {
      const result = await moveFiles(Array.from(selected), destination, true);
      const prot = result.blocked?.length || 0;
      showBanner(
        result.failed > 0 ? 'error' : 'success',
        `Moved ${result.moved}/${result.total} file(s)${result.failed ? `, ${result.failed} failed` : ''}${prot ? ` (${prot} protected, left untouched)` : ''}`
      );
      setSelected(new Set());
      await Promise.all([refreshFiles(), refreshFolders()]);
    } catch (err) {
      showBanner('error', `Move failed: ${err.message}`);
    }
  };

  const handleDeleteSelected = async () => {
    if (selected.size === 0) return;
    if (!window.confirm(`Delete ${selected.size} file(s)? They will be backed up first and can be restored from Cleanup.`)) {
      return;
    }
    try {
      const result = await deleteOrganizerFiles(Array.from(selected));
      const prot = result.blocked?.length || 0;
      showBanner(
        result.failed > 0 || prot > 0 ? 'error' : 'success',
        `Deleted ${result.deleted}/${result.total} file(s)${result.failed ? `, ${result.failed} failed` : ''}${prot ? ` (${prot} protected, left untouched)` : ''}`
      );
      setSelected(new Set());
      await Promise.all([refreshFiles(), refreshFolders()]);
    } catch (err) {
      showBanner('error', `Delete failed: ${err.message}`);
    }
  };

  const handleCleanupEmptyFolders = async () => {
    let root = activeFolder;
    if (!root) {
      root = window.prompt('Enter a root folder to clean up empty subfolders under:', destination || '');
    }
    if (!root) return;
    try {
      const result = await deleteEmptyFolders(root);
      setCleanupResult(result);
      showBanner('success', `Removed ${result.count} empty folder(s)`);
      await refreshFolders();
    } catch (err) {
      showBanner('error', `Cleanup failed: ${err.message}`);
    }
  };

  const canMove = selected.size > 0 && !!destination;
  const canDelete = selected.size > 0;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="file-organizer">
      {banner && (
        <div className={`organizer-banner ${banner.type}`}>
          <span>{banner.message}</span>
          <button className="banner-dismiss" onClick={() => setBanner(null)}>×</button>
        </div>
      )}

      <div className="organizer-layout">
        <aside className="organizer-sidebar">
          <h3>File Type</h3>
          <div className="type-pills">
            {FILE_TYPES.map((t) => (
              <button
                key={t.key}
                className={`type-pill${activeType === t.key ? ' active' : ''}`}
                onClick={() => setActiveType(t.key)}
              >
                <span>{t.icon}</span> {t.label}
              </button>
            ))}
          </div>

          <h3>Folders</h3>
          <div className="folder-list">
            <button
              className={`folder-item${activeFolder === '' ? ' active' : ''}`}
              onClick={() => setActiveFolder('')}
            >
              <span className="folder-icon">🗂️</span>
              <span className="folder-name">All Folders</span>
            </button>
            {folders.length === 0 && (
              <div className="folder-empty">No indexed folders yet — run a scan first.</div>
            )}
            {folders.map((f) => (
              <button
                key={f}
                className={`folder-item${activeFolder === f ? ' active' : ''}`}
                onClick={() => setActiveFolder(f)}
                title={f}
              >
                <span className="folder-icon">📁</span>
                <span className="folder-name truncate">{f}</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="organizer-main">
          <div className="organizer-toolbar">
            <label className="select-all-label">
              <input
                type="checkbox"
                checked={allVisibleSelected}
                onChange={toggleSelectAll}
                disabled={files.length === 0}
              />
              Select all visible
            </label>
            {selected.size > 0 && <span className="selected-badge">{selected.size} selected</span>}
            <span className="file-count">{total.toLocaleString()} file(s)</span>
            <div className="view-toggle">
              <button
                className={`view-btn${viewMode === 'list' ? ' active' : ''}`}
                onClick={() => setViewMode('list')}
                title="List view"
              >
                ☰
              </button>
              <button
                className={`view-btn${viewMode === 'grid' ? ' active' : ''}`}
                onClick={() => setViewMode('grid')}
                title="Thumbnail grid"
              >
                ⊞
              </button>
            </div>
          </div>

          <div className="organizer-table-wrap">
            {loading ? (
              <div className="organizer-loading">Loading files...</div>
            ) : files.length === 0 ? (
              <div className="organizer-empty">
                <span className="empty-icon">🗃️</span>
                <p>No files match this filter.</p>
                <p className="empty-hint">Try a different folder or file type, or run a scan from the Scan page.</p>
              </div>
            ) : viewMode === 'grid' ? (
              <div className="organizer-grid">
                {files.map((f) => {
                  const type = guessType(f.mime_type, f.name);
                  const isSelected = selected.has(f.id);
                  return (
                    <div
                      key={f.id}
                      className={`grid-tile${isSelected ? ' selected' : ''}`}
                      onClick={() => toggleSelect(f.id)}
                      title={f.path}
                    >
                      <div className="grid-tile-thumb">
                        {type === 'image' ? (
                          <img className="thumb-media" src={getThumbnailUrl(f.id)} alt={f.name} loading="lazy" />
                        ) : type === 'video' ? (
                          <VideoThumb fileId={f.id} name={f.name} />
                        ) : (
                          <span className="thumb-fallback-icon">{TYPE_ICONS[type] || '📄'}</span>
                        )}
                        <input
                          type="checkbox"
                          className="grid-tile-checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(f.id)}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </div>
                      <div className="grid-tile-name truncate">{f.name}</div>
                      <div className="grid-tile-size">{formatBytes(f.size)}</div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <table className="organizer-table">
                <thead>
                  <tr>
                    <th className="organizer-checkbox-col" />
                    <th className="organizer-name-col">Name</th>
                    <th className="organizer-path-col">Path</th>
                    <th className="organizer-size-col">Size</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((f) => {
                    const type = guessType(f.mime_type, f.name);
                    return (
                      <tr key={f.id} className={selected.has(f.id) ? 'selected' : ''}>
                        <td className="organizer-checkbox-col">
                          <input
                            type="checkbox"
                            checked={selected.has(f.id)}
                            onChange={() => toggleSelect(f.id)}
                          />
                        </td>
                        <td className="file-name-cell">
                          <span className="file-type-icon">{TYPE_ICONS[type] || '📄'}</span>
                          <span className="file-name-text truncate" title={f.name}>{f.name}</span>
                        </td>
                        <td className="file-path truncate" title={f.path}>{f.path}</td>
                        <td className="file-size-cell">{formatBytes(f.size)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          <div className="organizer-pagination">
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              ← Prev
            </button>
            <span>Page {page} of {pageCount}</span>
            <button
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next →
            </button>
          </div>
        </section>

        <aside className="organizer-destination">
          <h3>Move To</h3>

          <div className="destination-current">
            <label>Destination</label>
            <div className="destination-input-row">
              <input
                type="text"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                placeholder="C:\Users\YourName\Organized"
                className="destination-input"
              />
              <button className="action-btn" onClick={handleBrowseDestination} title="Browse...">
                📂
              </button>
            </div>
          </div>

          <div className="new-folder-row">
            <input
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="New folder name"
              className="new-folder-input"
            />
            <button className="action-btn" onClick={handleCreateFolder} disabled={!destination || !newFolderName.trim()}>
              + Create
            </button>
          </div>

          <h3>Existing Folders</h3>
          <div className="destination-folder-list">
            {folders.length === 0 && (
              <div className="folder-empty">No indexed folders yet.</div>
            )}
            {folders.map((f) => (
              <button
                key={f}
                className={`destination-folder-item${destination === f ? ' active' : ''}`}
                onClick={() => setDestination(f)}
                title={f}
              >
                <span className="folder-icon">📁</span>
                <span className="folder-name truncate">{f}</span>
              </button>
            ))}
          </div>

          <div className="destination-actions">
            <button
              className="action-btn primary full-width"
              onClick={handleMoveSelected}
              disabled={!canMove}
              title={!canMove ? 'Select files and a destination first' : ''}
            >
              Move {selected.size > 0 ? `${selected.size} ` : ''}Selected
            </button>
            <button
              className="action-btn danger full-width"
              onClick={handleDeleteSelected}
              disabled={!canDelete}
              title={!canDelete ? 'Select files first' : ''}
            >
              Delete Selected
            </button>
            <button className="action-btn secondary full-width" onClick={handleCleanupEmptyFolders}>
              Clean Up Empty Folders
            </button>
          </div>

          {cleanupResult && (
            <div className="cleanup-result">
              Removed {cleanupResult.count} empty folder(s)
              {cleanupResult.removed?.length > 0 && (
                <span className="cleanup-list"> — {cleanupResult.removed.slice(0, 3).join(', ')}
                  {cleanupResult.removed.length > 3 ? '…' : ''}</span>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

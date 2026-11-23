import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  startScan,
  getScanStatistics,
  validateScanPath,
  getScanRoots,
  getScanHistory,
  getScanSummary,
  cancelScan,
  formatBytes,
} from '../../services/api';
import FolderPicker from './FolderPicker';
import './FileScanner.css';

// Scan keeps running server-side regardless of this component's lifetime;
// this key lets us reattach to it after navigating away and back.
const ACTIVE_SCAN_KEY = 'ssm.activeScan';
const OPTIONS_KEY = 'ssm.scanOptions';
const DEFAULT_OPTIONS = { recursive: true, includeHidden: false, computeHash: true };

const PHASE_LABELS = {
  starting: 'Starting…',
  indexing: 'Indexing files',
  'analyzing usage': 'Analyzing usage',
  'finding duplicates': 'Finding duplicates',
  cancelling: 'Stopping…',
};

const CATEGORY_ICONS = {
  image: '🖼️', video: '🎬', audio: '🎵', document: '📄', archive: '🗜️', program: '⚙️', other: '📦',
};

function readJson(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || 'null');
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch (err) {
    console.warn(`Could not save ${key}:`, err);
  }
}

function timeAgo(iso) {
  if (!iso) return '';
  // Backend timestamps are naive UTC
  const then = new Date(iso.endsWith('Z') ? iso : `${iso}Z`).getTime();
  const s = Math.max(0, (Date.now() - then) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

function formatDuration(seconds) {
  if (seconds == null) return '';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  return `${m}m ${Math.round(seconds % 60)}s`;
}

export default function FileScanner({ onScanStart }) {
  const navigate = useNavigate();
  const [selectedPath, setSelectedPath] = useState('');
  const [options, setOptions] = useState(() => ({ ...DEFAULT_OPTIONS, ...readJson(OPTIONS_KEY, {}) }));
  const [pathInfo, setPathInfo] = useState(null);
  const [roots, setRoots] = useState([]);
  const [history, setHistory] = useState([]);
  const [pickerOpen, setPickerOpen] = useState(false);

  const [scanId, setScanId] = useState(null);
  const [isScanning, setIsScanning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [hasProgressEvent, setHasProgressEvent] = useState(false);
  const [scanStats, setScanStats] = useState(null);
  const [scanError, setScanError] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [summary, setSummary] = useState(null);
  const [notice, setNotice] = useState(null);
  const [elapsed, setElapsed] = useState(0);

  const wsRef = useRef(null);
  const tickRef = useRef(null);
  const pollRef = useRef(null);

  const refreshHistory = useCallback(() => {
    getScanHistory(6).then(setHistory).catch(() => setHistory([]));
  }, []);

  useEffect(() => {
    getScanRoots().then(setRoots).catch(() => setRoots([]));
    refreshHistory();
  }, [refreshHistory]);

  useEffect(() => writeJson(OPTIONS_KEY, options), [options]);

  // Live validation: show the folder that will actually be scanned
  // (e.g. "D:" -> "D:\") and catch typos before starting.
  useEffect(() => {
    if (!selectedPath.trim() || isScanning) {
      setPathInfo(null);
      return undefined;
    }
    const handle = setTimeout(() => {
      validateScanPath(selectedPath).then(setPathInfo).catch(() => setPathInfo(null));
    }, 300);
    return () => clearTimeout(handle);
  }, [selectedPath, isScanning]);

  const stopWatching = () => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    clearInterval(tickRef.current);
    clearInterval(pollRef.current);
    tickRef.current = null;
    pollRef.current = null;
  };

  useEffect(() => stopWatching, []);

  const resetScanState = () => {
    writeJson(ACTIVE_SCAN_KEY, null);
    stopWatching();
    setScanId(null);
    setIsScanning(false);
    setProgress(0);
    setHasProgressEvent(false);
    setScanStats(null);
    setScanError(null);
    setScanResult(null);
    setSummary(null);
    setNotice(null);
    setElapsed(0);
  };

  // One handler for both WebSocket messages and polled status snapshots.
  const applyUpdate = (id, data) => {
    if (typeof data.percentage === 'number' && (data.total_estimated > 0 || data.percentage > 0)) {
      setProgress(data.percentage);
      setHasProgressEvent(true);
    }
    setScanStats({
      phase: data.phase || 'indexing',
      filesFound: data.files_found ?? 0,
      totalSize: data.total_size ?? 0,
      potentialSavings: data.potential_savings ?? 0,
      totalEstimated: data.total_estimated ?? 0,
      filesPerSecond: data.files_per_second ?? 0,
      hashesReused: data.hashes_reused ?? 0,
      skippedFolders: data.skipped_folders ?? 0,
      currentFolder: data.current_folder ?? '',
      currentFile: data.current_file ?? '',
    });

    const status = data.status;
    if (!['completed', 'failed', 'cancelled', 'interrupted'].includes(status)) return;

    stopWatching();
    writeJson(ACTIVE_SCAN_KEY, null);
    setIsScanning(false);
    refreshHistory();

    if (status === 'completed') {
      setProgress(100);
      setScanResult({
        status,
        filesFound: data.files_found ?? 0,
        totalSize: data.total_size ?? 0,
        potentialSavings: data.potential_savings ?? 0,
        duplicateGroups: data.duplicate_groups,
        hashesReused: data.hashes_reused ?? 0,
        filesPerSecond: data.files_per_second ?? 0,
      });
      getScanSummary(id).then(setSummary).catch(() => setSummary(null));
      if (onScanStart) onScanStart();
    } else if (status === 'cancelled') {
      setScanResult({
        status,
        filesFound: data.files_found ?? 0,
        totalSize: data.total_size ?? 0,
        potentialSavings: data.potential_savings ?? 0,
      });
    } else {
      setScanError(data.error_message || 'Scan failed for an unknown reason');
    }
  };

  // Polling fallback if the WebSocket cannot connect or drops mid-scan.
  const startPolling = (id) => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const status = await getScanStatistics(id);
        const p = status?.progress || {};
        applyUpdate(id, { ...p, status: p.status || status?.status, error_message: p.error_message || status?.error_message });
      } catch (err) {
        console.warn('Status poll failed:', err);
      }
    }, 1000);
  };

  const attachToScan = (id, path, start) => {
    stopWatching();
    setScanId(id);
    setIsScanning(true);
    setScanError(null);
    setScanResult(null);
    setSummary(null);
    writeJson(ACTIVE_SCAN_KEY, { scanId: id, path, startedAt: start });

    setElapsed((Date.now() - start) / 1000);
    tickRef.current = setInterval(() => setElapsed((Date.now() - start) / 1000), 500);

    let ws;
    try {
      ws = new WebSocket(`ws://127.0.0.1:8000/ws/scan?scan_id=${encodeURIComponent(id)}`);
    } catch {
      startPolling(id);
      return;
    }
    wsRef.current = ws;
    ws.onmessage = (event) => {
      try {
        applyUpdate(id, JSON.parse(event.data));
      } catch (err) {
        console.warn('Bad progress message:', err);
      }
    };
    ws.onerror = () => startPolling(id);
    ws.onclose = () => {
      wsRef.current = null;
      // Closed before a final status: keep following the scan by polling
      startPolling(id);
    };
  };

  // On mount (including returning to this page), reattach to a scan that is
  // still running server-side instead of showing a blank "Start" state.
  useEffect(() => {
    const saved = readJson(ACTIVE_SCAN_KEY, null);
    if (!saved?.scanId) return;
    (async () => {
      try {
        const status = await getScanStatistics(saved.scanId);
        setSelectedPath(saved.path || status?.path || '');
        if (status?.status === 'running') {
          attachToScan(saved.scanId, saved.path, saved.startedAt || Date.now());
        } else {
          applyUpdate(saved.scanId, {
            ...(status?.progress || {}),
            status: status?.status,
            error_message: status?.error_message,
          });
        }
      } catch (err) {
        console.warn('Could not reattach to saved scan:', err);
        writeJson(ACTIVE_SCAN_KEY, null);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleBrowse = async () => {
    const api = window.electron;
    if (api?.openFileDialog) {
      try {
        const path = await api.openFileDialog();
        if (path) setSelectedPath(path);
      } catch (err) {
        console.error('Browse failed:', err);
        setPickerOpen(true);
      }
      return;
    }
    setPickerOpen(true);
  };

  const handleScan = async (pathOverride) => {
    const path = (typeof pathOverride === 'string' ? pathOverride : selectedPath).trim();
    if (!path) {
      setScanError('Choose a folder to scan first.');
      return;
    }
    if (pathInfo && pathInfo.input === path && !pathInfo.is_dir) {
      setScanError(pathInfo.message);
      return;
    }

    setIsScanning(true);
    setProgress(0);
    setHasProgressEvent(false);
    setScanStats(null);
    setScanError(null);
    setScanResult(null);
    setNotice(null);

    try {
      const result = await startScan(path, options);
      if (!result?.scan_id) throw new Error('Backend did not return scan_id');
      setSelectedPath(result.path || path);
      if (result.alreadyRunning) setNotice(result.message);
      attachToScan(result.scan_id, result.path || path, Date.now());
    } catch (error) {
      console.error('Scan failed:', error);
      setIsScanning(false);
      setScanError(error.message);
    }
  };

  const handleCancel = async () => {
    if (!scanId) return;
    setScanStats((s) => (s ? { ...s, phase: 'cancelling' } : s));
    try {
      await cancelScan(scanId);
    } catch (err) {
      setNotice(`Could not stop the scan: ${err.message}`);
    }
  };

  const toggleOption = (key) => setOptions((o) => ({ ...o, [key]: !o[key] }));

  const pathHint = pathInfo && !isScanning && (
    <p className={`path-hint ${pathInfo.is_dir && pathInfo.readable ? 'ok' : 'bad'}`}>
      {pathInfo.is_dir && pathInfo.readable
        ? pathInfo.path !== pathInfo.input.trim()
          ? `Will scan ${pathInfo.path}`
          : 'Ready to scan'
        : pathInfo.message}
    </p>
  );

  const maxCategory = summary?.by_category?.[0]?.size || 1;

  return (
    <div className="file-scanner">
      <div className="scanner-header">
        <h2>📁 Scan Folders</h2>
        <p>Select a folder to scan for files and duplicates</p>
      </div>

      <div className="scanner-content">
        <div className="path-selector">
          <label htmlFor="folder-path">Select Folder:</label>
          <div className="path-input-group">
            <input
              id="folder-path"
              type="text"
              value={selectedPath}
              onChange={(e) => setSelectedPath(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !isScanning && handleScan()}
              placeholder="C:\Users\YourName\Documents"
              className="path-input"
              disabled={isScanning}
              spellCheck={false}
              autoComplete="off"
            />
            <button className="browse-btn" onClick={handleBrowse} disabled={isScanning}>
              Browse...
            </button>
          </div>
          {pathHint}
          {roots.length > 0 && !isScanning && (
            <div className="quick-picks" aria-label="Quick picks">
              {roots.map((r) => (
                <button
                  key={r.path}
                  type="button"
                  className={`quick-pick ${r.kind}`}
                  onClick={() => setSelectedPath(r.path)}
                  title={r.path}
                >
                  {r.kind === 'drive' ? '💽' : '📂'} {r.name}
                </button>
              ))}
            </div>
          )}
        </div>

        {notice && <p className="scan-notice">{notice}</p>}

        {!isScanning && !scanResult && !scanError && (
          <button className="scan-btn primary" onClick={() => handleScan()}>
            🔍 Start Scanning
          </button>
        )}

        {isScanning && (
          <div className="scanning-progress">
            <div className={`progress-bar ${hasProgressEvent ? 'determinate' : 'indeterminate'}`}>
              {hasProgressEvent ? (
                <div className="progress-fill" style={{ width: `${progress}%` }} />
              ) : (
                <div className="progress-fill-indeterminate" />
              )}
            </div>
            <div className="progress-text">
              <span className="status">
                {PHASE_LABELS[scanStats?.phase] || 'Scanning…'} {hasProgressEvent ? `${progress}%` : ''}
              </span>
              <span className="elapsed">{elapsed.toFixed(0)}s elapsed</span>
            </div>

            {scanStats && (
              <>
                <div className="scan-stat-cards">
                  <div className="stat-card">
                    <span className="stat-icon">🗂️</span>
                    <span className="stat-label">Files Found</span>
                    <span className="stat-value">
                      {scanStats.filesFound.toLocaleString()}
                      {scanStats.totalEstimated > 0 && (
                        <small> / {scanStats.totalEstimated.toLocaleString()}</small>
                      )}
                    </span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-icon">💽</span>
                    <span className="stat-label">Total Size</span>
                    <span className="stat-value">{formatBytes(scanStats.totalSize)}</span>
                  </div>
                  <div className="stat-card savings">
                    <span className="stat-icon">♻️</span>
                    <span className="stat-label">Potential Savings</span>
                    <span className="stat-value">{formatBytes(scanStats.potentialSavings)}</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-icon">⚡</span>
                    <span className="stat-label">Speed</span>
                    <span className="stat-value">{Math.round(scanStats.filesPerSecond).toLocaleString()}/s</span>
                  </div>
                </div>
                <div className="scan-meta-line">
                  {scanStats.hashesReused > 0 && (
                    <span>{scanStats.hashesReused.toLocaleString()} unchanged files skipped re-hashing</span>
                  )}
                  {scanStats.skippedFolders > 0 && (
                    <span>{scanStats.skippedFolders.toLocaleString()} folders not readable</span>
                  )}
                </div>
                <div className="scan-current-line truncate" title={scanStats.currentFolder}>
                  <span className="current-folder">{scanStats.currentFolder}</span>
                  {scanStats.currentFile && (
                    <span className="current-file"> / {scanStats.currentFile}</span>
                  )}
                </div>
              </>
            )}
            <button
              type="button"
              className="scan-btn ghost stop-btn"
              onClick={handleCancel}
              disabled={!scanId || scanStats?.phase === 'cancelling'}
            >
              ■ Stop scan
            </button>
          </div>
        )}

        {scanResult && (
          <div className={`scan-result-card ${scanResult.status === 'completed' ? 'success' : 'warn'}`}>
            <div className="result-icon">{scanResult.status === 'completed' ? '✅' : '⏹️'}</div>
            <h3>{scanResult.status === 'completed' ? 'Scan Complete' : 'Scan Stopped'}</h3>
            <div className="result-stats">
              <div className="result-stat">
                <span className="label">Files Found</span>
                <span className="value">{scanResult.filesFound.toLocaleString()}</span>
              </div>
              <div className="result-stat">
                <span className="label">Total Size</span>
                <span className="value">{formatBytes(scanResult.totalSize)}</span>
              </div>
              <div className="result-stat">
                <span className="label">Potential Savings</span>
                <span className="value">{formatBytes(scanResult.potentialSavings)}</span>
              </div>
              {scanResult.duplicateGroups != null && (
                <div className="result-stat">
                  <span className="label">Duplicate Groups</span>
                  <span className="value">{scanResult.duplicateGroups.toLocaleString()}</span>
                </div>
              )}
            </div>

            {summary?.by_category?.length > 0 && (
              <div className="result-breakdown">
                <h4>Where the space goes</h4>
                {summary.by_category.map((c) => (
                  <div className="breakdown-row" key={c.category}>
                    <span className="breakdown-label">
                      {CATEGORY_ICONS[c.category] || '📦'} {c.category}
                    </span>
                    <span className="breakdown-bar">
                      <span style={{ width: `${Math.max(2, (c.size / maxCategory) * 100)}%` }} />
                    </span>
                    <span className="breakdown-value">
                      {formatBytes(c.size)} · {c.count.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {summary?.largest_files?.length > 0 && (
              <div className="result-largest">
                <h4>Largest files</h4>
                <ul>
                  {summary.largest_files.map((f) => (
                    <li key={f.id} title={f.path}>
                      <span className="truncate">{f.name}</span>
                      <span>{f.size_formatted}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="result-actions">
              <button className="scan-btn primary" onClick={() => navigate('/duplicates')}>
                🔄 View Duplicates
              </button>
              <button className="scan-btn secondary" onClick={() => navigate('/organizer')}>
                🗂️ Open Organizer
              </button>
              <button className="scan-btn ghost" onClick={resetScanState}>
                Scan Another Folder
              </button>
            </div>
          </div>
        )}

        {scanError && (
          <div className="scan-result-card error">
            <div className="result-icon">⚠️</div>
            <h3>Scan Failed</h3>
            <p className="error-message">{scanError}</p>
            <div className="result-actions">
              <button className="scan-btn primary" onClick={resetScanState}>
                Try Again
              </button>
            </div>
          </div>
        )}

        <div className="scan-options">
          <h3>Scan Options</h3>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={options.includeHidden}
              onChange={() => toggleOption('includeHidden')}
              disabled={isScanning}
            />
            <span>Include hidden files</span>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={options.recursive}
              onChange={() => toggleOption('recursive')}
              disabled={isScanning}
            />
            <span>Scan subfolders recursively</span>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={options.computeHash}
              onChange={() => toggleOption('computeHash')}
              disabled={isScanning}
            />
            <span>Calculate file hashes (needed for exact duplicates)</span>
          </label>
        </div>

        <div className="recent-scans">
          <h3>Recent Scans</h3>
          <div className="recent-list">
            {history.length === 0 && <p className="recent-empty">No scans yet.</p>}
            {history.map((h) => (
              <button
                type="button"
                className="recent-item"
                key={h.id}
                onClick={() => !isScanning && setSelectedPath(h.path)}
                disabled={isScanning}
                title="Use this folder"
              >
                <span className="path truncate">{h.path}</span>
                <span className={`recent-status ${h.status}`}>{h.status}</span>
                <span className="time">
                  {h.total_files ? `${h.total_files.toLocaleString()} files · ${h.total_size_formatted}` : ''}
                  {h.duration_seconds != null ? ` · ${formatDuration(h.duration_seconds)}` : ''}
                  {` · ${timeAgo(h.started_at)}`}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {pickerOpen && (
        <FolderPicker
          initialPath={pathInfo?.is_dir ? pathInfo.path : ''}
          onClose={() => setPickerOpen(false)}
          onPick={(path) => {
            setSelectedPath(path);
            setPickerOpen(false);
          }}
        />
      )}
    </div>
  );
}

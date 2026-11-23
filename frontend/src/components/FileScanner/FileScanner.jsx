import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { startScan, getScanStatistics, formatBytes } from '../../services/api';
import './FileScanner.css';

// Scan keeps running server-side regardless of this component's lifetime;
// this key lets us reattach to it after navigating away and back.
const ACTIVE_SCAN_KEY = 'ssm.activeScan';

export default function FileScanner({ onScanStart }) {
  const navigate = useNavigate();
  const [selectedPath, setSelectedPath] = useState('');
  const [isScanning, setIsScanning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [hasProgressEvent, setHasProgressEvent] = useState(false);
  const [scanStats, setScanStats] = useState(null);
  const [scanError, setScanError] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [startedAt, setStartedAt] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const wsRef = useRef(null);
  const tickRef = useRef(null);

  const handlePathChange = (e) => setSelectedPath(e.target.value);

  const handleBrowse = async () => {
    try {
      const api = window.electron;
      const path = api?.openFileDialog
        ? await api.openFileDialog()
        : api?.ipcRenderer?.invoke
          ? await api.ipcRenderer.invoke('select-folder')
          : null;
      if (path) setSelectedPath(path);
    } catch (err) {
      console.error('Browse failed:', err);
    }
  };

  const clearActiveScan = () => {
    try {
      localStorage.removeItem(ACTIVE_SCAN_KEY);
    } catch (err) {
      console.warn('Could not clear active scan from storage:', err);
    }
  };

  const resetScanState = () => {
    clearActiveScan();
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    setIsScanning(false);
    setProgress(0);
    setHasProgressEvent(false);
    setScanStats(null);
    setScanError(null);
    setScanResult(null);
    setStartedAt(null);
    setElapsed(0);
  };

  // Opens (or reopens, after navigating back) the WebSocket that streams
  // progress for a scan the backend is already running, and keeps the
  // scan_id in localStorage so it survives this component unmounting.
  const attachToScan = (scanId, path, start) => {
    setIsScanning(true);
    setScanError(null);
    setScanResult(null);
    setStartedAt(start);

    try {
      localStorage.setItem(
        ACTIVE_SCAN_KEY,
        JSON.stringify({ scanId, path, startedAt: start })
      );
    } catch (err) {
      console.warn('Could not persist active scan to storage:', err);
    }

    if (tickRef.current) clearInterval(tickRef.current);
    tickRef.current = setInterval(() => setElapsed((Date.now() - start) / 1000), 500);

    const ws = new WebSocket(`ws://127.0.0.1:8000/ws/scan?scan_id=${scanId}`);
    wsRef.current = ws;
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (typeof data.percentage === 'number') {
        setProgress(data.percentage);
        setHasProgressEvent(true);
      }
      setScanStats({
        filesFound: data.files_found ?? 0,
        totalSize: data.total_size ?? 0,
        potentialSavings: data.potential_savings ?? 0,
        currentFolder: data.current_folder ?? '',
        currentFile: data.current_file ?? '',
      });

      if (data.status === 'completed') {
        clearInterval(tickRef.current);
        clearActiveScan();
        setIsScanning(false);
        setProgress(100);
        setScanResult({
          status: 'completed',
          filesFound: data.files_found ?? 0,
          totalSize: data.total_size ?? 0,
          potentialSavings: data.potential_savings ?? 0,
        });
        ws.close();
        if (onScanStart) onScanStart();
      } else if (data.status === 'failed') {
        clearInterval(tickRef.current);
        clearActiveScan();
        setIsScanning(false);
        setScanError(data.error_message || 'Scan failed for an unknown reason');
        ws.close();
      }
    };
    ws.onerror = (err) => {
      console.error('WS error:', err);
    };
    ws.onclose = () => {
      clearInterval(tickRef.current);
      setIsScanning(false);
    };
  };

  // On mount (including returning to this page), reattach to a scan that is
  // still running server-side instead of showing a blank "Start Scanning" state.
  useEffect(() => {
    let saved;
    try {
      saved = JSON.parse(localStorage.getItem(ACTIVE_SCAN_KEY) || 'null');
    } catch {
      saved = null;
    }
    if (!saved?.scanId) return;

    (async () => {
      try {
        const status = await getScanStatistics(saved.scanId);
        if (status?.status === 'completed') {
          clearActiveScan();
          const p = status.progress || {};
          setScanResult({
            status: 'completed',
            filesFound: p.files_found ?? status.total_files ?? 0,
            totalSize: p.total_size ?? status.total_size ?? 0,
            potentialSavings: p.potential_savings ?? 0,
          });
        } else if (status?.status === 'failed') {
          clearActiveScan();
          setScanError(status.error_message || 'Scan failed for an unknown reason');
        } else if (status?.status === 'running') {
          setSelectedPath(saved.path || '');
          attachToScan(saved.scanId, saved.path, saved.startedAt || Date.now());
        } else {
          clearActiveScan();
        }
      } catch (err) {
        console.warn('Could not reattach to saved scan:', err);
        clearActiveScan();
      }
    })();

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (tickRef.current) clearInterval(tickRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleScan = async () => {
    if (!selectedPath) {
      alert('Please select a folder');
      return;
    }

    setIsScanning(true);
    setProgress(0);
    setHasProgressEvent(false);
    setScanStats(null);
    setScanError(null);
    setScanResult(null);

    try {
      const result = await startScan(selectedPath, {
        recursive: true,
        includeHidden: false,
        computeHash: true,
      });
      const scanId = result?.scan_id ?? result?.data?.scan_id;
      if (!scanId) throw new Error('Backend did not return scan_id');

      attachToScan(scanId, selectedPath, Date.now());
    } catch (error) {
      console.error('Scan failed:', error);
      setIsScanning(false);
      setScanError(error.message);
    }
  };

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
              onChange={handlePathChange}
              placeholder="C:\Users\YourName\Documents"
              className="path-input"
              disabled={isScanning}
            />
            <button className="browse-btn" onClick={handleBrowse} disabled={isScanning}>
              Browse...
            </button>
          </div>
        </div>

        {!isScanning && !scanResult && !scanError && (
          <button className="scan-btn primary" onClick={handleScan}>
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
              <span className="status">Scanning... {hasProgressEvent ? `${progress}%` : ''}</span>
              <span className="elapsed">{elapsed.toFixed(0)}s elapsed</span>
            </div>

            {scanStats && (
              <>
                <div className="scan-stat-cards">
                  <div className="stat-card">
                    <span className="stat-icon">🗂️</span>
                    <span className="stat-label">Files Found</span>
                    <span className="stat-value">{scanStats.filesFound.toLocaleString()}</span>
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
                    <span className="stat-icon">⏱️</span>
                    <span className="stat-label">Elapsed</span>
                    <span className="stat-value">{elapsed.toFixed(0)}s</span>
                  </div>
                </div>
                <div className="scan-current-line truncate">
                  <span className="current-folder">{scanStats.currentFolder}</span>
                  {scanStats.currentFile && (
                    <span className="current-file"> / {scanStats.currentFile}</span>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {scanResult && scanResult.status === 'completed' && (
          <div className="scan-result-card success">
            <div className="result-icon">✅</div>
            <h3>Scan Complete</h3>
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
            </div>
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
            <input type="checkbox" defaultChecked />
            <span>Include hidden files</span>
          </label>
          <label className="checkbox-label">
            <input type="checkbox" defaultChecked />
            <span>Scan subfolders recursively</span>
          </label>
          <label className="checkbox-label">
            <input type="checkbox" />
            <span>Skip system folders</span>
          </label>
          <label className="checkbox-label">
            <input type="checkbox" defaultChecked />
            <span>Calculate file hashes</span>
          </label>
        </div>

        <div className="recent-scans">
          <h3>Recent Scans</h3>
          <div className="recent-list">
            <div className="recent-item">
              <span className="path">C:\Users\User\Documents</span>
              <span className="time">2 hours ago</span>
            </div>
            <div className="recent-item">
              <span className="path">C:\Users\User\Pictures</span>
              <span className="time">1 day ago</span>
            </div>
            <div className="recent-item">
              <span className="path">D:\Archive</span>
              <span className="time">1 week ago</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

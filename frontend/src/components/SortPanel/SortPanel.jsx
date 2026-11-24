import React, { useCallback, useEffect, useState } from 'react';
import {
  listOrganizerFolders,
  previewSort,
  applySort,
  listJournal,
  undoOperation,
} from '../../services/api';
import ConfirmModal from '../UI/ConfirmModal';
import './SortPanel.css';

const MODES = [
  { key: 'type', label: 'By type', hint: 'Images, Documents, Video…' },
  { key: 'extension', label: 'By extension', hint: 'jpg, pdf, mp4…' },
  { key: 'date', label: 'By date', hint: 'Modified year or month' },
];

export default function SortPanel() {
  const [folders, setFolders] = useState([]);
  const [source, setSource] = useState('');
  const [mode, setMode] = useState('type');
  const [granularity, setGranularity] = useState('year');
  const [recursive, setRecursive] = useState(false);
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [message, setMessage] = useState(null); // {type: 'ok'|'error', text}
  const [history, setHistory] = useState([]);

  const opts = { source: source.trim(), mode, granularity, recursive };

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await listJournal(10));
    } catch {
      setHistory([]);
    }
  }, []);

  useEffect(() => {
    listOrganizerFolders()
      .then((d) => setFolders(d?.folders || []))
      .catch(() => setFolders([]));
    refreshHistory();
  }, [refreshHistory]);

  // Any option change invalidates the previous preview
  useEffect(() => { setPlan(null); }, [source, mode, granularity, recursive]);

  const run = async (fn) => {
    setBusy(true);
    setMessage(null);
    try {
      return await fn();
    } catch (e) {
      setMessage({ type: 'error', text: e.message || String(e) });
      return null;
    } finally {
      setBusy(false);
    }
  };

  const handlePreview = async () => {
    const result = await run(() => previewSort(opts));
    if (result) {
      setPlan(result);
      if (result.total === 0) setMessage({ type: 'ok', text: 'Nothing to sort: files are already in place.' });
    }
  };

  const handleApply = async () => {
    setConfirm(false);
    const result = await run(() => applySort(opts));
    if (!result) return;
    setPlan(null);
    const failed = result.failed?.length || 0;
    setMessage({
      type: failed ? 'error' : 'ok',
      text: `Moved ${result.moved} file(s)${failed ? `, ${failed} could not be moved` : ''}. You can undo this below.`,
    });
    refreshHistory();
  };

  const handleUndo = async (id) => {
    const result = await run(() => undoOperation(id));
    if (!result) return;
    const skipped = result.skipped?.length || 0;
    setMessage({
      type: skipped ? 'error' : 'ok',
      text: `Restored ${result.restored} file(s)${skipped ? `; ${skipped} skipped because they changed since (not overwritten)` : ''}.`,
    });
    refreshHistory();
  };

  return (
    <section className="sort-panel dashboard-card" aria-labelledby="sort-title">
      <h3 id="sort-title">Auto-sort</h3>

      <div className="sort-grid">
        <label className="sort-field sort-source">
          <span>Folder to sort</span>
          <input
            list="sort-folders"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder="Pick an indexed folder or type a path"
            spellCheck="false"
          />
          <datalist id="sort-folders">
            {folders.map((f) => <option key={f} value={f} />)}
          </datalist>
        </label>

        <fieldset className="sort-field sort-modes">
          <legend>Sort</legend>
          {MODES.map((m) => (
            <label key={m.key} className={`sort-mode${mode === m.key ? ' is-on' : ''}`}>
              <input type="radio" name="sort-mode" value={m.key} checked={mode === m.key} onChange={() => setMode(m.key)} />
              <b>{m.label}</b>
              <small>{m.hint}</small>
            </label>
          ))}
        </fieldset>

        {mode === 'date' && (
          <label className="sort-field">
            <span>Group by</span>
            <select value={granularity} onChange={(e) => setGranularity(e.target.value)}>
              <option value="year">Year</option>
              <option value="month">Year and month</option>
            </select>
          </label>
        )}

        <label className="sort-check">
          <input type="checkbox" checked={recursive} onChange={(e) => setRecursive(e.target.checked)} />
          Include subfolders
        </label>
      </div>

      <div className="sort-actions">
        <button className="sort-btn" onClick={handlePreview} disabled={busy || !source.trim()}>
          {busy && !plan ? 'Working…' : 'Preview'}
        </button>
        <button className="sort-btn primary" onClick={() => setConfirm(true)} disabled={busy || !plan || plan.total === 0}>
          Apply sort{plan ? ` (${plan.total})` : ''}
        </button>
      </div>

      <div role="status" aria-live="polite">
        {message && <p className={`sort-msg is-${message.type}`}>{message.text}</p>}
      </div>

      {plan && plan.total > 0 && (
        <div className="sort-preview">
          <div className="sort-chips">
            {Object.entries(plan.folders).map(([name, n]) => (
              <span key={name} className="sort-chip"><b>{name}</b> {n}</span>
            ))}
          </div>
          <ul className="sort-moves">
            {plan.preview.slice(0, 8).map((m) => (
              <li key={m.file_id}><span title={m.src}>{m.src.split(/[\\/]/).pop()}</span> → <code>{m.folder}/</code></li>
            ))}
          </ul>
          {plan.total > 8 && <p className="sort-more">…and {plan.total - 8} more. Nothing has moved yet.</p>}
          {plan.missing_on_disk > 0 && (
            <p className="sort-more">{plan.missing_on_disk} indexed file(s) no longer exist on disk and were skipped. Re-scan to refresh.</p>
          )}
        </div>
      )}

      <h4 className="sort-history-title">Recent changes</h4>
      {history.length === 0 ? (
        <p className="sort-more">No sorts or moves yet.</p>
      ) : (
        <ul className="sort-history">
          {history.map((h) => (
            <li key={h.id}>
              <span className="sort-history-text">
                <b>{h.summary || h.kind}</b>
                <small>{new Date(h.created_at + 'Z').toLocaleString()} · {h.item_count} file(s)</small>
              </span>
              {h.undone ? (
                <em>Undone</em>
              ) : (
                <button className="sort-btn" onClick={() => handleUndo(h.id)} disabled={busy}>Undo</button>
              )}
            </li>
          ))}
        </ul>
      )}

      <ConfirmModal
        visible={confirm}
        title="Apply this sort?"
        message={`This moves ${plan?.total ?? 0} file(s) into subfolders. Nothing is overwritten, and you can undo it afterwards.`}
        confirmLabel="Move files"
        onConfirm={handleApply}
        onCancel={() => setConfirm(false)}
        loading={busy}
      />
    </section>
  );
}

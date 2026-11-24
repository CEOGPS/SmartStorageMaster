import React, { useEffect, useRef, useState } from 'react';
import { previewRename, applyRename } from '../../services/api';
import ConfirmModal from '../UI/ConfirmModal';
import '../SortPanel/SortPanel.css';
import './RenamePanel.css';

const TOKENS = [
  { t: '{name}', d: 'original name (after find/replace)' },
  { t: '{n:3}', d: 'number, 3 digits' },
  { t: '{date:%Y-%m-%d}', d: 'modified date' },
  { t: '{created:%Y%m%d_%H%M%S}', d: 'created date and time' },
  { t: '{parent}', d: 'folder name' },
  { t: '{size_kb}', d: 'size in KB' },
];
const STATUS_LABEL = { ok: 'Will rename', unchanged: 'No change', conflict: 'Conflict', error: 'Invalid' };

export default function RenamePanel({ folders = [], onChanged }) {
  const [o, setO] = useState({
    folder: '', match: '', template: '{name}', find: '', replace: '', use_regex: false,
    case_sensitive: false, case: 'none', ext_case: 'keep', start: 1, step: 1, order: 'name', recursive: false,
  });
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const templateRef = useRef(null);
  const reqId = useRef(0);

  const set = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.type === 'number' ? Number(e.target.value) : e.target.value;
    setO((prev) => ({ ...prev, [k]: v }));
  };

  const body = () => ({ ...o, folder: o.folder.trim(), match: o.match.trim() || null });

  // Live preview: debounced, and stale responses are ignored
  useEffect(() => {
    if (!o.folder.trim()) { setPlan(null); setError(null); return undefined; }
    const id = ++reqId.current;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const p = await previewRename(body());
        if (id === reqId.current) { setPlan(p); setError(null); }
      } catch (e) {
        if (id === reqId.current) { setPlan(null); setError(e.message || String(e)); }
      } finally {
        if (id === reqId.current) setLoading(false);
      }
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [o]);

  const insertToken = (tok) => {
    const el = templateRef.current;
    const at = el ? el.selectionStart ?? o.template.length : o.template.length;
    const end = el ? el.selectionEnd ?? at : at;
    const next = o.template.slice(0, at) + tok + o.template.slice(end);
    setO((prev) => ({ ...prev, template: next }));
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at + tok.length, at + tok.length); });
  };

  const handleApply = async () => {
    setConfirm(false);
    setBusy(true);
    setMessage(null);
    try {
      const r = await applyRename(body());
      const failed = r.failed?.length || 0;
      setMessage({
        type: failed ? 'error' : 'ok',
        text: `Renamed ${r.renamed} file(s)${r.skipped ? `, skipped ${r.skipped} with conflicts or invalid names` : ''}${failed ? `, ${failed} failed` : ''}. You can undo it under Recent changes.`,
      });
      onChanged?.();
      setO((prev) => ({ ...prev })); // refresh the preview against the new names
    } catch (e) {
      setMessage({ type: 'error', text: e.message || String(e) });
    } finally {
      setBusy(false);
    }
  };

  const ready = plan?.counts?.ok || 0;
  const blocked = (plan?.counts?.conflict || 0) + (plan?.counts?.error || 0);

  return (
    <section className="sort-panel dashboard-card rename-panel" aria-labelledby="rename-title">
      <h3 id="rename-title">Bulk rename</h3>

      <div className="sort-grid">
        <label className="sort-field sort-source">
          <span>Folder</span>
          <input list="rename-folders" value={o.folder} onChange={set('folder')} placeholder="Pick an indexed folder or type a path" spellCheck="false" />
          <datalist id="rename-folders">{folders.map((f) => <option key={f} value={f} />)}</datalist>
        </label>

        <div className="rename-row is-filter">
          <label className="sort-field">
            <span>Only files matching (regex, optional)</span>
            <input value={o.match} onChange={set('match')} placeholder="e.g. \.jpe?g$" spellCheck="false" />
          </label>
          <label className="sort-check"><input type="checkbox" checked={o.recursive} onChange={set('recursive')} /> Include subfolders</label>
        </div>

        <div className="rename-row is-find">
        <label className="sort-field">
          <span>Find</span>
          <input value={o.find} onChange={set('find')} placeholder={o.use_regex ? 'e.g. IMG_(\\d+)' : 'text to replace'} spellCheck="false" />
        </label>
        <label className="sort-field">
          <span>Replace with</span>
          <input value={o.replace} onChange={set('replace')} placeholder={o.use_regex ? 'e.g. photo-\\1' : ''} spellCheck="false" />
        </label>
        <div className="rename-toggles">
          <label className="sort-check"><input type="checkbox" checked={o.use_regex} onChange={set('use_regex')} /> Regex</label>
          <label className="sort-check"><input type="checkbox" checked={o.case_sensitive} onChange={set('case_sensitive')} /> Match case</label>
        </div>
        </div>

        <label className="sort-field sort-source">
          <span>New name (extension is kept)</span>
          <input ref={templateRef} value={o.template} onChange={set('template')} spellCheck="false" className="rename-template" />
        </label>
        <div className="rename-tokens sort-source" role="group" aria-label="Insert a token">
          {TOKENS.map(({ t, d }) => (
            <button key={t} type="button" className="rename-token" onClick={() => insertToken(t)} title={d}>
              <code>{t}</code><small>{d}</small>
            </button>
          ))}
        </div>

        <label className="sort-field"><span>Case</span>
          <select value={o.case} onChange={set('case')}>
            <option value="none">Keep</option><option value="lower">lowercase</option>
            <option value="upper">UPPERCASE</option><option value="title">Title Case</option>
          </select>
        </label>
        <label className="sort-field"><span>Extension</span>
          <select value={o.ext_case} onChange={set('ext_case')}>
            <option value="keep">Keep</option><option value="lower">.lower</option><option value="upper">.UPPER</option>
          </select>
        </label>
        <label className="sort-field"><span>Number in order of</span>
          <select value={o.order} onChange={set('order')}>
            <option value="name">Name</option><option value="modified">Date modified</option><option value="size">Size</option>
          </select>
        </label>
        <div className="rename-nums">
          <label className="sort-field"><span>Start</span><input type="number" value={o.start} onChange={set('start')} /></label>
          <label className="sort-field"><span>Step</span><input type="number" value={o.step} onChange={set('step')} /></label>
        </div>
      </div>

      <div role="status" aria-live="polite" className="rename-status">
        {error && <p className="sort-msg is-error">{error}</p>}
        {message && <p className={`sort-msg is-${message.type}`}>{message.text}</p>}
        {plan && !error && (
          <p className="sort-more">
            {loading ? 'Updating preview… ' : ''}{ready} will be renamed
            {plan.counts.unchanged ? `, ${plan.counts.unchanged} unchanged` : ''}
            {blocked ? `, ${blocked} skipped (see below)` : ''}. Nothing has been renamed yet.
          </p>
        )}
      </div>

      {plan && plan.preview.length > 0 && (
        <div className="rename-table-wrap">
          <table className="rename-table">
            <thead><tr><th scope="col">Current name</th><th scope="col">New name</th><th scope="col">Status</th></tr></thead>
            <tbody>
              {plan.preview.slice(0, 200).map((i) => (
                <tr key={i.file_id} className={`is-${i.status}`}>
                  <td title={i.path}>{i.old_name}</td>
                  <td>{i.new_name}</td>
                  <td title={i.reason || ''}><span className={`rename-badge is-${i.status}`}>{STATUS_LABEL[i.status]}</span>{i.reason && <small>{i.reason}</small>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {plan.total > 200 && <p className="sort-more">Showing the first 200 of {plan.total}.</p>}
        </div>
      )}

      <div className="sort-actions">
        <button className="sort-btn primary" onClick={() => setConfirm(true)} disabled={busy || loading || !ready || !!error}>
          {busy ? 'Renaming…' : `Rename ${ready || ''} file${ready === 1 ? '' : 's'}`}
        </button>
      </div>

      <ConfirmModal
        visible={confirm}
        title="Rename these files?"
        message={`${ready} file(s) will be renamed.${blocked ? ` ${blocked} with conflicts or invalid names will be skipped.` : ''} Nothing is overwritten, and you can undo it afterwards.`}
        confirmLabel="Rename"
        onConfirm={handleApply}
        onCancel={() => setConfirm(false)}
        loading={busy}
      />
    </section>
  );
}

import React, { useCallback, useEffect, useState } from 'react';
import { getProtectedFolders, addProtectedFolder, removeProtectedFolder } from '../../services/api';
import './ProtectedFolders.css';

/** Folders the app will never move, rename, sort or delete from, even when the AI assistant asks */
export default function ProtectedFolders() {
  const [data, setData] = useState({ system: [], user: [] });
  const [path, setPath] = useState('');
  const [note, setNote] = useState('');
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setData(await getProtectedFolders()); } catch (e) { setMessage({ type: 'error', text: e.message }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async (e) => {
    e.preventDefault();
    if (!path.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      const r = await addProtectedFolder(path.trim(), note.trim());
      setMessage({ type: 'ok', text: r.already ? 'That folder is already protected.' : 'Folder protected.' });
      setPath('');
      setNote('');
      await load();
    } catch (err) {
      setMessage({ type: 'error', text: err.message || String(err) });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id) => {
    setBusy(true);
    try { await removeProtectedFolder(id); await load(); }
    catch (err) { setMessage({ type: 'error', text: err.message || String(err) }); }
    finally { setBusy(false); }
  };

  return (
    <div className="settings-section protected-folders">
      <h2>Protected folders</h2>
      <p className="pf-help">
        Files in a protected folder can never be moved, renamed, sorted or deleted by this app, including
        when you ask the AI assistant. Scanning still reads them.
      </p>

      <form className="pf-add" onSubmit={add}>
        <label>
          <span>Folder to protect</span>
          <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="C:\Users\You\Documents\Taxes" spellCheck="false" />
        </label>
        <label>
          <span>Note (optional)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why it is protected" />
        </label>
        <button type="submit" className="pf-btn primary" disabled={busy || !path.trim()}>Protect</button>
      </form>

      <div role="status" aria-live="polite">
        {message && <p className={`pf-msg is-${message.type}`}>{message.text}</p>}
      </div>

      <h3 className="pf-sub">Your protected folders</h3>
      {data.user.length === 0 ? (
        <p className="pf-empty">None yet.</p>
      ) : (
        <ul className="pf-list">
          {data.user.map((p) => (
            <li key={p.id}>
              <span className="pf-path"><code>{p.path}</code>{p.note && <small>{p.note}</small>}</span>
              <button className="pf-btn" onClick={() => remove(p.id)} disabled={busy} aria-label={`Stop protecting ${p.path}`}>Remove</button>
            </li>
          ))}
        </ul>
      )}

      <details className="pf-system">
        <summary>Always protected by the app ({data.system.length})</summary>
        <ul className="pf-list">
          {data.system.map((p) => (
            <li key={p.path}><span className="pf-path"><code>{p.path}</code><small>{p.reason}</small></span></li>
          ))}
        </ul>
      </details>
    </div>
  );
}

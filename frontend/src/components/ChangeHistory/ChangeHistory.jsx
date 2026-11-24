import React, { useCallback, useEffect, useState } from 'react';
import { listJournal, undoOperation } from '../../services/api';
import '../SortPanel/SortPanel.css';

/** Recent reversible changes (moves, sorts, renames) with one-click undo */
export default function ChangeHistory({ refreshKey = 0, onChanged }) {
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  const refresh = useCallback(async () => {
    try { setHistory(await listJournal(10)); } catch { setHistory([]); }
  }, []);

  useEffect(() => { refresh(); }, [refresh, refreshKey]);

  const handleUndo = async (id) => {
    setBusy(true);
    setMessage(null);
    try {
      const r = await undoOperation(id);
      const skipped = r.skipped?.length || 0;
      setMessage({
        type: skipped ? 'error' : 'ok',
        text: `Restored ${r.restored} file(s)${skipped ? `; ${skipped} skipped because they changed since (not overwritten)` : ''}.`,
      });
      onChanged?.();
    } catch (e) {
      setMessage({ type: 'error', text: e.message || String(e) });
    } finally {
      setBusy(false);
      refresh();
    }
  };

  return (
    <section className="sort-panel dashboard-card" aria-labelledby="history-title">
      <h3 id="history-title">Recent changes</h3>
      <div role="status" aria-live="polite">
        {message && <p className={`sort-msg is-${message.type}`}>{message.text}</p>}
      </div>
      {history.length === 0 ? (
        <p className="sort-more">No moves, sorts or renames yet.</p>
      ) : (
        <ul className="sort-history">
          {history.map((h) => (
            <li key={h.id}>
              <span className="sort-history-text">
                <b>{h.summary || h.kind}</b>
                <small>{new Date(h.created_at + 'Z').toLocaleString()} · {h.kind}</small>
              </span>
              {h.undone ? <em>Undone</em> : (
                <button className="sort-btn" onClick={() => handleUndo(h.id)} disabled={busy}>Undo</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

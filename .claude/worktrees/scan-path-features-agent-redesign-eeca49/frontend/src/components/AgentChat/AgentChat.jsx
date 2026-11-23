import React, { useState, useRef, useEffect, useCallback } from 'react';
import { sendAgentMessage, getAgentStatus } from '../../services/api';
import AgentAvatar from './AgentAvatar';
import './AgentChat.css';

const STORE_KEY = 'ssm.agentChat';
const PREFS_KEY = 'ssm.agentPrefs';
const MAX_SAVED = 40;
const BARS = 36;

const QUICK_PROMPTS = [
  { label: 'Biggest space hogs', tone: 'amber', text: "What's taking up the most space in my last scan?" },
  { label: 'Find duplicates', tone: 'amber', text: 'Find duplicate files in my most recent scan and summarize them.' },
  { label: 'Cleanup plan', tone: 'teal', text: 'Suggest a safe cleanup plan. Do not delete anything yet.' },
  { label: 'Scan Downloads', tone: 'teal', text: 'Scan my Downloads folder.' },
];

function load(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback;
  } catch {
    return fallback;
  }
}

function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: chat still works for this session */
  }
}

/**
 * Agent dock - floating AI assistant in the CEOLife style: a portrait
 * "seal" button that opens a console with the live avatar, waveform,
 * quick-action pills, the conversation and a composer.
 *
 * Talks to the same /api/agent/chat endpoint as before; every action the
 * agent takes is one of the app's own page actions.
 */
function AgentChat() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState(() => load(STORE_KEY, []));
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [expandedActions, setExpandedActions] = useState({});
  const [status, setStatus] = useState(null); // { online, model, model_installed }
  const [prefs, setPrefs] = useState(() => ({ readAloud: false, ...load(PREFS_KEY, {}) }));
  const [talking, setTalking] = useState(false);
  const [mouth, setMouth] = useState(0);
  const [levels, setLevels] = useState(() => Array(BARS).fill(0));

  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const frameRef = useRef(0);
  const talkTimer = useRef(0);

  useEffect(() => save(STORE_KEY, messages.slice(-MAX_SAVED)), [messages]);
  useEffect(() => save(PREFS_KEY, prefs), [prefs]);

  const refreshStatus = useCallback(() => {
    getAgentStatus().then(setStatus).catch(() => setStatus({ online: false, model: '', backendDown: true }));
  }, []);

  useEffect(() => refreshStatus(), [refreshStatus]);

  useEffect(() => {
    if (!open) return undefined;
    refreshStatus();
    const id = setInterval(refreshStatus, 30000);
    const t = setTimeout(() => inputRef.current?.focus(), 60);
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', onKey);
    return () => {
      clearInterval(id);
      clearTimeout(t);
      window.removeEventListener('keydown', onKey);
    };
  }, [open, refreshStatus]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, loading, open]);

  // Mouth + waveform animation while the agent speaks.
  useEffect(() => {
    if (!talking) {
      setMouth(0);
      setLevels(Array(BARS).fill(0));
      return undefined;
    }
    const start = performance.now();
    const step = (now) => {
      const t = (now - start) / 1000;
      const env = Math.abs(Math.sin(t * 17) * Math.sin(t * 6.3 + 1));
      setMouth(0.15 + env * 0.85);
      setLevels(Array.from({ length: BARS }, (_, i) =>
        Math.abs(Math.sin(t * 9 + i * 0.7) * Math.cos(t * 4.1 + i * 0.31)) * (0.4 + env * 0.6)));
      frameRef.current = requestAnimationFrame(step);
    };
    frameRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frameRef.current);
  }, [talking]);

  useEffect(() => () => {
    clearTimeout(talkTimer.current);
    window.speechSynthesis?.cancel();
  }, []);

  const speak = (text) => {
    clearTimeout(talkTimer.current);
    const synth = window.speechSynthesis;
    if (prefs.readAloud && synth && typeof window.SpeechSynthesisUtterance === 'function') {
      synth.cancel();
      const utter = new window.SpeechSynthesisUtterance(text);
      utter.onstart = () => setTalking(true);
      utter.onend = () => setTalking(false);
      utter.onerror = () => setTalking(false);
      synth.speak(utter);
      return;
    }
    // Silent mode: a short "speaking" pulse scaled to the reply length
    setTalking(true);
    talkTimer.current = setTimeout(() => setTalking(false), Math.min(3200, 600 + text.length * 18));
  };

  const toggleActions = (idx) => setExpandedActions((prev) => ({ ...prev, [idx]: !prev[idx] }));

  const send = async (raw) => {
    const text = (raw ?? input).trim();
    if (!text || loading) return;

    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setInput('');
    setLoading(true);
    window.speechSynthesis?.cancel();
    setTalking(false);

    try {
      const data = await sendAgentMessage(text, history);
      const reply = data?.reply || '(no reply)';
      setMessages((prev) => [...prev, { role: 'assistant', content: reply, actionsTaken: data?.actions_taken || [] }]);
      speak(reply);
    } catch (error) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: `Sorry, something went wrong: ${error.message || error}`,
        actionsTaken: [],
        error: true,
      }]);
      refreshStatus();
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    window.speechSynthesis?.cancel();
    setTalking(false);
    setMessages([]);
    setExpandedActions({});
  };

  const toggleReadAloud = () => {
    setPrefs((p) => {
      if (p.readAloud) window.speechSynthesis?.cancel();
      return { ...p, readAloud: !p.readAloud };
    });
  };

  const offline = status && !status.online;
  const avatarState = offline ? 'offline' : loading ? 'thinking' : talking ? 'talking' : 'idle';
  const stateLabel = status?.backendDown
    ? 'Backend offline'
    : offline
      ? 'Ollama offline'
      : loading
        ? 'Thinking'
        : talking
          ? 'Speaking'
          : 'Active';

  return (
    <div className="agent-dock-root" data-open={open}>
      {open && (
        <section className="az-dock" role="dialog" aria-label="Storage agent">
          <header className="dk-head">
            <div className="dk-brand">
              <span className="dk-logo">STORAGE&nbsp;AI</span>
              <span className={`dk-active is-${avatarState}`}>
                <span className="dk-spark" aria-hidden>✦</span>
                {stateLabel}
              </span>
            </div>
            <div className="dk-head-actions">
              <button type="button" className="dk-icon" onClick={clearChat} title="Clear conversation"
                aria-label="Clear conversation" disabled={!messages.length}>
                <svg viewBox="0 0 24 24" aria-hidden><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>
              </button>
              <button type="button" className="dk-icon" onClick={() => setOpen(false)} title="Minimize"
                aria-label="Minimize agent">
                <svg viewBox="0 0 24 24" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            </div>
          </header>

          <div className="dk-stage">
            <AgentAvatar state={avatarState} mouth={mouth} />
            <span className={`az-pip is-${avatarState}`} aria-hidden />
            <div className="dk-wave" aria-hidden>
              {levels.map((level, i) => {
                const idle = 12 + 30 * Math.abs(Math.sin(i * 0.83) * Math.cos(i * 0.37));
                return (
                  <span
                    key={i}
                    className={i % 5 === 2 ? 'is-teal' : ''}
                    style={{ height: `${Math.max(idle * (avatarState === 'idle' ? 0.5 : 0.8), level * 100)}%` }}
                  />
                );
              })}
            </div>
            <div className="dk-model">
              {status?.model ? `${status.model}` : 'local model'}
              {status && status.online && !status.model_installed ? ' · not pulled' : ''}
            </div>
          </div>

          <div className="dk-pills">
            {QUICK_PROMPTS.map((p) => (
              <button key={p.label} type="button" className={`dk-pill is-${p.tone}`}
                onClick={() => send(p.text)} disabled={loading}>
                {p.label}
              </button>
            ))}
          </div>

          <div className="dk-thread" ref={scrollRef} aria-live="polite">
            {offline && (
              <p className="dk-note">
                {status?.backendDown
                  ? 'Cannot reach the Storage Manager backend on port 8000.'
                  : <>Start Ollama and run <code>ollama pull {status?.model || 'llama3.2'}</code> to chat.</>}
              </p>
            )}
            {messages.length === 0 && !offline && (
              <p className="dk-note">
                Ask in plain words — “scan D:\Photos and tell me what’s taking space” or
                “clean up duplicates in Downloads over 100MB”. Nothing is deleted without your OK.
              </p>
            )}
            {messages.map((m, idx) => (
              <div key={idx} className={`dk-line ${m.role === 'user' ? 'is-me' : ''} ${m.error ? 'is-error' : ''}`}>
                <span className={`dk-who ${m.role === 'user' ? 'is-me' : ''}`}>{m.role === 'user' ? 'You' : 'Agent'}</span>
                <div className="dk-text">
                  {m.content}
                  {m.role === 'assistant' && m.actionsTaken?.length > 0 && (
                    <div className="dk-acts">
                      <button type="button" className="dk-acts-toggle" onClick={() => toggleActions(idx)}
                        aria-expanded={!!expandedActions[idx]}>
                        {expandedActions[idx] ? '▾' : '▸'} {m.actionsTaken.length} action{m.actionsTaken.length > 1 ? 's' : ''} taken
                      </button>
                      {expandedActions[idx] && (
                        <ul>{m.actionsTaken.map((a, i) => <li key={i}>{a}</li>)}</ul>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="dk-line">
                <span className="dk-who">Agent</span>
                <div className="dk-text dk-typing" aria-label="Thinking"><i /><i /><i /></div>
              </div>
            )}
          </div>

          <form className="dk-compose" onSubmit={(e) => { e.preventDefault(); send(); }}>
            <input
              ref={inputRef}
              value={input}
              placeholder="Message the agent"
              aria-label="Message the agent"
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
            />
            <button type="submit" className={loading ? 'is-busy' : ''} aria-label="Send"
              disabled={loading || !input.trim()}>
              <svg viewBox="0 0 24 24" aria-hidden><path d="M4 12l16-8-6 16-2.5-6.5L4 12z" /></svg>
            </button>
          </form>

          <div className="dk-toggles">
            <button type="button" className="dk-toggle" aria-pressed={prefs.readAloud} onClick={toggleReadAloud}>
              Read aloud
              <span className={`az-toggle ${prefs.readAloud ? 'is-on' : ''}`} aria-hidden />
            </button>
            <span className="dk-hint">Esc to minimize</span>
          </div>
        </section>
      )}

      {!open && (
        <button type="button" className="az-seal" onClick={() => setOpen(true)}
          title="Open storage agent" aria-label="Open storage agent">
          <span className="az-seal-face">
            <AgentAvatar state={loading ? 'thinking' : 'idle'} />
          </span>
          <span className={`az-live ${offline ? 'is-off' : ''}`} />
        </button>
      )}
    </div>
  );
}

export default AgentChat;

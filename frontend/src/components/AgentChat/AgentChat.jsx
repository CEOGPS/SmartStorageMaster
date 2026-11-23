import React, { useState, useRef, useEffect } from 'react';
import { sendAgentMessage } from '../../services/api';
import AgentAvatar from './AgentAvatar';
import './AgentChat.css';

/**
 * Floating AI agent chat panel.
 *
 * Lets the user type natural-language requests ("clean up duplicates in
 * Downloads over 100MB") instead of only using the fixed page buttons.
 * Purely additive - does not replace any existing page/button.
 */
function AgentChat() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]); // { role, content, actionsTaken? }
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [expandedActions, setExpandedActions] = useState({});
  const [speaking, setSpeaking] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const speakTimer = useRef(null);

  const avatarState = loading ? 'thinking' : speaking ? 'speaking' : 'idle';

  useEffect(() => () => clearTimeout(speakTimer.current), []);

  // Focus the input when the panel opens; Escape closes it
  useEffect(() => {
    if (!open) return undefined;
    const t = setTimeout(() => inputRef.current?.focus(), 200);
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => { clearTimeout(t); window.removeEventListener('keydown', onKey); };
  }, [open]);

  const startSpeaking = (text) => {
    clearTimeout(speakTimer.current);
    setSpeaking(true);
    speakTimer.current = setTimeout(() => setSpeaking(false), Math.min(6000, Math.max(1500, text.length * 25)));
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading, open]);

  const toggleActions = (idx) => {
    setExpandedActions((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const nextMessages = [...messages, { role: 'user', content: text }];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);

    try {
      const data = await sendAgentMessage(text, history);
      startSpeaking(data?.reply || '');
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data?.reply || '(no reply)',
          actionsTaken: data?.actions_taken || [],
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Sorry, something went wrong: ${error.message || error}`,
          actionsTaken: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="agent-chat-root">
      <div
        id="agent-chat-panel"
        className={`agent-chat-panel${open ? ' is-open' : ''}`}
        role="dialog"
        aria-label="AI assistant"
        aria-hidden={!open}
        inert={!open ? '' : undefined}
      >
        <>
          <div className="agent-chat-header">
            <AgentAvatar state={avatarState} size="sm" />
            <span className="agent-chat-title">
              Zoie
              <small className={`agent-chat-status is-${avatarState}`}>
                {avatarState === 'idle' ? 'Ready' : avatarState === 'thinking' ? 'Thinking…' : 'Speaking'}
              </small>
            </span>
            <button
              className="agent-chat-close"
              onClick={() => setOpen(false)}
              title="Close"
              aria-label="Close chat"
            >
              ✕
            </button>
          </div>

          <div className="agent-chat-messages" ref={scrollRef} role="log" aria-live="polite">
            {messages.length === 0 && (
              <div className="agent-chat-empty">
                Try asking things like "scan C:\Users\Me and tell me what's
                taking the most space" or "clean up duplicates in Downloads
                over 100MB".
              </div>
            )}
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`agent-chat-message ${m.role === 'user' ? 'from-user' : 'from-assistant'}`}
              >
                <div className="agent-chat-bubble">{m.content}</div>
                {m.role === 'assistant' && m.actionsTaken && m.actionsTaken.length > 0 && (
                  <div className="agent-chat-actions">
                    <button
                      className="agent-chat-actions-toggle"
                      onClick={() => toggleActions(idx)}
                    >
                      {expandedActions[idx] ? '▾' : '▸'} actions taken ({m.actionsTaken.length})
                    </button>
                    {expandedActions[idx] && (
                      <ul className="agent-chat-actions-list">
                        {m.actionsTaken.map((a, i) => (
                          <li key={i}>{a}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="agent-chat-message from-assistant">
                <div className="agent-chat-bubble agent-chat-loading">Thinking…</div>
              </div>
            )}
          </div>

          <div className="agent-chat-input-row">
            <input
              type="text"
              className="agent-chat-input"
              placeholder="Ask the assistant..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              ref={inputRef}
              aria-label="Message the assistant"
            />
            <button
              className="agent-chat-send"
              onClick={handleSend}
              disabled={loading || !input.trim()}
            >
              Send
            </button>
          </div>
        </>
      </div>

      <button
        className={`agent-chat-toggle${open ? ' is-open' : ''}`}
        onClick={() => setOpen((v) => !v)}
        title="AI Assistant"
        aria-label={open ? 'Close AI assistant' : 'Open AI assistant'}
        aria-expanded={open}
        aria-controls="agent-chat-panel"
      >
        <AgentAvatar state={avatarState} size="md" />
      </button>
    </div>
  );
}

export default AgentChat;

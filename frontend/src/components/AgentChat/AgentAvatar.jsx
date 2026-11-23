import React from 'react';
import './AgentAvatar.css';

const LABELS = { idle: 'Ready', thinking: 'Thinking', speaking: 'Speaking' };

/**
 * Agent avatar with three visual states.
 *   idle     - slow breathing glow, green status pip
 *   thinking - orbiting dots + amber pip
 *   speaking - waveform bars + purple pulse ring
 * Decorative only: the state is announced via the `label` text for screen readers.
 */
export default function AgentAvatar({ state = 'idle', size = 'md', src = '/avatars/zoie.webp', name = 'Zoie' }) {
  return (
    <span className={`agent-avatar is-${state} size-${size}`} role="img" aria-label={`${name}: ${LABELS[state]}`}>
      <span className="agent-avatar-ring" aria-hidden="true" />
      <span className="agent-avatar-face">
        <img src={src} alt="" draggable="false" loading="lazy" decoding="async" />
      </span>
      {state === 'thinking' && (
        <span className="agent-avatar-orbit" aria-hidden="true"><i /><i /><i /></span>
      )}
      {state === 'speaking' && size !== 'sm' && (
        <span className="agent-avatar-wave" aria-hidden="true">
          {Array.from({ length: 7 }, (_, i) => <i key={i} style={{ '--i': i }} />)}
        </span>
      )}
      <span className="agent-avatar-pip" aria-hidden="true" />
    </span>
  );
}

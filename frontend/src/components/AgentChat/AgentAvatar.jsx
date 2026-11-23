import React, { useId } from 'react';

/**
 * Holographic agent face in the CEOLife palette (cyan #4fd2ff, violet
 * #a78bfa / #c084fc, teal #2dd4bf on black). Pure SVG so it works offline
 * inside the desktop app with no image assets.
 *
 * state: 'idle' | 'thinking' | 'talking' | 'offline'
 * mouth: 0..1 mouth opening, driven by the dock while the agent "speaks"
 */
export default function AgentAvatar({ state = 'idle', mouth = 0, className = '' }) {
  const uid = useId().replace(/:/g, '');
  const bg = `az-bg-${uid}`;
  const edge = `az-edge-${uid}`;
  const glow = `az-glow-${uid}`;

  return (
    <svg
      className={`az-avatar is-${state} ${className}`}
      viewBox="0 0 200 200"
      role="img"
      aria-label={`Agent is ${state}`}
      style={{ '--mouth-open': mouth }}
    >
      <defs>
        <radialGradient id={bg} gradientUnits="userSpaceOnUse" cx="100" cy="80" r="150">
          <stop offset="0%" stopColor="#2a1050" />
          <stop offset="55%" stopColor="#0a0d16" />
          <stop offset="100%" stopColor="#000" />
        </radialGradient>
        <linearGradient id={edge} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#4fd2ff" />
          <stop offset="100%" stopColor="#a78bfa" />
        </linearGradient>
        <filter id={glow} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.4" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Background and grid extend past the viewBox so a wide stage has no seams */}
      <rect x="-400" y="-200" width="1000" height="600" fill="#000" />
      <rect x="-400" y="0" width="1000" height="200" fill={`url(#${bg})`} />

      {/* scan-line grid */}
      <g className="az-grid" stroke="#4fd2ff" strokeOpacity="0.07">
        {Array.from({ length: 9 }, (_, i) => (
          <line key={i} x1="-400" x2="600" y1={20 + i * 20} y2={20 + i * 20} />
        ))}
      </g>

      {/* halo: dashes spin while thinking */}
      <g className="az-halo">
        <circle cx="100" cy="94" r="80" fill="none" stroke={`url(#${edge})`} strokeOpacity="0.35"
          strokeWidth="1.5" strokeDasharray="4 10" />
        <circle cx="100" cy="94" r="70" fill="none" stroke="#4fd2ff" strokeOpacity="0.12" strokeWidth="1" />
      </g>

      {/* shoulders */}
      <path d="M26 200 C36 166 68 152 100 152 C132 152 164 166 174 200 Z"
        fill="#4fd2ff" fillOpacity="0.06" stroke={`url(#${edge})`} strokeWidth="2" />
      <path d="M100 152 L100 200" stroke="#4fd2ff" strokeOpacity="0.18" strokeWidth="1" />

      {/* head */}
      <path d="M100 30 C132 30 150 54 150 88 C150 122 128 146 100 146 C72 146 50 122 50 88 C50 54 68 30 100 30 Z"
        fill="#080c12" fillOpacity="0.92" stroke={`url(#${edge})`} strokeWidth="2.5" filter={`url(#${glow})`} />

      {/* circuit traces */}
      <g stroke="#2dd4bf" strokeOpacity="0.55" strokeWidth="1.2" fill="none" strokeLinecap="round">
        <path d="M58 104 L68 104 L74 112" />
        <path d="M142 104 L132 104 L126 112" />
        <path d="M100 34 L100 48" />
      </g>
      <g fill="#2dd4bf" fillOpacity="0.8">
        <circle cx="74" cy="112" r="1.8" />
        <circle cx="126" cy="112" r="1.8" />
        <circle cx="100" cy="50" r="1.8" />
      </g>

      {/* visor + eyes */}
      <rect x="60" y="74" width="80" height="24" rx="12" fill="#4fd2ff" fillOpacity="0.07"
        stroke="#4fd2ff" strokeOpacity="0.4" />
      <g className="az-eyes" filter={`url(#${glow})`}>
        <rect x="72" y="82" width="18" height="8" rx="4" fill="#8aebff" />
        <rect x="110" y="82" width="18" height="8" rx="4" fill="#8aebff" />
      </g>

      {/* mouth */}
      <rect className="az-mouth-bar" x="84" y="119" width="32" height="5" rx="2.5"
        fill="#c084fc" filter={`url(#${glow})`} />
    </svg>
  );
}

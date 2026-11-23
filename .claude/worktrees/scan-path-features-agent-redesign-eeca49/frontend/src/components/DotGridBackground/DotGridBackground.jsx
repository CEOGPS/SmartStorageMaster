import React, { useEffect, useRef } from 'react';
import './DotGridBackground.css';

const IDLE_TIMEOUT_MS = 850;

export default function DotGridBackground() {
  const layerRef = useRef(null);
  const idleTimerRef = useRef(null);

  useEffect(() => {
    const el = layerRef.current;
    if (!el) return;

    const handleMouseMove = (e) => {
      el.style.setProperty('--mx', `${e.clientX}px`);
      el.style.setProperty('--my', `${e.clientY}px`);
      el.classList.add('is-active');

      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      idleTimerRef.current = setTimeout(() => {
        el.classList.remove('is-active');
      }, IDLE_TIMEOUT_MS);
    };

    window.addEventListener('mousemove', handleMouseMove);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    };
  }, []);

  return <div ref={layerRef} className="dot-grid-background" aria-hidden="true" />;
}

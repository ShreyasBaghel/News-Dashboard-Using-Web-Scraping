import React, { useState, useEffect } from 'react';
import { RefreshCw, Clock } from 'lucide-react';

export default function RefreshTimer({ nextUpdate }) {
  const [timeLeft, setTimeLeft] = useState('');

  useEffect(() => {
    if (!nextUpdate) return;

    const calculateTime = () => {
      const target = new Date(nextUpdate).getTime();
      const now = new Date().getTime();
      const diff = target - now;

      if (diff <= 0) {
        setTimeLeft('Scheduled Refresh Pending...');
        return;
      }

      const hours = Math.floor(diff / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diff % (1000 * 60)) / 1000);

      const parts = [];
      if (hours > 0) parts.push(`${hours}h`);
      parts.push(`${minutes}m`);
      parts.push(`${seconds}s`);

      setTimeLeft(parts.join(' '));
    };

    calculateTime();
    const interval = setInterval(calculateTime, 1000);

    return () => clearInterval(interval);
  }, [nextUpdate]);

  return (
    <div 
      className="glass-panel"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '0.75rem 1.25rem',
        borderRadius: 'var(--radius-md)',
        background: 'rgba(26, 58, 92, 0.04)',
        border: '1px solid rgba(26, 58, 92, 0.1)',
        fontSize: '0.875rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)' }}>
        <Clock size={16} style={{ color: 'var(--color-secondary)' }} />
        <span>Next automatic sync in:</span>
        <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontFamily: 'monospace' }}>
          {timeLeft || '--:--:--'}
        </span>
      </div>
    </div>
  );
}

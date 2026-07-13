import React, { useState, useEffect } from 'react';
import { RefreshCw, Clock } from 'lucide-react';

export default function RefreshTimer({ nextUpdate, onManualRefresh, isLoading, userRole = 'employee' }) {
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
        justifyContent: 'space-between',
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
      
      {userRole === 'admin' && (
        <button
          onClick={onManualRefresh}
          disabled={isLoading}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-primary)',
            padding: '0.4rem 1rem',
            borderRadius: '100px',
            cursor: 'pointer',
            fontFamily: 'var(--font-title)',
            fontSize: '0.8rem',
            fontWeight: 600,
            transition: 'var(--transition-bounce)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'var(--bg-surface-hover)';
            e.currentTarget.style.borderColor = 'var(--color-primary)';
            e.currentTarget.style.color = 'var(--color-primary)';
            e.currentTarget.style.transform = 'translateY(-1px)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'var(--bg-surface)';
            e.currentTarget.style.borderColor = 'var(--border-color)';
            e.currentTarget.style.color = 'var(--text-primary)';
            e.currentTarget.style.transform = 'translateY(0)';
          }}
        >
          <RefreshCw 
            size={14} 
            className={isLoading ? 'spinning' : ''} 
            style={{ 
              animation: isLoading ? 'spin 1.2s linear infinite' : 'none',
              color: 'var(--color-primary)' 
            }} 
          />
          {isLoading ? 'Synchronizing...' : 'Force Refresh Pipeline'}
        </button>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

import React from 'react';
import ArticleCard from './ArticleCard';
import { Zap } from 'lucide-react';

export default function PinnedSection({ articles }) {
  if (!articles || articles.length === 0) return null;

  return (
    <div 
      className="animate-fade-in" 
      style={{ 
        display: 'flex', 
        flexDirection: 'column', 
        gap: '1.25rem',
        width: '100%',
        padding: '1.5rem',
        borderRadius: 'var(--radius-lg)',
        background: 'radial-gradient(100% 100% at 0% 0%, rgba(26, 58, 92, 0.04) 0%, rgba(226, 160, 43, 0.02) 100%)',
        border: '1px solid rgba(26, 58, 92, 0.12)',
        boxShadow: 'inset 0 1px 1px 0 rgba(255, 255, 255, 0.4)'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <Zap size={20} style={{ color: 'var(--color-accent)' }} />
        <h2 style={{ fontSize: '1.35rem', color: 'var(--text-primary)', fontFamily: 'var(--font-title)' }}>
          High-Impact Tech Intelligence
        </h2>
        <span 
          style={{ 
            fontSize: '0.7rem', 
            background: 'var(--gradient-tech)', 
            padding: '0.2rem 0.6rem', 
            borderRadius: '100px', 
            color: '#fff', 
            fontWeight: 'bold',
            letterSpacing: '0.05em',
            boxShadow: '0 2px 8px var(--glow-primary)'
          }}
        >
          PINNED
        </span>
      </div>
      
      <div 
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          gap: '1.25rem'
        }}
      >
        {articles.map((article, idx) => (
          <ArticleCard key={`pinned-${idx}`} article={article} />
        ))}
      </div>
    </div>
  );
}

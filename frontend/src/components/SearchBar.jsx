import React, { useState } from 'react';
import { Search, X, Cpu, Factory, Leaf, Lightbulb } from 'lucide-react';

const SUGGESTIONS = [
  { label: 'Cement Decarbonization', icon: Leaf },
  { label: 'Smart Manufacturing', icon: Factory },
  { label: 'Industrial Automation', icon: Cpu },
  { label: 'AI & Machine Learning', icon: Lightbulb }
];

export default function SearchBar({ onSearch, onClear, isLoading }) {
  const [value, setValue] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (value.trim()) {
      onSearch(value.trim());
    }
  };

  const handleSuggestionClick = (label) => {
    setValue(label);
    onSearch(label);
  };

  const handleClear = () => {
    setValue('');
    onClear();
  };

  return (
    <div className="search-bar-wrapper animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '100%' }}>
      <form onSubmit={handleSubmit} style={{ position: 'relative', width: '100%' }}>
        <div 
          className="glass-panel" 
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '0.5rem 1.25rem',
            borderRadius: '100px',
            border: '1px solid var(--border-color)',
            boxShadow: 'var(--shadow-panel)',
            transition: 'var(--transition-smooth)',
            background: 'var(--bg-surface)',
          }}
          onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--border-hover)'}
          onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--border-color)'}
        >
          <Search size={20} style={{ color: 'var(--text-secondary)', marginRight: '0.75rem', flexShrink: 0 }} />
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Search keywords (e.g. green cement, autonomous robotics...)"
            disabled={isLoading}
            style={{
              width: '100%',
              background: 'none',
              border: 'none',
              outline: 'none',
              color: 'var(--text-primary)',
              fontSize: '1.05rem',
              fontFamily: 'var(--font-body)',
              padding: '0.6rem 0',
            }}
          />
          {value && (
            <button
              type="button"
              onClick={handleClear}
              disabled={isLoading}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '0.25rem',
                borderRadius: '50%',
                transition: 'var(--transition-smooth)',
              }}
              onMouseEnter={(e) => e.currentTarget.style.color = 'var(--text-primary)'}
              onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-secondary)'}
            >
              <X size={18} />
            </button>
          )}
          <button
            type="submit"
            disabled={isLoading || !value.trim()}
            style={{
              marginLeft: '0.75rem',
              background: 'var(--gradient-tech)',
              border: 'none',
              color: '#ffffff',
              padding: '0.6rem 1.5rem',
              borderRadius: '100px',
              fontWeight: 600,
              fontSize: '0.9rem',
              fontFamily: 'var(--font-title)',
              cursor: 'pointer',
              boxShadow: '0 4px 12px var(--glow-primary)',
              transition: 'var(--transition-bounce)',
              opacity: (isLoading || !value.trim()) ? 0.6 : 1,
              pointerEvents: (isLoading || !value.trim()) ? 'none' : 'auto',
            }}
            onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.03)'}
            onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
          >
            Search
          </button>
        </div>
      </form>
      
      {/* Suggestions tags */}
      <div 
        style={{ 
          display: 'flex', 
          flexWrap: 'wrap', 
          gap: '0.5rem', 
          alignItems: 'center',
          fontSize: '0.85rem',
          color: 'var(--text-secondary)' 
        }}
      >
        <span>Popular suggestions:</span>
        {SUGGESTIONS.map((item, idx) => {
          const Icon = item.icon;
          return (
            <button
              key={idx}
              type="button"
              onClick={() => handleSuggestionClick(item.label)}
              disabled={isLoading}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-color)',
                borderRadius: '100px',
                padding: '0.3rem 0.8rem',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                transition: 'var(--transition-smooth)',
                fontFamily: 'var(--font-body)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--bg-surface-hover)';
                e.currentTarget.style.borderColor = 'var(--color-primary)';
                e.currentTarget.style.color = 'var(--color-primary)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'var(--bg-surface)';
                e.currentTarget.style.borderColor = 'var(--border-color)';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }}
            >
              <Icon size={12} style={{ color: 'var(--color-primary)' }} />
              {item.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

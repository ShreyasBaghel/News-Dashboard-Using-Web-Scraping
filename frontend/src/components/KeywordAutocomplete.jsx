import React, { useState, useEffect, useRef } from 'react';
import { Search, X, Tag, Factory, Leaf, Lightbulb, Cpu, Briefcase } from 'lucide-react';

const POPULAR_SUGGESTIONS = [
  { label: 'cement', icon: Leaf },
  { label: 'decarbonization', icon: Leaf },
  { label: 'automation', icon: Cpu },
  { label: 'ai', icon: Lightbulb },
  { label: 'robotics', icon: Lightbulb },
  { label: 'manufacturing', icon: Factory }
];

export default function KeywordAutocomplete({ onSearch, onClear, isLoading }) {
  const [inputValue, setInputValue] = useState('');
  const [chips, setChips] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef(null);
  const inputRef = useRef(null);

  // Debounced suggestion fetching
  useEffect(() => {
    if (inputValue.trim().length < 2) {
      setSuggestions([]);
      return;
    }

    const delayDebounce = setTimeout(async () => {
      try {
        const query = encodeURIComponent(inputValue.trim().toLowerCase());
        const response = await fetch(`http://localhost:8000/api/keywords/suggest?q=${query}`);
        if (response.ok) {
          const data = await response.json();
          // Filter out keywords that are already in chips
          const filtered = (data.suggestions || []).filter(item => !chips.includes(item));
          setSuggestions(filtered);
        }
      } catch (err) {
        console.error('Error fetching suggestions:', err);
      }
    }, 250);

    return () => clearTimeout(delayDebounce);
  }, [inputValue, chips]);

  // Handle click outside to close suggestions dropdown
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectKeyword = (keyword) => {
    const kw = keyword.toLowerCase().trim();
    if (kw && !chips.includes(kw)) {
      setChips([...chips, kw]);
    }
    setInputValue('');
    setSuggestions([]);
    setShowDropdown(false);
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  const handleRemoveChip = (chipToRemove) => {
    const updated = chips.filter(c => c !== chipToRemove);
    setChips(updated);
    if (updated.length === 0) {
      onClear();
    }
  };

  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    if (chips.length > 0) {
      // Send comma-separated list of chips to the onSearch handler
      onSearch(chips.join(','));
    }
  };

  const handleClearAll = () => {
    setChips([]);
    setInputValue('');
    setSuggestions([]);
    setShowDropdown(false);
    onClear();
  };

  return (
    <div className="search-bar-wrapper animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '100%', position: 'relative' }}>
      
      {/* Search Input Box */}
      <form onSubmit={handleSubmit} style={{ position: 'relative', width: '100%' }}>
        <div 
          className="glass-panel" 
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            padding: '0.5rem 1.25rem',
            borderRadius: '100px',
            border: '1px solid var(--border-color)',
            boxShadow: 'var(--shadow-panel)',
            transition: 'var(--transition-smooth)',
            background: 'var(--bg-surface)',
            gap: '0.5rem'
          }}
          onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--border-hover)'}
          onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--border-color)'}
        >
          <Search size={20} style={{ color: 'var(--text-secondary)', flexShrink: 0 }} />
          
          {/* Chips list inside the search bar */}
          {chips.map((chip, idx) => (
            <span 
              key={idx}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.25rem',
                background: 'linear-gradient(135deg, rgba(26, 58, 92, 0.08) 0%, rgba(26, 58, 92, 0.15) 100%)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-color)',
                padding: '0.2rem 0.6rem',
                borderRadius: '100px',
                fontSize: '0.8rem',
                fontWeight: 600,
                animation: 'fadeInUp 0.3s ease'
              }}
            >
              <Tag size={10} style={{ color: 'var(--color-primary)' }} />
              {chip}
              <button
                type="button"
                onClick={() => handleRemoveChip(chip)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  padding: '0.1rem',
                  borderRadius: '50%',
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = 'var(--color-accent)'}
                onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-secondary)'}
              >
                <X size={10} />
              </button>
            </span>
          ))}

          {/* Autocomplete Input text box */}
          <input
            type="text"
            ref={inputRef}
            value={inputValue}
            onChange={(e) => {
              setInputValue(e.target.value);
              setShowDropdown(true);
            }}
            onFocus={() => setShowDropdown(true)}
            placeholder={chips.length === 0 ? "Type to search keywords (e.g. cement, robotics, ai...)" : "Add more keywords..."}
            disabled={isLoading}
            style={{
              flexGrow: 1,
              minWidth: '150px',
              background: 'none',
              border: 'none',
              outline: 'none',
              color: 'var(--text-primary)',
              fontSize: '1.05rem',
              fontFamily: 'var(--font-body)',
              padding: '0.6rem 0',
            }}
          />

          {/* Clear button if chips or text is present */}
          {(chips.length > 0 || inputValue) && (
            <button
              type="button"
              onClick={handleClearAll}
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

          {/* Search trigger button */}
          <button
            type="submit"
            disabled={isLoading || chips.length === 0}
            style={{
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
              opacity: (isLoading || chips.length === 0) ? 0.5 : 1,
              pointerEvents: (isLoading || chips.length === 0) ? 'none' : 'auto',
            }}
            onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.03)'}
            onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
          >
            Search
          </button>
        </div>

        {/* Floating Dropdown for Autocomplete suggestions */}
        {showDropdown && suggestions.length > 0 && (
          <div 
            ref={dropdownRef}
            className="glass-panel"
            style={{
              position: 'absolute',
              top: '100%',
              left: '1.5rem',
              right: '1.5rem',
              marginTop: '0.5rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)',
              background: 'var(--bg-surface)',
              boxShadow: '0 10px 25px rgba(0,0,0,0.15)',
              zIndex: 100,
              maxHeight: '250px',
              overflowY: 'auto',
              padding: '0.5rem 0'
            }}
          >
            {suggestions.map((item, idx) => (
              <div 
                key={idx}
                onClick={() => handleSelectKeyword(item)}
                style={{
                  padding: '0.6rem 1.25rem',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  color: 'var(--text-primary)',
                  transition: 'background 0.2s ease',
                  fontFamily: 'var(--font-body)'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--bg-surface-hover)';
                  e.currentTarget.style.color = 'var(--color-primary)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = 'var(--text-primary)';
                }}
              >
                <Search size={14} style={{ color: 'var(--text-muted)' }} />
                <span>{item}</span>
              </div>
            ))}
          </div>
        )}
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
        {POPULAR_SUGGESTIONS.map((item, idx) => {
          const Icon = item.icon;
          const isSelected = chips.includes(item.label);
          return (
            <button
              key={idx}
              type="button"
              onClick={() => handleSelectKeyword(item.label)}
              disabled={isLoading || isSelected}
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
                opacity: isSelected ? 0.5 : 1,
                pointerEvents: isSelected ? 'none' : 'auto'
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

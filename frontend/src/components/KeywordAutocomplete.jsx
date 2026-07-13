import React, { useState, useEffect, useRef } from 'react';
import { Search, X, Tag } from 'lucide-react';

const API_BASE_URL = 
  (import.meta.env && (import.meta.env.VITE_API_URL || import.meta.env.REACT_APP_API_URL)) || 
  'http://localhost:8000/api';

export default function KeywordAutocomplete({ onSearch, onClear, isLoading, chips = [], setChips }) {
  const [inputValue, setInputValue] = useState('');
  const [allTags, setAllTags] = useState([]);
  const [showPopup, setShowPopup] = useState(false);
  const popupRef = useRef(null);
  const inputRef = useRef(null);

  // Fetch all keywords for the grid on focus / startup
  useEffect(() => {
    const fetchAllTags = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/keywords/suggest?q=`);
        if (response.ok) {
          const data = await response.json();
          setAllTags(data.suggestions || []);
        }
      } catch (err) {
        console.error('Error fetching keyword suggestions:', err);
      }
    };
    fetchAllTags();
  }, [chips]);

  // Handle click outside to close the searchable tag popup
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (popupRef.current && !popupRef.current.contains(e.target)) {
        setShowPopup(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectKeyword = (keyword) => {
    const kw = keyword.trim();
    if (kw) {
      setChips([kw]);
      onSearch(kw);
    }
    setInputValue('');
    setShowPopup(false);
  };

  const handleRemoveChip = (chipToRemove) => {
    const updated = chips.filter(c => c !== chipToRemove);
    setChips(updated);
    if (updated.length === 0) {
      onClear();
    }
  };

  const handleClearAll = () => {
    setChips([]);
    setInputValue('');
    setShowPopup(false);
    onClear();
  };

  // Filter tags in real-time as user types
  const filteredTags = allTags.filter(tag => 
    tag.toLowerCase().includes(inputValue.toLowerCase().strip ? inputValue.toLowerCase().strip() : inputValue.toLowerCase())
  );

  return (
    <div className="search-bar-wrapper animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%', position: 'relative' }}>
      
      {/* Search Input Box */}
      <div style={{ width: '100%' }}>
        <div 
          className="glass-panel" 
          onClick={() => {
            if (inputRef.current) inputRef.current.focus();
            setShowPopup(true);
          }}
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
            gap: '0.5rem',
            position: 'relative',
            cursor: 'text'
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
              }}
            >
              <Tag size={10} style={{ color: 'var(--color-primary)' }} />
              {chip}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleRemoveChip(chip);
                }}
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
              setShowPopup(true);
            }}
            onFocus={() => setShowPopup(true)}
            placeholder={chips.length === 0 ? "Click to search tags or type to filter..." : "Add search filters..."}
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
              onClick={(e) => {
                e.stopPropagation();
                handleClearAll();
              }}
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
            >
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      {/* SEARCH POPUP (3-Column Grid) */}
      {showPopup && (
        <div 
          ref={popupRef}
          className="glass-panel tags-search-popup animate-fade-in"
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            marginTop: '0.5rem',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-color)',
            zIndex: 9999,
          }}
        >
          {/* Inner Search Box */}
          <div style={{ display: 'flex', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem', marginBottom: '1rem' }}>
            <Search size={16} style={{ color: 'var(--text-muted)', marginRight: '0.5rem' }} />
            <input 
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Search keywords..."
              style={{
                border: 'none',
                background: 'none',
                outline: 'none',
                width: '100%',
                color: 'var(--text-primary)',
                fontSize: '0.95rem'
              }}
            />
          </div>

          {/* 3-Column CSS Grid list */}
          {filteredTags.length > 0 ? (
            <div className="tags-grid">
              {filteredTags.map((item, idx) => (
                <div 
                  key={idx}
                  onClick={() => handleSelectKeyword(item)}
                  className="tag-item"
                >
                  <span>{item}</span>
                  <Tag size={12} style={{ color: 'var(--color-secondary)' }} />
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              No matching keywords found in the cache.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

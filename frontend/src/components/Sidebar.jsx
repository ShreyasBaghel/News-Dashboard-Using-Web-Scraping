import React, { useState } from 'react';
import { Tag, Filter, ChevronLeft, ChevronRight, Hash, FolderOpen } from 'lucide-react';

export default function Sidebar({ 
  keywordCounts = {}, 
  chips = [], 
  onSelectKeyword, 
  isOpen, 
  onToggle 
}) {
  const [filterText, setFilterText] = useState('');

  // 1. Process and sort keywords alphabetically
  const keywords = Object.entries(keywordCounts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => a.name.localeCompare(b.name));

  // 2. Filter keywords locally
  const filteredKeywords = keywords.filter(kw => 
    kw.name.toLowerCase().includes(filterText.toLowerCase().trim())
  );

  // 3. Group by first letter for alphabetical list
  const groupings = {};
  filteredKeywords.forEach(kw => {
    const firstLetter = kw.name.charAt(0).toUpperCase();
    const groupKey = /^[A-Z]/.test(firstLetter) ? firstLetter : '#';
    if (!groupings[groupKey]) {
      groupings[groupKey] = [];
    }
    groupings[groupKey].push(kw);
  });

  const sortedGroupKeys = Object.keys(groupings).sort();

  return (
    <>
      {/* Sidebar Container */}
      <aside 
        className={`glass-panel sidebar-container ${isOpen ? 'open' : 'collapsed'}`}
        style={{
          width: isOpen ? '280px' : '0px',
          minWidth: isOpen ? '280px' : '0px',
          flexShrink: 0,
          position: 'relative',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          background: 'var(--bg-surface)',
          borderColor: isOpen ? 'var(--border-color)' : 'transparent',
          boxShadow: isOpen ? 'var(--shadow-panel)' : 'none',
          zIndex: 90
        }}
      >
        {/* Sidebar Header */}
        <div 
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '1.25rem 1.5rem',
            borderBottom: '1px solid var(--border-color)',
            background: 'linear-gradient(180deg, rgba(26, 58, 92, 0.03) 0%, rgba(26, 58, 92, 0) 100%)',
            flexShrink: 0
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--color-primary)' }}>
            <FolderOpen size={18} style={{ color: 'var(--color-secondary)' }} />
            <h2 style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-title)', margin: 0, color: 'var(--text-primary)' }}>
              Explore Topics
            </h2>
          </div>
          <button
            onClick={onToggle}
            style={{
              background: 'rgba(0, 0, 0, 0.03)',
              border: '1px solid var(--border-color)',
              borderRadius: '6px',
              padding: '0.25rem',
              cursor: 'pointer',
              color: 'var(--text-secondary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'var(--transition-bounce)'
            }}
            title="Collapse Sidebar"
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(0, 0, 0, 0.08)';
              e.currentTarget.style.transform = 'scale(1.05)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(0, 0, 0, 0.03)';
              e.currentTarget.style.transform = 'scale(1)';
            }}
          >
            <ChevronLeft size={16} />
          </button>
        </div>

        {/* Sidebar Tag Filter Box */}
        <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--border-color)', flexShrink: 0 }}>
          <div 
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '0.45rem 0.85rem',
              background: 'var(--bg-surface-hover)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              gap: '0.5rem',
              transition: 'var(--transition-smooth)'
            }}
          >
            <Filter size={14} style={{ color: 'var(--text-muted)' }} />
            <input 
              type="text" 
              placeholder="Filter topics..."
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              style={{
                background: 'none',
                border: 'none',
                outline: 'none',
                width: '100%',
                fontSize: '0.85rem',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-body)'
              }}
            />
          </div>
        </div>

        {/* Tag List Container */}
        <div 
          className="sidebar-scrollable-content"
          style={{
            flexGrow: 1,
            overflowY: 'auto',
            padding: '1.25rem'
          }}
        >
          {sortedGroupKeys.length > 0 ? (
            sortedGroupKeys.map(groupKey => (
              <div key={groupKey} style={{ marginBottom: '1.5rem' }}>
                {/* Alphabetical Section Divider */}
                <div 
                  style={{
                    fontSize: '0.75rem',
                    fontWeight: 800,
                    color: 'var(--color-secondary)',
                    letterSpacing: '0.05em',
                    marginBottom: '0.5rem',
                    borderBottom: '1px dashed var(--border-color)',
                    paddingBottom: '0.2rem',
                    fontFamily: 'var(--font-title)'
                  }}
                >
                  {groupKey}
                </div>
                {/* List of Chips */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                  {groupings[groupKey].map(kw => {
                    const isSelected = chips.includes(kw.name);
                    return (
                      <button
                        key={kw.name}
                        onClick={() => onSelectKeyword(kw.name)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          width: '100%',
                          padding: '0.45rem 0.75rem',
                          borderRadius: '6px',
                          border: isSelected ? '1px solid var(--color-secondary)' : '1px solid transparent',
                          background: isSelected 
                            ? 'linear-gradient(135deg, rgba(226, 160, 43, 0.08) 0%, rgba(226, 160, 43, 0.15) 100%)' 
                            : 'transparent',
                          color: isSelected ? 'var(--color-secondary)' : 'var(--text-primary)',
                          fontWeight: isSelected ? 700 : 500,
                          fontSize: '0.85rem',
                          fontFamily: 'var(--font-body)',
                          cursor: 'pointer',
                          textAlign: 'left',
                          transition: 'var(--transition-smooth)'
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected) {
                            e.currentTarget.style.background = 'var(--bg-surface-hover)';
                            e.currentTarget.style.color = 'var(--color-primary)';
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) {
                            e.currentTarget.style.background = 'transparent';
                            e.currentTarget.style.color = 'var(--text-primary)';
                          }
                        }}
                      >
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <Tag size={12} style={{ color: isSelected ? 'var(--color-secondary)' : 'var(--text-muted)', flexShrink: 0 }} />
                          {kw.name}
                        </span>
                        <span 
                          style={{
                            fontSize: '0.7rem',
                            padding: '0.1rem 0.4rem',
                            borderRadius: '100px',
                            background: isSelected ? 'rgba(226, 160, 43, 0.2)' : 'var(--border-color)',
                            color: isSelected ? 'var(--color-secondary)' : 'var(--text-secondary)',
                            fontWeight: 600
                          }}
                        >
                          {kw.count}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))
          ) : (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem', padding: '2rem 0', fontStyle: 'italic' }}>
              No matching topics
            </div>
          )}
        </div>
      </aside>

      {/* Floating Closed Tab (to reopen sidebar on desktop) */}
      {!isOpen && (
        <button
          onClick={onToggle}
          className="glass-panel"
          style={{
            position: 'fixed',
            left: '1.5rem',
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-color)',
            borderRadius: '0 8px 8px 0',
            padding: '1.25rem 0.4rem',
            cursor: 'pointer',
            color: 'var(--text-primary)',
            boxShadow: 'var(--shadow-panel)',
            zIndex: 89,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'var(--transition-bounce)'
          }}
          title="Expand Topics Sidebar"
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'var(--bg-surface-hover)';
            e.currentTarget.style.color = 'var(--color-primary)';
            e.currentTarget.style.transform = 'translateY(-50%) scale(1.05)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'var(--bg-surface)';
            e.currentTarget.style.color = 'var(--text-primary)';
            e.currentTarget.style.transform = 'translateY(-50%) scale(1)';
          }}
        >
          <ChevronRight size={18} />
        </button>
      )}
    </>
  );
}

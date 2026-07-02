import React, { useState } from 'react';
import { ExternalLink, ChevronDown, ChevronUp, Calendar, Newspaper, Info } from 'lucide-react';

export default function ArticleCard({ article }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const { title, url, source, published_at, summary, scraped_content, company, is_pinned } = article;

  // Format date nicely
  const formatDate = (dateStr) => {
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return dateStr;
    }
  };

  const getBrandStyles = () => {
    if (!is_pinned || !company) return null;
    const normCompany = company.toUpperCase();
    if (normCompany.includes('NVIDIA')) {
      return {
        bg: 'rgba(22, 163, 74, 0.08)',
        border: 'rgba(22, 163, 74, 0.2)',
        text: '#15803d',
        glow: 'rgba(22, 163, 74, 0.1)',
        label: 'NVIDIA'
      };
    } else if (normCompany.includes('MICROSOFT')) {
      return {
        bg: 'rgba(37, 99, 235, 0.08)',
        border: 'rgba(37, 99, 235, 0.2)',
        text: '#1d4ed8',
        glow: 'rgba(37, 99, 235, 0.1)',
        label: 'Microsoft'
      };
    } else if (normCompany.includes('OPENAI')) {
      return {
        bg: 'rgba(124, 58, 237, 0.08)',
        border: 'rgba(124, 58, 237, 0.2)',
        text: '#6d28d9',
        glow: 'rgba(124, 58, 237, 0.1)',
        label: 'OpenAI'
      };
    }
    return {
      bg: 'rgba(26, 58, 92, 0.05)',
      border: 'rgba(26, 58, 92, 0.15)',
      text: 'var(--color-primary)',
      glow: 'var(--glow-primary)',
      label: company
    };
  };

  const brand = getBrandStyles();

  return (
    <div 
      className="glass-panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        position: 'relative',
        overflow: 'hidden',
        background: brand ? 'rgba(26, 58, 92, 0.02)' : 'var(--bg-surface)',
        borderColor: brand ? brand.border : 'var(--border-color)',
        boxShadow: brand ? `0 10px 30px -10px ${brand.glow}` : 'var(--shadow-panel)',
        transition: 'var(--transition-smooth)',
        animation: 'fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-5px)';
        e.currentTarget.style.borderColor = brand ? brand.border : 'var(--border-hover)';
        if (brand) {
          e.currentTarget.style.boxShadow = `0 15px 35px -5px ${brand.glow}`;
        } else {
          e.currentTarget.style.boxShadow = '0 15px 35px -5px var(--glow-primary)';
        }
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.borderColor = brand ? brand.border : 'var(--border-color)';
        if (brand) {
          e.currentTarget.style.boxShadow = `0 10px 30px -10px ${brand.glow}`;
        } else {
          e.currentTarget.style.boxShadow = 'var(--shadow-panel)';
        }
      }}
    >
      {/* Brand Pill for Pinned Tech articles */}
      {brand && (
        <div 
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '3px',
            background: brand.text
          }}
        />
      )}

      {/* Card Body */}
      <div style={{ padding: '1.25rem', flexGrow: 1, display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
        
        {/* Metadata row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.75rem' }}>
          <span 
            style={{ 
              display: 'inline-flex', 
              alignItems: 'center', 
              gap: '0.25rem', 
              color: brand ? brand.text : 'var(--text-secondary)',
              fontWeight: 600,
              background: brand ? brand.bg : 'rgba(26, 58, 92, 0.03)',
              padding: '0.25rem 0.6rem',
              borderRadius: '4px',
              border: brand ? `1px solid ${brand.border}` : '1px solid var(--border-color)'
            }}
          >
            <Newspaper size={12} />
            {source}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', color: 'var(--text-muted)' }}>
            <Calendar size={12} />
            {formatDate(published_at)}
          </span>
        </div>

        {/* Title */}
        <h3 style={{ fontSize: '1.15rem', lineHeight: 1.4, fontWeight: 600, margin: 0, fontFamily: 'var(--font-title)' }}>
          <a 
            href={url} 
            target="_blank" 
            rel="noopener noreferrer"
            style={{
              color: 'var(--text-primary)',
              textDecoration: 'none',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.5rem',
              transition: 'var(--transition-smooth)'
            }}
            onMouseEnter={(e) => e.currentTarget.style.color = brand ? brand.text : 'var(--color-primary)'}
            onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-primary)'}
          >
            <span style={{ flexGrow: 1 }}>{title}</span>
            <ExternalLink size={14} style={{ flexShrink: 0, marginTop: '3px' }} />
          </a>
        </h3>

        {/* Brand Label Badge */}
        {brand && (
          <div style={{ display: 'flex' }}>
            <span 
              style={{
                fontSize: '0.7rem',
                fontWeight: 800,
                letterSpacing: '0.05em',
                textTransform: 'uppercase',
                color: '#ffffff',
                backgroundColor: brand.text,
                padding: '0.15rem 0.5rem',
                borderRadius: '100px',
                boxShadow: `0 2px 8px ${brand.glow}`
              }}
            >
              {brand.label} Key Update
            </span>
          </div>
        )}

        {/* AI Summary */}
        <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
          {summary}
        </p>
      </div>

      {/* Accordion expander for scraped text */}
      {scraped_content && (
        <div style={{ borderTop: '1px solid var(--border-color)', background: 'rgba(26, 58, 92, 0.02)' }}>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0.75rem 1.25rem',
              background: 'none',
              border: 'none',
              color: 'var(--text-secondary)',
              fontSize: '0.8rem',
              fontWeight: 500,
              cursor: 'pointer',
              outline: 'none',
              transition: 'var(--transition-smooth)'
            }}
            onMouseEnter={(e) => e.currentTarget.style.color = 'var(--text-primary)'}
            onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-secondary)'}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <Info size={12} style={{ color: brand ? brand.text : 'var(--color-secondary)' }} />
              {isExpanded ? 'Hide Raw Scraped Text' : 'View Scraped Paragraphs'}
            </span>
            {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {isExpanded && (
            <div 
              style={{ 
                padding: '0 1.25rem 1.25rem 1.25rem', 
                fontSize: '0.8rem', 
                color: 'var(--text-muted)', 
                lineHeight: 1.5,
                maxHeight: '180px',
                overflowY: 'auto'
              }}
            >
              <div style={{ fontStyle: 'italic', borderLeft: '2px solid var(--border-color)', paddingLeft: '0.75rem' }}>
                "{scraped_content}"
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

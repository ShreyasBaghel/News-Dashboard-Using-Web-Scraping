import React, { useState } from 'react';
import { ExternalLink, ChevronDown, ChevronUp, Calendar, Newspaper, Info, Pin, Sparkles, Cpu } from 'lucide-react';

export default function ArticleCard({ article, onTogglePin }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isIntelExpanded, setIsIntelExpanded] = useState(false);
  const { 
    title, url, source, published_at, summary, scraped_content, company, is_pinned,
    executive_summary, business_implications, ai_relevance, industry_categories, innovation_score, sentiment
  } = article;

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
      {/* Pinned Ribbon */}
      {is_pinned && (
        <div 
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            background: 'linear-gradient(135deg, #e2a02b 0%, #b45309 100%)',
            color: '#ffffff',
            fontSize: '0.65rem',
            fontWeight: 800,
            padding: '0.15rem 0.5rem',
            borderBottomRightRadius: '4px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            zIndex: 9,
            letterSpacing: '0.05em',
            textTransform: 'uppercase'
          }}
        >
          Pinned
        </div>
      )}

      {/* Pin Toggle Button */}
      {onTogglePin && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onTogglePin(article);
          }}
          style={{
            position: 'absolute',
            top: '0.5rem',
            right: '0.5rem',
            background: is_pinned ? 'rgba(226, 160, 43, 0.15)' : 'rgba(0, 0, 0, 0.03)',
            border: is_pinned ? '1px solid rgba(226, 160, 43, 0.4)' : '1px solid var(--border-color)',
            borderRadius: '50%',
            width: '28px',
            height: '28px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            color: is_pinned ? '#e2a02b' : 'var(--text-muted)',
            zIndex: 10,
            transition: 'all 0.2s ease',
            outline: 'none'
          }}
          title={is_pinned ? "Unpin Article" : "Pin Article"}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = 'scale(1.1)';
            e.currentTarget.style.background = is_pinned ? 'rgba(226, 160, 43, 0.25)' : 'rgba(0, 0, 0, 0.08)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'scale(1)';
            e.currentTarget.style.background = is_pinned ? 'rgba(226, 160, 43, 0.15)' : 'rgba(0, 0, 0, 0.03)';
          }}
        >
          <Pin size={13} style={{ transform: is_pinned ? 'rotate(45deg)' : 'none', fill: is_pinned ? '#e2a02b' : 'none' }} />
        </button>
      )}
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

        {/* Clickable keyword tags */}
        {article.keywords && article.keywords.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginTop: '0.5rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>Tags:</span>
            {article.keywords.map((kw, idx) => (
              <span 
                key={idx}
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  padding: '0.15rem 0.5rem',
                  borderRadius: '100px',
                  backgroundColor: 'rgba(226, 160, 43, 0.1)',
                  color: 'var(--color-secondary)',
                  border: '1px solid rgba(226, 160, 43, 0.2)',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease'
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  window.dispatchEvent(new CustomEvent('search-keyword', { detail: kw }));
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--color-secondary)';
                  e.currentTarget.style.color = '#ffffff';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'rgba(226, 160, 43, 0.1)';
                  e.currentTarget.style.color = 'var(--color-secondary)';
                }}
              >
                {kw}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Business Intelligence Accordion */}
      {executive_summary && (
        <div style={{ borderTop: '1px solid var(--border-color)', background: 'linear-gradient(180deg, rgba(226, 160, 43, 0.02) 0%, rgba(226, 160, 43, 0.05) 100%)' }}>
          <button
            onClick={() => setIsIntelExpanded(!isIntelExpanded)}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0.75rem 1.25rem',
              background: 'none',
              border: 'none',
              color: 'var(--color-secondary)',
              fontSize: '0.85rem',
              fontWeight: 700,
              cursor: 'pointer',
              outline: 'none',
              transition: 'var(--transition-smooth)'
            }}
            onMouseEnter={(e) => e.currentTarget.style.color = 'var(--text-primary)'}
            onMouseLeave={(e) => e.currentTarget.style.color = 'var(--color-secondary)'}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Sparkles size={14} style={{ fill: 'currentColor' }} />
              Business Intelligence Insights
            </span>
            {isIntelExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {isIntelExpanded && (
            <div style={{ padding: '0 1.25rem 1.25rem 1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              
              {/* Sentiment & Innovation Score */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', fontWeight: 700 }}>
                  <span style={{ color: 'var(--text-muted)' }}>Sentiment:</span>
                  <span 
                    style={{
                      padding: '0.15rem 0.6rem',
                      borderRadius: '100px',
                      textTransform: 'uppercase',
                      fontSize: '0.65rem',
                      letterSpacing: '0.03em',
                      backgroundColor: 
                        sentiment === 'Positive' ? 'rgba(34, 197, 94, 0.15)' :
                        sentiment === 'Negative' ? 'rgba(239, 68, 68, 0.15)' :
                        sentiment === 'Mixed' ? 'rgba(168, 85, 247, 0.15)' :
                        'rgba(148, 163, 184, 0.15)',
                      color:
                        sentiment === 'Positive' ? '#22c55e' :
                        sentiment === 'Negative' ? '#ef4444' :
                        sentiment === 'Mixed' ? '#a855f7' :
                        'var(--text-muted)',
                      border: 
                        sentiment === 'Positive' ? '1px solid rgba(34, 197, 94, 0.3)' :
                        sentiment === 'Negative' ? '1px solid rgba(239, 68, 68, 0.3)' :
                        sentiment === 'Mixed' ? '1px solid rgba(168, 85, 247, 0.3)' :
                        '1px solid rgba(148, 163, 184, 0.3)'
                    }}
                  >
                    {sentiment}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', fontWeight: 700, marginLeft: 'auto' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Innovation:</span>
                  <span 
                    style={{
                      padding: '0.15rem 0.5rem',
                      borderRadius: '4px',
                      background: 'linear-gradient(135deg, #e2a02b 0%, #b45309 100%)',
                      color: '#ffffff',
                      fontSize: '0.7rem'
                    }}
                  >
                    {innovation_score}/100
                  </span>
                </div>
              </div>

              {/* Categories */}
              {industry_categories && industry_categories.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>Categories:</span>
                  {industry_categories.map((cat, idx) => (
                    <span 
                      key={idx}
                      style={{
                        fontSize: '0.65rem',
                        fontWeight: 600,
                        padding: '0.1rem 0.45rem',
                        borderRadius: '4px',
                        backgroundColor: 'var(--border-color)',
                        color: 'var(--text-secondary)',
                        border: '1px solid rgba(0,0,0,0.03)'
                      }}
                    >
                      {cat}
                    </span>
                  ))}
                </div>
              )}

              {/* Executive Summary */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', borderLeft: '2px solid var(--color-secondary)', paddingLeft: '0.75rem' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Executive Summary</span>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
                  {executive_summary}
                </p>
              </div>

              {/* Implications */}
              {business_implications && business_implications.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Business Implications</span>
                  <ul style={{ paddingLeft: '1.1rem', margin: 0, display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                    {business_implications.map((imp, idx) => (
                      <li key={idx} style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                        {imp}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* AI Tech */}
              {ai_relevance && (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.35rem', padding: '0.5rem 0.75rem', borderRadius: '6px', backgroundColor: 'rgba(26, 58, 92, 0.03)', border: '1px solid var(--border-color)' }}>
                  <Cpu size={14} style={{ color: brand ? brand.text : 'var(--color-primary)', marginTop: '2px', flexShrink: 0 }} />
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                    <strong style={{ color: 'var(--text-primary)' }}>AI Tech:</strong> {ai_relevance}
                  </div>
                </div>
              )}

            </div>
          )}
        </div>
      )}

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

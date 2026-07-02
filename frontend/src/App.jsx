import React, { useState, useEffect } from 'react';
import { fetchDashboardData, forceRefreshDashboard } from './api/newsApi';
import SearchBar from './components/SearchBar';
import RefreshTimer from './components/RefreshTimer';
import PinnedSection from './components/PinnedSection';
import ArticleGrid from './components/ArticleGrid';
import ArticleCard from './components/ArticleCard';
import { Newspaper, AlertCircle, Building2, Terminal, Sun, Moon } from 'lucide-react';

const LoadingSkeleton = () => (
  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1.5rem', width: '100%' }}>
    {[1, 2, 3, 4, 5, 6].map(i => (
      <div 
        key={i} 
        className="glass-panel shimmer" 
        style={{ 
          height: '240px', 
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--border-color)'
        }}
      />
    ))}
  </div>
);

export default function App() {
  const [keyword, setKeyword] = useState('');
  const [payload, setPayload] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState(null);
  
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('theme') || 'light';
  });

  useEffect(() => {
    document.body.className = `${theme}-theme`;
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  const loadFeed = async (searchWord = '') => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchDashboardData(searchWord);
      setPayload(data);
    } catch (err) {
      setError(err.message || 'Failed to load news dashboard payload.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleForceRefresh = async () => {
    setIsRefreshing(true);
    setError(null);
    try {
      const data = await forceRefreshDashboard(keyword);
      setPayload(data);
    } catch (err) {
      setError(err.message || 'Refresh request failed.');
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    loadFeed();
  }, []);

  const handleSearch = (term) => {
    setKeyword(term);
    loadFeed(term);
  };

  const handleClear = () => {
    setKeyword('');
    loadFeed('');
  };

  return (
    <div className="app-container">
      {/* Premium Header */}
      <header 
        className="glass-panel animate-fade-in"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '1.25rem 2rem',
          borderRadius: 'var(--radius-lg)',
          background: 'linear-gradient(90deg, #1a3a5c 0%, #254a75 100%)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          color: '#ffffff'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
          <div 
            style={{
              background: '#ffffff',
              padding: '0.6rem',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 15px rgba(0, 0, 0, 0.15)'
            }}
          >
            <Building2 size={24} style={{ color: '#1a3a5c' }} />
          </div>
          <div>
            <h1 style={{ fontSize: '1.45rem', lineHeight: 1.1, fontFamily: 'var(--font-title)', color: '#ffffff' }}>
              Dalmia Cement <span style={{ color: '#e2a02b' }}>News Intel Hub</span>
            </h1>
            <span style={{ fontSize: '0.75rem', color: '#e2e8f0' }}>
              AI-Powered Competitor & Technology Aggregator
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              color: '#ffffff',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '0.5rem',
              borderRadius: '50%',
              transition: 'var(--transition-bounce)',
            }}
            title={`Switch to ${theme === 'light' ? 'Dark' : 'Light'} Mode`}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.25)';
              e.currentTarget.style.transform = 'scale(1.1)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
              e.currentTarget.style.transform = 'scale(1)';
            }}
          >
            {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'rgba(255, 255, 255, 0.7)' }}>
            <Terminal size={14} style={{ color: '#e2a02b' }} />
            <span style={{ fontSize: '0.75rem', fontFamily: 'monospace' }}>POC Build v1.0.0</span>
          </div>
        </div>
      </header>

      {/* Main Search Panel */}
      <SearchBar onSearch={handleSearch} onClear={handleClear} isLoading={isLoading || isRefreshing} theme={theme} />

      {/* Refresh Scheduler Status */}
      {payload && (
        <RefreshTimer 
          nextUpdate={payload.next_update} 
          onManualRefresh={handleForceRefresh} 
          isLoading={isRefreshing} 
        />
      )}

      {/* Errors display */}
      {error && (() => {
        const isConnError = error.startsWith("ConnectionError:");
        const displayError = isConnError ? error.replace("ConnectionError:", "").trim() : error;
        return (
          <div 
            className="glass-panel animate-fade-in"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              padding: '1rem 1.5rem',
              borderColor: isConnError 
                ? (theme === 'light' ? '#fee2e2' : 'rgba(239, 68, 68, 0.3)')
                : (theme === 'light' ? '#fde68a' : 'rgba(245, 158, 11, 0.3)'),
              background: isConnError
                ? (theme === 'light' ? '#fef2f2' : 'rgba(239, 68, 68, 0.1)')
                : (theme === 'light' ? '#fffbeb' : 'rgba(245, 158, 11, 0.05)'),
              color: isConnError
                ? (theme === 'light' ? '#991b1b' : '#fca5a5')
                : (theme === 'light' ? '#b45309' : '#fcd34d'),
              borderRadius: 'var(--radius-md)'
            }}
          >
            <AlertCircle size={20} style={{ flexShrink: 0 }} />
            <div style={{ fontSize: '0.9rem' }}>
              <strong>{isConnError ? 'Connection Error:' : 'Pipeline Sync Warning:'}</strong> {displayError}
            </div>
          </div>
        );
      })()}

      {/* Loading Skeleton */}
      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div className="glass-panel shimmer" style={{ height: '30px', width: '200px', borderRadius: '4px' }} />
            <LoadingSkeleton />
          </div>
        </div>
      ) : (
        payload && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
            
            {/* Pinned Section */}
            {payload.pinned_articles && payload.pinned_articles.length > 0 && (
              <PinnedSection articles={payload.pinned_articles} />
            )}

            {/* General Section */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                <Newspaper size={18} style={{ color: 'var(--color-primary)' }} />
                <h2 style={{ fontSize: '1.25rem', fontFamily: 'var(--font-title)' }}>
                  {keyword ? `Topic Intelligence: "${payload.keyword}"` : 'General Manufacturing & Industry Feed'}
                </h2>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                  Showing {payload.articles ? payload.articles.length : 0} summarized articles
                </span>
              </div>

              {payload.articles && payload.articles.length > 0 ? (
                <ArticleGrid>
                  {payload.articles.map((article, idx) => (
                    <ArticleCard key={`general-${idx}`} article={article} />
                  ))}
                </ArticleGrid>
              ) : (
                <div 
                  className="glass-panel"
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '4rem 2rem',
                    textAlign: 'center',
                    color: 'var(--text-secondary)',
                    gap: '0.75rem'
                  }}
                >
                  <Newspaper size={48} style={{ color: 'var(--text-muted)' }} />
                  <h3 style={{ fontSize: '1.15rem', color: 'var(--text-primary)' }}>No matching articles found</h3>
                  <p style={{ fontSize: '0.9rem', maxWidth: '400px' }}>
                    All raw articles for this topic were either filtered due to the 7-day de-duplication rules, or search results were empty.
                  </p>
                </div>
              )}
            </div>

          </div>
        )
      )}
    </div>
  );
}

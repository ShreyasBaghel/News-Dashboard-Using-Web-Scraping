import React, { useState, useEffect } from 'react';
import { fetchDashboardData, forceRefreshDashboard } from './api/newsApi';
import KeywordAutocomplete from './components/KeywordAutocomplete';
import RefreshTimer from './components/RefreshTimer';
import PinnedSection from './components/PinnedSection';
import ArticleGrid from './components/ArticleGrid';
import ArticleCard from './components/ArticleCard';
import DalmiaLogo from './components/DalmiaLogo';
import { Newspaper, AlertCircle, Building2, Terminal, Sun, Moon, Search, Zap } from 'lucide-react';

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
  const [normalFeed, setNormalFeed] = useState([]);
  const [searchResults, setSearchResults] = useState([]);
  const [pinnedArticles, setPinnedArticles] = useState([]);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [activeView, setActiveView] = useState('feed'); // 'feed', 'search', 'pinned'
  const [lastUpdated, setLastUpdated] = useState('');
  const [nextUpdate, setNextUpdate] = useState('');

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

  const loadInitialData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchDashboardData('');
      setNormalFeed(data.articles || []);
      setPinnedArticles(data.pinned_articles || []);
      setLastUpdated(data.last_updated || '');
      setNextUpdate(data.next_update || '');
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
      const data = await forceRefreshDashboard(searchKeyword);
      if (searchKeyword) {
        setSearchResults(data.articles || []);
      } else {
        setNormalFeed(data.articles || []);
      }
      if (data.pinned_articles) {
        setPinnedArticles(data.pinned_articles);
      }
      setLastUpdated(data.last_updated || '');
      setNextUpdate(data.next_update || '');
    } catch (err) {
      setError(err.message || 'Refresh request failed.');
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  const handleSearch = async (term) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchDashboardData(term);
      setSearchResults(data.articles || []);
      setSearchKeyword(term);
      if (data.pinned_articles && data.pinned_articles.length > 0) {
        setPinnedArticles(data.pinned_articles);
      }
      if (data.last_updated) setLastUpdated(data.last_updated);
      if (data.next_update) setNextUpdate(data.next_update);
      setActiveView('search');
    } catch (err) {
      setError(err.message || 'Search failed.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClear = () => {
    setSearchKeyword('');
    setSearchResults([]);
    setActiveView('feed');
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
              padding: '0.4rem 0.8rem',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <DalmiaLogo height="32px" />
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
      <KeywordAutocomplete onSearch={handleSearch} onClear={handleClear} isLoading={isLoading || isRefreshing} />

      {/* Navigation Tabs */}
      <div className="nav-tabs-container glass-panel animate-fade-in">
        {[
          { id: 'feed', label: 'Home Feed', icon: Newspaper, count: normalFeed.length },
          { id: 'search', label: 'Search Results', icon: Search, count: searchKeyword ? searchResults.length : null },
          { id: 'pinned', label: 'Pinned Intel', icon: Zap, count: pinnedArticles.length }
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeView === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveView(tab.id)}
              className={`nav-tab-button ${isActive ? 'active' : ''}`}
            >
              <Icon size={18} style={{ color: isActive ? '#ffffff' : 'var(--color-primary)', flexShrink: 0 }} />
              <span>{tab.label}</span>
              {tab.count !== null && (
                <span className="nav-tab-badge">
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Refresh Scheduler Status */}
      {nextUpdate && (
        <RefreshTimer 
          nextUpdate={nextUpdate} 
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

      {/* Loading Skeleton / Main View Content */}
      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div className="glass-panel shimmer" style={{ height: '30px', width: '200px', borderRadius: '4px' }} />
            <LoadingSkeleton />
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
          
          {/* Feed View */}
          {activeView === 'feed' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                <Newspaper size={18} style={{ color: 'var(--color-primary)' }} />
                <h2 style={{ fontSize: '1.25rem', fontFamily: 'var(--font-title)' }}>
                  General Manufacturing & Industry Feed
                </h2>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                  Showing {normalFeed.length} summarized articles
                </span>
              </div>

              {normalFeed.length > 0 ? (
                <ArticleGrid>
                  {normalFeed.map((article, idx) => (
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
                  <h3 style={{ fontSize: '1.15rem', color: 'var(--text-primary)' }}>No articles found</h3>
                  <p style={{ fontSize: '0.9rem', maxWidth: '400px' }}>
                    The industry feed is currently empty.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Search View */}
          {activeView === 'search' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                <Search size={18} style={{ color: 'var(--color-primary)' }} />
                <h2 style={{ fontSize: '1.25rem', fontFamily: 'var(--font-title)' }}>
                  {searchKeyword ? `Topic Intelligence: "${searchKeyword}"` : 'Search Results'}
                </h2>
                {searchKeyword && (
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                    Showing {searchResults.length} summarized articles
                  </span>
                )}
              </div>

              {!searchKeyword ? (
                <div className="glass-panel welcome-panel animate-fade-in">
                  <Search size={48} style={{ color: 'var(--text-muted)' }} />
                  <h3 style={{ fontSize: '1.25rem', color: 'var(--text-primary)', fontFamily: 'var(--font-title)' }}>
                    AI Search Desk
                  </h3>
                  <p style={{ fontSize: '0.95rem', maxWidth: '450px', lineHeight: 1.6 }}>
                    Enter industry, technology, or competitor keywords in the search bar above to fetch targeted real-time intelligence reports.
                  </p>
                </div>
              ) : searchResults.length > 0 ? (
                <ArticleGrid>
                  {searchResults.map((article, idx) => (
                    <ArticleCard key={`search-${idx}`} article={article} />
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
          )}

          {/* Pinned View */}
          {activeView === 'pinned' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {pinnedArticles.length > 0 ? (
                <PinnedSection articles={pinnedArticles} />
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
                  <Zap size={48} style={{ color: 'var(--text-muted)' }} />
                  <h3 style={{ fontSize: '1.15rem', color: 'var(--text-primary)' }}>No pinned articles</h3>
                  <p style={{ fontSize: '0.9rem', maxWidth: '400px' }}>
                    There are no high-impact company articles pinned at the moment.
                  </p>
                </div>
              )}
            </div>
          )}

        </div>
      )}
    </div>
  );
}

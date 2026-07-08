const API_BASE_URL = 
  (import.meta.env && (import.meta.env.VITE_API_URL || import.meta.env.REACT_APP_API_URL)) || 
  'http://localhost:8000/api';

/**
 * Fetch latest dashboard payload (general feed + pinned company feeds)
 * @param {string} [keyword] Optional keyword search term
 * @returns {Promise<object>} Dashboard payload object
 */
export async function fetchDashboardData(keyword = '') {
  const url = new URL(`${API_BASE_URL}/news`);
  if (keyword) {
    url.searchParams.append('keyword', keyword);
  }
  
  try {
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Failed to fetch news feed (Status ${response.status})`);
    }
    
    return await response.json();
  } catch (err) {
    // Intercept network/CORS connectivity failures
    if (err.name === 'TypeError' || err.message === 'Failed to fetch' || err.message.includes('fetch')) {
      throw new Error("ConnectionError: Could not reach the backend — is the server running?");
    }
    throw err;
  }
}

/**
 * Force manual pipeline execution, bypassing SQLite cache
 * @param {string} [keyword] Optional keyword search term to refresh
 * @returns {Promise<object>} Refreshed dashboard payload object
 */
export async function forceRefreshDashboard(keyword = '') {
  try {
    const response = await fetch(`${API_BASE_URL}/news/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ keyword: keyword || null }),
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Failed to refresh news feed (Status ${response.status})`);
    }
    
    return await response.json();
  } catch (err) {
    // Intercept network/CORS connectivity failures
    if (err.name === 'TypeError' || err.message === 'Failed to fetch' || err.message.includes('fetch')) {
      throw new Error("ConnectionError: Could not reach the backend — is the server running?");
    }
    throw err;
  }
}

/**
 * Pin an article to the pinned-articles store
 * @param {object} article The article object to pin
 * @param {string} [keyword] The currently active search keyword
 * @returns {Promise<object>} Updated dashboard payload
 */
export async function pinArticle(article, keyword = '') {
  try {
    const response = await fetch(`${API_BASE_URL}/news/pin`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ article, keyword: keyword || null }),
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Failed to pin article (Status ${response.status})`);
    }
    
    return await response.json();
  } catch (err) {
    if (err.name === 'TypeError' || err.message === 'Failed to fetch' || err.message.includes('fetch')) {
      throw new Error("ConnectionError: Could not reach the backend — is the server running?");
    }
    throw err;
  }
}

/**
 * Unpin an article from the pinned-articles store
 * @param {string} url The URL of the article to unpin
 * @param {string} [keyword] The currently active search keyword
 * @returns {Promise<object>} Updated dashboard payload
 */
export async function unpinArticle(url, keyword = '') {
  try {
    const response = await fetch(`${API_BASE_URL}/news/unpin`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ url, keyword: keyword || null }),
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Failed to unpin article (Status ${response.status})`);
    }
    
    return await response.json();
  } catch (err) {
    if (err.name === 'TypeError' || err.message === 'Failed to fetch' || err.message.includes('fetch')) {
      throw new Error("ConnectionError: Could not reach the backend — is the server running?");
    }
    throw err;
  }
}


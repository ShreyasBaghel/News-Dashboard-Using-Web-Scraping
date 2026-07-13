const API_BASE_URL = 
  (import.meta.env && (import.meta.env.VITE_API_URL || import.meta.env.REACT_APP_API_URL)) || 
  'http://localhost:8000/api';

/**
 * Gets the authorization role header from localStorage.
 * @returns {object} headers object containing X-User-Role
 */
function getAuthHeaders() {
  const role = localStorage.getItem('user_role') || 'employee';
  return {
    'X-User-Role': role
  };
}

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
        ...getAuthHeaders()
      },
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Failed to fetch news feed (Status ${response.status})`);
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
 * Force manual pipeline execution, bypassing SQLite cache (Admin only)
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
        ...getAuthHeaders()
      },
      body: JSON.stringify({ keyword: keyword || null }),
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Failed to refresh news feed (Status ${response.status})`);
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
        ...getAuthHeaders()
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
        ...getAuthHeaders()
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

/**
 * Fetch list of monitored search keywords (Admin only)
 * @returns {Promise<object>} list of monitored keywords
 */
export async function fetchMonitoredKeywords() {
  try {
    const response = await fetch(`${API_BASE_URL}/admin/keywords`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        ...getAuthHeaders()
      }
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to fetch monitored keywords');
    }
    return await response.json();
  } catch (err) {
    if (err.name === 'TypeError' || err.message === 'Failed to fetch' || err.message.includes('fetch')) {
      throw new Error("ConnectionError: Could not reach the backend");
    }
    throw err;
  }
}

/**
 * Add a new keyword to the monitored list (Admin only)
 * @param {string} keyword The keyword to add
 * @returns {Promise<object>} Update response
 */
export async function addMonitoredKeyword(keyword) {
  try {
    const response = await fetch(`${API_BASE_URL}/admin/keywords`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        ...getAuthHeaders()
      },
      body: JSON.stringify({ keyword })
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to add monitored keyword');
    }
    return await response.json();
  } catch (err) {
    if (err.name === 'TypeError' || err.message === 'Failed to fetch' || err.message.includes('fetch')) {
      throw new Error("ConnectionError: Could not reach the backend");
    }
    throw err;
  }
}

/**
 * Remove a keyword from the monitored list (Admin only)
 * @param {string} keyword The keyword to remove
 * @returns {Promise<object>} Update response
 */
export async function removeMonitoredKeyword(keyword) {
  try {
    const url = new URL(`${API_BASE_URL}/admin/keywords`);
    url.searchParams.append('keyword', keyword);
    
    const response = await fetch(url.toString(), {
      method: 'DELETE',
      headers: {
        'Accept': 'application/json',
        ...getAuthHeaders()
      }
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to remove monitored keyword');
    }
    return await response.json();
  } catch (err) {
    if (err.name === 'TypeError' || err.message === 'Failed to fetch' || err.message.includes('fetch')) {
      throw new Error("ConnectionError: Could not reach the backend");
    }
    throw err;
  }
}

/**
 * Manually trigger pipeline execution in the background (Admin only)
 * @returns {Promise<object>} Execution status
 */
export async function runPipelineInBackground() {
  try {
    const response = await fetch(`${API_BASE_URL}/admin/pipeline/run`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        ...getAuthHeaders()
      }
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to trigger pipeline run');
    }
    return await response.json();
  } catch (err) {
    if (err.name === 'TypeError' || err.message === 'Failed to fetch' || err.message.includes('fetch')) {
      throw new Error("ConnectionError: Could not reach the backend");
    }
    throw err;
  }
}

/**
 * Fetch current status of pipeline execution (Admin only)
 * @returns {Promise<object>} status
 */
export async function fetchPipelineStatus() {
  try {
    const response = await fetch(`${API_BASE_URL}/admin/pipeline/status`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        ...getAuthHeaders()
      }
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to fetch pipeline status');
    }
    return await response.json();
  } catch (err) {
    if (err.name === 'TypeError' || err.message === 'Failed to fetch' || err.message.includes('fetch')) {
      throw new Error("ConnectionError: Could not reach the backend");
    }
    throw err;
  }
}

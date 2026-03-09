import { useState, useEffect } from 'react';

/**
 * Custom hook for API calls with error handling
 * @param {string} url - API endpoint URL
 * @param {object} options - Fetch options (method, headers, body, etc)
 * @param {number} pollInterval - Auto-refresh interval in ms (0 = no polling)
 * @returns {object} { data, loading, error }
 */
export function useApi(url, options = {}, pollInterval = 0) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    let timeoutId = null;

    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);

        const response = await fetch(url, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
          ...options,
        });

        if (!response.ok) {
          throw new Error(`API Error: ${response.status} ${response.statusText}`);
        }

        const result = await response.json();

        if (isMounted) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || 'Failed to fetch data');
          setData(null);
        }
        console.error(`API Error [${url}]:`, err);
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    // Initial fetch
    fetchData();

    // Setup polling if interval specified
    if (pollInterval > 0) {
      const poll = () => {
        timeoutId = setTimeout(() => {
          fetchData();
          poll();
        }, pollInterval);
      };
      poll();
    }

    // Cleanup
    return () => {
      isMounted = false;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [url, options, pollInterval]);

  return { data, loading, error };
}

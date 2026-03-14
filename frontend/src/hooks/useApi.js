import { useCallback, useEffect, useMemo, useState } from 'react';

/**
 * Custom hook for API calls with error handling
 * @param {string} url - API endpoint URL
 * @param {object} options - Fetch options (method, headers, body, etc)
 * @param {number} pollInterval - Auto-refresh interval in ms (0 = no polling)
 * @returns {object} { data, loading, error, refetch }
 */
export function useApi(url, options = {}, pollInterval = 0) {
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const optionsKey = useMemo(() => {
    try {
      return JSON.stringify(options || {});
    } catch {
      return '{}';
    }
  }, [options]);

  const refetch = useCallback(() => {
    setRefreshToken((prev) => prev + 1);
  }, []);

  useEffect(() => {
    let isMounted = true;

    const fetchData = async () => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort();
      }, 5000);

      try {
        setLoading(true);
        setError(null);

        const parsedOptions = optionsKey ? JSON.parse(optionsKey) : {};
        const response = await fetch(url, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
          ...parsedOptions,
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`API Error: ${response.status} ${response.statusText}`);
        }

        const result = await response.json();

        if (isMounted) {
          setData(result ?? {});
          setError(null);
        }
      } catch (err) {
        const message = err?.name === 'AbortError'
          ? 'Request timed out after 5 seconds'
          : (err?.message || 'Failed to fetch data');

        if (isMounted) {
          setError(message);
          setData({});
        }
        console.error(`API Error [${url}]:`, err);
      } finally {
        clearTimeout(timeoutId);
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    // Initial fetch
    fetchData();

    // Setup polling if interval specified
    const intervalId = pollInterval > 0
      ? setInterval(fetchData, pollInterval)
      : null;

    // Cleanup
    return () => {
      isMounted = false;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [url, optionsKey, pollInterval, refreshToken]);

  return { data, loading, error, refetch };
}

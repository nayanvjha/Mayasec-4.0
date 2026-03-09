import { useMemo } from 'react';

/**
 * useEventFilter
 * 
 * Custom hook for filtering events based on multiple criteria.
 * Applies filters with AND logic (all filters must match).
 * 
 * Filters:
 * - severity: Exact match (or 'ALL' for no filter)
 * - eventType: Exact match (or 'ALL' for no filter)
 * - sourceIp: Substring match (case-insensitive)
 * - timeWindow: Events within last X minutes
 * 
 * Parameters:
 * - events: Array of event objects
 * - filters: {
 *     severity: 'ALL' | 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO',
 *     eventType: 'ALL' | string,
 *     sourceIp: string (substring),
 *     timeWindow: number (minutes)
 *   }
 * 
 * Returns:
 * - filteredEvents: Filtered array
 * - filterStats: { total, filtered, hidden }
 */
const useEventFilter = (events = [], filters = {}) => {
  const {
    severity = 'ALL',
    eventType = 'ALL',
    sourceIp = '',
    timeWindow = 30,
  } = filters;

  // Memoize filtered results
  const { filteredEvents, filterStats } = useMemo(() => {
    if (!events || events.length === 0) {
      return {
        filteredEvents: [],
        filterStats: { total: 0, filtered: 0, hidden: 0 },
      };
    }

    const now = Date.now();
    const timeWindowMs = timeWindow * 60 * 1000; // Convert minutes to milliseconds

    const filtered = events.filter(event => {
      // Severity filter
      if (severity !== 'ALL') {
        const eventSeverity = String(event.severity || '').toUpperCase();
        if (eventSeverity !== severity.toUpperCase()) {
          return false;
        }
      }

      // Event type filter
      if (eventType !== 'ALL') {
        const normalizedEventType = String(event.event_type || '').toLowerCase();
        if (normalizedEventType !== eventType.toLowerCase()) {
          return false;
        }
      }

      // Source IP filter (substring match, case-insensitive)
      if (sourceIp && sourceIp.trim()) {
        const eventSourceIp = String(event.source_ip || '').toLowerCase();
        const filterSourceIp = sourceIp.toLowerCase().trim();
        if (!eventSourceIp.includes(filterSourceIp)) {
          return false;
        }
      }

      // Time window filter
      if (timeWindow > 0) {
        const eventTime = event.timestamp;
        if (eventTime) {
          // Try to parse timestamp
          let eventTimeMs;
          
          if (typeof eventTime === 'string') {
            // ISO string or similar
            eventTimeMs = new Date(eventTime).getTime();
          } else if (typeof eventTime === 'number') {
            // Milliseconds or seconds since epoch
            eventTimeMs = eventTime > 1e10 ? eventTime : eventTime * 1000;
          } else {
            // Can't parse timestamp, include event
            return true;
          }

          // Check if within time window
          if (isNaN(eventTimeMs) || now - eventTimeMs > timeWindowMs) {
            return false;
          }
        }
      }

      return true;
    });

    return {
      filteredEvents: filtered,
      filterStats: {
        total: events.length,
        filtered: filtered.length,
        hidden: events.length - filtered.length,
      },
    };
  }, [events, severity, eventType, sourceIp, timeWindow]);

  return {
    filteredEvents,
    filterStats,
  };
};

export default useEventFilter;

/**
 * Helper: Get all unique event types from events array
 */
export const getAvailableEventTypes = (events = []) => {
  const types = new Set();
  events.forEach(event => {
    if (event.event_type) {
      types.add(event.event_type);
    }
  });
  return Array.from(types).sort();
};

/**
 * Helper: Get all unique severities from events array
 */
export const getAvailableSeverities = (events = []) => {
  const severities = new Set();
  events.forEach(event => {
    if (event.severity) {
      severities.add(event.severity.toUpperCase());
    }
  });
  return Array.from(severities).sort();
};

/**
 * Helper: Check if event matches filters
 * Useful for checking incoming events against current filters
 */
export const eventMatchesFilters = (event, filters) => {
  const {
    severity = 'ALL',
    eventType = 'ALL',
    sourceIp = '',
    timeWindow = 30,
  } = filters;

  // Severity filter
  if (severity !== 'ALL') {
    const eventSeverity = String(event.severity || '').toUpperCase();
    if (eventSeverity !== severity.toUpperCase()) {
      return false;
    }
  }

  // Event type filter
  if (eventType !== 'ALL') {
    const normalizedEventType = String(event.event_type || '').toLowerCase();
    if (normalizedEventType !== eventType.toLowerCase()) {
      return false;
    }
  }

  // Source IP filter
  if (sourceIp && sourceIp.trim()) {
    const eventSourceIp = String(event.source_ip || '').toLowerCase();
    const filterSourceIp = sourceIp.toLowerCase().trim();
    if (!eventSourceIp.includes(filterSourceIp)) {
      return false;
    }
  }

  // Time window filter
  if (timeWindow > 0) {
    const eventTime = event.timestamp;
    if (eventTime) {
      let eventTimeMs;
      
      if (typeof eventTime === 'string') {
        eventTimeMs = new Date(eventTime).getTime();
      } else if (typeof eventTime === 'number') {
        eventTimeMs = eventTime > 1e10 ? eventTime : eventTime * 1000;
      } else {
        return true;
      }

      const now = Date.now();
      const timeWindowMs = timeWindow * 60 * 1000;
      
      if (isNaN(eventTimeMs) || now - eventTimeMs > timeWindowMs) {
        return false;
      }
    }
  }

  return true;
};

import { useState, useEffect, useRef } from 'react';

/**
 * Custom hook for raw WebSocket real-time events
 * One-way stream: server → client only
 * 
 * @param {string} apiUrl - Base API URL (e.g., http://localhost:5000)
 * @returns {object} { socket, connected, events, alerts, error }
 */
export function useWebSocket(apiUrl, handlers = {}) {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState(null);
  const [lastAlert, setLastAlert] = useState(null);
  const [lastResponse, setLastResponse] = useState(null);
  const [lastPolicyDecision, setLastPolicyDecision] = useState(null);
  const [responseMode, setResponseMode] = useState(null);
  const [lastResponseDecision, setLastResponseDecision] = useState(null);
  const socketRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const handlersRef = useRef(handlers);

  useEffect(() => {
    handlersRef.current = handlers;
  }, [handlers]);

  useEffect(() => {
    if (!apiUrl) return;

    const allowedTypes = new Set([
      'event_ingested',
      'phase_escalated',
      'alert_created',
      'ip_blocked',
      'ip_unblocked',
      'response_mode',
      'response_decision',
    ]);

    const toWebSocketUrl = (baseUrl) => {
      try {
        const parsed = new URL(baseUrl);
        const protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${parsed.host}/ws/events`;
      } catch {
        return baseUrl.replace(/^http/, 'ws').replace(/\/$/, '') + '/ws/events';
      }
    };

    const connect = () => {
      const wsUrl = toWebSocketUrl(apiUrl);
      const socket = new WebSocket(wsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        console.log('WebSocket connected');
        setConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };

      socket.onclose = () => {
        console.warn('WebSocket disconnected');
        setConnected(false);
        setError('Connection lost. Reconnecting...');

        if (reconnectAttemptsRef.current < 5) {
          reconnectAttemptsRef.current += 1;
          reconnectTimerRef.current = setTimeout(connect, 1000);
        }
      };

      socket.onerror = (err) => {
        console.error('WebSocket connection error:', err);
        setError('Connection error');
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (!payload || !allowedTypes.has(payload.type)) return;

          const normalizeEventData = (raw) => {
            if (!raw || typeof raw !== 'object') return {};
            if (raw.data && typeof raw.data === 'object') {
              return {
                ...raw.data,
                timestamp: raw.data.timestamp || raw.timestamp || payload.timestamp,
                event_type: raw.data.event_type || raw.event_type || raw.type,
                destination: raw.data.destination || raw.destination || payload?.data?.destination,
              };
            }
            return {
              ...raw,
              timestamp: raw.timestamp || payload.timestamp,
              destination: raw.destination || payload?.data?.destination,
            };
          };

          if (payload.type === 'response_mode') {
            setResponseMode(payload.mode || null);
            if (handlersRef.current.onResponseMode) handlersRef.current.onResponseMode(payload.mode);
            return;
          }

          if (payload.type === 'response_decision') {
            setLastResponseDecision(payload);
            if (handlersRef.current.onResponseDecision) handlersRef.current.onResponseDecision(payload);
          }

          const data = payload.data || {};
          if (payload.type === 'event_ingested') {
            const normalized = normalizeEventData(data);
            setEvents((prevEvents) => [normalized, ...prevEvents]);
            if (handlersRef.current.onEvent) handlersRef.current.onEvent(normalized);
          } else if (payload.type === 'alert_created') {
            setAlerts((prevAlerts) => [data, ...prevAlerts]);
            setLastAlert(data);
            if (handlersRef.current.onAlert) handlersRef.current.onAlert(data);
          } else if (payload.type === 'ip_blocked' || payload.type === 'ip_unblocked') {
            setLastResponse(data);
            if (handlersRef.current.onResponse) handlersRef.current.onResponse(data);
          } else if (payload.type === 'phase_escalated') {
            setLastPolicyDecision(data);
            if (handlersRef.current.onPolicyDecision) handlersRef.current.onPolicyDecision(data);
          }
        } catch (parseError) {
          console.warn('Invalid WebSocket payload', parseError);
        }
      };
    };

    connect();

    // Cleanup on unmount
    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, [apiUrl]);

  return {
    socket: socketRef.current,
    connected,
    events,
    alerts,
    error,
    lastAlert,
    lastResponse,
    lastPolicyDecision,
    responseMode,
    lastResponseDecision,
    setEvents,
    setAlerts,
  };
}

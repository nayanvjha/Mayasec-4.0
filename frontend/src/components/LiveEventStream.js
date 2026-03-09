import React, { useState, useEffect, useRef } from 'react';
import './LiveEventStream.css';

/**
 * LiveEventStream Component
 * 
 * Core SOC console component displaying real-time security events.
 * 
 * Props:
 * - events: Array of event objects from WebSocket
 * - connected: Boolean indicating WebSocket connection status
 * - onEventSelect: Callback when analyst selects an event
 * - selectedEventId: ID of currently selected event (for visual marking)
 * - error: Optional error message
 * 
 * Behavior:
 * - Displays newest events first (timestamp DESC)
 * - Updates in real-time via WebSocket (no polling)
 * - Highlights new events on arrival (500ms)
 * - Selected event marked with visual indicator (frozen while new events stream)
 * - Scrollable feed
 * - Color-coded by severity
 * 
 * Investigation Mode:
 * - Selected event remains highlighted even as new events arrive
 * - Analyst can compare new events to selected baseline
 * - New events appear at top, selected event stays marked
 * - Click another event to change selection or click same to deselect
 * 
 * Data Model (Event):
 * {
 *   event_id: string,
 *   timestamp: ISO8601,
 *   source_ip: string,
 *   destination_ip: string,
 *   event_type: string,
 *   threat_score: number (0-100),
 *   severity_level: enum (CRITICAL, HIGH, MEDIUM, LOW),
 *   raw_data: object
 * }
 */

function LiveEventStream({ events = [], connected = false, onEventSelect = null, selectedEventId = null, error = null }) {
  const [highlightedEventId, setHighlightedEventId] = useState(null);
  const [previousEventCount, setPreviousEventCount] = useState(0);
  const streamRef = useRef(null);

  // Highlight new events on arrival
  useEffect(() => {
    if (events && events.length > previousEventCount) {
      // New events arrived
      const newEvent = events[0]; // Newest event
      if (newEvent) {
        const eventId = newEvent.event_id || `event-${newEvent.timestamp}`;
        setHighlightedEventId(eventId);
        
        // Remove highlight after 500ms
        const timer = setTimeout(() => {
          setHighlightedEventId(null);
        }, 500);
        
        return () => clearTimeout(timer);
      }
    }
    setPreviousEventCount(events ? events.length : 0);
  }, [events, previousEventCount]);

  // Auto-scroll to top when new events arrive
  useEffect(() => {
    if (streamRef.current && events && events.length > 0) {
      streamRef.current.scrollTop = 0;
    }
  }, [events]);

  // Render empty state
  if (!events || events.length === 0) {
    return (
      <div className="live-event-stream">
        <div className="stream-header">
          <span className="stream-title">Live Event Stream</span>
          <span className={`connection-status ${connected ? 'connected' : 'disconnected'}`}>
            {connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        <div className="stream-empty">
          <p>Waiting for events...</p>
          <p className="status-message">
            {connected ? 'WebSocket connected. Listening for security events.' : 'Connecting...'}
          </p>
        </div>
      </div>
    );
  }

  // Get severity class for styling
  const getSeverityClass = (severityLevel) => {
    if (!severityLevel) return 'severity-low';
    const level = severityLevel.toLowerCase();
    switch (level) {
      case 'critical':
        return 'severity-critical';
      case 'high':
        return 'severity-high';
      case 'medium':
        return 'severity-medium';
      case 'low':
        return 'severity-low';
      default:
        return 'severity-low';
    }
  };

  // Format timestamp for display
  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  // Get threat level label
  const getThreatLabel = (score) => {
    if (score >= 80) return 'CRITICAL';
    if (score >= 60) return 'HIGH';
    if (score >= 40) return 'MEDIUM';
    return 'LOW';
  };

  return (
    <div className="live-event-stream">
      {/* Header */}
      <div className="stream-header">
        <span className="stream-title">Live Event Stream</span>
        <span className="event-count">{events.length} events</span>
        <span className={`connection-status ${connected ? 'connected' : 'disconnected'}`}>
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      {/* Error state */}
      {error && (
        <div className="stream-error">
          <p>Error: {error}</p>
        </div>
      )}

      {/* Events list */}
      <div className="stream-events" ref={streamRef}>
        {events.map((event) => {
          const eventId = event.event_id || `event-${event.timestamp}`;
          const isHighlighted = eventId === highlightedEventId;
          const isSelected = eventId === selectedEventId;
          const severityClass = getSeverityClass(event.severity_level);
          const threatLabel = getThreatLabel(event.threat_score);

          return (
            <div
              key={eventId}
              className={`event-row ${severityClass} ${isHighlighted ? 'new-event' : ''} ${isSelected ? 'selected-event' : ''}`}
              onClick={() => onEventSelect && onEventSelect(event, isSelected)}
              role="button"
              tabIndex="0"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && onEventSelect) {
                  onEventSelect(event, isSelected);
                }
              }}
            >
              {/* Left: Timestamp */}
              <div className="event-timestamp">
                {formatTime(event.timestamp)}
              </div>

              {/* Center: Event Details */}
              <div className="event-details">
                <span className="event-type">{event.event_type || 'unknown'}</span>
                <span className="source-ip">{event.source_ip || 'N/A'}</span>
                <span className="separator">→</span>
                <span className="dest-ip">{event.destination_ip || 'N/A'}</span>
              </div>

              {/* Right: Threat Score + Severity */}
              <div className="event-threat">
                <span className="threat-score">{event.threat_score}</span>
                <span className="threat-label">{threatLabel}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="stream-footer">
        <p>Tip: Click an event to view details and timeline</p>
      </div>
    </div>
  );
}

export default LiveEventStream;

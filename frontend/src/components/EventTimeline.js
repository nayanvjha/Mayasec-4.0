import React, { useMemo } from 'react';
import './EventTimeline.css';

/**
 * EventTimeline Component
 * 
 * Displays all events correlated to a selected event via correlation_id.
 * Investigation-focused: dense, readable timeline showing attack progression.
 * 
 * Props:
 * - selectedEvent: The event analyst is investigating
 * - allEvents: All events from WebSocket
 * - connected: WebSocket connection status
 * 
 * Behavior:
 * - Filters allEvents by correlation_id
 * - Orders chronologically (earliest first for timeline reading)
 * - Shows time delta between events (escalation tracking)
 * - Shows threat_score progression (attack intensity)
 * - Shows severity level progression (escalation)
 * - Updates live as new related events arrive via WebSocket
 * 
 * Data Requirements:
 * Event must have:
 * - event_id: string (UUID)
 * - correlation_id: string (groups related events)
 * - timestamp: ISO8601 string
 * - event_type: string
 * - threat_score: number (0-100)
 * - severity_level: enum (CRITICAL, HIGH, MEDIUM, LOW)
 * - source_ip: string
 * - destination_ip: string
 * 
 * No Mock Data:
 * - Only displays real events from allEvents array
 * - No placeholder or fake correlation IDs
 * - Empty timeline if no correlations found
 * 
 * No Charts:
 * - Text-based escalation display
 * - Time deltas shown as numeric values
 * - Threat score shown as numbers, not graphs
 * - Severity as color-coded text labels
 * 
 * No Polling:
 * - Updates via WebSocket only
 * - allEvents prop updates trigger re-filter
 * - Timeline re-renders automatically
 */

function EventTimeline({ selectedEvent, allEvents = [], connected = false }) {
  // Filter and sort events by correlation_id
  const timelineEvents = useMemo(() => {
    if (!selectedEvent || !selectedEvent.correlation_id) {
      return [];
    }

    // Filter events matching correlation_id
    const correlated = allEvents.filter(
      (event) => event.correlation_id === selectedEvent.correlation_id
    );

    // Sort chronologically (oldest first for timeline reading)
    const sorted = correlated.sort((a, b) => {
      const timeA = new Date(a.timestamp).getTime();
      const timeB = new Date(b.timestamp).getTime();
      return timeA - timeB;
    });

    return sorted;
  }, [selectedEvent, allEvents]);

  // If no selected event or no correlation_id, show empty state
  if (!selectedEvent || !selectedEvent.correlation_id) {
    return (
      <div className="event-timeline">
        <div className="timeline-header">
          <h3>Attack Timeline</h3>
          <span className="connection-status">
            {connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        <div className="timeline-empty">
          <p>No correlation_id found</p>
          <p className="hint">Select event with correlation_id to view timeline</p>
        </div>
      </div>
    );
  }

  // If no correlated events found
  if (timelineEvents.length === 0) {
    return (
      <div className="event-timeline">
        <div className="timeline-header">
          <h3>Attack Timeline</h3>
          <span className="correlation-id">ID: {selectedEvent.correlation_id.substring(0, 8)}...</span>
        </div>
        <div className="timeline-empty">
          <p>No related events found</p>
          <p className="hint">Waiting for events with this correlation_id</p>
        </div>
      </div>
    );
  }

  // Calculate time delta between events
  const getTimeDelta = (current, previous) => {
    if (!previous) return 'START';
    const curr = new Date(current.timestamp).getTime();
    const prev = new Date(previous.timestamp).getTime();
    const delta = Math.abs(curr - prev);

    if (delta < 1000) return '<1s';
    if (delta < 60000) return `${Math.floor(delta / 1000)}s`;
    if (delta < 3600000) return `${Math.floor(delta / 60000)}m`;
    return `${Math.floor(delta / 3600000)}h`;
  };

  // Get severity class for styling
  const getSeverityClass = (severity) => {
    if (!severity) return 'severity-low';
    const level = severity.toLowerCase();
    return `severity-${level}`;
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

  return (
    <div className="event-timeline">
      {/* Header */}
      <div className="timeline-header">
        <h3>Attack Timeline</h3>
        <span className="event-count">{timelineEvents.length} events</span>
        <span className="correlation-id">
          ID: {selectedEvent.correlation_id.substring(0, 8)}...
        </span>
      </div>

      {/* Timeline visualization */}
      <div className="timeline-container">
        {timelineEvents.map((event, index) => {
          const previousEvent = index > 0 ? timelineEvents[index - 1] : null;
          const timeDelta = getTimeDelta(event.timestamp, previousEvent?.timestamp);
          const severityClass = getSeverityClass(event.severity_level);
          const isSelected = event.event_id === selectedEvent.event_id;

          return (
            <div
              key={event.event_id}
              className={`timeline-event ${severityClass} ${isSelected ? 'selected' : ''}`}
            >
              {/* Time delta from previous event */}
              <div className="timeline-delta">
                <span className="delta-label">{timeDelta}</span>
              </div>

              {/* Timeline marker (circle on the line) */}
              <div className="timeline-marker">
                <div className={`marker-dot ${severityClass}`}></div>
              </div>

              {/* Event details */}
              <div className="timeline-event-details">
                <div className="event-header">
                  <span className="event-time">{formatTime(event.timestamp)}</span>
                  <span className={`event-severity ${severityClass}`}>
                    {event.severity_level}
                  </span>
                </div>

                <div className="event-type-line">
                  <span className="event-type">{event.event_type}</span>
                  <span className="threat-score">
                    Threat: {event.threat_score}
                  </span>
                </div>

                <div className="event-ips">
                  <span className="source-ip">{event.source_ip}</span>
                  <span className="separator">→</span>
                  <span className="dest-ip">{event.destination_ip}</span>
                </div>

                {/* Escalation indicator */}
                {index > 0 && previousEvent && (
                  <div className="escalation-indicator">
                    <span className="delta-threat">
                      Δ{event.threat_score - previousEvent.threat_score > 0 ? '+' : ''}
                      {event.threat_score - previousEvent.threat_score}
                    </span>
                  </div>
                )}

                {/* Show if this is selected event */}
                {isSelected && (
                  <div className="selected-marker">
                    <span className="selected-label">INVESTIGATING</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Timeline footer with escalation summary */}
      {timelineEvents.length > 1 && (
        <div className="timeline-footer">
          <div className="escalation-summary">
            <span className="label">Escalation:</span>
            <span className="value">
              {timelineEvents[0].threat_score} → {timelineEvents[timelineEvents.length - 1].threat_score}
            </span>
          </div>
          <div className="duration-summary">
            <span className="label">Duration:</span>
            <span className="value">
              {(() => {
                const start = new Date(timelineEvents[0].timestamp).getTime();
                const end = new Date(timelineEvents[timelineEvents.length - 1].timestamp).getTime();
                const delta = Math.abs(end - start);
                if (delta < 1000) return '<1s';
                if (delta < 60000) return `${Math.floor(delta / 1000)}s`;
                if (delta < 3600000) return `${Math.floor(delta / 60000)}m`;
                return `${Math.floor(delta / 3600000)}h`;
              })()}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export default EventTimeline;

import React, { useState, useEffect } from 'react';
import './LiveEventFeed.css';

/**
 * LiveEventFeed Component
 * SOC-Style Real-Time Event Stream
 * 
 * Features:
 * - Displays incoming security events in real-time
 * - Color-coded by severity (critical, high, medium, low)
 * - New events highlighted briefly (500ms fade)
 * - Source IPs and attack types prominently displayed
 * - Threat scores with visual escalation
 * - WebSocket-driven updates only (no REST polling)
 * 
 * No artificial animations - only real event arrivals trigger updates
 */
function LiveEventFeed({ events, connected, error, onEventSelect }) {
  const [highlightedEventId, setHighlightedEventId] = useState(null);

  // Highlight new events briefly when they arrive
  useEffect(() => {
    if (events && events.length > 0) {
      const firstEvent = events[0];
      const eventId = firstEvent.event_id || firstEvent.id || `event-${Date.now()}`;
      setHighlightedEventId(eventId);

      // Remove highlight after 500ms
      const timer = setTimeout(() => {
        setHighlightedEventId(null);
      }, 500);

      return () => clearTimeout(timer);
    }
  }, [events]);

  if (!events || events.length === 0) {
    return (
      <div className="live-event-feed panel">
        <div className="feed-header">
          <h3>Live Event Stream</h3>
          <div className="connection-status">
            <span className={`status-indicator ${connected ? 'connected' : 'disconnected'}`} />
            <span className="status-text">
              {connected ? 'Listening' : 'Offline'}
            </span>
          </div>
        </div>
        <div className="event-list empty">
          {error ? (
            <div className="error-message">
              <span className="error-icon">⚠️</span>
              <span>{error}</span>
            </div>
          ) : (
            <div className="waiting-state">
              <div className="waiting-icon"></div>
              <span>Waiting for security events...</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="live-event-feed panel">
      <div className="feed-header">
        <div className="feed-title-section">
          <h3>Live Event Stream</h3>
          <span className="event-count">{events.length} event{events.length !== 1 ? 's' : ''}</span>
        </div>
        <div className="connection-status">
          <span className={`status-indicator ${connected ? 'connected' : 'disconnected'}`} />
          <span className="status-text">
            {connected ? 'Listening' : 'Offline'}
          </span>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
        </div>
      )}

      <div className="event-list">
        {events.map((event, index) => {
          const timestamp = event.timestamp || event.created_at || new Date().toISOString();
          const eventType = event.event_type || event.type || 'UNKNOWN_EVENT';
          const threatLevel = event.threat_level || 'unknown';
          const threatScore = event.threat_score || 0;
          const sourceIp = event.source_ip || event.ip_address || 'Unknown';
          const destIp = event.destination_ip || 'N/A';
          const eventId = event.event_id || event.id || `event-${index}`;
          const isNewEvent = eventId === highlightedEventId;

          return (
            <div
              key={eventId}
              className={`event-item event-${threatLevel} ${isNewEvent ? 'new-event' : ''}`}
              title={`Event ID: ${eventId}`}
              onClick={() => {
                if (typeof onEventSelect === 'function') {
                  onEventSelect(event);
                }
              }}
            >
              {/* Severity Indicator */}
              <div className="event-severity">
                {threatLevel === 'critical' && <span className="severity-badge critical"></span>}
                {threatLevel === 'high' && <span className="severity-badge high"></span>}
                {threatLevel === 'medium' && <span className="severity-badge medium"></span>}
                {threatLevel === 'low' && <span className="severity-badge low"></span>}
                {!['critical', 'high', 'medium', 'low'].includes(threatLevel) && <span className="severity-badge unknown">⚪</span>}
              </div>

              {/* Event Content */}
              <div className="event-content">
                <div className="event-header">
                  <span className="threat-badge" data-level={threatLevel}>
                    {threatLevel.toUpperCase()}
                  </span>
                  <span className="event-type">{eventType}</span>
                  <span className="event-time">
                    {new Date(timestamp).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                      hour12: false
                    })}
                  </span>
                </div>

                {/* IP Information */}
                <div className="event-ips">
                  <span className="ip-badge source">
                    <span className="ip-label">From:</span>
                    <span className="ip-value">{sourceIp}</span>
                  </span>
                  {destIp !== 'N/A' && (
                    <span className="ip-badge dest">
                      <span className="ip-label">To:</span>
                      <span className="ip-value">{destIp}</span>
                    </span>
                  )}
                </div>

                {/* Event Details */}
                <div className="event-details">
                  {event.action && <span className="detail-item">{event.action}</span>}
                  {event.reason && <span className="detail-item">{event.reason}</span>}
                </div>
              </div>

              {/* Threat Score */}
              <div className="threat-score-display">
                <div className="score-container">
                  <span className={`score-value score-${threatLevel}`}>
                    {threatScore}
                  </span>
                  <span className="score-label">Score</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="feed-footer">
        <span className="status-indicator" style={{
          backgroundColor: connected ? '#3fb950' : '#f85149'
        }} />
        <span className="footer-text">
          {connected ? 'Real-time streaming via WebSocket' : 'Connection lost'}
        </span>
      </div>
    </div>
  );
}

export default LiveEventFeed;

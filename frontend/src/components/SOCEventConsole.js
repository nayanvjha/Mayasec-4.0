/**
 * SOC Event Console Component
 * 
 * Main container for the MAYASEC SOC investigation interface.
 * 
 * Architecture:
 * - Event-driven updates only (WebSocket/Socket.IO)
 * - No REST polling for live data
 * - No static metric cards or charts
 * - No summary aggregations
 * - Raw event stream primary focus
 * 
 * Data Flow:
 * 1. WebSocket delivers events in real-time
 * 2. Events displayed in live stream (newest first)
 * 3. Analyst selects event for investigation
 * 4. Detail/timeline views load on demand
 * 5. Analyst makes decision (mark alert, escalate, etc.)
 * 
 * Props:
 * - apiUrl: Backend API endpoint
 * - connected: WebSocket connection status
 * - events: Array of real-time events from WebSocket
 * - alerts: Array of real-time alerts from WebSocket
 * - error: Connection error state
 * - onEventSelect: Callback when analyst selects event
 */

import React, { useState } from 'react';
import LiveEventStream from './LiveEventStream';
import EventTimeline from './EventTimeline';
import './SOCEventConsole.css';

function SOCEventConsole({
  apiUrl = 'http://localhost:5000',
  connected = false,
  events = [],
  alerts = [],
  error = null,
  onEventSelect = null,
}) {
  const [selectedEvent, setSelectedEvent] = useState(null);

  const handleEventSelect = (event, isCurrentlySelected) => {
    // Toggle selection: if clicking same event, deselect; otherwise select new event
    if (isCurrentlySelected) {
      setSelectedEvent(null);
    } else {
      setSelectedEvent(event);
      if (onEventSelect) {
        onEventSelect(event);
      }
    }
  };

  return (
    <div className="soc-event-console">
      {/* Main Console Layout */}
      <div className="console-layout">
        {/* Left: Live Event Stream (Primary View) */}
        <div className="console-stream-panel">
          <LiveEventStream
            events={events}
            connected={connected}
            onEventSelect={handleEventSelect}
            selectedEventId={selectedEvent?.event_id || null}
            error={error}
          />
        </div>

        {/* Right: Investigation Panel (Details + Timeline) */}
        <div className={`console-investigation-panel ${selectedEvent ? 'investigation-active' : ''}`}>
          {selectedEvent ? (
            <>
              {/* Event Details Section */}
              <div className="investigation-details">
                <div className="details-header">
                  <h3>Investigating Event</h3>
                  <button
                    className="close-button"
                    onClick={() => setSelectedEvent(null)}
                    title="Deselect event (close details)"
                  >
                    ✕
                  </button>
                </div>

                <div className="details-content">
                  <div className="detail-section">
                    <span className="label">Event ID:</span>
                    <span className="value">{selectedEvent.event_id}</span>
                  </div>

                  <div className="detail-section">
                    <span className="label">Timestamp:</span>
                    <span className="value">{selectedEvent.timestamp}</span>
                  </div>

                  <div className="detail-section">
                    <span className="label">Type:</span>
                    <span className="value">{selectedEvent.event_type}</span>
                  </div>

                  <div className="detail-section">
                    <span className="label">Source:</span>
                    <span className="value">{selectedEvent.source_ip}</span>
                  </div>

                  <div className="detail-section">
                    <span className="label">Destination:</span>
                    <span className="value">{selectedEvent.destination_ip}</span>
                  </div>

                  <div className="detail-section">
                    <span className="label">Threat Score:</span>
                    <span className="value">{selectedEvent.threat_score}</span>
                  </div>

                  <div className="detail-section">
                    <span className="label">Severity:</span>
                    <span className="value">{selectedEvent.severity_level}</span>
                  </div>

                  {selectedEvent.correlation_id && (
                    <div className="detail-section">
                      <span className="label">Correlation ID:</span>
                      <span className="value">{selectedEvent.correlation_id.substring(0, 16)}...</span>
                    </div>
                  )}

                  {selectedEvent.alert_id && (
                    <div className="detail-section">
                      <span className="label">Alert ID:</span>
                      <span className="value">{selectedEvent.alert_id}</span>
                    </div>
                  )}

                  {selectedEvent.raw_data && (
                    <div className="detail-section raw-data">
                      <span className="label">Raw Data:</span>
                      <pre className="value">
                        {JSON.stringify(selectedEvent.raw_data, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>

              {/* Timeline Section (if correlation_id exists) */}
              {selectedEvent.correlation_id && (
                <div className="investigation-timeline">
                  <EventTimeline
                    selectedEvent={selectedEvent}
                    allEvents={events}
                    connected={connected}
                  />
                </div>
              )}
            </>
          ) : (
            <div className="no-selection">
              <p>Click an event to investigate</p>
              <p className="hint">Selection freezes while new events stream</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default SOCEventConsole;

import React, { useState } from 'react';
import './OperatorContextPanel.css';

/**
 * OperatorContextPanel
 * 
 * Displays comprehensive event context for SOC operators.
 * Read-only display of:
 * - Raw log payload
 * - Parsed fields
 * - Detection reason
 * - Severity reasoning
 * - Correlation explanation
 * 
 * Updates when selected event changes.
 * Supports copy-to-clipboard for all sections.
 */
const OperatorContextPanel = ({ selectedEvent }) => {
  const [copiedSection, setCopiedSection] = useState(null);

  if (!selectedEvent) {
    return (
      <div className="operator-context-panel">
        <div className="context-empty">
          Select an event to view operator context
        </div>
      </div>
    );
  }

  /**
   * Copy section content to clipboard
   */
  const handleCopy = (section, content) => {
    navigator.clipboard.writeText(content).then(() => {
      setCopiedSection(section);
      setTimeout(() => setCopiedSection(null), 2000);
    });
  };

  /**
   * Format JSON for display
   */
  const formatJSON = (obj) => {
    try {
      return JSON.stringify(obj, null, 2);
    } catch (e) {
      return String(obj);
    }
  };

  /**
   * Extract raw payload
   * Raw log is the original event data as received
   */
  const rawPayload = selectedEvent.raw_log || selectedEvent;
  const rawPayloadStr = formatJSON(rawPayload);

  /**
   * Extract parsed fields
   * Exclude system fields, include domain-specific fields
   */
  const getParsedFields = () => {
    const excluded = [
      'event_id',
      'correlation_id',
      'timestamp',
      'raw_log',
      'type',
      'severity',
      'detection_reason',
      'severity_reasoning',
      'correlation_explanation'
    ];

    const parsed = {};
    Object.entries(selectedEvent).forEach(([key, value]) => {
      if (!excluded.includes(key)) {
        parsed[key] = value;
      }
    });

    return parsed;
  };

  const parsedFields = getParsedFields();
  const parsedFieldsStr = formatJSON(parsedFields);

  /**
   * Extract detection reason
   * Why this event triggered detection
   */
  const detectionReason = selectedEvent.detection_reason || 'No detection reason provided';

  /**
   * Extract severity reasoning
   * Why this event was assigned its severity level
   */
  const severityReasoning = selectedEvent.severity_reasoning || 
    `Event assigned severity level: ${selectedEvent.severity || 'unknown'}`;

  /**
   * Extract correlation explanation
   * How this event relates to others via correlation_id
   */
  const correlationExplanation = selectedEvent.correlation_explanation ||
    `Correlation ID: ${selectedEvent.correlation_id || 'Not correlated'}`;

  return (
    <div className="operator-context-panel">
      {/* Raw Log Payload Section */}
      <div className="context-section">
        <div className="section-header">
          <h4>Raw Log Payload</h4>
          <button
            className={`copy-btn ${copiedSection === 'raw' ? 'copied' : ''}`}
            onClick={() => handleCopy('raw', rawPayloadStr)}
            title="Copy to clipboard"
          >
            {copiedSection === 'raw' ? '✓ Copied' : 'Copy'}
          </button>
        </div>
        <pre className="section-content raw-payload">
          {rawPayloadStr}
        </pre>
      </div>

      {/* Parsed Fields Section */}
      <div className="context-section">
        <div className="section-header">
          <h4>Parsed Fields</h4>
          <button
            className={`copy-btn ${copiedSection === 'parsed' ? 'copied' : ''}`}
            onClick={() => handleCopy('parsed', parsedFieldsStr)}
            title="Copy to clipboard"
          >
            {copiedSection === 'parsed' ? '✓ Copied' : 'Copy'}
          </button>
        </div>
        <pre className="section-content parsed-fields">
          {parsedFieldsStr}
        </pre>
      </div>

      {/* Detection Reason Section */}
      <div className="context-section">
        <div className="section-header">
          <h4>Detection Reason</h4>
          <button
            className={`copy-btn ${copiedSection === 'detection' ? 'copied' : ''}`}
            onClick={() => handleCopy('detection', detectionReason)}
            title="Copy to clipboard"
          >
            {copiedSection === 'detection' ? '✓ Copied' : 'Copy'}
          </button>
        </div>
        <div className="section-content detection-reason">
          {detectionReason}
        </div>
      </div>

      {/* Severity Reasoning Section */}
      <div className="context-section">
        <div className="section-header">
          <h4>Severity Reasoning</h4>
          <button
            className={`copy-btn ${copiedSection === 'severity' ? 'copied' : ''}`}
            onClick={() => handleCopy('severity', severityReasoning)}
            title="Copy to clipboard"
          >
            {copiedSection === 'severity' ? '✓ Copied' : 'Copy'}
          </button>
        </div>
        <div className="section-content severity-reasoning">
          {severityReasoning}
        </div>
      </div>

      {/* Correlation Explanation Section */}
      <div className="context-section">
        <div className="section-header">
          <h4>Correlation Explanation</h4>
          <button
            className={`copy-btn ${copiedSection === 'correlation' ? 'copied' : ''}`}
            onClick={() => handleCopy('correlation', correlationExplanation)}
            title="Copy to clipboard"
          >
            {copiedSection === 'correlation' ? '✓ Copied' : 'Copy'}
          </button>
        </div>
        <div className="section-content correlation-explanation">
          {correlationExplanation}
        </div>
      </div>

      {/* Event Metadata Footer */}
      <div className="context-footer">
        <div className="metadata">
          <span className="meta-item">
            <strong>Event ID:</strong> {selectedEvent.event_id}
          </span>
          <span className="meta-item">
            <strong>Timestamp:</strong> {selectedEvent.timestamp}
          </span>
          <span className="meta-item">
            <strong>Severity:</strong> <span className={`severity-badge severity-${selectedEvent.severity?.toLowerCase()}`}>
              {selectedEvent.severity}
            </span>
          </span>
        </div>
      </div>
    </div>
  );
};

export default OperatorContextPanel;

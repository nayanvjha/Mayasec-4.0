/**
 * @deprecated FROZEN - Do not modify, refactor, or enhance
 * 
 * This component is part of the legacy dashboard architecture.
 * Status: DEPRECATED as of January 15, 2026
 * 
 * Reason: Alert summary list and REST polling patterns are not
 * compatible with the new SOC Event Console architecture.
 * 
 * Migration: This component will be removed when the new SOC Console
 * is fully integrated. Do NOT invest development time in this code.
 */

import React from 'react';
import { useApi } from '../hooks/useApi';
import './AlertsPanel.css';

function AlertsPanel({ apiUrl, limit = 20, pollInterval = 30000 }) {
  const { data: response, loading, error } = useApi(
    `${apiUrl}/api/v1/alerts?limit=${limit}`,
    {},
    pollInterval
  );

  const alerts = response?.data || response?.alerts || [];

  if (error) {
    return (
      <div className="alerts-panel panel panel-error">
        <h3>Recent Alerts</h3>
        <div className="error-message">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="alerts-panel panel panel-loading">
        <h3>Recent Alerts</h3>
        <div className="loading-indicator">Loading...</div>
      </div>
    );
  }

  if (!alerts || alerts.length === 0) {
    return (
      <div className="alerts-panel panel panel-empty">
        <h3>Recent Alerts</h3>
        <div className="empty-state">No alerts at this time</div>
      </div>
    );
  }

  return (
    <div className="alerts-panel panel">
      <h3>Recent Alerts ({alerts.length})</h3>
      
      <div className="alerts-list">
        {alerts.map((alert, index) => (
          <div key={alert.id || index} className={`alert-item alert-${getSeverityClass(alert.severity)}`}>
            <div className="alert-header">
              <div className="alert-title-container">
                <span className={`alert-severity-badge severity-${getSeverityClass(alert.severity)}`}>
                  {alert.severity ? alert.severity.toUpperCase() : 'UNKNOWN'}
                </span>
                <span className="alert-title">
                  {alert.title || alert.type || alert.name || 'Alert'}
                </span>
              </div>
              <span className="alert-timestamp">
                {formatTime(alert.timestamp || alert.created_at)}
              </span>
            </div>

            {alert.description && (
              <div className="alert-description">
                {alert.description}
              </div>
            )}

            <div className="alert-details">
              {alert.source_ip && (
                <div className="detail-item">
                  <span className="detail-label">Source IP:</span>
                  <code className="detail-code">{alert.source_ip}</code>
                </div>
              )}

              {alert.destination_ip && (
                <div className="detail-item">
                  <span className="detail-label">Destination IP:</span>
                  <code className="detail-code">{alert.destination_ip}</code>
                </div>
              )}

              {alert.rule_id && (
                <div className="detail-item">
                  <span className="detail-label">Rule ID:</span>
                  <code className="detail-code">{alert.rule_id}</code>
                </div>
              )}

              {alert.status && (
                <div className="detail-item">
                  <span className="detail-label">Status:</span>
                  <span className={`status-badge status-${alert.status.toLowerCase()}`}>
                    {alert.status}
                  </span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="alerts-footer">
        Showing latest {alerts.length} alerts
      </div>
    </div>
  );
}

/**
 * Helper function to get severity class for styling
 */
function getSeverityClass(severity) {
  if (!severity) return 'unknown';
  const sev = severity.toLowerCase();
  if (sev.includes('critical')) return 'critical';
  if (sev.includes('high')) return 'high';
  if (sev.includes('medium')) return 'medium';
  if (sev.includes('low')) return 'low';
  return 'unknown';
}

/**
 * Helper function to format timestamp
 */
function formatTime(timestamp) {
  if (!timestamp) return 'Unknown';
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return timestamp;
  }
}

export default AlertsPanel;

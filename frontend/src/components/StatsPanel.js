/**
 * @deprecated FROZEN - Do not modify, refactor, or enhance
 * 
 * This component is part of the legacy dashboard architecture.
 * Status: DEPRECATED as of January 15, 2026
 * 
 * Reason: Summary charts and REST polling patterns are not
 * compatible with the new SOC Event Console architecture.
 * 
 * Migration: This component will be removed when the new SOC Console
 * is fully integrated. Do NOT invest development time in this code.
 */

import React from 'react';
import { useApi } from '../hooks/useApi';
import './StatsPanel.css';

function StatsPanel({ apiUrl, pollInterval = 30000 }) {
  const { data: eventsData, loading: eventsLoading, error: eventsError } = useApi(
    `${apiUrl}/api/v1/events`,
    {},
    pollInterval
  );

  const { data: alertsData, loading: alertsLoading, error: alertsError } = useApi(
    `${apiUrl}/api/v1/alerts`,
    {},
    pollInterval
  );

  const loading = eventsLoading || alertsLoading;
  const error = eventsError || alertsError;

  if (error && !eventsData && !alertsData) {
    return (
      <div className="stats-panel panel panel-error">
        <h3>Security Statistics</h3>
        <div className="error-message">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (loading && !eventsData && !alertsData) {
    return (
      <div className="stats-panel panel panel-loading">
        <h3>Security Statistics</h3>
        <div className="loading-indicator">Loading...</div>
      </div>
    );
  }

  const events = eventsData?.events || [];
  const alerts = alertsData?.alerts || [];
  const totalEvents = eventsData?.count || events.length;
  const totalAlerts = alertsData?.count || alerts.length;

  // Calculate severity breakdown from events
  const severityBreakdown = {};
  const threatLevels = {};
  events.forEach(event => {
    const level = event.threat_level || 'unknown';
    threatLevels[level] = (threatLevels[level] || 0) + 1;
  });

  // Calculate severity breakdown from alerts
  const alertSeverityBreakdown = {};
  alerts.forEach(alert => {
    const severity = alert.severity || 'unknown';
    alertSeverityBreakdown[severity] = (alertSeverityBreakdown[severity] || 0) + 1;
  });

  // Count threat types from events
  const eventTypes = {};
  events.forEach(event => {
    const type = event.event_type || 'unknown';
    eventTypes[type] = (eventTypes[type] || 0) + 1;
  });

  return (
    <div className="stats-panel panel">
      <h3>Security Statistics</h3>
      
      <div className="stats-grid">
        {/* Total Events */}
        <div className="stat-card">
          <div className="stat-icon">📊</div>
          <div className="stat-content">
            <div className="stat-label">Total Events</div>
            <div className="stat-value">
              {totalEvents.toLocaleString()}
            </div>
          </div>
        </div>

        {/* Total Alerts */}
        <div className="stat-card alert-card">
          <div className="stat-icon">🚨</div>
          <div className="stat-content">
            <div className="stat-label">Total Alerts</div>
            <div className="stat-value">
              {totalAlerts.toLocaleString()}
            </div>
          </div>
        </div>

        {/* Critical Events */}
        {threatLevels['critical'] !== undefined && (
          <div className="stat-card critical-card">
            <div className="stat-icon">🔴</div>
            <div className="stat-content">
              <div className="stat-label">Critical Events</div>
              <div className="stat-value">{threatLevels['critical']}</div>
            </div>
          </div>
        )}

        {/* High Severity Events */}
        {threatLevels['high'] !== undefined && (
          <div className="stat-card warning-card">
            <div className="stat-icon">🟠</div>
            <div className="stat-content">
              <div className="stat-label">High Severity</div>
              <div className="stat-value">{threatLevels['high']}</div>
            </div>
          </div>
        )}

        {/* Medium Severity Events */}
        {threatLevels['medium'] !== undefined && (
          <div className="stat-card medium-card">
            <div className="stat-icon">🟡</div>
            <div className="stat-content">
              <div className="stat-label">Medium Severity</div>
              <div className="stat-value">{threatLevels['medium']}</div>
            </div>
          </div>
        )}

        {/* Low Severity Events */}
        {threatLevels['low'] !== undefined && (
          <div className="stat-card low-card">
            <div className="stat-icon">🟢</div>
            <div className="stat-content">
              <div className="stat-label">Low Severity</div>
              <div className="stat-value">{threatLevels['low']}</div>
            </div>
          </div>
        )}
      </div>

      {/* Breakdown by Type */}
      {Object.keys(eventTypes).length > 0 && (
        <div className="breakdown-section">
          <div className="breakdown-label">Events by Type</div>
          <div className="breakdown-list">
            {Object.entries(eventTypes).slice(0, 5).map(([type, count]) => (
              <div key={type} className="breakdown-item">
                <span className="type-name">{type}</span>
                <span className="type-count">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Breakdown by Threat Level */}
      {Object.keys(threatLevels).length > 0 && (
        <div className="breakdown-section">
          <div className="breakdown-label">Threat Level Distribution</div>
          <div className="severity-breakdown">
            {Object.entries(threatLevels).map(([level, count]) => (
              <div key={level} className="severity-row">
                <span className="severity-name">{level}</span>
                <div className="severity-bar-container">
                  <div 
                    className={`severity-bar severity-${level.toLowerCase()}`}
                    style={{ width: `${(count / Object.values(threatLevels).reduce((a, b) => a + b, 0)) * 100}%` }}
                  />
                </div>
                <span className="severity-count">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Alert Severity Distribution */}
      {Object.keys(alertSeverityBreakdown).length > 0 && (
        <div className="breakdown-section">
          <div className="breakdown-label">Alert Severity Distribution</div>
          <div className="severity-breakdown">
            {Object.entries(alertSeverityBreakdown).map(([severity, count]) => (
              <div key={severity} className="severity-row">
                <span className="severity-name">{severity}</span>
                <div className="severity-bar-container">
                  <div 
                    className={`severity-bar severity-${severity.toLowerCase()}`}
                    style={{ width: `${(count / Object.values(alertSeverityBreakdown).reduce((a, b) => a + b, 0)) * 100}%` }}
                  />
                </div>
                <span className="severity-count">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default StatsPanel;

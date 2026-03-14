import React, { useEffect, useMemo, useState } from 'react';
import { useApi } from '../hooks/useApi';
import './StatsPanel.css';

function StatsPanel({ apiUrl, pollInterval = 30000 }) {
  const {
    data: eventsData,
    loading: eventsLoading,
    error: eventsError,
    refetch: refetchEvents,
  } = useApi(
    `${apiUrl}/api/v1/events`,
    {}
  );

  const {
    data: alertsData,
    loading: alertsLoading,
    error: alertsError,
    refetch: refetchAlerts,
  } = useApi(
    `${apiUrl}/api/v1/alerts`,
    {}
  );

  const {
    data: distributionData,
    loading: distributionLoading,
    error: distributionError,
    refetch: refetchDistribution,
  } = useApi(
    `${apiUrl}/api/v1/metrics/threat-distribution`,
    {}
  );

  const [allowSpinner, setAllowSpinner] = useState(true);

  useEffect(() => {
    const intervalId = setInterval(() => {
      refetchEvents();
      refetchAlerts();
      refetchDistribution();
    }, pollInterval);

    return () => clearInterval(intervalId);
  }, [pollInterval, refetchAlerts, refetchDistribution, refetchEvents]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setAllowSpinner(false);
    }, 5000);

    return () => clearTimeout(timer);
  }, []);

  const loading = eventsLoading || alertsLoading || distributionLoading;
  const error = eventsError || alertsError || distributionError;

  const events = Array.isArray(eventsData?.events)
    ? eventsData.events
    : Array.isArray(eventsData?.data)
      ? eventsData.data
      : Array.isArray(eventsData)
        ? eventsData
        : [];

  const alerts = Array.isArray(alertsData?.alerts)
    ? alertsData.alerts
    : Array.isArray(alertsData?.data)
      ? alertsData.data
      : Array.isArray(alertsData)
        ? alertsData
        : [];

  const totalEvents = Number.isFinite(eventsData?.count) ? eventsData.count : events.length;
  const totalAlerts = Number.isFinite(alertsData?.count) ? alertsData.count : alerts.length;

  // Calculate severity breakdown from events
  const threatLevels = {};
  events.forEach((event) => {
    const level = event?.threat_level || event?.severity || 'unknown';
    threatLevels[level] = (threatLevels[level] || 0) + 1;
  });

  // Calculate severity breakdown from alerts
  const alertSeverityBreakdown = {};
  alerts.forEach((alert) => {
    const severity = alert?.severity || 'unknown';
    alertSeverityBreakdown[severity] = (alertSeverityBreakdown[severity] || 0) + 1;
  });

  // Count threat types from events
  const eventTypes = {};
  events.forEach((event) => {
    const type = event?.event_type || event?.type || 'unknown';
    eventTypes[type] = (eventTypes[type] || 0) + 1;
  });

  const parsedDistribution = useMemo(() => {
    if (!distributionData || Object.keys(distributionData).length === 0) {
      return [];
    }

    const raw = distributionData?.data
      || distributionData?.distribution
      || distributionData?.threat_distribution
      || distributionData;

    if (Array.isArray(raw)) {
      return raw
        .map((item) => {
          if (!item || typeof item !== 'object') return null;
          const name = item.level || item.severity || item.name || item.label || item.type || 'unknown';
          const count = Number(item.count ?? item.value ?? 0);
          return { name, count: Number.isFinite(count) ? count : 0 };
        })
        .filter(Boolean)
        .filter((item) => item.count >= 0);
    }

    if (raw && typeof raw === 'object') {
      return Object.entries(raw).map(([name, value]) => {
        const count = Number(value);
        return { name, count: Number.isFinite(count) ? count : 0 };
      });
    }

    return [];
  }, [distributionData]);

  const totalDistribution = parsedDistribution.reduce((sum, item) => sum + item.count, 0);
  const hasRicherDistribution = parsedDistribution.length > 0;
  const showLoading = loading && allowSpinner && totalEvents === 0 && totalAlerts === 0 && !hasRicherDistribution;

  if (showLoading) {
    return (
      <div className="stats-panel panel panel-loading">
        <h3>Security Statistics</h3>
        <div className="loading-indicator">Loading...</div>
      </div>
    );
  }

  const shouldShowAwaiting = totalEvents === 0 && totalAlerts === 0 && totalDistribution === 0;

  return (
    <div className="stats-panel panel">
      <h3>Security Statistics</h3>
      {error && (
        <div className="error-message">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
        </div>
      )}
      
      <div className="stats-grid">
        {/* Total Events */}
        <div className="stat-card">
          <div className="stat-icon"></div>
          <div className="stat-content">
            <div className="stat-label">Total Events</div>
            <div className="stat-value">
              {totalEvents.toLocaleString()}
            </div>
          </div>
        </div>

        {/* Total Alerts */}
        <div className="stat-card alert-card">
          <div className="stat-icon"></div>
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
            <div className="stat-icon"></div>
            <div className="stat-content">
              <div className="stat-label">Critical Events</div>
              <div className="stat-value">{threatLevels['critical']}</div>
            </div>
          </div>

        )}

        {/* High Severity Events */}
        {threatLevels['high'] !== undefined && (
          <div className="stat-card warning-card">
            <div className="stat-icon"></div>
            <div className="stat-content">
              <div className="stat-label">High Severity</div>
              <div className="stat-value">{threatLevels['high']}</div>
            </div>
          </div>
        )}

        {/* Medium Severity Events */}
        {threatLevels['medium'] !== undefined && (
          <div className="stat-card medium-card">
            <div className="stat-icon"></div>
            <div className="stat-content">
              <div className="stat-label">Medium Severity</div>
              <div className="stat-value">{threatLevels['medium']}</div>
            </div>
          </div>
        )}

        {/* Low Severity Events */}
        {threatLevels['low'] !== undefined && (
          <div className="stat-card low-card">
            <div className="stat-icon"></div>
            <div className="stat-content">
              <div className="stat-label">Low Severity</div>
              <div className="stat-value">{threatLevels['low']}</div>
            </div>
          </div>
        )}
      </div>

      {shouldShowAwaiting && (
        <div className="empty-state">Awaiting first detection...</div>
      )}

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

      {/* API Threat Distribution */}
      {hasRicherDistribution ? (
        <div className="breakdown-section">
          <div className="breakdown-label">Threat Distribution</div>
          <div className="severity-breakdown">
            {parsedDistribution.map(({ name, count }) => (
              <div key={name} className="severity-row">
                <span className="severity-name">{name}</span>
                <div className="severity-bar-container">
                  <div
                    className={`severity-bar severity-${String(name).toLowerCase()}`}
                    style={{ width: `${totalDistribution > 0 ? (count / totalDistribution) * 100 : 0}%` }}
                  />
                </div>
                <span className="severity-count">{count}</span>
              </div>
            ))}
          </div>
        </div>
      ) : shouldShowAwaiting && (
        <div className="breakdown-section">
          <div className="breakdown-label">Threat Distribution</div>
          <div className="empty-state">Awaiting first detection...</div>
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

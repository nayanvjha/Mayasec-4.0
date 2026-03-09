/**
 * @deprecated FROZEN - Do not modify, refactor, or enhance
 * 
 * This component is part of the legacy dashboard architecture.
 * Status: DEPRECATED as of January 15, 2026
 * 
 * Reason: Static metric cards and REST polling patterns are not
 * compatible with the new SOC Event Console architecture.
 * 
 * Migration: This component will be removed when the new SOC Console
 * is fully integrated. Do NOT invest development time in this code.
 */

import React from 'react';
import { useApi } from '../hooks/useApi';
import './HealthPanel.css';

function HealthPanel({ apiUrl, pollInterval = 30000 }) {
  const { data: health, loading, error } = useApi(
    `${apiUrl}/api/v1/health`,
    {},
    pollInterval
  );

  if (error) {
    return (
      <div className="health-panel panel panel-error">
        <h3>System Health</h3>
        <div className="error-message">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="health-panel panel panel-loading">
        <h3>System Health</h3>
        <div className="loading-indicator">Loading...</div>
      </div>
    );
  }

  if (!health) {
    return (
      <div className="health-panel panel panel-empty">
        <h3>System Health</h3>
        <div className="empty-state">No data available</div>
      </div>
    );
  }

  const isHealthy = health.status === 'healthy';
  const statusClass = isHealthy ? 'status-healthy' : 'status-unhealthy';

  return (
    <div className="health-panel panel">
      <h3>System Health</h3>
      
      <div className={`health-status ${statusClass}`}>
        <div className="health-indicator">
          {isHealthy ? '🟢' : '🔴'}
        </div>
        <div className="health-info">
          <span className="status-label">Status:</span>
          <span className="status-value">{health.status.toUpperCase()}</span>
        </div>
      </div>

      {health.services && Object.keys(health.services).length > 0 && (
        <div className="services-detail">
          <div className="detail-label">Services</div>
          <div className="services-list">
            {Object.entries(health.services).map(([service, status]) => (
              <div key={service} className="service-item">
                <span className={`service-indicator ${status === 'healthy' ? 'healthy' : 'unhealthy'}`}>
                  {status === 'healthy' ? '✓' : '✗'}
                </span>
                <span className="service-name">{service}</span>
                <span className="service-status">{status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {health.timestamp && (
        <div className="last-update">
          Last updated: {new Date(health.timestamp).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}

export default HealthPanel;

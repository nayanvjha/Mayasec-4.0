import React, { useEffect, useState } from 'react';
import { useApi } from '../hooks/useApi';
import './HealthPanel.css';

function HealthPanel({ apiUrl, pollInterval = 30000 }) {
  const { data: health, loading, error, refetch } = useApi(
    `${apiUrl}/api/v1/health`,
    {},
    pollInterval
  );
  const [loadingTimedOut, setLoadingTimedOut] = useState(false);

  useEffect(() => {
    if (!loading) {
      setLoadingTimedOut(false);
      return undefined;
    }

    const timer = setTimeout(() => {
      setLoadingTimedOut(true);
    }, 3000);

    return () => clearTimeout(timer);
  }, [loading]);

  const hasHealthData = Boolean(health && Object.keys(health).length > 0);
  const statusRaw = typeof health?.status === 'string' ? health.status.toLowerCase() : '';
  const isHealthy = statusRaw === 'healthy';
  const statusClass = isHealthy ? 'status-healthy' : 'status-unhealthy';

  if (error || (loading && loadingTimedOut)) {
    return (
      <div className="health-panel panel panel-error">
        <h3>System Health</h3>
        <div className="health-status status-unhealthy">
          <div className="health-indicator"></div>
          <div className="health-info">
            <span className="status-label">Status:</span>
            <span className="status-value" style={{ color: '#ff9800' }}>API Unreachable</span>
          </div>
        </div>
        <button onClick={refetch}>Retry</button>
      </div>
    );
  }

  if (loading && !hasHealthData) {
    return (
      <div className="health-panel panel panel-loading">
        <h3>System Health</h3>
        <div className="loading-indicator">Loading...</div>
      </div>
    );
  }

  if (!hasHealthData) {
    return (
      <div className="health-panel panel panel-empty">
        <h3>System Health</h3>
        <div className="health-status status-unhealthy">
          <div className="health-indicator"></div>
          <div className="health-info">
            <span className="status-label">Status:</span>
            <span className="status-value" style={{ color: '#ff9800' }}>API Unreachable</span>
          </div>
        </div>
        <button onClick={refetch}>Retry</button>
      </div>
    );
  }

  return (
    <div className="health-panel panel">
      <h3>System Health</h3>
      
      <div className={`health-status ${statusClass}`}>
        <div className="health-indicator">
          {isHealthy ? '' : ''}
        </div>
        <div className="health-info">
          <span className="status-label">Status:</span>
          <span className="status-value">{isHealthy ? 'Healthy' : 'Degraded'}</span>
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

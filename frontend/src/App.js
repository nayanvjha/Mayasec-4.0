import React, { useState, useEffect } from 'react';
import HealthPanel from './components/HealthPanel';
import StatsPanel from './components/StatsPanel';
import AlertsPanel from './components/AlertsPanel';
import BlockedIpsPanel from './components/BlockedIpsPanel';
import { useWebSocket } from './hooks/useWebSocket';
import './App.css';

/**
 * Main MAYASEC Dashboard Component
 * Displays: System health, security statistics, and recent alerts
 * Auto-refreshes every 30 seconds
 * Shows error state if API is unavailable
 */
function resolveApiUrl() {
  const envUrl = process.env.REACT_APP_API_URL;
  if (envUrl) {
    try {
      const parsed = new URL(envUrl);
      if (parsed.hostname === 'api' && typeof window !== 'undefined' && window.location?.hostname) {
        parsed.hostname = window.location.hostname;
        return parsed.toString().replace(/\/$/, '');
      }
      return envUrl.replace(/\/$/, '');
    } catch {
      return envUrl;
    }
  }

  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `http://${window.location.hostname}:5000`;
  }

  return 'http://localhost:5000';
}

function App() {
  const apiUrl = resolveApiUrl();
  const [systemStatus, setSystemStatus] = useState('checking');
  const [lastUpdate, setLastUpdate] = useState(null);
  const { responseMode } = useWebSocket(apiUrl);

  // Check system health on mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/health`, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        });
        
        if (response.ok) {
          setSystemStatus('online');
        } else {
          setSystemStatus('degraded');
        }
      } catch (err) {
        console.error('Health check failed:', err);
        setSystemStatus('offline');
      }
      setLastUpdate(new Date());
    };

    checkHealth();
  }, [apiUrl]);

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <div className="header-title">
            <h1>MAYASEC Dashboard</h1>
            <p className="subtitle">Security Monitoring Platform</p>
          </div>
          <div className="header-status">
            <span className={`status-indicator status-${systemStatus}`} />
            <span className="status-text">{systemStatus.charAt(0).toUpperCase() + systemStatus.slice(1)}</span>
            {responseMode && (
              <span className="last-update-time">
                Response mode: {responseMode}
              </span>
            )}
            {lastUpdate && (
              <span className="last-update-time">
                Updated: {lastUpdate.toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="main-content">
        {systemStatus === 'offline' ? (
          <div className="error-state">
            <div className="error-container">
              <div className="error-icon">🔌</div>
              <h2>API Connection Failed</h2>
              <p>Unable to connect to MAYASEC API at {apiUrl}</p>
              <p className="error-details">
                Please verify that:
              </p>
              <ul className="error-checklist">
                <li>API service is running (port 5000)</li>
                <li>Backend services are healthy</li>
                <li>Network connectivity is available</li>
              </ul>
              <div className="error-actions">
                <button className="retry-button" onClick={() => window.location.reload()}>
                  Retry Connection
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="dashboard-grid">
            {/* Health Status Panel */}
            <div className="panel-container">
              <HealthPanel apiUrl={apiUrl} pollInterval={30000} />
            </div>

            {/* Statistics Panel */}
            <div className="panel-container">
              <StatsPanel apiUrl={apiUrl} pollInterval={30000} />
            </div>

            {/* Recent Alerts Panel */}
            <div className="panel-container full-width">
              <AlertsPanel apiUrl={apiUrl} limit={20} pollInterval={30000} />
            </div>

            {/* Blocked IPs Panel */}
            <div className="panel-container full-width">
              <BlockedIpsPanel apiUrl={apiUrl} pollInterval={30000} />
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="footer">
        <p>&copy; 2026 MAYASEC. All rights reserved. | 
          <span className="api-endpoint"> API: {apiUrl}</span>
        </p>
      </footer>
    </div>
  );
}

export default App;

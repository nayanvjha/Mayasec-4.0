import React, { useState, useEffect, useMemo } from 'react';
import HealthPanel from './components/HealthPanel';
import StatsPanel from './components/StatsPanel';
import AlertsPanel from './components/AlertsPanel';
import BlockedIpsPanel from './components/BlockedIpsPanel';
import LiveEventFeed from './components/LiveEventFeed';
import LiveEventStream from './components/LiveEventStream';
import EventTimeline from './components/EventTimeline';
import SOCEventConsole from './components/SOCEventConsole';
import OperatorContextPanel from './components/OperatorContextPanel';
import EventStreamFilters from './components/EventStreamFilters';
import CopilotPanel from './components/CopilotPanel';
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
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [streamFilters, setStreamFilters] = useState({
    severity: 'ALL',
    eventType: 'ALL',
    sourceIp: '',
    timeWindow: 30,
  });

  const {
    responseMode,
    connected,
    events,
    alerts,
    error: wsError,
  } = useWebSocket(apiUrl);

  const availableEventTypes = useMemo(() => {
    const all = new Set(
      (events || [])
        .map((event) => event?.event_type)
        .filter(Boolean)
    );
    return Array.from(all);
  }, [events]);

  const filteredEvents = useMemo(() => {
    const list = events || [];
    const now = Date.now();
    const windowMs = (Number(streamFilters.timeWindow) || 30) * 60 * 1000;

    return list.filter((event) => {
      const severity = String(event?.severity_level || event?.threat_level || '').toUpperCase();
      if (streamFilters.severity !== 'ALL' && severity !== streamFilters.severity) {
        return false;
      }

      const eventType = String(event?.event_type || '');
      if (streamFilters.eventType !== 'ALL' && eventType !== streamFilters.eventType) {
        return false;
      }

      const sourceIp = String(event?.source_ip || event?.ip_address || '');
      if (streamFilters.sourceIp && !sourceIp.includes(streamFilters.sourceIp)) {
        return false;
      }

      const ts = event?.timestamp || event?.created_at;
      if (!ts) {
        return false;
      }

      const eventTime = new Date(ts).getTime();
      if (!Number.isFinite(eventTime)) {
        return false;
      }

      return now - eventTime <= windowMs;
    });
  }, [events, streamFilters]);

  const handleStreamEventSelect = (event, isCurrentlySelected = false) => {
    if (isCurrentlySelected) {
      setSelectedEvent(null);
      return;
    }
    setSelectedEvent(event);
  };

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
          <div className="dashboard-tabs">
            <nav className="tab-nav" role="tablist" aria-label="SOC Dashboard Views">
              <button
                className={`tab-button ${activeTab === 'overview' ? 'active' : ''}`}
                onClick={() => setActiveTab('overview')}
                role="tab"
                aria-selected={activeTab === 'overview'}
              >
                Overview
              </button>
              <button
                className={`tab-button ${activeTab === 'live' ? 'active' : ''}`}
                onClick={() => setActiveTab('live')}
                role="tab"
                aria-selected={activeTab === 'live'}
              >
                Live Feed
              </button>
              <button
                className={`tab-button ${activeTab === 'timeline' ? 'active' : ''}`}
                onClick={() => setActiveTab('timeline')}
                role="tab"
                aria-selected={activeTab === 'timeline'}
              >
                Timeline
              </button>
              <button
                className={`tab-button ${activeTab === 'alerts' ? 'active' : ''}`}
                onClick={() => setActiveTab('alerts')}
                role="tab"
                aria-selected={activeTab === 'alerts'}
              >
                Alerts
              </button>
            </nav>

            {activeTab === 'overview' && (
              <div className="dashboard-grid tab-panel" role="tabpanel">
                <div className="panel-container">
                  <HealthPanel apiUrl={apiUrl} pollInterval={30000} />
                </div>
                <div className="panel-container">
                  <StatsPanel apiUrl={apiUrl} pollInterval={30000} />
                </div>
              </div>
            )}

            {activeTab === 'live' && (
              <div className="tab-panel live-feed-layout" role="tabpanel">
                <div className="panel-container full-width">
                  <EventStreamFilters
                    apiUrl={apiUrl}
                    onFilterChange={setStreamFilters}
                    availableEventTypes={availableEventTypes}
                  />
                </div>
                <div className="panel-container full-width">
                  <LiveEventFeed
                    apiUrl={apiUrl}
                    events={filteredEvents}
                    connected={connected}
                    error={wsError}
                  />
                </div>
                <div className="panel-container full-width">
                  <LiveEventStream
                    apiUrl={apiUrl}
                    events={filteredEvents}
                    connected={connected}
                    error={wsError}
                    selectedEventId={selectedEvent?.event_id || null}
                    onEventSelect={handleStreamEventSelect}
                  />
                </div>
              </div>
            )}

            {activeTab === 'timeline' && (
              <div className="tab-panel timeline-layout" role="tabpanel">
                <div className="panel-container full-width">
                  <EventTimeline
                    apiUrl={apiUrl}
                    selectedEvent={selectedEvent}
                    allEvents={filteredEvents}
                    connected={connected}
                  />
                </div>
                <div className="panel-container full-width">
                  <SOCEventConsole
                    apiUrl={apiUrl}
                    connected={connected}
                    events={filteredEvents}
                    alerts={alerts}
                    error={wsError}
                    onEventSelect={setSelectedEvent}
                  />
                </div>
              </div>
            )}

            {activeTab === 'alerts' && (
              <div className="tab-panel alerts-layout" role="tabpanel">
                <div className="panel-container full-width">
                  <AlertsPanel apiUrl={apiUrl} limit={20} pollInterval={30000} />
                </div>
                <div className="panel-container full-width">
                  <BlockedIpsPanel apiUrl={apiUrl} pollInterval={30000} />
                </div>
                <div className="panel-container full-width">
                  <OperatorContextPanel apiUrl={apiUrl} selectedEvent={selectedEvent} />
                </div>
              </div>
            )}
            </div>
        )}

        <CopilotPanel apiUrl={apiUrl} />
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

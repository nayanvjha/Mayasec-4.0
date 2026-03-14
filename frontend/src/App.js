import React, { useState, useEffect, useMemo } from 'react';
import AlertsPanel from './components/AlertsPanel';
import LiveEventFeed from './components/LiveEventFeed';
import LiveEventStream from './components/LiveEventStream';
import EventTimeline from './components/EventTimeline';
import AttackStoryViewer from './components/AttackStoryViewer';
import SOCEventConsole from './components/SOCEventConsole';
import EventStreamFilters from './components/EventStreamFilters';
import CopilotPanel from './components/CopilotPanel';
import KPICards from './components/KPICards';
import ThreatRadarChart from './components/ThreatRadarChart';
import TrafficSparkline from './components/TrafficSparkline';
import ThreatMapPanel from './components/ThreatMapPanel';
import MitreHeatmap from './components/MitreHeatmap';
import ThreatAttributionPanel from './components/ThreatAttributionPanel';
import SettingsPanel from './components/SettingsPanel';
import HoneypotSessionViewer from './components/HoneypotSessionViewer';
import CommandCenter from './components/CommandCenter';
import DemoInjector from './components/DemoInjector';
import EventInspectModal from './components/EventInspectModal';
import LoginPage from './components/LoginPage';
import TrafficLogsView from './views/TrafficLogsView';
import ReportsView from './views/ReportsView';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { Shield, Activity, Server, Cpu, Bug, UserCircle } from 'lucide-react';
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

function DashboardApp({ authUser, onLogout }) {
  const apiUrl = resolveApiUrl();
  const tabRouteMap = useMemo(() => ({
    'command-center': '/',
    overview: '/overview',
    live: '/live',
    timeline: '/timeline',
    stories: '/stories',
    honeypot: '/honeypot',
    settings: '/settings',
    'traffic-logs': '/traffic-logs',
    reports: '/reports',
  }), []);

  const routeTabMap = useMemo(() => (
    Object.entries(tabRouteMap).reduce((acc, [tab, path]) => {
      acc[path] = tab;
      return acc;
    }, {})
  ), [tabRouteMap]);

  const initialTab = useMemo(() => {
    if (typeof window === 'undefined') return 'command-center';
    return routeTabMap[window.location.pathname] || 'command-center';
  }, [routeTabMap]);

  const [systemStatus, setSystemStatus] = useState('checking');
  const [modeLoading, setModeLoading] = useState(false);
  const [activeSensors, setActiveSensors] = useState(0);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [activeTab, setActiveTab] = useState(initialTab);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [mitreFilter, setMitreFilter] = useState(null);
  const [streamFilters, setStreamFilters] = useState({
    severity: 'ALL',
    eventType: 'ALL',
    sourceIp: '',
    timeWindow: 30,
  });
  const [avatarMenuOpen, setAvatarMenuOpen] = useState(false);

  const {
    responseMode,
    connected,
    events,
    alerts,
    error: wsError,
  } = useWebSocket(apiUrl);

  const wsEvents = useMemo(() => events || [], [events]);

  const hasActiveThreat = useMemo(() => {
    return wsEvents.some((event) => Number(event?.threat_score || event?.score || 0) >= 90);
  }, [wsEvents]);

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

      if (mitreFilter) {
        const eventMitre = String(
          event?.technique_id
          || event?.mitre_technique_id
          || event?.mitre?.technique_id
          || ''
        ).toUpperCase();
        if (eventMitre !== String(mitreFilter).toUpperCase()) {
          return false;
        }
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
  }, [events, streamFilters, mitreFilter]);

  const handleStreamEventSelect = (event, isCurrentlySelected = false) => {
    if (isCurrentlySelected) {
      setSelectedEvent(null);
      return;
    }
    setSelectedEvent(event);
  };

  const handleCommandCenterEventSelect = (event) => {
    setSelectedEvent(event || null);
    setActiveTab('live');
  };

  async function handleResponseModeChange(e) {
    const selectedMode = e.target.value;

    if (responseMode === 'deception' && selectedMode !== 'deception') {
      const confirmed = window.confirm(
        'You are leaving deception mode. Continue?'
      );

      if (!confirmed) return;
    }

    setModeLoading(true);

    try {
      await fetch(`${apiUrl}/api/v1/response-mode`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization:
            `Bearer ${process.env.REACT_APP_ADMIN_TOKEN || 'mayasec_internal_token'}`,
        },
        body: JSON.stringify({ mode: selectedMode }),
      });
    } catch (err) {
      console.error('Failed to change response mode', err);
    }

    setModeLoading(false);
  }

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

  useEffect(() => {
    let mounted = true;

    const fetchSensors = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/sensors`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            Authorization:
              `Bearer ${process.env.REACT_APP_ADMIN_TOKEN || 'mayasec_internal_token'}`,
          },
        });

        if (!response.ok) {
          throw new Error(`status=${response.status}`);
        }

        const payload = await response.json();
        if (!mounted) return;

        if (Number.isFinite(Number(payload?.active))) {
          setActiveSensors(Number(payload.active));
          return;
        }

        const sensors = Array.isArray(payload?.sensors) ? payload.sensors : [];
        setActiveSensors(sensors.filter((s) => Boolean(s?.is_active)).length);
      } catch {
        if (!mounted) return;
        setActiveSensors(0);
      }
    };

    fetchSensors();
    const id = setInterval(fetchSensors, 15000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [apiUrl]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const onPopState = () => {
      const tab = routeTabMap[window.location.pathname] || 'command-center';
      setActiveTab(tab);
    };

    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, [routeTabMap]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const targetPath = tabRouteMap[activeTab] || '/';
    if (window.location.pathname !== targetPath) {
      window.history.pushState({}, '', targetPath);
    }
  }, [activeTab, tabRouteMap]);

  return (
    <div className="app">
      {/* Header */}
      <header className={`header ${hasActiveThreat ? 'threat-active' : ''}`}>
        <div className="header-content">
          <div className="header-brand">
            <div className="header-brand-row">
              <Shield size={22} className="header-icon" />
              <span className="header-title">MAYASEC</span>
            </div>
            <p className="subtitle">AI-Powered Threat Defense</p>
          </div>
          <div className="header-status">
            <Server size={16} />
            <span className={`status-indicator status-${systemStatus}`} />
            <span className="status-text">{systemStatus.charAt(0).toUpperCase() + systemStatus.slice(1)}</span>
            <div className="ws-status">
              <span className={`ws-dot ${connected ? 'online' : 'offline'}`} />
              <span>{connected ? 'Connected' : 'Disconnected'}</span>
            </div>
            <span className="sensor-badge">Sensors: {activeSensors} Active</span>
            {responseMode && (
              <span className="last-update-time">
                Response mode:
                {' '}
                <select
                  className="response-mode-select"
                  value={responseMode}
                  onChange={handleResponseModeChange}
                  disabled={modeLoading}
                >
                  <option value="monitor">monitor</option>
                  <option value="guarded">guarded</option>
                  <option value="deception">deception</option>
                </select>
                {modeLoading && ' Updating...'}
              </span>
            )}
            {lastUpdate && (
              <span className="last-update-time">
                Updated: {lastUpdate.toLocaleTimeString()}
              </span>
            )}
            <div style={{ position: 'relative' }}>
              <button
                type="button"
                onClick={() => setAvatarMenuOpen((prev) => !prev)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  border: '1px solid rgba(88,166,255,0.35)',
                  background: 'rgba(13,17,23,0.75)',
                  color: '#e6edf3',
                  borderRadius: '999px',
                  padding: '4px 10px',
                  cursor: 'pointer',
                }}
              >
                <UserCircle size={16} />
                <span>{authUser?.display_name || authUser?.email || 'User'}</span>
              </button>
              {avatarMenuOpen && (
                <div
                  style={{
                    position: 'absolute',
                    right: 0,
                    top: 'calc(100% + 6px)',
                    minWidth: '180px',
                    background: 'rgba(10,14,26,0.95)',
                    border: '1px solid rgba(88,166,255,0.3)',
                    borderRadius: '8px',
                    padding: '8px',
                    zIndex: 100,
                  }}
                >
                  <div style={{ color: '#8b949e', fontSize: '0.75rem', marginBottom: '6px' }}>
                    {authUser?.email}
                  </div>
                  <button
                    type="button"
                    onClick={onLogout}
                    style={{
                      width: '100%',
                      border: '1px solid rgba(248,81,73,0.45)',
                      background: 'rgba(248,81,73,0.12)',
                      color: '#f85149',
                      borderRadius: '6px',
                      padding: '7px 8px',
                      cursor: 'pointer',
                    }}
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="main-content">
        {systemStatus === 'offline' ? (
          <div className="error-state">
            <div className="error-container">
              <div className="error-icon"></div>
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
                className={`tab-button ${activeTab === 'command-center' ? 'active' : ''}`}
                onClick={() => setActiveTab('command-center')}
                role="tab"
                aria-selected={activeTab === 'command-center'}
              >
                <Shield size={16} />
                Command Center
              </button>
              <button
                className={`tab-button ${activeTab === 'overview' ? 'active' : ''}`}
                onClick={() => setActiveTab('overview')}
                role="tab"
                aria-selected={activeTab === 'overview'}
              >
                <Activity size={16} />
                Overview
              </button>
              <button
                className={`tab-button ${activeTab === 'live' ? 'active' : ''}`}
                onClick={() => setActiveTab('live')}
                role="tab"
                aria-selected={activeTab === 'live'}
              >
                <Cpu size={16} />
                Live Feed
              </button>
              <button
                className={`tab-button ${activeTab === 'timeline' ? 'active' : ''}`}
                onClick={() => setActiveTab('timeline')}
                role="tab"
                aria-selected={activeTab === 'timeline'}
              >
                <Shield size={16} />
                Timeline
              </button>
              <button
                className={`tab-button ${activeTab === 'stories' ? 'active' : ''}`}
                onClick={() => setActiveTab('stories')}
                role="tab"
                aria-selected={activeTab === 'stories'}
              >
                <Shield size={16} />
                Attack Stories
              </button>
              <button
                className={`tab-button ${activeTab === 'honeypot' ? 'active' : ''}`}
                onClick={() => setActiveTab('honeypot')}
                role="tab"
                aria-selected={activeTab === 'honeypot'}
              >
                <Bug size={16} />
                Honeypot
              </button>
              <button
                className={`tab-button ${activeTab === 'traffic-logs' ? 'active' : ''}`}
                onClick={() => setActiveTab('traffic-logs')}
                role="tab"
                aria-selected={activeTab === 'traffic-logs'}
              >
                <Activity size={16} />
                Traffic Logs
              </button>
              <button
                className={`tab-button ${activeTab === 'reports' ? 'active' : ''}`}
                onClick={() => setActiveTab('reports')}
                role="tab"
                aria-selected={activeTab === 'reports'}
              >
                <Shield size={16} />
                Reports
              </button>
              <button
                className={`tab-button ${activeTab === 'settings' ? 'active' : ''}`}
                onClick={() => setActiveTab('settings')}
                role="tab"
                aria-selected={activeTab === 'settings'}
              >
                Settings
              </button>
            </nav>

            {activeTab === 'command-center' && (
              <CommandCenter
                apiUrl={apiUrl}
                connected={connected}
                events={wsEvents}
                authUser={authUser}
                onNavigateLiveFeed={handleCommandCenterEventSelect}
              />
            )}

            {activeTab === 'overview' && (
              <div className="dashboard-grid tab-panel" role="tabpanel">
                <div className="panel-container full-width">
                  <KPICards events={wsEvents} />
                </div>

                <div className="dashboard-row-split">
                  <div className="panel-container">
                    <TrafficSparkline events={wsEvents} />
                  </div>
                  <div className="panel-container">
                    <ThreatRadarChart events={wsEvents} />
                  </div>
                </div>

                <div className="panel-container full-width">
                  <ThreatMapPanel />
                </div>

                <div className="dashboard-row-split">
                  <div className="panel-container">
                    <ThreatAttributionPanel apiUrl={apiUrl} />
                  </div>
                  <div className="panel-container">
                    <MitreHeatmap onFilter={(ttp) => setMitreFilter(ttp)} />
                  </div>
                </div>

                <div className="panel-container full-width">
                  <AlertsPanel apiUrl={apiUrl} limit={20} pollInterval={30000} />
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
                    mitreFilter={mitreFilter}
                    onEventSelect={setSelectedEvent}
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

            {activeTab === 'stories' && (
              <div className="tab-panel" role="tabpanel">
                <AttackStoryViewer apiUrl={apiUrl} />
              </div>
            )}

            {activeTab === 'settings' && (
              <div className="tab-panel" role="tabpanel">
                <SettingsPanel apiUrl={apiUrl} responseMode={responseMode} connected={connected} />
              </div>
            )}

            {activeTab === 'honeypot' && (
              <div className="tab-panel" role="tabpanel">
                <HoneypotSessionViewer apiUrl={apiUrl} />
              </div>
            )}

            {activeTab === 'traffic-logs' && (
              <div className="tab-panel" role="tabpanel">
                <TrafficLogsView />
              </div>
            )}

            {activeTab === 'reports' && (
              <div className="tab-panel" role="tabpanel">
                <ReportsView />
              </div>
            )}
            </div>
        )}

        <CopilotPanel apiUrl={apiUrl} />
      </main>

      {process.env.NODE_ENV !== 'production' && <DemoInjector />}
      <EventInspectModal event={selectedEvent} onClose={() => setSelectedEvent(null)} />

      {/* Footer */}
      <footer className="footer">
        <p>&copy; 2026 MAYASEC · AI-Powered Threat Defense</p>
      </footer>
    </div>
  );
}

function AuthGate() {
  const { authenticated, loading, user, logout } = useAuth();

  if (loading) {
    return (
      <div className="app">
        <div className="error-state">
          <div className="error-container">
            <h2>Loading...</h2>
          </div>
        </div>
      </div>
    );
  }

  if (!authenticated) {
    return <LoginPage />;
  }

  return <DashboardApp authUser={user} onLogout={logout} />;
}

function App() {
  const apiUrl = resolveApiUrl();
  return (
    <AuthProvider apiUrl={apiUrl}>
      <AuthGate />
    </AuthProvider>
  );
}

export default App;

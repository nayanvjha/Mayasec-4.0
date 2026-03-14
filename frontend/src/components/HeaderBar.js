import React from 'react';

function HeaderBar({ systemStatus, connected, activeSensors = 0, children }) {
  return (
    <header className="header">
      <div className="header-content">
        <div className="header-status">
          <span className={`status-indicator status-${systemStatus || 'checking'}`} />
          <span className="status-text">{systemStatus || 'checking'}</span>
          <div className="ws-status">
            <span className={`ws-dot ${connected ? 'online' : 'offline'}`} />
            <span>{connected ? 'Connected' : 'Disconnected'}</span>
          </div>
          <span className="sensor-badge">Sensors: {activeSensors} Active</span>
          {children}
        </div>
      </div>
    </header>
  );
}

export default HeaderBar;

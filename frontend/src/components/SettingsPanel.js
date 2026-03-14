import React, { useState } from 'react';
import { Shield, ShieldAlert, ShieldCheck, Copy, Check } from 'lucide-react';
import './SettingsPanel.css';

function SettingsPanel({ apiUrl, responseMode, connected }) {
  const [loadingMode, setLoadingMode] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  const adminToken = process.env.REACT_APP_ADMIN_TOKEN || 'mayasec_internal_token';
  const maskedToken = 'maya•••••••ken';

  const modeCards = [
    {
      key: 'monitor',
      title: 'Monitor',
      description: 'Observe only. Log threats without blocking.',
      Icon: Shield,
    },
    {
      key: 'guarded',
      title: 'Guarded',
      description: 'Active defense. Block high-threat IPs.',
      Icon: ShieldAlert,
    },
    {
      key: 'deception',
      title: 'Deception',
      description: 'Full honeypot. Route attackers to decoy.',
      Icon: ShieldCheck,
    },
  ];

  const websocketStatus = connected === undefined
    ? 'Unknown'
    : connected
      ? 'Connected'
      : 'Disconnected';

  const handleModeChange = async (mode) => {
    if (!mode || mode === responseMode || loadingMode) {
      return;
    }

    setError('');
    setLoadingMode(mode);

    try {
      const response = await fetch(`${apiUrl}/api/v1/response-mode`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${adminToken}`,
        },
        body: JSON.stringify({ mode }),
      });

      if (!response.ok) {
        throw new Error(`Failed to update mode: ${response.status}`);
      }
    } catch (err) {
      console.error('Failed to change response mode', err);
      setError('Failed to update response mode. Please try again.');
    } finally {
      setLoadingMode(null);
    }
  };

  const handleCopyToken = async () => {
    try {
      await navigator.clipboard.writeText(adminToken);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch (err) {
      console.error('Failed to copy token', err);
    }
  };

  return (
    <div className="panel settings-panel">
      <h3>Settings</h3>

      <div className="settings-section">
        <h4 className="settings-heading">Response Mode</h4>
        <div className="settings-mode-grid">
          {modeCards.map(({ key, title, description, Icon }) => {
            const isActive = responseMode === key;
            const isLoading = loadingMode === key;

            return (
              <button
                key={key}
                type="button"
                className={`settings-mode-card ${isActive ? 'active' : ''}`}
                onClick={() => handleModeChange(key)}
                disabled={Boolean(loadingMode)}
              >
                <div className="settings-mode-icon-wrap">
                  <Icon size={20} className="settings-mode-icon" />
                </div>
                <div className="settings-mode-title-row">
                  <span className="settings-mode-title">{title}</span>
                  {isLoading && <span className="settings-mode-loading">Updating...</span>}
                </div>
                <p className="settings-mode-description">{description}</p>
              </button>
            );
          })}
        </div>
        {error && <p className="settings-error">{error}</p>}
      </div>

      <div className="settings-row-grid">
        <div className="settings-section settings-metric-card">
          <h4 className="settings-heading">Score Threshold</h4>
          <div className="settings-threshold-value">80</div>
          <p className="settings-subtext">Read-only (ingress proxy default)</p>
        </div>

        <div className="settings-section settings-metric-card">
          <h4 className="settings-heading">API Token</h4>
          <div className="settings-token-row">
            <span className="settings-token-value">{maskedToken}</span>
            <button type="button" className="settings-copy-btn" onClick={handleCopyToken}>
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        </div>
      </div>

      <div className="settings-section settings-system-info">
        <h4 className="settings-heading">System Info</h4>
        <div className="settings-info-row">
          <span className="settings-info-label">API URL</span>
          <span className="settings-info-value">{apiUrl}</span>
        </div>
        <div className="settings-info-row">
          <span className="settings-info-label">Current Mode</span>
          <span className="settings-info-value">{responseMode || 'unknown'}</span>
        </div>
        <div className="settings-info-row">
          <span className="settings-info-label">WebSocket</span>
          <span className="settings-info-value">{websocketStatus}</span>
        </div>
      </div>
    </div>
  );
}

export default SettingsPanel;

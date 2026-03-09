import React, { useEffect, useMemo, useState } from 'react';
import { useApi } from '../hooks/useApi';
import './BlockedIpsPanel.css';

/**
 * BlockedIpsPanel Component
 * Displays currently blocked IPs with ability to unblock selected entries.
 */
function BlockedIpsPanel({ apiUrl, pollInterval = 30000 }) {
  const [refreshToken, setRefreshToken] = useState(0);
  const [selected, setSelected] = useState({});
  const [actionState, setActionState] = useState({ loading: false, error: null, success: null });

  const { data, loading, error } = useApi(
    `${apiUrl}/api/v1/alerts/blocked?limit=200&refresh=${refreshToken}`,
    {},
    pollInterval
  );

  const blockedIps = Array.isArray(data?.blocked_ips)
    ? data.blocked_ips
    : Array.isArray(data?.data)
      ? data.data
      : Array.isArray(data)
        ? data
        : [];

  useEffect(() => {
    if (!blockedIps.length) {
      setSelected({});
      return;
    }
    setSelected((prev) => {
      const next = {};
      blockedIps.forEach((item) => {
        const ip = item.ip_address;
        if (prev[ip]) {
          next[ip] = true;
        }
      });
      return next;
    });
  }, [blockedIps]);

  const selectedIps = useMemo(
    () => Object.keys(selected).filter((ip) => selected[ip]),
    [selected]
  );

  const allSelected = blockedIps.length > 0 && selectedIps.length === blockedIps.length;

  const toggleIp = (ip) => {
    setSelected((prev) => ({ ...prev, [ip]: !prev[ip] }));
  };

  const toggleAll = () => {
    if (allSelected) {
      setSelected({});
      return;
    }
    const next = {};
    blockedIps.forEach((item) => {
      next[item.ip_address] = true;
    });
    setSelected(next);
  };

  const unblockIp = async (ipAddress) => {
    const response = await fetch(`${apiUrl}/api/v1/alerts/unblock`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ip_address: ipAddress, reason: 'operator_unblock' }),
    });

    if (!response.ok) {
      let message = `Failed to unblock ${ipAddress}`;
      try {
        const payload = await response.json();
        if (payload?.error) {
          message = payload.error;
        }
      } catch {
        // ignore JSON parse errors
      }
      throw new Error(message);
    }

    return response.json();
  };

  const handleUnblock = async () => {
    if (!selectedIps.length) return;

    setActionState({ loading: true, error: null, success: null });

    const results = await Promise.allSettled(
      selectedIps.map((ipAddress) => unblockIp(ipAddress))
    );

    const failures = results.filter((result) => result.status === 'rejected');

    if (failures.length > 0) {
      setActionState({
        loading: false,
        error: `${failures.length} unblock request(s) failed`,
        success: null,
      });
    } else {
      setActionState({
        loading: false,
        error: null,
        success: `Unblocked ${selectedIps.length} IP(s)`,
      });
    }

    setSelected({});
    setRefreshToken(Date.now());
  };

  if (error) {
    return (
      <div className="blocked-ips-panel panel panel-error">
        <h3>Blocked IPs</h3>
        <div className="error-message">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (loading && blockedIps.length === 0) {
    return (
      <div className="blocked-ips-panel panel panel-loading">
        <h3>Blocked IPs</h3>
        <div className="loading-indicator">Loading...</div>
      </div>
    );
  }

  if (!blockedIps.length) {
    return (
      <div className="blocked-ips-panel panel panel-empty">
        <h3>Blocked IPs</h3>
        <div className="empty-state">No active blocks</div>
      </div>
    );
  }

  return (
    <div className="blocked-ips-panel panel">
      <h3>Blocked IPs ({blockedIps.length})</h3>

      <div className="blocked-ips-actions">
        <label className="select-all">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={toggleAll}
          />
          Select all
        </label>
        <button
          className="unblock-button"
          onClick={handleUnblock}
          disabled={!selectedIps.length || actionState.loading}
        >
          {actionState.loading ? 'Unblocking...' : `Unblock Selected (${selectedIps.length})`}
        </button>
      </div>

      {actionState.error && (
        <div className="action-message error">
          {actionState.error}
        </div>
      )}
      {actionState.success && (
        <div className="action-message success">
          {actionState.success}
        </div>
      )}

      <div className="blocked-ips-list">
        {blockedIps.map((item) => (
          <div key={item.ip_address} className="blocked-ip-row">
            <label className="blocked-ip-select">
              <input
                type="checkbox"
                checked={!!selected[item.ip_address]}
                onChange={() => toggleIp(item.ip_address)}
              />
            </label>
            <div className="blocked-ip-details">
              <div className="blocked-ip-main">
                <span className="blocked-ip-address">{item.ip_address}</span>
                {item.reason && <span className="blocked-ip-reason">{item.reason}</span>}
              </div>
              <div className="blocked-ip-meta">
                {item.is_permanent ? (
                  <span className="blocked-ip-tag permanent">Permanent</span>
                ) : (
                  <span className="blocked-ip-tag">Expires {formatTimestamp(item.expires_at)}</span>
                )}
                {item.last_blocked_at && (
                  <span className="blocked-ip-tag">Last blocked {formatTimestamp(item.last_blocked_at)}</span>
                )}
                {Number.isFinite(item.block_count) && (
                  <span className="blocked-ip-tag">Count {item.block_count}</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatTimestamp(value) {
  if (!value) return 'Unknown';
  try {
    const date = new Date(value);
    return date.toLocaleString();
  } catch {
    return String(value);
  }
}

export default BlockedIpsPanel;

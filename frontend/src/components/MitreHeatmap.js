import React, { useEffect, useMemo, useState } from 'react';
import './MitreHeatmap.css';

const PLACEHOLDER_TECHNIQUES = [
  { technique_id: 'T1190', name: 'Exploit Public-Facing Application', count: 0 },
  { technique_id: 'T1110', name: 'Brute Force', count: 0 },
  { technique_id: 'T1046', name: 'Network Service Discovery', count: 0 },
  { technique_id: 'T1059', name: 'Command and Scripting Interpreter', count: 0 },
  { technique_id: 'T1078', name: 'Valid Accounts', count: 0 },
  { technique_id: 'T1133', name: 'External Remote Services', count: 0 },
  { technique_id: 'T1566', name: 'Phishing', count: 0 },
  { technique_id: 'T1204', name: 'User Execution', count: 0 },
  { technique_id: 'T1486', name: 'Data Encrypted for Impact', count: 0 },
  { technique_id: 'T1082', name: 'System Information Discovery', count: 0 },
  { technique_id: 'T1083', name: 'File and Directory Discovery', count: 0 },
  { technique_id: 'T1018', name: 'Remote System Discovery', count: 0 },
];

function normalizeSummary(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.data)) return payload.data;
  if (Array.isArray(payload?.summary)) return payload.summary;
  return [];
}

function getCellColor(count, maxCount) {
  if (!maxCount || count <= 0) {
    return '#1a2332';
  }

  const t = Math.max(0, Math.min(1, count / maxCount));

  // Interpolate in HSL from dark blue-gray to alert red
  const start = { h: 220, s: 32, l: 15 };
  const end = { h: 1, s: 84, l: 63 };

  const h = start.h + (end.h - start.h) * t;
  const s = start.s + (end.s - start.s) * t;
  const l = start.l + (end.l - start.l) * t;

  return `hsl(${h.toFixed(1)}, ${s.toFixed(1)}%, ${l.toFixed(1)}%)`;
}

function MitreHeatmap({ apiUrl, onFilter }) {
  const [techniques, setTechniques] = useState([]);
  const [showPlaceholderHeader, setShowPlaceholderHeader] = useState(false);
  const adminToken = process.env.REACT_APP_ADMIN_TOKEN || 'mayasec_internal_token';
  const apiBase = useMemo(() => {
    if (apiUrl) return apiUrl.replace(/\/$/, '');
    if (typeof window !== 'undefined' && window.location?.hostname) {
      return `http://${window.location.hostname}:5000`;
    }
    return 'http://localhost:5000';
  }, [apiUrl]);

  useEffect(() => {
    let mounted = true;

    const fetchSummary = async () => {
      try {
        const response = await fetch(`${apiBase}/api/v1/mitre/summary`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${adminToken}`,
          },
        });

        if (!response.ok) {
          throw new Error(`API Error: ${response.status}`);
        }

        const payload = await response.json();
        const rows = normalizeSummary(payload);

        if (!mounted) return;

        if (rows.length === 0) {
          setTechniques(PLACEHOLDER_TECHNIQUES);
          setShowPlaceholderHeader(true);
          return;
        }

        setTechniques(
          rows.map((row) => ({
            technique_id: row?.technique_id || 'UNKNOWN',
            name: row?.name || 'Unknown Technique',
            count: Number(row?.count) || 0,
          }))
        );
        setShowPlaceholderHeader(false);
      } catch {
        if (!mounted) return;
        setTechniques(PLACEHOLDER_TECHNIQUES);
        setShowPlaceholderHeader(true);
      }
    };

    fetchSummary();
    const intervalId = setInterval(fetchSummary, 60000);

    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, [adminToken, apiBase]);

  const maxCount = useMemo(() => {
    const counts = techniques.map((item) => Number(item?.count) || 0);
    return counts.length > 0 ? Math.max(...counts) : 0;
  }, [techniques]);

  const rowsToRender = techniques.length > 0 ? techniques : PLACEHOLDER_TECHNIQUES;

  const handleCellClick = (techniqueId) => {
    if (typeof onFilter === 'function') {
      onFilter(techniqueId);
    }
  };

  return (
    <div className="mitre-heatmap panel">
      <h3>MITRE ATT&CK Heatmap</h3>
      {showPlaceholderHeader && (
        <div className="mitre-heatmap-empty-header">No MITRE detections yet</div>
      )}

      <div className="mitre-heatmap-grid">
        {rowsToRender.map((item, index) => (
          <button
            key={`${item.technique_id}-${index}`}
            type="button"
            className={`mitre-cell ${typeof onFilter === 'function' ? 'clickable' : 'disabled'}`}
            style={{ backgroundColor: getCellColor(Number(item.count) || 0, maxCount) }}
            onClick={() => handleCellClick(item.technique_id)}
            title={`${item.technique_id} • ${item.name} • ${item.count}`}
          >
            <div className="mitre-id">{item.technique_id}</div>
            <div className="mitre-name">{item.name}</div>
            <div className="mitre-count">{Number(item.count) || 0}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

export default MitreHeatmap;

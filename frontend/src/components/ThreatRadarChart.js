import React, { useEffect, useMemo, useState } from 'react';
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import './ThreatRadarChart.css';

function ThreatRadarChart({ apiUrl, events = [] }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const defaultData = [
    { subject: 'SQLi', value: 0, fullMark: 100 },
    { subject: 'XSS', value: 0, fullMark: 100 },
    { subject: 'DDoS', value: 0, fullMark: 100 },
    { subject: 'BruteForce', value: 0, fullMark: 100 },
    { subject: 'PathTraversal', value: 0, fullMark: 100 },
    { subject: 'Probe', value: 0, fullMark: 100 },
  ];

  useEffect(() => {
    let isMounted = true;

    const fetchData = async () => {
      try {
        setLoading(true);
        const resolvedApiUrl = apiUrl
          || process.env.REACT_APP_API_URL
          || (typeof window !== 'undefined' && window.location?.hostname
            ? `http://${window.location.hostname}:5000`
            : 'http://localhost:5000');

        const token = process.env.REACT_APP_ADMIN_TOKEN || '';
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const response = await fetch(`${resolvedApiUrl}/api/v1/metrics/threat-distribution`, {
          method: 'GET',
          headers,
        });

        if (!response.ok) {
          throw new Error(`API Error: ${response.status} ${response.statusText}`);
        }

        const result = await response.json();

        if (isMounted) {
          const raw = Array.isArray(result)
            ? result
            : Array.isArray(result?.data)
              ? result.data
              : (result?.distribution && typeof result.distribution === 'object')
                ? Object.entries(result.distribution).map(([type, count]) => ({ type, count }))
                : [];

          if (raw.length > 0) {
            const transformedData = raw.map((item) => ({
              subject: item?.type || item?.subject || 'Unknown',
              value: Number(item?.count ?? item?.value ?? 0),
              fullMark: 100,
            }));
            setData(transformedData);
          } else {
            setData([]);
          }
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err?.message || 'Failed to load threat distribution');
          setData([]);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchData();

    const intervalId = setInterval(fetchData, 30000);

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, [apiUrl]);

  const fallbackFromEvents = useMemo(() => {
    if (!Array.isArray(events) || events.length === 0) {
      return [];
    }

    const byType = {};
    events.forEach((event) => {
      const eventType = String(event?.event_type || event?.type || 'Unknown');
      byType[eventType] = (byType[eventType] || 0) + 1;
    });

    return Object.entries(byType).map(([subject, value]) => ({
      subject,
      value,
      fullMark: 100,
    }));
  }, [events]);

  const activeData = data.length > 0
    ? data
    : (fallbackFromEvents.length > 0 ? fallbackFromEvents : defaultData);

  const showSubtitle = activeData === defaultData;

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      return (
        <div className="radar-tooltip">
          <p className="radar-tooltip-label">{`${payload[0].payload.subject}`}</p>
          <p className="radar-tooltip-value">{`Detections: ${payload[0].value}`}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="threat-radar-panel panel card">
      <div className="radar-header">
        <h3>Threat Distribution Radar</h3>
        {loading && <span className="radar-loading-indicator">Updating...</span>}
      </div>

      {showSubtitle && (
        <div className="radar-subtitle">
          {error ? <span className="error-text">API Error - Showing Schema</span> : 'No detections yet'}
        </div>
      )}

      <div className="radar-chart-container">
        <ResponsiveContainer width="100%" height={300}>
          <RadarChart cx="50%" cy="50%" outerRadius="70%" data={activeData}>
            <PolarGrid stroke="rgba(255, 255, 255, 0.15)" />
            <PolarAngleAxis
              dataKey="subject"
              tick={{ fill: '#8b949e', fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Radar
              name="Events"
              dataKey="value"
              stroke="#00ff9f"
              strokeWidth={2}
              fill="#00ff9f"
              fillOpacity={0.2}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default ThreatRadarChart;

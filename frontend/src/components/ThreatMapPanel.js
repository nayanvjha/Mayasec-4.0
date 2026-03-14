import React, { useEffect, useMemo, useState } from 'react';
import { ComposableMap, Geographies, Geography, Marker } from 'react-simple-maps';
import './ThreatMapPanel.css';

const WORLD_GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';

function toNumberOrNull(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function normalizeTopIps(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.data)) return payload.data;
  if (Array.isArray(payload?.top_ips)) return payload.top_ips;
  return [];
}

function ThreatMapPanel({ apiUrl }) {
  const [topIps, setTopIps] = useState([]);
  const [isEmptyOrError, setIsEmptyOrError] = useState(false);
  const [geoLoadFailed, setGeoLoadFailed] = useState(false);
  const apiBase = useMemo(() => {
    if (apiUrl) return apiUrl.replace(/\/$/, '');
    if (typeof window !== 'undefined' && window.location?.hostname) {
      return `http://${window.location.hostname}:5000`;
    }
    return 'http://localhost:5000';
  }, [apiUrl]);

  useEffect(() => {
    let mounted = true;

    const fetchTopIps = async () => {
      try {
        const response = await fetch(`${apiBase}/api/v1/metrics/top-ips`, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        });

        if (!response.ok) {
          throw new Error(`API Error: ${response.status}`);
        }

        const payload = await response.json();
        const rows = normalizeTopIps(payload);

        if (!mounted) return;

        setTopIps(rows);
        setIsEmptyOrError(rows.length === 0);
      } catch {
        if (!mounted) return;
        setTopIps([]);
        setIsEmptyOrError(true);
      }
    };

    fetchTopIps();
    const intervalId = setInterval(fetchTopIps, 60000);

    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, [apiBase]);

  useEffect(() => {
    let mounted = true;

    const checkGeo = async () => {
      try {
        const res = await fetch(WORLD_GEO_URL, { method: 'GET' });
        if (!res.ok) {
          throw new Error('GeoJSON load failed');
        }
        if (mounted) setGeoLoadFailed(false);
      } catch {
        if (mounted) setGeoLoadFailed(true);
      }
    };

    checkGeo();
  }, []);

  const markerData = useMemo(() => {
    const withCoords = topIps
      .map((row) => ({
        ip: row?.ip || 'unknown',
        count: Number(row?.count) || 0,
        country: row?.country || 'N/A',
        lat: toNumberOrNull(row?.lat),
        lng: toNumberOrNull(row?.lng),
      }))
      .filter((row) => row.lat !== null && row.lng !== null);

    if (withCoords.length === 0) return [];

    const counts = withCoords.map((x) => x.count);
    const minCount = Math.min(...counts);
    const maxCount = Math.max(...counts);

    return withCoords.map((row) => {
      let radius = 4;
      if (maxCount > minCount) {
        radius = 4 + ((row.count - minCount) / (maxCount - minCount)) * 12;
      }
      radius = Math.max(4, Math.min(16, radius));

      const ratio = maxCount > minCount
        ? (row.count - minCount) / (maxCount - minCount)
        : 1;
      const hue = 24 - (24 * ratio); // orange (24) -> red (0)
      const color = `hsl(${hue.toFixed(1)}, 84%, 62%)`;

      return {
        ...row,
        radius,
        color,
      };
    });
  }, [topIps]);

  const tableRows = useMemo(() => {
    return [...topIps]
      .sort((a, b) => (Number(b?.count) || 0) - (Number(a?.count) || 0))
      .slice(0, 10);
  }, [topIps]);

  return (
    <div className="threat-map-panel panel">
      <h3>Attacker Origin Map</h3>

      {geoLoadFailed ? (
        <div className="threat-map-fallback">
          <table className="threat-map-table">
            <thead>
              <tr>
                <th>IP</th>
                <th>Country</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.length > 0 ? (
                tableRows.map((row, idx) => (
                  <tr key={`${row?.ip || 'ip'}-${idx}`}>
                    <td>{row?.ip || 'N/A'}</td>
                    <td>{row?.country || 'N/A'}</td>
                    <td>{Number(row?.count) || 0}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3}>No attacker origins detected</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="threat-map-canvas">
          <ComposableMap projectionConfig={{ scale: 145 }}>
            <Geographies geography={WORLD_GEO_URL}>
              {({ geographies }) =>
                geographies.map((geo) => (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    style={{
                      default: {
                        fill: '#1a2332',
                        stroke: '#2a3a52',
                        strokeWidth: 0.6,
                        outline: 'none',
                      },
                      hover: {
                        fill: '#202c40',
                        stroke: '#2a3a52',
                        strokeWidth: 0.6,
                        outline: 'none',
                      },
                      pressed: {
                        fill: '#202c40',
                        stroke: '#2a3a52',
                        strokeWidth: 0.6,
                        outline: 'none',
                      },
                    }}
                  />
                ))
              }
            </Geographies>

            {markerData.map((row) => (
              <Marker key={`${row.ip}-${row.lat}-${row.lng}`} coordinates={[row.lng, row.lat]}>
                <circle r={row.radius} fill={row.color} fillOpacity={0.7} stroke={row.color} strokeWidth={1}>
                  <title>{`${row.ip} (${row.country}) • ${row.count}`}</title>
                </circle>
              </Marker>
            ))}
          </ComposableMap>
        </div>
      )}

      {isEmptyOrError && (
        <div className="threat-map-subtitle">No attacker origins detected</div>
      )}
    </div>
  );
}

export default ThreatMapPanel;

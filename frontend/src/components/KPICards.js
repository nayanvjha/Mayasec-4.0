import React, { useEffect, useMemo, useState } from 'react';
import { Server, Activity, AlertTriangle, Shield, Cpu, Bug } from 'lucide-react';
import './KPICards.css';

function resolveApiBase() {
  const envUrl = process.env.REACT_APP_API_URL;
  if (envUrl) {
    return envUrl.replace(/\/$/, '');
  }

  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `http://${window.location.hostname}:5000`;
  }

  return 'http://localhost:5000';
}

async function fetchJson(url) {
  const response = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`API Error: ${response.status}`);
  }
  return response.json();
}

function safeNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function formatValue(value, decimals = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }

  if (typeof value === 'number') {
    return decimals > 0 ? value.toFixed(decimals) : value.toLocaleString();
  }

  return String(value);
}

function KPICards({ events = [] }) {
  const apiBase = resolveApiBase();

  const [healthStatus, setHealthStatus] = useState(null);
  const [totalEvents, setTotalEvents] = useState(null);
  const [activeThreats, setActiveThreats] = useState(null);
  const [blockedIps, setBlockedIps] = useState(null);
  const [avgScore, setAvgScore] = useState(null);

  useEffect(() => {
    let mounted = true;

    const loadKpis = async () => {
      const healthPromise = fetchJson(`${apiBase}/api/v1/health`);
      const metricsPromise = fetchJson(`${apiBase}/api/v1/metrics`);
      const blockedPromise = fetchJson(`${apiBase}/api/v1/alerts/blocked`);

      const [healthResult, metricsResult, blockedResult] = await Promise.allSettled([
        healthPromise,
        metricsPromise,
        blockedPromise,
      ]);

      if (!mounted) return;

      if (healthResult.status === 'fulfilled') {
        const status = String(healthResult.value?.status || '').toLowerCase();
        setHealthStatus(status === 'healthy' ? 'Healthy' : 'Degraded');
      } else {
        setHealthStatus(null);
      }

      if (metricsResult.status === 'fulfilled') {
        const metrics = metricsResult.value || {};
        const total = safeNumber(metrics?.total_events);
        setTotalEvents(total);

        const avg = safeNumber(metrics?.avg_threat_score);
        setAvgScore(avg);

        if (Array.isArray(metrics?.events)) {
          const highThreatCount = metrics.events.filter((event) => Number(event?.threat_score) > 80).length;
          setActiveThreats(highThreatCount);
        } else {
          const fallbackActive = safeNumber(metrics?.active_threats);
          setActiveThreats(fallbackActive);
        }
      } else {
        setTotalEvents(null);
        setAvgScore(null);
        setActiveThreats(null);
      }

      if (blockedResult.status === 'fulfilled') {
        const payload = blockedResult.value;
        const blockedList = Array.isArray(payload)
          ? payload
          : Array.isArray(payload?.blocked_ips)
            ? payload.blocked_ips
            : Array.isArray(payload?.data)
              ? payload.data
              : [];
        setBlockedIps(blockedList.length);
      } else {
        setBlockedIps(null);
      }
    };

    loadKpis().catch(() => {
      if (!mounted) return;
      setHealthStatus(null);
      setTotalEvents(null);
      setActiveThreats(null);
      setBlockedIps(null);
      setAvgScore(null);
    });

    const intervalId = setInterval(() => {
      loadKpis().catch(() => {
        if (!mounted) return;
        setHealthStatus(null);
        setTotalEvents(null);
        setActiveThreats(null);
        setBlockedIps(null);
        setAvgScore(null);
      });
    }, 30000);

    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, [apiBase]);

  const cards = useMemo(
    () => [
      {
        key: 'status',
        icon: <Server size={18} />,
        label: 'System Status',
        value: healthStatus || '—',
        accent: 'status',
        statusDot: healthStatus ? (healthStatus === 'Healthy' ? 'healthy' : 'degraded') : 'unknown',
      },
      {
        key: 'total',
        icon: <Activity size={18} />,
        label: 'Total Events',
        value: formatValue(totalEvents),
        accent: 'events',
        trend: '↗',
      },
      {
        key: 'threats',
        icon: <AlertTriangle size={18} />,
        label: 'Active Threats',
        value: formatValue(activeThreats),
        accent: 'threats',
      },
      {
        key: 'blocked',
        icon: <Shield size={18} />,
        label: 'Blocked IPs',
        value: formatValue(blockedIps),
        accent: 'blocked',
      },
      {
        key: 'avg',
        icon: <Cpu size={18} />,
        label: 'ML Avg Score',
        value: avgScore === null ? '—' : formatValue(avgScore, 1),
        accent: 'ml',
      },
    ],
    [activeThreats, avgScore, blockedIps, healthStatus, totalEvents]
  );

  const derivedFromEvents = useMemo(() => {
    if (!Array.isArray(events) || events.length === 0) {
      return null;
    }

    const scores = events
      .map((event) => Number(event?.threat_score))
      .filter((v) => Number.isFinite(v));

    const total = events.length;
    const active = scores.filter((s) => s > 80).length;
    const avg = scores.length > 0
      ? scores.reduce((a, b) => a + b, 0) / scores.length
      : null;

    return { total, active, avg };
  }, [events]);

  const effectiveCards = useMemo(() => {
    if (!derivedFromEvents) {
      return cards;
    }

    return cards.map((card) => {
      if (card.key === 'total') {
        return { ...card, value: formatValue(derivedFromEvents.total) };
      }
      if (card.key === 'threats') {
        return { ...card, value: formatValue(derivedFromEvents.active) };
      }
      if (card.key === 'avg') {
        return {
          ...card,
          value: derivedFromEvents.avg === null ? card.value : formatValue(derivedFromEvents.avg, 1),
        };
      }
      return card;
    });
  }, [cards, derivedFromEvents]);

  const honeypotCatches = useMemo(() => {
    if (!Array.isArray(events) || events.length === 0) {
      return 0;
    }

    return events.filter((event) => (
      event?.destination === 'honeypot' || event?.data?.destination === 'honeypot'
    )).length;
  }, [events]);

  const cardsWithHoneypot = useMemo(
    () => [
      ...effectiveCards,
      {
        key: 'honeypot',
        icon: <Bug size={18} />,
        label: 'Honeypot Catches',
        value: formatValue(honeypotCatches),
        accent: 'honeypot',
      },
    ],
    [effectiveCards, honeypotCatches]
  );

  return (
    <div className="kpi-cards-row">
      {cardsWithHoneypot.map((card) => (
        <div key={card.key} className={`kpi-card card kpi-${card.accent}`}>
          <div className="kpi-header">
            <span className="kpi-icon">{card.icon}</span>
            <span className="kpi-label">{card.label}</span>
          </div>
          <div className="kpi-value-wrap">
            {card.statusDot && <span className={`kpi-dot ${card.statusDot}`} />}
            <span className="kpi-value">{card.value}</span>
            {card.trend && <span className="kpi-trend">{card.trend}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

export default KPICards;

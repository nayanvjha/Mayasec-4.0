import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ThreatMapPanel from './ThreatMapPanel';
import AttackStoryViewer from './AttackStoryViewer';
import DeceptionReplayModal from './DeceptionReplayModal';
import MitreHeatmap from './MitreHeatmap';
import KPICards from './KPICards';
import ActiveDeceptionPanel from './ActiveDeceptionPanel';
import { runDemoSequence } from '../utils/demoOrchestrator';
import './CommandCenter.css';

const ADMIN_TOKEN = process.env.REACT_APP_ADMIN_TOKEN || 'mayasec_internal_token';
const SERVER_POINT = { x: 78, y: 54 };

function severityFromEvent(event) {
  const raw = String(event?.severity_level || event?.threat_level || '').toLowerCase();
  if (raw === 'high' || raw === 'critical') return 'high';
  if (raw === 'medium') return 'medium';
  if (raw === 'low') return 'low';
  const score = Number(event?.threat_score || event?.score || event?.data?.score || 0);
  if (score >= 80) return 'high';
  if (score >= 50) return 'medium';
  return 'low';
}

function formatEvent(event) {
  return {
    id: event?.event_id || `${event?.timestamp || Date.now()}-${event?.source_ip || 'na'}`,
    timestamp: event?.timestamp || new Date().toISOString(),
    attackType: event?.attack_type || event?.event_type || event?.data?.event_type || 'unknown',
    sourceIp: event?.source_ip || event?.ip_address || event?.data?.source_ip || 'unknown',
    score: Number(event?.threat_score || event?.score || event?.data?.score || 0),
    severity: severityFromEvent(event),
    destination: event?.destination || event?.data?.destination || '',
    mitre: event?.mitre_technique_id || event?.technique_id || event?.data?.mitre_technique_id || event?.data?.technique_id || null,
    raw: event,
  };
}

function hashToPoint(seed) {
  const text = String(seed || '0.0.0.0');
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const x = 12 + (Math.abs(h) % 56);
  const y = 20 + ((Math.abs(h >> 8) % 55));
  return { x, y };
}

function severityRank(value) {
  const v = String(value || '').toLowerCase();
  if (v === 'critical') return 4;
  if (v === 'high') return 3;
  if (v === 'medium') return 2;
  return 1;
}

function durationLabel(start, end) {
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  if (!Number.isFinite(s) || !Number.isFinite(e) || e < s) return '—';
  const total = Math.floor((e - s) / 1000);
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return `${m}m ${String(sec).padStart(2, '0')}s`;
}

function AnimatedCounter({ value, suffix = '' }) {
  const [display, setDisplay] = useState(value || 0);

  useEffect(() => {
    const from = Number(display) || 0;
    const to = Number(value) || 0;
    const duration = 450;
    const start = performance.now();

    let raf = null;
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const current = from + (to - from) * eased;
      setDisplay(current);
      if (t < 1) {
        raf = requestAnimationFrame(step);
      }
    };

    raf = requestAnimationFrame(step);
    return () => {
      if (raf) cancelAnimationFrame(raf);
    };
  }, [value]);

  return <span>{`${Math.round(display).toLocaleString()}${suffix}`}</span>;
}

function phaseClass(name) {
  const low = String(name || '').toLowerCase();
  if (low.includes('recon')) return 'recon';
  if (low.includes('credential')) return 'credential';
  if (low.includes('exploit')) return 'exploit';
  if (low.includes('honeypot')) return 'honeypot';
  return 'other';
}

function CommandCenter({ apiUrl, connected, events = [], authUser, onNavigateLiveFeed }) {
  const [clock, setClock] = useState(new Date());
  const [isDemoRunning, setIsDemoRunning] = useState(false);
  const [feedEntries, setFeedEntries] = useState([]);
  const [arcs, setArcs] = useState([]);
  const [stories, setStories] = useState([]);
  const [activeStory, setActiveStory] = useState(null);
  const [expandViewer, setExpandViewer] = useState(false);
  const [replaySession, setReplaySession] = useState(null);
  const [metricSnapshot, setMetricSnapshot] = useState({ eps: 0, blockedToday: 0, activeStories: 0, honeypotSessions: 0 });
  const [showDeceptions, setShowDeceptions] = useState(false);
  const [activeDeceptionCount, setActiveDeceptionCount] = useState(0);
  const [deceptionFlash, setDeceptionFlash] = useState(false);

  const seenEventIds = useRef(new Set());
  const streamRef = useRef(null);
  const demoRunRef = useRef(null);
  const previousActiveDeceptionCount = useRef(0);

  const tenantName = authUser?.tenant_name || authUser?.tenant_id || 'Tenant Alpha';

  const recomputeMetrics = useCallback((entries, activeStoriesCount) => {
    const now = Date.now();
    const tenSec = entries.filter((e) => now - new Date(e.timestamp).getTime() <= 10000).length;
    const startOfDay = new Date();
    startOfDay.setHours(0, 0, 0, 0);

    const blockedToday = entries.filter((e) => {
      const ts = new Date(e.timestamp).getTime();
      const blockedByType = /blocked|redirect|deception/i.test(String(e.attackType || ''));
      return ts >= startOfDay.getTime() && blockedByType;
    }).length;

    const honeypotSessions = entries.filter((e) => String(e.destination || '').toLowerCase() === 'honeypot').length;

    setMetricSnapshot({
      eps: Math.max(0, Math.round((tenSec / 10) * 10) / 10),
      blockedToday,
      activeStories: activeStoriesCount,
      honeypotSessions,
    });
  }, []);

  const processIncomingEvent = useCallback((event) => {
    const normalized = formatEvent(event);
    const key = normalized.id;
    if (seenEventIds.current.has(key)) return;

    seenEventIds.current.add(key);
    setFeedEntries((prev) => {
      const next = [normalized, ...prev].slice(0, 50);
      recomputeMetrics(next, stories.filter((s) => String(s.status || '').toLowerCase() !== 'resolved').length);
      return next;
    });

    const start = hashToPoint(normalized.sourceIp);
    const arcId = `${normalized.id}-arc`;
    setArcs((prev) => [...prev, { id: arcId, start, end: SERVER_POINT }]);
    window.setTimeout(() => {
      setArcs((prev) => prev.filter((a) => a.id !== arcId));
    }, 820);
  }, [recomputeMetrics, stories]);

  useEffect(() => {
    const id = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!events || events.length === 0) return;
    const newest = events[0];
    processIncomingEvent(newest);
  }, [events, processIncomingEvent]);

  useEffect(() => {
    if (!streamRef.current) return;
    streamRef.current.scrollTop = 0;
  }, [feedEntries]);

  useEffect(() => {
    let mounted = true;

    const loadStories = async () => {
      try {
        const res = await fetch(`${apiUrl}/api/v1/stories?limit=25`, {
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${ADMIN_TOKEN}`,
          },
        });
        const data = await res.json();
        if (!mounted) return;
        const list = Array.isArray(data) ? data : [];
        setStories(list);

        if (list.length > 0) {
          const next = [...list].sort((a, b) => {
            const sev = severityRank(b.severity) - severityRank(a.severity);
            if (sev !== 0) return sev;
            return new Date(b.end_time || b.created_at || 0).getTime() - new Date(a.end_time || a.created_at || 0).getTime();
          })[0];

          const detailRes = await fetch(`${apiUrl}/api/v1/stories/${next.id}`, {
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${ADMIN_TOKEN}`,
            },
          });
          const detail = await detailRes.json();
          if (mounted && detailRes.ok) setActiveStory(detail);
        } else {
          setActiveStory(null);
        }

        recomputeMetrics(feedEntries, list.filter((s) => String(s.status || '').toLowerCase() !== 'resolved').length);
      } catch {
        if (!mounted) return;
        setStories([]);
        setActiveStory(null);
      }
    };

    loadStories();
    const id = setInterval(loadStories, 10000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [apiUrl, recomputeMetrics, feedEntries]);

  useEffect(() => () => {
    if (demoRunRef.current?.cancel) {
      demoRunRef.current.cancel();
    }
  }, []);

  const attacksLast5m = useMemo(() => {
    const now = Date.now();
    return feedEntries.filter((e) => now - new Date(e.timestamp).getTime() <= 5 * 60 * 1000).length;
  }, [feedEntries]);

  const topMitre = useMemo(() => {
    const counts = new Map();
    feedEntries.forEach((e) => {
      if (!e.mitre) return;
      counts.set(e.mitre, (counts.get(e.mitre) || 0) + 1);
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
  }, [feedEntries]);

  const replayCapture = useMemo(() => {
    const phases = Array.isArray(activeStory?.timeline) ? activeStory.timeline : [];
    const match = phases.find((p) => p?.capture_preview);
    return match?.capture_preview || null;
  }, [activeStory]);

  const onStartDemo = () => {
    if (isDemoRunning) return;
    setIsDemoRunning(true);
    const run = runDemoSequence((demoEvent) => processIncomingEvent(demoEvent));
    demoRunRef.current = run;
    run.done.finally(() => setIsDemoRunning(false));
  };

  const handleActiveCountChange = useCallback((count) => {
    setActiveDeceptionCount(Number(count) || 0);
    if ((Number(count) || 0) > previousActiveDeceptionCount.current) {
      setDeceptionFlash(true);
      window.setTimeout(() => setDeceptionFlash(false), 1000);
    }
    previousActiveDeceptionCount.current = Number(count) || 0;
  }, []);

  const handleReplayFromSession = useCallback(async (sessionId) => {
    if (!sessionId) return;
    try {
      const res = await fetch(`${apiUrl}/api/v1/honeypot/sessions/${sessionId}/timeline?limit=50`, {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${ADMIN_TOKEN}`,
        },
      });
      const timeline = await res.json();
      const list = Array.isArray(timeline) ? timeline : [];
      const latest = list[list.length - 1];
      if (!latest) return;
      setReplaySession({
        session_id: latest.session_id,
        source_ip: latest.source_ip,
        attack_type: latest.attack_type,
        request_payload: latest.request_payload,
        response_snippet: latest.response_snippet,
        timestamp: latest.timestamp,
        waf_score: 88,
        uri: '/honeypot',
      });
    } catch {
      // no-op
    }
  }, [apiUrl]);

  useEffect(() => {
    let mounted = true;
    const loadActiveCount = async () => {
      try {
        const res = await fetch(`${apiUrl}/api/v1/honeypot/active-sessions?limit=200`, {
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${ADMIN_TOKEN}`,
          },
        });
        const data = await res.json();
        if (!mounted) return;
        handleActiveCountChange(Array.isArray(data) ? data.length : 0);
      } catch {
        if (!mounted) return;
        handleActiveCountChange(0);
      }
    };

    loadActiveCount();
    const id = setInterval(loadActiveCount, 3000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [apiUrl, handleActiveCountChange]);

  return (
    <section className="command-center-root" role="tabpanel" aria-label="Command Center">
      <header className="cc-header">
        <div className="cc-title">MAYASEC COMMAND CENTER</div>
        <div className={`cc-live-state ${isDemoRunning ? 'sim' : 'live'}`}>
          <span className="cc-live-dot" />
          <span>{isDemoRunning ? 'SIMULATION' : 'LIVE'}</span>
          {!connected && <span className="cc-disconnected">WS OFFLINE</span>}
        </div>
        <div className="cc-header-right">
          <span className="cc-time">{clock.toLocaleTimeString()}</span>
          <span className="cc-tenant">{tenantName}</span>
          <button
            type="button"
            className={`cc-deception-badge ${deceptionFlash ? 'flash' : ''}`}
            onClick={() => setShowDeceptions(true)}
          >
            Active Deceptions: {activeDeceptionCount}
          </button>
          <button type="button" className="cc-demo-btn" onClick={onStartDemo} disabled={isDemoRunning}>
            {isDemoRunning ? 'Running Demo…' : 'Start Demo'}
          </button>
        </div>
      </header>

      <div className="cc-grid">
        <section className="cc-panel cc-map">
          <div className="cc-panel-title">Threat Map</div>
          <div className="cc-map-wrapper">
            <ThreatMapPanel apiUrl={apiUrl} />
            <div className="cc-map-overlay-count">{attacksLast5m} attacks in last 5 minutes</div>
            <svg className="cc-arc-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              {arcs.map((arc) => {
                const cx = (arc.start.x + arc.end.x) / 2;
                const cy = Math.max(6, Math.min(50, Math.min(arc.start.y, arc.end.y) - 20));
                return (
                  <path
                    key={arc.id}
                    className="cc-arc"
                    d={`M ${arc.start.x} ${arc.start.y} Q ${cx} ${cy} ${arc.end.x} ${arc.end.y}`}
                  />
                );
              })}
            </svg>
          </div>
        </section>

        <section className="cc-panel cc-feed">
          <div className="cc-panel-title">Attack Feed</div>
          <div className="cc-feed-list" ref={streamRef}>
            {feedEntries.map((item) => (
              <button
                type="button"
                key={item.id}
                className="cc-feed-row"
                onClick={() => onNavigateLiveFeed?.(item.raw)}
              >
                <span>{new Date(item.timestamp).toLocaleTimeString()}</span>
                <span className={`cc-sev-dot ${item.severity}`} />
                <span className="cc-attack-type">{item.attackType}</span>
                <span>{item.sourceIp}</span>
                <span className="cc-score">score={item.score}</span>
              </button>
            ))}
            {feedEntries.length === 0 && <div className="cc-empty">Waiting for telemetry…</div>}
          </div>
        </section>

        <section className="cc-panel cc-story">
          <div className="cc-panel-title">Active Story</div>
          {activeStory ? (
            <>
              <div className="cc-story-header">
                <h3>{activeStory.title}</h3>
                <div className="cc-story-meta">
                  <span>{activeStory.attacker_ip}</span>
                  <span>{durationLabel(activeStory.start_time, activeStory.end_time)}</span>
                  <span className={`cc-story-sev ${String(activeStory.severity || '').toLowerCase()}`}>{String(activeStory.severity || '').toUpperCase()}</span>
                </div>
              </div>
              <div className="cc-phase-list">
                {(activeStory.timeline || []).map((phase, idx) => (
                  <div key={`${phase.phase}-${idx}`} className={`cc-phase ${phaseClass(phase.phase)}`}>
                    <div className="cc-phase-name">{phase.phase}</div>
                    <div className="cc-phase-sub">{phase.event_count || 0} events · Score {phase.score_range || '—'}</div>
                  </div>
                ))}
              </div>
              <p className="cc-narrative">{activeStory.narrative || 'Narrative pending…'}</p>
              <div className="cc-story-actions">
                <button type="button" onClick={() => setExpandViewer(true)}>Expand</button>
                <button
                  type="button"
                  disabled={!replayCapture}
                  onClick={() => {
                    if (!replayCapture) return;
                    setReplaySession({
                      session_id: replayCapture.session_id,
                      source_ip: replayCapture.source_ip,
                      attack_type: replayCapture.attack_type,
                      request_payload: replayCapture.request_payload,
                      response_snippet: replayCapture.llm_response,
                      timestamp: replayCapture.timestamp,
                      waf_score: replayCapture.waf_score,
                      uri: '/honeypot',
                    });
                  }}
                >
                  Replay
                </button>
              </div>
            </>
          ) : (
            <div className="cc-empty">No active attack stories.</div>
          )}
        </section>

        <section className="cc-panel cc-stats">
          <div className="cc-panel-title">Threat Stats</div>
          <div className="cc-stats-grid">
            <div className="cc-stat-card">
              <span>Events / second</span>
              <strong><AnimatedCounter value={metricSnapshot.eps} /></strong>
            </div>
            <div className="cc-stat-card">
              <span>Attacks blocked today</span>
              <strong><AnimatedCounter value={metricSnapshot.blockedToday} /></strong>
            </div>
            <div className="cc-stat-card">
              <span>Active attack stories</span>
              <strong><AnimatedCounter value={metricSnapshot.activeStories} /></strong>
            </div>
            <div className="cc-stat-card">
              <span>Honeypot sessions</span>
              <strong><AnimatedCounter value={metricSnapshot.honeypotSessions} /></strong>
            </div>
          </div>
          <div className="cc-kpi-embed">
            <KPICards events={feedEntries.map((f) => f.raw)} />
          </div>
        </section>

        <section className="cc-panel cc-mitre">
          <div className="cc-panel-title">MITRE Heatmap</div>
          <div className="cc-mitre-wrap">
            <MitreHeatmap apiUrl={apiUrl} />
          </div>
          <div className="cc-mitre-top8">
            {topMitre.map(([id, count]) => (
              <span key={id}>{id} · {count}</span>
            ))}
          </div>
        </section>
      </div>

      {expandViewer && (
        <div className="cc-story-modal" role="dialog" aria-modal="true">
          <div className="cc-story-modal-header">
            <span>Attack Story Viewer</span>
            <button type="button" onClick={() => setExpandViewer(false)}>Close</button>
          </div>
          <div className="cc-story-modal-body">
            <AttackStoryViewer apiUrl={apiUrl} />
          </div>
        </div>
      )}

      <DeceptionReplayModal
        session={replaySession}
        isOpen={Boolean(replaySession)}
        onClose={() => setReplaySession(null)}
      />

      <ActiveDeceptionPanel
        apiUrl={apiUrl}
        isOpen={showDeceptions}
        onClose={() => setShowDeceptions(false)}
        onViewTimeline={() => {
          setExpandViewer(true);
          setShowDeceptions(false);
        }}
        onReplaySession={handleReplayFromSession}
        onActiveCountChange={handleActiveCountChange}
      />
    </section>
  );
}

export default CommandCenter;

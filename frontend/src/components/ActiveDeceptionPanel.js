import React, { useEffect, useMemo, useState } from 'react';

const ADMIN_TOKEN = process.env.REACT_APP_ADMIN_TOKEN || 'mayasec_internal_token';

function toDurationLabel(seconds) {
  const s = Math.max(0, Number(seconds) || 0);
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${String(rem).padStart(2, '0')}s`;
}

function ActiveDeceptionPanel({ apiUrl, isOpen, onClose, onViewTimeline, onReplaySession, onActiveCountChange }) {
  const [sessions, setSessions] = useState([]);
  const [watchSessionId, setWatchSessionId] = useState(null);
  const [watchFeed, setWatchFeed] = useState([]);

  useEffect(() => {
    if (!isOpen) return undefined;
    let mounted = true;

    const loadSessions = async () => {
      try {
        const res = await fetch(`${apiUrl}/api/v1/honeypot/active-sessions?limit=100`, {
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${ADMIN_TOKEN}`,
          },
        });
        const data = await res.json();
        if (!mounted) return;
        const list = Array.isArray(data) ? data : [];
        setSessions(list);
        if (typeof onActiveCountChange === 'function') onActiveCountChange(list.length);
      } catch {
        if (!mounted) return;
        setSessions([]);
      }
    };

    loadSessions();
    const id = setInterval(loadSessions, 3000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [apiUrl, isOpen, onActiveCountChange]);

  useEffect(() => {
    if (!watchSessionId) return undefined;
    let mounted = true;

    const loadTimeline = async () => {
      try {
        const res = await fetch(`${apiUrl}/api/v1/honeypot/sessions/${watchSessionId}/timeline?limit=120`, {
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${ADMIN_TOKEN}`,
          },
        });
        const data = await res.json();
        if (!mounted) return;
        const list = Array.isArray(data) ? data : [];
        setWatchFeed(list.slice(-20).reverse());
      } catch {
        if (!mounted) return;
        setWatchFeed([]);
      }
    };

    loadTimeline();
    const id = setInterval(loadTimeline, 3000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [apiUrl, watchSessionId]);

  const watchSession = useMemo(() => sessions.find((s) => s.session_id === watchSessionId) || null, [sessions, watchSessionId]);

  if (!isOpen) return null;

  return (
    <aside className="active-deception-sidebar" role="dialog" aria-modal="true" aria-label="Active Deception Sessions">
      <div className="ads-header">
        <strong>ACTIVE DECEPTION SESSIONS</strong>
        <span>[{sessions.length} active]</span>
        <button type="button" onClick={onClose}>Close</button>
      </div>

      <div className="ads-list">
        {sessions.map((session) => (
          <article key={session.id || session.session_id} className="ads-item">
            <div className="ads-row">
              <span>IP: {session.source_ip}</span>
              <span>Duration: {toDurationLabel(session.duration_seconds)}</span>
              <span>Interactions: {session.interaction_count}</span>
            </div>
            <div className="ads-row ads-dim">
              <span>Tools: {(session.detected_tools || []).join(', ') || 'manual'}</span>
              <span>Skill: {session.skill_level}</span>
            </div>
            <div className="ads-row ads-dim">
              <span>Phase: {session.attack_phase}</span>
              <span>Environment: {session.environment}</span>
            </div>
            <div className="ads-actions">
              <button type="button" onClick={() => setWatchSessionId(session.session_id)}>Watch Live</button>
              <button type="button" onClick={() => onViewTimeline?.(session.session_id)}>View Timeline</button>
              <button type="button" onClick={() => onReplaySession?.(session.session_id)}>View Fake Environment</button>
            </div>
          </article>
        ))}
        {sessions.length === 0 && <div className="ads-empty">No active deception sessions.</div>}
      </div>

      {watchSessionId && (
        <div className="ads-watch">
          <div className="ads-watch-header">
            <strong>WATCH LIVE: {watchSession?.source_ip || watchSessionId}</strong>
            <button type="button" onClick={() => setWatchSessionId(null)}>Stop</button>
          </div>
          <div className="ads-watch-feed">
            {watchFeed.map((item) => (
              <div key={item.id} className="ads-watch-row">
                <span>{new Date(item.timestamp).toLocaleTimeString()}</span>
                <span>{item.attack_type}</span>
                <span>{String(item.request_payload || '').slice(0, 120)}</span>
              </div>
            ))}
            {watchFeed.length === 0 && <div className="ads-empty">No interactions yet.</div>}
          </div>
        </div>
      )}
    </aside>
  );
}

export default ActiveDeceptionPanel;

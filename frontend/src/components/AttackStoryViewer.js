import React, { useEffect, useMemo, useState } from 'react';
import DeceptionReplayModal from './DeceptionReplayModal';
import './AttackStoryViewer.css';

function phaseClass(name) {
  const low = String(name || '').toLowerCase();
  if (low.includes('recon')) return 'phase-recon';
  if (low.includes('credential')) return 'phase-credential';
  if (low.includes('exploit')) return 'phase-exploitation';
  if (low.includes('deception')) return 'phase-deception';
  if (low.includes('honeypot')) return 'phase-honeypot';
  return '';
}

function toDuration(start, end) {
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  if (!Number.isFinite(s) || !Number.isFinite(e) || e < s) return '—';
  const total = Math.floor((e - s) / 1000);
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return `${m}m ${String(sec).padStart(2, '0')}s`;
}

function AttackStoryViewer({ apiUrl }) {
  const [stories, setStories] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [replaySession, setReplaySession] = useState(null);

  const adminToken = process.env.REACT_APP_ADMIN_TOKEN || 'mayasec_internal_token';

  useEffect(() => {
    let mounted = true;

    const loadStories = async () => {
      try {
        setLoading(true);
        const res = await fetch(`${apiUrl}/api/v1/stories?limit=100`, {
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${adminToken}`,
          },
        });
        const data = await res.json();
        if (!mounted) return;
        const list = Array.isArray(data) ? data : [];
        setStories(list);
        if (!selectedId && list.length > 0) {
          setSelectedId(list[0].id);
        }
      } catch {
        if (!mounted) return;
        setStories([]);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    loadStories();
    const id = setInterval(loadStories, 30000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [apiUrl, adminToken, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      return;
    }

    let mounted = true;
    const loadDetail = async () => {
      try {
        const res = await fetch(`${apiUrl}/api/v1/stories/${selectedId}`, {
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${adminToken}`,
          },
        });
        const data = await res.json();
        if (!mounted) return;
        if (res.ok) setSelected(data);
      } catch {
        if (!mounted) return;
        setSelected(null);
      }
    };

    loadDetail();
    return () => {
      mounted = false;
    };
  }, [apiUrl, selectedId, adminToken]);

  const honeypotPhase = useMemo(() => {
    const phases = Array.isArray(selected?.timeline) ? selected.timeline : [];
    return phases.find((p) => String(p?.phase || '').toLowerCase().includes('honeypot')) || null;
  }, [selected]);

  const handleStatusChange = async (status) => {
    if (!selected?.id || !status) return;
    try {
      await fetch(`${apiUrl}/api/v1/stories/${selected.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${adminToken}`,
        },
        body: JSON.stringify({ status }),
      });
      setSelected((prev) => (prev ? { ...prev, status } : prev));
      setStories((prev) => prev.map((s) => (s.id === selected.id ? { ...s, status } : s)));
    } catch {
      // no-op
    }
  };

  return (
    <div className="attack-story-viewer">
      <aside className="story-list">
        <div className="story-list-header">
          <h3>Attack Stories</h3>
        </div>

        {loading && <div className="story-empty">Loading stories...</div>}
        {!loading && stories.length === 0 && <div className="story-empty">No stories yet.</div>}

        {stories.map((story) => (
          <button
            key={story.id}
            type="button"
            className={`story-list-item ${selectedId === story.id ? 'active' : ''}`}
            onClick={() => setSelectedId(story.id)}
          >
            <div className="story-title">{story.title}</div>
            <div className="story-meta">
              <span>{story.attacker_ip}</span>
              <span>{String(story.severity || '').toUpperCase()}</span>
              <span>{story.event_count || 0} events</span>
            </div>
          </button>
        ))}
      </aside>

      <section className="story-detail">
        {!selected && <div className="story-empty">Select a story to inspect timeline.</div>}

        {selected && (
          <>
            <h2 className="story-headline">ATTACK STORY: {selected.title}</h2>
            <div className="story-top-meta">
              <span>Attacker: {selected.attacker_ip}</span>
              <span>Duration: {toDuration(selected.start_time, selected.end_time)}</span>
              <span>Severity: {String(selected.severity || '').toUpperCase()}</span>
              <span>Status: {selected.status}</span>
            </div>

            <div className="story-narrative">{selected.narrative || 'Narrative pending...'}</div>

            <div className="story-controls">
              <label htmlFor="story-status">Status</label>
              <select
                id="story-status"
                value={selected.status || 'active'}
                onChange={(e) => handleStatusChange(e.target.value)}
              >
                <option value="active">active</option>
                <option value="investigating">investigating</option>
                <option value="resolved">resolved</option>
              </select>
              <button
                type="button"
                disabled={!honeypotPhase?.capture_preview}
                onClick={() => {
                  if (!honeypotPhase?.capture_preview) return;
                  const c = honeypotPhase.capture_preview;
                  setReplaySession({
                    session_id: c.session_id,
                    source_ip: c.source_ip,
                    attack_type: c.attack_type,
                    request_payload: c.request_payload,
                    response_snippet: c.llm_response,
                    timestamp: c.timestamp,
                    waf_score: c.waf_score,
                    uri: '/honeypot',
                  });
                }}
              >
                View Fake Environment
              </button>
            </div>

            <div className="phase-timeline">
              {(selected.timeline || []).map((phase, idx) => (
                <article key={`${phase.phase}-${idx}`} className={`phase-card ${phaseClass(phase.phase)}`}>
                  <h4 className="phase-title">{phase.phase}</h4>
                  <div className="phase-meta">
                    <span>{phase.start_time || '—'}</span>
                    <span>{phase.event_count || 0} events</span>
                    <span>Score {phase.score_range || '—'}</span>
                  </div>
                  <div className="phase-desc">{phase.description || 'No description'}</div>
                  {Array.isArray(phase.mitre) && phase.mitre.length > 0 && (
                    <div className="phase-mitre">
                      {phase.mitre.map((m) => (
                        <span key={m} className="phase-pill">MITRE: {m}</span>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </>
        )}
      </section>

      <DeceptionReplayModal
        session={replaySession}
        isOpen={Boolean(replaySession)}
        onClose={() => setReplaySession(null)}
      />
    </div>
  );
}

export default AttackStoryViewer;

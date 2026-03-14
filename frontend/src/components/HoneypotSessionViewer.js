import React, { useEffect, useMemo, useState } from 'react';
import { RotateCcw } from 'lucide-react';
import DeceptionReplayModal from './DeceptionReplayModal';
import './HoneypotSessionViewer.css';

function timeAgo(ts) {
  const t = new Date(ts).getTime();
  if (!Number.isFinite(t)) return 'unknown';
  const delta = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

function severityClass(score) {
  if (score >= 90) return 'critical';
  if (score >= 75) return 'high';
  if (score >= 50) return 'medium';
  return 'low';
}

function HoneypotSessionViewer({ apiUrl }) {
  const [sessions, setSessions] = useState([]);
  const [replaySession, setReplaySession] = useState(null);
  const [attackType, setAttackType] = useState('');
  const [sourceIp, setSourceIp] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      const params = new URLSearchParams({ limit: '200', offset: '0' });
      if (attackType) params.set('attack_type', attackType);

      try {
        const res = await fetch(`${apiUrl}/api/v1/honeypot/sessions?${params.toString()}`);
        const data = await res.json();
        if (!mounted) return;
        setSessions(Array.isArray(data) ? data : []);
      } catch {
        if (!mounted) return;
        setSessions([]);
      }
    };

    load();
    const id = setInterval(load, 15000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [apiUrl, attackType]);

  const filtered = useMemo(() => {
    return sessions.filter((s) => {
      if (sourceIp && !String(s.source_ip || '').includes(sourceIp)) return false;
      const t = s.timestamp ? new Date(s.timestamp).getTime() : NaN;
      if (startDate) {
        const st = new Date(startDate).getTime();
        if (Number.isFinite(t) && t < st) return false;
      }
      if (endDate) {
        const et = new Date(endDate).getTime();
        if (Number.isFinite(t) && t > et) return false;
      }
      return true;
    });
  }, [sessions, sourceIp, startDate, endDate]);

  const attackTypes = useMemo(() => {
    const set = new Set(sessions.map((s) => s.attack_type).filter(Boolean));
    return Array.from(set).sort();
  }, [sessions]);

  return (
    <>
      <div className="honeypot-session-viewer panel">
        <h3>Honeypot Session Viewer</h3>

        <div className="honeypot-toolbar">
          <select className="honeypot-select" value={attackType} onChange={(e) => setAttackType(e.target.value)}>
            <option value="">All attack types</option>
            {attackTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input
            className="honeypot-input"
            placeholder="Filter source IP"
            value={sourceIp}
            onChange={(e) => setSourceIp(e.target.value)}
          />
          <input className="honeypot-input" type="datetime-local" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          <input className="honeypot-input" type="datetime-local" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>

        <div className="honeypot-list">
          {filtered.length === 0 && <div className="honeypot-empty">No honeypot sessions found.</div>}

          {filtered.map((s) => {
            const key = `${s.session_id || 'sid'}-${s.timestamp || ''}`;
            const sev = severityClass(Number(s.waf_score || 0));

            return (
              <div key={key} className="honeypot-card">
                <div className="honeypot-card-head">
                  <span className="honeypot-attack-badge">{s.attack_type || 'unknown'}</span>
                  <span className={`honeypot-sev-badge honeypot-sev-${sev}`}>WAF {Number(s.waf_score || 0)}</span>
                </div>

                <div className="honeypot-meta">
                  <span><strong>IP:</strong> {s.source_ip || 'n/a'}</span>
                  <span><strong>URI:</strong> {s.uri || '/'}</span>
                  <span><strong>Time:</strong> {timeAgo(s.timestamp)}</span>
                </div>

                <div className="honeypot-snippet">
                  <strong>Request:</strong> {(s.request_payload || '').slice(0, 180)}
                </div>

                <div className="honeypot-snippet">
                  <strong>Response:</strong> {(s.response_snippet || '').slice(0, 180)}
                </div>

                <div className="honeypot-actions">
                  <button
                    className="replay-btn"
                    onClick={() => setReplaySession(s)}
                  >
                    <RotateCcw size={14} />
                    Replay Attack
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <DeceptionReplayModal
        session={replaySession}
        isOpen={Boolean(replaySession)}
        onClose={() => setReplaySession(null)}
      />
    </>
  );
}

export default HoneypotSessionViewer;

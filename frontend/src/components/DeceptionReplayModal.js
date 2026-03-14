import React, { useEffect, useMemo, useState } from 'react';
import { Play, Pause, SkipBack, SkipForward, X } from 'lucide-react';
import './DeceptionReplayModal.css';

const STAGES = [
  {
    title: 'Attacker Payload Received',
    subtitle: 'Incoming attack captured at ingress'
  },
  {
    title: 'Live Attack Flow — ML Analysis and Routing Decision',
    subtitle: 'Packet traverses interception pipeline'
  },
  {
    title: 'Deception Environment Activated',
    subtitle: 'Attacker rendered into AI-generated fake environment'
  },
  {
    title: 'Intelligence Extraction',
    subtitle: 'Threat intelligence harvested from controlled interaction'
  }
];

const MITRE_BY_ATTACK = {
  sql_injection: { id: 'T1190', name: 'Exploit Public-Facing Application' },
  xss: { id: 'T1059.007', name: 'Command and Scripting Interpreter: JavaScript' },
  command_injection: { id: 'T1059.004', name: 'Unix Shell' },
  path_traversal: { id: 'T1006', name: 'Direct Volume Access' },
  auth_bypass: { id: 'T1078', name: 'Valid Accounts' },
  rce: { id: 'T1068', name: 'Exploitation for Privilege Escalation' },
  unknown: { id: 'T1190', name: 'Exploit Public-Facing Application' }
};

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

function isJSON(text) {
  if (!text || typeof text !== 'string') return false;
  try {
    JSON.parse(text);
    return true;
  } catch {
    return false;
  }
}

function inferAttackType(payload) {
  const value = String(payload || '').toLowerCase();
  if (/select\s+.*from|union\s+select|or\s+1=1|information_schema/.test(value)) return 'sql_injection';
  if (/<script|onerror=|onload=|javascript:/.test(value)) return 'xss';
  if (/\bcat\s+\/etc\/passwd\b|\bwget\b|\bcurl\b|\b;\s*id\b|\|\s*sh\b/.test(value)) return 'command_injection';
  if (/\.\.\/|%2e%2e%2f/.test(value)) return 'path_traversal';
  return 'unknown';
}

function estimateScore(payload, attackType) {
  const size = String(payload || '').length;
  const entropyBump = /--|\bunion\b|<script|\/etc\/passwd|\bselect\b/i.test(payload || '') ? 22 : 10;
  const attackWeight = {
    sql_injection: 34,
    xss: 28,
    command_injection: 38,
    path_traversal: 30,
    auth_bypass: 36,
    rce: 42,
    unknown: 20
  };
  const sizeWeight = Math.min(20, Math.round(size / 25));
  return clamp((attackWeight[attackType] || 20) + entropyBump + sizeWeight, 8, 99);
}

function extractIndicators(payload, sourceIp) {
  const value = String(payload || '');
  const urls = value.match(/https?:\/\/[^\s"']+/gi) || [];
  const ips = value.match(/\b\d{1,3}(?:\.\d{1,3}){3}\b/g) || [];
  const commands = value.match(/\b(cat|wget|curl|chmod|bash|sh|python|nc|nmap)\b/gi) || [];
  const unique = (arr) => Array.from(new Set(arr)).slice(0, 4);

  return {
    iocs: unique([...urls, ...ips, ...(sourceIp ? [sourceIp] : [])]),
    commands: unique(commands)
  };
}

function severityFromScore(score) {
  if (score >= 90) return 'Critical';
  if (score >= 75) return 'High';
  if (score >= 50) return 'Medium';
  return 'Low';
}

function deriveMethod(payload, fallbackUri = '/') {
  const text = String(payload || '').trim();
  const firstLine = text.split('\n')[0] || '';
  const methodMatch = firstLine.match(/^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b/i);
  const uriMatch = firstLine.match(/^(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)/i);
  return {
    method: (methodMatch?.[1] || 'GET').toUpperCase(),
    uri: uriMatch?.[1] || fallbackUri || '/'
  };
}

function payloadToHtml(payload) {
  const text = String(payload || '');
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/("[^"]*"|'[^']*')/g, '<span class="drm-syntax-string">$1</span>')
    .replace(/\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|SELECT|UNION|DROP|INSERT|UPDATE|FROM|WHERE|OR|AND)\b/gi, '<span class="drm-syntax-keyword">$1</span>')
    .replace(/\b\d+(?:\.\d+)?\b/g, '<span class="drm-syntax-number">$&</span>');
}

function JsonTreeNode({ label, value, depth = 0 }) {
  const isObject = value && typeof value === 'object';
  const isArray = Array.isArray(value);
  const [open, setOpen] = useState(depth < 2);

  if (!isObject) {
    return (
      <div className="drm-json-line" style={{ marginLeft: depth * 12 }}>
        {label ? <span className="drm-json-key">{label}: </span> : null}
        <span className="drm-json-primitive">{JSON.stringify(value)}</span>
      </div>
    );
  }

  const entries = isArray
    ? value.map((item, idx) => [String(idx), item])
    : Object.entries(value);

  return (
    <div className="drm-json-node" style={{ marginLeft: depth * 12 }}>
      <button type="button" className="drm-json-toggle" onClick={() => setOpen((v) => !v)}>
        {open ? '▾' : '▸'} {label ? <span className="drm-json-key">{label}: </span> : null}
        <span className="drm-json-brace">{isArray ? '[' : '{'}</span>
      </button>
      {open && entries.map(([k, v]) => (
        <JsonTreeNode key={`${depth}-${k}`} label={k} value={v} depth={depth + 1} />
      ))}
      {open && <div className="drm-json-line" style={{ marginLeft: (depth + 1) * 12 }}><span className="drm-json-brace">{isArray ? ']' : '}'}</span></div>}
    </div>
  );
}

export default function DeceptionReplayModal({ session, isOpen, onClose }) {
  const [currentStage, setCurrentStage] = useState(0);
  const [autoplay, setAutoplay] = useState(true);
  const [splitView, setSplitView] = useState(false);
  const [pipelinePhase, setPipelinePhase] = useState(0);

  const requestPayload = String(session?.request_payload || '');
  const responseSnippet = String(session?.response_snippet || '');
  const attackType = String(session?.attack_type || inferAttackType(requestPayload));
  const requestMeta = deriveMethod(requestPayload, session?.uri || '/');

  const score = useMemo(() => {
    if (!session) return 0;
    const source = Number(session.waf_score);
    if (Number.isFinite(source) && source > 0) return clamp(Math.round(source), 0, 100);
    return estimateScore(requestPayload, attackType);
  }, [session, requestPayload, attackType]);

  const mitre = MITRE_BY_ATTACK[attackType] || MITRE_BY_ATTACK.unknown;
  const indicators = extractIndicators(requestPayload, session?.source_ip);
  const severity = severityFromScore(score);
  const blocked = score >= 80;
  const estimatedDuration = Math.max(8, Math.min(220, Math.round(requestPayload.length / 7 + score / 2)));
  const fakeExfil = useMemo(() => {
    if (attackType === 'sql_injection') return 'Synthetic customer/account records (honeypot generated)';
    if (attackType === 'path_traversal') return 'Fake /etc/passwd entries and decoy system metadata';
    if (attackType === 'command_injection') return 'Simulated shell output and decoy process inventory';
    if (attackType === 'xss') return 'Mock session tokens and fabricated browser storage artifacts';
    return 'Deceptive artifacts only (no production data exposed)';
  }, [attackType]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen) return;
    setCurrentStage(0);
    setAutoplay(true);
    setSplitView(false);
    setPipelinePhase(0);
  }, [isOpen, session?.session_id]);

  useEffect(() => {
    if (!isOpen || !autoplay) return undefined;
    const timer = setInterval(() => {
      setCurrentStage((value) => (value >= STAGES.length - 1 ? 0 : value + 1));
    }, 2500);
    return () => clearInterval(timer);
  }, [autoplay, isOpen]);

  useEffect(() => {
    if (!isOpen || currentStage !== 1) return;
    setPipelinePhase(0);
    const timer = setInterval(() => {
      setPipelinePhase((value) => {
        if (value >= 4) {
          clearInterval(timer);
          return 4;
        }
        return value + 1;
      });
    }, 600);

    return () => clearInterval(timer);
  }, [currentStage, isOpen]);

  if (!isOpen || !session) return null;

  const progress = ((currentStage + 1) / STAGES.length) * 100;
  const parsedJson = isJSON(responseSnippet) ? JSON.parse(responseSnippet) : null;

  const intelligenceCards = [
    {
      label: 'Session Duration',
      value: `~${estimatedDuration}s`
    },
    {
      label: 'Attack Type',
      value: attackType.replace(/_/g, ' ')
    },
    {
      label: 'Severity',
      value: severity
    },
    {
      label: 'MITRE ATT&CK',
      value: `${mitre.id} · ${mitre.name}`
    },
    {
      label: 'Exfiltrated (Decoy)',
      value: fakeExfil
    }
  ];

  return (
    <div className="drm-overlay" onClick={onClose}>
      <div className="drm-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <header className="drm-header">
          <div>
            <h3>Deception Replay Simulator</h3>
            <p>{STAGES[currentStage].title} — {STAGES[currentStage].subtitle}</p>
          </div>
          <div className="drm-header-actions">
            <button
              type="button"
              className={`drm-icon-btn ${splitView ? 'active' : ''}`}
              onClick={() => setSplitView((value) => !value)}
              title="Split View"
            >
              <span>Split View</span>
            </button>
            <button type="button" className="drm-icon-btn" onClick={onClose} title="Close replay">
              <X size={15} />
            </button>
          </div>
        </header>

        <div className="drm-step-label">Step {currentStage + 1} of {STAGES.length}</div>

        <div className="drm-progress-wrap">
          <div className="drm-progress-bar" style={{ width: `${progress}%` }} />
        </div>

        <div className="drm-stage-rail">
          {STAGES.map((stage, idx) => (
            <button
              key={stage.title}
              className={`drm-stage-node ${idx === currentStage ? 'active' : ''} ${idx < currentStage ? 'complete' : ''}`}
              onClick={() => setCurrentStage(idx)}
            >
              <span>{idx + 1}</span>
              {stage.title}
            </button>
          ))}
        </div>

        {splitView ? (
          <div className="drm-split-layout">
            <section className="drm-panel">
              <h4>INCOMING ATTACK</h4>
              <div className="drm-meta-grid">
                <div><strong>Source:</strong> {session.source_ip || 'n/a'}</div>
                <div><strong>Method:</strong> {requestMeta.method}</div>
                <div><strong>URI:</strong> {requestMeta.uri}</div>
                <div><strong>Attack:</strong> {attackType}</div>
                <div><strong>Timestamp:</strong> {session.timestamp || 'n/a'}</div>
                <div><strong>WAF Score:</strong> <span className={`drm-waf-badge ${blocked ? 'danger' : 'safe'}`}>{score}/100</span></div>
              </div>
              <pre className="drm-terminal"><code dangerouslySetInnerHTML={{ __html: payloadToHtml(requestPayload || 'No payload captured') }} /></pre>
            </section>

            <section className="drm-panel drm-environment-panel">
              <h4>FAKE ENVIRONMENT — This is what the attacker sees</h4>
              <div className="drm-browser-frame">
                <div className="drm-browser-bar">
                  <span className="dot" />
                  <span className="dot" />
                  <span className="dot" />
                  <span className="url">https://portal-secure.example{requestMeta.uri || '/'}</span>
                </div>
                <div className="drm-browser-canvas">
                  {parsedJson ? (
                    <div className="drm-json-tree"><JsonTreeNode value={parsedJson} depth={0} /></div>
                  ) : (
                    <iframe
                      title="Deception environment preview"
                      className="drm-sandbox"
                      sandbox="allow-same-origin"
                      srcDoc={responseSnippet || '<html><body><p>Empty environment response.</p></body></html>'}
                    />
                  )}
                  <div className="drm-scanline" />
                </div>
              </div>
            </section>
          </div>
        ) : (
          <div className="drm-stage-body" key={`stage-${currentStage}`}>
            {currentStage === 0 && (
              <section className="drm-panel">
                <h4><span className="drm-incoming-label">INCOMING ATTACK</span> Attacker Payload Received</h4>
                <div className="drm-meta-grid">
                  <div><strong>Source:</strong> {session.source_ip || 'n/a'}</div>
                  <div><strong>Method:</strong> {requestMeta.method}</div>
                  <div><strong>URI:</strong> {requestMeta.uri}</div>
                  <div><strong>Timestamp:</strong> {session.timestamp || 'n/a'}</div>
                  <div><strong>WAF Score:</strong> <span className={`drm-waf-badge ${blocked ? 'danger' : 'safe'}`}>{score}/100</span></div>
                </div>
                <pre className="drm-terminal"><code dangerouslySetInnerHTML={{ __html: payloadToHtml(requestPayload || 'No payload captured') }} /></pre>
              </section>
            )}

            {currentStage === 1 && (
              <section className="drm-panel">
                <h4>Live Attack Flow — ML Analysis and Routing Decision</h4>
                <div className="drm-vertical-pipeline">
                  <div className={`drm-v-node ${pipelinePhase >= 0 ? 'active' : ''}`}>
                    <div className="drm-v-node-title">[NET] ATTACKER IP</div>
                    <div className="drm-v-node-sub">{session.source_ip || 'n/a'}</div>
                  </div>
                  <div className="drm-v-line" />

                  <div className={`drm-v-node ${pipelinePhase >= 1 ? 'active' : ''}`}>
                    <div className="drm-v-node-title">[SHIELD] INGRESS PROXY</div>
                    <div className="drm-v-node-sub">Request intercepted · Port 80</div>
                  </div>
                  <div className="drm-v-line" />

                  <div className={`drm-v-node ${pipelinePhase >= 2 ? 'active' : ''}`}>
                    <div className="drm-v-node-title">[BRAIN] ML SCORING</div>
                    <div className="drm-v-node-sub">Score: {score}/100</div>
                    <div className="drm-gauge-track">
                      <div className="drm-gauge-fill" style={{ width: pipelinePhase >= 2 ? `${score}%` : '0%' }} />
                    </div>
                    <div className="drm-v-node-sub">============ {pipelinePhase >= 2 ? `${score}%` : '0%'}</div>
                  </div>
                  <div className="drm-v-line" />

                  <div className={`drm-v-node verdict ${blocked ? 'blocked' : 'safe'} ${pipelinePhase >= 3 ? 'active flash' : ''}`}>
                    <div className="drm-v-node-title">[WARN] VERDICT</div>
                    <div className="drm-v-node-sub">
                      {pipelinePhase < 3 ? 'Analyzing...' : blocked ? 'REDIRECT -> HONEYPOT' : 'PASSED -> Production'}
                    </div>
                    <div className="drm-v-node-sub">Score {blocked ? '>=' : '<'} 80 threshold</div>
                  </div>
                  <div className="drm-v-line" />

                  <div className={`drm-v-node ${pipelinePhase >= 4 ? 'active success' : ''}`}>
                    <div className="drm-v-node-title">[MASK] DECEPTION ENV</div>
                    <div className="drm-v-node-sub">LLM Honeypot · Attacker now inside fake environment</div>
                  </div>

                  <div className={`drm-v-packet phase-${pipelinePhase}`} />
                </div>
              </section>
            )}

            {currentStage === 2 && (
              <section className="drm-panel drm-environment-panel">
                <h4>FAKE ENVIRONMENT — This is what the attacker sees</h4>
                <div className="drm-browser-frame">
                  <div className="drm-browser-bar">
                    <span className="dot" />
                    <span className="dot" />
                    <span className="dot" />
                    <span className="url">https://portal-secure.example{requestMeta.uri || '/'}</span>
                  </div>
                  <div className="drm-browser-canvas">
                    {parsedJson ? (
                      <div className="drm-json-tree"><JsonTreeNode value={parsedJson} depth={0} /></div>
                    ) : (
                      <iframe
                        title="Deception environment preview"
                        className="drm-sandbox"
                        sandbox="allow-same-origin"
                        srcDoc={responseSnippet || '<html><body><p>Empty environment response.</p></body></html>'}
                      />
                    )}
                    <div className="drm-scanline" />
                  </div>
                </div>
              </section>
            )}

            {currentStage === 3 && (
              <section className="drm-panel">
                <h4>Threat Intelligence Summary</h4>
                <div className="drm-intel-grid triple">
                  {intelligenceCards.map((card) => (
                    <article key={card.label} className="drm-intel-card">
                      <span>{card.label}</span>
                      <strong>{card.value}</strong>
                    </article>
                  ))}
                </div>

                <div className="drm-ioc-wrap">
                  <div>
                    <h5>IOCs</h5>
                    {indicators.iocs.length ? (
                      <ul>
                        {indicators.iocs.map((ioc) => <li key={ioc}>{ioc}</li>)}
                      </ul>
                    ) : (
                      <p>No IOC extracted.</p>
                    )}
                  </div>

                  <div>
                    <h5>Suspicious Commands</h5>
                    {indicators.commands.length ? (
                      <ul>
                        {indicators.commands.map((cmd) => <li key={cmd}>{cmd}</li>)}
                      </ul>
                    ) : (
                      <p>No shell command patterns found.</p>
                    )}
                  </div>
                </div>
              </section>
            )}
          </div>
        )}

        <footer className="drm-footer">
          <button
            type="button"
            className="drm-ctrl-btn"
            onClick={() => setCurrentStage((value) => (value === 0 ? STAGES.length - 1 : value - 1))}
          >
            <SkipBack size={14} />
            Previous Step
          </button>

          <button type="button" className="drm-ctrl-btn" onClick={() => setAutoplay((value) => !value)}>
            {autoplay ? <Pause size={14} /> : <Play size={14} />}
            {autoplay ? 'Pause Auto-Play' : 'Auto-Play'}
          </button>

          <button
            type="button"
            className="drm-ctrl-btn"
            onClick={() => setCurrentStage((value) => (value >= STAGES.length - 1 ? 0 : value + 1))}
          >
            Next Step
            <SkipForward size={14} />
          </button>
        </footer>
      </div>
    </div>
  );
}

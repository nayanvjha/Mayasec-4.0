const techniqueByEvent = {
  scan_start: 'T1046',
  credential_attack: 'T1110',
  sqli_attack: 'T1190',
  ml_detection: 'T1190',
  honeypot_redirect: 'T1565',
  honeypot_interaction: 'T1071',
};

const defaultsByEvent = {
  scan_start: {
    attack_type: 'Port Scan',
    severity_level: 'low',
    threat_score: 28,
  },
  credential_attack: {
    attack_type: 'Credential Attack',
    severity_level: 'medium',
    threat_score: 64,
  },
  sqli_attack: {
    attack_type: 'SQLi',
    severity_level: 'high',
    threat_score: 88,
  },
  ml_detection: {
    attack_type: 'ML Detection',
    severity_level: 'high',
    threat_score: 92,
  },
  honeypot_redirect: {
    attack_type: 'Honeypot Redirect',
    severity_level: 'medium',
    threat_score: 74,
    destination: 'honeypot',
  },
  honeypot_interaction: {
    attack_type: 'Honeypot Interaction',
    severity_level: 'high',
    threat_score: 83,
    destination: 'honeypot',
  },
};

export const demoSequence = [
  {
    delay: 0,
    event: 'scan_start',
    data: {
      source_ip: '203.0.113.42',
      destination_ip: '10.10.0.10',
      destination_port: 443,
    },
  },
  {
    delay: 3000,
    event: 'credential_attack',
    data: {
      source_ip: '203.0.113.42',
      username: 'admin',
      attempts: 17,
    },
  },
  {
    delay: 7000,
    event: 'sqli_attack',
    data: {
      source_ip: '203.0.113.42',
      payload: "' OR 1=1 --",
      uri: '/login',
    },
  },
  {
    delay: 12000,
    event: 'ml_detection',
    data: {
      source_ip: '203.0.113.42',
      score: 92,
      model: 'xgboost-v4',
    },
  },
  {
    delay: 15000,
    event: 'honeypot_redirect',
    data: {
      source_ip: '203.0.113.42',
      destination: 'honeypot',
      session_id: 'demo-session-001',
    },
  },
  {
    delay: 20000,
    event: 'honeypot_interaction',
    data: {
      source_ip: '203.0.113.42',
      destination: 'honeypot',
      session_id: 'demo-session-001',
      request_payload: 'GET /admin/export?format=json HTTP/1.1',
      llm_response: '{"message":"Simulated honeypot response"}',
    },
  },
];

function toNormalizedEvent(step, index) {
  const d = step?.data || {};
  const defaults = defaultsByEvent[step.event] || {};
  const score = Number(d.score ?? defaults.threat_score ?? 0);

  return {
    event_id: `demo-${Date.now()}-${index}`,
    timestamp: new Date().toISOString(),
    event_type: step.event,
    attack_type: d.attack_type || defaults.attack_type || step.event,
    source_ip: d.source_ip || '203.0.113.42',
    destination: d.destination || defaults.destination,
    threat_score: Number.isFinite(score) ? score : 0,
    severity_level: d.severity_level || defaults.severity_level || 'low',
    technique_id: d.technique_id || techniqueByEvent[step.event] || 'T1046',
    mitre_technique_id: d.mitre_technique_id || techniqueByEvent[step.event] || 'T1046',
    data: {
      ...d,
      event_type: step.event,
      destination: d.destination || defaults.destination,
      score,
    },
  };
}

export function runDemoSequence(onEvent) {
  const timers = [];
  let cancelled = false;
  const maxDelay = Math.max(...demoSequence.map((s) => Number(s.delay) || 0), 0);

  const done = new Promise((resolve) => {
    demoSequence.forEach((step, index) => {
      const t = setTimeout(() => {
        if (cancelled || typeof onEvent !== 'function') return;
        onEvent(toNormalizedEvent(step, index));
      }, Number(step.delay) || 0);
      timers.push(t);
    });

    const completeTimer = setTimeout(() => {
      resolve();
    }, maxDelay + 1200);
    timers.push(completeTimer);
  });

  return {
    totalDurationMs: maxDelay,
    done,
    cancel: () => {
      cancelled = true;
      timers.forEach((t) => clearTimeout(t));
    },
  };
}

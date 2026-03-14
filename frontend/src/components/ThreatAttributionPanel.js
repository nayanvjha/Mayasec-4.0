import { useEffect, useState } from 'react';
import './ThreatAttributionPanel.css';

const APT_SIGNATURES = {
  'APT28 (Fancy Bear)': {
    ttps: ['T1566', 'T1078', 'T1059.001', 'T1071', 'T1027'],
    origin: 'Russia',
    description: 'Russian GRU threat actor known for spearphishing and credential theft',
    mitre_url: 'https://attack.mitre.org/groups/G0007/',
  },
  'APT29 (Cozy Bear)': {
    ttps: ['T1021.001', 'T1078', 'T1110', 'T1550', 'T1098'],
    origin: 'Russia',
    description: 'Russian SVR actor targeting government and critical infrastructure',
    mitre_url: 'https://attack.mitre.org/groups/G0016/',
  },
  'Lazarus Group': {
    ttps: ['T1190', 'T1059', 'T1486', 'T1041', 'T1083'],
    origin: 'North Korea',
    description: 'North Korean state actor known for destructive malware and financial crime',
    mitre_url: 'https://attack.mitre.org/groups/G0032/',
  },
  'LockBit Ransomware': {
    ttps: ['T1486', 'T1078', 'T1562', 'T1490', 'T1489'],
    origin: 'Unknown',
    description: 'Prolific ransomware group using double extortion tactics',
    mitre_url: 'https://attack.mitre.org/software/S0685/',
  },
  Sandworm: {
    ttps: ['T1190', 'T1059.003', 'T1485', 'T1529', 'T1078'],
    origin: 'Russia',
    description: 'Russian GRU unit responsible for destructive attacks on infrastructure',
    mitre_url: 'https://attack.mitre.org/groups/G0034/',
  },
  'Cobalt Group': {
    ttps: ['T1566', 'T1055', 'T1059.001', 'T1021.002', 'T1083'],
    origin: 'Unknown',
    description: 'Financially motivated group targeting financial institutions',
    mitre_url: 'https://attack.mitre.org/groups/G0080/',
  },
};

function calculateAttribution(detectedTtps) {
  if (!detectedTtps || detectedTtps.length === 0) return [];

  return Object.entries(APT_SIGNATURES)
    .map(([groupName, data]) => {
      const matches = data.ttps.filter((ttp) =>
        detectedTtps.some((detected) => detected.startsWith(ttp) || ttp.startsWith(detected))
      );
      const confidence = Math.round((matches.length / data.ttps.length) * 100);
      return {
        groupName,
        confidence,
        matches,
        origin: data.origin,
        description: data.description,
        mitre_url: data.mitre_url,
      };
    })
    .filter((r) => r.confidence > 0)
    .sort((a, b) => b.confidence - a.confidence);
}

function getConfidenceClass(confidence) {
  if (confidence > 60) return 'high';
  if (confidence >= 30) return 'medium';
  return 'low';
}

function ThreatAttributionPanel({ apiUrl }) {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detectedCount, setDetectedCount] = useState(0);

  const baseUrl = apiUrl
    ? apiUrl.replace(/\/$/, '')
    : (typeof window !== 'undefined' ? `http://${window.location.hostname}:5000` : 'http://localhost:5000');

  useEffect(() => {
    let mounted = true;

    const fetchAttribution = async () => {
      try {
        const response = await fetch(`${baseUrl}/api/v1/mitre/summary`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer mayasec_internal_token',
          },
        });

        if (!response.ok) {
          throw new Error(`API Error: ${response.status}`);
        }

        const payload = await response.json();
        const data = Array.isArray(payload)
          ? payload
          : Array.isArray(payload?.data)
            ? payload.data
            : Array.isArray(payload?.ttps)
              ? payload.ttps
              : [];

        const techniqueIds = data
          .map((item) => item.technique_id)
          .filter(Boolean)
          .map((id) => String(id).toUpperCase());

        const attributionResults = calculateAttribution(techniqueIds);

        if (mounted) {
          setDetectedCount(techniqueIds.length);
          setResults(attributionResults);
          setLoading(false);
        }
      } catch {
        if (mounted) {
          setDetectedCount(0);
          setResults([]);
          setLoading(false);
        }
      }
    };

    fetchAttribution();
    const intervalId = setInterval(fetchAttribution, 60000);

    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, []);

  const top = results[0];
  const secondary = results.slice(1, 3);

  return (
    <div className="threat-attribution-panel">
      <div className="attribution-header">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#00ff9f" strokeWidth="1.8">
          <circle cx="12" cy="12" r="9" />
          <circle cx="12" cy="12" r="4" />
          <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
        </svg>
        <span>Threat Attribution</span>
      </div>

      {loading && <div className="attribution-empty">Analysing TTP patterns...</div>}

      {!loading && results.length === 0 && detectedCount > 0 && (
        <div className="unknown-actor-card">
          <div className="unknown-title">Unknown actor pattern</div>
          <div className="unknown-desc">Observed TTP combination does not match known threat groups</div>
        </div>
      )}

      {!loading && results.length === 0 && detectedCount === 0 && (
        <div className="unknown-actor-card">
          <div className="unknown-title">No TTPs detected</div>
          <div className="unknown-desc">Run an attack simulation to populate attribution signals</div>
        </div>
      )}

      {!loading && top && (
        <>
          <div className="top-match-card">
            <div className="top-row">
              <div className={`group-name ${getConfidenceClass(top.confidence)}`}>{top.groupName}</div>
              <div className="origin-badge">{top.origin}</div>
            </div>

            <div className="confidence-wrap">
              <div className="confidence-bar">
                <div
                  className={`confidence-fill ${getConfidenceClass(top.confidence)}`}
                  style={{ width: `${top.confidence}%` }}
                />
              </div>
              <div className="confidence-label">Confidence: {top.confidence}%</div>
            </div>

            <div className="group-description">{top.description}</div>

            <a
              className="mitre-link"
              href={top.mitre_url}
              target="_blank"
              rel="noreferrer"
            >
              View on MITRE ATT&amp;CK →
            </a>

            <div className="ttp-pills">
              {top.matches.map((ttp) => (
                <span key={ttp} className="ttp-pill">{ttp}</span>
              ))}
            </div>
          </div>

          {secondary.length > 0 && (
            <div className="secondary-list">
              {secondary.map((item) => (
                <div key={item.groupName} className="secondary-card">
                  <div className="secondary-top">
                    <div className="secondary-name">{item.groupName}</div>
                    <div className="origin-badge">{item.origin}</div>
                  </div>
                  <div className="confidence-bar">
                    <div
                      className={`confidence-fill ${getConfidenceClass(item.confidence)}`}
                      style={{ width: `${item.confidence}%` }}
                    />
                  </div>
                  <div className="confidence-label">Confidence: {item.confidence}%</div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default ThreatAttributionPanel;

# Real-Time Event Streaming - Quick Reference

## 🚀 Quick Start

### Access the Dashboard
```
http://localhost:3000
```

### Connect to Raw WebSocket (Read-Only)
Use any RFC 6455 client (e.g., wscat):

ws://localhost:5000/ws/events

### Send a Test Event
```bash
curl -X POST http://localhost:5000/api/v1/emit-event \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "my-event-001",
    "event_type": "THREAT_DETECTED",
    "source_ip": "192.168.1.1",
    "destination_ip": "10.0.0.1",
    "action": "BLOCKED",
    "threat_level": "high",
    "threat_score": 85,
    "threat_description": "Example threat"
  }'
```

---

## 🏗️ Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│                    MAYASEC REAL-TIME PIPELINE               │
└─────────────────────────────────────────────────────────────┘

Event Source (Logs, Sensors)
           ↓
┌──────────────────────────┐
│  Core Service            │  (Port 5001)
│  - Threat Analysis       │
│  - Event Enrichment      │
│  - Database Storage      │
└──────┬───────────────────┘
       │ (HTTP POST)
       ↓
┌──────────────────────────┐
│  API Service             │  (Port 5000)
│  - Raw WebSocket         │  /ws/events
│  - Event Broadcasting    │  (server → client only)
└──────┬───────────────────┘
       │ (WebSocket)
       ↓
┌──────────────────────────┐
│  Frontend (React)        │  (Port 3000)
│  - useWebSocket Hook     │
│  - LiveEventFeed         │
│  - Real-Time Display     │
└──────────────────────────┘
```

---

## 📱 React Component API

### Using WebSocket in Any Component

```javascript
import { useWebSocket } from './hooks/useWebSocket';

function MyComponent() {
  const { 
    connected,      // boolean - WebSocket connected
    events,         // array - Real-time events
    alerts,         // array - Real-time alerts
    error,          // string - Error message if any
    setEvents       // function - Update events state
  } = useWebSocket('http://localhost:5000');

  return (
    <div>
      <p>{connected ? '🟢 Live' : '🔴 Offline'}</p>
      {events.map(e => <EventItem key={e.event_id} event={e} />)}
    </div>
  );
}

export default MyComponent;
```

### Event Object Structure

```javascript
{
  event_id: "test-001",
  event_type: "MALWARE_DETECTED",
  source_ip: "192.168.1.100",
  destination_ip: "10.0.0.1",
  action: "BLOCKED",
  threat_level: "critical",  // critical | high | medium | low
  threat_score: 95,          // 0-100
  threat_description: "Known malware signature detected",
  timestamp: "2026-01-15T08:26:18.289173"
}
```

---

## 🔌 Raw WebSocket Stream (Public, Read-Only)

Endpoint:
ws://localhost:5000/ws/events

Cloudflare Pages / HTTPS:
- Use wss://<api-host>/ws/events when the UI is served over HTTPS.
- Keep the API host explicit (no Socket.IO path).

Behavior:
- One-way only (server → client)
- Clients cannot send messages
- Firehose stream (no subscriptions)

Payload format (one JSON event per frame):
```
{
  "type": "event_ingested",
  "timestamp": "2026-01-18T10:22:31Z",
  "data": {
    "source_ip": "10.0.1.23",
    "event_type": "auth_failure",
    "severity": "medium",
    "correlation_id": "uuid"
  }
}
```

Supported event types only:
- event_ingested
- phase_escalated
- alert_created
- ip_blocked
- ip_unblocked
- response_mode
- response_decision

Legacy Socket.IO:
- Socket.IO is retained for backward compatibility during migration.
- SOC UI should use the raw WebSocket endpoint for stability and compatibility.

---

## 🛡️ Response Mode (Backend Authoritative)

Response mode is decided by backend configuration only and is read-only to the UI.

Configuration (backend only):
- Environment: MAYASEC_RESPONSE_MODE=monitor|guarded|active
- Or file: response.mode (single word: monitor | guarded | active)

Mode event (emitted on startup and on connect):
```
{
  "type": "response_mode",
  "mode": "guarded",
  "timestamp": "2026-01-18T10:22:31Z"
}
```

Response decision event (emitted for every enforcement decision):
```
{
  "type": "response_decision",
  "timestamp": "2026-01-18T10:22:31Z",
  "data": {
    "mode": "guarded",
    "decision": "enforced",
    "action": "block_ip",
    "reason": "guarded:threshold_met",
    "ip_address": "10.0.1.23"
  }
}
```

---

## 🔌 API Endpoints

### Emit Event (Called by Core)
```
POST /api/v1/emit-event
Content-Type: application/json

{
  "event_id": "string (required)",
  "event_type": "string",
  "source_ip": "string",
  "destination_ip": "string", 
  "action": "BLOCKED|LOGGED|FLAGGED",
  "threat_level": "critical|high|medium|low",
  "threat_score": number (0-100),
  "threat_description": "string"
}

Response: {"status": "emitted", "event_id": "...", "timestamp": "..."}
```

### Emit Alert (Called by Core)
```
POST /api/v1/emit-alert
Content-Type: application/json

{
  "alert_id": "string",
  "alert_type": "string",
  "severity": "critical|high|medium|low",
  "message": "string",
  "timestamp": "timestamp"
}

Response: {"status": "emitted", "alert_id": "...", "timestamp": "..."}
```

### Health Check
```
GET /health
Response: {"status": "ok"}
```

---

## 🔧 Configuration

### Environment Variables

**Frontend** (`frontend/src/App.js`)
```javascript
const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:5000';
```

**Core Service** (`core/__init__.py`)
```python
API_URL = os.getenv('API_URL', 'http://api:5000')  # For Docker
```

**docker-compose.yml**
```yaml
services:
  mayasec-ui:
    environment:
      REACT_APP_API_URL: http://localhost:5000
  
  core:
    environment:
      API_URL: http://api:5000
```

---

## 🔍 Debugging

### Check if WebSocket is Connected

**Browser DevTools → Network → WS**
```
socket.io/?EIO=4&transport=websocket  ✓ Connected
```

### Monitor API Event Emissions
```bash
docker-compose logs api | grep "Emitting event"
```

### Check Frontend Connection Logs
```bash
# Browser console should show:
# "Connected to WebSocket server"
```

### Test Event Emission
```bash
curl -X POST http://localhost:5000/api/v1/emit-event \
  -H "Content-Type: application/json" \
  -d '{"event_id":"test","event_type":"TEST","source_ip":"1.1.1.1","destination_ip":"2.2.2.2","action":"LOGGED","threat_level":"low","threat_score":10,"threat_description":"Test"}'
```

### View Full API Logs
```bash
docker-compose logs api -f
```

### View Frontend Build Status
```bash
docker-compose logs mayasec-ui -f
```

---

## 🚀 Deployment Checklist

- [ ] All containers running: `docker-compose ps`
- [ ] API health: `curl http://localhost:5000/health`
- [ ] Frontend loads: `curl http://localhost:3000`
- [ ] socket.io-client in frontend package.json
- [ ] WebSocket server enabled in API logs
- [ ] Test event can be sent and received
- [ ] LiveEventFeed component visible in dashboard
- [ ] Connection indicator shows "Connected"

---

## 📊 Performance Tips

1. **Limit Events in Memory**: LiveEventFeed only keeps recent N events
2. **Use Connection Indicator**: Let users know when WebSocket is offline
3. **Batch Events**: Group multiple events before UI update
4. **Throttle Updates**: Don't update every single incoming event (optional)
5. **Pagination**: Consider paginating event feed for 1000+ events

---

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| WebSocket won't connect | Check firewall, verify port 5000 is open |
| Events not appearing | Check `REACT_APP_API_URL` in docker-compose |
| High latency | Switch to WebSocket transport (check DevTools) |
| Component crashes | Add error boundary around `useWebSocket` hook |
| No socket.io-client error | Run `npm install socket.io-client` in frontend |

---

## 📚 Files to Know

| File | What It Does |
|------|-------------|
| `mayasec_api.py` | WebSocket server, event broadcasting |
| `core/__init__.py` | Event processing, WebSocket emission calls |
| `frontend/src/hooks/useWebSocket.js` | React hook for Socket.IO connections |
| `frontend/src/components/LiveEventFeed.js` | Real-time event display component |
| `frontend/src/App.js` | Dashboard integration point |
| `docker-compose.yml` | Service orchestration |

---

## 💡 Tips & Tricks

### Manually Test Socket.IO Connection
```bash
# Install socket.io-client globally
npm install -g socket.io-client

# Create test script and run
node test-socket.js
```

### Clear Event Feed Programmatically
```javascript
const { setEvents } = useWebSocket('http://localhost:5000');
setEvents([]);  // Clears all events
```

### Filter Events by Threat Level
```javascript
const { events } = useWebSocket('http://localhost:5000');
const criticalEvents = events.filter(e => e.threat_level === 'critical');
```

### Access Socket Directly (Advanced)
```javascript
// In useWebSocket hook, socketRef.current gives you the Socket.IO instance
// Allows sending custom messages: socket.emit('custom_event', data)
```

---

## 🎯 Common Use Cases

### Use Case 1: Display Critical Threats Only
```javascript
const { events, connected } = useWebSocket(apiUrl);
const critical = events.filter(e => e.threat_level === 'critical');

return (
  <div>
    {critical.length > 0 && (
      <AlertBanner>🚨 {critical.length} Critical Threats!</AlertBanner>
    )}
  </div>
);
```

### Use Case 2: Play Sound on Critical Event
```javascript
const { events } = useWebSocket(apiUrl);

useEffect(() => {
  events.forEach(event => {
    if (event.threat_level === 'critical') {
      new Audio('/alert-sound.mp3').play();
    }
  });
}, [events]);
```

### Use Case 3: Export Events to CSV
```javascript
const { events } = useWebSocket(apiUrl);

const exportCSV = () => {
  const csv = events.map(e => 
    `${e.event_id},${e.threat_level},${e.threat_score}`
  ).join('\n');
  
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'events.csv';
  a.click();
};
```

---

## 📞 Support

For issues, check:
1. Docker logs: `docker-compose logs [service]`
2. Browser console: DevTools → Console
3. Network tab: DevTools → Network → WS
4. This guide's Troubleshooting section

---

**Last Updated**: January 15, 2026  
**Status**: ✅ Production Ready

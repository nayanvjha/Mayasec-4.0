# SOC Console Data Flow & Architecture

## End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         BACKEND LAYER                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Network Event (from IDS/Firewall)                             │
│         ↓                                                        │
│  MAYASEC API: /ingest                                           │
│  ├─ Normalize & validate                                        │
│  ├─ Calculate threat_score (0-100)                             │
│  ├─ Assign severity_level                                       │
│  ├─ Check threat intelligence                                   │
│  └─ Store in PostgreSQL                                         │
│         ↓                                                        │
│  Alert Rule Engine                                              │
│  ├─ Single high-severity event? → ALERT                        │
│  ├─ Pattern detected? → ALERT                                  │
│  ├─ Threat intel match? → ALERT                               │
│  └─ Store alert_id with event                                 │
│         ↓                                                        │
│  Core Service (Event Processing)                                │
│  └─ Enrich event data, final calculations                      │
│         ↓                                                        │
│  WebSocket Broadcast (Socket.IO emit)                          │
│  └─ Send complete event object to all connected clients        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND LAYER                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Socket.IO Client (WebSocket Connection)                        │
│  └─ Listen for 'event:new' messages                            │
│         ↓                                                        │
│  SOCEventConsole Component                                      │
│  ├─ Receive event object                                        │
│  ├─ Add to live stream (top of list)                           │
│  ├─ Sort by timestamp descending (newest first)                │
│  └─ Update display in real-time (no polling)                   │
│         ↓                                                        │
│  Analyst Interaction                                            │
│  ├─ Scans live stream for anomalies                            │
│  ├─ Selects event of interest                                  │
│  └─ Drills down to details/timeline/context                   │
│         ↓                                                        │
│  Detail Panel (On-Demand Load)                                  │
│  ├─ Display full event object (from WebSocket)                │
│  ├─ Show raw_data field (unmodified backend data)             │
│  ├─ Display threat intel matches                              │
│  ├─ Options: [Show Timeline] [Show History] [Take Action]    │
│         ↓                                                        │
│  Timeline View (REST Load)                                      │
│  ├─ Query backend: GET /api/events?source_ip=X&timeframe=5m  │
│  ├─ Display related events (same source IP)                   │
│  ├─ Order by timestamp (oldest → newest)                      │
│  └─ Show pattern evolution                                     │
│         ↓                                                        │
│  Historical Context (REST Load)                                 │
│  ├─ Query backend: GET /alerts?source_ip=X&days=30           │
│  ├─ Query threat intel: GET /threat-intel?ip=X               │
│  ├─ Display previous incidents, reputation                    │
│         ↓                                                        │
│  Analyst Decision & Action                                      │
│  ├─ Mark alert: TRUE_POSITIVE / FALSE_POSITIVE               │
│  ├─ Assign to response team                                    │
│  ├─ Block IP (if applicable)                                   │
│  ├─ Log findings                                               │
│         ↓                                                        │
│  Frontend sends update to backend                              │
│  └─ POST /api/alert/{id}/update {status: "RESOLVED", notes: ""}
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────┐
│                      BACKEND UPDATES STATE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Alert Status Update                                            │
│  ├─ Update alert.status in PostgreSQL                         │
│  ├─ Update alert.resolved_at timestamp                        │
│  ├─ Store analyst notes in audit log                          │
│  └─ Broadcast update via WebSocket (optional)                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Temporal Ordering Rules

### Display Order (Live Stream)

```
Events sorted by: timestamp DESC (descending, newest first)

Example:
14:05:00 - Event: Port scan attempt (severity: HIGH)
14:04:45 - Event: Port scan attempt (severity: HIGH)
14:04:30 - Event: Port scan attempt (severity: MEDIUM)
14:04:15 - Event: Failed login (severity: LOW)
↑ Most recent event (analyst sees first)
```

### Timeline Order (Related Events)

```
Events sorted by: timestamp ASC (ascending, oldest first)

Same source IP, last 24 hours:
14:00:00 - Event: Port scan attempt (severity: MEDIUM)
14:00:15 - Event: Port scan attempt (severity: MEDIUM)
14:00:30 - Event: Port scan attempt (severity: HIGH)
14:00:45 - Event: Failed login (severity: CRITICAL)
↑ Attack evolution visible (analyst sees pattern)
```

---

## Event State Lifecycle

```
┌──────────────┐
│ Created      │
│ (timestamp)  │
└──────┬───────┘
       │
       ↓
┌──────────────────┐
│ Enriched         │
│ (threat scoring) │
└──────┬───────────┘
       │
       ↓
┌──────────────────────┐
│ Alert Generated?     │
│ (rule check)         │
└──────┬───────────────┘
       │
       ├─→ YES ──→ Alert created (alert_id assigned)
       │
       └─→ NO ──→ Event stored, awaiting pattern match
                  (may trigger alert later if related events arrive)
       
       ↓
┌──────────────────┐
│ Broadcast        │
│ (WebSocket)      │
└──────┬───────────┘
       │
       ↓
┌──────────────────┐
│ Analyst Views    │
│ (console)        │
└──────┬───────────┘
       │
       ↓
┌──────────────────────┐
│ Alert Marked         │
│ (analyst decision)    │
└──────┬───────────────┘
       │
       ├─→ TRUE_POSITIVE ──→ Investigation / Escalation
       │
       ├─→ FALSE_POSITIVE ──→ Alert closed
       │
       └─→ INVESTIGATING ──→ In-progress, awaiting resolution
```

---

## Data Ownership & Authority

### Event Object

**Created By:** Backend (immutable)  
**Updated By:** Backend only (if threat score recalculated)  
**Displayed By:** Frontend (WebSocket)  
**Owns:** source_ip, destination_ip, timestamp, threat_score, raw_data  

**Frontend Assumption:** Event object is complete and accurate as received from WebSocket.

### Alert Object

**Created By:** Backend (rule engine)  
**Updated By:** Analyst (through frontend)  
**Displayed By:** Frontend  
**Owns:** status, assigned_to, resolved_at, notes  

**Frontend Responsibility:** 
- Display alert status
- Capture analyst notes
- Send updates to backend
- Maintain investigation audit trail

### Live Stream

**Owned By:** Frontend (local state)  
**Updated By:** WebSocket messages (append new events)  
**Authority:** Events are authoritative; stream is ordered copy  
**No Polling:** Stream is never re-fetched; only appended with WebSocket  

---

## WebSocket Message Contract

### Event Broadcast Message

```json
{
  "type": "event:new",
  "data": {
    "event_id": "uuid",
    "timestamp": "2026-01-15T14:32:00Z",
    "source_ip": "10.1.1.100",
    "destination_ip": "192.168.1.50",
    "source_port": null,
    "destination_port": 443,
    "protocol": "TCP",
    "event_type": "port_scan",
    "threat_score": 87,
    "severity_level": "HIGH",
    "raw_data": { /* original event object */ },
    "event_description": "Port scan detected",
    "detection_source": "IDS",
    "attack_category": "reconnaissance",
    "threat_intel_match": true,
    "alert_id": "alert-uuid-123"
  }
}
```

### Alert Update Message

```json
{
  "type": "alert:updated",
  "data": {
    "alert_id": "uuid",
    "status": "RESOLVED",
    "resolved_at": "2026-01-15T14:35:00Z",
    "assigned_to": "analyst@mayasec.com",
    "notes": "Confirmed brute force attack, IPs blocked"
  }
}
```

---

## REST Endpoints (On-Demand, Not Polling)

### For Detail Drill-Down

**Get related events (timeline):**
```
GET /api/v1/events?source_ip={ip}&timeframe=5m
Response: Array of events, ordered by timestamp ASC
```

**Get alert history:**
```
GET /api/v1/alerts?source_ip={ip}&days=30
Response: Array of historical alerts
```

**Get threat intelligence:**
```
GET /api/v1/threat-intel?ip={ip}
Response: Reputation, matches, country info
```

**Update alert status:**
```
POST /api/v1/alerts/{alert_id}/update
Body: { status: "RESOLVED", notes: "..." }
Response: Updated alert object
```

---

## Console State Machine

```
State: IDLE
└─ Analyst viewing live stream
   └─ New event arrives
      └─ Update display
         └─ Stay in IDLE

State: EVENT_SELECTED
└─ Analyst clicked event in stream
   └─ Load event details
      └─ Display detail panel
         └─ Options: [Timeline] [History] [Investigate]

State: TIMELINE_OPEN
└─ Analyst clicked "Show Timeline"
   └─ Load related events (REST)
      └─ Display events in chronological order
         └─ Analyst reviews pattern

State: CONTEXT_OPEN
└─ Analyst clicked "Show History"
   └─ Load historical data (REST)
      └─ Display previous alerts, threat intel
         └─ Analyst assesses familiarity

State: ACTION_TAKEN
└─ Analyst marked alert as resolved/investigated
   └─ Send update to backend
      └─ Backend confirms
         └─ Return to IDLE

State: ERROR
└─ WebSocket disconnected or API error
   └─ Display error message
      └─ Show retry option
         └─ Reconnect on retry
```

---

## Performance Considerations

**Live Stream (WebSocket):**
- ✓ Instant updates (< 100ms)
- ✓ No polling overhead
- ✓ Scales with event volume
- ✓ Single WebSocket connection for all events

**Detail Loads (REST):**
- ⏳ Loaded on demand (not preloaded)
- ⏳ Small queries (single event or related events)
- ⏳ Minimal network overhead
- ✓ Cached by browser (timeline often not re-fetched)

**No Aggregation:**
- ✓ No summary calculation overhead
- ✓ Raw events = minimal processing
- ✓ Frontend just displays, backend calculates

---

## Summary

1. **Backend** processes events once: normalize, score, enrich, alert
2. **WebSocket** broadcasts events to all analysts in real-time
3. **Frontend** receives events and displays them ordered by timestamp
4. **Analyst** interacts with stream: select, drill down, investigate
5. **REST** provides on-demand context (related events, history, threat intel)
6. **Decision** triggers backend update (alert status)
7. **Audit trail** maintained throughout

This is event-driven, not metric-driven. No polling. No aggregation. No dashboards. Just events and analyst actions.

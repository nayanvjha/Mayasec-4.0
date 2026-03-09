# MAYASEC SOC Event Console - Mental Model & Architecture

**Date:** January 15, 2026  
**Status:** Design & Requirements  
**Purpose:** Define the SOC-first event console architecture  

---

## I. Security Event Model

### Event Definition
A **Security Event** is an atomic observation from the network or system that requires analyst attention.

### Event Structure

```
Event {
  // Identification
  event_id: string (UUID)
  event_type: string (e.g., "port_scan", "brute_force", "exploit_attempt")
  
  // Temporal Context
  timestamp: ISO8601 (when the event occurred)
  first_seen: ISO8601 (when first detected by MAYASEC)
  last_seen: ISO8601 (when last seen, if repeating)
  
  // Network Context
  source_ip: string
  destination_ip: string
  source_port: integer (optional)
  destination_port: integer (optional)
  protocol: string (e.g., "TCP", "UDP")
  
  // Severity & Threat Assessment
  threat_score: integer (0-100, no aggregation, raw calculated value)
  severity_level: enum (CRITICAL, HIGH, MEDIUM, LOW)
  
  // Content & Details
  raw_data: object (original event from backend, unmodified)
  event_description: string (human-readable summary)
  detection_source: string (e.g., "IDS", "firewall", "honeypot")
  
  // Classification
  attack_category: string (e.g., "reconnaissance", "initial_access", "execution")
  threat_intel_match: boolean (true if matched against threat feed)
  
  // Relationships
  alert_id: string (optional, null if not yet escalated to alert)
  related_events: [event_id] (events from same source IP in same timeframe)
}
```

### Event Properties

**Immutable:**
- event_id
- timestamp (when the actual event occurred)
- first_seen
- source_ip
- destination_ip
- raw_data
- detection_source

**Mutable (by analyst or backend rules):**
- severity_level (analyst can adjust after investigation)
- threat_score (can be recalculated or adjusted)
- alert_id (assigned when escalated)

### Event Ordering

Events are ordered by **timestamp descending** (newest first) in the live stream.

**Display Order Rules:**
1. Primary sort: timestamp (newest first)
2. Grouping context: source IP (events from same source are contextually related)
3. Timeline view: timestamp ascending (oldest first, to see pattern evolution)

---

## II. Alert Lifecycle

### Alert Definition
An **Alert** is a grouped response to one or more related security events that requires immediate or follow-up investigation.

### Alert Creation Triggers

Alerts are created by **backend rules**, not the frontend. Frontend displays them.

**Triggers:**
1. Single high-severity event (threat_score > 80 → instant alert)
2. Multiple events from same source within time window (< 5 minutes)
3. Event pattern match (e.g., 5+ failed logins = brute force alert)
4. Threat intelligence match + action taken
5. Manual escalation by analyst

### Alert Structure

```
Alert {
  // Identification
  alert_id: string (UUID)
  alert_type: string (e.g., "suspected_brute_force", "port_scan_detected")
  
  // Temporal
  created_at: ISO8601 (when alert was generated)
  updated_at: ISO8601 (last time alert changed)
  resolved_at: ISO8601 (optional, when analyst resolved)
  
  // Composition
  event_ids: [string] (array of related event_ids)
  primary_event_id: string (the event that triggered the alert)
  
  // Status
  status: enum (OPEN, INVESTIGATING, RESOLVED, FALSE_POSITIVE)
  severity: enum (CRITICAL, HIGH, MEDIUM, LOW)
  confidence: integer (0-100, how confident is the alert valid)
  
  // Analyst Context
  assigned_to: string (optional, analyst name)
  notes: [{ timestamp, analyst, text }] (investigation log)
  
  // Action Taken
  action: string (optional, e.g., "blocked_ip", "elevated_investigation")
  recommendation: string (suggested next steps)
  
  // Linkage
  related_alerts: [alert_id] (other alerts from same source IP, timeframe)
}
```

### Event-to-Alert Relationship

**One-to-Many:** One alert can group multiple events.  
**Many-to-One:** Multiple events can belong to one alert.

**Relationship Logic:**
```
Events → Alert when:
- Same source IP
- Occurred within 5 minute window
- Part of recognizable pattern
- OR single high-severity event (immediate alert)

Alert → Events mapping:
- Alert.event_ids contains all related event IDs
- Alert.primary_event_id = the event that triggered escalation
- Alert.related_events in Event object points back to alert
```

**Example Timeline:**
```
14:00:00 - Event 1: Port scan from 10.1.1.100 → severity MEDIUM
14:00:15 - Event 2: Port scan from 10.1.1.100 → severity MEDIUM
14:00:30 - Event 3: Port scan from 10.1.1.100 → severity MEDIUM
14:00:45 - Event 4: Port scan from 10.1.1.100 → severity HIGH

14:00:45 → Alert created: "port_scan_detected"
├─ event_ids: [Event1, Event2, Event3, Event4]
├─ primary_event_id: Event4 (the high-severity trigger)
└─ alert_status: OPEN
```

---

## III. Operator (Analyst) Flow

### Interaction Paradigm

A SOC analyst interacts with MAYASEC through **progressive disclosure**: Start with high-level threat signal, drill down to granular detail.

### The Analyst's Mental Model

**Question 1: "What's happening right now?"**
→ Analyst looks at **Live Event Stream**
- See newest events first
- Scan for severity indicators (color, score)
- Identify anomalies in source IPs, targets, patterns

**Question 2: "Is this a real threat?"**
→ Analyst looks at **Event Details**
- Raw network data from the event
- Full packet capture (if available)
- Threat intelligence matches
- Detection confidence

**Question 3: "Is this part of a larger attack?"**
→ Analyst looks at **Timeline of Related Events**
- All events from the same source IP
- Events in the same 5-10 minute window
- Pattern recognition (escalation, distribution, etc.)

**Question 4: "What's the context?"**
→ Analyst looks at **Historical Context**
- Previous alerts from this source IP (days/weeks)
- Geographic information
- Organization knowledge (is this known good actor?)
- Asset information (what was the target?)

**Question 5: "What do I do?"**
→ Analyst takes **Action**
- Mark alert as false positive
- Assign to response team
- Block IP / revoke access
- Escalate to incident response

### Analyst Journey (Typical)

```
1. ALERT NOTIFICATION
   "Alert: Suspected brute force on server DB-01"
   ↓
2. IMPACT ASSESSMENT
   "How many failed logins? From where? What severity?"
   ↓
3. EVIDENCE REVIEW
   "Show me the events. What's the pattern?"
   ↓
4. CONTEXT CHECK
   "Have I seen this attacker before? Is this known?"
   ↓
5. DECISION
   "True positive or false alarm?"
   ↓
6. ACTION
   "Block, investigate, monitor, dismiss"
   ↓
7. DOCUMENTATION
   "Log findings and actions for next analyst"
```

---

## IV. Console Layout Logic

### Information Architecture (Not Visual Design)

The console presents information in **layers**, not all at once.

#### Layer 1: Live Stream (Primary View)
**Purpose:** Real-time threat awareness  
**Content:**
- Newest events first
- Each event shows: timestamp, source IP, target, event type, severity, threat score
- Limited details (text only, no charts)
- Live updating (WebSocket-driven)

**Analyst Action:** Scan for anomalies, identify interesting events

#### Layer 2: Event Details (Secondary View - On Demand)
**Purpose:** Understand a specific event  
**Content:**
- Full event data (all fields from Event model)
- Raw backend data (unmodified)
- Threat intelligence matches (if any)
- Detection source and method
- Timestamp and metadata

**Analyst Action:** Read raw data, check threat intel, assess severity

#### Layer 3: Related Events (Tertiary View - On Demand)
**Purpose:** See the attack pattern  
**Content:**
- All events from the same source IP (last 24 hours)
- Timeline ordering (oldest to newest)
- Highlight severity progression
- Show time gaps between events

**Analyst Action:** Identify pattern, assess escalation, understand intent

#### Layer 4: Alert Context (Quaternary View - On Demand)
**Purpose:** Historical perspective  
**Content:**
- Previous alerts from this source IP
- Associated incident records (if filed)
- Threat intelligence feeds (matches, country, reputation)
- Geographic information
- Asset information (what was attacked)

**Analyst Action:** Assess familiarity, apply organizational knowledge

### Console Layout Zones

```
┌─────────────────────────────────────────────────────────┐
│ HEADER: System status, time, connection indicator       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  LIVE STREAM ZONE                    DETAIL ZONE      │
│  ┌──────────────────┐               ┌──────────────┐  │
│  │ Event 1 (newest) │               │ Event details│  │
│  │ [tap to select]  │──────select──→│ (selected)   │  │
│  │                  │               │              │  │
│  │ Event 2          │               │ Raw data     │  │
│  │ Event 3          │               │ Threat intel │  │
│  │ Event 4          │               │ Metadata     │  │
│  │ ...              │               │              │  │
│  │ (scrollable)     │               │ [show timeline]
│  │                  │               │ [show context]
│  │ LIVE (updates)   │               │              │  │
│  └──────────────────┘               └──────────────┘  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ CONTEXT ZONE (optional, scrollable)                     │
│  ┌─────────────────────────────────────────────────┐  │
│  │ Timeline of related events from source IP       │  │
│  │ Historical alerts, threat intel, asset info     │  │
│  └─────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Data Flow in Console

```
Backend (WebSocket)
    ↓
    New Event arrives
    ↓
Live Stream Zone
(immediate display, chronological)
    ↓
Analyst [taps/selects event]
    ↓
Detail Zone
(displays event data, options to expand)
    ↓
Analyst [clicks "show timeline"]
    ↓
Context Zone
(loads related events, historical data)
    ↓
Analyst [marks as resolved/investigated]
    ↓
Backend (alert status update)
```

### What Updates Live vs Static

**LIVE (WebSocket-driven):**
- New events in stream (append to top)
- Severity/threat score of current events
- Connection status indicator
- Analyst presence (who's looking at what)

**STATIC (loaded on demand):**
- Event details (raw data doesn't change after event is stored)
- Historical timelines (past events)
- Threat intelligence (cached, updated periodically not per-event)
- Asset/context information (loaded when analyst requests)

**NOT LIVE (polling is wrong):**
- Event counts (calculate from stream)
- Statistics (calculate from event stream, not separate API)
- Summary aggregations (derive from raw events in console, not from summary endpoint)

---

## V. Event Processing Pipeline

### From Network to Console

```
1. NETWORK DETECTION
   Packet → IDS/Firewall detects suspicious behavior
   
2. BACKEND PROCESSING
   Raw alert → MAYASEC API (/ingest)
   ├─ Normalize event data
   ├─ Calculate threat score
   ├─ Classify severity
   ├─ Check threat intelligence
   └─ Determine if alert trigger

3. ALERT GENERATION (Backend)
   Event → Ruleset check
   ├─ High severity? → Immediate alert
   ├─ Pattern match? → Grouped alert
   └─ Threat intel? → Alert if action taken

4. WEBSOCKET BROADCAST
   Event → Socket.IO emit to all connected analysts
   └─ "event:new" with full event object

5. CONSOLE RECEPTION
   Frontend receives WebSocket message
   ├─ Add to live stream (top of list)
   ├─ Sort by timestamp descending
   └─ Display to analyst

6. ANALYST INVESTIGATION
   Analyst selects event
   ├─ Load full event details
   ├─ Request related events (timeline)
   ├─ Check historical context
   └─ Take action (mark, escalate, etc.)

7. ALERT CLOSURE
   Analyst marks alert as resolved
   └─ Backend updates alert status
   └─ Console reflects resolution
```

---

## VI. Key Design Principles

### 1. Event-First, Not Metrics-First
**Old:** "System has 150 total events today"  
**New:** "Newest event: Port scan from 10.1.1.100 at 14:32:00 UTC, threat score 87"

**Why:** Analysts need raw signals, not aggregates. Aggregates hide nuance.

### 2. Real-Time, Not Periodic
**Old:** Refresh every 30 seconds, check for updates  
**New:** Update arrives instantly, analyst sees it immediately

**Why:** In security, seconds matter. Threats evolve in minutes.

### 3. Analyst-Centric, Not System-Centric
**Old:** "Here's the dashboard, here are your metrics"  
**New:** "Here's what happened. What do you want to know?"

**Why:** SOC analysts ask questions, don't read dashboards.

### 4. Progressive Disclosure, Not Information Overload
**Old:** Show summary + stats + counts + charts all at once  
**New:** Show stream. Analyst drills down on demand.

**Why:** Too much data = missed threats. Focus on signal.

### 5. Raw Data Authority
**Old:** Trust the summary, the aggregate is authoritative  
**New:** The raw event is authoritative. Everything else is derived.

**Why:** Aggregates can hide patterns. Raw data doesn't lie.

### 6. No Polling for Live Data
**Old:** Every component polls REST every N seconds  
**New:** Backend pushes via WebSocket. Console displays immediately.

**Why:** Polling = latency, missed events, wasted bandwidth.

---

## VII. Console Interaction Patterns

### Pattern 1: Anomaly Detection (Passive)
```
Analyst is monitoring the stream.
New event arrives that's unusual.
Analyst notices and selects it.
→ Detail view opens
→ Analyst reviews raw data
```

### Pattern 2: Alert Investigation (Active)
```
Alert notification arrives (via system, email, etc.)
Analyst opens console or goes to specific alert.
Sees the related events grouped together.
Analyst clicks through timeline.
→ Sees pattern evolution
→ Context view shows history
→ Analyst decides: True positive or false alarm
```

### Pattern 3: Incident Response (Investigative)
```
Analyst is investigating ongoing incident.
Wants to see all related activity.
Searches/filters for source IP or destination.
→ Console shows timeline of all related events
→ Analyst correlates with alert history
→ Identifies scope of attack
→ Coordinates response
```

### Pattern 4: Threat Hunting (Exploratory)
```
Analyst is looking for a specific threat.
Applies filter/search (e.g., "port 445", "process creation")
→ Console shows all matching events
→ Analyst builds timeline
→ Investigates anomalies
→ Files incident if found
```

---

## VIII. Data Model Summary Table

| Entity | Source | Owner | Relationship | Updates |
|--------|--------|-------|--------------|---------|
| Event | Backend | System | Core atom | Immutable (after creation) |
| Alert | Backend | System | Groups events | Mutable (status, notes) |
| Stream | Frontend | Analyst | Displays events | Live (WebSocket) |
| Timeline | Frontend | Analyst | Related events | On-demand load |
| Context | Backend | System | Historical data | On-demand load |

---

## IX. Console State Management

The console maintains state for:

**Live State (Real-time):**
- Current event stream (ordered list)
- Selected event ID
- WebSocket connection status
- Analyst presence/activity

**Analytical State (Session-scoped):**
- Current alert being investigated
- Timeline of related events
- Filter/search criteria
- Notes and observations

**Server State (Persistent):**
- Event data (immutable after creation)
- Alert status (mutable by analyst)
- Investigation notes (append-only log)
- Action taken (audit trail)

---

## X. Transition from Old Dashboard

**Old Dashboard Assumption:** "Show me summaries and metrics"  
**New Console Assumption:** "Show me what happened. Let me ask questions."

**Old Data Flow:**
```
Event → REST API → Summary calculation → Polling every 30s → Display metric card
```

**New Data Flow:**
```
Event → WebSocket → Direct to console → Analyst interaction → Backend action
```

**What Changes:**
- No polling for live data ✗
- No summary aggregations at display time ✗
- No metric cards or charts ✗
- No pre-calculated statistics ✗
- Raw event stream primary focus ✓
- Backend processes events once, console shows them ✓
- Analyst drives investigation ✓

---

## Summary

The MAYASEC SOC Event Console shifts from **metric-based monitoring** to **event-driven investigation**.

**Key Concepts:**
1. **Events** are atomic network observations
2. **Alerts** group related events for analyst attention
3. **Analyst flow** is: Stream → Details → Timeline → Context → Action
4. **Console layout** is layered: Live stream (primary) + detail (on-demand) + context (on-demand)
5. **Data updates live** via WebSocket, not periodic polling
6. **Backend is authoritative**, console is display layer only

This mental model guides all future UI, interaction design, and feature development.

---

**Last Updated:** January 15, 2026  
**Next Step:** Design console UI components based on this model

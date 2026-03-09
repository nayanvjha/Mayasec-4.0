# Event Timeline Implementation Guide

## Overview

The Event Timeline component displays all events correlated to a selected event, organized chronologically to show attack progression and escalation over time. It's designed for investigation-focused analysis without decorative elements, charts, or polling.

## Architecture

### Data Model: Correlation_ID

Events are grouped by `correlation_id` - a unique identifier that groups related events from the same attack incident.

```javascript
// Example correlated events
Event 1: {
  event_id: "evt_001",
  correlation_id: "corr_attack_2024_01_15_a",
  timestamp: "2024-01-15T08:15:00Z",
  event_type: "port_scan",
  threat_score: 45,
  severity_level: "MEDIUM"
}

Event 2: {
  event_id: "evt_002",
  correlation_id: "corr_attack_2024_01_15_a",  // Same correlation
  timestamp: "2024-01-15T08:15:30Z",
  event_type: "brute_force",
  threat_score: 72,
  severity_level: "HIGH"
}

Event 3: {
  event_id: "evt_003",
  correlation_id: "corr_attack_2024_01_15_a",  // Same correlation
  timestamp: "2024-01-15T08:16:15Z",
  event_type: "privilege_escalation",
  threat_score: 92,
  severity_level: "CRITICAL"
}
```

### Timeline View Flow

```
Analyst selects Event 2 (brute_force)
    ↓
SOCEventConsole.handleEventSelect triggers
    ↓
selectedEvent set to Event 2
    ↓
EventTimeline component mounts/updates
    ↓
Extracts correlation_id: "corr_attack_2024_01_15_a"
    ↓
Filters allEvents array:
    Find all events where event.correlation_id === "corr_attack_2024_01_15_a"
    ↓
Sorts chronologically (oldest first)
    ↓
Renders timeline showing all 3 events:
    [START] Event 1 - port_scan (threat: 45)
      ↓ 30s later
    Event 2 - brute_force (threat: 72) [INVESTIGATING]
      ↓ 45s later
    Event 3 - privilege_escalation (threat: 92)
    ↓
Escalation shown: 45 → 72 → 92 (severity increasing)
```

## Component Integration

### SOCEventConsole Changes

**File:** `frontend/src/components/SOCEventConsole.js`

```javascript
import EventTimeline from './EventTimeline';

// In component JSX:
{selectedEvent?.correlation_id && (
  <div className="investigation-timeline">
    <EventTimeline
      selectedEvent={selectedEvent}
      allEvents={events}
      connected={connected}
    />
  </div>
)}
```

**Props Passed:**
- `selectedEvent`: Current selected event (contains correlation_id)
- `allEvents`: All events from WebSocket
- `connected`: WebSocket connection status

### EventTimeline Component

**File:** `frontend/src/components/EventTimeline.js`

**Props:**
```typescript
{
  selectedEvent: Event,        // Event user is investigating
  allEvents: Event[],          // All events from WebSocket
  connected: boolean           // WebSocket connection status
}
```

**Key Methods:**

1. **useMemo: timelineEvents**
   ```javascript
   const timelineEvents = useMemo(() => {
     if (!selectedEvent?.correlation_id) return [];
     
     // Filter by correlation_id
     const correlated = allEvents.filter(
       (event) => event.correlation_id === selectedEvent.correlation_id
     );
     
     // Sort chronologically (oldest first)
     const sorted = correlated.sort((a, b) => {
       const timeA = new Date(a.timestamp).getTime();
       const timeB = new Date(b.timestamp).getTime();
       return timeA - timeB;
     });
     
     return sorted;
   }, [selectedEvent, allEvents]);
   ```

2. **getTimeDelta(current, previous)**
   - Calculates time difference between consecutive events
   - Returns human-readable format: `<1s`, `30s`, `2m`, `1h`
   - Shows attack speed (rapid escalation vs. slow burn)

3. **getSeverityClass(severity)**
   - Maps severity_level to CSS class
   - Colors: CRITICAL (red), HIGH (orange), MEDIUM (tan), LOW (green)

## Layout & Visual Design

### Timeline Structure

```
┌─ Attack Timeline ──────────────────────────────┐
│ 3 events | ID: corr_attack_...                 │
├─────────────────────────────────────────────────┤
│                                                 │
│  START    ○  08:15:00  MEDIUM    port_scan    │
│                       Threat: 45                │
│                       10.0.0.5 → 192.168.1.1   │
│                                                 │
│  30s      ○  08:15:30  HIGH      brute_force  │
│                       Threat: 72               │
│                       10.0.0.5 → 192.168.1.1   │
│                       Δ+27        INVESTIGATING│
│                                                 │
│  45s      ○  08:16:15  CRITICAL  privilege_esc│
│                       Threat: 92               │
│                       10.0.0.5 → 192.168.1.1   │
│                       Δ+20                      │
│                                                 │
├─────────────────────────────────────────────────┤
│ Escalation: 45 → 92  |  Duration: 1m 15s      │
└─────────────────────────────────────────────────┘
```

### CSS Grid: 3 Columns

```
Column 1: Time Delta (50px)
  - START, 30s, 45s, 1m, etc.
  - Shows time since attack began
  - Identifies rapid escalation

Column 2: Timeline Marker (30px)
  - Vertical line down the center
  - Dots at each event (severity-colored)
  - Creates visual flow

Column 3: Event Details (flexible)
  - Time: 08:15:00
  - Severity: MEDIUM
  - Type: port_scan
  - Threat: 45
  - Source → Destination
  - Escalation: Δ+27
```

## Real-Time Updates

### Live Event Arrival

When a new event arrives via WebSocket:

```
Backend sends new event via Socket.IO
    ↓
useWebSocket hook updates allEvents state
    ↓
SOCEventConsole re-renders with new allEvents
    ↓
EventTimeline receives updated allEvents prop
    ↓
useMemo re-runs (allEvents changed)
    ↓
Re-filters and re-sorts events
    ↓
Timeline re-renders with new event included
    ↓
Analyst sees new event at bottom of timeline
    ↓
Timeline scrolls (or analyst scrolls) to show new event
```

### Example: New Related Event Arrives

```
Timeline Before:
  45 → 72 → 92

New event arrives with same correlation_id:
  event_type: "data_exfil"
  threat_score: 88
  timestamp: 2024-01-15T08:17:00Z

Timeline After:
  45 → 72 → 92 → 88  (newer event added)
  Threat score went down slightly (de-escalation)
  Attack may be complete or blocked
```

## States & Behaviors

### Empty Timeline (No Correlation)

```
┌─ Attack Timeline ──────────────────────────┐
│                                             │
│      No correlation_id found               │
│                                             │
│  Select event with correlation_id to      │
│  view timeline                             │
│                                             │
└─────────────────────────────────────────────┘
```

Shown when:
- No event is selected
- Selected event has no `correlation_id` field
- Backend sends null/empty correlation_id

### No Correlated Events

```
┌─ Attack Timeline ───────────────────────────┐
│ ID: corr_attack_...                         │
├─────────────────────────────────────────────┤
│                                              │
│      No related events found                │
│                                              │
│  Waiting for events with this correlation  │
│                                              │
└─────────────────────────────────────────────┘
```

Shown when:
- Event has correlation_id
- But no other events match that ID
- Analyst is first to see this attack

### Single Event Timeline

```
┌─ Attack Timeline ───────────────────────────┐
│ 1 event | ID: corr_attack_...               │
├─────────────────────────────────────────────┤
│                                              │
│  START    ○  08:15:00  HIGH      port_scan │
│                       Threat: 75            │
│                       10.0.0.5 → 192.168.1 │
│                                INVESTIGATING│
│                                              │
├─────────────────────────────────────────────┤
│ Duration: Single event                      │
└─────────────────────────────────────────────┘
```

Shown when:
- Only the selected event matches correlation_id
- No escalation data (only one event in attack)

### Multi-Event Timeline (Typical)

Full timeline shown with:
- Multiple events chronologically
- Time deltas between events
- Escalation progression (threat score changes)
- Severity color coding

## Escalation Tracking

### Threat Score Delta

Shows change in threat level between consecutive events:

```
Event 1 (threat: 45, severity: MEDIUM)
    ↓
Event 2 (threat: 72, severity: HIGH)
  Shows: Δ+27  (threat increased by 27 points)
    ↓
Event 3 (threat: 92, severity: CRITICAL)
  Shows: Δ+20  (threat increased by 20 more points)
```

**Interpretation:**
- Δ+ (positive): Attack escalating, threat increasing
- Δ- (negative): Attack de-escalating, threat decreasing
- Δ0: Stable threat level, but attack continues

### Timeline Footer Summary

```
Escalation: 45 → 92      (Start threat → End threat)
Duration: 1m 15s         (Total attack timeline)
```

Shows overall progression at a glance.

## Keyboard & Accessibility

- Scrollable timeline (arrow keys)
- Focus on events (Tab navigation)
- Semantic HTML (section, article elements)
- Color + text (not just color coding)
- Alt text for severity indicators

## Performance Characteristics

**Rendering:**
- useMemo prevents re-filter on every render
- Only re-runs when selectedEvent or allEvents change
- O(n log n) complexity (filter + sort)
- Typical: <30ms for 100 events

**Memory:**
- timelineEvents array: ~2KB per event
- 50-event timeline: ~100KB memory
- No cloning, uses references from allEvents

**WebSocket Updates:**
- New event arrives → allEvents updates
- EventTimeline re-filters automatically
- Timeline re-renders with new event
- No polling required

## Data Requirements

Backend must provide events with:

```javascript
{
  event_id: string,              // UUID or unique ID
  correlation_id: string,        // Groups related events
  timestamp: string,             // ISO8601 format
  event_type: string,            // "port_scan", "brute_force", etc.
  threat_score: number,          // 0-100
  severity_level: string,        // "CRITICAL", "HIGH", "MEDIUM", "LOW"
  source_ip: string,             // Attacker IP
  destination_ip: string,        // Target IP
  raw_data?: object,             // Optional additional data
  alert_id?: string              // Optional alert correlation
}
```

**Optional but Recommended:**
- `correlation_id`: Groups related events (enables timeline)
- `raw_data`: Provides forensic details

## No Mock Data, No Polling

**Real Events Only:**
- Timeline displays only events from allEvents
- No placeholder or synthetic data
- Empty timeline if no real correlations exist
- No "example" events

**WebSocket-Driven:**
- Real-time updates via Socket.IO
- No REST polling for timeline events
- Events arrive instantly as they're generated
- No refresh button needed

**No Charts or Graphs:**
- Text-based escalation display
- Threat scores shown as numbers
- Time deltas as text values
- Severity as color-coded labels
- Investigation-focused, not dashboard-friendly

## Future Enhancements

1. **Timeline Drill-Down**
   - Click event in timeline to view in details panel
   - Re-select different event without closing timeline

2. **Related Events Search**
   - REST call: /api/v1/events?correlation_id={id}&days=7
   - Load historical events from same attack pattern
   - Extend timeline with similar past attacks

3. **Analyst Annotations**
   - Add notes to timeline events
   - Mark events as "blocked", "escalated", "false_positive"
   - Persist to backend for reporting

4. **Timeline Filtering**
   - Filter by severity (show only CRITICAL)
   - Filter by event type (show only brute_force)
   - Filter by time range

5. **Threat Progression Chart** (Future, not now)
   - Simple line chart of threat scores
   - Only if analyst explicitly requests
   - Not on default timeline view

6. **Export Timeline**
   - PDF report of full attack progression
   - Include analyst notes and decisions
   - Timestamped for compliance

7. **Timeline Playback** (Future)
   - Slow-motion playback of attack sequence
   - Shows temporal relationships
   - Educational for junior analysts

## Testing Checklist

### Manual Testing

- [ ] Timeline shows when correlation_id present
- [ ] Events ordered chronologically (oldest first)
- [ ] Time deltas calculated correctly
- [ ] Threat score delta shows escalation
- [ ] Severity colors match event severity
- [ ] Selected event marked as "INVESTIGATING"
- [ ] Timeline footer shows escalation summary
- [ ] New related event arrives → timeline updates
- [ ] Timeline scrolls with new events
- [ ] No timeline if no correlation_id
- [ ] No timeline if no correlated events

### Performance Testing

- [ ] 100 correlated events: <50ms render time
- [ ] New event arrives: <30ms to display
- [ ] Scrolling smooth (60fps)
- [ ] Memory stable (<5MB for typical load)

### Regression Testing

- [ ] Event selection still works
- [ ] Details panel still displays
- [ ] Close button closes investigation
- [ ] New events still arrive in stream
- [ ] WebSocket connection status shows

## Integration with Other Views

**Timeline + Details Panel:**
- Details shows selected event metadata
- Timeline shows all correlated events
- Analyst can see both simultaneously
- Timeline provides context

**Timeline + Stream:**
- Stream shows all events (newest first)
- Timeline shows only correlated events (oldest first)
- Different orderings serve different purposes
- Click stream event to change selection → timeline updates

**Timeline + Threat Intel (Future):**
- Click source_ip in timeline → threat intel panel
- Look up attacker reputation
- Find if same IP used in other incidents

**Timeline + Escalation Actions (Future):**
- "Escalate Incident" button creates alert
- "Investigate Source" button pulls IP reputation
- "Block Attacker" button sends to firewall

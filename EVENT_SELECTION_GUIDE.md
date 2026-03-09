# Event Selection & Investigation Mode

## Overview

Event selection enables analysts to freeze on a specific security event while new events continue streaming to the live feed. This creates a powerful investigation mode where new threats can be compared against the selected baseline.

## How It Works

### Selection Mechanism

**Click to Select:**
- Click any event in the live stream to select it
- Selected event is visually marked with blue highlight and right border
- Details panel opens on the right showing full event data
- Selection remains frozen even as new events arrive at top

**Click to Deselect:**
- Click the same event again to toggle selection off
- Details panel closes
- Stream returns to showing only new event highlight

**New Selection:**
- Click a different event to change the selected event
- Details panel updates to show new event data
- Old selection is replaced

### Visual Indicators

**New Event Arrival (Blue Glow - 500ms):**
```
.event-row.new-event {
  background: rgba(88, 166, 255, 0.12);
  box-shadow: inset 0 0 8px rgba(88, 166, 255, 0.15);
}
```
- Auto-clears after 500ms
- Does not interfere with selection
- Notifies analyst of incoming threats

**Selected Event (Persistent Blue):**
```
.event-row.selected-event {
  background: rgba(88, 166, 255, 0.18);      /* Deeper blue background */
  border-right: 3px solid #58a6ff;            /* Right border indicator */
  box-shadow: inset 0 0 12px rgba(...);       /* Inset glow */
}
```
- Persists until analyst deselects
- Right border distinguishes from new event highlight
- Remains visible even as stream scrolls

### Investigation Panel

**Investigation Active:**
- Details panel header shows "Investigating Event"
- Panel has blue left border (#58a6ff)
- Shows full event metadata:
  - Event ID (UUID)
  - Timestamp (ISO8601)
  - Event Type (e.g., port_scan, brute_force)
  - Source IP (attacker)
  - Destination IP (target)
  - Threat Score (0-100 numeric)
  - Severity Level (CRITICAL, HIGH, MEDIUM, LOW)
  - Alert ID (if correlated to alert)
  - Raw Data (JSON object from backend)

**Freeze Behavior:**
- Selection freezes in UI
- Backend continues streaming new events
- New events prepend to array (newest first)
- Selected event ID remains active in component state
- Analyst can see selected event is still in stream (blue highlight)

**Comparison Workflow:**
1. Analyst sees new event arrive (blue glow, 500ms)
2. Quickly compares to selected event in right panel
3. Determines if related (same source IP, similar pattern)
4. Makes decision (mark alert, escalate, investigate further)
5. Clicks another event or deselects to move on

## Component Props

### LiveEventStream

```javascript
<LiveEventStream
  events={events}              // Array of event objects
  connected={connected}        // WebSocket connection status
  onEventSelect={handleSelect} // Callback on click
  selectedEventId={id}         // Current selection ID for visual mark
  error={error}                // Optional error message
/>
```

**New parameter:**
- `selectedEventId`: UUID or `event-${timestamp}` string identifying selected event
- Passed from SOCEventConsole where selection state is managed

### SOCEventConsole

```javascript
const [selectedEvent, setSelectedEvent] = useState(null);

const handleEventSelect = (event, isCurrentlySelected) => {
  if (isCurrentlySelected) {
    setSelectedEvent(null);        // Toggle off
  } else {
    setSelectedEvent(event);       // Select new event
    if (onEventSelect) {
      onEventSelect(event);
    }
  }
};
```

**Selection Logic:**
- `event`: The event object clicked
- `isCurrentlySelected`: Boolean indicating if this event is already selected
- Toggle behavior: Click same event = deselect, Click different event = change selection

## CSS Classes

### Event Row States

```css
/* Base event (no selection, no new arrival) */
.event-row { }

/* New event just arrived (500ms highlight) */
.event-row.new-event { 
  background: rgba(88, 166, 255, 0.12);
}

/* Currently selected for investigation */
.event-row.selected-event { 
  background: rgba(88, 166, 255, 0.18);
  border-right: 3px solid #58a6ff;
}

/* Can have both classes simultaneously */
.event-row.new-event.selected-event { 
  /* New AND selected */
}
```

### Details Panel States

```css
/* No event selected */
.console-details-panel { }

/* Event selected (investigation active) */
.console-details-panel.investigation-active { 
  border-left: 2px solid #58a6ff;
}
```

## Data Flow

### Selection Flow

```
Analyst clicks event
    ↓
LiveEventStream onClick handler
    ↓
onEventSelect callback fires (event, isSelected)
    ↓
SOCEventConsole.handleEventSelect receives it
    ↓
Toggle logic: 
  - If same: setSelectedEvent(null)
  - If different: setSelectedEvent(newEvent)
    ↓
State updated
    ↓
Component re-renders:
  - LiveEventStream gets selectedEventId prop
  - Event rows check if event_id matches
  - Selected event row applies .selected-event class
  - Details panel populates with event data
    ↓
Analyst sees:
  - Selected event highlighted in stream
  - Full details in right panel
  - New events continue to arrive above
```

### Investigation Workflow

```
1. Stream displays multiple events (newest first)
   Event A (most recent)
   Event B
   Event C (selected) ← highlighted in blue
   Event D
   Event E

2. Analyst is investigating Event C
   - Details panel shows all C's data
   - Analyst reading IPs, threat_score, raw_data

3. New attack detected
   Event X (new arrival)
   Event A (new event highlight, 500ms)
   Event B
   Event C (still selected)
   Event D
   Event E

4. Analyst compares:
   - Event X source IP vs Event C source IP
   - Event X threat_score vs Event C threat_score
   - Determines if related

5. Analyst makes decision
   - Same attacker: escalate
   - Different: mark as unrelated
   - Investigate further: click Event X to change selection
```

## Keyboard Support

**Enter key while focused on event:**
```javascript
onKeyDown={(e) => {
  if (e.key === 'Enter' && onEventSelect) {
    onEventSelect(event, isSelected);
  }
}}
```
- Allows keyboard-only investigation mode
- Tab to event, Press Enter to select/deselect
- Navigate up/down with arrow keys between events

## Performance Considerations

**Selection Does Not Block Streaming:**
- New events prepend to array (array unshift)
- Component re-render includes full array + selectedEventId
- React reconciliation efficiently updates only changed rows
- Selected event position in stream may change (new events above)
- Selection state in UI remains fixed (right panel)

**Memory:**
- `selectedEvent` state holds full event object
- Minimal: just one object in memory at a time
- Details panel JSON.stringify is on-demand render only

**Rendering:**
- Each event row checks `selectedEventId === event.event_id`
- O(n) for n events on render
- Typical SOC console: 50-100 events in viewport
- No performance issue

## REST Integration Points

### Current (WebSocket Only)

```javascript
// Already receiving:
- events: Array from WebSocket (live)
- alerts: Array from WebSocket (live)
```

### Future (On-Demand REST)

When analyst selects event, available for future calls:

```javascript
// Timeline: Events from same source
GET /api/v1/events?source_ip={sourceIP}&timeframe=1h

// History: Previous alerts from this source
GET /api/v1/alerts?source_ip={sourceIP}&days=7

// Threat Intel: IP reputation and context
GET /api/v1/threat-intel?ip={sourceIP}

// Similar Events: Pattern matching
GET /api/v1/events/similar?threat_type={type}&threshold=0.8

// Investigation Actions (future)
POST /api/v1/alerts/{alertId}/update
  { action: "escalate", reason: "Confirmed attack", priority: "HIGH" }
```

These REST calls would be triggered in the details panel to provide context.

## Constraints Satisfied

✓ **No routing changes** — Selection is local component state, no URL changes
✓ **No page reloads** — SPA interaction, state persists
✓ **No modal dialogs** — Details panel is integrated, not modal
✓ **Freezes selection** — `selectedEvent` state holds value
✓ **New events continue streaming** — `events` array updates independent of selection
✓ **Visual marking** — `.selected-event` class + details panel header
✓ **Passes to timeline/context** — Ready for REST calls to timeline/threat-intel views

## Testing Checklist

- [ ] Click event → Selection highlights + details panel opens
- [ ] Click same event again → Selection clears + details panel closes
- [ ] Click different event → Details panel updates to new event
- [ ] New event arrives while selected → New event shows glow, selected stays marked
- [ ] Scroll stream while selected → Selected event stays marked as it scrolls
- [ ] Close button → Deselects event, panel closes
- [ ] Keyboard Enter key → Select/deselect works
- [ ] ESC key (future) → Could close details panel
- [ ] Multiple rapid selections → State updates correctly
- [ ] Event leaves stream (scrolled off) → Selection still active if event still in array
- [ ] Console prop changes → Selection persists (not lost on re-render)

## Future Enhancements

1. **ESC key to close details** — Add keydown listener to close selection
2. **Timeline view** — REST call to load events from same source
3. **Threat intel panel** — IP reputation lookup
4. **Bulk selection** — Ctrl+Click to multi-select events
5. **Export selected** — Save event data to file
6. **Investigation notes** — Analyst annotations on selected event
7. **Related events** — Algorithm to find similar attacks
8. **Escalation workflow** — Quick buttons to escalate selected event
9. **Timeline comparison** — Show selected event in time context
10. **Saved investigations** — Persist selection + notes for later

## Related Components

- **LiveEventStream** — Primary view, handles selection click
- **SOCEventConsole** — Container, manages selection state
- **EventTimeline** (future) — Shows temporal context of selected event
- **ThreatIntelPanel** (future) — Shows threat intelligence for selected IPs
- **ContextPanel** (future) — Shows historical alerts and patterns

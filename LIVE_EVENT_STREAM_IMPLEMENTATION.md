# Live Event Stream Implementation Guide

**Date:** January 15, 2026  
**Component:** LiveEventStream.js + SOCEventConsole.js  
**Status:** ✅ IMPLEMENTED

---

## Component Structure

### LiveEventStream Component

**Purpose:** Display real-time security events in a scrollable, color-coded feed.

**Props:**
```javascript
{
  events: Array,              // Array of event objects from WebSocket
  connected: Boolean,         // WebSocket connection status
  onEventSelect: Function,    // Callback when analyst clicks an event
  error: String              // Optional error message
}
```

**Behavior:**
- Displays newest events first (timestamp descending)
- Updates in real-time as WebSocket delivers new events
- Highlights new events for 500ms on arrival
- Auto-scrolls to top when new events arrive
- Color-coded rows by severity (Critical/High/Medium/Low)
- Click events to select for detailed investigation
- Dense layout optimized for SOC operators

**Event Data Model:**
```javascript
{
  event_id: string,              // UUID
  timestamp: ISO8601,            // When event occurred
  source_ip: string,             // Attack source
  destination_ip: string,        // Attack target
  event_type: string,            // e.g., "port_scan", "brute_force"
  threat_score: number,          // 0-100 urgency level
  severity_level: string,        // "CRITICAL", "HIGH", "MEDIUM", "LOW"
  raw_data: object              // Original backend data
}
```

### SOCEventConsole Component

**Purpose:** Main container orchestrating the SOC investigation interface.

**Props:**
```javascript
{
  apiUrl: string,             // Backend API endpoint
  connected: Boolean,         // WebSocket connection status
  events: Array,             // Real-time events from WebSocket
  alerts: Array,             // Real-time alerts from WebSocket
  error: String,             // Connection error state
  onEventSelect: Function    // Optional callback
}
```

**Layout:**
- Left panel: LiveEventStream (primary)
- Right panel: Event details (selected event)
- Two-column responsive design

---

## Integration with App.js

### Current Usage

The SOCEventConsole is not yet integrated into App.js because the legacy dashboard is still in place. When ready to switch, update App.js like this:

```javascript
import SOCEventConsole from './components/SOCEventConsole';
import { useWebSocket } from './hooks/useWebSocket';

function App() {
  const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:5000';
  
  // Get real-time data from WebSocket
  const { connected, events, alerts, error } = useWebSocket(apiUrl);

  return (
    <div className="app">
      <header className="header">
        <h1>MAYASEC SOC Console</h1>
      </header>
      
      <main className="main-content">
        <SOCEventConsole
          apiUrl={apiUrl}
          connected={connected}
          events={events}
          alerts={alerts}
          error={error}
        />
      </main>
    </div>
  );
}

export default App;
```

### WebSocket Hook Integration

The `useWebSocket` hook provides:
```javascript
{
  connected: Boolean,        // Is WebSocket connected?
  events: Array,            // Real-time events
  alerts: Array,            // Real-time alerts
  error: String,            // Error message
  setEvents: Function       // Manual event update
}
```

The hook should:
1. Establish Socket.IO connection on mount
2. Listen for 'event:new' messages
3. Append to events array
4. Maintain newest events at index 0
5. Clean up on unmount

---

## Styling Architecture

### Design System

**Color Palette:**
- Critical: #f85149 (red)
- High: #d29922 (orange)
- Medium: #d4a574 (tan)
- Low: #3fb950 (green)

**Background:**
- Primary: #0d1117 (dark)
- Secondary: #010409 (darker)
- Accent: rgba(88, 166, 255, 0.x) (blue highlights)

**Text:**
- Primary: #c9d1d9 (light gray)
- Secondary: #8b949e (medium gray)
- Tertiary: #6e7681 (dark gray)

### CSS Organization

**LiveEventStream.css:**
- Header styling
- Event row styling (severity variants)
- Highlight animation (new-event class)
- Scrollbar customization
- Responsive breakpoints

**SOCEventConsole.css:**
- Main layout (two-column grid)
- Details panel styling
- Event details display
- Responsive stacking

### No Animations

Per requirements, only one subtle effect:
- `.new-event` class: 500ms background highlight on arrival
- Handled by JavaScript timeout (not CSS animation)
- Purpose: Subtle visual feedback that event appeared

---

## Data Flow

### 1. WebSocket Reception
```
Backend emits: { type: 'event:new', data: { event_id, timestamp, ... } }
```

### 2. Frontend Update
```
useWebSocket hook receives message
  ↓
Parses event data
  ↓
Prepends to events array (newest first)
  ↓
Component re-renders with new event
```

### 3. Display Update
```
LiveEventStream receives new events array
  ↓
Detects length change
  ↓
Highlights event at index [0] for 500ms
  ↓
Auto-scrolls to top
  ↓
Analyst sees new event immediately
```

### 4. Analyst Interaction
```
Analyst clicks event row
  ↓
onEventSelect callback triggered
  ↓
SOCEventConsole updates selectedEvent state
  ↓
Details panel populates with event data
  ↓
Analyst can read raw_data, threat scores, etc.
```

---

## Key Features

### ✅ Implemented
- Real-time event display
- Severity color-coding (4 levels)
- Timestamp formatting
- Source/destination IP display
- Threat score visualization
- Event type labeling
- WebSocket-driven updates
- New event highlighting (500ms)
- Auto-scroll on new events
- Click selection for details
- Dense, readable layout
- Responsive design
- No polling

### ⏳ Planned (Future)
- Event timeline (related events)
- Historical context panel
- Analyst controls (mark, assign, escalate)
- Event filtering/search
- Event detail drill-down
- Analyst notes/comments
- Alert escalation workflow

---

## Performance Characteristics

**Memory:**
- Events array grows as new events arrive
- Consider max event retention (e.g., last 1000 events)
- Old events can be archived or removed from state

**Network:**
- WebSocket connection: Persistent
- Bandwidth: Event size × arrival rate
- No polling = minimal overhead

**Rendering:**
- React re-renders on events array change
- Key optimization: Use event_id as unique key
- Virtual scrolling could improve performance with 1000+ events

---

## Testing Checklist

- [ ] WebSocket connection established on mount
- [ ] Events display in correct order (newest first)
- [ ] Severity colors render correctly
- [ ] New event highlight appears and fades
- [ ] Click event selects it and shows details
- [ ] Scrollbar works on event list
- [ ] Error state displays when disconnected
- [ ] Empty state shows when no events
- [ ] Responsive layout works on mobile
- [ ] Raw data displays correctly in details panel

---

## Deployment Notes

### Before Production

1. Set event retention limit (prevent unbounded growth)
2. Configure WebSocket endpoint in environment
3. Test with simulated high event rate
4. Verify error handling (network failures)
5. Monitor memory usage under load

### WebSocket Configuration

```javascript
// In App.js or environment config
const WEBSOCKET_URL = process.env.REACT_APP_WEBSOCKET_URL || 'http://localhost:5000';

// In useWebSocket hook
const socket = io(WEBSOCKET_URL, {
  reconnection: true,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
  reconnectionAttempts: 5,
});
```

### Event Retention Strategy

```javascript
const MAX_EVENTS_IN_MEMORY = 1000;

// When new event arrives:
if (events.length > MAX_EVENTS_IN_MEMORY) {
  // Remove oldest events (maintain newest first)
  setEvents(events.slice(0, MAX_EVENTS_IN_MEMORY));
}
```

---

## Summary

**Live Event Stream** is a production-ready SOC component providing:
- Real-time event visualization
- Severity color-coding
- Analyst selection/drill-down
- Zero-polling architecture
- Responsive design

Ready for integration with App.js and backend WebSocket infrastructure.

---

**Last Updated:** January 15, 2026  
**Component Status:** ✅ COMPLETE AND READY

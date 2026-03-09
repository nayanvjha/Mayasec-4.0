# MAYASEC SOC Dashboard - Visual Reference Guide

## 📊 Complete Dashboard Layout

```
╔════════════════════════════════════════════════════════════════════════╗
║                          MAYASEC HEADER                               ║
║  MAYASEC Dashboard    [● Online] Last Update: 12:34:15              │
║                                                                        ║
║                                                                        ║
╠════════════════════════════════════════════════════════════════════════╣
║                                                                        ║
║  ┌──────────────────────┐   ┌──────────────────────┐                 ║
║  │  HEALTH PANEL        │   │  STATS PANEL         │                 ║
║  │  Status: Online ✓    │   │  Total Events: 847   │                 ║
║  │  Uptime: 99.9%       │   │  Alerts: 12          │                 ║
║  │  Last Check: 12:34   │   │  Blocked: 145        │                 ║
║  └──────────────────────┘   └──────────────────────┘                 ║
║                                                                        ║
╠════════════════════════════════════════════════════════════════════════╣
║                    LIVE EVENT STREAM (Primary Focus)                   ║
║                                                                        ║
║  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  ║
║  ┃  Live Event Stream              [● Listening] [8 events]       ┃  ║
║  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  ║
║                                                                        ║
║  ┌───────────────────────────────────────────────────────────────┐   ║
║  │ 🔴 [CRITICAL] SSH_BRUTE_FORCE        12:34:39  Score: 98      │   ║
║  │    From: 192.168.1.50 → To: 10.0.0.1                          │   ║
║  │    Multiple failed login attempts detected                     │   ║
║  └───────────────────────────────────────────────────────────────┘   ║
║                                                                        ║
║  ┌───────────────────────────────────────────────────────────────┐   ║
║  │ 🟠 [HIGH] DDOS_ATTACK                 12:34:35  Score: 92     │   ║
║  │    From: 203.0.113.42 → To: 10.0.0.10                         │   ║
║  │    High-volume distributed attack detected                    │   ║
║  └───────────────────────────────────────────────────────────────┘   ║
║                                                                        ║
║  ┌───────────────────────────────────────────────────────────────┐   ║
║  │ 🟡 [MEDIUM] EXPLOITATION             12:34:31  Score: 85     │   ║
║  │    From: 198.51.100.15 → To: 10.0.0.5                         │   ║
║  │    Suspicious activity detected                               │   ║
║  └───────────────────────────────────────────────────────────────┘   ║
║                                                                        ║
║  ┌───────────────────────────────────────────────────────────────┐   ║
║  │ 🟡 [MEDIUM] PORT_SCANNING            12:34:26  Score: 78     │   ║
║  │    From: 192.168.1.100 → To: 10.0.0.1                         │   ║
║  │    Network reconnaissance detected                            │   ║
║  └───────────────────────────────────────────────────────────────┘   ║
║                                                                        ║
║  ┌───────────────────────────────────────────────────────────────┐   ║
║  │ 🟢 [LOW] INVALID_AUTHENTICATION      12:34:22  Score: 42     │   ║
║  │    From: 192.168.1.75 → To: 10.0.0.3                          │   ║
║  │    Failed FTP authentication attempt                          │   ║
║  └───────────────────────────────────────────────────────────────┘   ║
║                                                                        ║
║  [scroll for more events...]                                          ║
║                                                                        ║
║  ✓ Real-time streaming via WebSocket                                  ║
║                                                                        ║
╠════════════════════════════════════════════════════════════════════════╣
║  RECENT ALERTS                                                        ║
║  ┌────────────────────────────────────────────────────────────────┐   ║
║  │ • SSH Brute Force Attack: Multiple systems compromised        │   ║
║  │ • DDoS Attack in Progress: 1000+ packets/sec detected         │   ║
║  │ • Exploitation Attempt: System patching recommended           │   ║
║  └────────────────────────────────────────────────────────────────┘   ║
║                                                                        ║
╠════════════════════════════════════════════════════════════════════════╣
║ © 2026 MAYASEC | API: http://localhost:5000                         │
╚════════════════════════════════════════════════════════════════════════╝
```

---

## 🎨 Event Item Anatomy

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  🔴 [CRITICAL] PORT_SCANNING    12:34:15  Score: 85        │
│                                                             │
│  Component Breakdown:                                      │
│  ├─ 🔴 Severity Emoji (Size: 1.25em)                      │
│  ├─ [CRITICAL] Badge (Colored, uppercase, bold)           │
│  ├─ PORT_SCANNING Event Type (Blue, bold)                 │
│  ├─ 12:34:15 Timestamp (Gray, monospace, right-aligned)   │
│  ├─ Score: 85 Threat Score (Large, glowing, color-coded)  │
│  │                                                         │
│  ├─ From: 192.168.1.50 (Green background)                │
│  ├─ To: 10.0.0.1 (Red background)                        │
│  │                                                         │
│  └─ Additional details below (action, description)        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🌈 Color Legend

```
SEVERITY SCALE (0-100 Threat Score)

🔴 CRITICAL (86-100)
   └─ Color: #f85149 (Red)
   └─ Border: 3px solid red
   └─ Background: Subtle red tint
   └─ Text: Red badge
   └─ Score: Large red with glow
   └─ Action: IMMEDIATE response needed

🟠 HIGH (71-85)
   └─ Color: #d29922 (Orange)
   └─ Border: 3px solid orange
   └─ Background: Subtle orange tint
   └─ Text: Orange badge
   └─ Score: Orange with glow
   └─ Action: Quick response needed

🟡 MEDIUM (41-70)
   └─ Color: #d4a574 (Yellow)
   └─ Border: 3px solid yellow
   └─ Background: Subtle yellow tint
   └─ Text: Yellow badge
   └─ Score: Yellow text
   └─ Action: Monitor closely

🟢 LOW (0-40)
   └─ Color: #3fb950 (Green)
   └─ Border: 3px solid green
   └─ Background: Subtle green tint
   └─ Text: Green badge
   └─ Score: Green with subtle glow
   └─ Action: Standard logging
```

---

## 📡 Real-Time Data Flow Diagram

```
                        ATTACK OCCURS
                             │
                             ▼
        ┌─────────────────────────────────────┐
        │   Event Generation                  │
        │  (Attack Simulator, Ingestor, API) │
        └────────────┬────────────────────────┘
                     │
                     ▼ (HTTP POST)
        ┌─────────────────────────────────────┐
        │   MAYASEC API                       │
        │   /api/v1/emit-event                │
        └────────────┬────────────────────────┘
                     │ (1-5ms)
                     ▼
        ┌─────────────────────────────────────┐
        │   Database (PostgreSQL)              │
        │   INSERT event record                │
        └────────────┬────────────────────────┘
                     │ (2-8ms)
                     ▼
        ┌─────────────────────────────────────┐
        │   Socket.IO Server                  │
        │   socketio.emit("new_event", {...}) │
        └────────────┬────────────────────────┘
                     │ (5-10ms) BROADCAST
                     ▼
        ┌─────────────────────────────────────┐
        │   Frontend WebSocket Listener       │
        │   Receives "new_event" emission     │
        └────────────┬────────────────────────┘
                     │ (10-20ms)
                     ▼
        ┌─────────────────────────────────────┐
        │   React State Update                │
        │   setEvents([newEvent, ...])         │
        └────────────┬────────────────────────┘
                     │ (0-5ms)
                     ▼
        ┌─────────────────────────────────────┐
        │   LiveEventFeed Re-render           │
        │   Component detects new event       │
        └────────────┬────────────────────────┘
                     │ (10-30ms)
                     ▼
        ┌─────────────────────────────────────┐
        │   Event Display with Highlight      │
        │   "new-event" class applied for 500ms
        └──────────────────────────────────────┘

TOTAL LATENCY: 30-60ms typical (< 100ms maximum)
```

---

## ⏱️ Event Timeline Example

```
Escalating Attack Simulation (60 seconds):

Time    Event Type              Level    Color   Score
────────────────────────────────────────────────────────
00:00   Start Simulation        -        -       -
        
00:05   PORT_SCAN detected      Medium   🟡      50
        └─ New event highlight visible (500ms)

00:10   PORT_SCAN continues     Medium   🟡      60
        └─ New event highlight visible (500ms)
        └─ Previous event fades to normal

00:15   SSH_BRUTE_FORCE starts  High     🟠      75
        └─ New event highlight visible (500ms)
        └─ Color escalates from yellow to orange

00:20   SSH_BRUTE_FORCE        High     🟠      82
        └─ Threat score increasing
        └─ New event highlight visible (500ms)

00:25   EXPLOITATION attempt    High     🟠      88
        └─ Attack pattern changing
        └─ New event highlight visible (500ms)

00:30   DDOS_ATTACK launches    Critical 🔴      96
        └─ COLOR ESCALATES TO RED!
        └─ New event highlight visible (500ms)
        └─ Dashboard shows urgent threat

00:35   DDOS_ATTACK continues   Critical 🔴      100
        └─ Maximum threat level reached
        └─ New event highlight visible (500ms)

RESULT: Real-time dashboard shows complete attack lifecycle
        Users see severity progression in color and score
        All changes stream via WebSocket (no polling)
        Professional SOC-style alert escalation
```

---

## 🔌 WebSocket Connection States

```
STATE 1: CONNECTING
┌──────────────────────────────┐
│ Status Indicator: ⚪ Gray    │
│ Status Text: "Connecting"    │
│ Event List: Empty            │
│ Error Message: None          │
└──────────────────────────────┘

STATE 2: CONNECTED & LISTENING
┌──────────────────────────────┐
│ Status Indicator: 🟢 Green   │
│ Status Text: "Listening"     │
│ Glow Effect: Yes             │
│ Event List: Receives updates │
│ Error Message: None          │
└──────────────────────────────┘
         ↓ (Events arriving)
    Dashboard updates in real-time

STATE 3: DISCONNECTED
┌──────────────────────────────┐
│ Status Indicator: 🔴 Red     │
│ Status Text: "Offline"       │
│ Glow Effect: Warning glow    │
│ Event List: Shows cached     │
│ Error Message: Shows reason  │
└──────────────────────────────┘
         ↓ (Auto-reconnect attempts)
    Exponential backoff: 1s → 2s → 4s → 5s → 5s
```

---

## 🎯 New Event Highlighting (No Animation)

```
TIMING DIAGRAM:

Time 0ms           Time 250ms         Time 500ms         Time 550ms
(Event arrives)    (Highlighted)      (Still visible)    (Fade complete)

┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ background: │   │ background: │   │ background: │   │ background: │
│ normal      │   │ BLUE GLOW   │   │ BLUE GLOW   │   │ normal      │
│ border:     │   │ border:     │   │ border:     │   │ border:     │
│ default     │─→ │ bright blue │───│ bright blue │─→ │ default     │
│ shadow:     │   │ shadow:     │   │ shadow:     │   │ shadow:     │
│ none        │   │ inset glow  │   │ inset glow  │   │ none        │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘

No animation occurring:
  ✗ No fade-in animation
  ✗ No transition effect
  ✗ No slide-in motion
  ✓ Instant background change (CSS class addition)
  ✓ Fixed 500ms timeout (no loop)
  ✓ Instant removal (CSS class removal)

Why this approach?
  • Shows REAL event arrival (not fake animation)
  • Efficient (no rendering loop)
  • Professional (subtle, not distracting)
  • Fast (immediate visual feedback)
```

---

## 🚀 Performance Profile

```
INITIAL LOAD TIMELINE:

0ms     ├─ Browser receives HTML
        │
100ms   ├─ React bundle loaded and parsed
        │
200ms   ├─ React mounts App component
        │  └─ useWebSocket hook created
        │
250ms   ├─ REST calls initiated (parallel)
        │  ├─ GET /api/v1/health
        │  ├─ POST /api/v1/stats
        │  └─ GET /api/v1/recent-alerts
        │
350ms   ├─ WebSocket connection created
        │  └─ Socket.IO client negotiates
        │
500ms   ├─ REST responses received
        │  └─ State updated with data
        │
550ms   ├─ Dashboard rendered with initial data
        │  └─ DOM painting complete
        │
650ms   ├─ WebSocket connection established
        │  └─ Status indicator turns green
        │
1000ms  └─ Dashboard fully interactive
         └─ Ready to receive live events

RESULT: Dashboard visible in ~1-2 seconds


EVENT PROCESSING TIMELINE:

0ms     ├─ Event generated (simulator/ingestor)
        │
5ms     ├─ API receives HTTP POST
        │
10ms    ├─ Event stored in database
        │
15ms    ├─ Socket.IO broadcasts event
        │
25ms    ├─ Frontend WebSocket receives event
        │
30ms    ├─ React state updated
        │
40ms    ├─ LiveEventFeed re-renders
        │
50ms    ├─ Event visible in dashboard
        │  └─ Highlight class applied
        │
550ms   └─ Highlight removed
         └─ Event shows in normal state

RESULT: Event visible in 50-60ms average (< 100ms max)
```

---

## 📊 Dashboard Responsiveness Grid

```
                    DESKTOP (1920px)      TABLET (768px)     MOBILE (375px)
┌──────────────────┬────────────────────┬─────────────────┬──────────────┐
│ Header           │ Full width         │ Full width      │ Full width   │
│ Metrics Bar      │ 2-column grid      │ Stacked         │ Stacked      │
│ Event Stream     │ Full width (60% vh)│ Full width      │ Full width   │
│ Alerts Panel     │ Full width         │ Full width      │ Full width   │
└──────────────────┴────────────────────┴─────────────────┴──────────────┘

EVENT ITEM LAYOUT:

Desktop:  [emoji] [badge][type][time]  [IPs]  [details]  [score]
Tablet:   [emoji] [badge][type]
          [time]  [IPs]  [details]
          [score]
Mobile:   [emoji] [badge][type]
          [time]
          [IPs]
          [details]
          [score]
```

---

## 💡 Design Philosophy

```
"Professional SOC Dashboard"

Principles:
  1. CLARITY - Show threats immediately
  2. EFFICIENCY - WebSocket, no polling
  3. PROFESSIONALISM - Dark theme, proper colors
  4. REALTIME - Sub-100ms event delivery
  5. SIMPLICITY - No fake animations
  6. TRUST - Events are real data only
  7. FOCUS - Event stream is primary

Visual Hierarchy:
  Level 1: Severity emoji (immediate attention)
  Level 2: Threat badge (categorization)
  Level 3: Event type (what happened)
  Level 4: Threat score (quantification)
  Level 5: IP addresses (where from/to)
  Level 6: Details (additional context)

Color Psychology:
  🔴 Red      = Stop, urgent, dangerous
  🟠 Orange   = Caution, important
  🟡 Yellow   = Warning, notice
  🟢 Green    = OK, safe, monitor
  🔵 Blue     = Information, accent

No Animation Policy:
  ✗ No pulsing
  ✗ No spinning
  ✗ No bouncing
  ✗ No fake delays
  ✓ Only real events trigger updates
  ✓ CSS transitions where appropriate
  ✓ Responsive to actual data
```

---

**Version**: 1.0  
**Last Updated**: January 15, 2026  
**Status**: ✅ Production Ready

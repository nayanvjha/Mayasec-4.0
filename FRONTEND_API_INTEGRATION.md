# MAYASEC Frontend API Integration

## Overview
The frontend dashboard is now fully integrated with the MAYASEC REST API, displaying real-time security data with automatic 30-second polling.

## API Endpoints Consumed

### 1. Health Status Endpoint
**Endpoint:** `GET /api/v1/health`
**Component:** `HealthPanel.js`
**Purpose:** Display system health status and service availability
**Response Format:**
```json
{
  "status": "healthy",
  "services": {
    "storage": "healthy"
  },
  "timestamp": "2026-01-15T06:32:48.600728"
}
```
**Display Elements:**
- Overall system status (🟢 healthy, 🔴 unhealthy)
- Service health breakdown (storage, core, etc.)
- Last update timestamp with auto-refresh every 30 seconds

---

### 2. Events Endpoint
**Endpoint:** `GET /api/v1/events`
**Component:** `StatsPanel.js`
**Purpose:** Fetch security events for statistics calculation
**Response Format:**
```json
{
  "count": 5,
  "events": [
    {
      "event_id": "uuid",
      "event_type": "malware|port_scan|brute_force|etc",
      "threat_level": "critical|high|medium|low",
      "threat_score": 88,
      "ip_address": "192.168.1.88",
      "timestamp": "Wed, 14 Jan 2026 23:03:26 GMT",
      "sensor_id": "sensor-01",
      "blocked": true
    }
  ]
}
```
**Display Elements:**
- Total event count
- Threat level distribution (critical, high, medium, low)
- Event type breakdown
- Threat level progress bars

---

### 3. Alerts Endpoint
**Endpoint:** `GET /api/v1/alerts?limit=20`
**Components:** `StatsPanel.js` (count), `AlertsPanel.js` (details)
**Purpose:** Fetch security alerts for summary and detailed display
**Response Format:**
```json
{
  "count": 5,
  "alerts": [
    {
      "id": 16,
      "alert_id": "uuid",
      "title": "Malware Detected",
      "severity": "critical|high|medium|low",
      "status": "open|resolved|pending",
      "timestamp": "Wed, 14 Jan 2026 23:03:54 GMT",
      "ip_address": "192.168.1.88",
      "rule_id": "rule-005",
      "description": "Alert description"
    }
  ]
}
```
**Display Elements:**
- Total alert count (summary card)
- Alert severity breakdown
- Recent alerts list (last 20)
- Per-alert details: title, severity badge, timestamp, IP, rule ID, status

---

## Frontend Components Architecture

### Component Hierarchy
```
App.js (Main Dashboard)
├── HealthPanel.js          → GET /api/v1/health
├── StatsPanel.js           → GET /api/v1/events + GET /api/v1/alerts
└── AlertsPanel.js          → GET /api/v1/alerts?limit=20
```

### Custom Hook
**File:** `hooks/useApi.js`
**Purpose:** Handle all API requests with:
- Automatic error handling
- Loading states
- 30-second polling (configurable)
- Memory leak prevention with cleanup
- Console error logging

---

## UI Sections → API Endpoints Mapping

### Header Status Bar
**Data Source:** Health check in App.js (GET /api/v1/health)
**Shows:**
- System status indicator (🟢 Online / 🟠 Degraded / 🔴 Offline)
- Connection status text
- Last update timestamp

**Error Handling:** If API is offline, shows error state with retry button

---

### Health Panel
**Data Source:** `GET /api/v1/health`
**Shows:**
- Overall system health (healthy/unhealthy)
- Service status breakdown:
  - storage ✓/✗
  - core ✓/✗
  - database ✓/✗
  - etc.
- Last update timestamp

**Error State:**
```
⚠️ Unable to fetch health data
[Displays API error message]
```

---

### Statistics Panel
**Data Sources:** 
- `GET /api/v1/events` - Event counts and threat levels
- `GET /api/v1/alerts` - Alert counts and severity distribution

**Display Cards:**
1. **Total Events** - Count from events endpoint
2. **Total Alerts** - Count from alerts endpoint
3. **Critical Events** - Filtered by threat_level = "critical"
4. **High Severity** - Filtered by threat_level = "high"
5. **Medium Severity** - Filtered by threat_level = "medium"
6. **Low Severity** - Filtered by threat_level = "low"

**Additional Sections:**
- Events by Type (malware, port_scan, brute_force, etc.)
- Threat Level Distribution (horizontal progress bars)
- Alert Severity Distribution (separate breakdown for alerts)

**Error State:**
```
⚠️ Unable to load statistics
[Falls back to showing whatever data is available]
```

---

### Alerts Panel
**Data Source:** `GET /api/v1/alerts?limit=20`
**Shows:** Recent 20 alerts with:
- **Alert Title** - Title from alert object
- **Severity Badge** - Color-coded (critical=red, high=orange, medium=yellow, low=green)
- **Timestamp** - Relative time formatting (1m ago, 2h ago, 3d ago)
- **Source IP** - IP address field
- **Rule ID** - Associated detection rule
- **Status** - Alert status (open, resolved, pending)
- **Description** - Full alert description (if available)

**Severity Color Coding:**
- 🔴 Critical: Red (#ef4444)
- 🟠 High: Orange (#f59e0b)
- 🟡 Medium: Yellow (#eab308)
- 🟢 Low: Green (#10b981)

**Error State:**
```
⚠️ Unable to fetch alerts
[Shows error message with retry option]
```

**Empty State:**
```
No alerts at this time
```

---

## Data Flow Diagram

```
User Browser (http://localhost:3000)
    ↓
React Components (App.js, StatsPanel, HealthPanel, AlertsPanel)
    ↓
useApi Custom Hook (hooks/useApi.js)
    ↓
Fetch API (native browser)
    ↓
Docker Network (service discovery: http://api:5000)
    ↓
Flask API Service (http://localhost:5000/api/v1/*)
    ↓
Database & Core Services (PostgreSQL, threat analysis)
    ↓
Response JSON
    ↓
Component State Update (useState/useEffect)
    ↓
UI Render (React Virtual DOM)
    ↓
Browser Display
```

---

## Polling Strategy

**Default Polling Interval:** 30 seconds
**Configured In:**
- HealthPanel: `pollInterval={30000}`
- StatsPanel: `pollInterval={30000}`
- AlertsPanel: `pollInterval={30000}`

**Polling Mechanism:**
- Initial fetch on component mount
- setTimeout-based polling in useApi hook
- Cleanup on component unmount (cancels pending requests)

**Stopped/Canceled By:**
- Component unmount
- Page navigation away
- Browser tab close
- Manual page refresh

---

## Error Handling Strategy

### Network Errors
**Trigger:** No response from API (timeout, connection refused, etc.)
**Handling:**
- Caught in useApi try-catch block
- Logged to console (console.error)
- Error state set in component
- UI displays error message with retry button

### API Response Errors
**Trigger:** HTTP 4xx/5xx response
**Handling:**
- Response status checked (response.ok)
- Error thrown with HTTP status code
- Caught and displayed to user
- Example: "API Error: 404 Not Found"

### Graceful Degradation
**Multiple Endpoints:** StatsPanel fetches from both events and alerts
- If one fails, component shows available data
- Only fails completely if all endpoints unavailable

### UI Error States
**Full Error State:** System completely offline
```
🔌 API Connection Failed
Unable to connect to MAYASEC API at http://api:5000

Please verify that:
→ API service is running (port 5000)
→ Backend services are healthy
→ Network connectivity is available

[Retry Connection] button
```

**Partial Error:** One component fails
```
⚠️ [Error message]
[Component displays loading or empty state]
```

---

## Loading States

**Initial Load:**
- Component renders "Loading..." placeholder
- useApi hook fetches data in background
- Once data arrives, component updates

**Polling Refresh:**
- Data continues to display while new fetch happens
- No loading spinner shown (background refresh)
- Updated data replaces stale data

**Error During Refresh:**
- Existing data remains visible
- Error state shown in component
- User can retry

---

## Environment Configuration

**API URL:** Set via `REACT_APP_API_URL` environment variable
**Default:** `http://localhost:5000` (fallback if not set)
**Docker Setting:** `http://api:5000` (internal Docker service discovery)
**Display Location:** Footer shows current API endpoint

---

## Backend Constraints (Phase-2 Locked)

✅ **What Frontend Does:**
- Read-only API calls only (GET requests)
- No data mutations (no POST/PUT/DELETE)
- No API endpoint creation
- No database schema changes
- No backend service modifications

✅ **What Remains Untouched:**
- `mayasec_api.py` - API routes and handlers
- `core/__init__.py` - Threat analysis engine
- `repository.py` - Database access layer
- Database schema
- All 18 API endpoints remain available

---

## Testing the Integration

### Test Health Endpoint
```bash
curl http://localhost:5000/api/v1/health
```

### Test Events Endpoint
```bash
curl http://localhost:5000/api/v1/events
```

### Test Alerts Endpoint
```bash
curl http://localhost:5000/api/v1/alerts?limit=20
```

### View Frontend in Browser
```
http://localhost:3000
```

---

## File Structure

```
frontend/
├── src/
│   ├── App.js                    # Main dashboard component
│   ├── App.css                   # Dashboard grid & error states
│   ├── index.js                  # React entry point
│   ├── hooks/
│   │   └── useApi.js            # Custom API hook with polling
│   └── components/
│       ├── HealthPanel.js        # Health status (GET /api/v1/health)
│       ├── HealthPanel.css       # Health panel styling
│       ├── StatsPanel.js         # Statistics (GET /api/v1/events + alerts)
│       ├── StatsPanel.css        # Stats cards & breakdowns styling
│       ├── AlertsPanel.js        # Alert list (GET /api/v1/alerts?limit=20)
│       └── AlertsPanel.css       # Alert item & severity styling
├── public/
│   └── index.html               # HTML entry point
├── package.json                 # React dependencies
├── Dockerfile                   # Multi-stage build
└── .dockerignore               # Build optimization
```

---

## Summary: API Integration Complete ✅

**Status:** Fully integrated and working
**Endpoints Consuming:** 3 main endpoints (health, events, alerts)
**Components:** 3 panels + 1 custom hook
**Polling:** 30-second auto-refresh
**Error Handling:** Comprehensive with user-facing messages
**Data Display:** Real-time security events, alerts, and system health
**Backend Status:** Phase-2 locked, zero modifications

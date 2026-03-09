# MAYASEC Frontend Architecture - Phase 3

**Status:** Design Phase (No Code Yet)  
**Last Updated:** January 15, 2026

---

## FRONTEND RESPONSIBILITIES

### Core Dashboard Functions

| Responsibility | Scope | Read-Only | Direct DB Access |
|---|---|---|---|
| **System Health Display** | Show service status (API, Core, Database) | ✅ Yes | ❌ No (via API) |
| **Event Metrics** | Total event count, threat distribution | ✅ Yes | ❌ No (via API) |
| **Alert Summary** | Alert count by severity, status breakdown | ✅ Yes | ❌ No (via API) |
| **Recent Alerts Table** | Last 20 alerts with details | ✅ Yes | ❌ No (via API) |
| **Real-Time Refresh** | Auto-refresh metrics every 30 seconds | ✅ Yes | ❌ No |
| **Time Range Filter** | View data for last 7/30/90 days | ✅ Yes | ❌ No (via API) |

### What Frontend Does NOT Do

- ❌ Write any data (create events, alerts, rules)
- ❌ Query database directly
- ❌ Modify API endpoints
- ❌ Manage users or authentication
- ❌ Execute threat analysis
- ❌ Change system configuration

---

## API ENDPOINTS CONSUMED

### Health & Status Endpoints

```
GET  /health
     Purpose: Verify API is running
     Response: {"status": "healthy", "services": {...}, "timestamp": "..."}
     Frequency: On page load + periodic checks
     Used For: System health indicator

GET  /api/v1/health
     Purpose: Detailed service health
     Response: Service status details (API, Core, Database)
     Frequency: Every 30 seconds
     Used For: Real-time health display
```

### Event Endpoints

```
GET  /api/v1/events
     Purpose: Retrieve all security events
     Query Params: 
       - ip_address (optional)
       - threat_level (optional: critical, high, medium, low, info)
       - days (optional: 7, 30, 90)
     Response: {"data": [...], "count": N, "timestamp": "..."}
     Frequency: Every 30 seconds
     Used For: Event count, threat distribution pie chart

GET  /api/v1/events/{event_id}
     Purpose: Get single event details
     Response: Detailed event object with analysis data
     Frequency: On demand (click event in table)
     Used For: Event detail popup/modal (if needed)
```

### Alert Endpoints

```
GET  /api/v1/alerts
     Purpose: Retrieve all active alerts
     Query Params:
       - status (optional: open, acknowledged, closed)
       - severity (optional: critical, high, medium, low)
       - limit (optional, default 20)
     Response: {"data": [...], "count": N, "timestamp": "..."}
     Frequency: Every 30 seconds
     Used For: Alert summary, recent alerts table

GET  /api/v1/alerts/{alert_id}
     Purpose: Get single alert details
     Response: Detailed alert object
     Frequency: On demand
     Used For: Alert detail modal
```

### Statistics/Analytics Endpoints

```
GET  /api/v1/statistics
     Purpose: Get aggregated statistics
     Query Params: days (optional)
     Response: {
       "total_events": N,
       "total_alerts": N,
       "threat_distribution": {...},
       "blocked_count": N,
       "top_sources": [...]
     }
     Frequency: Every 30 seconds
     Used For: Stat cards, charts

GET  /api/v1/statistics/threats
     Purpose: Threat level distribution
     Query Params: days (optional)
     Response: {"critical": N, "high": N, "medium": N, "low": N, "info": N}
     Frequency: Every 30 seconds
     Used For: Severity pie chart
```

### Summary of Consumed Endpoints

| Endpoint | Purpose | Frequency | Critical |
|----------|---------|-----------|----------|
| GET /health | System status | Page load | ✅ |
| GET /api/v1/health | Detailed health | 30s | ✅ |
| GET /api/v1/events | Event list | 30s | ✅ |
| GET /api/v1/alerts | Alert list | 30s | ✅ |
| GET /api/v1/statistics | Aggregated stats | 30s | ✅ |
| GET /api/v1/statistics/threats | Threat distribution | 30s | ✅ |
| GET /api/v1/events/{id} | Event details | On demand | ❌ |
| GET /api/v1/alerts/{id} | Alert details | On demand | ❌ |

**Total Endpoints Used: 8 out of 18 API endpoints**

---

## DATA FLOW DIAGRAM

### Request Flow (Text Format)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     MAYASEC FRONTEND (Browser)                       │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Dashboard Components                                       │    │
│  │                                                             │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │    │
│  │  │ Health Panel │  │ Stat Cards   │  │ Severity     │     │    │
│  │  │ (API Status) │  │ (Events/     │  │ Pie Chart    │     │    │
│  │  │              │  │  Alerts)     │  │              │     │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘     │    │
│  │                                                             │    │
│  │  ┌──────────────────────────────────────────────────────┐  │    │
│  │  │  Recent Alerts Table (Last 20)                       │  │    │
│  │  │  [ID] [Title] [Severity] [IP] [Status] [Time]       │  │    │
│  │  └──────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              ▲                                       │
│                              │                                       │
│              HTTP Requests (JSON, Every 30s)                        │
│                              │                                       │
└──────────────────────────────┼───────────────────────────────────────┘
                               │
                               ▼
        ┌──────────────────────────────────────────────────┐
        │     MAYASEC API SERVICE (Flask, Port 5000)       │
        │                                                  │
        │  GET /health                      ◄─────────┐   │
        │  GET /api/v1/health               │         │   │
        │  GET /api/v1/events               │ Routes  │   │
        │  GET /api/v1/alerts               │ Requests
        │  GET /api/v1/statistics           │         │   │
        │  GET /api/v1/statistics/threats   │         │   │
        │  GET /api/v1/events/{id}          ◄─────────┘   │
        │  GET /api/v1/alerts/{id}                        │
        │                                                  │
        │  [No Data Writes - Read-Only]                   │
        │  [No Modifications - Frontend Only Reads]       │
        │                                                  │
        └────────┬──────────────────────┬─────────────────┘
                 │                      │
         Data Queries           Status Checks
                 │                      │
                 ▼                      ▼
        ┌──────────────────────────────────────────────────┐
        │    MAYASEC CORE SERVICE (Port 5001)              │
        │    - Threat Analysis Engine                      │
        │    - Detection Pipeline                          │
        │    - Feature Extraction                          │
        │    - Correlation Engine                          │
        │                                                  │
        │  [No Direct Frontend Access]                     │
        │  [API Queries Only]                              │
        └────────────────┬─────────────────────────────────┘
                         │
                    Data Queries
                         │
                         ▼
        ┌──────────────────────────────────────────────────┐
        │    PostgreSQL Database (Port 5432)               │
        │                                                  │
        │  Tables:                                         │
        │  - security_logs      (50+ events in test)       │
        │  - alerts             (5+ alerts in test)        │
        │  - alert_rules        (5 rules)                  │
        │  - login_attempts                                │
        │  - honeypot_logs                                 │
        │  - network_flows                                 │
        │  - blocked_ips                                   │
        │  - alert_history                                 │
        │                                                  │
        │  [Read-Only Access from API]                     │
        │  [No Direct Frontend Access]                     │
        └──────────────────────────────────────────────────┘
```

### Data Flow Summary

```
FRONTEND                API                 CORE               DATABASE
(Read-Only)         (Routes/Queries)    (Analysis/Status)   (Persistent Storage)

User loads page
    │
    ├──→ GET /health ────→ [Check API] ──→ Returns status
    │
    ├──→ GET /api/v1/health ──→ [Verify services] ──→ Core health ──→ DB ping
    │
    ├──→ GET /api/v1/events ──→ [Query events] ──────────────→ SELECT * FROM security_logs
    │                                                            Returns: 5 events
    │
    ├──→ GET /api/v1/alerts ──→ [Query alerts] ──────────────→ SELECT * FROM alerts
    │                                                            Returns: 5 alerts
    │
    ├──→ GET /api/v1/statistics ──→ [Aggregate stats] ───────→ COUNT(*), GROUP BY, etc.
    │                                                            Returns: totals, distribution
    │
    └──→ GET /api/v1/statistics/threats ──→ [Threat breakdown] ──→ GROUP BY threat_level
                                                                    Returns: critical, high, medium, low

[Auto-Refresh Every 30 Seconds - Repeat Above]
```

---

## COMPONENT-TO-ENDPOINT MAPPING

### Dashboard Component: Health Status Panel

```
Component: System Health Indicator
├── Displays: API Status, Core Status, Database Status
├── Endpoints Called:
│   ├── GET /health              → API is running
│   ├── GET /api/v1/health       → Detailed service status
│   └── Refresh Rate: Every 30 seconds
├── Data Displayed:
│   ├── API: "✅ Healthy" or "❌ Down"
│   ├── Core: "✅ Ready" or "❌ Failed"
│   └── Database: "✅ Connected" or "❌ Disconnected"
└── User Interaction: View-only, no actions
```

### Dashboard Component: Event Metrics (Stat Cards)

```
Component: Total Events Card
├── Displays: Total event count (e.g., "5 Events")
├── Endpoints Called:
│   ├── GET /api/v1/statistics   → {"total_events": 5, ...}
│   └── Refresh Rate: Every 30 seconds
├── Data Transformation:
│   ├── Extract: response.total_events
│   ├── Format: Large number display
│   └── Color: Based on count (0 = gray, >100 = orange, >1000 = red)
└── User Interaction: Click to see event details table

Component: Total Alerts Card
├── Displays: Total alert count (e.g., "5 Alerts")
├── Endpoints Called:
│   ├── GET /api/v1/statistics   → {"total_alerts": 5, ...}
│   └── Refresh Rate: Every 30 seconds
├── Data Transformation:
│   ├── Extract: response.total_alerts
│   ├── Format: Large number display
│   └── Color: Based on count (critical/high = red, medium = orange)
└── User Interaction: Click to filter alerts by status
```

### Dashboard Component: Severity Distribution (Pie Chart)

```
Component: Alerts by Severity Pie Chart
├── Displays: Distribution of threat levels
├── Endpoints Called:
│   ├── GET /api/v1/statistics/threats → {"critical": 2, "high": 3, ...}
│   └── Refresh Rate: Every 30 seconds
├── Data Transformation:
│   ├── Extract: Each severity level and count
│   ├── Calculate: Percentages
│   ├── Map Colors: 
│   │   ├── critical = red (#ff0000)
│   │   ├── high = orange (#ff6600)
│   │   ├── medium = yellow (#ffaa00)
│   │   ├── low = blue (#0066ff)
│   │   └── info = gray (#cccccc)
│   └── Labels: "Critical (40%)", "High (60%)", etc.
└── User Interaction: Hover for tooltip, click to filter
```

### Dashboard Component: Recent Alerts Table

```
Component: Recent Alerts Table (Last 20)
├── Displays: Alert details in tabular format
├── Endpoints Called:
│   ├── GET /api/v1/alerts?limit=20 → List of alerts
│   └── GET /api/v1/alerts/{id}     → Individual alert details (on click)
│   └── Refresh Rate: Every 30 seconds
├── Table Columns:
│   ├── Alert ID
│   ├── Title
│   ├── Severity (color-coded badge)
│   ├── IP Address
│   ├── Status (open/acknowledged/closed)
│   └── Timestamp
├── Data Transformation:
│   ├── Sort: By timestamp DESC (newest first)
│   ├── Format: Dates to human-readable (e.g., "2 min ago")
│   ├── Severity Badge: Color-coded
│   └── Status Badge: Icon + text
└── User Interaction:
    ├── Click row → Show alert detail modal
    ├── Sort columns → Frontend sort (not API call)
    └── Pagination: Show 20 per page (if more exist)
```

---

## DATA REFRESH STRATEGY

### Polling Schedule

```
┌─ Page Load ─────────┐
│                     │
│  ┌─────────────────┴─────────────────┐
│  │                                   │
│  ▼                                   ▼
│ Call /health              Call /api/v1/health
│ + /api/v1/events          + /api/v1/statistics
│ + /api/v1/alerts          + /api/v1/statistics/threats
│
│  ┌─────────────────────────────────┐
│  │   Initial Dashboard Render      │
│  └─────────────────────────────────┘
│
│  ┌─────────── Wait 30 Seconds ──────────┐
│  │                                       │
│  ▼                                       ▼
│ Refresh All Data              User scrolling/idle
│ (Poll all endpoints)          (No refresh during interaction)
│
│  └─────────────────────────────────────┘
│   (Repeat every 30s indefinitely)
│
└─ User Navigates Away ──────────────┘
   (Stop polling, cleanup)
```

### Caching Strategy (Frontend Only)

```
Cache Level: Browser Memory
├── Current Data: All API responses stored in state
├── Last Updated: Timestamp tracked per endpoint
├── Stale Data: 30 second TTL
├── On Refresh:
│   ├── If <30s old: Use cached version
│   ├── If >30s old: Fetch fresh from API
│   └── Show loading spinner during fetch
└── On Failure: Show cached + "Data may be outdated" warning
```

---

## ERROR HANDLING & EDGE CASES

### API Connection Error
```
Scenario: API at :5000 is unreachable
├── Frontend Displays:
│   ├── Health Panel: "❌ API Unreachable"
│   ├── Data Panels: "Unable to load data"
│   ├── Table: Empty with error message
│   └── Severity: Red banner at top
├── Auto-Retry: Every 10 seconds
└── User Action: Manual refresh button available
```

### Core Service Down (But API Up)
```
Scenario: API responds but Core is not healthy
├── Frontend Displays:
│   ├── Health Panel: "⚠️  Core Service Offline"
│   ├── Event/Alert data: Stale (last known values)
│   ├── Warning: "Some data may be outdated"
│   └── Severity: Yellow/orange warning
├── Impact: Statistics still show, but analysis halted
└── User Action: None needed (system recovers auto)
```

### Database Connection Lost
```
Scenario: API can't connect to database
├── Frontend Displays:
│   ├── Health Panel: "❌ Database Offline"
│   ├── All data panels: "No data available"
│   └── Severity: Red banner + critical alert
├── Impact: Complete dashboard freeze (no data to show)
└── User Action: Wait for DBA/ops to restore DB
```

### No Events/Alerts (Empty State)
```
Scenario: Database is healthy but no data yet
├── Frontend Displays:
│   ├── Stat Cards: "0 Events", "0 Alerts"
│   ├── Pie Chart: Empty or message
│   ├── Table: "No alerts found" placeholder
│   └── Severity: Green (this is normal for fresh start)
├── Impact: Dashboard functions normally, just empty
└── User Action: Wait for events to be ingested
```

---

## FRONTEND TECH STACK (To Be Determined)

### Framework Options (TBD)

```
JavaScript Frameworks (Choose One):
├── React
│   ├── Pros: Large ecosystem, component reuse, state management
│   ├── Cons: Build step required, learning curve
│   └── Libraries: React Query, Recharts for charts
│
├── Vue
│   ├── Pros: Gentle learning curve, good reactivity
│   ├── Cons: Smaller ecosystem than React
│   └── Libraries: Vite for build, Chart.js for charts
│
└── Plain HTML/CSS/JS
    ├── Pros: No build step, minimal dependencies
    ├── Cons: More manual DOM management
    └── Libraries: Fetch API, Chart.js

UI Component Library (TBD):
├── Tailwind CSS: Utility-first, light, fast
├── Bootstrap: Full-featured, pre-built components
├── Material UI: Professional, accessible
└── Custom CSS: Simple, zero dependencies

Chart Library (TBD):
├── Recharts (React-native)
├── Chart.js (Framework agnostic)
├── D3.js (Powerful, complex learning curve)
└── ECharts (Feature-rich, large bundle)
```

---

## NETWORK & SECURITY

### Cross-Origin Requests (CORS)

```
Frontend Origin: http://localhost:3000 (assumed)
API Origin:      http://localhost:5000

CORS Requirements:
├── Frontend will make requests from :3000
├── API at :5000 must allow :3000 in CORS headers
├── Current Status: Unknown (may need docker-compose update)
└── Solution: Ensure API returns CORS headers or reverse proxy
```

### Authentication

```
Current: None (No login system)
├── Frontend: No auth headers sent
├── API: No validation of user identity
├── Database: No row-level security
└── Assumption: Deployment in trusted network only
```

### Data Privacy

```
All data displayed is aggregated/summary level:
├── No sensitive personal information
├── No plaintext passwords shown
├── IP addresses visible (security data)
├── Alert descriptions shown (non-sensitive)
└── Safe for internal network viewing
```

---

## SUMMARY

### Frontend is:
- ✅ Read-only visualization
- ✅ API consumer only (no direct DB)
- ✅ Single-page dashboard
- ✅ Auto-refreshing (30s interval)
- ✅ Status-aware (shows service health)
- ✅ Error-resilient (graceful degradation)

### Frontend is NOT:
- ❌ Business logic executor
- ❌ Data modifier
- ❌ User management system
- ❌ Configuration interface
- ❌ Multi-page application

### Ready for Implementation:
1. Choose frontend framework
2. Create page layout/components
3. Implement API client
4. Implement data refresh logic
5. Add error handling
6. Style and polish
7. Deploy as Docker service


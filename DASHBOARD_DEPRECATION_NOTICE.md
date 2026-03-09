# MAYASEC Dashboard Deprecation Notice

**Status:** Current dashboard UI components marked for deprecation  
**Effective:** Immediately  
**Migration Path:** New SOC-style event console UI (TBD)  

---

## Components Marked for Discard

### 1. HealthPanel Component
**File:** `frontend/src/components/HealthPanel.js`  
**File:** `frontend/src/components/HealthPanel.css`  

**Classification:** Static Metric Card  
**Data Source:** Polling-based (`pollInterval = 30000ms`)  
**REST Endpoint:** `GET /api/v1/health`  

**Current Functionality:**
- Displays system health status
- Shows overall status indicator (🟢 Healthy / 🔴 Unhealthy)
- Polls every 30 seconds
- Static card layout with metric display

**Deprecation Reason:** 
- Static metric cards not suitable for SOC-style event-driven architecture
- Polling-based updates conflict with real-time WebSocket streaming
- Health status should be integrated into header/connection indicator

**Action:** 
- ❌ Do NOT enhance
- ❌ Do NOT refactor
- ❌ Do NOT apply styling updates
- ✅ Leave as-is for backward compatibility
- ✅ Mark code with deprecation comments

---

### 2. StatsPanel Component
**File:** `frontend/src/components/StatsPanel.js`  
**File:** `frontend/src/components/StatsPanel.css`  

**Classification:** Polling-based Summary Card  
**Data Source:** Polling-based (`pollInterval = 30000ms`)  
**REST Endpoints:** 
- `GET /api/v1/events`
- `GET /api/v1/alerts`

**Current Functionality:**
- Displays total event counts
- Shows alert summary statistics
- Calculates severity breakdown
- Displays threat level distribution
- Polls every 30 seconds

**Deprecation Reason:**
- Summary statistics based on stale polling data
- Does not support real-time threat escalation visualization
- Cannot show live event stream context
- Metric cards are legacy dashboard pattern

**Action:**
- ❌ Do NOT enhance
- ❌ Do NOT refactor
- ❌ Do NOT apply styling updates
- ✅ Leave as-is for backward compatibility
- ✅ Mark code with deprecation comments

---

### 3. AlertsPanel Component
**File:** `frontend/src/components/AlertsPanel.js`  
**File:** `frontend/src/components/AlertsPanel.css`  

**Classification:** Polling-based Summary List  
**Data Source:** Polling-based (`pollInterval = 30000ms`)  
**REST Endpoint:** `GET /api/v1/alerts?limit=20`  

**Current Functionality:**
- Displays recent alerts (last 10-20)
- Shows alert severity classification
- Displays timestamps and details
- Polls every 30 seconds
- Limited to fixed number of items

**Deprecation Reason:**
- Static list view does not support live event stream
- Polling-based updates create latency in threat visibility
- Alert management should be driven by event stream
- Cannot show real-time escalation patterns

**Action:**
- ❌ Do NOT enhance
- ❌ Do NOT refactor
- ❌ Do NOT apply styling updates
- ✅ Leave as-is for backward compatibility
- ✅ Mark code with deprecation comments

---

## Components to Retain (Event-Driven)

### LiveEventFeed Component
**File:** `frontend/src/components/LiveEventFeed.js`  
**File:** `frontend/src/components/LiveEventFeed.css`  

**Classification:** Real-time Event Stream  
**Data Source:** WebSocket-driven (Socket.IO)  
**Update Pattern:** Event-driven (no polling)  

**Status:** ✅ ACTIVE - Core component for new SOC console  
**Action:** Continue enhancement and refinement

---

## Deprecation Code Markers

Add deprecation notices to all marked components:

```javascript
/**
 * @deprecated This component is deprecated and will be removed in MAYASEC 5.0
 * Reason: Static metric cards and polling-based updates not suitable for 
 *         SOC-style event-driven architecture
 * Migration: Use new SOC event console UI (coming soon)
 * Status: UNMAINTAINED - No style or functionality updates
 */
```

---

## Implementation Tasks

### ✅ COMPLETED
- [x] Identify components for deprecation
- [x] Classify by pattern (static metrics, polling summaries)
- [x] Document discard list
- [x] Confirm no styling work will be done

### ⏳ UPCOMING
- [ ] Add deprecation comments to component code
- [ ] Add deprecation comments to CSS files
- [ ] Update App.js to note deprecated component usage
- [ ] Plan new SOC event console UI architecture
- [ ] Design event-driven data flow for replacements
- [ ] Create new dashboard layout specification

---

## Summary Table

| Component | Type | Data Pattern | Status | Action |
|-----------|------|-------------|--------|--------|
| HealthPanel | Static Metric | Polling (30s) | 🔴 DEPRECATED | Do not modify |
| StatsPanel | Summary Card | Polling (30s) | 🔴 DEPRECATED | Do not modify |
| AlertsPanel | Summary List | Polling (30s) | 🔴 DEPRECATED | Do not modify |
| LiveEventFeed | Event Stream | WebSocket | ✅ ACTIVE | Continue development |

---

## Styling Work Status

**Confirmation: NO styling work will be performed on deprecated components**

The following components will receive NO further enhancements:
- ❌ HealthPanel.css - UNMAINTAINED
- ❌ StatsPanel.css - UNMAINTAINED  
- ❌ AlertsPanel.css - UNMAINTAINED

Focus will shift exclusively to:
- ✅ LiveEventFeed.css - ACTIVE DEVELOPMENT
- ✅ New SOC console components (to be created)

---

## Migration Path

Once new SOC event console components are ready:

1. Create new component structure
2. Migrate event-driven logic from LiveEventFeed
3. Build replacement UI components
4. Remove deprecated components from App.js
5. Delete deprecated files
6. Update documentation

---

**Last Updated:** January 15, 2026  
**Next Review:** Upon new SOC console specification completion

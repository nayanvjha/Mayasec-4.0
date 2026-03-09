# MAYASEC Architecture Review: OS Coupling & Containerization Gaps

**Analysis Date:** 15 January 2026  
**Current Status:** Monolithic, OS-coupled, Python-executable only  
**Target Status:** Docker + Docker Compose, microservices, OS-agnostic  

---

## Executive Summary

The current Mayasec implementation is **fundamentally incompatible** with the required Docker-first, OS-agnostic architecture. The codebase exhibits:

- **8 critical OS-coupled assumptions** (hardcoded paths, filesystem dependencies)
- **4 database coupling issues** (SQLite monolithic storage)
- **3 external service dependencies** without containerization
- **6 runtime separation problems** (monolithic app, no microservice boundaries)
- **5 configuration management gaps** (env vars, no unified config layer)

---

## PART 1: OS-COUPLED ASSUMPTIONS

### 1.1 Hardcoded Filesystem Paths (CRITICAL)

**Location:** `app.py`, `suricata_forwarder.py`, `security_monitor.py`

| Issue | Current Code | Problem | Impact |
|-------|--------------|---------|--------|
| **Suricata EVE path** | `"/var/log/suricata/eve.json"` | Unix-only path | Windows/macOS fail silently |
| **Database location** | `"security_logs.db"` relative path | Working directory dependent | Container volume mismatch |
| **Log file location** | `"security_monitor.log"` relative path | CWD-dependent, not idempotent | Lost logs in containers |
| **Config file paths** | `"forwarder-config.example.json"` relative | No standard config dir | Cannot use /etc/mayasec or Windows equiv |
| **Gemini API key** | `.env` file (dotenv) | Assumes local filesystem | Breaks in container secrets model |

**Code Examples:**
```python
# app.py:27
SURICATA_LOG_PATH = "/var/log/suricata/eve.json"

# suricata_forwarder.py:39
DEFAULT_SURICATA_LOG_PATH = "/var/log/suricata/eve.json"

# security_monitor.py:29
handler = logging.FileHandler('security_monitor.log')
```

**Docker-specific problem:** Containers cannot assume `/var/log/suricata/` exists. Must use volume mounts with explicit targets.

---

### 1.2 Direct File I/O Without Abstraction (CRITICAL)

**Location:** `app.py:load_suricata_logs()`, `suricata_forwarder.py:FileTailer`

```python
# app.py:50-56
def load_suricata_logs(max_lines=2000):
    if not os.path.exists(SURICATA_LOG_PATH):
        return []
    
    logs = deque(maxlen=max_lines)
    with open(SURICATA_LOG_PATH, "r") as f:
        logs.extend(f)
```

**Problems:**
- No abstraction layer for different log sources
- Tight coupling to filesystem operations
- Cannot switch sources at runtime (file vs. HTTP vs. Kafka)
- File rotation detection via inode comparison (Unix-specific)
- No error handling for file encoding mismatches

**Container implication:** Cannot gracefully handle missing volumes at startup.

---

### 1.3 Relative Database Paths (CRITICAL)

**Location:** `app.py:25`, `security_monitor.py:36`

```python
# app.py:25
DATABASE_PATH = 'security_logs.db'

# security_monitor.py:36
self.conn = sqlite3.connect('security_logs.db', check_same_thread=False)
```

**Problems:**
- Both hardcode relative path → database location undefined
- No persistence strategy specified
- Duplicate DB initialization in two modules
- SQLite not suitable for containerized multi-replica deployments

**Docker implications:**
- Requires explicit volume mount with correct relative path
- No health checks for DB availability
- No DB initialization ordering in compose

---

## PART 2: MONOLITHIC DATABASE COUPLING

### 2.1 SQLite as Primary Storage (ARCHITECTURAL)

**Location:** `app.py` (entire app), `security_monitor.py`, `log_ingestion.py`

**Current Schema:**
```sql
-- security_logs (9 columns, primary event store)
-- honeypot_logs (7 columns)
-- blocked_ips (5 columns)
-- login_attempts (10 columns)
-- users (5 columns)
```

**Problems:**
1. **Single point of failure** - No replication, backup, or failover
2. **Not horizontally scalable** - SQLite locks prevent concurrent writes
3. **No query optimization** - Full table scans for aggregations
4. **Monolithic schema** - All modules directly hit same DB
5. **No schema versioning** - ALTER TABLE wrapped in try-except (fragile)

**Evidence in code:**
```python
# app.py:265-268 (direct DB connection everywhere)
def authenticate_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT password_hash FROM users WHERE username = ? AND is_active = 1', (username,))
```

**Container implications:**
- Cannot run multiple app replicas (SQLite file locks)
- Cannot scale horizontally
- Storage must be PersistentVolume (single-node only)
- No zero-downtime upgrades possible

---

### 2.2 Schema Migration Strategy Insufficient

**Location:** `app.py:120-200` (init_database function)

```python
# app.py:145-152 (unsafe migration)
try:
    cursor.execute('ALTER TABLE security_logs ADD COLUMN sensor_id TEXT')
except:
    pass  # Column likely exists
```

**Problems:**
- Silent failures hide schema inconsistencies
- No versioning table to track migration state
- No rollback strategy
- Assumes single schema version at runtime

**Multi-container problem:** If containers start before DB is ready, schema might be partially initialized.

---

## PART 3: EXTERNAL DEPENDENCIES (NOT CONTAINERIZED)

### 3.1 Gemini AI API Integration (EXTERNAL)

**Location:** `threat_intel.py:1-61`

```python
# threat_intel.py:7
GEMINI_KEY = os.getenv("GEM_API_KEY")

def analyze_with_gemini(event: dict):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
```

**Problems:**
1. **Hard external dependency** - Cannot run without API key
2. **No fallback logic** - If API is down, entire analysis fails
3. **No timeout handling** - Sync request blocks
4. **Credential in environment** - Not following container secrets best practices
5. **Called from hot path** - Login attempt analysis blocks response

**Container implications:**
- Network egress required (may be blocked)
- Rate limiting not handled
- Retry logic missing
- No circuit breaker

---

### 3.2 Flask Development Server in Production

**Location:** `app.py:end` (implied entry point)

```python
# Typical Flask startup:
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8000)
```

**Problems:**
1. Flask dev server not production-grade
2. No WSGI server (gunicorn) integration
3. No graceful shutdown handling
4. No health check endpoint

**Container implications:**
- Cannot perform rolling updates
- No readiness probes
- Graceful termination broken (instant kill)

---

### 3.3 No API Rate Limiting or Load Balancing

**Location:** `app.py` routes (no middleware)

**Problems:**
- POST `/api/ingest/event` has no rate limiting
- No request validation middleware
- No logging of all requests
- No metrics collection

---

## PART 4: RUNTIME SEPARATION FAILURES

### 4.1 Monolithic Application (ARCHITECTURAL)

**Current structure:**
```
app.py (884 lines, mixed concerns):
├── Flask routes (30 routes)
├── Database operations (direct SQLite)
├── Authentication logic
├── Log file reading (/var/log/suricata/eve.json)
├── Threat analysis coordination
└── UI rendering (Jinja2 templates)
```

**Problems:**
1. **Single process, single language** - Can't scale individual concerns
2. **Synchronous everything** - Blocking on file I/O, API calls
3. **No clear service boundaries** - Which code does what?
4. **Tight coupling** - Change one thing, break others

**Evidence:**
```python
# app.py:322-370 (login route is 48 lines doing too much)
@app.route('/login', methods=['POST'])
def login():
    # 1. Extract request data
    # 2. Call Gemini AI analysis (SYNC, BLOCKING)
    # 3. Log to database
    # 4. Check threat level
    # 5. Redirect or render template
```

---

### 4.2 Suricata Forwarder as Separate Script

**Location:** `suricata_forwarder.py` (532 lines, standalone)

**Problems:**
1. **Separate runtime required** - Cannot share container with core app
2. **Duplicate ingestion logic** - EVE parsing replicated
3. **No shared configuration** - Different env var prefix (MAYASEC_ vs none)
4. **Filesystem coupling** - Requires access to `/var/log/suricata/eve.json`

**Current design:**
```
Suricata (on sensor host)
    ↓ eve.json
suricata_forwarder.py (separate process)
    ↓ HTTP POST
mayasec app.py
    ↓ sqlite3
security_logs.db
```

**Container problem:** If forwarder and app in separate containers, forwarder cannot see eve.json unless Suricata also containerized and volume-mounted.

---

### 4.3 Security Monitor as Background Thread

**Location:** `security_monitor.py` (131 lines)

```python
class SecurityMonitor:
    def start_monitoring(self):
        while True:
            logs = self.fetch_recent_logs(hours=1)  # Method doesn't exist!
            if logs:
                summary = analyze_with_gemini({"recent_logs": logs})
```

**Problems:**
1. **Reference to non-existent method** - `fetch_recent_logs()` undefined
2. **Blocking loop in main process** - Prevents graceful shutdown
3. **No error recovery** - If Gemini fails, loop continues
4. **Hardcoded sleep (3 seconds)** - Inefficient wakeup

**Container implications:**
- Thread prevents SIGTERM handling
- No way to gracefully shutdown within 30s default timeout
- Zombie processes if container is killed

---

## PART 5: CONFIGURATION MANAGEMENT GAPS

### 5.1 No Unified Configuration Layer

**Current approach:**
```python
# app.py
DATABASE_PATH = 'security_logs.db'  # Hardcoded
SURICATA_LOG_PATH = "/var/log/suricata/eve.json"  # Hardcoded
USE_LOCAL_LOGS = os.getenv('USE_LOCAL_LOGS', 'true')  # Env var

# suricata_forwarder.py
DEFAULT_SURICATA_LOG_PATH = "/var/log/suricata/eve.json"  # Duplicate hardcoded
DEFAULT_API_URL = "http://localhost:8000"  # Hardcoded

# threat_intel.py
GEMINI_KEY = os.getenv("GEM_API_KEY")  # Env var only

# .env file (dotenv)
# GEM_API_KEY=secret...
```

**Problems:**
1. **No config schema** - No validation of required vars
2. **Scattered defaults** - Same values defined in 3 files
3. **No type safety** - All env vars are strings
4. **No documentation** - Required vars not listed anywhere
5. **Dotenv not containerized** - Containers don't have .env files

---

### 5.2 Missing Health Check Endpoints

**Location:** None (doesn't exist)

**Problems:**
- Docker Compose needs health checks for `depends_on`
- No `/health` or `/ready` endpoint
- App startup not verified before routing traffic
- DB connectivity not tested

---

## PART 6: REQUIRED MICROSERVICE BOUNDARIES

### 6.1 Proposed Service Decomposition

**Current monolith:**
```
app.py (884 lines)
├── HTTP API (routes)
├── Log ingestion
├── Database operations
├── Authentication
├── Web UI
└── Background analysis
```

**Required target:**
```
mayasec-ingestor
├── POST /api/ingest/event
├── Validate + normalize
└── Publish to queue (Kafka/Redis)

mayasec-core
├── Consume events
├── Run threat analysis
├── Apply correlation rules
└── Publish enriched events

mayasec-storage
├── PostgreSQL database
├── Schema versioning
├── Replication/backup
└── Query API

mayasec-api
├── REST API for queries
├── Authentication + authz
├── Rate limiting
└── Metrics/observability

mayasec-ui
├── React/Vue frontend
├── Static files
└── Browser security
```

---

### 6.2 Event Flow Redesign Required

**Current:**
```
Ingest → Validate → Analyze (Gemini) → Store (SQLite) → Return
```

**Required (async):**
```
Ingest
  ↓ (validate, normalize)
Event Queue (Kafka/Redis)
  ↓
Analysis Worker (mayasec-core)
  ↓ (enrich, correlate)
Event Queue (enriched)
  ↓
Storage (PostgreSQL)
  ↓
Query API (mayasec-api)
  ↓
UI (React)
```

---

## PART 7: DATABASE MIGRATION STRATEGY

### 7.1 SQLite → PostgreSQL (MANDATORY)

**Why:**
- SQLite cannot be replicated in Docker
- No connection pooling
- No support for horizontal scaling
- File locking prevents concurrent writes

**Impact:**
- All DB initialization code must change
- Connection strings must be configurable
- Schema versioning must be implemented (Alembic/Flyway)
- Data migration required for existing deployments

---

## PART 8: CONTAINERIZATION GAPS

### 8.1 No Dockerfile

**Missing:**
- Python base image specification
- Dependency layer (requirements.txt separation)
- Multi-stage build for optimization
- Non-root user
- Health check CMD

---

### 8.2 No Docker Compose

**Missing:**
- Service definitions for 5 containers
- Volume mounts for persistent data
- Environment variable configuration
- Health checks and depends_on
- Network isolation
- Resource limits

---

### 8.3 No .dockerignore

**Problems:**
- Build includes test files, __pycache__, .venv
- Image bloat (test dependencies included)
- Increased attack surface

---

## SUMMARY: REFACTORING PRIORITY

### TIER 1 (BLOCKERS - Must fix before Docker)
1. **Remove all hardcoded paths** → Make configurable via env vars or ConfigMaps
2. **Extract database layer** → Abstract DB operations into service
3. **Remove file-based Suricata reading** → Move to ingestor microservice
4. **Fix security_monitor.py** → Either fix `fetch_recent_logs()` or remove
5. **Create health check endpoint** → Required for K8s/Docker Compose

### TIER 2 (ARCHITECTURAL - Container-first design)
6. **Migrate SQLite → PostgreSQL** → Multi-container requirement
7. **Extract mayasec-ingestor service** → Dedicated event API
8. **Extract mayasec-core service** → Threat analysis worker
9. **Create unified config layer** → Environment variable schema
10. **Implement schema versioning** → Database migrations with Alembic

### TIER 3 (OPERATIONAL - Production readiness)
11. **Add WSGI server** (gunicorn) → Replace Flask dev server
12. **Implement graceful shutdown** → Signal handling
13. **Add rate limiting** → Protect /api/ingest/event
14. **Add observability** → Logging, metrics, tracing
15. **Create docker-compose.yml** → Single canonical deployment

### TIER 4 (HARDENING)
16. **Remove Gemini hard dependency** → Add fallback analysis
17. **Add request validation** → JSON schema validation
18. **Implement API authentication** → Token-based auth
19. **Add database backup strategy** → Automated backups
20. **Create README for Docker deployment** → User-facing docs

---

## CRITICAL FILES TO MODIFY

```
MUST MODIFY:
- app.py (884 lines → split across services)
- threat_intel.py (remove hard Gemini dependency)
- security_monitor.py (fix or remove)
- log_ingestion.py (move to ingestor service)

MUST CREATE:
- Dockerfile (for each service)
- docker-compose.yml (orchestration)
- .dockerignore (build optimization)
- requirements.txt (main + per-service)
- config_schema.py (unified config)
- database_init.py (schema versioning with Alembic)
- health_check.py (readiness/liveness probes)

MUST MODIFY/CREATE:
- QUICKSTART.md (Docker Compose instructions)
- README.md (architecture diagram, Docker instructions)
- Architecture docs (this analysis → living doc)
```

---

## ESTIMATED SCOPE

| Category | Count | Effort | Risk |
|----------|-------|--------|------|
| Code refactoring | 8 files | 40 hours | HIGH |
| New microservices | 5 services | 60 hours | HIGH |
| Database migration | SQLite→PG | 20 hours | CRITICAL |
| Docker/Compose | 3 files | 10 hours | MEDIUM |
| Testing/validation | 20 tests | 30 hours | HIGH |
| Documentation | 5 docs | 10 hours | LOW |
| **TOTAL** | | **170 hours** | **HIGH** |

---

## RECOMMENDATION

**Do NOT write code yet.** The architecture is fundamentally incompatible with the requirements. Proceed with:

1. **Phase 0 (Planning):** Approve this document. Define microservice contracts.
2. **Phase 1 (Foundation):** Create Dockerfiles, docker-compose.yml, PostgreSQL schema
3. **Phase 2 (Services):** Extract ingestor, core, API services
4. **Phase 3 (Integration):** Connect services, implement health checks
5. **Phase 4 (Hardening):** Add observability, authentication, rate limiting

**Blockers before code:**
- [ ] Microservice contracts defined (API specs)
- [ ] PostgreSQL schema designed
- [ ] Configuration schema approved
- [ ] Deployment architecture diagram reviewed


## CORRELATION_ID QUICK REFERENCE - BACKEND INTEGRATION

**TL;DR**: Use `CorrelationEngine` to generate correlation_id for every event before storage.

---

## 1-MINUTE SETUP

### Install Migration
```bash
# Add correlation_id column to all event tables
psql mayasec < migrations/003_add_correlation_id.sql
```

### Import Engine
```python
from correlation_engine import CorrelationEngine

engine = CorrelationEngine()
```

### Generate ID
```python
# When creating event
event = {
    'event_id': str(uuid.uuid4()),
    'source_ip': '10.0.0.5',
    'destination_ip': '192.168.1.1',
    'destination_port': 22,
    'timestamp': datetime.utcnow().isoformat(),
    'event_type': 'port_scan'
}

# Generate correlation_id
event['correlation_id'] = engine.generate_correlation_id(event)

# Store event with correlation_id
db.insert('security_logs', event)
```

---

## FULL WORKFLOW

### Core Service (Event Creation)

```python
from correlation_engine import CorrelationEngine

class EventProcessor:
    def __init__(self):
        self.correlation_engine = CorrelationEngine()
    
    def process_event(self, raw_event: Dict) -> Dict:
        """Process raw event and prepare for storage"""
        
        # Normalize event
        event = {
            'event_id': str(uuid.uuid4()),
            'event_type': raw_event['type'],
            'timestamp': raw_event.get('timestamp', datetime.utcnow()).isoformat(),
            'source_ip': raw_event['src_ip'],
            'destination_ip': raw_event.get('dst_ip', '0.0.0.0'),
            'destination_port': raw_event.get('dst_port', 0),
        }
        
        # CRITICAL: Generate correlation_id before storage
        event['correlation_id'] = self.correlation_engine.generate_correlation_id(event)
        
        # Log for audit trail
        logger.info(f"Generated correlation for {event['event_id']}: {event['correlation_id']}")
        
        # Store in database
        self.repository.create_event(event, threat_analysis={})
        
        # Emit for real-time dashboard
        requests.post('http://api:5000/api/v1/emit-event', json=event)
        
        return event
```

### Event from Log File

```python
# Example: Processing Suricata alert
raw_alert = {
    'timestamp': '2024-01-15T08:15:00.123Z',
    'src_ip': '10.0.0.5',
    'dst_ip': '192.168.1.1',
    'dst_port': 22,
    'alert': {'signature': 'SSH Port Scan'}
}

event = normalize_alert(raw_alert)
event['correlation_id'] = engine.generate_correlation_id(event)
db.insert(event)
```

### Event from API

```python
# REST endpoint receiving event
@app.route('/api/v1/events', methods=['POST'])
def ingest_event():
    data = request.get_json()
    
    event = {
        'event_id': str(uuid.uuid4()),
        'source_ip': data['source_ip'],
        'destination_ip': data.get('destination_ip', '0.0.0.0'),
        'destination_port': data.get('port', 0),
        'timestamp': datetime.utcnow().isoformat(),
        'event_type': data['event_type']
    }
    
    # Generate correlation_id
    event['correlation_id'] = correlation_engine.generate_correlation_id(event)
    
    # Store
    db.insert('security_logs', event)
    
    # Emit to dashboard
    requests.post('http://api:5000/api/v1/emit-event', json=event)
    
    return jsonify({'event_id': event['event_id'], 'correlation_id': event['correlation_id']})
```

---

## CORRELATION ALGORITHM

### How It Works

1. **Extract from event**:
   - source_ip (attacker)
   - destination_ip:port (target)
   - timestamp

2. **Query database**:
   ```sql
   SELECT correlation_id FROM security_logs
   WHERE source_ip = %s
     AND destination_ip = %s
     AND destination_port = %s
     AND timestamp BETWEEN (now - 5min) AND (now + 5min)
   ```

3. **If found**: Use existing correlation_id
   - All related events get same ID

4. **If not found**: Generate new correlation_id
   - Format: `corr_YYYYMMDD_SRCIP_DSTIP_PORT_HASH`
   - Same format for same source+dest → idempotent

### Examples

```
Event 1: 10.0.0.5 → 192.168.1.1:22 at 08:15:00
  → correlation_id = "corr_20240115_10000005_192168110122_abc12"

Event 2: 10.0.0.5 → 192.168.1.1:22 at 08:15:30 (30s later, same target)
  → correlation_id = "corr_20240115_10000005_192168110122_abc12" ✓ SAME!

Event 3: 10.0.0.5 → 192.168.1.2:22 at 08:15:35 (different target)
  → correlation_id = "corr_20240115_10000005_192168110122_xyz99" ✗ DIFFERENT

Event 4: 10.0.0.6 → 192.168.1.1:22 at 08:16:00 (different attacker)
  → correlation_id = "corr_20240115_10000006_192168110122_def45" ✗ DIFFERENT
```

---

## IMMUTABLE FIELDS

Once generated, **NEVER MODIFY** correlation_id:

```python
# ❌ WRONG - Don't change correlation_id after creation
event['correlation_id'] = 'some_other_id'  # NEVER!

# ❌ WRONG - Don't re-generate for existing event
event['correlation_id'] = engine.generate_correlation_id(event)  # WRONG if already set!

# ✅ RIGHT - Use guarantee_correlation_id for safety checks only
event = engine.guarantee_correlation_id(event)  # Only adds if missing
```

---

## DATABASE QUERIES

### Get All Events in Attack

```sql
SELECT * FROM security_logs
WHERE correlation_id = 'corr_20240115_10000005_192168110122_abc12'
ORDER BY timestamp ASC;
```

### Count Events by Correlation

```sql
SELECT correlation_id, COUNT(*) as event_count
FROM security_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY correlation_id
ORDER BY event_count DESC;
```

### Find Correlations for IP

```sql
SELECT DISTINCT correlation_id
FROM security_logs
WHERE ip_address = '10.0.0.5'
  AND timestamp > NOW() - INTERVAL '1 hour'
ORDER BY timestamp DESC;
```

---

## TESTING

### Test 1: Same event = Same ID

```python
engine = CorrelationEngine()

event1 = {
    'source_ip': '10.0.0.5',
    'destination_ip': '192.168.1.1',
    'destination_port': 22,
    'timestamp': '2024-01-15T08:15:00Z'
}

id1 = engine.generate_correlation_id(event1)
id2 = engine.generate_correlation_id(event1)

assert id1 == id2, "Same event should always generate same ID"
print(f"✓ Deterministic: {id1}")
```

### Test 2: Different target = Different ID

```python
event1 = {'source_ip': '10.0.0.5', 'destination_ip': '192.168.1.1', 'destination_port': 22}
event2 = {'source_ip': '10.0.0.5', 'destination_ip': '192.168.1.2', 'destination_port': 22}

id1 = engine.generate_correlation_id(event1)
id2 = engine.generate_correlation_id(event2)

assert id1 != id2, "Different targets should generate different IDs"
print(f"✓ Different targets: {id1} vs {id2}")
```

### Test 3: API includes ID in response

```bash
curl -X POST http://api:5000/api/v1/emit-event \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt_test",
    "source_ip": "10.0.0.5",
    "destination_ip": "192.168.1.1",
    "destination_port": 22,
    "event_type": "port_scan"
  }'

# Response should include:
# {
#   "status": "emitted",
#   "event_id": "evt_test",
#   "correlation_id": "corr_20240115_10000005_192168110122_abc12"
# }
```

### Test 4: WebSocket includes ID

```javascript
// Browser console
const socket = io('http://api:5000');

socket.on('new_event', (message) => {
  const event = message.data;
  console.log('✓ Event:', event.event_id);
  console.log('✓ Correlation:', event.correlation_id);
  
  if (!event.correlation_id) {
    console.error('✗ MISSING correlation_id!');
  }
});
```

---

## COMMON PATTERNS

### Pattern 1: During Threat Analysis

```python
# Core service processes event
raw_event = parse_suricata_log(log_line)

# Normalize
event = {
    'event_id': str(uuid.uuid4()),
    'source_ip': raw_event['src_ip'],
    'destination_ip': raw_event['dst_ip'],
    'destination_port': raw_event['dst_port'],
    'timestamp': raw_event['timestamp'],
    'event_type': classify_event(raw_event),
}

# BEFORE threat analysis: Generate correlation_id
event['correlation_id'] = correlation_engine.generate_correlation_id(event)

# Threat analysis can use correlation_id for context
threat_analysis = analyze_threat(event)

# Persist with correlation_id
repository.create_event(event, threat_analysis)

# Emit to dashboard
emit_to_websocket(event)
```

### Pattern 2: Batch Ingestion

```python
# Process multiple events
events = parse_log_batch(log_file)

for raw_event in events:
    event = normalize(raw_event)
    
    # Generate correlation_id
    event['correlation_id'] = correlation_engine.generate_correlation_id(event)
    
    # Batch insert
    batch.append(event)

# Insert all at once
db.insert_batch('security_logs', batch)
```

### Pattern 3: Retroactive Correlation

```python
# If you have old events without correlation_id:
old_events = db.query('SELECT * FROM security_logs WHERE correlation_id IS NULL')

for event in old_events:
    # Don't re-generate! Use existing pattern
    # This is a one-time migration
    event['correlation_id'] = correlation_engine.generate_correlation_id(event)
    
    # Update once
    db.update('security_logs', 
              where={'event_id': event['event_id']},
              correlation_id=event['correlation_id'])
```

---

## DEPLOYMENT CHECKLIST

- [ ] Run migration: `migrations/003_add_correlation_id.sql`
- [ ] Copy `correlation_engine.py` to backend
- [ ] Update Core service to call `correlation_engine.generate_correlation_id()`
- [ ] Update API `mayasec_api.py` with new imports and methods
- [ ] Test: Generate correlation_id for sample events
- [ ] Test: Verify same event = same ID
- [ ] Test: Verify WebSocket includes correlation_id
- [ ] Deploy Core service
- [ ] Deploy API service
- [ ] Monitor logs: Check for correlation_id in emission logs
- [ ] Verify frontend timeline works with correlation_id

---

## TROUBLESHOOTING

### Issue: Events missing correlation_id

```python
# Verify guarantee is working
event = {'event_id': 'test', 'source_ip': '10.0.0.5'}
event = correlation_engine.guarantee_correlation_id(event)
assert event['correlation_id'], "Should have correlation_id"
```

### Issue: Different IDs for same events

```python
# Verify deterministic generation
id1 = engine.generate_correlation_id(event)
id2 = engine.generate_correlation_id(event)
assert id1 == id2, "IDs should be identical"

# Check if timestamp differs (affects ID)
print(f"Timestamp precision: {event['timestamp']}")
```

### Issue: Timeline not grouping events

```sql
-- Verify IDs are in database
SELECT DISTINCT correlation_id FROM security_logs 
LIMIT 10;

-- Verify index exists
SELECT * FROM pg_indexes 
WHERE tablename = 'security_logs' 
AND indexname LIKE '%correlation%';
```

---

## SUPPORT

- **Documentation**: [CORRELATION_ID_LOCKING.md](CORRELATION_ID_LOCKING.md)
- **Algorithm Details**: [CORRELATION_HANDLING.md](CORRELATION_HANDLING.md)
- **Engine Code**: [correlation_engine.py](correlation_engine.py)
- **API Changes**: [mayasec_api.py](mayasec_api.py#L163-L195)
- **Schema**: [migrations/003_add_correlation_id.sql](migrations/003_add_correlation_id.sql)

"""
MAYASEC Ingestor Service

Single entry point for all security events.
Accepts:
- HTTP POST /api/ingest/event (JSON)
- Log files via mounted volume (file watcher)

Normalizes all events to canonical schema.
Forwards to mayasec-api for analysis and WebSocket emission.
"""

import os
import logging
import json
import uuid
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import requests

from .normalizer import normalize_event
from .sources import start_watchers
from jsonschema import validate, ValidationError

# Load environment
load_dotenv()

# Configuration
INGESTOR_PORT = int(os.getenv('INGESTOR_PORT', 5001))
API_SERVICE_URL = os.getenv('API_SERVICE_URL', os.getenv('CORE_SERVICE_URL', 'http://mayasec-api:5000'))
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = os.getenv('LOG_DIR', '/app/logs')

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{LOG_DIR}/ingestor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('Ingestor')

# Load event schema
with open('/app/event_schema.json', 'r') as f:
    EVENT_SCHEMA = json.load(f)

# Create Flask app
app = Flask(__name__)
app.json.sort_keys = False

# Enable CORS for browser-based attacker UI
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["POST", "OPTIONS"],
        "allow_headers": "*"
    }
})

# Queue for batching events (in-memory for now)
event_queue = []
MAX_QUEUE_SIZE = int(os.getenv('MAX_QUEUE_SIZE', '100'))
FLUSH_INTERVAL_SECONDS = int(os.getenv('INGESTOR_FLUSH_INTERVAL_SECONDS', '2'))


def generate_event_id() -> str:
    """Generate unique event ID (UUID v4)"""
    return str(uuid.uuid4())


def validate_event(event: Dict[str, Any]) -> bool:
    """Validate event against schema"""
    try:
        validate(instance=event, schema=EVENT_SCHEMA)
        return True
    except ValidationError as e:
        logger.warning(f"Event validation failed: {e.message}")
        return False


def _ingest_normalized_event(event: Dict[str, Any]) -> bool:
    event['correlation_id'] = None

    if not event.get('raw_log'):
        logger.warning("raw_log missing; dropping event")
        return False

    if not validate_event(event):
        return False

    event_queue.append(event)
    logger.debug(f"Event ingested: {event['event_id']}")

    if len(event_queue) >= MAX_QUEUE_SIZE:
        events_to_send = event_queue[:]
        event_queue.clear()
        forward_to_api(events_to_send)

    return True


# Attach ingest function for runtime access
app.config['INGEST_FUNC'] = _ingest_normalized_event


def _flush_loop():
    while True:
        try:
            if event_queue:
                events_to_send = event_queue[:]
                event_queue.clear()
                forward_to_api(events_to_send)
        except Exception as e:
            logger.error(f"Flush loop error: {e}")
        time.sleep(FLUSH_INTERVAL_SECONDS)


def forward_to_api(events: list) -> bool:
    """Send normalized events to mayasec-api (ingestion only, WebSocket emission)"""
    if not events:
        return True
    
    try:
        response = requests.post(
            f'{API_SERVICE_URL}/api/v1/events/ingest',
            json={'events': events},
            timeout=10
        )
        
        if response.status_code in (200, 202):
            logger.info(f"Forwarded {len(events)} events to mayasec-api")
            return True
        else:
            logger.error(f"Failed to forward events: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to mayasec-api: {e}")
        return False


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'mayasec-ingestor',
        'timestamp': datetime.utcnow().isoformat()
    }), 200


@app.route('/api/ingest/event', methods=['POST'])
def ingest_event():
    """
    Ingest a single security event via HTTP POST
    
    Expected JSON:
    {
        "event_type": "login_attempt|honeypot_interaction|network_alert|...",
        "timestamp": "2026-01-15T10:30:00Z",
        "source": "http_api|log_file|ids|...",
        "sensor_id": "string",
        ... other fields
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON body provided'}), 400
        
        # Normalize incoming event (backend owns normalization)
        if 'event_id' not in data:
            data['event_id'] = generate_event_id()
        
        # Normalize timestamp
        if 'timestamp' not in data:
            data['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        elif isinstance(data['timestamp'], str):
            # Ensure ISO format with Z suffix
            if not data['timestamp'].endswith('Z'):
                data['timestamp'] += 'Z'
        
        normalized = normalize_event(data)

        # Validate against schema
        if not _ingest_normalized_event(normalized):
            return jsonify({
                'error': 'Event validation failed',
                'event_id': data.get('event_id')
            }), 400
        
        return jsonify({
            'status': 'accepted',
            'event_id': normalized['event_id']
        }), 202
        
    except Exception as e:
        logger.error(f"Error ingesting event: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ingest/batch', methods=['POST'])
def ingest_batch():
    """
    Ingest multiple events in a single request
    
    Expected JSON:
    {
        "events": [
            { event 1 },
            { event 2 },
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'events' not in data:
            return jsonify({'error': 'No events provided'}), 400
        
        events = data['events']
        if not isinstance(events, list):
            return jsonify({'error': 'events must be an array'}), 400
        
        if len(events) == 0:
            return jsonify({'error': 'events array cannot be empty'}), 400
        
        if len(events) > 1000:
            return jsonify({'error': 'Maximum 1000 events per batch'}), 400
        
        # Normalize and validate all events
        valid_events = []
        for event in events:
            if 'event_id' not in event:
                event['event_id'] = generate_event_id()
            
            if 'timestamp' not in event:
                event['timestamp'] = datetime.utcnow().isoformat() + 'Z'
            elif isinstance(event['timestamp'], str) and not event['timestamp'].endswith('Z'):
                event['timestamp'] += 'Z'
            
            normalized = normalize_event(event)
            if _ingest_normalized_event(normalized):
                valid_events.append(normalized)
            else:
                logger.warning(f"Skipping invalid event in batch: {event.get('event_id')}")
        
        if not valid_events:
            return jsonify({'error': 'No valid events in batch'}), 400
        
        # Add to queue
        event_queue.extend(valid_events)
        
        # Forward if queue is getting large
        if len(event_queue) >= MAX_QUEUE_SIZE:
            events_to_send = event_queue[:]
            event_queue.clear()
            forward_to_api(events_to_send)
        
        return jsonify({
            'status': 'accepted',
            'count': len(valid_events),
            'event_ids': [e['event_id'] for e in valid_events]
        }), 202
        
    except Exception as e:
        logger.error(f"Error ingesting batch: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ingest/flush', methods=['POST'])
def flush_queue():
    """Force flush all queued events to mayasec-core"""
    try:
        if event_queue:
            events_to_send = event_queue[:]
            event_queue.clear()
            forward_to_api(events_to_send)
            return jsonify({
                'status': 'flushed',
                'count': len(events_to_send)
            }), 200
        else:
            return jsonify({
                'status': 'empty',
                'count': 0
            }), 200
            
    except Exception as e:
        logger.error(f"Error flushing queue: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/status', methods=['GET'])
def status():
    """Return ingestor status"""
    return jsonify({
        'service': 'mayasec-ingestor',
        'status': 'running',
        'queue_size': len(event_queue),
        'max_queue_size': MAX_QUEUE_SIZE,
        'timestamp': datetime.utcnow().isoformat()
    }), 200


if __name__ == '__main__':
    logger.info(f"Starting MAYASEC Ingestor on port {INGESTOR_PORT}")
    logger.info(f"Core service URL: {CORE_SERVICE_URL}")
    flush_thread = threading.Thread(target=_flush_loop, daemon=True)
    flush_thread.start()
    start_watchers(ingest_func=_ingest_normalized_event)
    app.run(host='0.0.0.0', port=INGESTOR_PORT, debug=False)

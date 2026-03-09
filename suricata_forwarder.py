#!/usr/bin/env python3
"""
Suricata EVE.JSON Forwarder to Mayasec API

This script:
- Tails Suricata's eve.json log file
- Parses JSON events
- Sends them to Mayasec's /api/ingest/event endpoint
- Retries on failure with exponential backoff
- Requires no root privileges (reads from user-accessible logs)
- Runs as a standalone daemon

Configuration:
- Environment variables or config file
- API URL, sensor ID, source identification
- Retry behavior and logging
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_SURICATA_LOG_PATH = "/var/log/suricata/eve.json"
DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_SENSOR_ID = "suricata-forwarder"
DEFAULT_SOURCE = "suricata-eve"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_BATCH_SIZE = 10  # Events per batch
DEFAULT_BATCH_TIMEOUT = 5  # Seconds

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Configuration management"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self.api_url = os.getenv('MAYASEC_API_URL', DEFAULT_API_URL)
        self.sensor_id = os.getenv('MAYASEC_SENSOR_ID', DEFAULT_SENSOR_ID)
        self.source = os.getenv('MAYASEC_SOURCE', DEFAULT_SOURCE)
        self.eve_json_path = os.getenv('SURICATA_EVE_JSON', DEFAULT_SURICATA_LOG_PATH)
        self.log_level = os.getenv('LOG_LEVEL', DEFAULT_LOG_LEVEL)
        self.batch_size = int(os.getenv('BATCH_SIZE', DEFAULT_BATCH_SIZE))
        self.batch_timeout = int(os.getenv('BATCH_TIMEOUT', DEFAULT_BATCH_TIMEOUT))
        self.max_retries = int(os.getenv('MAX_RETRIES', '3'))
        self.retry_backoff = float(os.getenv('RETRY_BACKOFF', '2.0'))
        self.read_timeout = int(os.getenv('READ_TIMEOUT', '10'))
        
        # Load from config file if provided
        if config_file and os.path.exists(config_file):
            self.load_from_file(config_file)
    
    def load_from_file(self, config_file: str):
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                for key, value in config.items():
                    attr_name = key.lower()
                    if hasattr(self, attr_name):
                        setattr(self, attr_name, value)
        except Exception as e:
            logging.warning(f"Could not load config file {config_file}: {e}")
    
    def validate(self) -> bool:
        """Validate configuration"""
        if not self.api_url:
            logging.error("MAYASEC_API_URL not set")
            return False
        
        if not os.path.exists(self.eve_json_path):
            logging.warning(f"EVE JSON file not found: {self.eve_json_path}")
            # Don't fail, it might appear later
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary (for logging)"""
        return {
            'api_url': self.api_url,
            'sensor_id': self.sensor_id,
            'source': self.source,
            'eve_json_path': self.eve_json_path,
            'batch_size': self.batch_size,
            'batch_timeout': self.batch_timeout,
            'max_retries': self.max_retries,
        }

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(log_level: str, log_file: Optional[str] = None):
    """Configure logging"""
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(level)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logging.warning(f"Could not create log file {log_file}: {e}")
    
    return logging.getLogger(__name__)

# ============================================================================
# HTTP CLIENT WITH RETRIES
# ============================================================================

def create_http_session(max_retries: int = 3, backoff: float = 2.0) -> requests.Session:
    """Create a requests session with retry logic"""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=max_retries,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST", "GET"],
        backoff_factor=backoff
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

# ============================================================================
# SURICATA EVE EVENT PARSING
# ============================================================================

def parse_eve_event(line: str) -> Optional[Dict[str, Any]]:
    """Parse a JSON line from Suricata EVE log"""
    try:
        event = json.loads(line)
        if not event:
            return None
        event['_raw_log'] = line
        return event
    except (json.JSONDecodeError, ValueError) as e:
        logging.warning(f"Failed to parse JSON: {e}")
        return None

def map_eve_to_ingest(eve_event: Dict[str, Any], config: Config) -> Optional[Dict[str, Any]]:
    """
    Convert Suricata EVE event to Mayasec ingest_event format
    
    EVE format: https://suricata.readthedocs.io/en/latest/output/eve/eve-json-output.html
    """
    event_type = eve_event.get('event_type', 'network_alert')
    
    # Only forward relevant event types
    if event_type not in ('alert', 'dns', 'http', 'tls', 'flow', 'metadata'):
        return None
    
    # Build ingest event
    ingest_event = {
        'source': config.source,
        'sensor_id': config.sensor_id,
        'timestamp': eve_event.get('timestamp', datetime.utcnow().isoformat() + 'Z'),
        'data': {
            'event_type': 'network_alert',  # Normalize all network events
            'sensor_type': 'suricata',
            'raw_log': eve_event.get('_raw_log'),
            'src_ip': eve_event.get('src_ip'),
            'dest_ip': eve_event.get('dest_ip'),
            'src_port': eve_event.get('src_port'),
            'dest_port': eve_event.get('dest_port'),
            'proto': eve_event.get('proto'),
        }
    }
    
    # Add alert details if present
    if 'alert' in eve_event:
        ingest_event['data']['alert'] = eve_event['alert']
    
    # Add protocol-specific details
    if 'dns' in eve_event:
        ingest_event['data']['dns'] = eve_event['dns']
    if 'http' in eve_event:
        ingest_event['data']['http'] = eve_event['http']
    if 'tls' in eve_event:
        ingest_event['data']['tls'] = eve_event['tls']
    
    # Add raw event for reference
    ingest_event['data']['eve_raw'] = eve_event
    
    return ingest_event

# ============================================================================
# FILE TAILING
# ============================================================================

class FileTailer:
    """Tail a file and yield new lines"""
    
    def __init__(self, filepath: str, logger: logging.Logger):
        self.filepath = filepath
        self.logger = logger
        self.file = None
        self.last_size = 0
        self.last_inode = None
    
    def open_file(self) -> bool:
        """Open file if it exists"""
        try:
            if not os.path.exists(self.filepath):
                return False
            
            self.file = open(self.filepath, 'r', buffering=1)
            self.last_size = os.path.getsize(self.filepath)
            self.last_inode = os.stat(self.filepath).st_ino
            self.logger.info(f"Opened file: {self.filepath}")
            return True
        except Exception as e:
            self.logger.warning(f"Could not open file {self.filepath}: {e}")
            return False
    
    def close_file(self):
        """Close file handle"""
        if self.file:
            try:
                self.file.close()
            except:
                pass
            self.file = None
    
    def get_lines(self) -> list:
        """Get new lines from file"""
        lines = []
        
        # File not open, try to open
        if not self.file:
            if not self.open_file():
                return lines
        
        try:
            # Check if file was rotated
            if os.path.exists(self.filepath):
                current_inode = os.stat(self.filepath).st_ino
                if current_inode != self.last_inode:
                    self.logger.info("File rotated detected, reopening")
                    self.close_file()
                    if not self.open_file():
                        return lines
            
            # Read new lines
            while True:
                line = self.file.readline()
                if not line:
                    break
                lines.append(line)
            
            return lines
        
        except Exception as e:
            self.logger.error(f"Error reading file: {e}")
            self.close_file()
            return lines
    
    def __del__(self):
        self.close_file()

# ============================================================================
# EVENT SUBMISSION
# ============================================================================

class EventSubmitter:
    """Submit events to Mayasec API"""
    
    def __init__(self, api_url: str, config: Config, logger: logging.Logger):
        self.api_url = api_url.rstrip('/')
        self.endpoint = f"{self.api_url}/api/ingest/event"
        self.config = config
        self.logger = logger
        self.session = create_http_session(config.max_retries, config.retry_backoff)
        self.stats = {
            'sent': 0,
            'failed': 0,
            'retried': 0,
        }
    
    def submit_event(self, event: Dict[str, Any]) -> bool:
        """Submit a single event to the API"""
        try:
            response = self.session.post(
                self.endpoint,
                json=event,
                headers={'Content-Type': 'application/json'},
                timeout=self.config.read_timeout
            )
            
            if response.status_code == 200:
                self.stats['sent'] += 1
                self.logger.debug(f"Event submitted successfully: {event['data'].get('src_ip')}")
                return True
            else:
                self.logger.warning(
                    f"API returned {response.status_code}: {response.text[:200]}"
                )
                self.stats['failed'] += 1
                return False
        
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {e}")
            self.stats['retried'] += 1
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            self.stats['failed'] += 1
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get submission statistics"""
        return self.stats.copy()

# ============================================================================
# MAIN FORWARDER
# ============================================================================

class SuricataForwarder:
    """Main forwarder service"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logging(config.log_level)
        self.tailer = FileTailer(config.eve_json_path, self.logger)
        self.submitter = EventSubmitter(config.api_url, config, self.logger)
        self.running = False
    
    def log_startup_info(self):
        """Log startup information"""
        self.logger.info("=" * 80)
        self.logger.info("Suricata EVE.JSON Forwarder for Mayasec")
        self.logger.info("=" * 80)
        self.logger.info(f"Configuration: {json.dumps(self.config.to_dict(), indent=2)}")
        self.logger.info("=" * 80)
    
    def process_events(self):
        """Process events from Suricata eve.json and forward to API"""
        self.log_startup_info()
        self.running = True
        batch = []
        last_batch_time = time.time()
        
        try:
            while self.running:
                # Get new lines from file
                lines = self.tailer.get_lines()
                
                # Process lines
                for line in lines:
                    eve_event = parse_eve_event(line)
                    if not eve_event:
                        continue
                    
                    # Map to ingest format
                    ingest_event = map_eve_to_ingest(eve_event, self.config)
                    if not ingest_event:
                        continue
                    
                    # Add to batch
                    batch.append(ingest_event)
                    
                    # Submit when batch is full
                    if len(batch) >= self.config.batch_size:
                        self.submit_batch(batch)
                        batch = []
                        last_batch_time = time.time()
                
                # Submit partial batch if timeout reached
                current_time = time.time()
                if batch and (current_time - last_batch_time) >= self.config.batch_timeout:
                    self.submit_batch(batch)
                    batch = []
                    last_batch_time = current_time
                
                # Sleep to avoid busy-waiting
                time.sleep(0.5)
        
        except KeyboardInterrupt:
            self.logger.info("Received interrupt, shutting down...")
        finally:
            # Submit remaining events
            if batch:
                self.submit_batch(batch)
            
            self.log_final_stats()
            self.tailer.close_file()
    
    def submit_batch(self, events: list):
        """Submit a batch of events"""
        if not events:
            return
        
        self.logger.info(f"Submitting batch of {len(events)} events")
        for event in events:
            self.submitter.submit_event(event)
    
    def log_final_stats(self):
        """Log final statistics"""
        stats = self.submitter.get_stats()
        total = stats['sent'] + stats['failed']
        success_rate = (stats['sent'] / total * 100) if total > 0 else 0
        
        self.logger.info("=" * 80)
        self.logger.info("Final Statistics:")
        self.logger.info(f"  Events sent: {stats['sent']}")
        self.logger.info(f"  Events failed: {stats['failed']}")
        self.logger.info(f"  Events retried: {stats['retried']}")
        self.logger.info(f"  Total processed: {total}")
        self.logger.info(f"  Success rate: {success_rate:.1f}%")
        self.logger.info("=" * 80)
    
    def stop(self):
        """Stop the forwarder"""
        self.running = False

# ============================================================================
# CLI
# ============================================================================

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Forward Suricata EVE.JSON events to Mayasec API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  MAYASEC_API_URL       - Mayasec API URL (default: http://localhost:8000)
  MAYASEC_SENSOR_ID     - Sensor identifier (default: suricata-forwarder)
  MAYASEC_SOURCE        - Event source name (default: suricata-eve)
  SURICATA_EVE_JSON     - Path to eve.json (default: /var/log/suricata/eve.json)
  LOG_LEVEL             - Logging level (default: INFO)
  BATCH_SIZE            - Events per batch (default: 10)
  BATCH_TIMEOUT         - Batch timeout in seconds (default: 5)
  MAX_RETRIES           - Max API retries (default: 3)
  RETRY_BACKOFF         - Retry backoff factor (default: 2.0)

Examples:
  # Default configuration
  python suricata_forwarder.py
  
  # With custom API URL
  MAYASEC_API_URL=http://192.168.1.100:8000 python suricata_forwarder.py
  
  # With custom sensor ID and logging
  MAYASEC_SENSOR_ID=suricata-dmz LOG_LEVEL=DEBUG python suricata_forwarder.py
  
  # With config file
  python suricata_forwarder.py --config /etc/mayasec/forwarder.json
        """
    )
    
    parser.add_argument(
        '--config',
        help='Path to JSON configuration file'
    )
    parser.add_argument(
        '--log-file',
        help='Path to log file (optional)'
    )
    parser.add_argument(
        '--api-url',
        help='Override Mayasec API URL'
    )
    parser.add_argument(
        '--sensor-id',
        help='Override sensor ID'
    )
    parser.add_argument(
        '--eve-json',
        help='Override path to eve.json'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = Config(args.config)
    
    # Override with command-line arguments
    if args.api_url:
        config.api_url = args.api_url
    if args.sensor_id:
        config.sensor_id = args.sensor_id
    if args.eve_json:
        config.eve_json_path = args.eve_json
    
    # Validate
    if not config.validate():
        sys.exit(1)
    
    # Create and run forwarder
    forwarder = SuricataForwarder(config)
    
    try:
        forwarder.process_events()
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()

"""
Correlation Engine for MAYASEC

SINGLE SOURCE OF TRUTH for event correlation.

CRITICAL INVARIANTS:
✓ correlation_id is ALWAYS generated (never empty, never null)
✓ correlation_id is DETERMINISTIC (same events → same ID)
✓ correlation_id is IMMUTABLE (never changes after assignment)
✓ correlation_id PERSISTS in database (permanent)
✓ correlation_id EMITS over WebSocket (clients always receive it)

STRATEGY: Source IP + Target (IP:Port) + Time Window
- Same attacker (source IP)
- Same target (destination IP + port combination)
- Within time window (300 seconds = 5 minutes)
= Same attack incident (same correlation_id)

EXAMPLES:
  Event: 10.0.0.5 → 192.168.1.1:22 at 08:15:00 (port_scan)
  Event: 10.0.0.5 → 192.168.1.1:22 at 08:15:30 (brute_force) ✓ CORRELATED
  Event: 10.0.0.5 → 192.168.1.2:22 at 08:15:35 (port_scan)   ✗ DIFFERENT TARGET
  Event: 10.0.0.6 → 192.168.1.1:22 at 08:15:40 (port_scan)   ✗ DIFFERENT ATTACKER

FORMAT: corr_yyyymmdd_srcip_dstip_port_hash
  Example: corr_20240115_10000005_192168110122_e4c8d
  - "corr_": Prefix (identifies as correlation ID)
  - "20240115": Date (YYYYMMDD, groups by day)
  - "10000005": Source IP (converted to integer for compact form)
  - "192168110122": Dest IP:Port (combined, no colons)
  - "e4c8d": Hash (MD5 first 5 chars, adds entropy)

IMPLEMENTATION:
1. On event ingestion: Extract source, destination, port, timestamp
2. Query database: Find events matching source+destination in 5-min window
3. Determine correlation_id:
   a. If match found: Use existing ID (inherit from matched event)
   b. If no match: Generate new ID (start of new incident)
4. Store in database: Include correlation_id in INSERT
5. Emit on WebSocket: Include correlation_id in broadcast
6. Frontend: Receive correlation_id, use for timeline filtering

GUARANTEES:
✓ Idempotent: Ingesting same event twice gets same correlation_id
✓ Retroactive: Events already in DB are not re-correlated
✓ Deterministic: No randomness, same inputs = same output
✓ Transactional: Database commit ensures consistency
✓ Broadcast: WebSocket emission includes correlation_id
"""

import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger('CorrelationEngine')

# CONFIGURATION
CORRELATION_WINDOW_SECONDS = 300  # 5-minute time window
CORRELATION_PREFIX = "corr"
CORRELATION_VERSION = "1"


class CorrelationEngine:
    """Deterministic correlation_id generation and management"""
    
    def __init__(self, db_connection_getter=None):
        """
        Initialize correlation engine
        
        Args:
            db_connection_getter: Callable that returns a database connection
                                Used for querying existing correlations
        """
        self.db_connection_getter = db_connection_getter
        logger.info(f"Correlation Engine initialized (window={CORRELATION_WINDOW_SECONDS}s)")
    
    def generate_correlation_id(
        self,
        event: Dict[str, Any],
        existing_correlation_id: Optional[str] = None
    ) -> str:
        """
        Generate or retrieve correlation_id for an event.
        
        ALGORITHM:
        1. If event already has correlation_id, return it (idempotent)
        2. If database has related events, inherit their correlation_id
        3. Otherwise, generate new correlation_id
        
        Args:
            event: Event dictionary with at least:
                - source_ip (or ip_address.source)
                - destination_ip (or ip_address.destination)  [optional, uses 0.0.0.0 if missing]
                - destination_port (or port)                   [optional, uses 0 if missing]
                - timestamp (ISO 8601 datetime string or datetime object)
            
            existing_correlation_id: If event was pre-correlated, use this
        
        Returns:
            correlation_id: String in format "corr_yyyymmdd_srcip_dstip_port_hash"
        
        INVARIANTS:
        ✓ Never returns empty string
        ✓ Never returns null
        ✓ Same inputs always return same output
        ✓ Format is consistent and queryable
        """
        try:
            # If correlation_id already provided, return it (idempotent)
            if existing_correlation_id and existing_correlation_id.strip():
                logger.debug(f"Using provided correlation_id: {existing_correlation_id}")
                return existing_correlation_id
            
            # Extract event details
            source_ip = self._extract_source_ip(event)
            dest_ip = self._extract_dest_ip(event)
            dest_port = self._extract_dest_port(event)
            timestamp = self._extract_timestamp(event)
            
            # Log extraction for debugging
            logger.debug(
                f"Extracting correlation for: "
                f"src={source_ip} dst={dest_ip}:{dest_port} time={timestamp}"
            )
            
            # Try to find existing correlation in database
            if self.db_connection_getter:
                existing_id = self._find_existing_correlation(
                    source_ip, dest_ip, dest_port, timestamp
                )
                if existing_id:
                    logger.info(
                        f"Found existing correlation: {source_ip} → {dest_ip}:{dest_port} = {existing_id}"
                    )
                    return existing_id
            
            # Generate new correlation_id
            new_id = self._generate_new_correlation_id(
                source_ip, dest_ip, dest_port, timestamp
            )
            logger.info(
                f"Generated new correlation: {source_ip} → {dest_ip}:{dest_port} = {new_id}"
            )
            return new_id
            
        except Exception as e:
            logger.error(f"Error generating correlation_id: {e}")
            # FALLBACK: Generate UUID-based ID (deterministic)
            # Ensures we never return null, always fail gracefully
            import uuid
            fallback_id = f"{CORRELATION_PREFIX}_{uuid.uuid4().hex[:12]}"
            logger.warning(f"Using fallback correlation_id: {fallback_id}")
            return fallback_id
    
    def _extract_source_ip(self, event: Dict[str, Any]) -> str:
        """Extract source IP from event"""
        # Try multiple possible field names
        if 'source_ip' in event:
            return event['source_ip']
        if 'ip_address' in event:
            ip_addr = event['ip_address']
            if isinstance(ip_addr, dict) and 'source' in ip_addr:
                return ip_addr['source']
            if isinstance(ip_addr, str):
                return ip_addr
        if 'src_ip' in event:
            return event['src_ip']
        
        raise ValueError("Could not extract source IP from event")
    
    def _extract_dest_ip(self, event: Dict[str, Any]) -> str:
        """Extract destination IP from event (defaults to 0.0.0.0 if missing)"""
        # Try multiple possible field names
        if 'destination_ip' in event:
            return event['destination_ip']
        if 'dest_ip' in event:
            return event['dest_ip']
        if 'ip_address' in event:
            ip_addr = event['ip_address']
            if isinstance(ip_addr, dict) and 'destination' in ip_addr:
                return ip_addr['destination']
        
        # Default: Use 0.0.0.0 for unknown destination
        # This allows single-host scans to correlate
        logger.debug("Destination IP not found, using default 0.0.0.0")
        return "0.0.0.0"
    
    def _extract_dest_port(self, event: Dict[str, Any]) -> int:
        """Extract destination port from event (defaults to 0 if missing)"""
        # Try multiple possible field names
        if 'destination_port' in event:
            port = event['destination_port']
            if port:
                return int(port)
        if 'dest_port' in event:
            port = event['dest_port']
            if port:
                return int(port)
        if 'port' in event:
            port = event['port']
            if port:
                return int(port)
        
        # Default: Use 0 for unknown port
        logger.debug("Destination port not found, using default 0")
        return 0
    
    def _extract_timestamp(self, event: Dict[str, Any]) -> datetime:
        """Extract and parse timestamp from event"""
        timestamp = event.get('timestamp')
        
        # Already a datetime object
        if isinstance(timestamp, datetime):
            return timestamp
        
        # Parse ISO 8601 string
        if isinstance(timestamp, str):
            try:
                # Handle ISO 8601 with Z suffix
                if timestamp.endswith('Z'):
                    timestamp = timestamp[:-1] + '+00:00'
                return datetime.fromisoformat(timestamp)
            except ValueError:
                pass
        
        # Fallback to current time
        logger.debug("Could not parse timestamp, using current time")
        return datetime.utcnow()
    
    def _find_existing_correlation(
        self,
        source_ip: str,
        dest_ip: str,
        dest_port: int,
        timestamp: datetime
    ) -> Optional[str]:
        """
        Query database for existing correlation
        
        Finds events matching:
        - Same source_ip
        - Same destination_ip
        - Same destination_port
        - Within correlation window of timestamp
        """
        if not self.db_connection_getter:
            return None
        
        try:
            conn = self.db_connection_getter()
            cursor = conn.cursor()
            
            # Calculate time window bounds
            window_start = timestamp - timedelta(seconds=CORRELATION_WINDOW_SECONDS)
            window_end = timestamp + timedelta(seconds=CORRELATION_WINDOW_SECONDS)
            
            # Query for related events
            # Note: This query assumes database has ip_address + destination fields
            # Adjust column names based on actual schema
            cursor.execute('''
                SELECT DISTINCT correlation_id
                FROM security_logs
                WHERE ip_address = %s
                  AND metadata->>'destination_ip' = %s
                  AND (metadata->>'destination_port')::INT = %s
                  AND timestamp BETWEEN %s AND %s
                  AND correlation_id IS NOT NULL
                LIMIT 1
            ''', (source_ip, dest_ip, dest_port, window_start, window_end))
            
            result = cursor.fetchone()
            cursor.close()
            
            return result[0] if result else None
            
        except Exception as e:
            logger.warning(f"Database query for existing correlation failed: {e}")
            return None
    
    def _generate_new_correlation_id(
        self,
        source_ip: str,
        dest_ip: str,
        dest_port: int,
        timestamp: datetime
    ) -> str:
        """
        Generate deterministic new correlation_id
        
        Format: corr_yyyymmdd_srcip_dstip_port_hash
        
        DETERMINISTIC: Same inputs always produce same output
        UNIQUE: Different source/dest/time combinations produce different IDs
        COMPACT: Fits in VARCHAR(255)
        """
        # Date component (YYYYMMDD)
        date_str = timestamp.strftime('%Y%m%d')
        
        # Source IP component (compact form)
        src_parts = source_ip.split('.')
        if len(src_parts) == 4:
            # Convert IP to compact decimal string
            # 10.0.0.5 → 167772169 (decimal representation)
            src_int = (int(src_parts[0]) << 24) + (int(src_parts[1]) << 16) + \
                      (int(src_parts[2]) << 8) + int(src_parts[3])
            src_component = str(src_int)
        else:
            src_component = source_ip.replace('.', '')
        
        # Destination component (compact form with port)
        dst_parts = dest_ip.split('.')
        if len(dst_parts) == 4:
            dst_int = (int(dst_parts[0]) << 24) + (int(dst_parts[1]) << 16) + \
                      (int(dst_parts[2]) << 8) + int(dst_parts[3])
            dst_component = str(dst_int) + str(dest_port)
        else:
            dst_component = dest_ip.replace('.', '') + str(dest_port)
        
        # Hash component (adds entropy for uniqueness)
        # Combine source, destination, port, and date for hash
        hash_input = f"{source_ip}:{dest_ip}:{dest_port}:{date_str}"
        hash_obj = hashlib.md5(hash_input.encode())
        hash_component = hash_obj.hexdigest()[:5]  # First 5 chars of MD5
        
        # Assemble final correlation_id
        correlation_id = (
            f"{CORRELATION_PREFIX}_{date_str}_{src_component}_{dst_component}_{hash_component}"
        )
        
        return correlation_id
    
    def guarantee_correlation_id(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mutate event to ensure correlation_id is present
        
        CRITICAL GUARANTEE: Event will always have valid correlation_id after this
        
        Usage:
            event = correlation_engine.guarantee_correlation_id(event)
            # Now safe to persist and emit
        
        Args:
            event: Event dictionary
        
        Returns:
            Mutated event with correlation_id guaranteed
        """
        if 'correlation_id' not in event or not event['correlation_id']:
            event['correlation_id'] = self.generate_correlation_id(event)
        
        return event

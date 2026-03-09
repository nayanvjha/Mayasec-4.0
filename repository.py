"""
Repository Layer for Mayasec Database

Architecture:
- Abstraction layer between business logic and database
- Single point for all SQL queries
- Type-safe interfaces with no raw SQL outside this module
- Connection pooling ready (psycopg2.pool)
- Transaction management per operation
- Audit trail logging for all mutations

Usage:
    from repository import EventRepository, AlertRepository
    
    repo = EventRepository(db_config)
    event = repo.create_event(normalized_event, threat_analysis)
    logs = repo.query_logs(ip_address='1.2.3.4', days=7)
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
from psycopg2.pool import SimpleConnectionPool

logger = logging.getLogger('Repository')


class DatabaseConfig:
    """Database connection configuration"""
    
    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
    
    def get_dsn(self) -> str:
        """Get DSN connection string"""
        return f"host={self.host} port={self.port} database={self.database} user={self.user} password={self.password}"


class BaseRepository(ABC):
    """Base repository with connection management"""
    
    def __init__(self, db_config: DatabaseConfig):
        self.db_config = db_config
        self.pool = None
        self._init_pool()
    
    def _init_pool(self):
        """Initialize connection pool"""
        try:
            self.pool = SimpleConnectionPool(
                1, 5,  # min_conn, max_conn
                host=self.db_config.host,
                port=self.db_config.port,
                database=self.db_config.database,
                user=self.db_config.user,
                password=self.db_config.password
            )
            logger.info("Connection pool initialized")
        except psycopg2.Error as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise
    
    def get_connection(self):
        """Get connection from pool"""
        if not self.pool:
            raise RuntimeError("Connection pool not initialized")
        return self.pool.getconn()
    
    def return_connection(self, conn):
        """Return connection to pool"""
        if self.pool:
            self.pool.putconn(conn)
    
    def close_all(self):
        """Close all connections in pool"""
        if self.pool:
            self.pool.closeall()
            logger.info("Connection pool closed")
    
    def is_healthy(self) -> bool:
        """Check if database is accessible"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            cursor.close()
            return True
        except psycopg2.Error as e:
            logger.error(f"Health check failed: {e}")
            return False
        finally:
            if conn:
                self.return_connection(conn)


class EventRepository(BaseRepository):
    """Repository for security event persistence"""
    
    def create_event(self, event: Dict[str, Any], threat_analysis: Dict[str, Any]) -> bool:
        """
        Persist normalized event with threat analysis
        
        Routes to appropriate table based on event_type:
        - login_attempt, authentication_* → login_attempts + security_logs
        - honeypot_interaction → honeypot_logs + security_logs
        - network_alert → network_flows + security_logs
        - suspicious_behavior → alert_history + security_logs
        - default → security_logs
        
        Returns: True if successful, False otherwise
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            event_type = event.get('event_type', 'unknown')
            
            # Always store in security_logs as primary log
            self._store_security_log(cursor, event, threat_analysis)
            
            # Route to specialized tables
            if 'login' in event_type or 'auth' in event_type:
                self._store_login_attempt(cursor, event, threat_analysis)
            elif event_type == 'honeypot_interaction':
                self._store_honeypot_log(cursor, event, threat_analysis)
            elif event_type == 'network_alert':
                self._store_network_flow(cursor, event, threat_analysis)
            elif event_type == 'suspicious_behavior':
                self._store_alert_history(cursor, event, threat_analysis)
            
            conn.commit()
            logger.info(f"Event stored: {event.get('event_id')}")
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Failed to store event: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self.return_connection(conn)
    
    def _store_security_log(self, cursor, event: Dict[str, Any], analysis: Dict[str, Any]):
        """Store in primary security_logs table"""
        cursor.execute('''
            INSERT INTO security_logs
            (event_id, event_type, ip_address, username, action, user_agent,
             threat_level, threat_score, blocked, reason, sensor_id, source, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
        ''', (
            event.get('event_id'),
            event.get('event_type'),
            event.get('ip_address', {}).get('source'),
            event.get('username'),
            event.get('action'),
            event.get('user_agent'),
            analysis.get('threat_level', 'info'),
            analysis.get('threat_score', 0),
            event.get('action') == 'blocked',
            analysis.get('analysis_reason', event.get('reason', '')),
            event.get('sensor_id'),
            event.get('source'),
            json.dumps(analysis)
        ))
    
    def _store_login_attempt(self, cursor, event: Dict[str, Any], analysis: Dict[str, Any]):
        """Store login attempt for authentication tracking"""
        cursor.execute('''
            INSERT INTO login_attempts
            (event_id, ip_address, username, success, user_agent,
             sensor_id, threat_score, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
        ''', (
            event.get('event_id'),
            event.get('ip_address', {}).get('source'),
            event.get('username'),
            'success' in event.get('event_type', '').lower(),
            event.get('user_agent'),
            event.get('sensor_id'),
            analysis.get('threat_score', 0),
            json.dumps(analysis)
        ))
    
    def _store_honeypot_log(self, cursor, event: Dict[str, Any], analysis: Dict[str, Any]):
        """Store honeypot interaction"""
        cursor.execute('''
            INSERT INTO honeypot_logs
            (event_id, ip_address, username, password_attempt, user_agent,
             sensor_id, interaction_type, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
        ''', (
            event.get('event_id'),
            event.get('ip_address', {}).get('source'),
            event.get('username'),
            event.get('password_hash'),
            event.get('user_agent'),
            event.get('sensor_id'),
            event.get('action'),
            json.dumps(analysis)
        ))
    
    def _store_network_flow(self, cursor, event: Dict[str, Any], analysis: Dict[str, Any]):
        """Store network alert as flow event"""
        cursor.execute('''
            INSERT INTO network_flows
            (event_id, source_ip, destination_ip, source_port, destination_port,
             protocol, action, threat_score, sensor_id, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
        ''', (
            event.get('event_id'),
            event.get('ip_address', {}).get('source'),
            event.get('ip_address', {}).get('destination'),
            event.get('port', {}).get('source'),
            event.get('port', {}).get('destination'),
            event.get('protocol'),
            event.get('action'),
            analysis.get('threat_score', 0),
            event.get('sensor_id'),
            json.dumps({**event.get('alert', {}), **analysis})
        ))
    
    def _store_alert_history(self, cursor, event: Dict[str, Any], analysis: Dict[str, Any]):
        """Store suspicious behavior as alert"""
        cursor.execute('''
            INSERT INTO alert_history
            (event_id, alert_type, threat_level, threat_score, description,
             ip_address, username, sensor_id, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            event.get('event_id'),
            event.get('event_type'),
            analysis.get('threat_level', 'info'),
            analysis.get('threat_score', 0),
            analysis.get('analysis_reason', ''),
            event.get('ip_address', {}).get('source'),
            event.get('username'),
            event.get('sensor_id'),
            json.dumps(analysis)
        ))
    
    def batch_create_events(self, events: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> int:
        """
        Efficiently store multiple events
        
        Args:
            events: List of (event, threat_analysis) tuples
        
        Returns: Count of successfully stored events
        """
        conn = None
        success_count = 0
        try:
            conn = self.get_connection()
            for event, analysis in events:
                if self.create_event(event, analysis):
                    success_count += 1
            return success_count
        finally:
            if conn:
                self.return_connection(conn)
    
    def query_logs(self, ip_address: Optional[str] = None, username: Optional[str] = None,
                   threat_level: Optional[str] = None, days: int = 7,
                   limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Query security logs with optional filters
        
        Returns: List of log entries matching criteria
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            where_clauses = [
                f"timestamp > NOW() - INTERVAL '{days} days'"
            ]
            params = []
            
            if ip_address:
                where_clauses.append("ip_address = %s")
                params.append(ip_address)
            
            if username:
                where_clauses.append("username = %s")
                params.append(username)
            
            if threat_level:
                where_clauses.append("threat_level = %s")
                params.append(threat_level)
            
            where_sql = " AND ".join(where_clauses)
            
            cursor.execute(f'''
                SELECT * FROM security_logs
                WHERE {where_sql}
                ORDER BY timestamp DESC
                LIMIT %s
            ''', params + [limit])
            
            results = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            return results
            
        except psycopg2.Error as e:
            logger.error(f"Query failed: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get event by event_id"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute(
                'SELECT * FROM security_logs WHERE event_id = %s',
                (event_id,)
            )
            result = cursor.fetchone()
            cursor.close()
            return dict(result) if result else None
            
        except psycopg2.Error as e:
            logger.error(f"Get event failed: {e}")
            return None
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_ip_threat_summary(self, ip_address: str, days: int = 7) -> Dict[str, Any]:
        """Get threat summary for an IP address"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT
                    ip_address,
                    COUNT(*) as total_events,
                    COUNT(CASE WHEN threat_level = 'critical' THEN 1 END) as critical_count,
                    COUNT(CASE WHEN threat_level = 'high' THEN 1 END) as high_count,
                    COUNT(CASE WHEN blocked = TRUE THEN 1 END) as blocked_count,
                    MAX(threat_score) as max_threat_score,
                    AVG(threat_score) as avg_threat_score,
                    MAX(timestamp) as last_seen
                FROM security_logs
                WHERE ip_address = %s AND timestamp > NOW() - INTERVAL '%s days'
                GROUP BY ip_address
            ''', (ip_address, days))
            
            result = cursor.fetchone()
            cursor.close()
            return dict(result) if result else {}
            
        except psycopg2.Error as e:
            logger.error(f"Threat summary query failed: {e}")
            return {}
        finally:
            if conn:
                self.return_connection(conn)


class AlertRepository(BaseRepository):
    """Repository for alert and response management"""
    
    def create_alert(self, rule_id: str, title: str, severity: str,
                     event_ids: List[str], ip_address: Optional[str] = None,
                     username: Optional[str] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Create new alert
        
        Returns: alert_id if successful, None otherwise
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO alerts
                (rule_id, title, severity, event_ids, ip_address, username, description, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING alert_id
            ''', (
                rule_id, title, severity, event_ids or [],
                ip_address, username, title,
                json.dumps(metadata or {})
            ))
            
            alert_id = cursor.fetchone()[0]
            conn.commit()
            logger.info(f"Alert created: {alert_id}")
            return alert_id
            
        except psycopg2.Error as e:
            logger.error(f"Failed to create alert: {e}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_open_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all open alerts"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT * FROM alerts
                WHERE status = 'open'
                ORDER BY timestamp DESC
                LIMIT %s
            ''', (limit,))
            
            results = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            return results
            
        except psycopg2.Error as e:
            logger.error(f"Get open alerts failed: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)
    
    def block_ip(self, ip_address: str, reason: str, is_permanent: bool = False,
                 expires_at: Optional[datetime] = None,
                 threat_level: Optional[str] = None,
                 correlation_id: Optional[str] = None,
                 metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Block an IP address"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO blocked_ips
                (ip_address, reason, is_permanent, expires_at, threat_level, correlation_id, metadata, active, unblocked_at, unblock_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NULL, NULL)
                ON CONFLICT (ip_address) DO UPDATE SET
                    block_count = blocked_ips.block_count + 1,
                    last_blocked_at = CURRENT_TIMESTAMP,
                    expires_at = COALESCE(EXCLUDED.expires_at, blocked_ips.expires_at),
                    reason = EXCLUDED.reason,
                    is_permanent = EXCLUDED.is_permanent,
                    threat_level = COALESCE(EXCLUDED.threat_level, blocked_ips.threat_level),
                    correlation_id = COALESCE(EXCLUDED.correlation_id, blocked_ips.correlation_id),
                    metadata = COALESCE(EXCLUDED.metadata, blocked_ips.metadata),
                    active = TRUE,
                    unblocked_at = NULL,
                    unblock_reason = NULL
            ''', (
                ip_address,
                reason,
                is_permanent,
                expires_at,
                threat_level,
                correlation_id,
                json.dumps(metadata or {})
            ))
            
            conn.commit()
            logger.info(f"IP blocked: {ip_address}")
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Failed to block IP: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self.return_connection(conn)
    
    def is_ip_blocked(self, ip_address: str) -> bool:
        """Check if IP is currently blocked"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 1 FROM blocked_ips
                WHERE ip_address = %s
                AND (is_permanent = TRUE OR expires_at > CURRENT_TIMESTAMP)
                AND COALESCE(active, TRUE) = TRUE
                LIMIT 1
            ''', (ip_address,))
            
            result = cursor.fetchone()
            cursor.close()
            return result is not None
            
        except psycopg2.Error as e:
            logger.error(f"Check blocked IP failed: {e}")
            return False
        finally:
            if conn:
                self.return_connection(conn)

    def get_blocked_ips(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Get currently active blocked IPs"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute('''
                SELECT
                    ip_address::text as ip_address,
                    reason,
                    is_permanent,
                    blocked_at,
                    expires_at,
                    block_count,
                    last_blocked_at,
                    threat_level,
                    metadata,
                    active,
                    unblocked_at,
                    unblock_reason,
                    correlation_id
                FROM blocked_ips
                WHERE (is_permanent = TRUE OR expires_at > CURRENT_TIMESTAMP)
                AND COALESCE(active, TRUE) = TRUE
                ORDER BY last_blocked_at DESC
                LIMIT %s
            ''', (limit,))

            results = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            return results

        except psycopg2.Error as e:
            logger.error(f"Get blocked IPs failed: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

    def count_blocks_since(self, hours: int = 1) -> int:
        """Count blocks within the last N hours"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*)
                FROM blocked_ips
                WHERE last_blocked_at > NOW() - INTERVAL '%s hours'
            ''', (hours,))
            result = cursor.fetchone()
            cursor.close()
            return int(result[0]) if result else 0
        except psycopg2.Error as e:
            logger.error(f"Count blocks since failed: {e}")
            return 0
        finally:
            if conn:
                self.return_connection(conn)

    def get_expired_blocks(self) -> List[str]:
        """Get expired blocks that should be unblocked"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ip_address::text
                FROM blocked_ips
                WHERE is_permanent = FALSE
                AND expires_at IS NOT NULL
                AND expires_at <= CURRENT_TIMESTAMP
                AND COALESCE(active, TRUE) = TRUE
            ''')
            results = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return results
        except psycopg2.Error as e:
            logger.error(f"Get expired blocks failed: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

    def unblock_ip(self, ip_address: str, reason: str) -> bool:
        """Unblock an IP address"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE blocked_ips
                SET active = FALSE,
                    unblocked_at = CURRENT_TIMESTAMP,
                    unblock_reason = %s
                WHERE ip_address = %s
                AND COALESCE(active, TRUE) = TRUE
                RETURNING ip_address
            ''', (reason, ip_address))

            result = cursor.fetchone()
            conn.commit()
            cursor.close()
            return result is not None

        except psycopg2.Error as e:
            logger.error(f"Failed to unblock IP: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self.return_connection(conn)


class ResponseRepository(BaseRepository):
    """Repository for response mode state and enforcement decisions"""

    def set_response_mode(self, mode: str, source: str = 'env') -> Dict[str, Any]:
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                INSERT INTO response_mode_state (id, mode, source)
                VALUES (1, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    mode = EXCLUDED.mode,
                    source = EXCLUDED.source,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, mode, source, updated_at
            ''', (mode, source))
            result = cursor.fetchone()
            conn.commit()
            cursor.close()
            return dict(result) if result else {'mode': mode, 'source': source}
        except psycopg2.Error as e:
            logger.error(f"Failed to persist response mode: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.return_connection(conn)

    def get_response_mode(self) -> Optional[Dict[str, Any]]:
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT id, mode, source, updated_at
                FROM response_mode_state
                WHERE id = 1
            ''')
            result = cursor.fetchone()
            cursor.close()
            return dict(result) if result else None
        except psycopg2.Error as e:
            logger.error(f"Failed to fetch response mode: {e}")
            return None
        finally:
            if conn:
                self.return_connection(conn)

    def record_response_decision(self, decision: Dict[str, Any]) -> Optional[str]:
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO response_decisions
                (mode, decision, action, reason, ip_address, correlation_id,
                 event_id, threat_level, threat_score, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING decision_id
            ''', (
                decision.get('mode'),
                decision.get('decision'),
                decision.get('action'),
                decision.get('reason'),
                decision.get('ip_address'),
                decision.get('correlation_id'),
                decision.get('event_id'),
                decision.get('threat_level'),
                decision.get('threat_score'),
                json.dumps(decision.get('metadata') or {})
            ))
            result = cursor.fetchone()
            conn.commit()
            cursor.close()
            return str(result[0]) if result else None
        except psycopg2.Error as e:
            logger.error(f"Failed to record response decision: {e}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                self.return_connection(conn)


class StatisticsRepository(BaseRepository):
    """Repository for analytics and reporting"""
    
    def get_threat_distribution(self, days: int = 7) -> Dict[str, int]:
        """Get count of events by threat level"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT threat_level, COUNT(*) as count
                FROM security_logs
                WHERE timestamp > NOW() - INTERVAL '%s days'
                GROUP BY threat_level
            ''', (days,))
            
            return {row['threat_level']: row['count'] for row in cursor.fetchall()}
            
        except psycopg2.Error as e:
            logger.error(f"Threat distribution query failed: {e}")
            return {}
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_top_ips(self, days: int = 7, limit: int = 10) -> List[Tuple[str, int]]:
        """Get top attacking IPs by event count"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT ip_address, COUNT(*) as count
                FROM security_logs
                WHERE timestamp > NOW() - INTERVAL '%s days'
                AND ip_address IS NOT NULL
                GROUP BY ip_address
                ORDER BY count DESC
                LIMIT %s
            ''', (days, limit))
            
            return [(row[0], row[1]) for row in cursor.fetchall()]
            
        except psycopg2.Error as e:
            logger.error(f"Top IPs query failed: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

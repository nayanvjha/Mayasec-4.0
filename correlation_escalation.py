"""
Correlation & Escalation Engine (Deterministic)

- Correlates events by source_ip + destination + time window
- Escalates severity monotonically
- Creates alerts once per correlation session
"""

import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger('CorrelationEscalation')

SEVERITY_ORDER = {
    'info': 0,
    'low': 1,
    'medium': 2,
    'high': 3,
    'critical': 4
}

SEVERITY_SCORE = {
    'info': 0,
    'low': 20,
    'medium': 45,
    'high': 75,
    'critical': 90
}

PHASE_ORDER = {
    'reconnaissance': 0,
    'initial_access': 1,
    'credential_access': 2,
    'lateral_movement': 3,
    'persistence': 4,
    'command_and_control': 5,
    'impact': 6
}

PHASE_MIN_SEVERITY = {
    'reconnaissance': 'low',
    'initial_access': 'medium',
    'credential_access': 'high',
    'lateral_movement': 'high',
    'persistence': 'high',
    'command_and_control': 'critical',
    'impact': 'critical'
}


class CorrelationEscalationEngine:
    def __init__(self, event_repo, alert_repo, enforcement_service=None, response_mode: Optional[str] = None):
        self.event_repo = event_repo
        self.alert_repo = alert_repo
        self.enforcement = enforcement_service
        self.response_mode = response_mode
        self.window_minutes = int(os.getenv('CORRELATION_WINDOW_MINUTES', '10'))
        self.alert_threshold = os.getenv('ALERT_THRESHOLD', 'high').lower()

        self.auth_threshold_medium = int(os.getenv('AUTH_FAIL_THRESHOLD_MEDIUM', '5'))
        self.auth_threshold_high = int(os.getenv('AUTH_FAIL_THRESHOLD_HIGH', '10'))
        self.auth_threshold_critical = int(os.getenv('AUTH_FAIL_THRESHOLD_CRITICAL', '20'))
        self.port_scan_threshold = int(os.getenv('PORT_SCAN_UNIQUE_PORTS', '10'))

        self.alert_rule_id = 'correlation_escalation'
        self.alert_repo.ensure_alert_rule(
            rule_id=self.alert_rule_id,
            rule_name='Correlation Escalation Threshold',
            description='Alert when correlation session severity crosses threshold',
            severity=self.alert_threshold
        )

    def _deterministic_correlation_id(self, source_ip: str, destination: Optional[str], window_start: datetime) -> str:
        key = f"{source_ip}|{destination or 'unknown'}|{window_start.isoformat()}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, key))

    def _get_window_start(self, event_time: datetime) -> datetime:
        minutes = self.window_minutes
        bucket = int(event_time.timestamp() // (minutes * 60))
        return datetime.utcfromtimestamp(bucket * minutes * 60)

    def _extract_destination(self, event: Dict[str, Any]) -> Optional[str]:
        if event.get('destination'):
            return event.get('destination')
        ip_addr = event.get('ip_address') or {}
        dest = ip_addr.get('destination') if isinstance(ip_addr, dict) else None
        if dest and isinstance(event.get('port'), dict) and event['port'].get('destination'):
            return f"{dest}:{event['port'].get('destination')}"
        return dest

    def _parse_event_time(self, event: Dict[str, Any]) -> datetime:
        ts = event.get('timestamp')
        if isinstance(ts, datetime):
            return ts
        try:
            if isinstance(ts, str) and ts.endswith('Z'):
                ts = ts[:-1] + '+00:00'
            return datetime.fromisoformat(ts)
        except Exception:
            return datetime.utcnow()

    def _monotonic_severity(self, current: str, candidate: str) -> str:
        if SEVERITY_ORDER.get(candidate, 0) > SEVERITY_ORDER.get(current, 0):
            return candidate
        return current

    def _monotonic_phase(self, current: str, candidate: str) -> str:
        if PHASE_ORDER.get(candidate, 0) > PHASE_ORDER.get(current, 0):
            return candidate
        return current

    def _phase_severity_floor(self, phase: str, severity: str) -> str:
        floor = PHASE_MIN_SEVERITY.get(phase, 'low')
        return self._monotonic_severity(severity, floor)

    def _derive_attack_phase(self, event: Dict[str, Any], state: Dict[str, Any], event_time: datetime,
                             destination: Optional[str]) -> Dict[str, Any]:
        current_phase = (state.get('attack_context') or {}).get('phase', 'reconnaissance')
        counts = state.get('counts', {})
        ports = state.get('ports', [])
        destinations = state.get('destinations', [])

        event_type = (event.get('event_type') or '').lower()
        sensor_type = (event.get('sensor_type') or '').lower()
        severity = event.get('severity', 'low')
        reason = 'no_change'
        confidence = float((state.get('attack_context') or {}).get('confidence', 0.2))

        candidate_phase = current_phase

        if 'honeypot' in event_type or sensor_type == 'honeypot':
            candidate_phase = self._monotonic_phase(candidate_phase, 'credential_access')
            reason = 'interaction with deception asset'
            confidence = max(confidence, 0.95)
            if counts.get('honeypot_hits', 0) >= 2:
                candidate_phase = self._monotonic_phase(candidate_phase, 'lateral_movement')
                reason = 'repeated_deception_interaction'
                confidence = max(confidence, 0.97)
            if counts.get('honeypot_hits', 0) >= 4:
                candidate_phase = self._monotonic_phase(candidate_phase, 'impact')
                reason = 'sustained_deception_interaction'
                confidence = max(confidence, 0.98)

        if event_type in ('port_scan', 'network_alert'):
            candidate_phase = self._monotonic_phase(candidate_phase, 'reconnaissance')
            reason = 'port_scan_or_probe'
            confidence = max(confidence, 0.4)

        if event_type in ('ssh_failed_login', 'web_auth_failed', 'login_attempt', 'authentication_failure'):
            candidate_phase = self._monotonic_phase(candidate_phase, 'initial_access')
            reason = 'repeated_auth_failures'
            confidence = max(confidence, 0.5)

        if counts.get('auth_failures', 0) >= self.auth_threshold_high:
            candidate_phase = self._monotonic_phase(candidate_phase, 'credential_access')
            reason = 'brute_force_or_spraying'
            confidence = max(confidence, 0.7)

        if event_type in ('authentication_success', 'login_success', 'web_auth_success') and counts.get('auth_failures', 0) > 0:
            candidate_phase = self._monotonic_phase(candidate_phase, 'credential_access')
            reason = 'auth_success_after_failures'
            confidence = max(confidence, 0.8)

        if destination and destination not in destinations:
            destinations.append(destination)
        if len(destinations) >= 2:
            candidate_phase = self._monotonic_phase(candidate_phase, 'lateral_movement')
            reason = 'multiple_internal_hosts'
            confidence = max(confidence, 0.75)

        last_seen_raw = state.get('last_seen')
        if last_seen_raw:
            try:
                last_seen = datetime.fromisoformat(last_seen_raw.replace('Z', '+00:00'))
                if event_time - last_seen > timedelta(minutes=30):
                    candidate_phase = self._monotonic_phase(candidate_phase, 'persistence')
                    reason = 'repeated_access_after_gap'
                    confidence = max(confidence, 0.7)
            except Exception:
                pass

        if event_type in ('c2_beacon', 'command_and_control', 'beacon'):
            candidate_phase = self._monotonic_phase(candidate_phase, 'command_and_control')
            reason = 'command_and_control_signal'
            confidence = max(confidence, 0.85)

        if event_type in ('dos', 'ddos', 'data_exfiltration', 'exfiltration', 'impact'):
            candidate_phase = self._monotonic_phase(candidate_phase, 'impact')
            reason = 'impact_pattern'
            confidence = max(confidence, 0.9)

        if counts.get('events', 0) >= 25:
            candidate_phase = self._monotonic_phase(candidate_phase, 'impact')
            reason = 'high_volume_abuse'
            confidence = max(confidence, 0.85)

        state['destinations'] = destinations

        return {
            'phase': candidate_phase,
            'confidence': round(min(confidence, 1.0), 2),
            'reason': reason
        }

    def _escalate(self, event: Dict[str, Any], state: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        severity = state.get('severity', 'low')
        counts = state.get('counts', {})
        ports = state.get('ports', [])
        counts['events'] = counts.get('events', 0) + 1

        event_type = event.get('event_type')
        sensor_type = (event.get('sensor_type') or '').lower()
        if 'honeypot' in (event_type or '').lower() or sensor_type == 'honeypot':
            counts['honeypot_hits'] = counts.get('honeypot_hits', 0) + 1
        if event_type in ('ssh_failed_login', 'web_auth_failed', 'login_attempt', 'authentication_failure'):
            counts['auth_failures'] = counts.get('auth_failures', 0) + 1
            if counts['auth_failures'] >= self.auth_threshold_critical:
                severity = self._monotonic_severity(severity, 'critical')
            elif counts['auth_failures'] >= self.auth_threshold_high:
                severity = self._monotonic_severity(severity, 'high')
            elif counts['auth_failures'] >= self.auth_threshold_medium:
                severity = self._monotonic_severity(severity, 'medium')

        if event_type in ('port_scan', 'network_alert'):
            alert = event.get('alert') or {}
            signature = (alert.get('signature') or '').lower() if isinstance(alert, dict) else ''
            category = (alert.get('category') or '').lower() if isinstance(alert, dict) else ''
            if 'scan' in signature or 'scan' in category or event_type == 'port_scan':
                severity = self._monotonic_severity(severity, 'high')

            port = None
            if isinstance(event.get('port'), dict):
                port = event['port'].get('destination')
            if port and port not in ports:
                ports.append(port)
            if len(ports) >= self.port_scan_threshold:
                severity = self._monotonic_severity(severity, 'high')

        state['counts'] = counts
        state['ports'] = ports
        state['severity'] = severity
        return severity, state

    def process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        source_ip = event.get('source_ip') or (event.get('ip_address') or {}).get('source')
        destination = self._extract_destination(event)
        if not source_ip:
            raise ValueError("source_ip required for correlation")

        event_time = self._parse_event_time(event)
        window_start = self._get_window_start(event_time)

        # Attempt to find existing correlation in window
        correlation = self.event_repo.find_active_correlation(source_ip, destination, self.window_minutes)
        if correlation:
            correlation_id = correlation['correlation_id']
            state = correlation.get('state', {})
        else:
            correlation_id = self._deterministic_correlation_id(source_ip, destination, window_start)
            state = {
                'counts': {},
                'ports': [],
                'destinations': [],
                'severity': 'low',
                'first_seen': event_time.isoformat() + 'Z'
            }
            state['attack_context'] = {
                'phase': 'reconnaissance',
                'confidence': 0.2,
                'reason': 'initialized'
            }
            state['phase_history'] = []

        # Escalate deterministically
        severity, state = self._escalate(event, state)
        state['last_seen'] = event_time.isoformat() + 'Z'
        state['destination'] = destination

        attack_context = self._derive_attack_phase(event, state, event_time, destination)
        current_phase = (state.get('attack_context') or {}).get('phase', 'reconnaissance')
        if PHASE_ORDER.get(attack_context['phase'], 0) > PHASE_ORDER.get(current_phase, 0):
            history = state.get('phase_history', [])
            history.append({
                'from': current_phase,
                'to': attack_context['phase'],
                'timestamp': event_time.isoformat() + 'Z',
                'reason': attack_context['reason']
            })
            state['phase_history'] = history
        state['attack_context'] = attack_context
        severity = self._phase_severity_floor(attack_context['phase'], severity)
        state['severity'] = severity

        # Persist correlation state
        self.event_repo.upsert_correlation_state(
            correlation_id=correlation_id,
            source_ip=source_ip,
            destination=destination,
            event_id=event.get('event_id'),
            severity=severity,
            event_time=event_time,
            state=state
        )

        # Update event correlation_id
        self.event_repo.set_event_correlation(event.get('event_id'), correlation_id)

        alert_id = None
        alert_data = None
        response_candidate = None
        if SEVERITY_ORDER.get(severity, 0) >= SEVERITY_ORDER.get(self.alert_threshold, 0):
            alert_id = self.alert_repo.get_alert_by_correlation(correlation_id)
            if not alert_id:
                alert_id = self.alert_repo.create_alert(
                    rule_id=self.alert_rule_id,
                    title='Correlated attack session escalation',
                    severity=severity,
                    event_ids=[event.get('event_id')],
                    ip_address=source_ip,
                    correlation_id=correlation_id,
                    metadata={
                        'destination': destination,
                        'counts': state.get('counts'),
                        'ports': state.get('ports'),
                        'attack_phase': attack_context.get('phase'),
                        'phase_reason': attack_context.get('reason'),
                        'phase_confidence': attack_context.get('confidence'),
                        'response_mode': self.response_mode
                    }
                )
                logger.info(f"Alert created for correlation_id={correlation_id} severity={severity}")
                alert_data = {
                    'alert_id': alert_id,
                    'id': alert_id,
                    'rule_id': self.alert_rule_id,
                    'title': 'Correlated attack session escalation',
                    'severity': severity,
                    'event_ids': [event.get('event_id')],
                    'ip_address': source_ip,
                    'correlation_id': correlation_id,
                    'metadata': {
                        'destination': destination,
                        'counts': state.get('counts'),
                        'ports': state.get('ports'),
                        'attack_phase': attack_context.get('phase'),
                        'phase_reason': attack_context.get('reason'),
                        'phase_confidence': attack_context.get('confidence'),
                        'response_mode': self.response_mode
                    },
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }

            reason = f"alert_severity={severity} rule={self.alert_rule_id}"
            if alert_id:
                reason = f"existing_alert:{reason}" if alert_data is None else reason
            response_candidate = {
                'action': 'block_ip',
                'ip_address': source_ip,
                'reason': reason,
                'correlation_id': correlation_id,
                'is_permanent': False,
                'ttl_hours': int(os.getenv('RESPONSE_BLOCK_TTL_HOURS', '24')),
                'threat_level': severity,
                'metadata': {
                    'alert_id': alert_id,
                    'destination': destination,
                    'attack_phase': attack_context.get('phase'),
                    'phase_reason': attack_context.get('reason'),
                    'response_mode': self.response_mode
                }
            }

        return {
            'correlation_id': correlation_id,
            'severity': severity,
            'alert_id': alert_id,
            'alert_data': alert_data,
            'response_candidate': response_candidate,
            'correlation_state': state
        }

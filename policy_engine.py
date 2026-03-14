"""
Policy Engine for MAYASEC Response Plane

Enforces blast-radius controls between alert creation and enforcement.
"""

import os
import ipaddress
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, List

from response_mode import resolve_response_mode

logger = logging.getLogger('PolicyEngine')


class ResponseMode(str, Enum):
    MONITOR = 'monitor'
    GUARDED = 'guarded'
    ACTIVE = 'active'
    DECEPTION = 'deception'


@dataclass
class PolicyDecision:
    action: str  # enforce | recommend | none
    reason: str
    mode: str
    safeguards: Dict[str, Any]


class PolicyEngine:
    def __init__(self, alert_repo):
        self.alert_repo = alert_repo
        mode, _ = resolve_response_mode()
        self.mode = self._resolve_mode(mode)
        self.allowlist = self._parse_allowlist(os.getenv('RESPONSE_ALLOWLIST', ''))
        self.max_blocks_per_hour = int(os.getenv('RESPONSE_MAX_BLOCKS_PER_HOUR', '10'))

    def get_state(self) -> Dict[str, Any]:
        return {
            'mode': self.mode.value,
            'allowlist': self.allowlist,
            'max_blocks_per_hour': self.max_blocks_per_hour
        }

    @staticmethod
    def _resolve_mode(mode_raw: str) -> ResponseMode:
        normalized = (mode_raw or '').strip().lower()
        for mode in ResponseMode:
            if mode.value == normalized:
                return mode
        raise ValueError(f"Invalid response mode: {mode_raw}")

    @staticmethod
    def _parse_allowlist(raw: str) -> List[str]:
        return [item.strip() for item in raw.split(',') if item.strip()]

    def _is_allowlisted(self, ip_address: str) -> bool:
        if not ip_address:
            return False
        for entry in self.allowlist:
            try:
                if '/' in entry:
                    if ipaddress.ip_address(ip_address) in ipaddress.ip_network(entry, strict=False):
                        return True
                elif ip_address == entry:
                    return True
            except ValueError:
                continue
        return False

    def _max_blocks_exceeded(self) -> bool:
        if self.max_blocks_per_hour <= 0:
            return False
        try:
            recent = self.alert_repo.count_blocks_since(hours=1)
            return recent >= self.max_blocks_per_hour
        except Exception as e:
            logger.error(f"Failed to check max blocks per hour: {e}")
            return False

    @staticmethod
    def _get_source_ip(event: Dict[str, Any]) -> Optional[str]:
        if not event:
            return None
        if 'source_ip' in event and event['source_ip']:
            return event['source_ip']
        ip_addr = event.get('ip_address')
        if isinstance(ip_addr, dict):
            return ip_addr.get('source')
        if isinstance(ip_addr, str):
            return ip_addr
        return None

    @staticmethod
    def _get_threat_score(event: Dict[str, Any]) -> int:
        analysis = event.get('threat_analysis', {}) if isinstance(event, dict) else {}
        try:
            return int(analysis.get('threat_score', 0))
        except Exception:
            return 0

    @staticmethod
    def _get_confidence(correlation_state: Optional[Dict[str, Any]]) -> float:
        if not correlation_state:
            return 0.0
        attack_context = correlation_state.get('attack_context') or {}
        try:
            return float(attack_context.get('confidence', 0.0))
        except Exception:
            return 0.0

    @staticmethod
    def _get_severity(event: Dict[str, Any]) -> str:
        severity = event.get('severity') if isinstance(event, dict) else None
        if isinstance(severity, str):
            return severity.lower()
        return 'low'

    @staticmethod
    def _is_honeypot_signal(event: Dict[str, Any]) -> bool:
        if not isinstance(event, dict):
            return False
        event_type = (event.get('event_type') or '').lower()
        sensor_type = (event.get('sensor_type') or '').lower()
        return 'honeypot' in event_type or sensor_type == 'honeypot'

    def evaluate(self,
                 event: Dict[str, Any],
                 correlation_state: Optional[Dict[str, Any]] = None,
                 asset_metadata: Optional[Dict[str, Any]] = None,
                 candidate_action: str = 'block_ip',
                 candidate_reason: str = 'policy-evaluated') -> PolicyDecision:
        source_ip = self._get_source_ip(event)
        safeguards = {
            'mode': self.mode.value,
            'allowlist': bool(self.allowlist),
            'max_blocks_per_hour': self.max_blocks_per_hour
        }

        if source_ip and self._is_allowlisted(source_ip):
            return PolicyDecision(
                action='none',
                reason='allowlisted_source_ip',
                mode=self.mode.value,
                safeguards=safeguards
            )

        if self._max_blocks_exceeded():
            return PolicyDecision(
                action='none',
                reason='max_blocks_per_hour_exceeded',
                mode=self.mode.value,
                safeguards=safeguards
            )

        severity = self._get_severity(event)
        threat_score = self._get_threat_score(event)
        honeypot_signal = self._is_honeypot_signal(event)

        if self.mode == ResponseMode.MONITOR:
            return PolicyDecision(
                action='recommend',
                reason=f"monitor:{candidate_reason}",
                mode=self.mode.value,
                safeguards=safeguards
            )

        if self.mode == ResponseMode.GUARDED:
            confidence = self._get_confidence(correlation_state)
            if honeypot_signal:
                return PolicyDecision(
                    action='enforce',
                    reason=f"guarded:honeypot_signal:{candidate_reason}",
                    mode=self.mode.value,
                    safeguards=safeguards
                )
            if severity == 'critical' or confidence >= 0.9 or threat_score >= 90:
                return PolicyDecision(
                    action='enforce',
                    reason=f"guarded:{candidate_reason}",
                    mode=self.mode.value,
                    safeguards=safeguards
                )
            return PolicyDecision(
                action='recommend',
                reason='guarded:threshold_not_met',
                mode=self.mode.value,
                safeguards=safeguards
            )

        if self.mode == ResponseMode.DECEPTION:
            return PolicyDecision(
                action='enforce',
                reason=f"deception:{candidate_reason}",
                mode=self.mode.value,
                safeguards=safeguards
            )

        return PolicyDecision(
            action='enforce',
            reason=f"active:{candidate_reason}",
            mode=self.mode.value,
            safeguards=safeguards
        )

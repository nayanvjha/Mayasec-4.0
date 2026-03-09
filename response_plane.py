"""
MAYASEC Response Plane

Responsibilities:
- Enforce OS-level blocking (iptables/nftables)
- Persist block decisions in database
- Unblock on TTL expiration or manual request

No mock behavior. Real firewall enforcement only.
"""

import os
import shutil
import ipaddress
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple, List, Callable

import logging

from policy_engine import PolicyEngine
from response_mode import resolve_response_mode

logger = logging.getLogger('ResponsePlane')


class FirewallCommandError(RuntimeError):
    pass


class FirewallService:
    """Firewall abstraction for iptables/nftables."""

    def __init__(self, backend: Optional[str] = None):
        self.backend = (backend or os.getenv('FIREWALL_BACKEND', 'auto')).lower()
        self._resolved_backend = None
        self._resolve_backend()

    def _resolve_backend(self) -> None:
        if self.backend not in ('auto', 'iptables', 'nftables'):
            raise ValueError(f"Unsupported FIREWALL_BACKEND: {self.backend}")

        if self.backend == 'iptables':
            if not shutil.which('iptables'):
                raise RuntimeError("iptables not available in container")
            self._resolved_backend = 'iptables'
        elif self.backend == 'nftables':
            if not shutil.which('nft'):
                raise RuntimeError("nft not available in container")
            self._resolved_backend = 'nftables'
        else:
            if shutil.which('nft'):
                self._resolved_backend = 'nftables'
            elif shutil.which('iptables'):
                self._resolved_backend = 'iptables'
            else:
                raise RuntimeError("No firewall backend available (nft/iptables missing)")

        logger.info(f"Firewall backend: {self._resolved_backend}")
        if self._resolved_backend == 'iptables':
            self._ensure_iptables_chain()
        else:
            self._ensure_nft_table()

    def _run(self, cmd: List[str]) -> Tuple[int, str, str]:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def _run_required(self, cmd: List[str]) -> str:
        code, out, err = self._run(cmd)
        if code != 0:
            raise FirewallCommandError(f"Command failed: {' '.join(cmd)} | {err or out}")
        return out

    def _ensure_iptables_chain(self) -> None:
        # Create chain if missing
        code, _, _ = self._run(['iptables', '-L', 'MAYASEC_BLOCK'])
        if code != 0:
            self._run_required(['iptables', '-N', 'MAYASEC_BLOCK'])

        # Ensure jump from INPUT
        code, _, _ = self._run(['iptables', '-C', 'INPUT', '-j', 'MAYASEC_BLOCK'])
        if code != 0:
            self._run_required(['iptables', '-I', 'INPUT', '1', '-j', 'MAYASEC_BLOCK'])

    def _ensure_nft_table(self) -> None:
        # Create table
        code, _, _ = self._run(['nft', 'list', 'table', 'inet', 'mayasec'])
        if code != 0:
            self._run_required(['nft', 'add', 'table', 'inet', 'mayasec'])

        # Create set
        code, _, _ = self._run(['nft', 'list', 'set', 'inet', 'mayasec', 'blocked_ips'])
        if code != 0:
            self._run_required([
                'nft', 'add', 'set', 'inet', 'mayasec', 'blocked_ips',
                '{', 'type', 'ipv4_addr', ';', 'flags', 'interval', ';', '}'
            ])

        # Create input chain
        code, _, _ = self._run(['nft', 'list', 'chain', 'inet', 'mayasec', 'input'])
        if code != 0:
            self._run_required([
                'nft', 'add', 'chain', 'inet', 'mayasec', 'input',
                '{', 'type', 'filter', 'hook', 'input', 'priority', '0', ';', 'policy', 'accept', ';', '}'
            ])

        # Ensure rule exists
        out = self._run_required(['nft', 'list', 'chain', 'inet', 'mayasec', 'input'])
        if '@blocked_ips' not in out:
            self._run_required([
                'nft', 'add', 'rule', 'inet', 'mayasec', 'input', 'ip', 'saddr', '@blocked_ips', 'drop'
            ])

    @staticmethod
    def _validate_ip(ip_address: str) -> None:
        try:
            ipaddress.ip_address(ip_address)
        except ValueError as e:
            raise ValueError(f"Invalid IP address: {ip_address}") from e

    def block_ip(self, ip_address: str) -> None:
        self._validate_ip(ip_address)

        if self._resolved_backend == 'nftables':
            out = self._run_required(['nft', 'list', 'set', 'inet', 'mayasec', 'blocked_ips'])
            if ip_address in out:
                return
            self._run_required([
                'nft', 'add', 'element', 'inet', 'mayasec', 'blocked_ips', '{', ip_address, '}'
            ])
        else:
            code, _, _ = self._run(['iptables', '-C', 'MAYASEC_BLOCK', '-s', ip_address, '-j', 'DROP'])
            if code == 0:
                return
            self._run_required(['iptables', '-A', 'MAYASEC_BLOCK', '-s', ip_address, '-j', 'DROP'])

    def unblock_ip(self, ip_address: str) -> None:
        self._validate_ip(ip_address)

        if self._resolved_backend == 'nftables':
            out = self._run_required(['nft', 'list', 'set', 'inet', 'mayasec', 'blocked_ips'])
            if ip_address not in out:
                return
            self._run_required([
                'nft', 'delete', 'element', 'inet', 'mayasec', 'blocked_ips', '{', ip_address, '}'
            ])
        else:
            # Remove all matching rules (idempotent)
            while True:
                code, _, _ = self._run(['iptables', '-C', 'MAYASEC_BLOCK', '-s', ip_address, '-j', 'DROP'])
                if code != 0:
                    break
                self._run_required(['iptables', '-D', 'MAYASEC_BLOCK', '-s', ip_address, '-j', 'DROP'])

    def is_blocked(self, ip_address: str) -> bool:
        self._validate_ip(ip_address)

        if self._resolved_backend == 'nftables':
            out = self._run_required(['nft', 'list', 'set', 'inet', 'mayasec', 'blocked_ips'])
            return ip_address in out

        code, _, _ = self._run(['iptables', '-C', 'MAYASEC_BLOCK', '-s', ip_address, '-j', 'DROP'])
        return code == 0


class EnforcementService:
    """Responsible only for enforcement and persistence."""

    def __init__(self, alert_repository, firewall_service: FirewallService):
        self.alert_repo = alert_repository
        self.firewall = firewall_service
        self.default_ttl_hours = int(os.getenv('RESPONSE_BLOCK_TTL_HOURS', '24'))

    def block_ip(self, ip_address: str, reason: str, correlation_id: str,
                 is_permanent: bool = False,
                 ttl_hours: Optional[int] = None,
                 metadata: Optional[Dict[str, Any]] = None,
                 threat_level: Optional[str] = None) -> Dict[str, Any]:
        if not correlation_id:
            correlation_id = 'manual'

        expires_at = None
        if not is_permanent:
            ttl = ttl_hours if ttl_hours is not None else self.default_ttl_hours
            expires_at = datetime.utcnow() + timedelta(hours=ttl)

        # Enforce OS-level block FIRST
        self.firewall.block_ip(ip_address)

        # Persist block decision
        success = self.alert_repo.block_ip(
            ip_address=ip_address,
            reason=reason,
            is_permanent=is_permanent,
            expires_at=expires_at,
            threat_level=threat_level,
            correlation_id=correlation_id,
            metadata=metadata
        )

        if not success:
            raise RuntimeError(f"Failed to persist block decision for {ip_address}")

        logger.info(f"Enforced block: {ip_address} (correlation_id={correlation_id})")
        return {
            'status': 'blocked',
            'ip_address': ip_address,
            'reason': reason,
            'correlation_id': correlation_id,
            'is_permanent': is_permanent,
            'expires_at': expires_at.isoformat() + 'Z' if expires_at else None
        }

    def unblock_ip(self, ip_address: str, reason: str) -> Dict[str, Any]:
        # Remove OS-level block FIRST
        self.firewall.unblock_ip(ip_address)

        success = self.alert_repo.unblock_ip(ip_address, reason=reason)
        if not success:
            raise RuntimeError(f"Failed to persist unblock decision for {ip_address}")

        logger.info(f"Enforced unblock: {ip_address} (reason={reason})")
        return {
            'status': 'unblocked',
            'ip_address': ip_address,
            'reason': reason,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

    def is_blocked(self, ip_address: str) -> bool:
        db_blocked = self.alert_repo.is_ip_blocked(ip_address)
        os_blocked = self.firewall.is_blocked(ip_address)
        if db_blocked != os_blocked:
            logger.warning(f"Block state mismatch for {ip_address}: db={db_blocked} os={os_blocked}")
        return db_blocked and os_blocked


class ResponseEngine:
    """Response orchestration (decisioning only)."""

    def __init__(
        self,
        enforcement_service: EnforcementService,
        policy_engine: Optional[PolicyEngine] = None,
        response_repo: Optional[Any] = None,
        ws_notifier: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ):
        self.enforcement = enforcement_service
        self.policy_engine = policy_engine
        self.response_repo = response_repo
        self.ws_notifier = ws_notifier
        self.block_score_threshold = int(os.getenv('RESPONSE_BLOCK_THRESHOLD', '80'))
        self.block_ttl_hours = int(os.getenv('RESPONSE_BLOCK_TTL_HOURS', '24'))
        self.response_mode, self.response_mode_source = resolve_response_mode()

    @staticmethod
    def _extract_source_ip(event: Dict[str, Any]) -> Optional[str]:
        if 'ip_address' in event and isinstance(event['ip_address'], dict):
            return event['ip_address'].get('source')
        return event.get('source_ip')

    def _should_block(self, analysis: Dict[str, Any]) -> bool:
        score = int(analysis.get('threat_score', 0))
        return score >= self.block_score_threshold

    def build_candidate(self, enriched_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        analysis = enriched_event.get('threat_analysis', {})
        source_ip = self._extract_source_ip(enriched_event)
        correlation_id = enriched_event.get('correlation_id')

        if not source_ip or not self._should_block(analysis):
            return None

        reason = analysis.get('analysis_reason', 'Automatic response: severity threshold crossed')

        return {
            'action': 'block_ip',
            'ip_address': source_ip,
            'reason': reason,
            'correlation_id': correlation_id,
            'is_permanent': False,
            'ttl_hours': self.block_ttl_hours,
            'threat_level': analysis.get('threat_level'),
            'metadata': {
                'threat_score': analysis.get('threat_score'),
                'event_id': enriched_event.get('event_id')
            }
        }

    def enforce_response(self, enriched_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        candidate = self.build_candidate(enriched_event)
        if not candidate:
            return None

        source_ip = candidate['ip_address']
        if self.enforcement.is_blocked(source_ip):
            decision_payload = {
                'mode': self.response_mode,
                'decision': 'skipped',
                'action': candidate.get('action'),
                'reason': 'already_blocked',
                'ip_address': source_ip,
                'correlation_id': candidate.get('correlation_id'),
                'event_id': enriched_event.get('event_id'),
                'threat_level': candidate.get('threat_level'),
                'threat_score': (candidate.get('metadata') or {}).get('threat_score'),
                'metadata': candidate.get('metadata')
            }
            self._record_decision(decision_payload)
            return decision_payload

        policy = self.policy_engine or PolicyEngine(self.enforcement.alert_repo)
        policy_decision = policy.evaluate(
            enriched_event,
            correlation_state=enriched_event.get('correlation_state'),
            candidate_action=candidate.get('action', 'block_ip'),
            candidate_reason=candidate.get('reason', 'auto-response')
        )

        if self.response_mode == 'monitor':
            logger.info("Enforcement skipped due to monitor mode")
            decision_payload = {
                'mode': self.response_mode,
                'decision': 'would_block',
                'action': candidate.get('action'),
                'reason': policy_decision.reason,
                'ip_address': source_ip,
                'correlation_id': candidate.get('correlation_id'),
                'event_id': enriched_event.get('event_id'),
                'threat_level': candidate.get('threat_level'),
                'threat_score': (candidate.get('metadata') or {}).get('threat_score'),
                'metadata': candidate.get('metadata')
            }
            self._record_decision(decision_payload)
            return decision_payload

        if policy_decision.action != 'enforce':
            logger.info("Enforcement skipped due to policy decision")
            decision_payload = {
                'mode': policy_decision.mode,
                'decision': 'skipped',
                'action': candidate.get('action'),
                'reason': policy_decision.reason,
                'ip_address': source_ip,
                'correlation_id': candidate.get('correlation_id'),
                'event_id': enriched_event.get('event_id'),
                'threat_level': candidate.get('threat_level'),
                'threat_score': (candidate.get('metadata') or {}).get('threat_score'),
                'metadata': candidate.get('metadata')
            }
            self._record_decision(decision_payload)
            return decision_payload

        try:
            logger.info(f"Enforcement allowed under {policy_decision.mode} mode")
            result = self.enforcement.block_ip(
                ip_address=candidate['ip_address'],
                reason=candidate['reason'],
                correlation_id=candidate.get('correlation_id'),
                is_permanent=candidate.get('is_permanent', False),
                ttl_hours=candidate.get('ttl_hours'),
                threat_level=candidate.get('threat_level'),
                metadata=candidate.get('metadata')
            )
            decision_payload = {
                'mode': policy_decision.mode,
                'decision': 'enforced',
                'action': candidate.get('action'),
                'reason': policy_decision.reason,
                'ip_address': source_ip,
                'correlation_id': candidate.get('correlation_id'),
                'event_id': enriched_event.get('event_id'),
                'threat_level': candidate.get('threat_level'),
                'threat_score': (candidate.get('metadata') or {}).get('threat_score'),
                'metadata': candidate.get('metadata')
            }
            self._record_decision(decision_payload)
            return result
        except Exception as e:
            logger.error(f"Enforcement failed for {source_ip}: {e}")
            decision_payload = {
                'mode': policy_decision.mode,
                'action': 'block_ip',
                'decision': 'failed',
                'ip_address': source_ip,
                'reason': candidate['reason'],
                'error': str(e)
            }
            self._record_decision(decision_payload)
            return decision_payload

    def _record_decision(self, decision_payload: Dict[str, Any]) -> None:
        if self.response_repo:
            try:
                self.response_repo.record_response_decision(decision_payload)
            except Exception:
                logger.warning("Failed to persist response decision")
        if self.ws_notifier:
            try:
                payload = dict(decision_payload)
                payload['mode'] = decision_payload.get('mode') or self.response_mode
                self.ws_notifier('response_decision', payload)
            except Exception:
                logger.warning("Failed to emit response_decision event")

    def unblock_expired(self) -> List[str]:
        expired = self.enforcement.alert_repo.get_expired_blocks()
        unblocked = []
        for ip_address in expired:
            try:
                self.enforcement.unblock_ip(ip_address, reason='TTL expired')
                unblocked.append(ip_address)
            except Exception as e:
                logger.error(f"Failed to unblock expired IP {ip_address}: {e}")
        return unblocked

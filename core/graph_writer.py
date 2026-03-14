import os
import asyncio
import logging
from datetime import datetime, timezone
from neo4j import GraphDatabase, exceptions as neo4j_exceptions

logger = logging.getLogger(__name__)

def get_driver():
    uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "mayasec_neo4j")
    return GraphDatabase.driver(uri, auth=(user, pwd))


def write_attack_event(event: dict):
    """Write a scored attack event to Neo4j synchronously."""
    try:
        data = event.get("data")
        if not isinstance(data, dict):
            data = {}

        source_ip = (
            event.get("source_ip")
            or data.get("source_ip")
            or event.get("ip_address")
            or data.get("ip_address")
        )
        service = (
            event.get("service")
            or data.get("service")
            or event.get("destination")
            or data.get("destination")
            or "unknown"
        )
        score = float(
            event.get("threat_score")
            or data.get("threat_score")
            or event.get("score")
            or data.get("score")
            or 0
        )
        timestamp = event.get("timestamp") or data.get(
            "timestamp", datetime.now(timezone.utc).isoformat()
        )
        ttps = (
            event.get("mitre_ttps")
            or data.get("mitre_ttps")
            or event.get("ttps")
            or data.get("ttps")
            or []
        )
        username = event.get("username") or data.get("username")
        password = event.get("password") or data.get("password")
        event_type = event.get("event_type") or data.get("event_type", "unknown")

        if source_ip is None or str(source_ip).strip() == "":
            logger.warning("Skipping graph write: missing source_ip")
            return

        source_ip = str(source_ip).strip()
        service = str(service or "unknown")
        event_type = str(event_type or "unknown")

        if not isinstance(ttps, list):
            ttps = [ttps] if ttps else []

        driver = get_driver()

        base_query = """
        MERGE (ip:AttackerIP {ip: $source_ip})
        ON CREATE SET ip.first_seen = $timestamp, ip.attack_count = 1
        ON MATCH SET ip.last_seen = $timestamp, ip.attack_count = ip.attack_count + 1

        MERGE (h:HoneypotTarget {service: $service})
        ON CREATE SET h.first_hit = $timestamp

        MERGE (ip)-[r:ATTACKED]->(h)
        ON CREATE SET r.first_score = $score, r.hit_count = 1, r.event_type = $event_type
        ON MATCH SET r.last_score = $score, r.hit_count = r.hit_count + 1
        """

        ttp_query = """
        MERGE (h:HoneypotTarget {service: $service})
        MERGE (m:MITRETechnique {technique_id: $technique_id})
        ON CREATE SET m.name = $technique_id
        MERGE (h)-[:TRIGGERED]->(m)
        """

        credential_query = """
        MERGE (ip:AttackerIP {ip: $source_ip})
        MERGE (c:Credential {username: $username, password: $password})
        MERGE (ip)-[:USED]->(c)
        """

        def _write_tx(tx):
            tx.run(
                base_query,
                source_ip=source_ip,
                service=service,
                score=score,
                timestamp=timestamp,
                event_type=event_type,
            )

            for ttp in ttps:
                if isinstance(ttp, dict):
                    technique_id = ttp.get("technique_id") or ttp.get("id") or ttp.get("name")
                else:
                    technique_id = ttp

                technique_id = str(technique_id).strip() if technique_id is not None else ""
                if not technique_id:
                    continue

                tx.run(
                    ttp_query,
                    service=service,
                    technique_id=technique_id,
                )

            if username and password:
                tx.run(
                    credential_query,
                    source_ip=source_ip,
                    username=str(username),
                    password=str(password),
                )

        with driver.session() as session:
            session.execute_write(_write_tx)

        driver.close()

    except (ValueError, TypeError) as exc:
        logger.exception("Failed parsing attack event for graph write: %s", exc)
    except neo4j_exceptions.Neo4jError as exc:
        logger.exception("Neo4j write failed: %s", exc)
    except Exception as exc:
        logger.exception("Unexpected graph writer error: %s", exc)


def close_driver():
    pass

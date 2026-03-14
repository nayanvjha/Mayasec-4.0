# MAYASEC 4.0: AI-Assisted Deception-First SOC Platform

Mayasec 4.0 is an advanced, multi-service security platform redefining threat detection through active deception, machine learning, and AI-assisted investigation. Moving beyond traditional alerting architectures, Mayasec 4.0 utilizes a stateful **3-Tier Honeypot Response Engine**, **Multi-Tenant Row-Level Security**, and an **AI-driven SOC Copilot** to trap, analyze, and neutralize attackers.

---

## 🚀 Key Features

*   **Active Deception Pipeline:** Traps attackers in dynamically generated sandbox environments.
*   **3-Tier Response Engine:**
    *   *Tier 1 (Rules/ML):* High-speed, low-latency dropping of obvious brute-force or noise.
    *   *Tier 2 (Cached LLM WAF):* AI-assisted WAF for zero-day payloads, utilizing local `Ollama` models and Redis caching.
    *   *Tier 3 (Stateful Honeypot):* Diverts persistent, high-value attackers to the `victim-web` decoy to gather intelligence.
*   **Multi-Tenant Architecture:** Built from the ground up with strict PostgreSQL Row-Level Security (RLS) for true SaaS multi-tenancy.
*   **Graph-Assisted SOC Copilot:** Natural language investigation utilizing `Neo4j` for attack correlation and visualization.
*   **Real-time Event Streaming:** `Redis Streams` power low-latency telemetry ingestion from Edge sensors to core processors.

---

## 🏗️ Platform Architecture

Mayasec 4.0 is designed as a distributed microservice architecture.

```text
Mayasec-4.0-main/
├── docker-compose.yml                # Main platform orchestration
├── mayasec_api.py                    # Control-plane API service (Port 5000)
├── core/                             # Threat correlation & behavioral engine (Port 5001)
├── ingress_proxy/                    # External entrypoint, HTTP proxy, and scoring router (Port 80/443)
├── victim-web/                       # Tier-3 Deception app (Honeypot)
├── ml-service/                       # PyTorch/XGBoost ML scoring API (Port 8001)
├── llm-service/                      # LLM WAF integration (Ollama / OpenAI) (Port 8002)
├── soc-copilot/                      # Graph-RAG AI analyst assistant (Port 8003)
├── frontend/                         # React SOC Dashboard UI (Port 3000)
├── workers/                          # Async workers (Event stream consumer, Report scheduler)
├── migrations/                       # PostgreSQL RLS and schema definitions
└── docs/                             # Architecture and API documentation
```

### 🕸️ Service Topology

| Service | Role | Network Port / Access |
|---|---|---|
| **Ingress Proxy** | Public HTTP/HTTPS gateway, routing logic | `80`, `443` |
| **Mayasec UI** | React-based SOC dashboard | `3000` |
| **Control API** | Control plane (`/api/v1/*`) | `5000` |
| **Core Engine** | Behavioral analysis & correlation | `5001` |
| **ML Service** | Request scoring based on ML models | Internal (`8001`) |
| **LLM Service** | Zero-day payload classifier | `8002` |
| **SOC Copilot** | MAYASEC AI Assistant | `8003` |
| **Victim Web** | Deception decoy backend | Internal (`8080`) |
| **Databases** | Storage Layer | `Postgres (5432)`, `Redis (6379)`, `ClickHouse (8123)`, `Neo4j (7474/7687)`|

---

## 🚦 Data Flow & Threat Detection Pipeline

1.  **Ingestion:** Internet traffic hits the `ingress-proxy`.
2.  **Scoring:** The proxy queries `ml-service` and checks behavioral telemetry.
3.  **Classification:** Ambiguous/suspicious payloads are forwarded to the `llm-service` WAF.
4.  **Routing:**
    *   Clean traffic -> `production-web`.
    *   Malicious traffic -> Diverted to `victim-web` (Honeypot).
5.  **Event Pipeline:** Events are emitted to `Redis Streams`.
6.  **Processing:** `event-worker` consumes the stream, logging to `PostgreSQL` and `Neo4j`.
7.  **Analysis:** The `core` engine correlates events, triggering SOC alerts, visualized in `mayasec-ui`.

---

## 🚀 Quick Start Guide

### 1) Prerequisites
*   Docker & Docker Compose (v2)
*   At least 8 GB RAM (16 GB recommended for running local LLMs via Ollama)

### 2) Configuration
Copy the environment template and verify your credentials:
```bash
cp .env.example .env
```
Ensure `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and `ADMIN_TOKEN` are set. If using OpenAI fallback in the LLM service, provide your `OPENAI_API_KEY`.

### 3) Launch the Platform
Start the entire stack, including all AI and messaging services:
```bash
docker compose up -d --build
```

### 4) Verify Services
```bash
docker compose ps
```
*Wait until all containers show a `(healthy)` status.*

### 5) Access Interfaces
*   **SOC Dashboard (UI):** [http://localhost:3000](http://localhost:3000)
*   **Control API:** [http://localhost:5000](http://localhost:5000)
*   **Neo4j Graph Browser:** [http://localhost:7474](http://localhost:7474)

---

## 🛠️ Operations & Troubleshooting

*   **View Logs:** `docker compose logs -f --tail=100 <service_name>`
*   **Rebuild specific service:** `docker compose up -d --build api`
*   **Run migrations:** `docker compose run --rm migrations python migration_manager.py run`
*   **Total Reset:** `docker compose down -v` (Destroys all volumes and DB states)

*For more in-depth architecture notes, review the `/docs` folder.*

#!/usr/bin/env bash
set -euo pipefail

echo "[MAYASEC] Sensor installer"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required but not found. Install Docker first."
  exit 1
fi

IMAGE="mayasec/sensor:latest"
CONTAINER_NAME="mayasec-sensor"

read -r -p "Enter MAYASEC API URL [http://localhost:5000]: " MAYASEC_API_URL
MAYASEC_API_URL=${MAYASEC_API_URL:-http://localhost:5000}

read -r -p "Enter MAYASEC API Key: " MAYASEC_API_KEY
if [[ -z "${MAYASEC_API_KEY}" ]]; then
  echo "API key is required"
  exit 1
fi

read -r -p "Choose mode (proxy/logtail) [proxy]: " MODE
MODE=${MODE:-proxy}

UPSTREAM_URL=""
LOG_FILE=""

if [[ "${MODE}" == "proxy" ]]; then
  read -r -p "Enter UPSTREAM_URL (example: http://my-app:8080): " UPSTREAM_URL
  if [[ -z "${UPSTREAM_URL}" ]]; then
    echo "UPSTREAM_URL is required for proxy mode"
    exit 1
  fi
elif [[ "${MODE}" == "logtail" ]]; then
  read -r -p "Enter LOG_FILE path (example: /var/log/nginx/access.log): " LOG_FILE
  if [[ -z "${LOG_FILE}" ]]; then
    echo "LOG_FILE is required for logtail mode"
    exit 1
  fi
else
  echo "Invalid mode: ${MODE}"
  exit 1
fi

echo "Pulling ${IMAGE}..."
docker pull "${IMAGE}"

echo "Stopping existing ${CONTAINER_NAME} if present..."
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

RUN_ARGS=(
  -d
  --name "${CONTAINER_NAME}"
  --restart unless-stopped
  -e "MAYASEC_API_URL=${MAYASEC_API_URL}"
  -e "MAYASEC_API_KEY=${MAYASEC_API_KEY}"
  -e "MODE=${MODE}"
)

if [[ "${MODE}" == "proxy" ]]; then
  RUN_ARGS+=(
    -e "UPSTREAM_URL=${UPSTREAM_URL}"
    -p 80:8080
  )
fi

if [[ "${MODE}" == "logtail" ]]; then
  RUN_ARGS+=(
    -e "LOG_FILE=${LOG_FILE}"
    -v "${LOG_FILE}:${LOG_FILE}:ro"
  )
fi

echo "Starting MAYASEC sensor..."
docker run "${RUN_ARGS[@]}" "${IMAGE}"

echo "Done. Sensor container is running as ${CONTAINER_NAME}."
echo "Check logs: docker logs -f ${CONTAINER_NAME}"

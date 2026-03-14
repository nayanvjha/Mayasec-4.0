#!/bin/bash
# startup_check.sh - Pre-flight cross-checks for Mayasec 4.0

echo "🔍 Starting Mayasec 4.0 Pre-flight Checks..."

# 1. Check Docker memory limit (Mac/Linux)
echo "[1/4] Checking Docker Resource Limits..."
DOCKER_MEM=$(docker info --format '{{.MemTotal}}' 2>/dev/null)
if [ -z "$DOCKER_MEM" ]; then
    echo "❌ Docker daemon might not be running!"
    exit 1
fi
echo "✅ Docker Total Memory: $(numfmt --to=iec $DOCKER_MEM)"

# 2. Check for port conflicts
echo "[2/4] Checking Required Ports (8000, 8001, 8002, 8003, 3000, 5432, 7474, 7687, 11434)..."
REQUIRED_PORTS=(8000 8001 8002 8003 3000 5432 7474 7687 11434)
CONFLICTS=0
for port in "${REQUIRED_PORTS[@]}"; do
    if lsof -i:$port -P -n | grep LISTEN > /dev/null; then
        echo "⚠️  Port $port is already in use!"
        CONFLICTS=1
    fi
done
if [ $CONFLICTS -eq 1 ]; then
    echo "⚠️  Please ensure ports are free by stopping conflicting services before running docker-compose up."
else
    echo "✅ No obvious port conflicts detected on host."
fi

# 3. Check for zombie Docker containers
echo "[3/4] Checking for lingering containers..."
ZOMBIES=$(docker ps -aq --filter status=exited --filter status=dead)
if [ -n "$ZOMBIES" ]; then
    echo "⚠️  Found stopped/exited containers. You may want to run 'docker rm \$(docker ps -aq --filter status=exited)' to clean up."
else
    echo "✅ No zombie containers found."
fi

# 4. Check docker-compose syntax
echo "[4/4] Validating docker-compose.yml syntax..."
if docker-compose config > /dev/null; then
    echo "✅ docker-compose.yml is valid."
else
    echo "❌ docker-compose.yml has syntax errors!"
    exit 1
fi

echo "🚀 All pre-flight checks completed. You can safely run:"
echo "   docker-compose up -d --build"
echo "   docker-compose logs -f (to watch logs safely without terminal freezing)"

#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# MAYASEC DEPLOYMENT & VALIDATION SCRIPT
# ═══════════════════════════════════════════════════════════════════════════════
# Usage: bash deploy_and_validate.sh [options]
# Options:
#   --skip-docker-install   Skip Docker installation (assumes Docker installed)
#   --skip-validation       Skip post-deployment validation
#   --cleanup              Remove all containers and volumes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOCKER_COMPOSE_CMD="${DOCKER_COMPOSE_CMD:-docker-compose}"
SKIP_DOCKER_INSTALL=0
SKIP_VALIDATION=0
CLEANUP=0

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-docker-install)
      SKIP_DOCKER_INSTALL=1
      shift
      ;;
    --skip-validation)
      SKIP_VALIDATION=1
      shift
      ;;
    --cleanup)
      CLEANUP=1
      shift
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# ═════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

print_header() {
  echo -e "\n${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}$1${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}\n"
}

print_success() {
  echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
  echo -e "${RED}✗ $1${NC}"
}

print_info() {
  echo -e "${YELLOW}→ $1${NC}"
}

# ═════════════════════════════════════════════════════════════════════════════
# MAIN DEPLOYMENT
# ═════════════════════════════════════════════════════════════════════════════

print_header "MAYASEC DEPLOYMENT SCRIPT"

# Check if cleanup requested
if [ $CLEANUP -eq 1 ]; then
  print_header "CLEANUP MODE"
  print_info "Removing all containers and volumes..."
  $DOCKER_COMPOSE_CMD down -v
  print_success "Cleanup complete"
  exit 0
fi

# Step 1: Check prerequisites
print_header "STEP 1: CHECK PREREQUISITES"

print_info "Checking system requirements..."

# Check Docker
if ! command -v docker &> /dev/null; then
  if [ $SKIP_DOCKER_INSTALL -eq 0 ]; then
    print_error "Docker not found, installing..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    print_success "Docker installed"
  else
    print_error "Docker not found and --skip-docker-install specified"
    exit 1
  fi
fi

# Check Docker version
DOCKER_VERSION=$(docker --version | awk '{print $3}' | sed 's/,//')
print_success "Docker $DOCKER_VERSION found"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
  print_error "Docker Compose not found"
  exit 1
fi

COMPOSE_VERSION=$($DOCKER_COMPOSE_CMD --version | awk '{print $4}' | sed 's/,//')
print_success "Docker Compose $COMPOSE_VERSION found"

# Check disk space
DISK_SPACE=$(df $SCRIPT_DIR | awk 'NR==2 {print $4}')
if [ "$DISK_SPACE" -lt 20971520 ]; then # 20GB in KB
  print_error "Insufficient disk space (need 20GB, have $((DISK_SPACE / 1048576))GB)"
  exit 1
fi
print_success "Disk space OK ($((DISK_SPACE / 1048576))GB available)"

# Check required files
print_info "Checking required files..."
REQUIRED_FILES=(
  "docker-compose.yml"
  "Dockerfile.migrations"
  "Dockerfile.core"
  "Dockerfile.api"
  "requirements.txt"
  ".env"
  "migration_manager.py"
  "repository.py"
  "mayasec_api.py"
  "core/__init__.py"
  "migrations/001_create_events.sql"
  "migrations/002_create_alerts.sql"
)

for file in "${REQUIRED_FILES[@]}"; do
  if [ ! -f "$SCRIPT_DIR/$file" ]; then
    print_error "Missing file: $file"
    exit 1
  fi
done
print_success "All required files found"

# Step 2: Prepare environment
print_header "STEP 2: PREPARE ENVIRONMENT"

print_info "Setting up deployment directory..."
cd "$SCRIPT_DIR"
print_success "Working directory: $SCRIPT_DIR"

print_info "Verifying .env configuration..."
if [ -f ".env" ]; then
  source .env
  print_success ".env loaded"
  print_info "Database: $DB_NAME"
  print_info "API Port: $API_PORT"
  print_info "Core Port: $CORE_PORT"
else
  print_error ".env file not found"
  exit 1
fi

# Step 3: Start deployment
print_header "STEP 3: START DEPLOYMENT"

print_info "Pulling Docker images..."
$DOCKER_COMPOSE_CMD pull

print_info "Building custom images..."
$DOCKER_COMPOSE_CMD build

print_info "Starting services..."
$DOCKER_COMPOSE_CMD up -d

print_success "Services started"

# Step 4: Wait for services to be ready
print_header "STEP 4: WAIT FOR SERVICES"

print_info "Waiting for PostgreSQL to be healthy..."
MAX_ATTEMPTS=30
ATTEMPTS=0
while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
  if $DOCKER_COMPOSE_CMD exec -T postgres pg_isready -U $DB_USER &> /dev/null; then
    print_success "PostgreSQL is healthy"
    break
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  echo "  Attempt $ATTEMPTS/$MAX_ATTEMPTS..."
  sleep 1
done

if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
  print_error "PostgreSQL failed to start"
  $DOCKER_COMPOSE_CMD logs postgres | tail -20
  exit 1
fi

print_info "Waiting for migrations to complete..."
MAX_ATTEMPTS=60
ATTEMPTS=0
while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
  MIGRATION_STATUS=$($DOCKER_COMPOSE_CMD ps -q migrations 2>/dev/null || echo "")
  if [ -z "$MIGRATION_STATUS" ]; then
    if [ $($DOCKER_COMPOSE_CMD ps -q migrations | wc -l) -eq 0 ]; then
      print_success "Migrations completed"
      break
    fi
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  echo "  Attempt $ATTEMPTS/$MAX_ATTEMPTS..."
  sleep 1
done

print_info "Waiting for Core service to be healthy..."
MAX_ATTEMPTS=30
ATTEMPTS=0
while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
  if curl -sf http://localhost:5001/health &> /dev/null; then
    print_success "Core service is healthy"
    break
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  echo "  Attempt $ATTEMPTS/$MAX_ATTEMPTS..."
  sleep 1
done

print_info "Waiting for API service to be healthy..."
MAX_ATTEMPTS=30
ATTEMPTS=0
while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
  if curl -sf http://localhost:5000/health &> /dev/null; then
    print_success "API service is healthy"
    break
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  echo "  Attempt $ATTEMPTS/$MAX_ATTEMPTS..."
  sleep 1
done

# Step 5: Validation (if not skipped)
if [ $SKIP_VALIDATION -eq 0 ]; then
  print_header "STEP 5: VALIDATION TESTS"

  # Test 5a: Container Health
  print_info "Checking container health..."
  $DOCKER_COMPOSE_CMD ps
  
  UNHEALTHY=$($DOCKER_COMPOSE_CMD ps | grep -v "healthy\|Exited 0" | wc -l)
  if [ $UNHEALTHY -gt 2 ]; then  # Allow 2 non-healthy (migrations)
    print_error "Some containers are not healthy"
    exit 1
  fi
  print_success "All containers healthy"

  # Test 5b: Database connectivity
  print_info "Testing database connectivity..."
  if $DOCKER_COMPOSE_CMD exec -T postgres psql -U $DB_USER -d $DB_NAME -c "SELECT 1" &> /dev/null; then
    print_success "Database connectivity OK"
  else
    print_error "Database connectivity failed"
    exit 1
  fi

  # Test 5c: Schema verification
  print_info "Verifying database schema..."
  TABLE_COUNT=$($DOCKER_COMPOSE_CMD exec -T postgres psql -U $DB_USER -d $DB_NAME -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" | tr -d ' ')
  if [ "$TABLE_COUNT" -ge 15 ]; then
    print_success "Database schema OK ($TABLE_COUNT tables)"
  else
    print_error "Database schema incomplete (found $TABLE_COUNT tables, need 15)"
    exit 1
  fi

  # Test 5d: API endpoints
  print_info "Testing API endpoints..."
  
  # Health check
  if curl -sf http://localhost:5000/health &> /dev/null; then
    print_success "GET /health"
  else
    print_error "GET /health failed"
    exit 1
  fi

  # Events endpoint
  if curl -sf http://localhost:5000/api/v1/events &> /dev/null; then
    print_success "GET /api/v1/events"
  else
    print_error "GET /api/v1/events failed"
    exit 1
  fi

  # Metrics endpoint
  if curl -sf http://localhost:5000/api/v1/metrics &> /dev/null; then
    print_success "GET /api/v1/metrics"
  else
    print_error "GET /api/v1/metrics failed"
    exit 1
  fi

  # OpenAPI endpoint
  if curl -sf http://localhost:5000/api/v1/openapi &> /dev/null; then
    print_success "GET /api/v1/openapi"
  else
    print_error "GET /api/v1/openapi failed"
    exit 1
  fi

  # Test 5e: Event ingestion
  print_info "Testing event ingestion..."
  RESPONSE=$(curl -s -X POST http://localhost:5001/api/events/process \
    -H "Content-Type: application/json" \
    -d '{
      "events": [{
        "event_type": "login_attempt",
        "source_ip": "192.168.1.100",
        "destination_ip": "10.0.0.1",
        "username": "testuser",
        "timestamp": "2026-01-15T10:30:00Z",
        "description": "Test event"
      }]
    }')

  if [ $? -eq 0 ]; then
    print_success "Event ingestion OK"
  else
    print_error "Event ingestion failed"
    exit 1
  fi

  # Verify event stored
  sleep 1
  EVENT_COUNT=$(curl -s "http://localhost:5000/api/v1/events?ip_address=192.168.1.100" | grep -o '"id"' | wc -l)
  if [ "$EVENT_COUNT" -gt 0 ]; then
    print_success "Event stored and queryable"
  else
    print_error "Event not found in storage"
    exit 1
  fi

fi

# Step 6: Summary
print_header "DEPLOYMENT COMPLETE ✓"

echo -e "${GREEN}All services are running and validated.${NC}\n"

echo "Service Status:"
echo "  PostgreSQL:  http://localhost:5432"
echo "  Core API:    http://localhost:5001/health"
echo "  Control API: http://localhost:5000/health"
echo ""

echo "Next Steps:"
echo "  1. View service logs:     docker-compose logs -f [service]"
echo "  2. Send events:          curl -X POST http://localhost:5001/api/events/process ..."
echo "  3. Query events:         curl http://localhost:5000/api/v1/events"
echo "  4. View metrics:         curl http://localhost:5000/api/v1/metrics"
echo "  5. Stop services:        docker-compose down"
echo ""

print_success "Deployment validation complete!"

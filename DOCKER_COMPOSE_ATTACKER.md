# Docker Compose Configuration for Attacker Simulator
#
# Add this service to your main docker-compose.yml to run the simulator
# alongside MAYASEC infrastructure.
#
# Usage:
#   # Run only the simulator
#   docker-compose --profile attacker up attacker-simulator
#
#   # Run MAYASEC + simulator together
#   docker-compose --profile attacker up ingestor api attacker-simulator
#
#   # Stop simulator
#   docker-compose --profile attacker down attacker-simulator

version: '3.8'

services:
  attacker-simulator:
    profiles:
      - attacker
    build:
      context: .
      dockerfile: Dockerfile.attacker-simulator
    container_name: mayasec-attacker-simulator
    network_mode: host  # Use host network for ingestor access
    environment:
      # MAYASEC ingestor endpoint
      MAYASEC_INGESTOR_URL: "http://localhost:5001"
      
      # Target IP to attack (simulated victim)
      ATTACKER_TARGET_IP: "192.168.1.100"
      
      # Source IP range for attacker IPs
      ATTACKER_SOURCE_IP: "203.0.113"
      
      # Duration in seconds
      DURATION: "3600"  # 1 hour
      
      # Intensity: low (0.5/sec), medium (2/sec), high (5/sec)
      INTENSITY: "medium"
    
    depends_on:
      - ingestor
    
    restart: unless-stopped
    
    # Resource limits (adjust as needed)
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M
        reservations:
          cpus: '0.25'
          memory: 128M
    
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:5001/health', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    
    # Optional: log everything to file
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    
    labels:
      io.mayasec.component: "attacker-simulator"
      io.mayasec.version: "1.0"

# Alternative configuration for separate VM
# Uncomment to use host network only when running simulator on separate machine:
#
# attacker-simulator-vm:
#   profiles:
#     - attacker
#   build:
#     context: .
#     dockerfile: Dockerfile.attacker-simulator
#   container_name: mayasec-attacker-simulator-vm
#   networks:
#     mayasec:
#       ipv4_address: 172.20.0.50
#   environment:
#     MAYASEC_INGESTOR_URL: "http://mayasec-ingestor:5001"  # Internal network
#     ATTACKER_TARGET_IP: "172.20.0.10"
#     ATTACKER_SOURCE_IP: "203.0.113"
#     DURATION: "3600"
#     INTENSITY: "high"
#   depends_on:
#     - ingestor
#   restart: unless-stopped
#
# networks:
#   mayasec:
#     external: true  # Use existing network

# Quick Start:
#
# 1. Copy this snippet into your docker-compose.yml
# 2. Rebuild images:
#    docker-compose build
#
# 3. Run simulator with MAYASEC:
#    docker-compose --profile attacker up -d ingestor api attacker-simulator
#
# 4. View logs:
#    docker-compose logs -f attacker-simulator
#
# 5. Monitor in SOC console:
#    open http://localhost:3000
#
# 6. Stop simulator:
#    docker-compose down attacker-simulator
#
# Environment Variables to Override:
#   - MAYASEC_INGESTOR_URL: Target ingestor endpoint
#   - ATTACKER_TARGET_IP: IP address to attack
#   - ATTACKER_SOURCE_IP: Source IP range
#   - DURATION: Simulation duration in seconds
#   - INTENSITY: low, medium, or high
#
# Example with overrides:
#   docker-compose --profile attacker up \
#     -e DURATION=600 \
#     -e INTENSITY=high \
#     attacker-simulator

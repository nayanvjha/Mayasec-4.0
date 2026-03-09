#!/bin/bash

# MAYASEC Demo Attack Scenarios
# Quick-start scripts for different attack demonstrations

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TARGET="${1:-http://localhost:5000}"
DASHBOARD_URL="${TARGET/5000/3000}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   MAYASEC Attack Simulation - Demo Scenarios${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}\n"

echo -e "${YELLOW}Target: ${TARGET}${NC}"
echo -e "${YELLOW}Dashboard: ${DASHBOARD_URL}${NC}\n"

# Show available demos
show_menu() {
    echo -e "${GREEN}Available Demos:${NC}\n"
    echo "  1) Quick Demo (60 sec escalating attack)"
    echo "  2) SSH Brute Force (10 attempts)"
    echo "  3) Port Scanning (20 ports)"
    echo "  4) DDoS Attack (50 packets)"
    echo "  5) Malware Detection (3-step sequence)"
    echo "  6) Mixed Attack (5 attempts each)"
    echo "  7) Extended Demo (180 sec escalating)"
    echo "  8) Continuous Testing (3 cycles)"
    echo "  0) Exit"
    echo ""
    read -p "Select demo (0-8): " choice
}

# Demo 1: Quick 60-second escalating attack
demo_quick() {
    echo -e "\n${BLUE}Running: 60-Second Escalating Attack${NC}"
    echo "Phases: Reconnaissance → Brute Force → Exploitation → Critical"
    echo "Watch dashboard for real-time threat escalation!"
    python3 "$SCRIPT_DIR/attack_simulator.py" \
        --target "$TARGET" \
        --scenario escalating \
        --duration 60
}

# Demo 2: SSH Brute Force
demo_ssh() {
    echo -e "\n${BLUE}Running: SSH Brute Force Attack${NC}"
    echo "10 sequential login attempts on port 22"
    python3 "$SCRIPT_DIR/attack_simulator.py" \
        --target "$TARGET" \
        --scenario ssh-brute \
        --intensity 10
}

# Demo 3: Port Scanning
demo_scan() {
    echo -e "\n${BLUE}Running: Network Port Scanning${NC}"
    echo "Scanning 20 common service ports"
    python3 "$SCRIPT_DIR/attack_simulator.py" \
        --target "$TARGET" \
        --scenario port-scan \
        --intensity 20
}

# Demo 4: DDoS Attack
demo_ddos() {
    echo -e "\n${BLUE}Running: DDoS Attack${NC}"
    echo "50 rapid-fire packets from multiple sources"
    python3 "$SCRIPT_DIR/attack_simulator.py" \
        --target "$TARGET" \
        --scenario ddos \
        --intensity 50
}

# Demo 5: Malware Detection
demo_malware() {
    echo -e "\n${BLUE}Running: Malware Detection Sequence${NC}"
    echo "File access → Privilege escalation → Malware signature"
    python3 "$SCRIPT_DIR/attack_simulator.py" \
        --target "$TARGET" \
        --scenario malware
}

# Demo 6: Mixed Attack
demo_mixed() {
    echo -e "\n${BLUE}Running: Mixed Attack Scenario${NC}"
    echo "Combining: Reconnaissance → Brute Force → Invalid Auth → DDoS"
    echo ""
    
    echo "Phase 1: Port Scanning..."
    python3 "$SCRIPT_DIR/attack_simulator.py" \
        --target "$TARGET" \
        --scenario port-scan \
        --intensity 5
    
    sleep 3
    
    echo -e "\n${YELLOW}Phase 2: SSH Brute Force...${NC}"
    python3 "$SCRIPT_DIR/attack_simulator.py" \
        --target "$TARGET" \
        --scenario ssh-brute \
        --intensity 5
    
    sleep 3
    
    echo -e "\n${YELLOW}Phase 3: Invalid Authentication...${NC}"
    python3 "$SCRIPT_DIR/attack_simulator.py" \
        --target "$TARGET" \
        --scenario invalid-auth \
        --intensity 5
    
    sleep 3
    
    echo -e "\n${YELLOW}Phase 4: DDoS Attack...${NC}"
    python3 "$SCRIPT_DIR/attack_simulator.py" \
        --target "$TARGET" \
        --scenario ddos \
        --intensity 20
}

# Demo 7: Extended 180-second escalating
demo_extended() {
    echo -e "\n${BLUE}Running: 180-Second Extended Escalating Attack${NC}"
    echo "Three full 4-phase escalation cycles (3 minutes total)"
    python3 "$SCRIPT_DIR/attack_simulator.py" \
        --target "$TARGET" \
        --scenario escalating \
        --duration 180
}

# Demo 8: Continuous 3-cycle testing
demo_continuous() {
    echo -e "\n${BLUE}Running: Continuous Testing (3 Cycles)${NC}"
    echo "Three consecutive 60-second escalating attacks"
    python3 "$SCRIPT_DIR/attack_simulator.py" \
        --target "$TARGET" \
        --scenario escalating \
        --duration 60 \
        --repeat 3
}

# Main loop
while true; do
    show_menu
    
    case $choice in
        1) demo_quick ;;
        2) demo_ssh ;;
        3) demo_scan ;;
        4) demo_ddos ;;
        5) demo_malware ;;
        6) demo_mixed ;;
        7) demo_extended ;;
        8) demo_continuous ;;
        0) 
            echo -e "\n${GREEN}Goodbye!${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid selection${NC}"
            continue
            ;;
    esac
    
    echo -e "\n${GREEN}✓ Demo complete!${NC}"
    echo -e "${YELLOW}Check dashboard: ${DASHBOARD_URL}${NC}\n"
    read -p "Press Enter to continue..."
done

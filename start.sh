#!/usr/bin/env bash
# start.sh — Launch Scholar Tracker (backend + bridge) in one terminal
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

cleanup() {
    echo -e "\n${RED}Shutting down...${NC}"
    kill $BACKEND_PID $BRIDGE_PID 2>/dev/null
    wait $BACKEND_PID $BRIDGE_PID 2>/dev/null
    echo "Done."
    exit 0
}
trap cleanup SIGINT SIGTERM

# 1. Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "python3 not found"; exit 1; }
command -v node    >/dev/null 2>&1 || { echo "node not found";    exit 1; }
command -v npm     >/dev/null 2>&1 || { echo "npm not found";     exit 1; }

# 2. Setup Python venv if needed
if [ ! -d ".venv" ]; then
    echo -e "${GREEN}Creating Python venv...${NC}"
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -e . --quiet

# 3. Setup Node dependencies if needed
if [ ! -d "bridge/node_modules" ]; then
    echo -e "${GREEN}Installing bridge dependencies...${NC}"
    (cd bridge && npm install)
fi

# 4. Copy .env if missing
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}Created .env from .env.example — edit it if needed${NC}"
fi

# 5. Start backend
echo -e "${GREEN}Starting backend...${NC}"
python3 main.py &
BACKEND_PID=$!
sleep 2

# 6. Start bridge
echo -e "${GREEN}Starting WhatsApp bridge...${NC}"
node bridge/index.js &
BRIDGE_PID=$!

echo -e "${GREEN}Both services running. Press Ctrl+C to stop.${NC}"
wait

#!/usr/bin/env bash
# Install BESS systemd services. Run as root: sudo bash deployment/systemd/install.sh
set -euo pipefail
cd "$(dirname "$0")"

cp bess-simulator.service bess-opc-bridge.service /etc/systemd/system/
systemctl daemon-reload

# Stop any legacy nohup-started processes before systemd takes over
pkill -f "python.*src/simulator/bess.py" || true
pkill -f "python.*src/opcua_bridge/opc_bridge.py" || true
sleep 2

systemctl enable --now bess-simulator.service bess-opc-bridge.service
systemctl --no-pager --lines=0 status bess-simulator.service bess-opc-bridge.service

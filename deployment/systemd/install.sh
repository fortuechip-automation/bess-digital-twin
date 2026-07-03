#!/usr/bin/env bash
# Install BESS systemd services. Run as root:
#   sudo bash deployment/systemd/install.sh [unit ...]
# Default units: bess-simulator bess-opc-bridge (the simulator VM set).
# On the EMS VM run: sudo bash deployment/systemd/install.sh bess-ems
set -euo pipefail
cd "$(dirname "$0")"

UNITS=("${@:-bess-simulator bess-opc-bridge}")
[ $# -gt 0 ] && UNITS=("$@")

for u in ${UNITS[@]}; do
  u="${u%.service}"
  cp "${u}.service" /etc/systemd/system/
done
systemctl daemon-reload

for u in ${UNITS[@]}; do
  u="${u%.service}"
  case "$u" in
    bess-simulator)  pkill -f "python.*src/simulator/bess.py" || true ;;
    bess-opc-bridge) pkill -f "python.*src/opcua_bridge/opc_bridge.py" || true ;;
    bess-ems)        pkill -f "python.*src/ems/ems.py" || true ;;
    bess-api)        pkill -f "uvicorn src.api.main" || true ;;
  esac
done
sleep 2

for u in ${UNITS[@]}; do
  u="${u%.service}"
  systemctl enable --now "${u}.service"
done
systemctl --no-pager --lines=0 status ${UNITS[@]} || true

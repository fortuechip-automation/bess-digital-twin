#!/usr/bin/env bash
set -euo pipefail

if [ ! -f /etc/systemd/system/bess-simulator.service ]; then
  echo "systemd units not installed - run: sudo bash deployment/systemd/install.sh" >&2
  exit 1
fi

sudo systemctl start bess-simulator.service bess-opc-bridge.service
./status_bess_stack.sh

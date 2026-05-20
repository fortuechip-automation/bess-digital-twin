#!/usr/bin/env bash
set -euo pipefail

cd /home/fox/bess-digital-twin

if ! pgrep -f 'python.*src/simulator/bess.py' >/dev/null; then
  nohup ./start_simulator.sh > bess.log 2>&1 &
  echo "Started simulator"
else
  echo "Simulator already running"
fi

if ! pgrep -f 'python.*src/opcua_bridge/opc_bridge.py' >/dev/null; then
  nohup ./start_opc_bridge.sh > opc_bridge.log 2>&1 &
  echo "Started OPC bridge"
else
  echo "OPC bridge already running"
fi

sleep 2
./status_bess_stack.sh

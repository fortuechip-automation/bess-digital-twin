#!/usr/bin/env bash
set -euo pipefail

SIM_PIDS="$(pgrep -f 'python.*src/simulator/bess.py' || true)"
OPC_PIDS="$(pgrep -f 'python.*src/opcua_bridge/opc_bridge.py' || true)"

if [ -n "$SIM_PIDS" ]; then
  kill $SIM_PIDS
  echo "Stopped simulator: $SIM_PIDS"
else
  echo "Simulator not running"
fi

if [ -n "$OPC_PIDS" ]; then
  kill $OPC_PIDS
  echo "Stopped OPC bridge: $OPC_PIDS"
else
  echo "OPC bridge not running"
fi

#!/usr/bin/env bash
set -euo pipefail

ps -eo pid,ppid,cmd | grep -Ei 'python.*(src/simulator/bess.py|src/opcua_bridge/opc_bridge.py)' | grep -v grep || true

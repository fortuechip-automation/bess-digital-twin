#!/usr/bin/env bash
set -euo pipefail

cd /home/fox/bess-digital-twin

if [ ! -f ./config/database.local.env ]; then
  echo "Missing ./config/database.local.env" >&2
  exit 1
fi

if [ ! -f ./config/opcua.local.env ]; then
  echo "Missing ./config/opcua.local.env" >&2
  exit 1
fi

source ./venv/bin/activate
set -a
source ./config/database.local.env
source ./config/opcua.local.env
set +a

exec python3 -u src/opcua_bridge/opc_bridge.py

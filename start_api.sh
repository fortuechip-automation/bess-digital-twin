#!/usr/bin/env bash
set -euo pipefail

cd /home/fox/bess-digital-twin

if [ ! -f ./config/database.local.env ]; then
  echo "Missing ./config/database.local.env" >&2
  exit 1
fi

source ./venv/bin/activate
set -a
source ./config/database.local.env
[ -f ./config/api.local.env ] && source ./config/api.local.env
set +a

exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000

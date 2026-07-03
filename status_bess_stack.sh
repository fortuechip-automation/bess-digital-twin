#!/usr/bin/env bash
set -euo pipefail

systemctl --no-pager --lines=0 status bess-simulator.service bess-opc-bridge.service || true

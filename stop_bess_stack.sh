#!/usr/bin/env bash
set -euo pipefail

sudo systemctl stop bess-simulator.service bess-opc-bridge.service
echo "BESS stack stopped"

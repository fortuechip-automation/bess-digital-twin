# BESS Runtime Runbook

## Current Runtime

The live BESS simulator runs from the project repo:

    /home/fox/bess-digital-twin

Main simulator entrypoint:

    src/simulator/bess.py

OPC bridge entrypoint:

    src/opcua_bridge/opc_bridge.py

The refactored simulator code is now committed in git. The previous simulator directory was backed up locally before the swap:

    /home/fox/bess-digital-twin/backup_pre_refactor_20260520_165935

Do not commit that backup directory.

## SSH Access

From OpenClaw or another host with the configured SSH key:

    ssh bess-simulator

## Helper Scripts

The repo contains these runtime helper scripts:

    start_simulator.sh
    start_opc_bridge.sh
    start_bess_stack.sh
    stop_bess_stack.sh
    status_bess_stack.sh

All commands below assume:

    cd /home/fox/bess-digital-twin

## Check Status

    ./status_bess_stack.sh

Expected output shows the simulator and OPC bridge when both are running:

    python3 -u src/simulator/bess.py
    python src/opcua_bridge/opc_bridge.py

## Start Both Processes

    ./start_bess_stack.sh

This starts both processes detached with nohup if they are not already running.

Logs:

    bess.log
    opc_bridge.log

## Stop Both Processes

    ./stop_bess_stack.sh

This stops:

    python.*src/simulator/bess.py
    python.*src/opcua_bridge/opc_bridge.py

## Start One By One

Start only the simulator:

    nohup ./start_simulator.sh > bess.log 2>&1 &

Start only the OPC bridge:

    nohup ./start_opc_bridge.sh > opc_bridge.log 2>&1 &

Recommended order:

1. Start simulator.
2. Wait a few seconds.
3. Start OPC bridge.

The OPC bridge can run before the simulator, but starting the simulator first gives the bridge fresh database rows immediately.

## Stop One By One

Stop only the simulator:

    pkill -f 'python.*src/simulator/bess.py'

Stop only the OPC bridge:

    pkill -f 'python.*src/opcua_bridge/opc_bridge.py'

## Logs

Simulator log:

    tail -n 40 bess.log

OPC bridge log:

    tail -n 40 opc_bridge.log

## Environment Files

The simulator and OPC bridge use local env files for secrets and host-specific configuration.

Simulator DB env:

    config/database.local.env

OPC env:

    config/opcua.local.env

These files are intentionally ignored by git. Do not commit passwords, tokens, or local credentials.

The simulator launcher loads:

    source ./venv/bin/activate
    source ./config/database.local.env
    python3 -u src/simulator/bess.py

The OPC bridge launcher loads:

    source ./venv/bin/activate
    source ./config/database.local.env
    source ./config/opcua.local.env
    python3 -u src/opcua_bridge/opc_bridge.py

## Data Path

Ignition does not connect directly to bess.py.

Runtime data path:

    bess.py -> PostgreSQL -> opc_bridge.py -> OPC UA -> Ignition tags -> Perspective dashboard

If the simulator restarts but the OPC bridge remains running, Ignition may not flicker or show a disconnect. The OPC server can remain connected while values briefly hold or resume from fresh database rows.

## Validation Performed

The refactor was validated with:

    ./venv/bin/python -m pytest -q

Result:

    6 passed

Live validation after deployment confirmed:

    Fresh telemetry
    Command processing works
    P_set follows command input
    P_actual follows setpoint
    Mode updates correctly
    No active alarms
    OPC bridge publishes live nodes

Known good observed state:

    P_set: 28 kW
    P_actual: about 27.16 kW
    Mode: CHARGE
    SOC: about 49.9 %
    Alarms: none
    Freshness: FRESH

## Useful Follow-Ups

Recommended next improvements:

1. Add a freshness indicator to Ignition: last_update, telemetry_age_seconds, or simulator_status.
2. Convert the helper scripts into systemd services once the refactor is trusted for longer running.
3. Keep /home/fox/bess-digital-twin as the single source of truth and avoid maintaining a second live copy under /opt/bess_sim.


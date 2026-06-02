# Current Project Status

The BESS digital twin currently supports a working simulator → PostgreSQL → OPC UA → Ignition SCADA loop.

## Confirmed Working

- Python BESS fleet simulator runs on the `bess-simulator` VM
- Simulator models site-level telemetry, inverters, and batteries
- PostgreSQL stores live site, inverter, battery, alarm, and command data
- OPC UA bridge starts on port `4840`
- OPC UA bridge reads latest telemetry from PostgreSQL
- Ignition SCADA dashboard displays live BESS values
- Ignition can send setpoint and mode commands back to the simulator
- Simulator receives the commands and updates site mode, actual power, current, voltage, temperature, and SOC
- Ignition dashboard command controls have been tested for both charging and discharging
- Site-level trend chart design is documented for SOC, power, voltage, current, and temperature

## Confirmed Data Flow

    Ignition SCADA
          ↓
    OPC UA command write
          ↓
    OPC UA bridge
          ↓
    PostgreSQL bess_commands table
          ↓
    Python BESS simulator
          ↓
    PostgreSQL telemetry tables
          ↓
    OPC UA bridge reads latest values
          ↓
    Ignition SCADA dashboard updates

## Example Test

A 9 kW charge command was sent from Ignition.

Observed simulator response:

- `P_set` changed to `9.0 kW`
- `P_actual` changed to approximately `8.7 kW`
- Current increased to approximately `10.9 A`
- Mode changed from `IDLE` to `CHARGE`
- Ignition dashboard displayed `CHARGING`

Example simulator output:

    COMMAND RECEIVED: P_set=9.0kW, Mode=CHARGE
    COMMAND EXECUTED: P_set=9.0 kW, Mode=CHARGE
    SITE → SOC=50.18% | P_set=9.0 kW | P_actual=8.7 kW | I=10.9 A | Mode=2 (CHARGE)

## Latest Dashboard Evidence

The current Ignition dashboard evidence shows the live control loop in a later charge-command state:

![Ignition dashboard 16 kW charge response](assets/screenshots/evidence/ignition-dashboard-16kw-charge-response.jpg)

Observed values from the screenshot:

- `SOC`: 50.24%
- `Mode`: CHARGING
- `P_set`: 16 kW
- `P_actual`: 15.52 kW
- `Command status`: SENT
- `Active alarms`: 0

Latest command-control testing is summarized in [progress/2026-06-02_ignition_dashboard_command_summary.md](progress/2026-06-02_ignition_dashboard_command_summary.md).

Confirmed behaviour from the dashboard:

- Charging produces positive `P_actual_kW`
- Discharging produces negative `P_actual_kW`
- `P_set_kW` remains positive while mode determines the operating direction
- The Apply button writes the selected mode value and a matching `lastCommand` string

## Trend Chart Plan

The first-pass Ignition trend-chart design is documented in [progress/2026-05-27_ignition_trend_charts.md](progress/2026-05-27_ignition_trend_charts.md).

The recommended implementation uses two operator-facing charts:

- Site power trend: `SOC`, `P_set_kW`, and `P_actual_kW`
- Electrical diagnostics trend: `Vdc`, `Idc`, and `Temp_C`

The reliable historical source is PostgreSQL `site_status`, which already stores one site-level row per simulator cycle.

## Current System Components

| Component | Status |
|---|---|
| BESS simulator | Working |
| PostgreSQL database | Working |
| OPC UA bridge | Working |
| Ignition SCADA dashboard | Working |
| Ignition trend chart design | Ready to build |
| Ignition command path | Working |
| Ignition charge/discharge controls | Working |
| Alarm table | Working |
| Secrets management via local env files | Working |
| AI assistant | Not started |
| Containerised deployment | Planned |

## Next Improvements

- Build the documented Ignition trend charts and capture screenshot evidence
- Fix the currently blank trend chart binding/history path
- Clean command handling so setpoint and mode changes create one clean command
- Add more alarm scenarios
- Add inverter and battery detail pages
- Add trend charts for SOC, power, voltage, and current

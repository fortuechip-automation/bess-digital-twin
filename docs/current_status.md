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
- Site-level trend tabs are built for Power, SOC, and DC Electrical telemetry
- Stage 1 site alarms use separate warning and critical thresholds with hysteresis
- `SITE_POWER_SHORTFALL` uses a five-cycle debounce and clears when the mismatch recovers or the site returns to idle
- Controlled live alarm injection supports SOC, temperature, DC voltage, DC current, and power-shortfall scenarios
- Informational events are stored as cleared history records and do not increase the active alarm count

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

## Trend Chart Evidence

The first-pass Ignition trend implementation is built and documented in [progress/2026-05-27_ignition_trend_charts.md](progress/2026-05-27_ignition_trend_charts.md).

The dashboard now separates site history into operator-facing tabs:

- Power
- SOC
- DC Electrical

![Ignition dashboard split trend tabs during discharge](assets/screenshots/evidence/ignition-dashboard-split-trends-discharge.jpg)

Observed values from the trend evidence screenshot:

- `SOC`: 94.33%
- `Actual mode`: DISCHARGING
- `P_set`: 15 kW
- `P_actual`: -15 kW
- `Vdc`: approximately 835.44 V
- `Command status`: SENT
- `Last command`: DISCHARGE 15.0 kW

The reliable historical source remains PostgreSQL `site_status`, which stores one site-level row per simulator cycle.

## Alarm Model Status

Stage 1 of the realistic alarm model is implemented.

Implemented site-level alarms:

- `SOC_HIGH` and `SOC_CRITICAL_HIGH`
- `SOC_LOW` and `SOC_CRITICAL_LOW`
- `TEMP_HIGH` and `TEMP_CRITICAL`
- `DC_BUS_HIGH` and `DC_BUS_LOW`
- `CURRENT_HIGH` and `CURRENT_CRITICAL`
- `SITE_POWER_SHORTFALL`

Warning and critical alarms can coexist, allowing the dashboard to show both the developing condition and the more serious threshold. Process alarms self-clear only after crossing their hysteresis clear threshold, which prevents alarm chatter near a limit.

Legacy noisy alarm codes are cleared by the Stage 1 checks. Startup, shutdown, command, and alarm-test lifecycle records remain informational events rather than active alarms.

The live test hook uses the PostgreSQL `alarm_test_injections` table and currently supports:

- `FORCE_SOC`
- `FORCE_TEMP`
- `FORCE_VDC`
- `FORCE_IDC`
- `FORCE_POWER_SHORTFALL`

Injections are explicit, time-limited, and applied through the normal simulator → PostgreSQL → OPC UA → Ignition data path. Random fault generation is not enabled.

Detailed design and test notes:

- [Alarm model design](progress/2026-06-05_alarm_model_design.md)
- [Stage 1 alarm test plan](progress/2026-06-05_stage1_alarm_test_plan.md)
- [Live alarm test hook design](progress/2026-06-05_live_alarm_test_hook_design.md)

Latest automated validation on 2026-06-24:

```text
17 passed in 2.89s
```

## Current System Components

| Component | Status |
|---|---|
| BESS simulator | Working |
| PostgreSQL database | Working |
| OPC UA bridge | Working |
| Ignition SCADA dashboard | Working |
| Ignition split trend tabs | Working |
| Ignition command path | Working |
| Ignition charge/discharge controls | Working |
| Alarm table | Working |
| Stage 1 alarm model and test injection | Working |
| Secrets management via local env files | Working |
| AI assistant | Not started |
| Containerised deployment | Planned |

## Next Improvements

- Refine trend chart styling, axes, and operator labels
- Add Stage 2 inverter, battery, and fleet-level alarm scenarios
- Design latched trip, acknowledgement, manual-reset, and command-inhibit behaviour
- Add an Ignition alarm table and controlled operator-facing test controls
- Add inverter and battery detail pages

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

## Confirmed Data Flow

```text
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

Example Test

A 9 kW charge command was sent from Ignition.

Observed simulator response:

P_set changed to 9.0 kW
P_actual changed to approximately 8.7 kW
Current increased to approximately 10.9 A
Mode changed from IDLE to CHARGE
Ignition dashboard displayed CHARGING

Example simulator output:
COMMAND RECEIVED: P_set=9.0kW, Mode=CHARGE
COMMAND EXECUTED: P_set=9.0 kW, Mode=CHARGE
SITE → SOC=50.18% | P_set=9.0 kW | P_actual=8.7 kW | I=10.9 A | Mode=2 (CHARGE)

| Component                              | Status      |
| -------------------------------------- | ----------- |
| BESS simulator                         | Working     |
| PostgreSQL database                    | Working     |
| OPC UA bridge                          | Working     |
| Ignition SCADA dashboard               | Working     |
| Ignition command path                  | Working     |
| Alarm table                            | Working     |
| Secrets management via local env files | Working     |
| AI assistant                           | Not started |
| Containerised deployment               | Planned     |

Next Improvements
Save screenshots of Ignition dashboard
Save sample terminal logs as evidence
Improve dashboard layout and visual consistency
Clean command handling so setpoint and mode changes create one clean command
Add more alarm scenarios
Add inverter and battery detail pages
Add trend charts for SOC, power, voltage, and current

# Ignition Charge Command Test

## Test Summary

Ignition was used to send a 9 kW charge command to the BESS simulator through the OPC UA bridge.

## Result

The command was successfully received by the simulator and executed.

## Observed Behaviour

- Site mode changed from `IDLE` to `CHARGE`
- Setpoint changed to `9.0 kW`
- Actual power changed to approximately `8.7 kW`
- Current increased to approximately `10.9 A`
- Ignition dashboard displayed `CHARGING`

## Example Output

```text
COMMAND RECEIVED → P_set=9.0kW, Mode=CHARGE
COMMAND EXECUTED → P_set=9.0 kW, Mode=CHARGE
SITE → SOC=50.18% | P_set=9.0 kW | P_actual=8.7 kW | Vdc=800.1 V | I=10.9 A | Mode=2 (CHARGE)

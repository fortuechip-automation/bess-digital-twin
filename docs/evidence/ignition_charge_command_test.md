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

    COMMAND RECEIVED → P_set=9.0kW, Mode=CHARGE
    COMMAND EXECUTED → P_set=9.0 kW, Mode=CHARGE
    SITE → SOC=50.18% | P_set=9.0 kW | P_actual=8.7 kW | Vdc=800.1 V | I=10.9 A | Mode=2 (CHARGE)

## Dashboard Evidence

The later Ignition dashboard capture shows the same command path working from the operator display:

![Ignition dashboard 16 kW charge response](../assets/screenshots/evidence/ignition-dashboard-16kw-charge-response.jpg)

Visible values:

- `SOC`: 50.24%
- `Mode`: CHARGING
- `P_set`: 16 kW
- `P_actual`: 15.52 kW
- `Vdc`: 799.97 V
- `Temperature`: 25.04 C
- `Active alarms`: 0

## Notes

The command path is functional from Ignition to the simulator.

A minor improvement is needed later: Ignition or the OPC UA bridge currently appears to create separate command records for setpoint and mode changes. This can be cleaned up in a future update.

# Ignition Dashboard Command Summary

## Goal

Capture the current state of the Ignition Perspective BESS dashboard work, especially the command controls and the charge/discharge behaviour confirmed during live testing.

## What Has Been Built

- Main BESS dashboard showing site KPIs for SOC, operating mode, active alarms, power setpoint, actual power, DC voltage, DC current, temperature, and command state.
- Operator control panel with:
  - Power setpoint input.
  - Mode dropdown for idle, charging, and discharging.
  - Apply command button.
- Command status display showing the last command sent from Perspective.
- Alarm summary showing the active alarm count.
- Trend chart area prepared on the dashboard, though chart data is not yet displaying correctly.

## Apply Button Logic

The Apply button reads values from sibling components:

- `PowerSetpoint.props.value`
- `ModeDropdown.props.value`

It then writes the following tags:

| Tag | Purpose |
|---|---|
| `[default]BESS1/Site/P_set_kW` | Requested power setpoint |
| `[default]BESS1/Site/Mode` | Requested operating mode |
| `[default]BESS1/Site/ApplyCommand` | Command trigger flag |
| `[default]BESS1/Commands/commandStatus` | Operator-facing command status |
| `[default]BESS1/Commands/lastCommand` | Operator-facing command summary |

The confirmed mode mapping is:

| Dropdown value | Mode text |
|---|---|
| `1` | `IDLE` |
| `2` | `CHARGE` |
| `3` | `DISCHARGE` |

The button script uses `abs(float(p_set))`, so the operator enters a positive setpoint and the simulator applies the sign convention based on mode.

## Confirmed Behaviour

Live dashboard testing confirmed both sides of the command path:

- A charge command produced positive actual power.
- A discharge command produced negative actual power.
- `lastCommand` matched the selected dropdown mode after the dropdown value mapping was checked.
- `P_set_kW` remained positive for both charging and discharging.
- `P_actual_kW` changed sign according to operating mode.

Observed discharge state from the dashboard:

- Actual mode: `DISCHARGING`
- `P_set`: approximately `25 kW`
- `P_actual`: approximately `-24.99 kW`
- `Vdc`: approximately `800 V`
- Temperature: approximately `24 C`
- Last command: `DISCHARGE 25.0 kW`

This confirms the intended sign convention:

- Charging = positive `P_actual_kW`
- Discharging = negative `P_actual_kW`

## Issue Found And Resolved

During testing, the dashboard appeared to show `DISCHARGING` selected while the command status still showed a charge command. The likely cause was a mismatch between the dropdown visible label and its underlying `props.value`.

The important check was that `ModeDropdown.props.options` and `ModeDropdown.props.value` must use this mapping:

```python
[
    {"label": "IDLE", "value": 1},
    {"label": "CHARGING", "value": 2},
    {"label": "DISCHARGING", "value": 3}
]
```

After confirming the mapping, the dashboard showed a correct discharge response.

## Remaining Work

- Fix the blank trend chart area. The likely cause is tag history, binding, query, or time range configuration rather than the command script.
- Prefer PostgreSQL-backed history from `site_status` for reliable trend data unless Ignition tag history is explicitly configured and verified.
- Capture final screenshot evidence once the trend chart displays SOC, setpoint, and actual power.
- Consider adding a debug print for the selected mode value in the Apply button script while commissioning:

```python
system.perspective.print("Apply mode value: " + str(mode))
```


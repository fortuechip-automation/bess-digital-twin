# Ignition Dashboard Progress Update

## Summary

Today’s work focused on improving the Ignition Perspective BESS SCADA dashboard and beginning the inverter fleet overview page.

## Completed

- Improved the main BESS dashboard layout and site overview presentation.
- Confirmed the main Perspective route `/` points to `BESS1_MainPage`.
- Created a new Perspective route:

  `/inverters → InvertersOverview`

- Started building the `InvertersOverview` page.
- Created the first inverter overview card for `INV01`.
- Added live inverter telemetry display for:
  - Actual power
  - Power setpoint
  - Mode
  - Temperature
  - DC voltage
  - Fault/status indication

## Display Formatting

Added expression bindings to improve display readability:

- Actual power formatted to one decimal place with `kW`
- Power setpoint formatted to one decimal place with `kW`
- Temperature formatted with `°C`
- Voltage formatted with `V`
- Mode displayed as readable text instead of only numeric values

## UI Improvements

The `INV01` card now includes:

- Dark SCADA-style card background
- Inverter name/title
- Green/red status indicator
- Large actual power display
- Supporting values for temperature, mode, setpoint, and DC voltage
- Separator line between primary and secondary values

## Notes

Ignition Perspective 8.3.1 Designer showed limitations with dragging and pasting components into existing containers. A practical workflow was adopted using manually placed Coordinate Containers and direct component placement.

The completed `INV01` card will be used as the master template for the remaining inverter cards.

## Next Steps

- Duplicate `INV01` card for `INV02` to `INV10`
- Update each copied card’s tag bindings to the correct inverter ID
- Add navigation from the main dashboard to `/inverters`
- Create a `BatteriesOverview` page for `BAT01` to `BAT20`
- Add dedicated charts and alarms pages

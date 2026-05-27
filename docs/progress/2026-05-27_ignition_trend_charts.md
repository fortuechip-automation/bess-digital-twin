# Ignition Trend Charts First Pass

## Goal

Add operator-facing trend charts to the main Ignition Perspective dashboard so the lab can show BESS behaviour over time, not only the latest live values.

The first pass should cover:

- SOC
- power setpoint
- actual power
- DC bus voltage
- DC current
- temperature

## Data Source

The simulator already writes one site-level telemetry row per second to `site_status`.

Relevant columns:

| Trend | Source column |
|---|---|
| SOC | `site_status.soc` |
| Power setpoint | `site_status.p_set_kw` |
| Actual power | `site_status.p_actual_kw` |
| DC voltage | `site_status.vdc` |
| DC current | `site_status.idc` |
| Temperature | `site_status.temp_c` |
| Mode context | `site_status.mode` |
| Timestamp | `site_status.ts` |

The OPC UA bridge also exposes the matching live site tags under `BESS1/Site`:

- `SOC`
- `P_set_kW`
- `P_actual_kW`
- `Vdc`
- `Idc`
- `Temp_C`
- `Mode`

## Recommended Ignition Layout

Use two charts rather than one overloaded chart.

### Site Power Trend

Component name: `chSitePowerTrend`

Suggested placement:

- Put it in the existing SITE TREND area below the KPI row.
- Give it the full available width.
- Use a height of roughly 280-340 px on desktop.

Pens:

| Pen | Axis | Style |
|---|---|---|
| `SOC` | right axis, percent | steady line |
| `P_set_kW` | left axis, kW | dashed or thinner line |
| `P_actual_kW` | left axis, kW | solid line |

Reasoning:

- `P_set_kW` vs `P_actual_kW` proves the command path and simulated plant response.
- SOC on the secondary axis shows the energy state changing over time without flattening the power traces.

### Electrical Diagnostics Trend

Component name: `chSiteElectricalTrend`

Suggested placement:

- Put it below `chSitePowerTrend`, or on a Diagnostics tab if the main page becomes crowded.
- Keep it wide and relatively shallow.

Pens:

| Pen | Axis | Style |
|---|---|---|
| `Vdc` | left axis, V | solid line |
| `Idc` | right axis, A | solid line |
| `Temp_C` | optional right axis, C | thin line |

Reasoning:

- Voltage/current/temperature are diagnostic signals, not primary operator controls.
- Keeping them separate from SOC and power makes the main trend readable.

## Historical Binding Approach

Prefer PostgreSQL history from `site_status` for these charts.

Avoid relying only on browsed OPC tags for history until Ignition tag history is explicitly configured and visible in the correct provider. A previous dashboard attempt showed the chart browsing `Sample_SQLite_Database / ignition-ignition-scada:default` without the expected BESS tags, so the first reliable path is a SQL-backed chart or named query using `site_status`.

Suggested SQL for a recent-history query:

```sql
SELECT
    ts,
    soc,
    p_set_kw,
    p_actual_kw,
    vdc,
    idc,
    temp_c,
    mode
FROM site_status
WHERE ts >= now() - (:minutes || ' minutes')::interval
ORDER BY ts;
```

Suggested default parameter:

```text
minutes = 30
```

## Acceptance Check

The trend feature is working when:

- The dashboard shows at least 30 minutes of SOC, setpoint, and actual power history.
- A charge/discharge command visibly changes `P_set_kW` first and `P_actual_kW` follows.
- SOC moves slowly in the expected direction during charge/discharge.
- Voltage/current/temperature appear in a separate diagnostic chart or tab.
- The chart fills the useful page width in the Perspective client instead of sitting in a narrow fixed-width area.

## Follow-Up

After the first chart is visible, capture a screenshot during a command response and add it to the evidence section of the README.

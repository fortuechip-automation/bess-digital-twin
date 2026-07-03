# BESS API Learning Guide — REST & JSON hands-on

The API service (`src/api/`) exposes the live BESS data as JSON over HTTP.
It runs on the EMS VM: **http://192.168.1.72:8000/docs**

## Stage 1 — Explore (no code)

Open `/docs` in a browser. This is Swagger UI, generated automatically from
the code. For each endpoint: click it → "Try it out" → "Execute" and study:

- the **request** it built (URL, query parameters, headers)
- the **response body** (live JSON from your plant) and **status code**

Things to try:

1. `GET /api/site/status` — a single JSON *object*. Note the types: numbers
   (`soc`), strings (`mode`, `ts` as ISO-8601 timestamp), integer (`active_alarms`).
2. `GET /api/batteries` — an *envelope object* containing a JSON *array* of 20
   objects. Envelopes (`{"count": ..., "batteries": [...]}`) are how real APIs
   leave room for pagination/metadata later.
3. `GET /api/ems/decisions?limit=3` — change `limit` to 0 or 9999 and watch the
   **422** validation error. The API rejects bad input *before* your code runs.
4. `POST /api/commands` — first without a key → **401**. Then with the key from
   `config/api.local.env` in the X-API-Key field, body:
   `{"mode": "CHARGE", "p_set_kw": 25}` → **201** and watch the Ignition
   dashboard / `bess.log` react. Try `{"mode": "TURBO"}` → **422**.

Same thing from the command line:

```bash
curl -s http://192.168.1.72:8000/api/site/status | python3 -m json.tool
curl -s "http://192.168.1.72:8000/api/ems/decisions?limit=5" | python3 -m json.tool
curl -s -X POST http://192.168.1.72:8000/api/commands \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BESS_API_KEY" \
  -d '{"mode":"DISCHARGE","p_set_kw":80}'
```

### Status codes you will meet
| Code | Meaning | Where you'll see it |
|---|---|---|
| 200 | OK | every successful GET |
| 201 | Created | successful POST /api/commands |
| 401 | Unauthorized | POST without/with wrong X-API-Key |
| 404 | Not found | data that doesn't exist |
| 422 | Validation error | bad query params or JSON body |
| 501 | Not implemented | the exercise endpoints — your homework |
| 503 | Service unavailable | server missing configuration |

## Stage 2 — Implement the exercises

Three endpoints in `src/api/main.py` raise **501** on purpose. Each has
acceptance criteria in its docstring. Suggested order:

1. **`GET /api/health`** (warm-up) — return a dict, learn try/except around DB calls
2. **`GET /api/batteries/{id}/history`** — path params + WHERE with parameters + 404
3. **`GET /api/alarms?active=true`** — optional boolean filter

Workflow on the EMS VM:

```bash
ssh bems
cd ~/bess-digital-twin
nano src/api/main.py               # implement an exercise
sudo systemctl restart bess-api    # reload
# then refresh /docs and test it
```

When an exercise passes its criteria, commit it — that's the portfolio trail.

## Stage 3 & 4 — next up
- Consume a real external API (AEMO prices / weather) — you become the client
- Webhook push on CRITICAL alarms — you design the payload

## JSON crib sheet
- **object** `{"key": value}` — keys always double-quoted strings
- **array** `[a, b, c]` — ordered list
- values: string, number, `true`/`false`, `null`, object, array (nesting!)
- no comments, no trailing commas, only double quotes — the parser is strict
- timestamps aren't a JSON type; APIs use ISO-8601 strings (`2026-07-03T20:45:05+10:00`)

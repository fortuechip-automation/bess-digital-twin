"""BESS Digital Twin REST API - Stage 1 learning scaffold.

Run:      ./start_api.sh          (or: uvicorn src.api.main:app --host 0.0.0.0 --port 8000)
Explore:  http://<host>:8000/docs (interactive Swagger UI - your main playground)

The endpoints marked EXERCISE return 501 Not Implemented - they are yours
to build. Copy the pattern from a working endpoint above them, and check
docs/api_learning_guide.md for hints and acceptance criteria.
"""

import os
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query
from pydantic import BaseModel, Field

try:
    from . import db
except ImportError:
    import db

MODE_NAMES = {1: "IDLE", 2: "CHARGE", 3: "DISCHARGE"}

app = FastAPI(
    title="BESS Digital Twin API",
    version="0.1.0",
    description=(
        "REST + JSON interface to the BESS simulator. "
        "Reads are open; writing commands requires the X-API-Key header. "
        "Endpoints marked EXERCISE are unimplemented on purpose - they're the Stage 2 homework."
    ),
)


# =========================================================
#  AUTH (used by POST endpoints only)
# =========================================================
def require_api_key(x_api_key: str = Header(default="", description="API key for write access")):
    expected = os.getenv("BESS_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Server has no BESS_API_KEY configured")
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


# =========================================================
#  REFERENCE ENDPOINTS (working - study these)
# =========================================================
@app.get("/api/site/status", tags=["site"])
def site_status():
    """Latest site-level telemetry, one JSON object."""
    row = db.fetch_one(
        """
        SELECT ts, soc, mode, p_set_kw, p_actual_kw, vdc, idc, temp_c, active_alarms
        FROM site_status
        ORDER BY ts DESC
        LIMIT 1
        """
    )
    if row is None:
        raise HTTPException(status_code=404, detail="No site telemetry found")
    row["mode"] = MODE_NAMES.get(row["mode"], f"UNKNOWN({row['mode']})")
    return row


@app.get("/api/batteries", tags=["fleet"])
def batteries():
    """Latest reading for every battery - a JSON array wrapped in an envelope."""
    rows = db.fetch_all(
        """
        SELECT DISTINCT ON (battery_id)
               battery_id, ts, soc, vdc, idc, p_dc_kw, temp_c, fault
        FROM battery_status
        ORDER BY battery_id, ts DESC
        """
    )
    return {"count": len(rows), "batteries": rows}


@app.get("/api/prices/current", tags=["market"])
def current_price():
    """The market price for the current 5-minute dispatch interval."""
    row = db.fetch_one(
        """
        SELECT interval_start, price_per_mwh, region
        FROM market_prices
        ORDER BY interval_start DESC
        LIMIT 1
        """
    )
    if row is None:
        raise HTTPException(status_code=404, detail="No market prices yet - is the EMS running?")
    return row


@app.get("/api/ems/decisions", tags=["ems"])
def ems_decisions(
    limit: int = Query(default=20, ge=1, le=500, description="How many recent decisions"),
):
    """Recent EMS decisions with their reasoning. Try changing ?limit= in /docs."""
    rows = db.fetch_all(
        """
        SELECT decision_id, ts, command_fk, current_soc, target_soc, reasoning
        FROM ems_decisions
        ORDER BY ts DESC
        LIMIT %s
        """,
        (limit,),
    )
    return {"count": len(rows), "decisions": rows}


class CommandRequest(BaseModel):
    """JSON body for POST /api/commands - pydantic validates it for you.

    Send an invalid body in /docs (mode "TURBO", p_set_kw 999) and watch
    the API answer 422 with a JSON error explaining exactly what's wrong.
    """

    mode: Literal["CHARGE", "DISCHARGE", "IDLE"]
    p_set_kw: float = Field(default=0.0, ge=0.0, le=250.0,
                            description="Unsigned power magnitude in kW (site limit 250)")


@app.post("/api/commands", status_code=201, tags=["control"],
          dependencies=[Depends(require_api_key)])
def create_command(cmd: CommandRequest):
    """Send a site command to the simulator (requires X-API-Key).

    Commands are written with operator priority (1), so the EMS stands
    down for its hold-off window afterwards - you are the operator here.
    """
    row = db.execute_returning(
        """
        INSERT INTO bess_commands (ts, p_set_kw, mode_set, priority, processed)
        VALUES (now(), %s, %s, 1, FALSE)
        RETURNING command_id, ts, p_set_kw, mode_set
        """,
        (cmd.p_set_kw, cmd.mode),
    )
    row["note"] = "Command queued - the simulator polls every second. EMS holds off after manual commands."
    return row


# =========================================================
#  EXERCISES (Stage 2 - implement these yourself)
# =========================================================
@app.get("/api/batteries/{battery_id}/history", tags=["exercises"])
def battery_history(
    battery_id: int = Path(ge=1, le=20, description="Battery number 1-20"),
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=500, ge=1, le=5000),
):
    """EXERCISE 1: return time-series history for one battery.

    Acceptance criteria (see docs/api_learning_guide.md):
      - Returns rows from battery_status for this battery_id newer than now() - hours
      - Newest first, at most `limit` rows
      - 404 with a helpful message if the battery has no data
      - Envelope: {"battery_id": ..., "count": ..., "history": [...]}

    Hint: copy the shape of ems_decisions() above; your SQL needs a WHERE
    with two conditions and two %s parameters.
    """
    rows = db.fetch_all(
        """
        SELECT ts, soc, vdc, idc, p_dc_kw, temp_c, fault
        FROM battery_status
        WHERE battery_id = %s
          AND ts > now() - interval '1 hour' * %s
        ORDER BY ts DESC
        LIMIT %s
        """,
        (battery_id, hours, limit),                      # blank 1: three values, in %s order
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data found for battery_id {battery_id}")
    return {"battery_id": battery_id, "count": len(rows), "history": rows}   # blanks 3 & 4



@app.get("/api/alarms", tags=["exercises"])
def alarms(
    active: bool | None = Query(default=None, description="true = only uncleared alarms"),
    limit: int = Query(default=50, ge=1, le=500),
):
    """EXERCISE 2: list alarms, optionally filtered to active ones.

    Acceptance criteria:
      - No filter: newest `limit` alarms from bess_alarms
      - ?active=true: only cleared = FALSE rows
      - ?active=false: only cleared = TRUE rows
      - Envelope: {"count": ..., "alarms": [...]}

    Hint: build the SQL conditionally, or use
    "WHERE (%s::boolean IS NULL OR cleared = NOT %s::boolean)".
    """
    raise HTTPException(status_code=501, detail="EXERCISE 2: not implemented yet - your turn!")


@app.get("/api/health", tags=["exercises"])
def health():
    """EXERCISE 3 (warm-up): return {"status": "ok", "db": true/false}.

    Try db.fetch_one("SELECT 1 AS ok") in a try/except - report whether
    the database is reachable instead of crashing.
    """
    try:
        db.fetch_one("SELECT 1 AS ok")
        return {"status": "ok", "db": True}      # blank 1
    except Exception:
        return {"status": "ok", "db": False}      # blank 2

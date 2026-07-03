"""Simulated AEMO NEM-style 5-minute market price feed.

Generates a deterministic price series (seeded per interval) with a realistic
daily shape: overnight trough, morning and evening peaks, a midday solar dip
with occasional negative prices, and rare high-price spike events.

Prices are stored in the market_prices table so SCADA and the EMS share one
auditable signal.
"""

import math
import random
from datetime import datetime, timedelta, timezone

INTERVAL_SECONDS = 300  # 5-minute dispatch intervals

# NEM market price bounds ($/MWh)
MARKET_PRICE_FLOOR = -1000.0
MARKET_PRICE_CAP = 16600.0

MARKET_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS market_prices (
    interval_start timestamptz PRIMARY KEY,
    price_per_mwh real NOT NULL,
    region text NOT NULL DEFAULT 'SIM1'
);
CREATE INDEX IF NOT EXISTS idx_market_prices_ts ON market_prices (interval_start DESC);
"""


def interval_start(ts: datetime) -> datetime:
    """Floor a timestamp to its 5-minute dispatch interval (UTC-safe)."""
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - epoch % INTERVAL_SECONDS, tz=timezone.utc)


def base_price_for_local_hour(hour_frac: float) -> float:
    """Piecewise daily price shape ($/MWh) for a fractional local hour 0..24."""
    # Anchor points (hour, price) roughly matching NEM daily dynamics.
    anchors = [
        (0.0, 38.0), (4.0, 32.0), (6.0, 55.0), (8.0, 105.0),
        (10.0, 60.0), (13.0, 42.0), (15.0, 55.0), (17.0, 115.0),
        (19.0, 135.0), (21.0, 75.0), (23.0, 45.0), (24.0, 38.0),
    ]
    for (h1, p1), (h2, p2) in zip(anchors, anchors[1:]):
        if h1 <= hour_frac <= h2:
            # Cosine interpolation for a smooth curve
            span = (hour_frac - h1) / (h2 - h1) if h2 > h1 else 0.0
            blend = (1.0 - math.cos(span * math.pi)) / 2.0
            return p1 + (p2 - p1) * blend
    return anchors[-1][1]


def simulated_price(interval_utc: datetime, tz_offset_hours: float = 10.0) -> float:
    """Deterministic simulated price for one dispatch interval."""
    seed = int(interval_utc.timestamp()) // INTERVAL_SECONDS
    rng = random.Random(seed)

    local_hour = ((interval_utc.timestamp() / 3600.0) + tz_offset_hours) % 24.0
    price = base_price_for_local_hour(local_hour)

    # Ordinary noise
    price += rng.gauss(0.0, 7.0)

    # Rare spike events (transmission constraint / generator trip)
    if rng.random() < 0.015:
        price *= rng.uniform(3.0, 9.0)

    # Occasional negative midday prices (excess rooftop solar)
    if 10.0 <= local_hour <= 15.0 and rng.random() < 0.03:
        price = rng.uniform(-60.0, -5.0)

    return round(max(MARKET_PRICE_FLOOR, min(MARKET_PRICE_CAP, price)), 2)


def ensure_market_table(cur):
    cur.execute(MARKET_TABLE_SQL)


def upsert_price(cur, interval_utc: datetime, region: str = "SIM1") -> float:
    """Insert the price for an interval if missing; return the stored price."""
    price = simulated_price(interval_utc)
    cur.execute(
        """
        INSERT INTO market_prices (interval_start, price_per_mwh, region)
        VALUES (%s, %s, %s)
        ON CONFLICT (interval_start) DO NOTHING
        """,
        (interval_utc, price, region),
    )
    cur.execute(
        "SELECT price_per_mwh FROM market_prices WHERE interval_start = %s",
        (interval_utc,),
    )
    return float(cur.fetchone()[0])


def backfill_prices(cur, hours: int = 24, region: str = "SIM1") -> int:
    """Backfill recent history so trends are populated on first start."""
    now_interval = interval_start(datetime.now(timezone.utc))
    inserted = 0
    for i in range(hours * 12, 0, -1):
        iv = now_interval - timedelta(seconds=i * INTERVAL_SECONDS)
        cur.execute(
            """
            INSERT INTO market_prices (interval_start, price_per_mwh, region)
            VALUES (%s, %s, %s)
            ON CONFLICT (interval_start) DO NOTHING
            """,
            (iv, simulated_price(iv), region),
        )
        inserted += cur.rowcount
    return inserted

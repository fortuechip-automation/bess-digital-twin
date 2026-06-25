#!/usr/bin/env python3
"""Downsample and prune BESS telemetry without interrupting live reads."""

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg2


ADVISORY_LOCK_ID = 0x42455353


@dataclass(frozen=True)
class RetentionPolicy:
    raw_days: int = 30
    event_days: int = 365
    batch_size: int = 250_000
    max_delete_batches: int = 24


SUMMARY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS site_status_5m (
    bucket timestamptz PRIMARY KEY,
    samples bigint NOT NULL,
    soc_avg double precision NOT NULL,
    p_set_kw_avg double precision NOT NULL,
    p_actual_kw_avg double precision NOT NULL,
    vdc_avg double precision NOT NULL,
    idc_avg double precision NOT NULL,
    temp_c_avg double precision NOT NULL,
    active_alarms_max integer NOT NULL
);

CREATE TABLE IF NOT EXISTS inverter_status_15m (
    bucket timestamptz NOT NULL,
    inverter_id integer NOT NULL,
    samples bigint NOT NULL,
    p_set_kw_avg double precision NOT NULL,
    p_actual_kw_avg double precision NOT NULL,
    vdc_avg double precision NOT NULL,
    idc_avg double precision NOT NULL,
    temp_c_avg double precision NOT NULL,
    fault_samples bigint NOT NULL,
    PRIMARY KEY (bucket, inverter_id)
);

CREATE TABLE IF NOT EXISTS battery_status_15m (
    bucket timestamptz NOT NULL,
    battery_id integer NOT NULL,
    samples bigint NOT NULL,
    soc_avg double precision NOT NULL,
    vdc_avg double precision NOT NULL,
    idc_avg double precision NOT NULL,
    p_dc_kw_avg double precision NOT NULL,
    temp_c_avg double precision NOT NULL,
    fault_samples bigint NOT NULL,
    PRIMARY KEY (bucket, battery_id)
);
"""


def database_config_from_env():
    required = {
        "host": "BESS_DB_HOST",
        "dbname": "BESS_DB_NAME",
        "user": "BESS_DB_USER",
        "password": "BESS_DB_PASSWORD",
    }
    missing = [env_name for env_name in required.values() if not os.getenv(env_name)]
    if missing:
        raise RuntimeError(f"Missing database environment variables: {', '.join(missing)}")

    config = {key: os.environ[env_name] for key, env_name in required.items()}
    config["port"] = int(os.getenv("BESS_DB_PORT", "5432"))
    config["connect_timeout"] = 10
    config["application_name"] = "bess_retention"
    return config


def cutoff_time(now, days):
    return now - timedelta(days=days)


def create_summary_tables(cur):
    cur.execute(SUMMARY_TABLE_SQL)


def configure_telemetry_autovacuum(cur):
    for table in ("site_status", "inverter_status", "battery_status"):
        cur.execute(
            f"""
            ALTER TABLE {table} SET (
                autovacuum_vacuum_scale_factor = 0.01,
                autovacuum_vacuum_threshold = 50000,
                autovacuum_analyze_scale_factor = 0.02,
                autovacuum_analyze_threshold = 50000
            )
            """
        )


def summarize_site(cur, cutoff):
    cur.execute(
        """
        WITH start_point AS (
            SELECT COALESCE(
                (SELECT max(bucket) FROM site_status_5m),
                (SELECT min(ts) FROM site_status)
            ) AS start_ts
        )
        INSERT INTO site_status_5m (
            bucket, samples, soc_avg, p_set_kw_avg, p_actual_kw_avg,
            vdc_avg, idc_avg, temp_c_avg, active_alarms_max
        )
        SELECT
            date_bin('5 minutes', ts, TIMESTAMPTZ '2000-01-01'),
            count(*), avg(soc), avg(p_set_kw), avg(p_actual_kw),
            avg(vdc), avg(idc), avg(temp_c), max(active_alarms)
        FROM site_status, start_point
        WHERE ts >= start_point.start_ts AND ts < %s
        GROUP BY 1
        ON CONFLICT (bucket) DO UPDATE SET
            samples = EXCLUDED.samples,
            soc_avg = EXCLUDED.soc_avg,
            p_set_kw_avg = EXCLUDED.p_set_kw_avg,
            p_actual_kw_avg = EXCLUDED.p_actual_kw_avg,
            vdc_avg = EXCLUDED.vdc_avg,
            idc_avg = EXCLUDED.idc_avg,
            temp_c_avg = EXCLUDED.temp_c_avg,
            active_alarms_max = EXCLUDED.active_alarms_max
        """,
        (cutoff,),
    )
    return cur.rowcount


def summarize_inverters(cur, cutoff):
    cur.execute(
        """
        WITH start_point AS (
            SELECT COALESCE(
                (SELECT max(bucket) FROM inverter_status_15m),
                (SELECT min(ts) FROM inverter_status)
            ) AS start_ts
        )
        INSERT INTO inverter_status_15m (
            bucket, inverter_id, samples, p_set_kw_avg, p_actual_kw_avg,
            vdc_avg, idc_avg, temp_c_avg, fault_samples
        )
        SELECT
            date_bin('15 minutes', ts, TIMESTAMPTZ '2000-01-01'),
            inverter_id, count(*), avg(p_set_kw), avg(p_actual_kw),
            avg(vdc), avg(idc), avg(temp_c), count(*) FILTER (WHERE fault)
        FROM inverter_status, start_point
        WHERE ts >= start_point.start_ts AND ts < %s
        GROUP BY 1, 2
        ON CONFLICT (bucket, inverter_id) DO UPDATE SET
            samples = EXCLUDED.samples,
            p_set_kw_avg = EXCLUDED.p_set_kw_avg,
            p_actual_kw_avg = EXCLUDED.p_actual_kw_avg,
            vdc_avg = EXCLUDED.vdc_avg,
            idc_avg = EXCLUDED.idc_avg,
            temp_c_avg = EXCLUDED.temp_c_avg,
            fault_samples = EXCLUDED.fault_samples
        """,
        (cutoff,),
    )
    return cur.rowcount


def summarize_batteries(cur, cutoff):
    cur.execute(
        """
        WITH start_point AS (
            SELECT COALESCE(
                (SELECT max(bucket) FROM battery_status_15m),
                (SELECT min(ts) FROM battery_status)
            ) AS start_ts
        )
        INSERT INTO battery_status_15m (
            bucket, battery_id, samples, soc_avg, vdc_avg, idc_avg,
            p_dc_kw_avg, temp_c_avg, fault_samples
        )
        SELECT
            date_bin('15 minutes', ts, TIMESTAMPTZ '2000-01-01'),
            battery_id, count(*), avg(soc), avg(vdc), avg(idc),
            avg(p_dc_kw), avg(temp_c), count(*) FILTER (WHERE fault)
        FROM battery_status, start_point
        WHERE ts >= start_point.start_ts AND ts < %s
        GROUP BY 1, 2
        ON CONFLICT (bucket, battery_id) DO UPDATE SET
            samples = EXCLUDED.samples,
            soc_avg = EXCLUDED.soc_avg,
            vdc_avg = EXCLUDED.vdc_avg,
            idc_avg = EXCLUDED.idc_avg,
            p_dc_kw_avg = EXCLUDED.p_dc_kw_avg,
            temp_c_avg = EXCLUDED.temp_c_avg,
            fault_samples = EXCLUDED.fault_samples
        """,
        (cutoff,),
    )
    return cur.rowcount


def delete_in_batches(conn, table, timestamp_column, cutoff, batch_size, max_batches, extra_where=""):
    total_deleted = 0
    batches = 0

    while max_batches == 0 or batches < max_batches:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {table}
                WHERE ctid IN (
                    SELECT ctid
                    FROM {table}
                    WHERE {timestamp_column} < %s {extra_where}
                    LIMIT %s
                )
                """,
                (cutoff, batch_size),
            )
            deleted = cur.rowcount
        conn.commit()
        total_deleted += deleted
        batches += 1
        if deleted < batch_size:
            break

    return total_deleted


def run_maintenance(conn, policy, delete_until_complete=False, now=None):
    now = now or datetime.now(timezone.utc)
    raw_cutoff = cutoff_time(now, policy.raw_days)
    event_cutoff = cutoff_time(now, policy.event_days)
    max_batches = 0 if delete_until_complete else policy.max_delete_batches

    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_ID,))
        if not cur.fetchone()[0]:
            raise RuntimeError("Another BESS retention job is already running")

    try:
        with conn.cursor() as cur:
            create_summary_tables(cur)
            configure_telemetry_autovacuum(cur)
            summary_counts = {
                "site_status_5m": summarize_site(cur, raw_cutoff),
                "inverter_status_15m": summarize_inverters(cur, raw_cutoff),
                "battery_status_15m": summarize_batteries(cur, raw_cutoff),
            }
        conn.commit()

        deleted_counts = {
            "battery_status": delete_in_batches(
                conn, "battery_status", "ts", raw_cutoff, policy.batch_size, max_batches
            ),
            "inverter_status": delete_in_batches(
                conn, "inverter_status", "ts", raw_cutoff, policy.batch_size, max_batches
            ),
            "site_status": delete_in_batches(
                conn, "site_status", "ts", raw_cutoff, policy.batch_size, max_batches
            ),
            "bess_commands": delete_in_batches(
                conn,
                "bess_commands",
                "ts",
                event_cutoff,
                policy.batch_size,
                max_batches,
                "AND processed = TRUE",
            ),
            "bess_alarms": delete_in_batches(
                conn,
                "bess_alarms",
                "ts",
                event_cutoff,
                policy.batch_size,
                max_batches,
                "AND cleared = TRUE",
            ),
        }
        return summary_counts, deleted_counts
    except Exception:
        conn.rollback()
        raise
    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_ID,))
        conn.commit()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-days", type=int, default=30)
    parser.add_argument("--event-days", type=int, default=365)
    parser.add_argument("--batch-size", type=int, default=250_000)
    parser.add_argument("--max-delete-batches", type=int, default=24)
    parser.add_argument(
        "--delete-until-complete",
        action="store_true",
        help="Remove the full historical backlog instead of limiting this run.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if min(args.raw_days, args.event_days, args.batch_size, args.max_delete_batches) <= 0:
        print("[RETENTION] Retention values and batch limits must be positive", file=sys.stderr)
        return 2

    policy = RetentionPolicy(
        raw_days=args.raw_days,
        event_days=args.event_days,
        batch_size=args.batch_size,
        max_delete_batches=args.max_delete_batches,
    )
    started = time.monotonic()

    try:
        conn = psycopg2.connect(**database_config_from_env())
        summary_counts, deleted_counts = run_maintenance(
            conn, policy, delete_until_complete=args.delete_until_complete
        )
        conn.close()
    except Exception as exc:
        print(f"[RETENTION] Failed: {exc}", file=sys.stderr)
        return 1

    print(f"[RETENTION] Raw telemetry retention: {policy.raw_days} days")
    print(f"[RETENTION] Alarm/command retention: {policy.event_days} days")
    for table, count in summary_counts.items():
        print(f"[RETENTION] Summary rows upserted: {table}={count}")
    for table, count in deleted_counts.items():
        print(f"[RETENTION] Raw rows deleted: {table}={count}")
    print(f"[RETENTION] Completed in {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

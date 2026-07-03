"""Tiny database helper for the BESS REST API.

Each call opens a short-lived connection - simple and safe at lab scale.
Rows come back as dicts (RealDictCursor) so FastAPI can serialize them
straight to JSON.
"""

import os

import psycopg2
import psycopg2.extras


def _config():
    return {
        "host": os.getenv("BESS_DB_HOST", "DB_HOST"),
        "database": os.getenv("BESS_DB_NAME", "bess"),
        "user": os.getenv("BESS_DB_USER", "bessuser"),
        "password": os.getenv("BESS_DB_PASSWORD", "CHANGE_ME"),
        "port": int(os.getenv("BESS_DB_PORT", "5432")),
        "connect_timeout": 5,
        "application_name": "bess_api",
    }


def fetch_one(sql: str, params=()):
    with psycopg2.connect(**_config()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def fetch_all(sql: str, params=()):
    with psycopg2.connect(**_config()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def execute_returning(sql: str, params=()):
    with psycopg2.connect(**_config()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        conn.commit()
        return row

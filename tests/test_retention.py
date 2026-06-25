from datetime import datetime, timezone

import pytest

from src.database.retention import RetentionPolicy, cutoff_time, database_config_from_env


def test_default_retention_policy_is_conservative():
    policy = RetentionPolicy()

    assert policy.raw_days == 30
    assert policy.event_days == 365
    assert policy.batch_size == 250_000
    assert policy.max_delete_batches == 24


def test_cutoff_time_uses_requested_number_of_days():
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)

    assert cutoff_time(now, 30) == datetime(2026, 5, 26, tzinfo=timezone.utc)


def test_database_config_requires_local_environment(monkeypatch):
    for name in (
        "BESS_DB_HOST",
        "BESS_DB_NAME",
        "BESS_DB_USER",
        "BESS_DB_PASSWORD",
        "BESS_DB_PORT",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="Missing database environment variables"):
        database_config_from_env()


def test_database_config_reads_local_environment(monkeypatch):
    monkeypatch.setenv("BESS_DB_HOST", "db.example")
    monkeypatch.setenv("BESS_DB_NAME", "bess")
    monkeypatch.setenv("BESS_DB_USER", "bessuser")
    monkeypatch.setenv("BESS_DB_PASSWORD", "secret")
    monkeypatch.setenv("BESS_DB_PORT", "5433")

    config = database_config_from_env()

    assert config["host"] == "db.example"
    assert config["dbname"] == "bess"
    assert config["port"] == 5433
    assert config["application_name"] == "bess_retention"

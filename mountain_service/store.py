"""Transactional cache, short retention windows and checked database snapshots."""

import json
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from poc.sources import utc
from poc.store import backup as sqlite_backup

APP_ID = 0x574D3033
FORECAST_RETENTION = 7 * 86400
OBSERVATION_RETENTION = 2 * 86400
MANUAL_BUDGET_SCHEMA = """
CREATE TABLE IF NOT EXISTS manual_weather_budget (
    utc_day INTEGER PRIMARY KEY, batches INTEGER NOT NULL
);
"""
SCHEMA = MANUAL_BUDGET_SCHEMA + """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY, source TEXT NOT NULL, fetched INTEGER NOT NULL, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshots_retention ON snapshots(fetched);
CREATE TABLE IF NOT EXISTS source_state (
    source TEXT PRIMARY KEY, checked INTEGER NOT NULL, next_due INTEGER NOT NULL,
    failures INTEGER NOT NULL, error TEXT, last_success INTEGER,
    snapshot_id INTEGER REFERENCES snapshots(id)
);
CREATE TABLE IF NOT EXISTS provider_control (
    provider TEXT PRIMARY KEY, blocked INTEGER NOT NULL, resume_at INTEGER
);
CREATE TABLE IF NOT EXISTS nelson (
    feature_id TEXT PRIMARY KEY, observed REAL NOT NULL, processed REAL,
    fetched INTEGER NOT NULL, temperature_c REAL NOT NULL, metadata TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS nelson_time ON nelson(observed);
"""


def encode(value):
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat() if seconds is not None else None


def validate(db):
    if (db.execute("PRAGMA application_id").fetchone()[0] != APP_ID
            or db.execute("PRAGMA user_version").fetchone()[0] != 1
            or not {"snapshots", "source_state", "nelson", "provider_control"} <= {
                row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")
            }):
        raise ValueError("Expected a v0.3.1 mountain service database")


def prepare(path):
    # Initialize in the target directory and publish only after SQLite commits.
    # The caller owns the service lock.
    if not path.exists():
        require_no_sidecars(path)
        with TemporaryDirectory(dir=path.parent) as directory:
            staged = Path(directory) / "initial.sqlite"
            with closing(sqlite3.connect(staged)) as db:
                db.executescript(f"BEGIN IMMEDIATE; {SCHEMA} PRAGMA application_id = {APP_ID}; "
                                 "PRAGMA user_version = 1; COMMIT;")
            staged.chmod(0o600)
            os.link(staged, path)
    with connect(path, write=True) as db:
        validate(db)
        # Additive migration for existing weather caches and restored backups.
        db.execute(MANUAL_BUDGET_SCHEMA)
        db.execute("PRAGMA journal_mode = WAL")


@contextmanager
def connect(path, write=False):
    mode = "rw" if write else "ro"
    with closing(sqlite3.connect(Path(path).as_uri() + "?mode=" + mode, uri=True, timeout=3)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        if write:
            db.execute("PRAGMA synchronous = FULL")
            db.execute("PRAGMA secure_delete = ON")
        yield db


def state(db, key):
    return db.execute("SELECT * FROM source_state WHERE source = ?", (key,)).fetchone()


def control(db, provider):
    return db.execute("SELECT * FROM provider_control WHERE provider = ?", (provider,)).fetchone()


def manual_weather_used(db, day):
    row = db.execute("SELECT batches FROM manual_weather_budget WHERE utc_day = ?", (day,)).fetchone()
    return row["batches"] if row else 0


def charge_manual_weather(db, day, limit):
    with db:
        db.execute("BEGIN IMMEDIATE")
        if manual_weather_used(db, day) >= limit:
            return False
        db.execute("""
            INSERT INTO manual_weather_budget VALUES (?, 1)
            ON CONFLICT(utc_day) DO UPDATE SET batches=batches+1
        """, (day,))
        return True


def save(db, source, now, data, error, failures, next_due, provider_block=None):
    with db:
        db.execute("BEGIN IMMEDIATE")
        previous = state(db, source.key)
        snapshot = previous["snapshot_id"] if previous else None
        last_success = previous["last_success"] if previous else None
        if error is None:
            last_success = now
            if source.kind == "measured":
                for reading in data:
                    metadata = {k: v for k, v in reading.items() if k != "temperature_c"}
                    observed = utc(reading["valid_at"]).timestamp()
                    processed_at = reading["processed_at"]
                    db.execute("""
                        INSERT INTO nelson VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(feature_id) DO UPDATE SET
                            observed=excluded.observed, processed=excluded.processed,
                            fetched=excluded.fetched, temperature_c=excluded.temperature_c,
                            metadata=excluded.metadata
                        WHERE COALESCE(excluded.processed, 0) >= COALESCE(nelson.processed, 0)
                          AND (nelson.metadata != excluded.metadata
                               OR nelson.temperature_c != excluded.temperature_c)
                    """, (reading["source_id"], observed,
                          utc(processed_at).timestamp() if processed_at else None, now,
                          reading["temperature_c"], encode(metadata)))
            elif source.kind != "camera":
                encoded = encode(data)
                prior = db.execute("SELECT data FROM snapshots WHERE id = ?", (snapshot,)).fetchone()
                if prior is None or encoded != prior["data"]:
                    snapshot = db.execute("""
                        INSERT INTO snapshots(source, fetched, data) VALUES (?, ?, ?)
                    """, (source.key, now, encoded)).lastrowid
        db.execute("""
            INSERT INTO source_state VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET checked=excluded.checked,
                next_due=excluded.next_due, failures=excluded.failures, error=excluded.error,
                last_success=excluded.last_success, snapshot_id=excluded.snapshot_id
        """, (source.key, now, next_due, failures, error, last_success, snapshot))
        if provider_block is not None:
            blocked, resume_at = provider_block
            db.execute("""
                INSERT INTO provider_control VALUES (?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET blocked=excluded.blocked, resume_at=excluded.resume_at
            """, (source.provider, blocked, resume_at))


def prune(db, now):
    with db:
        db.execute("UPDATE source_state SET snapshot_id=NULL WHERE last_success < ?",
                   (now - FORECAST_RETENTION,))
        db.execute("DELETE FROM snapshots WHERE fetched < ? AND id NOT IN "
                   "(SELECT snapshot_id FROM source_state WHERE snapshot_id IS NOT NULL)",
                   (now - FORECAST_RETENTION,))
        db.execute("DELETE FROM nelson WHERE observed < ?", (now - OBSERVATION_RETENTION,))
        db.execute("DELETE FROM manual_weather_budget WHERE utc_day < ?", (now // 86400 - 7,))


def observations(db, now, limit):
    rows = db.execute("""
        SELECT * FROM nelson WHERE observed BETWEEN ? AND ?
        ORDER BY observed DESC, processed DESC, feature_id DESC LIMIT ?
    """, (now - OBSERVATION_RETENTION, now, limit))
    return [{**json.loads(row["metadata"]), "temperature_c": row["temperature_c"],
             "retrieved_at": iso(row["fetched"])} for row in rows]


def require_no_sidecars(path):
    if any(os.path.lexists(str(path) + suffix) for suffix in ("-wal", "-shm", "-journal")):
        raise FileExistsError("Destination has SQLite sidecar files")


def copy_database(source, target):
    """Copy committed contents from an active database or a standalone backup."""
    require_no_sidecars(target)
    sqlite_backup(source, target, validate=validate)

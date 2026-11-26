"""SQLite cache and consistent offline snapshots for synthetic trials."""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from .sources import HOUR, require, snowfall_windows, utc


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshots_source ON snapshots(source, id);
CREATE TABLE IF NOT EXISTS attempts (
    source TEXT PRIMARY KEY,
    checked_at TEXT NOT NULL,
    snapshot_id INTEGER REFERENCES snapshots(id),
    error TEXT,
    last_success_at TEXT
);
"""


def open_store(path):
    db = sqlite3.connect(path, timeout=5)
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(SCHEMA)
    except BaseException:
        db.close()
        raise
    return db


def record(db, source, at, payload=None, error=None):
    require((payload is None) != (error is None), "Supply a payload or an error")
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False) if payload is not None else None
    with db:
        # Serialize compare and update, so concurrent writers cannot duplicate history.
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("""
            SELECT a.checked_at, s.id, s.data, a.last_success_at
            FROM attempts a LEFT JOIN snapshots s ON a.snapshot_id = s.id
            WHERE a.source = ?
        """, (source,)).fetchone()
        if previous and utc(previous[0]) > at:
            return
        snapshot_id = previous[1] if previous else None
        if encoded is not None and (previous is None or encoded != previous[2]):
            snapshot_id = db.execute("""
                INSERT INTO snapshots (source, fetched_at, data) VALUES (?, ?, ?)
            """, (source, at.isoformat(), encoded)).lastrowid
        last_success = at.isoformat() if error is None else (previous[3] if previous else None)
        db.execute("""
            INSERT INTO attempts VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                checked_at = excluded.checked_at, snapshot_id = excluded.snapshot_id,
                error = excluded.error, last_success_at = excluded.last_success_at
        """, (source, at.isoformat(), snapshot_id, error, last_success))


def read_cache(db, source, now):
    row = db.execute("""
        SELECT a.checked_at, a.error, s.fetched_at, s.data, a.last_success_at
        FROM attempts a LEFT JOIN snapshots s ON a.snapshot_id = s.id
        WHERE a.source = ?
    """, (source,)).fetchone()
    if row is None:
        return {"status": "unavailable"}
    checked_at, error, fetched_at, encoded, last_success = row
    result = {"status": "unavailable", "checked_at": checked_at, "error": error}
    if encoded is None:
        return result
    data = json.loads(encoded)
    kind = data["kind"]
    if kind == "forecast":
        # Last successful check describes the cache age. Model issue time stays unknown.
        age = now - utc(last_success)
        if snowfall_windows(data, now)["totals_cm"][24] is None:
            age = None
        limit = 14 * HOUR
    elif kind == "reported":
        age = now - utc(data["report_updated_at"])
        limit = 30 * HOUR
    else:
        times = [r["valid_at"] for r in data["readings"]] if "readings" in data else [data["valid_at"]]
        age = now - utc(max(times)) if times else None
        limit = 2 * HOUR
    if age is not None and age.total_seconds() >= 0:
        result["status"] = "fresh" if age <= limit else "stale"
    result.update({"data": data, "snapshot_fetched_at": fetched_at, "last_success_at": last_success,
                   "age_seconds": age.total_seconds() if age is not None else None})
    return result


def backup(source, destination):
    """Publish a checked standalone snapshot without overwriting an existing backup."""
    source = Path(source)
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    # Read through SQLite so committed pages still in the WAL are included.
    with TemporaryDirectory(dir=destination.parent) as directory:
        staged = Path(directory) / "snapshot.sqlite"
        with (closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src,
              closing(sqlite3.connect(staged)) as dst):
            src.backup(dst)
            dst.execute("PRAGMA journal_mode = DELETE")
            if (dst.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
                    or dst.execute("PRAGMA foreign_key_check").fetchall()):
                raise ValueError("Snapshot integrity checks failed")
        with staged.open("rb") as file:
            os.fsync(file.fileno())
        os.link(staged, destination)

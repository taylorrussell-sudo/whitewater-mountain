"""Run the local API, validate a source once, or manage database snapshots."""

import argparse
import fcntl
import logging
import os
import re
import signal
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

from . import __version__, store
from .cameras import DRIVEBC
from .api import LocalAPI, coverage
from .collect import Collector, FetchError, fetch_html, fetch_json, sample
from .sources import NELSON_CS, RESORT_SNOW, RESORT_WEATHER, SOURCES

REPOSITORY = Path(__file__).resolve().parents[1]
COLLECTABLE = {**SOURCES, DRIVEBC.key: DRIVEBC}
PROVIDERS = sorted({source.provider for source in COLLECTABLE.values()})


class DatabaseInUse(ValueError):
    pass


def private_path(value):
    path = Path(value).expanduser().resolve()
    if path.is_relative_to(REPOSITORY):
        raise ValueError("Database and backup paths must be outside the repository")
    return path


@contextmanager
def service_lock(path):
    with Path(str(path) + ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DatabaseInUse("A service or maintenance command already owns this database") from exc
        yield


def edge_origin(value):
    match = re.fullmatch(r"https?://([a-z0-9]+(?:[.-][a-z0-9]+)*)(?::([1-9][0-9]{0,4}))?", value)
    if not match or (match[2] and int(match[2]) > 65535):
        raise argparse.ArgumentTypeError("Use a canonical HTTP(S) origin with a DNS name or IPv4 address")
    if (value.startswith("https://") and match[2] == "443"
            or value.startswith("http://") and match[2] == "80"):
        raise argparse.ArgumentTypeError("Omit the default HTTP or HTTPS port")
    return value


def serve(path, port, enabled, origins):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with service_lock(path):
        store.prepare(path)
        stop, failed = Event(), Event()
        collector = Collector(path, [source for key, source in COLLECTABLE.items() if key in enabled])

        def stop_service(signum, frame):
            stop.set()
            collector.wake.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, stop_service)
        worker = Thread(target=collector.run, args=(stop, failed), daemon=True)
        with LocalAPI(port, path, enabled, failed, time.time, collector=collector,
                      origins=origins) as api:
            logging.info("Local API listening on http://127.0.0.1:%d", api.server_port)
            worker.start()
            try:
                while not stop.is_set():
                    api.handle_request()
            finally:
                stop.set()
                collector.wake.set()
                worker.join(timeout=30)


def probe(source):
    start = datetime.now(timezone.utc)
    fetch = fetch_html if source in (RESORT_SNOW, RESORT_WEATHER) else fetch_json
    data = sample(source, start, time.time, fetch)
    status = {"source": source.key, "checked_at": store.iso(time.time()), "status": "no_data"}
    if data is not None:
        status["status"] = "validated_response"
        if source.kind == "forecast":
            status["points"] = {
                name: {"returned_point": point["returned_point"],
                       "coverage": coverage(point["times"], point["values"], int(start.timestamp()) // 3600 * 3600)}
                for name, point in data["points"].items()
            }
        elif source.key == NELSON_CS.key:
            status["accepted_count"] = len(data)
            status["latest_valid_at"] = max(row["valid_at"] for row in data)
        elif source == RESORT_SNOW:
            status["available_fields"] = [key for key, value in data["values"].items() if value is not None]
        elif source == RESORT_WEATHER:
            status["available_stations"] = [key for key, value in data["stations"].items() if value]
        else:
            status["valid_profiles"] = sum(row is not None for row in data["crossings"])
            status["max_crossings"] = max(len(row) for row in data["crossings"] if row is not None)
            status["returned_point"] = data["returned_grid_point"]
    print(store.encode(status))
    return int(data is None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    local = commands.add_parser("serve", help="run the loopback API and scheduled collection")
    local.add_argument("--db", required=True)
    local.add_argument("--port", type=int, default=8765)
    local.add_argument("--collect", choices=COLLECTABLE, action="append", default=[])
    local.add_argument("--allow-origin", type=edge_origin, action="append", default=[],
                       help="exact browser origin for an approved private reverse proxy")
    inspect = commands.add_parser("probe", help="perform one live request and print coverage only")
    inspect.add_argument("source", choices=SOURCES)
    for name in ("backup", "restore"):
        command = commands.add_parser(name)
        command.add_argument("source")
        command.add_argument("destination")
    resume = commands.add_parser("resume", help="clear a 401/403 stop after access has been confirmed")
    resume.add_argument("--db", required=True)
    resume.add_argument("provider", choices=PROVIDERS)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    os.umask(0o077)
    try:
        if args.command == "serve":
            serve(private_path(args.db), args.port, set(args.collect), args.allow_origin)
        elif args.command == "probe":
            return probe(SOURCES[args.source])
        elif args.command == "resume":
            path = private_path(args.db)
            with service_lock(path), store.connect(path, write=True) as db, db:
                store.validate(db)
                db.execute("DELETE FROM provider_control WHERE provider = ? AND blocked = 1", (args.provider,))
        else:
            target = private_path(args.destination)
            with service_lock(target):
                store.copy_database(private_path(args.source), target)
    except (FetchError, OSError, sqlite3.Error, ValueError) as exc:
        if args.command == "serve" and not isinstance(exc, DatabaseInUse):
            logging.error("Service startup failed (%s)", type(exc).__name__)
        else:
            logging.error("%s: %s", args.command, exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

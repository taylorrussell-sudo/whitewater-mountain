"""Read-only JSON views. A request never triggers collection."""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from poc.sources import snowfall_windows, utc

from . import store
from .sources import DISABLED, NELSON_CS, SOURCES


def coverage(times, data, after):
    result = {}
    for name, values in data.items():
        available = [t for t, value in zip(times, values) if t >= after and value is not None]
        result[name] = {"hours": len(available), "first_valid_at": store.iso(available[0]) if available else None,
                        "last_valid_at": store.iso(available[-1]) if available else None}
    return result


def source_view(db, source, enabled, now):
    result = {**source.metadata(), "status": "disabled", "data": None}
    if source.key not in enabled:
        return {**result, "reason": "collection_not_enabled"}
    result["status"] = "unavailable"
    row = store.state(db, source.key)
    control = store.control(db, source.provider)
    result.update({
        "checked_at": store.iso(row["checked"]) if row else None,
        "last_success_at": store.iso(row["last_success"]) if row else None,
        "last_error": row["error"] if row else None,
        "provider_state": "ready",
        "next_attempt_at": store.iso(row["next_due"]) if row else None,
        "age_seconds": None, "age_basis": None,
    })
    if control and control["blocked"]:
        result.update(provider_state="blocked", next_attempt_at=None)
    elif control and control["resume_at"] > now:
        result.update(provider_state="cooldown", next_attempt_at=store.iso(
            max(control["resume_at"], row["next_due"] if row else 0)))
    if row is None or row["last_success"] is None or row["last_success"] > now:
        return result

    if source.kind == "measured":
        latest = store.observations(db, now, 1)
        if latest:
            data = latest[0]
            age = now - utc(data["valid_at"]).timestamp()
            status = "fresh" if age <= source.fresh_for else "stale"
            result.update(status=status, age_seconds=age, age_basis="observation_valid_time", data=data)
        return result

    age = now - row["last_success"]
    result.update(age_seconds=age, age_basis="last_successful_retrieval")
    if row["snapshot_id"] is None or age > store.FORECAST_RETENTION:
        return result
    snapshot = db.execute("SELECT fetched, data FROM snapshots WHERE id = ?",
                          (row["snapshot_id"],)).fetchone()
    data = json.loads(snapshot["data"])
    result["snapshot_retrieved_at"] = store.iso(snapshot["fetched"])
    anchor = now // 3600 * 3600
    if source.kind == "forecast":
        for point in data["points"].values():
            point["coverage"] = coverage(point["times"], point["values"], anchor)
        available = any(metric["hours"] for point in data["points"].values()
                        for metric in point["coverage"].values())
    else:
        data["coverage"] = coverage(data["times"], {"crossings": data["crossings"]}, anchor)
        available = bool(data["coverage"]["crossings"]["hours"])
    if not available:
        return result
    result.update(status="fresh" if age <= source.fresh_for else "stale", data=data)
    if source.kind == "forecast":
        data["lodge_snowfall_windows"] = (
            snowfall_windows(data["points"]["lodge"], datetime.fromtimestamp(now, timezone.utc))
            if result["status"] == "fresh" else None
        )
    return result


def weather(db, enabled, now):
    return {"api_version": 1, "as_of": store.iso(now),
            "sources": {**DISABLED, **{key: source_view(db, source, enabled, now)
                                      for key, source in SOURCES.items()}}}


class LocalAPI(ThreadingHTTPServer):
    timeout = 0.5

    def __init__(self, port, path, enabled, collector_failed, clock):
        self.path = path
        self.enabled = enabled
        self.collector_failed = collector_failed
        self.clock = clock
        super().__init__(("127.0.0.1", port), Handler)


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(3)
        super().setup()

    def log_message(self, *args):
        pass

    def reply(self, status, payload):
        data = store.encode(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            hosts.update(("127.0.0.1", "localhost"))
        origins = {"http://" + host for host in hosts}
        if self.headers.get("Host") not in hosts or self.headers.get("Origin", None) not in origins | {None}:
            self.reply(403, {"error": "local_requests_only"})
            return
        now = int(self.server.clock())
        try:
            with store.connect(self.server.path) as db, db:
                db.execute("BEGIN")
                status, payload = self.route(db, now)
        except sqlite3.Error:
            logging.exception("API database read failed")
            status, payload = 503, {"error": "database_unavailable"}
        try:
            self.reply(status, payload)
        except (ConnectionError, TimeoutError):
            pass

    def route(self, db, now):
        if self.path == "/healthz":
            db.execute("SELECT count(*) FROM source_state").fetchone()
            if self.server.collector_failed.is_set():
                return 503, {"status": "degraded"}
            return 200, {"status": "ok"}
        if self.path == "/v1/weather":
            return 200, weather(db, self.server.enabled, now)
        if self.path == "/v1/observations/nelson":
            enabled = NELSON_CS.key in self.server.enabled
            return 200, {"api_version": 1, "as_of": store.iso(now), "source": NELSON_CS.metadata(),
                         "status": "enabled" if enabled else "disabled", "retention_hours": 48,
                         "readings": store.observations(db, now, 288) if enabled else []}
        return 404, {"error": "not_found"}

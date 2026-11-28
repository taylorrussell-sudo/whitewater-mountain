"""Loopback dashboard, cache views and a scheduler request endpoint."""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from poc.sources import snowfall_windows, utc

from . import cameras, store
from .sources import DISABLED, NELSON_CS, RESORT_SNOW, RESORT_WEATHER, SOURCES

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "index.html"
LIVE_SCRIPT = Path(__file__).with_name("dashboard.js")
CAMERA_FIXTURES = {
    f"/mountain_service/camera_fixtures/{camera}.webp":
        ROOT / "mountain_service" / "camera_fixtures" / f"{camera}.webp"
    for camera in ("lodge", "summit", "raven", "glory", "weatherstick", "road")
}


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

    if source == NELSON_CS:
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
    if source == RESORT_SNOW:
        age = now - utc(data["report_updated_at"]).timestamp()
        status = freshness(age, source.fresh_for)
        return {**result, "status": status, "age_seconds": age, "age_basis": "report_update_time", "data": data}
    if source == RESORT_WEATHER:
        for reading in data["stations"].values():
            if reading:
                age = now - utc(reading["valid_at"]).timestamp()
                reading.update(status=freshness(age, source.fresh_for), age_seconds=age)
        readings = [r for r in data["stations"].values() if r and r["age_seconds"] >= 0]
        age = min((r["age_seconds"] for r in readings), default=None)
        return {**result, "status": freshness(age, source.fresh_for), "age_seconds": age,
                "age_basis": "newest_observation_valid_time", "data": data}
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


def freshness(age, limit):
    if age is None or age < 0:
        return "unavailable"
    return "fresh" if age <= limit else "stale"


def measured_inversion(db, sources, now):
    mountain = sources[RESORT_WEATHER.key]["data"]
    lodge = mountain["stations"].get("lodge") if mountain else None
    if (not lodge or lodge["status"] != "fresh" or lodge["temperature_c"] is None
            or sources[NELSON_CS.key]["status"] != "fresh"):
        return None
    at = utc(lodge["valid_at"]).timestamp()
    valley = store.observations(db, now, 288, since=now - NELSON_CS.fresh_for)
    candidates = [(abs(utc(reading["valid_at"]).timestamp() - at), reading) for reading in valley]
    closest = min(candidates, key=lambda candidate: candidate[0], default=None)
    if closest is None or closest[0] > 30 * 60:
        return None
    return {site: {key: reading[key] for key in ("valid_at", "temperature_c")}
            for site, reading in (("nelson", closest[1]), ("lodge", lodge))}


def weather(db, enabled, now):
    sources = {**DISABLED, **{key: source_view(db, source, enabled, now)
                            for key, source in SOURCES.items()}}
    return {"api_version": 1, "as_of": store.iso(now), "sources": sources,
            "measured_inversion": measured_inversion(db, sources, now)}


def camera_view(db, enabled, frame, now):
    source = cameras.DRIVEBC
    if source.key not in enabled:
        return {"status": "disabled"}
    row = store.state(db, source.key)
    result = {"status": "unavailable", "last_error": row["error"] if row else None}
    if frame is None or not 0 <= now - frame.modified <= cameras.MAX_AGE:
        return result
    stale = frame.delayed or now - frame.modified > source.fresh_for or result["last_error"] == "camera_offline"
    return {**result, "status": "stale" if stale else "fresh",
            "updated_at": store.iso(frame.modified),
            "image": f"/v1/cameras/{source.key}/{frame.revision}.jpg"}


class LocalAPI(ThreadingHTTPServer):
    timeout = 0.5

    def __init__(self, port, path, enabled, collector_failed, clock, collector=None, origins=()):
        self.path = path
        self.enabled = enabled
        self.collector_failed = collector_failed
        self.clock = clock
        self.collector = collector
        super().__init__(("127.0.0.1", port), Handler)
        port = self.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            hosts.update(("127.0.0.1", "localhost"))
        self.origins = {origin.split("://", 1)[1]: origin for origin in origins}
        self.origins.update((host, "http://" + host) for host in hosts)

    def handle_error(self, request, client_address):
        logging.warning("HTTP request failed")


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(3)
        super().setup()

    def log_message(self, *args):
        pass

    def send_content(self, status, data, content_type, retry_in=0, cache="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'self' 'unsafe-inline'; "
                         "style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; "
                         "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        if retry_in:
            self.send_header("Retry-After", str(retry_in))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (ConnectionError, TimeoutError):
            pass

    def reply(self, status, payload, retry_in=0):
        self.send_content(status, store.encode(payload).encode(), "application/json; charset=utf-8", retry_in)

    def is_allowed(self, require_origin=False):
        host = self.headers.get_all("Host")
        origin = self.headers.get_all("Origin")
        allowed_origin = self.server.origins.get(host[0]) if host and len(host) == 1 else None
        return bool(allowed_origin and
                    (origin == [allowed_origin] or (origin is None and not require_origin)))

    def do_POST(self):
        if not self.is_allowed(require_origin=True):
            self.reply(403, {"error": "same_origin_required"})
            return
        if self.path != "/v1/refresh":
            self.reply(404, {"error": "not_found"})
            return
        if (self.headers.get_all("X-Mountain-Refresh") != ["1"]
                or self.headers.get("Transfer-Encoding") is not None
                or self.headers.get_all("Content-Length") not in (None, ["0"])):
            self.reply(400, {"error": "invalid_refresh_request"})
            return
        if self.server.collector is None or self.server.collector_failed.is_set():
            self.reply(503, {"error": "collector_unavailable"})
            return
        status, error = self.server.collector.request_refresh()
        try:
            refresh = self.server.collector.refresh_status()
        except sqlite3.Error:
            self.reply(503, {"error": "database_unavailable"})
            return
        self.reply(status, {"error": error, "refresh": refresh},
                   refresh["retry_in"] if status == 429 else 0)

    def do_GET(self):
        if not self.is_allowed():
            self.reply(403, {"error": "local_requests_only"})
            return
        if self.path in ("/", "/index.html", "/dashboard.js", "/v1/refresh"):
            self.dashboard_route()
            return
        if self.path in CAMERA_FIXTURES:
            try:
                data = CAMERA_FIXTURES[self.path].read_bytes()
            except OSError:
                self.reply(404, {"error": "not_found"})
            else:
                self.send_content(200, data, "image/webp", cache="private, max-age=3600")
            return
        now = int(self.server.clock())
        if self.path.startswith("/v1/cameras/"):
            self.camera_image(now)
            return
        try:
            with store.connect(self.server.path) as db, db:
                db.execute("BEGIN")
                status, payload = self.route(db, now)
        except sqlite3.Error:
            logging.error("API database read failed")
            status, payload = 503, {"error": "database_unavailable"}
        self.reply(status, payload)

    def camera_image(self, now):
        frame = self.server.collector.camera_frame if self.server.collector else None
        key = cameras.DRIVEBC.key
        if (key in self.server.enabled and frame is not None
                and 0 <= now - frame.modified <= cameras.MAX_AGE
                and self.path == f"/v1/cameras/{key}/{frame.revision}.jpg"):
            self.send_content(200, frame.jpeg, "image/jpeg", cache="private, max-age=300")
        else:
            self.reply(404, {"error": "not_found"})

    def dashboard_route(self):
        if self.path == "/v1/refresh":
            if self.server.collector is None:
                self.reply(503, {"error": "collector_unavailable"})
            else:
                try:
                    refresh = self.server.collector.refresh_status()
                except sqlite3.Error:
                    self.reply(503, {"error": "database_unavailable"})
                else:
                    self.reply(200, refresh)
            return
        if self.path == "/dashboard.js":
            self.send_content(200, LIVE_SCRIPT.read_bytes(), "text/javascript; charset=utf-8")
            return
        html = DASHBOARD.read_text(encoding="utf-8").replace(
            '<body>', '<body data-live>', 1).replace(
            '</body>', '<script src="/dashboard.js"></script></body>', 1)
        self.send_content(200, html.encode(), "text/html; charset=utf-8")

    def route(self, db, now):
        if self.path == "/healthz":
            db.execute("SELECT count(*) FROM source_state").fetchone()
            if self.server.collector_failed.is_set():
                return 503, {"status": "degraded"}
            return 200, {"status": "ok"}
        if self.path == "/v1/weather":
            frame = self.server.collector.camera_frame if self.server.collector else None
            return 200, {**weather(db, self.server.enabled, now),
                         "camera": camera_view(db, self.server.enabled, frame, now)}
        if self.path == "/v1/observations/nelson":
            enabled = NELSON_CS.key in self.server.enabled
            return 200, {"api_version": 1, "as_of": store.iso(now), "source": NELSON_CS.metadata(),
                         "status": "enabled" if enabled else "disabled", "retention_hours": 48,
                         "readings": store.observations(db, now, 288) if enabled else []}
        return 404, {"error": "not_found"}

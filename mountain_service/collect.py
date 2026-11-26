"""Serial scheduler with persistent per-source and shared provider backoff."""

import json
import logging
import math
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from threading import Event, Lock
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import store

MAX_BODY = 1024 * 1024
HTTP_TIMEOUT = 8
HTTP_BODY_DEADLINE = 15
MANUAL_COOLDOWN = 60


class FetchError(Exception):
    def __init__(self, code, policy="retry", retry_after=None):
        super().__init__(code)
        self.code = code
        self.policy = policy
        self.retry_after = retry_after


def retry_after(value, now):
    if value:
        try:
            if value.isascii() and value.isdecimal():
                # Values beyond one hundred years are already a practical stop.
                return now + min(int(value), 100 * 365 * 86400)
            at = parsedate_to_datetime(value)
            return math.ceil((at if at.tzinfo else at.replace(tzinfo=timezone.utc)).timestamp())
        except (ValueError, OSError, OverflowError):
            pass
    return now + 3600


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_json(url):
    request = Request(url, headers={"User-Agent": "Whitewater Mountain Dashboard/0.3.2 (private household)",
                                    "Accept": "application/json, application/geo+json"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=HTTP_TIMEOUT) as response:
            if response.headers.get_content_type() not in ("application/json", "application/geo+json"):
                raise FetchError("unexpected_content_type", "interval")
            deadline = time.monotonic() + HTTP_BODY_DEADLINE
            body = bytearray()
            while len(body) <= MAX_BODY:
                if time.monotonic() > deadline:
                    raise FetchError("timeout")
                chunk = response.read1(min(65536, MAX_BODY + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
            if len(body) > MAX_BODY:
                raise FetchError("response_too_large", "interval")
    except HTTPError as exc:
        with exc:
            code = exc.code
            if code in (401, 403):
                raise FetchError(f"http_{code}", "stop") from None
            if code == 429 or (code == 503 and exc.headers.get("Retry-After")):
                raise FetchError(f"http_{code}", "provider_wait",
                                 exc.headers.get("Retry-After")) from None
            policy = "retry" if code == 408 or 500 <= code <= 599 else "interval"
            raise FetchError(f"http_{code}", policy) from None
    except TimeoutError:
        raise FetchError("timeout") from None
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise FetchError("timeout") from None
        # urllib may wrap a proxy CONNECT denial in URLError.
        if str(exc.reason).startswith("Tunnel connection failed: 403"):
            raise FetchError("proxy_http_403", "stop") from None
        raise FetchError("transport_error") from None
    except (OSError, HTTPException):
        raise FetchError("transport_error") from None
    try:
        return json.loads(body)
    except (ValueError, RecursionError):
        raise FetchError("invalid_json", "interval") from None


def sample(source, start, clock, fetch):
    payload = fetch(source.url(start))
    try:
        return source.normalize(payload, datetime.fromtimestamp(clock(), timezone.utc))
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        raise FetchError("unexpected_schema", "interval") from None


class Collector:
    def __init__(self, path, sources, clock=time.time, fetch=fetch_json, monotonic=time.monotonic):
        self.path = path
        self.sources = sources
        self.clock = clock
        self.fetch = fetch
        self.next_prune = 0
        self.monotonic = monotonic
        self.wake = Event()
        self.lock = Lock()
        self.refresh_state = "idle"
        self.outcomes = {}
        self.manual_allowed_at = 0

    def refresh_status(self):
        with self.lock:
            return {
                "state": self.refresh_state,
                "outcomes": self.outcomes.copy(),
                "retry_in": max(0, math.ceil(self.manual_allowed_at - self.monotonic())),
            }

    def request_refresh(self):
        with self.lock:
            if not self.sources:
                return 409, "no_enabled_sources"
            if self.refresh_state in ("queued", "running"):
                return 409, "refresh_in_progress"
            now = self.monotonic()
            if now < self.manual_allowed_at:
                return 429, "manual_cooldown"
            self.manual_allowed_at = now + MANUAL_COOLDOWN
            self.refresh_state = "queued"
            self.outcomes = {source.key: "queued" for source in self.sources}
            self.wake.set()
            return 202, None

    def cycle(self, stop=None, manual=False):
        now = int(self.clock())
        with store.connect(self.path, write=True) as db:
            if now >= self.next_prune:
                store.prune(db, now)
                self.next_prune = now + 3600
            for source in self.sources:
                if stop is not None and stop.is_set():
                    return
                if manual:
                    with self.lock:
                        self.outcomes[source.key] = "checking"
                outcome = self.refresh_if_due(db, source, manual)
                if manual:
                    with self.lock:
                        self.outcomes[source.key] = outcome

    def refresh_if_due(self, db, source, manual=False):
        now = int(self.clock())
        control = store.control(db, source.provider)
        previous = store.state(db, source.key)
        if control and control["blocked"]:
            return "provider_blocked"
        if control and control["resume_at"] > now:
            return "provider_cooldown"
        if previous and previous["next_due"] > now:
            if previous["error"]:
                return "backoff"
            # SWOB retains its conservative hourly cadence. A recent scheduled
            # Open-Meteo check also counts toward the minimum request spacing.
            spacing = source.interval if source.provider == "eccc" else MANUAL_COOLDOWN
            if not manual or now < previous["checked"] + spacing:
                return "recently_checked"
        data = None
        error = None
        cooldown = None
        failures = 0
        delay = source.interval
        start = datetime.fromtimestamp(now, timezone.utc)
        try:
            data = sample(source, start, self.clock, self.fetch)
            if data is None:
                error = "no_data"
        except FetchError as exc:
            error = exc.code
            if exc.policy == "retry":
                failures = min((previous["failures"] if previous else 0) + 1, 12)
                delay = min(source.interval, 60 * (2 ** (failures - 1)))
            elif exc.policy == "stop":
                cooldown = (True, None)
            elif exc.policy == "provider_wait":
                resume = max(int(self.clock()) + 300, retry_after(exc.retry_after, int(self.clock())))
                cooldown = (False, resume)
        completed = int(self.clock())
        store.save(db, source, completed, data, error, failures, completed + delay, cooldown)
        if error:
            logging.warning("%s refresh: %s", source.key, error)
        return "failed" if error else "updated"

    def run(self, stop, failed):
        while not stop.is_set():
            self.wake.clear()
            with self.lock:
                manual = self.refresh_state == "queued"
                if manual:
                    self.refresh_state = "running"
            cycle_failed = False
            try:
                self.cycle(stop, manual)
            except Exception:
                cycle_failed = True
                failed.set()
                logging.exception("Collection cycle failed")
            else:
                failed.clear()
            finally:
                if manual:
                    with self.lock:
                        self.refresh_state = "failed" if cycle_failed or stop.is_set() else "complete"
                        for key, outcome in self.outcomes.items():
                            if outcome in ("queued", "checking"):
                                self.outcomes[key] = "interrupted"
            if not stop.is_set():
                self.wake.wait(30 if cycle_failed else 5)

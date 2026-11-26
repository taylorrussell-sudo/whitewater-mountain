"""Serial scheduler with persistent per-source and shared provider backoff."""

import json
import logging
import math
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import store

MAX_BODY = 1024 * 1024
HTTP_TIMEOUT = 8
HTTP_BODY_DEADLINE = 15


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
    request = Request(url, headers={"User-Agent": "Whitewater Mountain Dashboard/0.3.1 (private household)",
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
    def __init__(self, path, sources, clock=time.time, fetch=fetch_json):
        self.path = path
        self.sources = sources
        self.clock = clock
        self.fetch = fetch
        self.next_prune = 0

    def cycle(self, stop=None):
        now = int(self.clock())
        with store.connect(self.path, write=True) as db:
            if now >= self.next_prune:
                store.prune(db, now)
                self.next_prune = now + 3600
            for source in self.sources:
                if stop is not None and stop.is_set():
                    return
                self.refresh_if_due(db, source)

    def refresh_if_due(self, db, source):
        now = int(self.clock())
        control = store.control(db, source.provider)
        previous = store.state(db, source.key)
        if control and (control["blocked"] or control["resume_at"] > now):
            return
        if previous and previous["next_due"] > now:
            return
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

    def run(self, stop, failed):
        while not stop.is_set():
            try:
                self.cycle(stop)
            except Exception:
                failed.set()
                logging.exception("Collection cycle failed")
                stop.wait(30)
            else:
                failed.clear()
                stop.wait(5)

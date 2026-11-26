"""Run a synthetic trial or a one-shot, read-only open-data probe."""

import argparse
import json
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .sources import (
    HOUR, LODGE, NELSON, UTC, forecast_url, normalize_forecast, normalize_resort_report,
    normalize_resort_weather, normalize_valley, require, snowfall_windows, utc, valley_url,
)
from .store import backup, open_store, read_cache, record
from .synthetic import NOW, forecast_fixture, mountain_fixture, report_fixture, valley_fixture

RESPONSE_LIMIT = 512 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_json(url):
    request = Request(url, headers={
        "User-Agent": "WhitewaterMountain-PoC/0.3.0 (manual source validation)",
        "Accept": "application/json, application/geo+json",
    })
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        content_type = response.headers.get_content_type()
        require(content_type in ("application/json", "application/geo+json"),
                f"Unexpected response type {content_type}")
        body = response.read(RESPONSE_LIMIT + 1)
        require(len(body) <= RESPONSE_LIMIT, "Response exceeds validation size cap")
        return json.loads(body), content_type


def probe(source):
    started_at = datetime.now(UTC)
    if source == "eccc":
        payload, content_type = fetch_json(valley_url(started_at))
        parsed = normalize_valley(payload)
        retrieved_at = datetime.now(UTC)
        require(parsed["readings"], "No usable Nelson CS temperatures in the response")
        newest = parsed["readings"][-1]
        age = retrieved_at - utc(newest["valid_at"])
        require(age >= 0 * HOUR, "Future-dated Nelson CS observation")
        diagnostics = {
            "station": parsed["station"], "station_reference": parsed["station_reference"],
            "returned_point": {key: newest[key] for key in ("latitude", "longitude", "elevation")},
            "provider": newest["provider"], "attribution": newest["attribution"],
            "processed_at": newest["processed_at"],
            "newest_valid_at": newest["valid_at"], "age_seconds": age.total_seconds(),
            "usable_readings": len(parsed["readings"]), "unit": "°C",
            "status": "fresh" if age <= 2 * HOUR else "stale",
        }
    else:
        point = LODGE if source == "forecast-lodge" else NELSON
        payload, content_type = fetch_json(forecast_url(point))
        parsed = normalize_forecast(payload, point)
        retrieved_at = datetime.now(UTC)
        windows = snowfall_windows(parsed, retrieved_at)
        diagnostics = {
            "requested_point": point, "returned_point": parsed["returned_point"],
            "model": parsed["model"], "model_issued_at": None, "units": parsed["units"],
            "first_valid_at": datetime.fromtimestamp(parsed["times"][0], UTC).isoformat(),
            "last_valid_at": datetime.fromtimestamp(parsed["times"][-1], UTC).isoformat(),
            "hours": len(parsed["times"]),
            "non_null_values": {key: sum(v is not None for v in items)
                                for key, items in parsed["values"].items()},
            "complete_72h_snow_windows": windows["max_rolling_24h"] is not None,
        }
    return {"endpoint": parsed["endpoint"], "content_type": content_type,
            "retrieved_at": retrieved_at.isoformat(), **diagnostics}


def demo(path):
    payloads = {
        "synthetic-whitewater-snow": normalize_resort_report(report_fixture()),
        "synthetic-whitewater-lodge": normalize_resort_weather(mountain_fixture("Whitewater Base")),
        "synthetic-whitewater-summit": normalize_resort_weather(mountain_fixture("Summit Top")),
        "synthetic-forecast-lodge": normalize_forecast(forecast_fixture(), LODGE),
        "synthetic-forecast-valley": normalize_forecast(forecast_fixture(NELSON), NELSON),
        "synthetic-eccc-nelson": normalize_valley(valley_fixture()),
    }
    with closing(open_store(path)) as db:
        summary = {}
        for source, payload in payloads.items():
            record(db, source, NOW, payload=payload)
            state = read_cache(db, source, NOW)
            summary[source] = {key: state[key] for key in ("status", "age_seconds")}
    return {"mode": "synthetic", "sources": summary,
            "snowfall_windows": snowfall_windows(payloads["synthetic-forecast-lodge"], NOW)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Run the synthetic trial").add_argument("database", type=Path)
    check = commands.add_parser("probe", help="Run one open-data request without persisting a payload")
    check.add_argument("source", choices=["forecast-lodge", "forecast-valley", "eccc"])
    snapshot = commands.add_parser("backup", help="Make a checked snapshot of the demo database")
    snapshot.add_argument("database", type=Path)
    snapshot.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            backup(args.database, args.destination)
            print("SQLite snapshot checked and saved")
        else:
            result = demo(args.database) if args.command == "demo" else probe(args.source)
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except (HTTPError, URLError, OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

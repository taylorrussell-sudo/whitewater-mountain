import json
import sqlite3
import subprocess
import sys
import unittest
from email.message import Message
from io import BytesIO
from unittest.mock import MagicMock, patch
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse

from poc.__main__ import RESPONSE_LIMIT, fetch_json
from poc.sources import (
    HOUR, LODGE, forecast_url, normalize_forecast, normalize_resort_report,
    normalize_resort_weather, normalize_valley, snowfall_windows, utc, valley_url,
)
from poc.store import backup, open_store, read_cache, record
from poc.synthetic import NOW, forecast_fixture, mountain_fixture, report_fixture, valley_fixture


class SourceTests(unittest.TestCase):
    def test_whitewater_report_keeps_windows_depth_and_update_separate(self):
        fixture = report_fixture()
        fixture["48h"] = None
        report = normalize_resort_report(fixture)
        self.assertEqual(report["elevation"], 1950)
        self.assertEqual(report["kind"], "reported")
        self.assertIsNone(report["observed_at"])
        self.assertEqual(report["report_updated_at"], "2026-01-15T16:30:00+00:00")
        self.assertEqual(report["values"], {
            "overnight": 6, "24h": 9, "48h": None, "3d": 16, "7d": 27,
            "season": 123, "base_depth": 77,
        })
        with self.assertRaises(ValueError):
            normalize_resort_report({**fixture, "unit": "mm"})

    def test_whitewater_weather_rejects_ambiguous_clock_and_invalid_wind(self):
        row = mountain_fixture("Whitewater Base")
        self.assertEqual(normalize_resort_weather(row)["elevation"], 1630)
        self.assertEqual(normalize_resort_weather({**row, "station": "Summit Top"})["elevation"], 2002)
        for change in ({"valid_at": "2026-11-01T01:00"}, {"wind_speed": -1},
                       {"wind_direction": 361}, {"wind_unit": "m/s"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_resort_weather({**row, **change})

    def test_forecast_contract_checks_units_clock_and_metadata(self):
        params = parse_qs(urlparse(forecast_url(LODGE)).query)
        self.assertEqual(params["models"], ["gem_global"])
        self.assertEqual(params["elevation"], ["1630"])
        fixture = forecast_fixture()
        fixture["longitude"] = -117.22
        parsed = normalize_forecast(fixture, LODGE)
        self.assertEqual(parsed["returned_point"]["longitude"], -117.22)
        self.assertEqual(parsed["requested_point"], LODGE)
        self.assertIsNone(parsed["model_issued_at"])
        for change in ({"utc_offset_seconds": -28800}, {"elevation": 1000},
                       {"hourly_units": {**fixture["hourly_units"], "snowfall": "mm"}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_forecast({**fixture, **change}, LODGE)

    def test_forecast_rejects_corrupt_hourly_arrays(self):
        for field, change in (("time", lambda a: a.__setitem__(1, a[0])),
                              ("snowfall", lambda a: a.__setitem__(0, -1)),
                              ("temperature_2m", lambda a: a.__setitem__(0, float("nan"))),
                              ("wind_speed_10m", lambda a: a.pop())):
            fixture = forecast_fixture()
            change(fixture["hourly"][field])
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalize_forecast(fixture, LODGE)

    def test_forecast_uses_end_of_hour_and_last_rolling_start(self):
        fixture = forecast_fixture()
        fixture["hourly"]["snowfall"] = [500] + [0] * 48 + [1] * 24 + [100] * 96
        forecast = normalize_forecast(fixture, LODGE)
        result = snowfall_windows(forecast, NOW)
        self.assertEqual(result["totals_cm"], {24: 0, 48: 0, 72: 24})
        self.assertEqual(result["max_rolling_24h"], {
            "cm": 24, "start": int((NOW + 48 * HOUR).timestamp()),
            "end": int((NOW + 72 * HOUR).timestamp()),
        })
        shifted = snowfall_windows(forecast, NOW + timedelta(minutes=20))
        self.assertEqual(shifted["start"], result["start"] + 3600)
        self.assertEqual(shifted["totals_cm"][72], 124)

    def test_forecast_missing_bin_is_distinct_from_zero_and_ties_use_first_start(self):
        fixture = forecast_fixture()
        fixture["hourly"]["snowfall"] = [0] * 169
        forecast = normalize_forecast(fixture, LODGE)
        result = snowfall_windows(forecast, NOW)
        self.assertEqual(result["max_rolling_24h"]["start"], result["start"])
        for field in fixture["hourly"]:
            fixture["hourly"][field].pop(70)
        result = snowfall_windows(normalize_forecast(fixture, LODGE), NOW)
        self.assertEqual(result["totals_cm"], {24: 0, 48: 0, 72: None})
        self.assertIsNone(result["max_rolling_24h"])

    def test_eccc_station_timestamp_unit_geometry_and_quality(self):
        params = parse_qs(urlparse(valley_url(NOW)).query)
        self.assertEqual(params["msc_id-value"], ["1145M29"])
        self.assertEqual(params["sortby"], ["-date_tm-value"])
        fixture = valley_fixture()
        reading = normalize_valley(fixture)["readings"][0]
        self.assertEqual(reading["valid_at"], "2026-01-15T17:00:00+00:00")
        self.assertEqual(reading["temperature_c"], -6.1)
        props = fixture["features"][0]["properties"]
        props["air_temp-uom"] = "°F"
        with self.assertRaises(ValueError):
            normalize_valley(fixture)
        props["air_temp-qa"] = -1
        self.assertEqual(normalize_valley(fixture)["readings"], [])
        props["msc_id-value"] = "different"
        with self.assertRaises(ValueError):
            normalize_valley(fixture)
        fixture = valley_fixture()
        fixture["features"][0]["geometry"]["coordinates"].append(1600)
        with self.assertRaisesRegex(ValueError, "elevation"):
            normalize_valley(fixture)


class TransportTests(unittest.TestCase):
    def test_rejects_html_and_oversize_responses(self):
        for media_type, data, error in (
                ("text/html", b"<html>", "Unexpected response type"),
                ("application/json", b" " * (RESPONSE_LIMIT + 1), "size cap")):
            with self.subTest(media_type=media_type), patch("poc.__main__.build_opener") as opener:
                response = MagicMock()
                response.headers = Message()
                response.headers["Content-Type"] = media_type
                response.read.side_effect = BytesIO(data).read
                opener.return_value.open.return_value.__enter__.return_value = response
                with self.assertRaisesRegex(ValueError, error):
                    fetch_json(forecast_url(LODGE))

    def test_json_response_has_meaningful_headers_and_a_timeout(self):
        with patch("poc.__main__.build_opener") as opener:
            response = MagicMock()
            response.headers = Message()
            response.headers["Content-Type"] = "application/geo+json"
            response.read.return_value = b'{"type":"FeatureCollection","features":[]}'
            connection = opener.return_value.open
            connection.return_value.__enter__.return_value = response
            payload, media_type = fetch_json(valley_url(NOW))
            self.assertEqual(payload["features"], [])
            self.assertEqual(media_type, "application/geo+json")
            args, kwargs = connection.call_args
            self.assertIn("WhitewaterMountain-PoC", args[0].get_header("User-agent"))
            self.assertEqual(kwargs["timeout"], 15)


class StorageTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "trial.sqlite"
        self.db = open_store(self.path)
        self.addCleanup(self.db.close)

    def test_cache_retains_last_success_and_tracks_new_versions(self):
        forecast = normalize_forecast(forecast_fixture(), LODGE)
        self.assertEqual(read_cache(self.db, "forecast", NOW)["status"], "unavailable")
        record(self.db, "forecast", NOW, payload=forecast)
        record(self.db, "forecast", NOW + HOUR, payload=forecast)
        record(self.db, "forecast", NOW + 2 * HOUR, error="timeout")
        record(self.db, "forecast", NOW, error="older result")
        state = read_cache(self.db, "forecast", NOW + 15 * HOUR)
        self.assertEqual(state["status"], "fresh")
        self.assertEqual(state["error"], "timeout")
        self.assertEqual(state["age_seconds"], 14 * 3600)
        self.assertEqual(self.db.execute("SELECT count(*) FROM snapshots").fetchone(), (1,))
        self.assertEqual(read_cache(self.db, "forecast", NOW + 16 * HOUR)["status"], "stale")
        self.assertEqual(read_cache(self.db, "forecast", NOW + 160 * HOUR)["status"], "unavailable")
        forecast["values"]["snowfall"][4] = 1
        record(self.db, "forecast", NOW + 16 * HOUR, payload=forecast)
        self.assertEqual(self.db.execute("SELECT count(*) FROM snapshots").fetchone(), (2,))
        record(self.db, "other", NOW, error="unreachable")
        self.assertEqual(read_cache(self.db, "other", NOW)["status"], "unavailable")
        self.assertEqual(read_cache(self.db, "forecast", NOW + 16 * HOUR)["status"], "fresh")

    def test_observation_and_report_age_never_come_from_fetch_timestamp(self):
        record(self.db, "valley", NOW, payload=normalize_valley(valley_fixture()))
        record(self.db, "report", NOW, payload=normalize_resort_report(report_fixture()))
        self.assertEqual(read_cache(self.db, "valley", NOW + 2 * HOUR)["status"], "stale")
        self.assertEqual(read_cache(self.db, "report", NOW + 2 * HOUR)["status"], "fresh")
        self.assertEqual(read_cache(self.db, "report", NOW + 30 * HOUR)["status"], "stale")
        future = normalize_resort_weather({**mountain_fixture("Whitewater Base"),
                                          "valid_at": "2026-01-15T19:00:00Z"})
        record(self.db, "future", NOW, payload=future)
        self.assertEqual(read_cache(self.db, "future", NOW)["status"], "unavailable")
        self.assertEqual(utc(future["valid_at"]), NOW + HOUR)

    def test_concurrent_duplicate_writes_and_rollback(self):
        report = normalize_resort_report(report_fixture())

        def collect(_):
            with closing(open_store(self.path)) as db:
                record(db, "report", NOW, payload=report)

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(collect, range(8)))
        self.db.executescript("""
            CREATE TRIGGER fail_attempt BEFORE UPDATE ON attempts
            BEGIN SELECT RAISE(ABORT, 'test transaction failure'); END;
        """)
        with self.assertRaises(sqlite3.IntegrityError):
            record(self.db, "report", NOW + HOUR, payload={**report, "unit": "test"})
        self.assertEqual(self.db.execute("SELECT count(*) FROM snapshots").fetchone(), (1,))

    def test_backup_copies_committed_wal_state_and_can_be_restored(self):
        self.db.execute("PRAGMA wal_autocheckpoint = 0")
        report = normalize_resort_report(report_fixture())
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        record(self.db, "report", NOW, payload=report)
        self.assertGreater(Path(str(self.path) + "-wal").stat().st_size, 0)
        self.db.execute("UPDATE snapshots SET data = 'uncommitted'")
        destination = self.path.with_name("restore.sqlite")
        try:
            backup(self.path, destination)
        finally:
            self.db.rollback()
        with closing(sqlite3.connect(destination)) as restored:
            self.assertEqual(restored.execute("PRAGMA journal_mode").fetchone(), ("delete",))
            self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone(), ("ok",))
            self.assertEqual(read_cache(restored, "report", NOW)["data"], report)
        with self.assertRaises(FileExistsError):
            backup(self.path, destination)

    def test_command_line_demo_is_synthetic_and_repeatable(self):
        command = [sys.executable, "-B", "-m", "poc", "demo", str(self.path)]
        first = subprocess.check_output(command)
        self.assertEqual(first, subprocess.check_output(command))
        self.assertEqual(json.loads(first)["mode"], "synthetic")
        self.assertEqual(self.db.execute("SELECT count(*) FROM snapshots").fetchone(), (6,))


if __name__ == "__main__":
    unittest.main()

"""Offline adapter, scheduler and SQLite regressions using invented weather."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from poc.sources import LODGE, NELSON
from poc.synthetic import NOW, forecast_fixture, valley_fixture

from mountain_service import store
from mountain_service.api import weather
from mountain_service.collect import Collector, FetchError, retry_after
from mountain_service.sources import FREEZING, HRDPS, IFS, NELSON_CS, PROFILE_FIELDS, crossings

ANCHOR = int(NOW.timestamp())


def forecast(now=ANCHOR, hours=48):
    payload = [forecast_fixture(point) for point in (LODGE, NELSON)]
    for row in payload:
        start = now // 3600 * 3600
        for field in row["hourly"]:
            row["hourly"][field] = row["hourly"][field][:hours]
        row["hourly"]["time"] = [start + 3600 * i for i in range(hours)]
    return payload


def profile(times=(ANCHOR,)):
    data = {**LODGE, "elevation": 1000, "utc_offset_seconds": 0,
            "hourly_units": {"time": "unixtime", **PROFILE_FIELDS}, "hourly": {"time": list(times)}}
    for field in PROFILE_FIELDS:
        data["hourly"][field] = [None] * len(times)
    for pressure, height, temperature in ((900, 1000, -4), (875, 1200, -2), (850, 1400, 2),
                                          (825, 1600, -1), (800, 1800, -4)):
        data["hourly"][f"temperature_{pressure}hPa"] = [temperature] * len(times)
        data["hourly"][f"geopotential_height_{pressure}hPa"] = [height] * len(times)
    return data


class AdaptersTest(unittest.TestCase):
    def test_pinned_models_and_independent_horizons(self):
        for source, model, hours in ((IFS, "ecmwf_ifs", "170"), (HRDPS, "gem_hrdps_continental", "48")):
            query = parse_qs(urlsplit(source.url(NOW)).query)
            self.assertEqual(query["models"], [model])
            self.assertEqual(query["forecast_hours"], [hours])
            self.assertEqual(len(query["latitude"][0].split(",")), 2)
            self.assertNotIn("freezing_level_height", query["hourly"][0])
        short = HRDPS.normalize(forecast(hours=45), NOW)
        self.assertEqual(short["model_grid_km"], 2.5)
        self.assertEqual(len(short["points"]["lodge"]["times"]), 45)
        self.assertIsNone(short["model_issued_at"])

    def test_forecast_contract_checks_and_missing_columns(self):
        payload = forecast()
        payload[1]["hourly"].pop("snowfall")
        payload[1]["hourly_units"].pop("snowfall")
        missing = IFS.normalize(payload, NOW)["points"]["nelson"]["values"]["snowfall"]
        self.assertEqual(missing, [None] * 48)
        payload[0]["hourly_units"]["snowfall"] = "mm"
        with self.assertRaises(ValueError):
            IFS.normalize(payload, NOW)
        payload[0]["hourly_units"]["snowfall"] = "cm"
        payload[0]["hourly"]["time"][1] = payload[0]["hourly"]["time"][0]
        with self.assertRaises(ValueError):
            IFS.normalize(payload, NOW)
        with self.assertRaises(ValueError):
            IFS.normalize(forecast(), NOW + timedelta(days=1))
        with self.assertRaises(ValueError):
            IFS.normalize(forecast()[::-1], NOW)

    def test_valley_identity_qa_valid_time_and_observation_kinds(self):
        data = valley_fixture()
        self.assertEqual(len(NELSON_CS.normalize(data, NOW)), 1)
        row = data["features"][0]["properties"]
        row["air_temp-qa"] = 99
        self.assertIsNone(NELSON_CS.normalize(data, NOW))
        row["air_temp-qa"] = 100
        self.assertIsNone(NELSON_CS.normalize(data, NOW + timedelta(hours=7)))
        self.assertIsNone(NELSON_CS.normalize(data, NOW - timedelta(hours=2)))
        row["wmo_synop_id-value"] = "00000"
        with self.assertRaises(ValueError):
            NELSON_CS.normalize(data, NOW)

    def test_profile_keeps_inversion_crossings_and_masks_ground(self):
        request = parse_qs(urlsplit(FREEZING.url(NOW)).query)
        self.assertEqual(request["models"], ["gfs025"])
        self.assertEqual(request["elevation"], ["nan"])
        samples = FREEZING.normalize(profile(), NOW)
        first, second = samples["crossings"][0]
        self.assertEqual(first, {"lower_m": 1300, "upper_m": 1300, "method": "linear_bracket"})
        self.assertAlmostEqual(second["lower_m"], 1533.33333333)
        self.assertIsNone(samples["model_issued_at"])

    def test_profile_does_not_bridge_gaps_or_extrapolate(self):
        self.assertEqual(crossings([(10, -3), (20, None), (30, 3), (40, 2)], 0), [])
        self.assertEqual(crossings([(10, -3), (20, 3), (30, 2)], 15), [])
        self.assertIsNone(crossings([(10, -3), (20, 3), (30, 2)], 25))
        self.assertIsNone(crossings([(10, -3), (9, 3), (30, 2)], 0))
        result = crossings([(10, -3), (20, 0), (30, 0), (40, 3)], 0)
        self.assertEqual(result, [{"lower_m": 20, "upper_m": 30, "method": "sampled_zero"}])


class StoreTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "mountain.sqlite"
        store.prepare(self.path)
        self.now = ANCHOR

    def views(self):
        with store.connect(self.path) as db:
            return weather(db, ("ifs", "nelson_cs", "hrdps", "freezing_profile"), self.now)["sources"]

    def test_manual_refresh_respects_provider_cooldown_stop_and_source_backoff(self):
        calls = []

        def fetch(url):
            calls.append(url)
            raise FetchError("unexpected_schema", "interval")

        collector = Collector(self.path, (IFS, HRDPS, NELSON_CS), lambda: self.now, fetch)
        with store.connect(self.path, write=True) as db:
            store.save(db, IFS, self.now, None, "http_429", 0, self.now + 180,
                       (False, self.now + 300))
            store.save(db, NELSON_CS, self.now, None, "http_403", 0, self.now + 3600,
                       (True, None))
            self.now += 120
            self.assertEqual(collector.refresh_if_due(db, IFS, manual=True), "provider_cooldown")
            self.assertEqual(collector.refresh_if_due(db, HRDPS, manual=True), "provider_cooldown")
            self.assertEqual(collector.refresh_if_due(db, NELSON_CS, manual=True), "provider_blocked")
            self.assertEqual(calls, [])
            self.now += 180
            self.assertEqual(collector.refresh_if_due(db, IFS, manual=True), "failed")
            self.now += 60
            self.assertEqual(collector.refresh_if_due(db, IFS, manual=True), "backoff")
            self.assertEqual(len(calls), 1)

    def test_scheduler_restart_good_cache_and_source_failure(self):
        calls = []
        attempts = 0

        def fetch(url):
            nonlocal attempts
            calls.append(url)
            if "weather.gc.ca" in url:
                return valley_fixture()
            if attempts:
                raise FetchError("timeout")
            attempts += 1
            return forecast(self.now)

        kwargs = dict(clock=lambda: self.now, fetch=fetch)
        Collector(self.path, (IFS, NELSON_CS), **kwargs).cycle()
        Collector(self.path, (IFS, NELSON_CS), **kwargs).cycle()
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.views()["nelson_cs"]["status"], "fresh")
        self.now += IFS.interval
        Collector(self.path, (IFS, NELSON_CS), **kwargs).cycle()
        sources = self.views()
        self.assertEqual(sources["ifs"]["status"], "fresh")
        self.assertEqual(sources["ifs"]["last_error"], "timeout")
        self.assertEqual(sources["ifs"]["next_attempt_at"], store.iso(self.now + 60))
        self.assertEqual(sources["nelson_cs"]["status"], "stale")
        self.now += 60
        Collector(self.path, (IFS,), **kwargs).cycle()
        self.assertEqual(self.views()["ifs"]["next_attempt_at"], store.iso(self.now + 120))
        self.now = ANCHOR + IFS.fresh_for + 1
        self.assertEqual(self.views()["ifs"]["status"], "stale")
        self.assertIsNone(self.views()["ifs"]["data"]["lodge_snowfall_windows"])
        self.now = ANCHOR + 49 * 3600
        self.assertEqual(self.views()["ifs"]["status"], "unavailable")

    def test_bad_source_schema_does_not_block_next_adapter(self):
        bad = forecast()
        bad[0]["hourly_units"] = []

        def fetch(url):
            return valley_fixture() if "weather.gc.ca" in url else bad

        Collector(self.path, (IFS, NELSON_CS), lambda: self.now, fetch).cycle()
        self.assertEqual(self.views()["ifs"]["last_error"], "unexpected_schema")
        self.assertEqual(self.views()["nelson_cs"]["status"], "fresh")

    def test_provider_cooldown_and_stop_survive_restart(self):
        contacted = []
        failure = FetchError("http_429", "provider_wait", "18000")

        def fetch(url):
            if "weather.gc.ca" in url:
                return valley_fixture()
            contacted.append(url)
            raise failure

        def run():
            Collector(self.path, (IFS, HRDPS, NELSON_CS), lambda: self.now, fetch).cycle()

        run()
        self.assertEqual(len(contacted), 1)
        self.assertEqual(self.views()["hrdps"]["next_attempt_at"], store.iso(ANCHOR + 18000))
        self.assertEqual(self.views()["nelson_cs"]["status"], "fresh")
        self.now += 17999
        run()
        self.assertEqual(len(contacted), 1)
        self.now += 1
        failure = FetchError("http_403", "stop")
        run()
        self.now += 2 * 86400
        run()
        self.assertEqual(len(contacted), 2)
        self.assertEqual(self.views()["hrdps"]["provider_state"], "blocked")
        self.assertEqual(self.views()["whitewater"]["status"], "disabled")
        self.assertIsNone(self.views()["southridge"]["data"])
        self.assertEqual(retry_after("Thu, 15 Jan 2026 18:20:00 GMT", ANCHOR), ANCHOR + 1200)

    def test_forecast_snapshot_dedup_retention_and_partial_snow(self):
        data = HRDPS.normalize(forecast(hours=45), NOW)
        with store.connect(self.path, write=True) as db:
            store.save(db, HRDPS, self.now, data, None, 0, self.now + 1)
            store.save(db, HRDPS, self.now + 1, data, None, 0, self.now + 2)
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots").fetchone()[0], 1)
            self.now += 1
            windows = self.views()["hrdps"]["data"]["lodge_snowfall_windows"]
            self.assertEqual(windows["totals_cm"][24], 0)
            self.assertIsNone(windows["totals_cm"][48])
            self.assertIsNone(windows["max_rolling_24h"])
            self.now += store.FORECAST_RETENTION + 1
            store.prune(db, self.now)
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots").fetchone()[0], 0)
            self.assertIsNone(store.state(db, "hrdps")["snapshot_id"])

    def test_observation_revision_distinct_features_and_retention(self):
        row, = NELSON_CS.normalize(valley_fixture(), NOW)
        earlier = {**row, "processed_at": "2026-01-15T17:00:10+00:00"}
        newer = {**row, "processed_at": "2026-01-15T17:00:30+00:00", "temperature_c": -5}
        alternate = {**earlier, "source_id": "other-feature"}
        with store.connect(self.path, write=True) as db:
            store.save(db, NELSON_CS, self.now, [earlier, alternate], None, 0, self.now + 1)
            store.save(db, NELSON_CS, self.now + 1, [newer], None, 0, self.now + 2)
            store.save(db, NELSON_CS, self.now + 2, [earlier], None, 0, self.now + 3)
            rows = store.observations(db, self.now + 2, 10)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["temperature_c"], -5)
            self.assertEqual(rows[0]["retrieved_at"], store.iso(self.now + 1))
            self.now += store.OBSERVATION_RETENTION + 1
            store.prune(db, self.now)
            self.assertEqual(db.execute("SELECT count(*) FROM nelson").fetchone()[0], 0)

    def test_online_backup_and_restore_during_uncommitted_write(self):
        snapshot = self.path.with_name("snapshot.sqlite")
        restored = self.path.with_name("restored.sqlite")
        row, = NELSON_CS.normalize(valley_fixture(), NOW)
        with store.connect(self.path, write=True) as db:
            store.save(db, NELSON_CS, self.now, [row], None, 0, self.now + 1)
            self.assertGreater(Path(str(self.path) + "-wal").stat().st_size, 0)
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE nelson SET temperature_c=999")
            store.copy_database(self.path, snapshot)
            db.rollback()
        store.copy_database(snapshot, restored)
        with store.connect(restored) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(store.observations(db, self.now, 1)[0]["temperature_c"], row["temperature_c"])
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            store.copy_database(snapshot, restored)
        unrelated = self.path.with_name("other.sqlite")
        with closing(sqlite3.connect(unrelated)):
            pass
        invalid = restored.with_name("invalid.sqlite")
        with self.assertRaises(ValueError):
            store.copy_database(unrelated, invalid)
        self.assertFalse(invalid.exists())
        Path(str(invalid) + "-wal").touch()
        with self.assertRaises(FileExistsError):
            store.copy_database(snapshot, invalid)

    def test_invalid_data_rolls_back_observation_batch_and_status(self):
        reading, = NELSON_CS.normalize(valley_fixture(), NOW)
        with store.connect(self.path, write=True) as db:
            with self.assertRaises(ValueError):
                store.save(db, NELSON_CS, self.now, [reading, {**reading, "valid_at": "invalid"}],
                           None, 0, self.now + 10)
            self.assertEqual(store.observations(db, self.now, 10), [])
            self.assertIsNone(store.state(db, "nelson_cs"))


if __name__ == "__main__":
    unittest.main()

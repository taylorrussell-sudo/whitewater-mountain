"""Synthetic Whitewater HTML, refresh policy, cache and comparison regressions."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mountain_service import store
from mountain_service.api import weather
from mountain_service.collect import Collector, FetchError
from mountain_service.sources import NELSON_CS, RESORT_SNOW, RESORT_WEATHER
from mountain_service.whitewater import PERMANENT_PACIFIC
from poc.synthetic import valley_fixture

NOW = datetime(2026, 11, 26, 18, tzinfo=timezone.utc)


def local(at):
    return datetime.fromtimestamp(at, PERMANENT_PACIFIC)


def snow_html(at, actual=22):
    stamp = local(at).strftime("%b %d, %Y at %H:%M")
    fields = (("24hr", actual), ("48hr", 26), ("3 Days", 33), ("7 Days", 52),
              ("Total Snowfall", 108), ("Current Base", 65))
    amounts = "".join(f"""
      <li><span class="condition-field__value">{value}</span>
      <span class="condition-field__unit">CM</span>
      <div class="condition-field__label">{label}</div></li>""" for label, value in fields)
    return f"""<main>
      <div class="snow-summary__item--overnight"><span class="value">17</span><span class="unit">cm</span></div>
      <div class="snow-summary__item--twentyfourhour"><span class="value">{actual}</span><span class="unit">cm</span></div>
      <div class="report-date"><p>Updated on {stamp}</p></div>
      <ul class="report-snowfall__list">{amounts}</ul>
      <p class="report-snowfall__source">Snow measurement at 1950 m</p></main>""".encode()


def station_html(at, lodge=-0.5, summit=1.3, summit_lag=3600):
    def table(name, stamp, temp, speed, direction):
        return f"""<h2>Last 24 hours at {name}</h2><br>
        <div><table class="weather-historic-table">
        <tr><th>Date &amp; Time</th><th>Air temp (°C)</th><th>Wind speed (km/hr)</th>
        <th>Prevailing Wind Direction</th><th>RH (%)</th></tr>
        <tr><td>{local(stamp):%b %d %H:%M}</td><td>{temp}</td>
        <td>{speed}</td><td>{direction}</td><td>74</td></tr></table></div>"""
    return (table("Summit Top - 2002 m", at - summit_lag, summit, 9.7, "270° (W)")
            + table("Whitewater Base - 1630 m", at, lodge, 0, "0° (N)")).encode()


class WhitewaterTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.sqlite"
        store.prepare(self.path)
        self.now = int(NOW.timestamp())

    def test_numerical_fields_and_schema_changes(self):
        html = snow_html(self.now, actual=0)
        data = RESORT_SNOW.normalize(html, NOW)
        self.assertEqual(data["report_updated_at"], NOW.isoformat())
        self.assertEqual(data["values"], {"overnight": 17, "24h": 0, "48h": 26,
                                          "3d": 33, "7d": 52, "season": 108, "base_depth": 65})
        mismatch = html.replace(b'class="value">0', b'class="value">4')
        self.assertIsNone(RESORT_SNOW.normalize(mismatch, NOW)["values"]["24h"])
        wrong_unit = html.replace(b'>CM<', b'>MM<')
        self.assertIsNone(RESORT_SNOW.normalize(wrong_unit, NOW)["values"]["base_depth"])
        with self.assertRaises(ValueError):
            RESORT_SNOW.normalize(snow_html(self.now + 3600), NOW)
        with self.assertRaises(ValueError):
            RESORT_WEATHER.normalize(station_html(self.now).replace(b'km/hr', b'm/s'), NOW)
        with self.assertRaises(ValueError):
            RESORT_WEATHER.normalize(b"<html>Access denied</html>", NOW)

    def test_station_time_rollover_units_and_partial_metrics(self):
        at = datetime(2027, 1, 1, 7, tzinfo=timezone.utc)
        html = station_html(int(at.timestamp()), lodge="—", summit_lag=3600)
        data = RESORT_WEATHER.normalize(html, at)["stations"]
        self.assertEqual(data["summit"]["valid_at"], (at - timedelta(hours=1)).isoformat())
        self.assertEqual(data["summit"]["wind_from_degrees"], 270)
        self.assertEqual(data["summit"]["wind_from"], "W")
        self.assertIsNone(data["lodge"]["temperature_c"])
        self.assertEqual(data["lodge"]["wind_kmh"], 0)

    def test_scheduler_spacing_rate_limit_and_durable_stop(self):
        calls = []
        failure = None

        def fetch(url):
            calls.append(url)
            if failure:
                raise failure
            return snow_html(self.now) if url == RESORT_SNOW.link else station_html(self.now)

        def collector():
            return Collector(self.path, (RESORT_SNOW, RESORT_WEATHER), lambda: self.now, fetch_resort=fetch)

        first = collector()
        first.cycle(manual=True)
        self.assertEqual(first.outcomes, {RESORT_SNOW.key: "updated", RESORT_WEATHER.key: "provider_spacing"})
        self.now += 9
        collector().cycle()
        self.assertEqual(calls, [RESORT_SNOW.link])
        self.now += 1
        collector().cycle()
        self.assertEqual(calls[-1], RESORT_WEATHER.link)
        self.now += RESORT_WEATHER.interval - 1
        early = collector()
        early.cycle(manual=True)
        self.assertEqual(set(early.outcomes.values()), {"recently_checked"})
        self.now += 1
        failure = FetchError("http_429", "provider_wait", "7200")
        collector().cycle()
        self.assertEqual(len(calls), 3)
        self.now += 7199
        collector().cycle(manual=True)
        self.assertEqual(len(calls), 3)
        failure = FetchError("http_403", "stop")
        self.now += 1
        collector().cycle()
        self.now += 24 * 3600
        blocked = collector()
        blocked.cycle(manual=True)
        self.assertEqual(set(blocked.outcomes.values()), {"provider_blocked"})
        self.assertEqual(len(calls), 4)

    def test_latest_only_freshness_and_measured_pair(self):
        valley = valley_fixture()
        row = valley["features"][0]
        at = NOW - timedelta(minutes=55)
        close_reading = {**row, "id": "close", "properties": {**row["properties"],
                         "obs_date_tm": (at + timedelta(minutes=5)).isoformat()}}
        row["properties"]["obs_date_tm"] = NOW.isoformat()
        valley["features"].append(close_reading)
        enabled = {RESORT_SNOW.key, RESORT_WEATHER.key, NELSON_CS.key}
        with store.connect(self.path, write=True) as db:
            report = RESORT_SNOW.normalize(snow_html(self.now - 3600), NOW)
            store.save(db, RESORT_SNOW, self.now - 60, report, None, 0, self.now)
            updated = RESORT_SNOW.normalize(snow_html(self.now), NOW)
            store.save(db, RESORT_SNOW, self.now, updated, None, 0, self.now)
            store.save(db, RESORT_SNOW, self.now + 1, None, "timeout", 1, self.now + 5)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 1)
            stations = RESORT_WEATHER.normalize(station_html(int(at.timestamp()), summit_lag=7200), NOW)
            store.save(db, RESORT_WEATHER, self.now, stations, None, 0, self.now)
            store.save(db, NELSON_CS, self.now, NELSON_CS.normalize(valley, NOW), None, 0, self.now)
            result = weather(db, enabled, self.now + 1)
            self.assertEqual(result["measured_inversion"]["nelson"]["valid_at"],
                             close_reading["properties"]["obs_date_tm"])
            mountain = result["sources"][RESORT_WEATHER.key]["data"]["stations"]
            self.assertEqual(mountain["lodge"]["status"], "fresh")
            self.assertEqual(mountain["summit"]["status"], "stale")
            self.assertEqual(result["sources"][RESORT_SNOW.key]["status"], "fresh")
            self.assertEqual(result["sources"][RESORT_SNOW.key]["last_error"], "timeout")
            self.assertIsNone(weather(db, enabled, self.now + 2 * 3600)["measured_inversion"])
            self.assertIsNone(weather(db, enabled - {NELSON_CS.key}, self.now + 1)["measured_inversion"])
            self.assertEqual(weather(db, enabled, self.now + 31 * 3600)["sources"][RESORT_SNOW.key]["status"], "stale")

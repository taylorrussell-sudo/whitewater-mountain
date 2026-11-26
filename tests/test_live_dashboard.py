"""Chromium tests of the private dashboard served by the real scheduler and API."""

import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

from mountain_service import store
from mountain_service.api import LocalAPI
from mountain_service.collect import Collector, FetchError
from mountain_service.sources import SOURCES
from mountain_service.tests.test_service import ANCHOR, forecast, profile
from poc.synthetic import valley_fixture


class LiveDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        playwright = sync_playwright().start()
        cls.addClassCleanup(playwright.stop)
        cls.browser = playwright.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH"))
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "mountain.sqlite"
        store.prepare(path)
        self.now = ANCHOR
        self.gate = Event()
        self.gate.set()
        self.ifs_error = None
        self.calls = []
        self.stale_nelson = False
        collector = Collector(path, tuple(SOURCES.values()), lambda: self.now, self.fetch, lambda: self.now)
        collector.cycle()
        stop = Event()
        failed = Event()
        api = LocalAPI(0, path, SOURCES, failed, lambda: self.now, collector)
        self.origin = f"http://127.0.0.1:{api.server_port}"
        http = Thread(target=api.serve_forever, daemon=True)
        http.start()
        self.addCleanup(api.server_close)
        self.addCleanup(http.join, 5)
        self.addCleanup(api.shutdown)
        worker = Thread(target=collector.run, args=(stop, failed), daemon=True)
        worker.start()

        def stop_worker():
            stop.set()
            self.gate.set()
            collector.wake.set()
            worker.join(5)

        self.addCleanup(stop_worker)
        self.page = self.browser.new_page(viewport={"width": 1920, "height": 1080})
        self.addCleanup(self.page.close)
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.requests = []
        self.page.on("request", lambda request: self.requests.append(request.url))
        self.page.goto(self.origin)
        expect(self.page.locator("#live-summary")).to_contain_text("ECMWF IFS HRES fresh")

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.assertTrue(all(url.startswith(self.origin + "/") for url in self.requests))

    def fetch(self, url):
        model = parse_qs(urlsplit(url).query).get("models", ["nelson"])[0]
        self.calls.append(model)
        anchor = self.now // 3600 * 3600
        if model == "nelson":
            payload = valley_fixture()
            valid = self.now - (10800 if self.stale_nelson else 600)
            payload["features"][0]["properties"]["obs_date_tm"] = datetime.fromtimestamp(
                valid, timezone.utc).isoformat()
            return payload
        if model == "gfs025":
            payload = profile([anchor + i * 3600 for i in range(3)])
            payload["hourly"]["temperature_850hPa"][1] = -2
            for name, series in payload["hourly"].items():
                if name != "time":
                    series[2] = None
            return payload
        if model == "ecmwf_ifs":
            if not self.gate.wait(8):
                raise AssertionError("Timed out waiting for fixture")
            if self.ifs_error:
                raise self.ifs_error
            payload = forecast(self.now, 169)
            payload[1]["hourly"]["temperature_2m"][:4] = [-1, -8, -10, -1]
            return payload
        payload = forecast(self.now, 45)
        payload[0]["hourly"]["snowfall"] = [0.25] * 45
        return payload

    def test_live_sources_layout_and_multiple_crossings(self):
        page = self.page
        expect(page.locator("#scenario")).to_be_hidden()
        expect(page.locator("#metrics .metric").nth(0)).to_contain_text("-6.1°C")
        expect(page.locator("#hrdps-summary")).to_contain_text("Next 24 h snow 6 cm")
        expect(page.locator("#powdercards .pred strong")).to_have_text("21.6 cm")
        expect(page.locator("#powdercards .powder").first).to_contain_text("Unavailable")
        expect(page.locator("#profile .freeze")).to_have_count(2)
        expect(page.locator("#profile-valid")).to_contain_text("1300 m, 1533 m")
        expect(page.locator("#inversion-comparison")).to_contain_text("+5.5°C · Notable")
        expect(page.locator("#inversion-timing")).to_contain_text("Duration 1–3 h")
        self.assertTrue(page.evaluate("document.documentElement.scrollHeight <= innerHeight"))
        page.locator('[data-tab="powder"]').click()
        expect(page.locator("#totals strong")).to_have_text(["0 cm", "16.2 cm", "21.6 cm"])
        page.locator("#hrdps-hourly summary").click()
        expect(page.locator("#hrdps-hourly tbody tr")).to_have_count(45)
        page.locator("#freezechart summary").click()
        expect(page.locator("#freezechart tbody")).to_contain_text("No crossing detected")
        expect(page.locator("#freezechart tbody")).to_contain_text("Unavailable")
        for width in (320, 390, 768):
            page.set_viewport_size({"width": width, "height": 844})
            for tab in ("overview", "powder", "webcams", "avalanche", "info"):
                with self.subTest(width=width, tab=tab):
                    page.locator(f'[data-tab="{tab}"]').click()
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        expect(page.locator("#live-sources")).to_contain_text("Last checked")
        expect(page.locator("#live-sources")).to_contain_text("Last successful check")
        expect(page.locator("#live-sources")).to_contain_text("Valid")
        expect(page.locator("#live-sources")).to_contain_text("Southridge")
        expect(page.locator("#live-sources")).to_contain_text("Unavailable · collection disabled")
        page.locator("#theme").select_option("light")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")

    def test_refresh_progress_partial_failure_staleness_and_recovery(self):
        page = self.page
        button = page.locator("#refresh-button")
        status = page.locator("#refresh-status")
        self.now += 61
        self.ifs_error = FetchError("http_503")
        self.gate.clear()
        button.click()
        expect(status).to_contain_text("ECMWF IFS HRES checking")
        expect(button).to_be_disabled()
        self.assertTrue(page.evaluate("document.documentElement.scrollHeight <= innerHeight"))
        expect(page.locator("#powdercards .pred strong")).to_have_text("21.6 cm")
        self.gate.set()
        expect(status).to_contain_text("ECMWF IFS HRES check failed")
        expect(status).to_contain_text("Canadian HRDPS check succeeded")
        expect(status).to_contain_text("Nelson CS skipped · recently checked")
        expect(page.locator("#powdercards .pred strong")).to_have_text("21.6 cm")
        self.assertEqual(self.calls.count("ecmwf_ifs"), 2)
        expect(button).to_have_text("Refresh Data (60s)")

        # Scheduled retry uses its original due time and can recover without a page action.
        self.now += 61
        self.ifs_error = None
        expect(button).to_be_enabled()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            ifs = page.request.get(self.origin + "/v1/weather").json()["sources"]["ifs"]
            if ifs["last_error"] is None:
                break
            time.sleep(0.05)
        self.assertIsNone(ifs["last_error"])
        self.assertEqual(self.calls.count("ecmwf_ifs"), 3)

        # Keep the last observation in SQLite and show it as stale without using it in a tile.
        self.stale_nelson = True
        self.now += 3 * 3600
        button.click()
        expect(page.locator("#live-summary")).to_contain_text("Nelson CS stale")
        expect(page.locator("#metrics .metric").first).to_contain_text("Unavailable")
        expect(page.locator("#inversion-comparison")).to_contain_text("Forecast")

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

from mountain_service import cameras, store
from mountain_service.api import LocalAPI
from mountain_service.collect import Collector, FetchError
from mountain_service.sources import RESORT_SNOW, RESORT_SOURCES, RESORT_WEATHER, SOURCES
from mountain_service.tests.test_cameras import jpeg, metadata
from mountain_service.tests.test_service import ANCHOR, forecast, profile
from mountain_service.tests.test_whitewater import NOW as RESORT_NOW, snow_html, station_html
from poc.synthetic import valley_fixture


class LiveDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        playwright = sync_playwright().start()
        cls.addClassCleanup(playwright.stop)
        cls.browser = playwright.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH"))
        cls.addClassCleanup(cls.browser.close)

    def start(self, resort=False):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "mountain.sqlite"
        store.prepare(path)
        self.now = int(RESORT_NOW.timestamp()) if resort else ANCHOR
        self.gate = Event()
        self.gate.set()
        self.ifs_error = None
        self.calls = []
        self.stale_nelson = False
        self.camera_frame_number = 0
        self.camera_offline = False
        self.resort_unavailable = False
        configured = tuple(source for source in SOURCES.values() if resort or source not in RESORT_SOURCES)
        if resort:
            Collector(path, (RESORT_SNOW,), lambda: self.now - 10, fetch_resort=self.fetch_resort).cycle()
        collector = Collector(path, (*configured, cameras.DRIVEBC), lambda: self.now, self.fetch,
                              lambda: self.now, self.fetch_image, fetch_resort=self.fetch_resort)
        collector.cycle()
        stop = Event()
        failed = Event()
        api = LocalAPI(0, path, {s.key for s in collector.sources}, failed, lambda: self.now, collector)
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

    def fetch_resort(self, url):
        if self.resort_unavailable:
            raise FetchError("http_503", "interval")
        if url == RESORT_SNOW.link:
            return snow_html(self.now - 3600)
        self.assertEqual(url, RESORT_WEATHER.link)
        return station_html(self.now)

    def fetch_image(self, url):
        self.assertEqual(url, cameras.IMAGE_URL)
        self.camera_frame_number += 1
        return jpeg(self.camera_frame_number)

    def fetch(self, url):
        if url == cameras.METADATA_URL:
            return metadata(self.now - 60, is_on=not self.camera_offline)
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
        self.start()
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

    def test_camera_selection_enlarge_refresh_and_stale_still(self):
        self.start()
        page = self.page
        road = page.locator('#camchips button').last
        image = page.locator('#camhero img')
        expect(road).to_have_attribute("aria-pressed", "true")
        expect(image).to_be_visible()
        self.assertEqual(image.evaluate("node => node.naturalWidth"), 320)
        original = image.get_attribute("src")
        reply = page.request.get(self.origin + original)
        self.assertEqual(reply.headers["content-type"], "image/jpeg")
        self.assertEqual(reply.body(), jpeg(1))
        self.assertIn("private", reply.headers["cache-control"])

        lodge = page.locator('#camchips button').first
        lodge.focus()
        page.keyboard.press("Enter")
        expect(lodge).to_be_focused()
        expect(page.locator('#camhero')).to_contain_text("Open official image")
        expect(image).to_have_count(0)
        page.reload()
        expect(lodge).to_have_attribute("aria-pressed", "true")
        road.click()

        enlarge = page.locator("#camhero [data-enlarge]")
        expect(enlarge).to_be_visible()
        enlarge.focus()
        page.keyboard.press("Enter")
        modal = page.get_by_role("dialog")
        expect(modal.locator("img")).to_be_visible()
        page.keyboard.press("Escape")
        expect(modal).to_be_hidden()
        expect(enlarge).to_be_focused()

        page.locator('[data-tab="webcams"]').click()
        expect(page.locator("#road-camera img")).to_be_visible()
        expect(page.locator("#cameragrid img")).to_have_count(1)
        expect(page.locator("#cameragrid")).to_contain_text("Weather Stick")
        page.set_viewport_size({"width": 390, "height": 844})
        gallery_url = "https://whitewatermountainresort.com/webcams/"
        gallery = page.get_by_role("link", name="Open Whitewater webcam gallery (new tab)")
        expect(gallery).to_have_attribute("href", gallery_url)
        self.assertGreaterEqual(gallery.bounding_box()["height"], 44)
        page.context.route(gallery_url, lambda route: route.fulfill(body="Official gallery fixture"))
        gallery.focus()
        with page.expect_popup() as new_tab:
            page.keyboard.press("Enter")
        popup = new_tab.value
        self.addCleanup(popup.close)
        expect(popup.locator("body")).to_have_text("Official gallery fixture")
        self.assertEqual(popup.url, gallery_url)
        self.assertTrue(popup.evaluate("window.opener === null && document.referrer === ''"))
        expect(page.locator("#webcams")).to_be_visible()

        page.locator("#road-camera [data-enlarge]").click()
        modal.get_by_role("button", name="Close").click()
        expect(modal).to_be_hidden()
        page.locator('[data-tab="overview"]').click()
        expect(road).to_have_attribute("aria-pressed", "true")

        self.now += cameras.MANUAL_SPACING
        page.locator("#refresh-button").click()
        expect(page.locator("#refresh-status")).to_contain_text("DriveBC check succeeded")
        expect(image).not_to_have_attribute("src", original)
        self.assertEqual(page.request.get(self.origin + original).status, 404)
        expect(page.locator("#weather-budget")).to_contain_text("5/6 left")

        self.camera_offline = True
        self.now += cameras.DRIVEBC.fresh_for + 1
        expect(page.locator("#camhero")).to_contain_text("Stale", timeout=20000)
        expect(image).to_be_visible()

    def test_refresh_progress_partial_failure_staleness_and_recovery(self):
        self.start()
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

    def test_whitewater_reports_mountain_conditions_and_measured_inversion(self):
        self.start(resort=True)
        page = self.page
        expect(page.locator("#metrics")).to_contain_text("Wind N 0 km/h")
        expect(page.locator("#metrics")).to_contain_text("Wind W 9.7 km/h")
        expect(page.locator("#metrics")).to_contain_text("22 cm")
        expect(page.locator("#powdercards .powder").first).to_have_attribute("data-level", "3")
        expect(page.locator("#powdercards .pred strong")).to_have_text("21.6 cm")
        observed = page.locator("#inversion-comparison .observed")
        expect(observed).to_contain_text("+5.6°C · Notable")
        expect(observed).to_contain_text("Valley Nov 26")
        expect(page.locator("#profile .cold-air-layer")).to_be_visible()
        self.assertTrue(page.evaluate("document.documentElement.scrollHeight <= innerHeight"))

        page.locator('[data-tab="powder"]').click()
        report = page.locator("#resort-report")
        expect(report.locator("strong")).to_have_text(
            ["17 cm", "22 cm", "26 cm", "33 cm", "52 cm", "108 cm", "65 cm"])
        expect(report.get_by_role("link", name="Whitewater Mountain Resort")).to_have_attribute(
            "href", RESORT_SNOW.link)

        self.now += 61
        page.locator("#refresh-button").click()
        expect(page.locator("#refresh-status")).to_contain_text("Whitewater weather skipped · recently checked")
        expect(page.locator("#refresh-status")).to_contain_text("Whitewater snow report skipped · recently checked")

        self.resort_unavailable = True
        self.now += 31 * 3600
        expect(page.locator("#refresh-button")).to_be_enabled()
        page.locator("#refresh-button").click()
        expect(page.locator("#powdercards2 .powder").first).to_contain_text("Unavailable")
        expect(report).to_contain_text("Stale")
        page.locator('[data-tab="overview"]').click()
        expect(observed).to_contain_text("Unavailable")
        expect(page.locator("#profile .cold-air-layer")).to_have_count(0)
        page.set_viewport_size({"width": 320, "height": 844})
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))

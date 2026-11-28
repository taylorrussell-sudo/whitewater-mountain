"""Camera gallery browser checks with bundled synthetic imagery."""

import os
import unittest
from functools import partial
from hashlib import sha256
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from mountain_service import cameras, store
from mountain_service.api import Handler, LocalAPI
from mountain_service.collect import Collector
from mountain_service.tests.test_cameras import jpeg
from mountain_service.tests.test_service import ANCHOR
import test_dashboard


RESORT_CAMERAS = {
    "Day Lodge": "lodge",
    "Summit": "summit",
    "Raven": "raven",
    "Glory Ridge": "glory",
    "Weather Stick": "weatherstick",
}
FIXTURE_PATH = "/mountain_service/camera_fixtures/"
FIFTEEN_MINUTES = 15 * 60 * 1000


class MockResortTiming(Handler):
    """Run the private dashboard with the same-origin fixture timing demo."""

    def send_content(self, status, data, content_type, retry_in=0, cache="no-store"):
        if content_type.startswith("text/html"):
            data = data.replace(b"<body data-live>", b"<body data-live data-resort-stills-demo>", 1)
        super().send_content(status, data, content_type, retry_in, cache)

    def send_header(self, keyword, value):
        if keyword.casefold() == "content-security-policy":
            value = value.replace("img-src 'self';", "img-src 'self' blob:;")
        super().send_header(keyword, value)


class CameraGalleryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = partial(test_dashboard.QuietHandler, directory=test_dashboard.ROOT)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        Thread(target=server.serve_forever, daemon=True).start()
        cls.addClassCleanup(server.server_close)
        cls.addClassCleanup(server.shutdown)
        cls.origin = f"http://127.0.0.1:{server.server_port}"
        playwright = sync_playwright().start()
        cls.addClassCleanup(playwright.stop)
        cls.browser = playwright.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH"))
        cls.addClassCleanup(cls.browser.close)

    def open_dashboard(self, width=1920, height=1080, mobile=False):
        page = self.browser.new_page(
            viewport={"width": width, "height": height}, is_mobile=mobile, has_touch=mobile
        )
        self.addCleanup(page.close)
        errors, external, images = [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: images.append(request.url)
                if request.resource_type == "image" else None)

        def same_origin(route):
            if route.request.url.startswith(self.origin + "/"):
                route.continue_()
            else:
                external.append(route.request.url)
                route.abort()

        page.route("**/*", same_origin)
        page.goto(self.origin + "/index.html")
        return page, images, errors, external

    def open_private_dashboard(self, *, timing_demo=False, image_status=None, mobile=False):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "camera.sqlite"
        store.prepare(path)
        image = jpeg()
        frame = cameras.Frame(ANCHOR - 60, False, sha256(image).hexdigest(), image)
        collector = Collector(path, (cameras.DRIVEBC,), lambda: ANCHOR)
        collector.camera_frame = frame
        server = LocalAPI(0, path, {cameras.DRIVEBC.key}, Event(), lambda: ANCHOR, collector)
        if timing_demo:
            server.RequestHandlerClass = MockResortTiming
        Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f"http://127.0.0.1:{server.server_port}"
        width, height = (390, 844) if mobile else (1920, 1080)
        page = self.browser.new_page(viewport={"width": width, "height": height}, has_touch=mobile, is_mobile=mobile)
        self.addCleanup(page.close)
        page.clock.install()
        page.add_init_script("""(() => {
            let browserVisible = true;
            Object.defineProperties(document, {
                hidden: {get: () => !browserVisible},
                visibilityState: {get: () => browserVisible ? 'visible' : 'hidden'}
            });
            window.setTestVisibility = visible => {
                browserVisible = visible;
                document.dispatchEvent(new Event('visibilitychange'));
            };
        })()""")
        requests, unexpected, errors = [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def only_fixture_traffic(route):
            request = route.request
            if not request.url.startswith(origin + "/"):
                unexpected.append(request.url)
                route.abort()
                return
            path = request.url.removeprefix(origin)
            if request.resource_type in ("fetch", "image") and path.startswith(FIXTURE_PATH):
                requests.append(path)
                status = image_status.get(path) if image_status else None
                if status:
                    route.fulfill(status=status)
                    return
            route.continue_()

        page.route("**/*", only_fixture_traffic)
        page.goto(origin)
        return page, requests, unexpected, errors

    def test_private_default_uses_only_synthetic_resort_images(self):
        page, requests, unexpected, errors = self.open_private_dashboard()
        page.get_by_role("button", name="Webcams", exact=True).click()
        gallery = page.locator("#gallery-camera")
        expect(gallery.locator("img")).to_have_attribute("src", "mountain_service/camera_fixtures/lodge.webp")
        expect(gallery.locator(".camera-preview-label")).to_have_text("Synthetic sample")
        expect(page.locator("#road-camera img")).to_be_visible()
        page.clock.fast_forward(2 * FIFTEEN_MINUTES)
        self.assertEqual(requests, [FIXTURE_PATH + "lodge.webp"])
        self.assertEqual(unexpected, [])
        self.assertEqual(errors, [])

    def test_demo_uses_only_selected_fixture_and_enlarges_existing_image(self):
        page, requests, unexpected, errors = self.open_private_dashboard(timing_demo=True)
        expect(page.locator("#camhero img")).to_be_visible()
        self.assertEqual(requests, [])
        page.get_by_role("button", name="Webcams", exact=True).click()
        gallery = page.locator("#gallery-camera")
        image = gallery.locator("img")
        expected_paths = []
        for camera, key in RESORT_CAMERAS.items():
            with self.subTest(camera=camera):
                gallery.get_by_role("button", name=camera, exact=True).click()
                expected_paths.append(FIXTURE_PATH + key + ".webp")
                expect(image).to_be_visible()
                self.assertEqual(requests, expected_paths)
                expect(gallery.get_by_role("link", name=f"{camera} still")).to_have_attribute(
                    "href", f"https://webcams.skiwhitewater.com/webcams/{key}/current.jpg"
                )
                expect(gallery.locator(".live-camera-date")).to_contain_text("Loaded by this browser")
                expect(gallery.locator(".camera-preview-label")).to_have_text("Synthetic sample")
        expect(gallery.locator("#gallery-mode")).to_have_text("Simulated refresh demo")
        expect(page.locator("#road-camera img")).to_have_attribute(
            "src", page.locator("#camhero img").get_attribute("src")
        )

        gallery.get_by_role("button", name="Day Lodge", exact=True).click()
        expect(image).to_be_visible()
        self.assertEqual(requests, expected_paths)
        image.evaluate("node => { window.selectedFixture = node; }")
        gallery.locator("[data-enlarge]").click()
        dialog = page.get_by_role("dialog", name="Day Lodge")
        expect(dialog.locator("img")).to_be_visible()
        self.assertTrue(dialog.locator("img").evaluate("node => node === window.selectedFixture"))
        page.keyboard.press("Escape")
        expect(dialog).to_be_hidden()
        expect(image).to_be_visible()
        self.assertEqual(requests, expected_paths)
        self.assertEqual(unexpected, [])
        self.assertEqual(errors, [])

    def test_demo_refresh_respects_interval_and_document_visibility(self):
        page, requests, unexpected, errors = self.open_private_dashboard(timing_demo=True)
        gallery = page.locator("#gallery-camera")
        image = gallery.locator("img")
        lodge = FIXTURE_PATH + "lodge.webp"
        page.evaluate("setTestVisibility(false)")
        page.get_by_role("button", name="Webcams", exact=True).click()
        expect(gallery).to_be_visible()
        self.assertEqual(requests, [])

        page.evaluate("setTestVisibility(true)")
        expect(image).to_be_visible()
        loaded = gallery.locator("time").get_attribute("datetime")
        self.assertEqual(requests, [lodge])
        page.clock.fast_forward(FIFTEEN_MINUTES - 5000)
        self.assertEqual(requests, [lodge])
        page.clock.fast_forward(6000)
        expect(gallery.locator("time")).not_to_have_attribute("datetime", loaded)
        self.assertEqual(requests, [lodge, lodge])

        page.evaluate("setTestVisibility(false)")
        loaded = gallery.locator("time").get_attribute("datetime")
        page.clock.fast_forward(FIFTEEN_MINUTES + 1000)
        self.assertEqual(requests, [lodge, lodge])
        expect(gallery.locator("time")).to_have_attribute("datetime", loaded)
        page.evaluate("setTestVisibility(true)")
        expect(gallery.locator("time")).not_to_have_attribute("datetime", loaded)
        self.assertEqual(requests, [lodge, lodge, lodge])

        page.get_by_role("button", name="Powder", exact=True).click()
        loaded = gallery.locator("time").get_attribute("datetime")
        page.clock.fast_forward(FIFTEEN_MINUTES + 1000)
        self.assertEqual(requests, [lodge, lodge, lodge])
        page.get_by_role("button", name="Webcams", exact=True).click()
        expect(gallery.locator("time")).not_to_have_attribute("datetime", loaded)
        self.assertEqual(requests, [lodge, lodge, lodge, lodge])
        self.assertEqual(unexpected, [])
        self.assertEqual(errors, [])

    def test_demo_failed_still_recovers_after_eligible_interval_on_phone(self):
        unavailable = FIXTURE_PATH + "weatherstick.webp"
        image_status = {unavailable: 503}
        page, requests, unexpected, errors = self.open_private_dashboard(
            timing_demo=True, mobile=True, image_status=image_status
        )
        page.set_viewport_size({"width": 390, "height": 300})
        page.get_by_role("button", name="Webcams", exact=True).tap()
        gallery = page.locator("#gallery-camera")
        frame = gallery.locator("#gallery-frame")
        self.assertGreaterEqual(frame.bounding_box()["y"], 300)
        page.clock.run_for(250)
        self.assertEqual(requests, [])
        page.set_viewport_size({"width": 390, "height": 844})
        gallery.get_by_role("button", name="Weather Stick", exact=True).tap()
        frame.scroll_into_view_if_needed()
        expect(gallery.get_by_role("status")).to_have_text("Sample image unavailable")
        expect(gallery.get_by_role("link", name="Weather Stick still")).to_be_visible()
        self.assertEqual(requests.count(unavailable), 1)
        image_status.clear()
        page.clock.fast_forward(FIFTEEN_MINUTES - 5000)
        self.assertEqual(requests.count(unavailable), 1)
        page.clock.fast_forward(6000)
        expect(gallery.locator("img")).to_be_visible()
        self.assertEqual(requests.count(unavailable), 2)
        self.assertEqual(unexpected, [])
        self.assertEqual(errors, [])

    def test_wall_requests_only_selected_stills_and_shows_stale_capture(self):
        page, images, errors, external = self.open_dashboard()
        expect(page.locator("#camhero img")).to_be_visible()
        self.assertEqual([urlsplit(url).path.rsplit("/", 1)[-1] for url in images], ["lodge.webp"])
        page.get_by_role("button", name="Webcams", exact=True).click()
        gallery = page.locator("#gallery-camera")
        expect(gallery.get_by_role("heading")).to_have_text("Day Lodge")
        expect(gallery.locator("img")).to_be_visible()
        expect(gallery.locator(".camera-preview-label")).to_have_text("Synthetic sample")
        expect(page.locator("#road-camera img")).to_be_visible()
        self.assertEqual({urlsplit(url).path.rsplit("/", 1)[-1] for url in images},
                         {"lodge.webp", "road.webp"})

        for camera, filename in [
            ("Summit", "summit"), ("Raven", "raven"), ("Glory Ridge", "glory"), ("Weather Stick", "weatherstick")
        ]:
            with self.subTest(camera=camera):
                button = gallery.get_by_role("button", name=camera, exact=True)
                button.click()
                expect(button).to_have_attribute("aria-pressed", "true")
                expect(gallery.get_by_role("heading")).to_have_text(camera)
                expect(gallery.locator("img")).to_be_visible()
                self.assertTrue(images[-1].endswith(f"/{filename}.webp"))
                if camera == "Raven":
                    expect(gallery.locator(".live-camera-date")).to_contain_text("Stale · Sample capture")
                    expect(gallery.locator("time")).to_have_attribute("datetime", "2026-01-17T13:35:00Z")
                    enlarge = gallery.get_by_role("button", name="Enlarge Raven sample")
                    enlarge.focus()
                    page.keyboard.press("Enter")
                    dialog = page.get_by_role("dialog", name="Raven")
                    expect(dialog.locator("img")).to_be_visible()
                    expect(dialog.locator(".live-camera-date")).to_contain_text("Stale")
                    page.keyboard.press("Escape")
                    expect(dialog).to_be_hidden()
                    expect(enlarge).to_be_focused()

        page.reload()
        page.get_by_role("button", name="Webcams", exact=True).click()
        expect(gallery.get_by_role("button", name="Weather Stick", exact=True)).to_have_attribute("aria-pressed", "true")
        self.assertEqual(external, [])
        self.assertEqual(errors, [])

    def test_iphone_loading_failure_and_simulated_offline(self):
        page, images, errors, external = self.open_dashboard(width=390, height=844, mobile=True)
        page.get_by_role("button", name="Webcams", exact=True).tap()
        gallery = page.locator("#gallery-camera")
        expect(gallery.locator("img")).to_be_visible()
        targets = gallery.locator("#gallery-chips button, #gallery-links a").all()
        for target in targets:
            bounds = target.bounding_box()
            self.assertGreaterEqual(bounds["width"], 44)
            self.assertGreaterEqual(bounds["height"], 44)

        pending = []
        page.route("**/summit.webp", lambda route: pending.append(route))
        gallery.get_by_role("button", name="Summit", exact=True).tap()
        expect(gallery.get_by_role("status")).to_have_text("Loading still…")
        pending.pop().continue_()
        expect(gallery.locator("img")).to_be_visible()

        page.route("**/glory.webp", lambda route: route.fulfill(status=503))
        gallery.get_by_role("button", name="Glory Ridge", exact=True).tap()
        expect(gallery.get_by_role("status")).to_have_text("Sample image unavailable")
        expect(gallery.get_by_role("button", name="Enlarge Glory Ridge sample")).to_be_hidden()
        expect(gallery.get_by_role("link", name="Glory Ridge still")).to_have_attribute(
            "href", "https://webcams.skiwhitewater.com/webcams/glory/current.jpg"
        )

        page.locator("#scenario").select_option("warm")
        gallery.get_by_role("button", name="Weather Stick", exact=True).tap()
        expect(gallery.get_by_role("status")).to_have_text("Simulated camera offline")
        self.assertFalse(any(url.endswith("/weatherstick.webp") for url in images))
        expect(gallery.get_by_role("link", name="Weather Stick still")).to_be_visible()
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        self.assertEqual(external, [])
        self.assertEqual(errors, [])

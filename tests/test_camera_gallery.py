"""Camera gallery browser checks with bundled synthetic imagery."""

import os
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

import test_dashboard


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

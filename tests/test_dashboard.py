import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest import TestCase

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
# Reported 24h, daily forecast, peak 24h start, current freezing level, avalanche bands.
SCENARIOS = {
    "powder": (26, [10, 18, 5, 2, 1, 4, 8], 24, 800, [3, 3, 2]),
    "storm": (5, [8, 35, 15, 5, 3, 2, 1], 24, 1000, [4, 3, 3]),
    "normal": (2, [1, 3, 0, 2, 0, 1, 2], 24, 1200, [2, 2, 1]),
    "warm": (0, [0, 0, 0, 3, 7, 2, 1], 0, 2350, [3, 3, 2]),
    "exceptional": (48, [30, 28, 14, 5, 1, 0, 2], 0, 550, [4, 4, 3]),
    "inversion": (1, [0, 1, 0, 0, 1, 0, 2], 24, 500, [2, 2, 1]),
}
TABS = ("overview", "powder", "webcams", "avalanche", "info")
CAMERAS = {
    "Day Lodge": "https://webcams.skiwhitewater.com/webcams/lodge/current.jpg",
    "Summit": "https://webcams.skiwhitewater.com/webcams/summit/current.jpg",
    "Raven": "https://webcams.skiwhitewater.com/webcams/raven/current.jpg",
    "Glory": "https://webcams.skiwhitewater.com/webcams/glory/current.jpg",
    "Snow plot": "https://webcams.skiwhitewater.com/webcams/weatherstick/current.jpg",
    "Access road": "https://www.drivebc.ca/",
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


class DashboardTest(TestCase):
    @classmethod
    def setUpClass(cls):
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=ROOT))
        Thread(target=server.serve_forever, daemon=True).start()
        cls.addClassCleanup(server.server_close)
        cls.addClassCleanup(server.shutdown)
        cls.origin = f"http://127.0.0.1:{server.server_port}/"

        playwright = sync_playwright().start()
        cls.addClassCleanup(playwright.stop)
        cls.browser = playwright.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_PATH"),
            ignore_default_args=["--hide-scrollbars"],
        )
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1920, "height": 1080})
        self.addCleanup(self.page.close)
        self.errors = []
        self.external_requests = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.route("**/*", self.route_request)
        response = self.page.goto(self.origin + "index.html")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body(), (ROOT / "index.html").read_bytes())

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.assertEqual(self.external_requests, [])

    def route_request(self, route):
        if route.request.url.startswith(self.origin):
            route.continue_()
        else:
            self.external_requests.append(route.request.url)
            route.abort()

    def tab(self, name):
        button = self.page.locator(f'[data-tab="{name}"]')
        button.click()
        expect(button).to_have_attribute("aria-current", "page")
        expect(self.page.locator(f"#{name}")).to_be_visible()
        expect(self.page.locator(".section.active")).to_have_count(1)

    def test_scenarios_tabs_and_wall_overview(self):
        ratings = ["", "Low", "Moderate", "Considerable", "High", "Extreme"]
        for scenario, (reported, snow, start, freeze, danger) in SCENARIOS.items():
            with self.subTest(scenario=scenario):
                self.tab("overview")
                self.page.locator("#scenario").select_option(scenario)
                expect(self.page.locator("#powdercards .powder strong").first).to_have_text(f"{reported} cm")
                profile_label = f"Schematic mountain elevations and freezing level {freeze} metres"
                if scenario == "inversion":
                    profile_label += ", with a schematic cold valley air layer"
                expect(self.page.locator("#profile svg")).to_have_attribute("aria-label", profile_label)
                peak = max(snow[:3])
                expect(self.page.locator("#powdersummary")).to_contain_text(
                    f"Peak forecast: {peak} cm from +{start}h to +{start + 24}h."
                )
                self.assertTrue(self.page.locator("#overview .card").evaluate_all(
                    "(cards) => cards.every(card => card.getBoundingClientRect().bottom <= innerHeight)"
                ))
                self.assertTrue(self.page.evaluate("document.documentElement.scrollHeight <= innerHeight"))
                self.page.get_by_role("button", name="Explore powder outlook →").press("Enter")
                expect(self.page.locator("#powder")).to_be_visible()
                expect(self.page.locator("#totals strong")).to_have_text(
                    [f"{sum(snow[:n])} cm" for n in (1, 2, 3)]
                )
                expect(self.page.locator("#powdercards2 .pred strong")).to_have_text(f"{peak} cm")
                for chart in ("overviewchart", "powderchart"):
                    expect(self.page.locator(f"#{chart} svg")).to_have_attribute(
                        "aria-label", f"Seven day snowfall: {', '.join(map(str, snow))} centimetres"
                    )
                expect(self.page.locator("#freezechart circle")).to_have_count(7)
                self.tab("avalanche")
                for where in ("dangerOverview", "dangerDetail"):
                    expect(self.page.locator(f"#{where} .danger strong")).to_have_text(
                        [f"{n} · {ratings[n]}" for n in danger]
                    )
                    expect(self.page.locator(f"#{where} .warn")).to_contain_text("Simulated ratings only.")

    def test_inversion_overview_states_and_theme(self):
        self.page.locator("#scenario").select_option("normal")
        observed = self.page.locator(".inversion-indicator.observed")
        forecast = self.page.locator(".inversion-indicator.forecast")
        timing = self.page.locator("#inversion-timing")
        key = self.page.locator("#cold-air-key")
        band = self.page.locator("#profile .cold-air-layer")
        expect(observed).to_contain_text("Observed · simulated")
        expect(observed).to_contain_text("-5°C · No positive inversion signal")
        expect(forecast).to_contain_text("Forecast · simulated")
        expect(forecast).to_contain_text("Unavailable")
        expect(band).to_have_count(0)
        expect(timing).to_be_hidden()

        self.page.locator("#scenario").select_option("inversion")
        expect(observed).to_contain_text("+8°C · Strong")
        expect(observed).to_contain_text("Valley -10°C · Lodge -2°C")
        expect(forecast).to_contain_text("+9°C · Strong")
        expect(forecast).to_contain_text("Valley -11°C · Lodge -2°C")
        expect(forecast).to_contain_text("Peak difference · +6h")
        expect(timing).to_have_text(
            "Illustrative timing · Onset +0h to +3h · Duration 6–12h · Dissipation +9h to +12h"
        )
        expect(key).to_have_text("Cold valley air · schematic")
        expect(key).to_be_visible()
        expect(self.page.locator("#temperature-plot svg")).to_have_accessible_name(
            "Temperature by elevation at Whitewater Lodge and Nelson valley. "
            "Circles show observations and diamonds show forecasts. Exact temperatures follow."
        )
        expect(self.page.locator("#temperature-plot .observed-point")).to_have_count(2)
        expect(self.page.locator("#temperature-plot .forecast-point")).to_have_count(2)
        freeze = self.page.locator("#profile .freeze")
        expect(freeze).to_have_count(1)
        self.page.emulate_media(reduced_motion="reduce")
        for theme in ("dark", "light"):
            self.page.locator("#theme").select_option(theme)
            expect(band).to_be_visible()
            expect(band).to_have_css("animation-name", "none")
            expect(observed).to_have_css("animation-name", "none")
            expect(forecast).to_have_css("border-left-style", "dashed")
            self.assertNotEqual(band.evaluate("el => getComputedStyle(el).fill"),
                                freeze.evaluate("el => getComputedStyle(el).stroke"))

        self.page.locator("#scenario").select_option("normal")
        expect(band).to_have_count(0)
        expect(key).to_be_hidden()
        expect(timing).to_be_hidden()
        expect(self.page.locator("#temperature-plot .forecast-point")).to_have_count(0)
        self.tab("info")
        expect(self.page.locator("#info")).to_contain_text("These provisional thresholds")
        expect(self.page.locator("#info")).to_contain_text("0°C or less")
        expect(self.page.locator("#info")).to_contain_text("3°C to below 6°C")
        expect(self.page.locator("#info")).to_contain_text("6°C or greater")

    def test_inversion_ski_context(self):
        self.page.locator("#scenario").select_option("normal")
        panel = self.page.locator("#inversion-ski-context")
        expect(panel).to_be_hidden()
        self.page.locator("#scenario").select_option("inversion")
        expect(panel).to_be_visible()
        expect(panel).to_contain_text("Observed · simulated:")
        expect(panel).to_contain_text("Less cold at lodge; wind and snow quality still matter.")
        expect(panel).to_contain_text("Valley fog / clear lodge (simulated).")
        expect(panel).to_contain_text("Forecast peak · simulated:")
        expect(panel).to_contain_text("Sky contrast unavailable.")
        self.page.evaluate("sc.inversion.skyComparison.hour = 3; render()")
        expect(panel).not_to_contain_text("Valley fog / clear lodge")
        self.page.evaluate("sc.inversion.lodge = 2; render()")
        expect(panel).to_contain_text("Above-freezing lodge air; snow softening possible.")
        self.page.evaluate("sc.inversion.lodge = 0; render()")
        expect(panel).to_contain_text("Lodge at freezing; snow response uncertain.")
        self.page.locator("#scenario").select_option("normal")
        expect(panel).to_be_hidden()

    def test_inversion_thresholds_and_comparable_pairs(self):
        cases = [
            (-1, "No positive inversion signal"), (0, "No positive inversion signal"),
            (0.01, "Weak"), (2.99, "Weak"), (3, "Notable"), (5.99, "Notable"),
            (6, "Strong"), (8, "Strong"),
        ]
        self.assertEqual(self.page.evaluate(
            """values => values.map(delta => {
                const pair = comparableTemperatures(stationSamples('observed', 0, 0, delta), 'observed');
                return inversionSignal(pair.delta);
            })""", [delta for delta, _ in cases]
        ), [label for _, label in cases])
        self.assertEqual(self.page.evaluate("""() => {
            const observed = stationSamples('observed', 0, -4, 0);
            return [
                comparableTemperatures(observed, 'observed'),
                comparableTemperatures(observed, 'forecast'),
                comparableTemperatures({...observed, lodge:{...observed.lodge, kind:'forecast'}}, 'observed'),
                comparableTemperatures({...observed, lodge:{...observed.lodge, hour:3}}, 'observed'),
                comparableTemperatures({...observed, lodge:{...observed.lodge, temp:null}}, 'observed'),
                comparableTemperatures({...observed, lodge:{...observed.lodge, temp:NaN}}, 'observed'),
                comparableTemperatures({valley:observed.valley}, 'observed'),
                comparableTemperatures(undefined, 'observed'),
            ];
        }"""), [{"hour": 0, "valley": -4, "lodge": 0, "delta": 4}] + [None] * 7)

    def test_forecast_timing_uses_adjacent_comparable_samples(self):
        examples = [
            ([(0, -1), (3, 3), (6, 6), (9, 6), (12, 0)], [6, [0, 3], [9, 12], [6, 12]]),
            ([(0, 0), (3, 3), (6, 0)], [3, [0, 3], [3, 6], [0, 6]]),
            ([(0, -1), (6, 6), (9, -1)], [6, None, [6, 9], None]),
            ([(0, -1), None, (6, 6), (9, -1)], [6, None, [6, 9], None]),
            ([(0, -1), (3, 6), None, (9, -1)], [3, [0, 3], None, None]),
            ([(0, 6), (3, 5)], [0, None, None, None]),
            ([(0, -1), (3, 0)], [3, None, None, None]),
            ([None], [None, None, None, None]),
            ([(0, 0), (3, 3), (6, 0), (9, 9), (12, 0)], [9, [6, 9], [9, 12], [0, 6]]),
        ]
        for samples, expected in examples:
            with self.subTest(samples=samples):
                self.assertEqual(self.page.evaluate(
                    """samples => {
                        const {pair, onset, dissipation, duration} = forecastInversion(samples.map(
                            sample => sample && stationSamples('forecast', sample[0], 0, sample[1])
                        ));
                        return [pair?.hour, onset, dissipation, duration];
                    }""", samples), expected)

    def test_forecast_signal_is_independent_of_observations_and_other_indicators(self):
        self.page.locator("#scenario").select_option("inversion")
        unrelated = ("#powdercards", "#dangerOverview", "#profile .freeze")
        before = [self.page.locator(selector).evaluate("el => el.outerHTML") for selector in unrelated]
        self.page.evaluate("""() => {
            sc.inversion.valley = undefined;
            sc.inversion.temperatureForecast[0].lodge.hour = 1;
            render();
        }""")
        expect(self.page.locator(".inversion-indicator.observed")).to_contain_text("Unavailable")
        expect(self.page.locator(".inversion-indicator.forecast")).to_contain_text("+9°C · Strong")
        expect(self.page.locator("#profile .cold-air-layer")).to_have_count(0)
        expect(self.page.locator("#inversion-timing")).to_contain_text(
            "Onset unavailable · Duration unavailable · Dissipation +9h to +12h"
        )
        after = [self.page.locator(selector).evaluate("el => el.outerHTML") for selector in unrelated]
        self.assertEqual(before, after)

    def test_peak_window_includes_last_start_and_breaks_ties_early(self):
        for snow, expected in [
            ([5, 5, 5], {"n": 5, "start": 0}),
            ([1, 2, 7, 30], {"n": 7, "start": 48}),
        ]:
            with self.subTest(snow=snow):
                self.assertEqual(self.page.evaluate("(snow) => peak({snow})", snow), expected)

    def test_camera_keyboard_and_links(self):
        buttons = self.page.locator("#camchips button")
        buttons.first.focus()
        for i, (name, url) in enumerate(CAMERAS.items()):
            button = buttons.nth(i)
            expect(button).to_be_focused()
            self.page.keyboard.press("Space" if i % 2 else "Enter")
            expect(button).to_be_focused()
            expect(button).to_have_css("outline-style", "solid")
            expect(button).to_have_attribute("aria-pressed", "true")
            expect(self.page.locator('#camchips [aria-pressed="true"]')).to_have_count(1)
            expect(self.page.locator("#camhero svg")).to_have_attribute(
                "aria-label", f"Illustrated placeholder for {name}"
            )
            expect(self.page.locator("#camlink a")).to_have_attribute("href", url)
            self.page.keyboard.press("Tab")
        expect(self.page.locator("#camlink a")).to_be_focused()
        self.page.locator("#scenario").select_option("warm")
        expect(buttons.last).to_have_attribute("aria-pressed", "true")
        self.tab("webcams")
        links = self.page.locator("#cameragrid .btnlink")
        self.assertEqual(links.evaluate_all("(links) => links.map(link => link.href)"), list(CAMERAS.values()))

    def test_responsive_layout(self):
        self.page.add_style_tag(content="html { scrollbar-gutter: stable }")
        self.page.locator("#scenario").select_option("inversion")
        for width in (320, 390, 420, 421, 640, 641, 768, 850, 851, 1024):
            self.page.set_viewport_size({"width": width, "height": 800})
            for tab in TABS:
                with self.subTest(width=width, tab=tab):
                    self.tab(tab)
                    clipped = self.page.evaluate("""() => {
                        const elements = document.querySelectorAll(
                            'html, .section.active :is(.card, .danger, .forecastdays, .powder, .orb, .metric, ' +
                            '.inversion-panel, .inversion-indicator)'
                        );
                        return [...elements]
                            .filter(el => el.scrollWidth > el.clientWidth + 1)
                            .map(el => el.id || el.querySelector('h2')?.textContent || el.className || el.tagName);
                    }""")
                    self.assertEqual(clipped, [])
                    if tab in ("overview", "powder", "info"):
                        self.assertTrue(self.page.locator(".section.active .orb").evaluate_all(
                            """orbs => orbs.every(orb => {
                                const card = orb.parentElement;
                                const padding = getComputedStyle(card);
                                return orb.offsetWidth <= card.clientWidth
                                    - parseFloat(padding.paddingLeft) - parseFloat(padding.paddingRight) + 1;
                            })"""
                        ))

    def test_camera_touch_targets(self):
        page = self.browser.new_page(viewport={"width": 320, "height": 800}, is_mobile=True, has_touch=True)
        self.addCleanup(page.close)
        page.goto(self.origin + "index.html")
        for selector in ("#camchips button, #camlink a", "#cameragrid .btnlink"):
            targets = page.locator(selector).all()
            self.assertTrue(targets)
            for target in targets:
                bounds = target.bounding_box()
                self.assertGreaterEqual(bounds["width"], 44)
                self.assertGreaterEqual(bounds["height"], 44)
            if selector.startswith("#camchips"):
                page.get_by_role("button", name="Summit", exact=True).tap()
                expect(page.locator("#camhero .overlay")).to_contain_text("Summit")
                page.get_by_role("button", name="Webcams", exact=True).tap()
                expect(page.locator("#webcams")).to_be_visible()

    def test_powder_thresholds_and_motion(self):
        reported = self.page.locator("#powdercards .powder").first.locator(".orb")
        forecast = self.page.locator("#powdercards .pred .orb")
        expect(reported).to_have_css("border-top-style", "solid")
        expect(forecast).to_have_css("border-top-style", "dashed")
        self.assertNotEqual(
            reported.evaluate("orb => getComputedStyle(orb).borderTopColor"),
            forecast.evaluate("orb => getComputedStyle(orb).borderTopColor"),
        )

        self.tab("info")
        slider = self.page.locator("#snowDemo")
        card = self.page.locator("#snowDemoCard .powder")
        orb = card.locator(".orb")
        effects = []
        for tier, (values, label) in enumerate([
            ((0, 4), "Normal conditions"),
            ((5, 9), "Fresh snow"),
            ((10, 14), "Powder watch"),
            ((15, 24), "Powder day"),
            ((25, 39), "Major powder day"),
            ((40, 60), "Exceptional snowfall"),
        ]):
            for value in values:
                slider.fill(str(value))
                expect(card).to_have_attribute("data-level", str(tier))
                expect(card.locator("h3")).to_have_text(label)
                expect(self.page.locator("#snowValue")).to_have_text(f"{value} cm")
                expect(orb).to_have_css("animation-name", "none" if tier < 3 else "breathe")
            effects.append(orb.evaluate("""orb => {
                const animation = orb.getAnimations()[0];
                if (animation) {
                    animation.pause();
                    animation.currentTime = animation.effect.getTiming().duration / 2;
                }
                const style = getComputedStyle(orb);
                return [style.borderTopColor, style.boxShadow];
            }"""))
        self.assertEqual(len({tuple(effect) for effect in effects}), 6)

        self.page.locator("#motion").check()
        expect(orb).to_have_css("animation-name", "none")
        self.assertNotEqual(orb.evaluate("orb => getComputedStyle(orb).boxShadow"), "none")
        self.page.locator("#motion").uncheck()
        self.page.emulate_media(reduced_motion="reduce")
        expect(orb).to_have_css("animation-name", "none")
        self.page.emulate_media(reduced_motion="no-preference")
        expect(orb).to_have_css("animation-name", "breathe")

    def test_avalanche_severity_colors_in_both_themes(self):
        self.page.locator("#scenario").select_option("storm")
        self.tab("avalanche")
        panel = self.page.locator("#dangerDetail")
        high = panel.locator(".d4")
        expect(high.locator("strong")).to_have_text("4 · High")
        for theme in ("dark", "light"):
            self.page.locator("#theme").select_option(theme)
            colors = panel.evaluate("""panel => {
                const sample = document.createElement('div');
                sample.innerHTML = danger({danger: [5, 2, 1]});
                panel.append(sample);
                const tiles = panel.querySelectorAll('.danger > div');
                const colors = [...tiles].map(tile => getComputedStyle(tile).borderTopColor);
                sample.remove();
                return [colors, getComputedStyle(panel).getPropertyValue('--line').trim()];
            }""")
            borders, neutral = colors
            self.assertEqual(len(set(borders)), 5)
            neutral_rgb = f"rgb({', '.join(str(int(neutral[i:i+2], 16)) for i in (1, 3, 5))})"
            self.assertNotIn(neutral_rgb, borders)

    def test_info_controls_themes_and_reload_defaults(self):
        self.page.locator('[data-tab="info"]').press("Space")
        expect(self.page.locator("#info")).to_be_visible()
        self.page.locator("#freezeDemo").fill("2500")
        expect(self.page.locator("#freezeValue")).to_have_text("2500 m")
        expect(self.page.locator("#infoprofile svg")).to_have_attribute(
            "aria-label", "Schematic mountain elevations and freezing level 2500 metres"
        )

        theme = self.page.locator("#theme")
        html = self.page.locator("html")
        theme.select_option("light")
        expect(html).to_have_attribute("data-theme", "light")
        theme.select_option("dark")
        expect(html).to_have_attribute("data-theme", "dark")
        self.page.emulate_media(color_scheme="light")
        theme.select_option("auto")
        expect(html).to_have_attribute("data-theme", "light")
        self.page.emulate_media(color_scheme="dark")
        expect(html).to_have_attribute("data-theme", "dark")

        self.page.locator("#scenario").select_option("exceptional")
        self.page.reload()
        expect(theme).to_have_value("dark")
        expect(self.page.locator("#scenario")).to_have_value("powder")
        expect(self.page.locator("#overview")).to_be_visible()

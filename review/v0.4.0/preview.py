"""Run the private dashboard on generated weather and a disposable loopback service."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
from urllib.parse import parse_qs, urlsplit

REVIEW = Path(__file__).resolve().parent
sys.path.insert(0, str(REVIEW.parents[1]))

from mountain_service import cameras, store, whitewater
from mountain_service.api import DASHBOARD, Handler, LocalAPI
from mountain_service.collect import Collector
from mountain_service.sources import NELSON_CS, RESORT_SNOW, RESORT_WEATHER, SOURCES
from mountain_service.tests.test_cameras import metadata
from mountain_service.tests.test_service import forecast, profile
from mountain_service.tests.test_whitewater import NOW, snow_html, station_html
from poc.synthetic import valley_fixture


SCENARIOS = {
    "fresh": "Fresh snowfall",
    "freezing": "Changing freezing levels",
    "stale": "Stale data and unavailable cameras",
}


class PreviewInputs:
    def __init__(self, scenario):
        self.scenario = scenario
        self.now = int(NOW.timestamp()) - whitewater.CRAWL_DELAY

    def clock(self):
        return self.now

    def weather(self, url):
        if url == cameras.METADATA_URL:
            return metadata(self.now - 60, is_on=self.scenario != "stale")
        if url == NELSON_CS.url(NOW):
            payload = valley_fixture()
            observed = self.now - (3 * 3600 if self.scenario == "stale" else 600)
            payload["features"][0]["properties"]["obs_date_tm"] = datetime.fromtimestamp(
                observed, timezone.utc).isoformat()
            return payload
        model = parse_qs(urlsplit(url).query).get("models", [None])[0]
        if model == "gfs025":
            start = self.now // 3600 * 3600
            payload = profile([start + hour * 3600 for hour in range(12)])
            if self.scenario == "freezing":
                # A double crossing, a warming layer higher up, then a gap.
                payload["hourly"]["temperature_850hPa"][3:6] = [-1] * 3
                payload["hourly"]["temperature_825hPa"][3:6] = [2] * 3
                payload["hourly"]["temperature_800hPa"][3:6] = [-2] * 3
                for field, values in payload["hourly"].items():
                    if field != "time":
                        values[8] = None
            return payload
        if model == "ecmwf_ifs":
            payload = forecast(self.now, 169)
            payload[0]["hourly"]["snowfall"][5:17] = [0.5] * 12
            payload[1]["hourly"]["temperature_2m"][:4] = [-1, -8, -10, -1]
            return payload
        if model == "gem_hrdps_continental":
            payload = forecast(self.now, 45)
            payload[0]["hourly"]["snowfall"] = [0.25] * 45
            return payload
        raise ValueError("Unknown forecast fixture")

    def resort(self, url):
        if url == RESORT_SNOW.link:
            age = 31 if self.scenario == "stale" else 1
            return snow_html(self.now - age * 3600)
        if url == RESORT_WEATHER.link:
            age = 3 if self.scenario == "stale" else 0
            lodge, summit = (1.5, -2) if self.scenario == "freezing" else (-0.5, -3.3)
            return station_html(self.now - age * 3600, lodge=lodge, summit=summit, summit_lag=900)
        raise ValueError("Unknown Whitewater fixture")

    def image(self, url):
        if url != cameras.IMAGE_URL:
            raise ValueError("Unknown camera fixture")
        return (REVIEW / "road-fixture.jpg").read_bytes()


class PreviewHandler(Handler):
    def dashboard_route(self):
        if self.path not in ("/", "/index.html"):
            super().dashboard_route()
            return
        scenario = self.server.scenario
        fixture_state = ' data-camera-fixtures="offline"' if scenario == "stale" else ""
        heading = f"<strong>Synthetic preview · {SCENARIOS[scenario]}</strong>"
        html = DASHBOARD.read_text(encoding="utf-8").replace(
            "<body>", f"<body data-live{fixture_state}>", 1).replace(
            "<strong>Private weather dashboard</strong>", heading, 1).replace(
            "<strong>Private weather</strong>", heading, 1).replace(
            "</body>", '<script src="/dashboard.js"></script></body>', 1)
        self.send_content(200, html.encode(), "text/html; charset=utf-8")


def serve(scenario, port):
    fixtures = PreviewInputs(scenario)
    stop, failed = Event(), Event()
    with TemporaryDirectory(prefix="whitewater-preview-") as directory:
        path = Path(directory) / "mountain.sqlite"
        store.prepare(path)
        options = {"clock": fixtures.clock, "fetch": fixtures.weather, "fetch_resort": fixtures.resort,
                   "fetch_image": fixtures.image}
        # Reserve the same provider spacing the production collector uses.
        Collector(path, (RESORT_SNOW,), **options).cycle()
        fixtures.now = int(NOW.timestamp())
        sources = (*SOURCES.values(), cameras.DRIVEBC)
        collector = Collector(path, sources, **options)
        collector.cycle()
        with LocalAPI(port, path, {source.key for source in sources}, failed, fixtures.clock, collector) as api:
            api.RequestHandlerClass = PreviewHandler
            api.scenario = scenario
            worker = Thread(target=collector.run, args=(stop, failed), daemon=True)
            worker.start()
            print(f"Synthetic preview · {SCENARIOS[scenario]} · http://127.0.0.1:{api.server_port}", flush=True)
            try:
                api.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                stop.set()
                collector.wake.set()
                worker.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="fresh")
    parser.add_argument("--port", type=int, default=8766, help="Loopback HTTP port (default 8766)")
    args = parser.parse_args()
    serve(args.scenario, args.port)

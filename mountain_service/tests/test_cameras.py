"""DriveBC timestamp, format and cache policy regressions with synthetic stills."""

from base64 import b64decode
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from mountain_service import cameras, store
from mountain_service.api import camera_view
from mountain_service.collect import Collector, DAILY_WEATHER_REFRESHES, FetchError
from mountain_service.sources import IFS
from mountain_service.tests.test_service import ANCHOR


# Solid grey fixture generated for tests. The JPEG comment makes revisions distinct.
GREY = b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4n"
    "ICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAC0AUABAREA/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/"
    "xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAA/AIY"
    + "A" * 306 + "f/Z"
)


def jpeg(revision=0):
    return GREY[:2] + b"\xff\xfe\x00\x03" + bytes([revision]) + GREY[2:]


def metadata(at, **overrides):
    return {"id": 759, "credit": "", "orientation": "N", "highway": "6", "is_on_demand": False,
            "is_on": True, "should_appear": True, "marked_delayed": False, "marked_stale": False,
            "last_update_modified": store.iso(at), **overrides}


class CameraTest(unittest.TestCase):
    def test_frame_timestamp_and_contract(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return jpeg()

        now = ANCHOR
        first = cameras.update(metadata(now), None, now, fetch)
        self.assertEqual(cameras.jpeg_dimensions(first.jpeg), (320, 180))
        self.assertEqual(first.modified, now)
        self.assertEqual(calls, [cameras.IMAGE_URL])
        self.assertTrue(cameras.update(metadata(now, marked_stale=True), first, now, fetch).delayed)
        self.assertEqual(calls, [cameras.IMAGE_URL])
        same = cameras.update(metadata(now + 60), first, now + 60, fetch)
        self.assertEqual(same.modified, first.modified)
        self.assertEqual(same.revision, first.revision)
        for payload in (metadata(now, credit="Partner"), metadata(now, is_on=False),
                        metadata(now + 600), metadata(now - cameras.MAX_AGE - 1),
                        metadata(now, last_update_modified="2026-11-26T10:00:00")):
            with self.subTest(payload=payload), self.assertRaises(cameras.InvalidCamera):
                cameras.update(payload, None, now, fetch)
        for invalid in (b"<html>offline", jpeg()[:-2], jpeg() + bytes(cameras.MAX_IMAGE)):
            with self.subTest(length=len(invalid)), self.assertRaises(cameras.InvalidCamera):
                cameras.update(metadata(now), None, now, lambda url: invalid)

    def test_camera_refresh_is_independent_of_weather_budget(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "service.sqlite"
            store.prepare(path)
            now = ANCHOR
            failure = False
            metadata_calls = []

            def fetch(url):
                self.assertEqual(url, cameras.METADATA_URL)
                metadata_calls.append(now)
                if failure:
                    raise FetchError("http_429", "provider_wait", "1800")
                return metadata(now - 30)

            collector = Collector(path, (IFS, cameras.DRIVEBC), lambda: now, fetch,
                                  fetch_image=lambda url: jpeg(len(metadata_calls)))
            with store.connect(path, write=True) as db:
                store.save(db, IFS, now, {}, None, 0, now + IFS.interval)
                for _ in range(DAILY_WEATHER_REFRESHES):
                    store.charge_manual_weather(db, now // 86400, DAILY_WEATHER_REFRESHES)
                self.assertEqual(collector.refresh_if_due(db, cameras.DRIVEBC), "updated")
                first = collector.camera_frame.revision
                now += cameras.MANUAL_SPACING - 1
                self.assertEqual(collector.refresh_if_due(db, cameras.DRIVEBC, set()), "recently_checked")
                now += 1
                self.assertEqual(collector.refresh_if_due(db, IFS, set()), "weather_budget_exhausted")
                self.assertEqual(collector.refresh_if_due(db, cameras.DRIVEBC, set()), "updated")
                frame = collector.camera_frame
                self.assertNotEqual(frame.revision, first)
                self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE source = ?",
                                            (cameras.DRIVEBC.key,)).fetchone()[0], 0)
                self.assertEqual(camera_view(db, {cameras.DRIVEBC.key}, frame, now)["status"], "fresh")
                now += cameras.DRIVEBC.interval
                failure = True
                self.assertEqual(collector.refresh_if_due(db, cameras.DRIVEBC), "failed")
                self.assertEqual(collector.refresh_if_due(db, cameras.DRIVEBC, set()), "provider_cooldown")
                self.assertIs(collector.camera_frame, frame)
                self.assertEqual(len(metadata_calls), 3)
                now = frame.modified + cameras.DRIVEBC.fresh_for + 1
                self.assertEqual(camera_view(db, {cameras.DRIVEBC.key}, frame, now)["status"], "stale")
                now = frame.modified + cameras.MAX_AGE + 1
                self.assertEqual(camera_view(db, {cameras.DRIVEBC.key}, frame, now)["status"], "unavailable")

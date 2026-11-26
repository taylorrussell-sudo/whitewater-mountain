"""Real loopback transport, API and process recovery with synthetic upstreams."""

import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from mountain_service import store
from mountain_service.api import LocalAPI
from mountain_service.collect import Collector, FetchError, fetch_json
from mountain_service.sources import IFS, NELSON_CS
from poc.synthetic import valley_fixture
from test_service import ANCHOR, forecast


class Upstream(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.calls.append(self.path)
        code, headers, data = self.server.responses[self.path]
        if self.path == "/timeout":
            time.sleep(0.25)
        self.send_response(code)
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (ConnectionError, TimeoutError):
            pass


def get(port, path, **headers):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        return response.status, response.getheaders(), payload
    finally:
        connection.close()


class HTTPTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "mountain.sqlite"

    def run_server(self, server):
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(worker.join)
        self.addCleanup(server.shutdown)
        return server.server_port

    def test_loopback_failure_and_recovery_without_request_driven_polling(self):
        store.prepare(self.path)
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        upstream.calls = []
        as_json = {"Content-Type": "application/json"}
        upstream.responses = {
            "/ifs": (503, as_json, b"{}"),
            "/obs": (200, as_json, json.dumps(valley_fixture()).encode()),
        }
        origin = f"http://127.0.0.1:{self.run_server(upstream)}"
        now = ANCHOR
        enabled = {"ifs", "nelson_cs"}
        failed = threading.Event()
        api = LocalAPI(0, self.path, enabled, failed, lambda: now)
        port = self.run_server(api)
        with patch.dict(os.environ, {"no_proxy": "127.0.0.1"}):
            with patch.object(type(IFS), "url", return_value=origin + "/ifs"):
                with patch.object(type(NELSON_CS), "url", return_value=origin + "/obs"):
                    collector = Collector(self.path, (IFS, NELSON_CS), lambda: now)
                    collector.cycle()
                    status, headers, payload = get(port, "/v1/weather")
                    self.assertEqual(status, 200)
                    self.assertIn(("Cache-Control", "no-store"), headers)
                    self.assertEqual(payload["sources"]["ifs"]["last_error"], "http_503")
                    self.assertEqual(payload["sources"]["ifs"]["status"], "unavailable")
                    self.assertEqual(payload["sources"]["nelson_cs"]["status"], "fresh")
                    self.assertEqual(len(get(port, "/v1/observations/nelson")[2]["readings"]), 1)
                    self.assertEqual(len(upstream.calls), 2)
                    now += 60
                    upstream.responses["/ifs"] = (200, as_json, json.dumps(forecast()).encode())
                    collector.cycle()
                    self.assertEqual(get(port, "/v1/weather")[2]["sources"]["ifs"]["status"], "fresh")
                    self.assertEqual(len(upstream.calls), 3)
        self.assertEqual(get(port, "/v1/weather", Host="outside.invalid")[0], 403)
        self.assertEqual(get(port, "/v1/weather", Origin="https://outside.invalid")[0], 403)
        self.assertEqual(get(port, "/missing")[0], 404)
        self.assertEqual(get(port, "/healthz")[0], 200)
        failed.set()
        self.assertEqual(get(port, "/healthz")[0], 503)
        failed.clear()
        self.path.rename(self.path.with_name("moved.sqlite"))
        with self.assertLogs(level="ERROR"):
            self.assertEqual(get(port, "/healthz")[0], 503)

    def test_transport_limits_retry_after_and_redirects(self):
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        as_json = {"Content-Type": "application/json"}
        upstream.calls = []
        upstream.responses = {
            "/limit": (429, {**as_json, "Retry-After": "600"}, b"{}"),
            "/stop": (403, as_json, b"{}"),
            "/redirect": (302, {"Location": "/stop"}, b""),
            "/invalid": (200, as_json, b"no json"),
            "/large": (200, as_json, b" " * (1024 * 1024 + 1)),
            "/type": (200, {"Content-Type": "text/html"}, b"{}"),
            "/timeout": (200, as_json, b"{}"),
        }
        origin = f"http://127.0.0.1:{self.run_server(upstream)}"
        with patch.dict(os.environ, {"no_proxy": "127.0.0.1"}):
            for path, code, mode in (
                ("/limit", "http_429", "provider_wait"),
                ("/stop", "http_403", "stop"),
                ("/redirect", "http_302", "interval"),
                ("/invalid", "invalid_json", "interval"),
                ("/large", "response_too_large", "interval"),
                ("/type", "unexpected_content_type", "interval"),
            ):
                with self.subTest(path=path), self.assertRaises(FetchError) as caught:
                    fetch_json(origin + path)
                self.assertEqual((caught.exception.code, caught.exception.policy), (code, mode))
                if path == "/limit":
                    self.assertEqual(caught.exception.retry_after, "600")
            with patch("mountain_service.collect.HTTP_TIMEOUT", 0.05):
                with self.assertRaisesRegex(FetchError, "timeout"):
                    fetch_json(origin + "/timeout")
        self.assertEqual(upstream.calls.count("/stop"), 1)

    def test_process_lock_crash_and_cli_backup_restore(self):
        def start(path):
            process = subprocess.Popen(
                [sys.executable, "-B", "-m", "mountain_service", "serve", "--db", str(path), "--port", "0"],
                stderr=subprocess.PIPE, text=True,
            )
            self.addCleanup(process.stderr.close)

            def stop():
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)

            self.addCleanup(stop)
            line = process.stderr.readline()
            match = re.search(r"127\.0\.0\.1:(\d+)", line)
            self.assertIsNotNone(match, line)
            return process, int(match.group(1))

        process, port = start(self.path)
        result = subprocess.run([sys.executable, "-B", "-m", "mountain_service", "serve", "--db",
                                 str(self.path), "--port", "0"], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"already owns", result.stderr)
        snapshot = self.path.with_name("backup.sqlite")
        restored = self.path.with_name("restored.sqlite")
        with store.connect(self.path, write=True) as db:
            # Keep the WAL open across SIGKILL to exercise the restart path.
            now = int(time.time())
            store.save(db, IFS, now, {"synthetic": True}, None, 0, now + 3600)
            self.assertTrue(Path(str(self.path) + "-wal").exists())
            self.assertEqual(get(port, "/healthz")[0], 200)
            subprocess.run([sys.executable, "-B", "-m", "mountain_service", "backup",
                            str(self.path), str(snapshot)], check=True, timeout=10)
            process.kill()
            process.wait(timeout=10)
            restarted, port = start(self.path)
            self.assertEqual(get(port, "/healthz")[0], 200)
            restarted.terminate()
            self.assertEqual(restarted.wait(timeout=10), 0)
        subprocess.run([sys.executable, "-B", "-m", "mountain_service", "restore",
                        str(snapshot), str(restored)], check=True, timeout=10)
        _, restored_port = start(restored)
        self.assertEqual(get(restored_port, "/healthz")[0], 200)
        with store.connect(restored) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(store.state(db, "ifs")["last_success"], now)


if __name__ == "__main__":
    unittest.main()

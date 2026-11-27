"""Optional integration test of the shipped edge templates on development loopback."""

import http.client
import os
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "deploy" / "pi"


@unittest.skipUnless(os.getenv("NGINX_PATH"), "set NGINX_PATH to run the private edge smoke test")
class PrivateEdgeTest(unittest.TestCase):
    def test_private_lan_and_tailnet_origin_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ingress = root / "ingress"
            ingress.mkdir()
            runtime = root / "run"
            runtime.mkdir()
            with socket.socket() as backend, socket.socket() as lan, socket.socket() as tailnet:
                for listener in (backend, lan, tailnet):
                    listener.bind(("127.0.0.1", 0))
                api_port, lan_port, tail_port = (s.getsockname()[1] for s in (backend, lan, tailnet))

            def render(template, target, replacements=()):
                settings = (TEMPLATES / (template + ".example")).read_text()
                for original, replacement in (
                    ("/etc/whitewater-mountain", str(root)),
                    ("/run/whitewater-mountain-edge", str(runtime)),
                    *replacements,
                ):
                    settings = settings.replace(original, replacement)
                target.write_text(settings)

            render("nginx.conf", root / "nginx.conf")
            render("proxy.conf", root / "proxy.conf", [("8765", str(api_port))])
            render("lan.conf", ingress / "lan.conf", [
                ("192.0.2.10", "127.0.0.1"), ("8780", str(lan_port)), ("192.0.2.0/24", "127.0.0.1/32"),
            ])
            render("tailscale.conf", ingress / "tailscale.conf", [("8781", str(tail_port))])
            lan_host = f"127.0.0.1:{lan_port}"
            tail_host = "replace-me.example.invalid"
            lan_origin = f"http://{lan_host}"
            tail_origin = f"https://{tail_host}"
            nginx = [os.environ["NGINX_PATH"], "-c", str(root / "nginx.conf")]
            subprocess.run([*nginx, "-t"], check=True, timeout=10, capture_output=True)
            # Use the same system Python and flags as the systemd template.
            with subprocess.Popen(
                ["/usr/bin/python3", "-EsB", "-m", "mountain_service", "serve",
                 "--db", str(root / "mountain.sqlite"), "--port", str(api_port),
                 "--allow-origin", lan_origin, "--allow-origin", tail_origin],
                stderr=subprocess.PIPE,
            ) as api, subprocess.Popen(nginx, stderr=subprocess.PIPE) as edge:
                try:
                    self.wait_for_health(api, api_port, f"127.0.0.1:{api_port}")
                    self.wait_for_health(edge, lan_port, lan_host)
                    self.wait_for_health(edge, tail_port, tail_host)
                    self.assertEqual(self.request("GET", lan_port, lan_host, path="/")[0], 200)
                    self.assertEqual(self.request("GET", lan_port, lan_host, source="127.0.0.2")[0], 403)
                    self.assertEqual(self.request("GET", lan_port, tail_host)[0], 403)
                    self.assertEqual(self.request("GET", tail_port, lan_host)[0], 403)
                    headers = [("X-Mountain-Refresh", "1")]
                    for port, host, origin in ((lan_port, lan_host, lan_origin),
                                               (tail_port, tail_host, tail_origin)):
                        with self.subTest(origin=origin):
                            ok_headers = [*headers, ("Origin", origin)]
                            # 409 shows the request reached the source-disabled collector.
                            status, response_headers, body = self.request("POST", port, host, ok_headers)
                            self.assertEqual(status, 409)
                            self.assertIn(b"no_enabled_sources", body)
                            self.assertNotIn("access-control-allow-origin", response_headers)
                            self.assertEqual(self.request("POST", port, host, headers)[0], 403)
                            self.assertEqual(self.request("POST", port, host, [("Origin", origin)])[0], 400)
                            for bad_origin in ("null", "https://outside.example", f"http://{tail_host}"):
                                self.assertEqual(self.request(
                                    "POST", port, host, [*headers, ("Origin", bad_origin)])[0], 403)
                            self.assertEqual(self.request("POST", port, host, [
                                *ok_headers, ("Origin", origin),
                            ])[0], 403)
                            self.assertEqual(self.request("POST", port, host, [
                                *ok_headers, ("Content-Length", "1"),
                            ], body=b"x")[0], 400)
                            self.assertEqual(self.request("POST", port, host, [
                                *ok_headers, ("Transfer-Encoding", "chunked"),
                            ], body=b"0\r\n\r\n")[0], 400)
                finally:
                    edge.terminate()
                    api.terminate()
                    edge.wait(timeout=10)
                    api.wait(timeout=10)

    def wait_for_health(self, process, port, host):
        for _ in range(60):
            if process.poll() is not None:
                self.fail(process.stderr.read().decode())
            try:
                if self.request("GET", port, host)[0] == 200:
                    return
            except ConnectionError:
                pass
            time.sleep(0.05)
        self.fail("Health check did not pass")

    @staticmethod
    def request(method, port, host, headers=(), *, body=None, path=None, source="127.0.0.1"):
        path = path or ("/healthz" if method == "GET" else "/v1/refresh")
        conn = http.client.HTTPConnection("127.0.0.1", port, source_address=(source, 0), timeout=2)
        try:
            conn.putrequest(method, path, skip_host=True)
            conn.putheader("Host", host)
            for name, value in headers:
                conn.putheader(name, value)
            conn.endheaders(body)
            response = conn.getresponse()
            return response.status, {name.lower() for name, _ in response.getheaders()}, response.read()
        finally:
            conn.close()

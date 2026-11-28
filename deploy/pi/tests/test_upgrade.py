"""Exercise the release transaction against real scratch Git trees and simulated services."""

import hashlib
import http.server
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from unittest.mock import patch

from deploy.pi import upgrade
from mountain_service import store


class SimulatedServices:
    def __init__(self, root, units):
        self.root = root
        self.config = units
        self.events = []
        self.release = self.root.resolve()
        self.unhealthy = set()
        self.failed_starts = set()
        self.interrupt = False
        self.fail_reset = False

    def units(self):
        return self.config.copy()

    def state(self, name):
        return self.config[name].active

    def stop(self, name):
        self.events.append(("stop", name))
        self.config[name] = replace(self.config[name], active="inactive")

    def start(self, name):
        self.events.append(("start", name))
        if name == upgrade.APP:
            if self.state(name) == "active":
                raise AssertionError("duplicate collector start")
            self.release = self.root.resolve()
            if self.interrupt:
                self.interrupt = False
                raise KeyboardInterrupt
        if (self.release, name) in self.failed_starts:
            self.config[name] = replace(self.config[name], active="failed")
            raise upgrade.UpgradeError("simulated start failure")
        self.config[name] = replace(self.config[name], active="active")

    def reset_failed(self, name):
        self.events.append(("reset", name))
        if self.fail_reset:
            raise upgrade.UpgradeError("simulated reset failure")
        if self.state(name) == "failed":
            self.config[name] = replace(self.config[name], active="inactive")

    def check_firewall(self, expected):
        if self.state(upgrade.FIREWALL) != expected:
            raise upgrade.UpgradeError("simulated firewall mismatch")

    def healthy(self, unit, origin, release=None):
        self.events.append(("probe", unit))
        if (self.release, unit) in self.unhealthy or self.state(unit) != "active":
            raise upgrade.UpgradeError("simulated health failure")
        if release is not None and release != self.release:
            raise AssertionError("backend serves the wrong release")
        expected = "http://127.0.0.1:8765" if unit == upgrade.APP else "http://192.168.17.2:8780"
        if origin != expected:
            raise AssertionError("wrong health origin")


@unittest.skipIf(os.geteuid() == 0, "run scratch integration tests as the unprivileged operator")
class UpgradeTests(unittest.TestCase):
    def setUp(self):
        private = tempfile.TemporaryDirectory()
        self.addCleanup(private.cleanup)
        self.work = Path(private.name)
        self.repo = self.directory("repo")
        self.git("init", "-q")
        self.git("config", "user.email", "release-test@example.test")
        self.git("config", "user.name", "Release Test")
        self.directory("repo/mountain_service")
        self.directory("repo/poc")
        (self.repo / "poc/__init__.py").write_text("")
        (self.repo / "index.html").write_text("synthetic baseline")
        self.initial = self.new_revision("0.3.4")
        self.candidate = self.new_revision("0.4.0")
        self.release_io = upgrade.GitRelease(self.repo)
        self.app = self.directory("opt")
        self.releases = self.directory("opt/releases")
        self.old_release = self.releases / f"v0.3.4-{self.initial[:12]}"
        self.new_release = self.releases / f"v0.4.0-{self.candidate[:12]}"
        self.release_io.stage(self.initial, "0.3.4", self.old_release)
        self.current = self.app / "current"
        self.original_link = f"releases/{self.old_release.name}"
        self.current.symlink_to(self.original_link)
        self.config = self.directory("etc")
        self.unit_dir = self.directory("units")
        self.lan = "http://192.168.17.2:8780"
        self.state_dir = self.directory("state", 0o700)
        self.db = self.state_dir / "mountain.sqlite"
        store.prepare(self.db)
        with store.connect(self.db, write=True) as db:
            store.charge_manual_weather(db, 122, 6)
        self.env = self.config / "service.env"
        self.env.write_text(f"MOUNTAIN_API_PORT=8765\nMOUNTAIN_DB={self.db}\n"
                            f'MOUNTAIN_EDGE_ARGS="--allow-origin {self.lan}"\n'
                            'MOUNTAIN_COLLECT_ARGS="--collect ifs --collect drivebc_whitewater"\n')
        self.env.chmod(0o600)
        for name in ("nginx.conf", "proxy.conf", "firewall.nft"):
            (self.config / name).write_text("synthetic " + name + "\n")
        (self.config / "firewall.nft").chmod(0o600)
        self.directory("etc/ingress")
        (self.config / "ingress/lan.conf").write_text("synthetic LAN policy")
        dropin_dir = self.directory(f"units/{upgrade.EDGE}.d")
        dropin = dropin_dir / "firewall.conf"
        dropin.write_text("synthetic dependency")
        self.baseline = {}
        for unit, enabled in zip(upgrade.UNITS, ("enabled", "enabled", "static")):
            fragment = self.unit_dir / unit
            fragment.write_text("synthetic " + unit)
            self.baseline[unit] = upgrade.Unit("active", enabled, str(fragment),
                                               (str(dropin),) if unit == upgrade.EDGE else ())
        self.services = SimulatedServices(self.current, self.baseline.copy())
        self.install = upgrade.Installation(self.app, self.config, self.unit_dir, self.services)
        self.private_backup = self.directory("backup", 0o700)
        self.archive = self.private_backup / "encrypted"
        self.archive.write_bytes(b"synthetic encrypted archive stand-in")
        self.archive.chmod(0o600)
        self.receipt = self.private_backup / "verified.json"
        self.restore = self.directory("restored", 0o700)
        identity = self.install.identity(self.initial, "0.3.4", self.old_release)
        identity["enablement"] = {name: unit.enabled for name, unit in self.baseline.items()}
        upgrade.write_json(self.restore / "release.json", identity)
        for name, installed in self.install.files(self.baseline).items():
            target = self.restore / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(installed, target)
        self.make_receipt()
        self.files_before = self.install.file_manifest(self.baseline)
        self.db_before = hashlib.sha256(self.db.read_bytes()).hexdigest()

    def directory(self, name, mode=0o755):
        path = self.work / name
        path.mkdir(mode=mode)
        path.chmod(mode)
        return path

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def new_revision(self, version):
        module = self.repo / "mountain_service/__main__.py"
        module.write_text(f"print({version!r})\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Release " + version)
        return self.git("rev-parse", "HEAD")

    def make_receipt(self):
        with self.install.lock():
            self.install.verify_backup(self.release_io, self.archive, self.restore, self.receipt)

    def perform(self, *, preflight=False, sha=None, version="0.4.0", lan="default"):
        with self.install.lock():
            self.install.upgrade(self.release_io, sha or self.candidate, version, self.archive,
                                 self.receipt, self.lan if lan == "default" else lan, preflight)

    def assert_preserved(self):
        self.assertEqual(self.install.file_manifest(self.baseline), self.files_before)
        self.assertEqual(self.services.units(), self.baseline)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), self.db_before)
        with store.connect(self.db) as handle:
            self.assertEqual(store.manual_weather_used(handle, 122), 1)
        self.assertNotIn(("stop", upgrade.FIREWALL), self.services.events)
        self.assertNotIn(("start", upgrade.FIREWALL), self.services.events)

    def assert_not_activated(self):
        self.assertEqual(os.readlink(self.current), self.original_link)
        self.assertFalse(self.install.metadata.exists())
        self.assertFalse(self.new_release.exists())
        self.assertFalse(any(event[0] in ("stop", "start") for event in self.services.events))

    def test_preflight_stages_without_mutating_services_or_release_pointer(self):
        self.perform(preflight=True)
        self.assert_not_activated()
        self.assert_preserved()

    def test_upgrade_preserves_state_boot_and_previous_release(self):
        self.perform()
        self.assertTrue(self.old_release.is_dir())
        self.assertEqual(self.current.resolve(), self.new_release)
        release = upgrade.read_json(self.install.metadata)
        self.assertEqual(release["commit"], self.candidate)
        self.assertEqual(release["version"], "0.4.0")
        self.assertEqual(release["previous_commit"], self.initial)
        self.assertEqual(release["previous_target"], str(self.old_release))
        actions = [event for event in self.services.events if event[0] in ("stop", "start")]
        self.assertEqual(actions, [("stop", upgrade.EDGE), ("stop", upgrade.APP),
                                   ("start", upgrade.APP), ("start", upgrade.EDGE)])
        self.assert_preserved()

    def test_bad_revision_wrong_version_and_unapproved_lan_fail_before_stop(self):
        for args in ({"sha": self.candidate[:12]}, {"sha": "f" * 40}, {"version": "0.4.1"},
                     {"lan": "http://192.168.17.3:8780"}, {"lan": None}):
            with self.subTest(args=args), self.assertRaises(upgrade.UpgradeError):
                self.perform(**args)
            self.assert_not_activated()

    def test_local_replace_ref_cannot_change_approved_content(self):
        replacement = self.new_revision("0.4.1")
        self.git("replace", self.candidate, replacement)
        self.perform()
        self.assertEqual((self.new_release / "mountain_service/__main__.py").read_text(), "print('0.4.0')\n")

    def test_local_archive_attributes_cannot_omit_reviewed_files(self):
        (self.repo / ".git/info/attributes").write_text("index.html export-ignore\n")
        with self.assertRaisesRegex(upgrade.UpgradeError, "omits files"):
            self.perform()
        self.assert_not_activated()

    def test_requires_exact_archived_configuration_and_unchanged_receipt(self):
        extra = self.restore / "runtime.sqlite"
        extra.write_bytes(b"excluded state")
        with self.assertRaisesRegex(upgrade.UpgradeError, "allowlist"):
            self.make_receipt()
        extra.unlink()
        (self.restore / "config/service.env").chmod(0o644)
        with self.assertRaisesRegex(upgrade.UpgradeError, "permissions"):
            self.make_receipt()
        self.archive.write_bytes(b"new encrypted backup")
        with self.assertRaisesRegex(upgrade.UpgradeError, "archive changed"):
            self.perform()
        self.assert_not_activated()

    def test_receipt_rejects_changed_config_boot_settings_and_release_content(self):
        original = self.env.read_bytes()
        self.env.write_bytes(original + b"# configuration changed\n")
        with self.assertRaisesRegex(upgrade.UpgradeError, "configuration changed"):
            self.perform()
        self.env.write_bytes(original)
        self.services.config[upgrade.EDGE] = replace(self.baseline[upgrade.EDGE], enabled="disabled")
        with self.assertRaisesRegex(upgrade.UpgradeError, "Boot enablement"):
            self.perform()
        self.services.config[upgrade.EDGE] = self.baseline[upgrade.EDGE]
        (self.old_release / "index.html").write_text("unexpected local edit")
        with self.assertRaisesRegex(upgrade.UpgradeError, "runtime files"):
            self.perform()
        self.assert_not_activated()

    def test_lan_probe_failure_restores_exact_link_and_allows_safe_retry(self):
        self.services.unhealthy.add((self.new_release, upgrade.EDGE))
        with self.assertRaisesRegex(upgrade.UpgradeError, "previous release was restored"):
            self.perform()
        self.assertEqual(os.readlink(self.current), self.original_link)
        self.assertFalse(self.install.metadata.exists())
        self.assert_preserved()
        self.services.unhealthy.clear()
        self.perform()
        self.assertEqual(self.current.resolve(), self.new_release)

    def test_failed_start_and_interrupt_roll_back_without_duplicate_start(self):
        self.services.failed_starts.add((self.new_release, upgrade.APP))
        with self.assertRaisesRegex(upgrade.UpgradeError, "previous release was restored"):
            self.perform()
        self.services.failed_starts.clear()
        self.services.interrupt = True
        with self.assertRaisesRegex(upgrade.UpgradeError, "previous release was restored"):
            self.perform()
        self.assertEqual(os.readlink(self.current), self.original_link)
        self.assert_preserved()

    def test_failure_to_restart_previous_release_reports_manual_recovery(self):
        self.services.unhealthy.add((self.new_release, upgrade.APP))
        self.services.fail_reset = True
        with self.assertRaisesRegex(upgrade.UpgradeError, "manual rollback"):
            self.perform()
        self.assertEqual(os.readlink(self.current), self.original_link)
        self.assertFalse(self.install.metadata.exists())

    def test_metadata_publication_failure_rolls_back(self):
        def fail_after_write(path, data):
            write_metadata(path, data)
            raise OSError("synthetic fsync error")

        write_metadata = upgrade.write_json
        with patch.object(upgrade, "write_json", side_effect=fail_after_write):
            with self.assertRaisesRegex(upgrade.UpgradeError, "previous release was restored"):
                self.perform()
        self.assertEqual(os.readlink(self.current), self.original_link)
        self.assertFalse(self.install.metadata.exists())
        self.assert_preserved()

    def test_malformed_verification_evidence_mid_activation_rolls_back(self):
        probe = self.services.healthy

        def corrupt_receipt(unit, origin, release=None):
            probe(unit, origin, release)
            if self.services.release == self.new_release:
                self.receipt.write_text("{")

        with patch.object(self.services, "healthy", side_effect=corrupt_receipt):
            with self.assertRaisesRegex(upgrade.UpgradeError, "previous release was restored"):
                self.perform()
        self.assertEqual(os.readlink(self.current), self.original_link)
        self.assertFalse(self.install.metadata.exists())
        self.assert_preserved()

    def test_disabled_edge_stays_stopped_and_lock_rejects_second_upgrade(self):
        self.baseline[upgrade.EDGE] = replace(self.baseline[upgrade.EDGE], active="inactive", enabled="disabled")
        self.services.config = self.baseline.copy()
        identity = upgrade.read_json(self.restore / "release.json")
        identity["enablement"][upgrade.EDGE] = "disabled"
        upgrade.write_json(self.restore / "release.json", identity)
        self.make_receipt()
        with self.install.lock(), self.assertRaisesRegex(upgrade.UpgradeError, "already|operation is running"):
            self.perform()
        self.perform(lan=None)
        self.assertNotIn(("start", upgrade.EDGE), self.services.events)
        self.assert_preserved()


class ProbeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("curl"), "curl required for loopback HTTP probe")
    def test_health_checks_require_200_and_expected_body_without_redirects(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            response = (200, b'{"status":"ok"}')

            def do_GET(self):
                status, body = self.response
                self.send_response(status)
                self.send_header("Location", "/followed")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                origin = f"http://127.0.0.1:{server.server_port}"
                self.assertTrue(upgrade.Services.http_ok(origin))
                for response in ((302, b'{"status":"ok"}'), (503, b'{"status":"ok"}'),
                                 (200, b'{"status":"wrong"}'), (200, b"x" * 200)):
                    Handler.response = response
                    self.assertFalse(upgrade.Services.http_ok(origin))
            finally:
                server.shutdown()
                worker.join()

    def test_health_retry_budget(self):
        services = upgrade.Services()
        with patch.object(services, "state", return_value="active"), patch.object(
                services, "http_ok", return_value=False) as probe, patch("time.sleep") as delay:
            with self.assertRaisesRegex(upgrade.UpgradeError, "retry budget"):
                services.healthy(upgrade.EDGE, "http://127.0.0.1:8765")
        self.assertEqual(probe.call_count, 10)
        self.assertEqual(delay.call_count, 9)

    def test_bad_cli_arguments_are_sanitized(self):
        marker = "synthetic-secret-marker"
        result = subprocess.run([sys.executable, "deploy/pi/upgrade.py", marker],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(marker, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()

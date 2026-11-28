#!/usr/bin/env python3
"""Upgrade the existing private Pi deployment to a reviewed, compatible release."""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit


APP = "whitewater-mountain.service"
EDGE = "whitewater-mountain-edge.service"
FIREWALL = "whitewater-mountain-firewall.service"
UNITS = (APP, EDGE, FIREWALL)
REPOSITORY = "https://github.com/taylorrussell-sudo/whitewater-mountain"
RUNTIME_PATHS = ("index.html", "mountain_service", "poc")
LAN_NETWORKS = tuple(map(ipaddress.IPv4Network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))
SHA = re.compile(r"[0-9a-f]{40}")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


class UpgradeError(Exception):
    """A fixed operator-facing error that contains no private values."""


def require(condition, message):
    if not condition:
        raise UpgradeError(message)


def digest(path, checksum=None):
    if checksum is None:
        checksum = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(128 * 1024), b""):
            checksum.update(block)
        return checksum.hexdigest()


def protected(path, *, directory=False, private=False):
    info = path.lstat()
    file_type = stat.S_ISDIR if directory else stat.S_ISREG
    forbidden = 0o077 if private else 0o022
    require(file_type(info.st_mode) and info.st_uid == os.geteuid()
            and not info.st_mode & forbidden, "A required path has unsafe ownership or permissions.")
    return path


def sync_directory(path):
    fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_private(path, data):
    with tempfile.TemporaryDirectory(prefix=".write-", dir=path.parent) as staging:
        staged = Path(staging) / path.name
        with staged.open("xb") as file:
            staged.chmod(0o600)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(staged, path)
        sync_directory(path.parent)


def write_json(path, data):
    write_private(path, (json.dumps(data, sort_keys=True, indent=2) + "\n").encode("utf-8"))


def read_json(path):
    return json.loads(protected(path, private=True).read_text(encoding="utf-8"))


def run(command, *, timeout, cwd=None, stdout=subprocess.PIPE, account=None):
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"}
    identity = {}
    if account is not None:
        env["HOME"] = account.pw_dir
        if os.geteuid() == 0:
            identity = {"user": account.pw_uid, "group": account.pw_gid, "extra_groups": ()}
        else:
            require(account.pw_uid == os.geteuid(), "The command account does not match the operator.")
    try:
        return subprocess.run(command, check=True, stdin=subprocess.DEVNULL, stdout=stdout,
                              stderr=subprocess.DEVNULL, timeout=timeout, cwd=cwd, env=env,
                              **identity).stdout
    except (OSError, subprocess.SubprocessError):
        raise UpgradeError("A required local command failed or timed out.") from None


class GitRelease:
    def __init__(self, checkout):
        self.checkout = checkout.resolve(strict=True)
        self.account = pwd.getpwuid(self.checkout.stat().st_uid)
        require(self.account.pw_uid != 0, "Use a trusted checkout owned by the unprivileged operator.")

    def git(self, *args, stdout=subprocess.PIPE):
        return run(["git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-C", str(self.checkout), *args],
                   timeout=60, stdout=stdout, account=self.account)

    def stage(self, sha, version, destination):
        require(SHA.fullmatch(sha), "Supply an explicitly approved full lowercase Git commit SHA.")
        require(VERSION.fullmatch(version), "Supply the reviewed application version.")
        resolved = self.git("rev-parse", "--verify", sha + "^{commit}")
        require(resolved.decode("ascii").strip() == sha, "The approved revision is unavailable.")
        tree = self.git("ls-tree", "-r", "-z", "--full-tree", sha, "--", *RUNTIME_PATHS)
        expected = {}
        for item in tree.rstrip(b"\0").split(b"\0"):
            fields, filename = item.split(b"\t", 1)
            mode, kind, oid = fields.split()
            require(mode in (b"100644", b"100755") and kind == b"blob",
                    "The reviewed runtime tree contains a non-regular file.")
            expected[os.fsdecode(filename)] = (mode, oid.decode("ascii"))
        destination.mkdir(mode=0o755)
        destination.chmod(0o755)
        with tempfile.TemporaryFile() as archive:
            self.git("archive", "--format=tar", sha, *RUNTIME_PATHS, stdout=archive)
            archive.seek(0)
            with tarfile.open(fileobj=archive, mode="r:") as package:
                for member in package:
                    name = Path(member.name)
                    require(not name.is_absolute() and ".." not in name.parts and name.parts
                            and name.parts[0] in RUNTIME_PATHS,
                            "The approved archive contains an unexpected path.")
                    target = destination / name
                    if member.isdir():
                        target.mkdir(mode=0o755)
                        target.chmod(0o755)
                    else:
                        require(member.isfile(), "The approved archive contains a non-regular file.")
                        mode, oid = expected.pop(name.as_posix(), (None, None))
                        with package.extractfile(member) as source, target.open("xb") as file:
                            shutil.copyfileobj(source, file)
                            file.flush()
                            os.fsync(file.fileno())
                        blob = hashlib.sha1(f"blob {member.size}\0".encode("ascii"))
                        require(oid == digest(target, blob), "The archive differs from the approved Git tree.")
                        target.chmod(0o755 if mode == b"100755" else 0o644)
        require(not expected, "The archive omits files from the approved Git tree.")
        output = run(["/usr/bin/python3", "-EsB", "-m", "mountain_service", "--version"],
                     timeout=15, cwd=destination, account=self.account)
        require(output.decode("ascii").strip() == version, "The archived CLI version did not match.")
        for path in reversed(sorted(destination.rglob("*"))):
            if path.is_dir():
                sync_directory(path)
        sync_directory(destination)


@dataclass(frozen=True)
class Unit:
    active: str
    enabled: str
    fragment: str
    dropins: tuple


class Services:
    def units(self):
        result = {}
        for name in UNITS:
            props = ("ActiveState", "UnitFileState", "FragmentPath", "DropInPaths")
            fields = dict(line.split("=", 1) for line in
                          self.show(name, *props).splitlines() if "=" in line)
            result[name] = Unit(fields["ActiveState"], fields["UnitFileState"],
                                fields["FragmentPath"], tuple(shlex.split(fields["DropInPaths"])))
        return result

    def show(self, name, *props):
        args = [f"--property={prop}" for prop in props]
        return run(["systemctl", "show", "--all", *args, name], timeout=10).decode()

    def state(self, name):
        return self.show(name, "ActiveState").strip().removeprefix("ActiveState=")

    def stop(self, name):
        run(["systemctl", "stop", name], timeout=65, stdout=subprocess.DEVNULL)
        require(self.state(name) == "inactive", "A Mountain service did not stop.")

    def start(self, name):
        run(["systemctl", "start", name], timeout=65, stdout=subprocess.DEVNULL)

    def reset_failed(self, name):
        run(["systemctl", "reset-failed", name], timeout=10, stdout=subprocess.DEVNULL)

    def check_firewall(self, expected):
        require(self.state(FIREWALL) == expected,
                "The Mountain firewall runtime state changed during the release operation.")
        if expected == "active":
            run(["nft", "list", "table", "inet", "whitewater_mountain"], timeout=10,
                stdout=subprocess.DEVNULL)

    def serving_release(self, release):
        pid = self.show(APP, "MainPID").strip().removeprefix("MainPID=")
        try:
            return pid.isdecimal() and int(pid) > 0 and (Path("/proc") / pid / "cwd").resolve(
                strict=True) == release
        except OSError:
            return False

    def healthy(self, unit, origin, release=None):
        for attempt in range(10):
            if (self.state(unit) == "active" and (release is None or self.serving_release(release))
                    and self.http_ok(origin)):
                return
            if attempt != 9:
                time.sleep(2)
        raise UpgradeError("A Mountain health check failed within its retry budget.")

    @staticmethod
    def http_ok(origin):
        try:
            result = run(["curl", "-q", "--noproxy", "*", "--silent", "--connect-timeout", "1",
                          "--max-time", "3", "--max-filesize", "128", "--write-out",
                          "\n%{http_code}", origin + "/healthz"], timeout=4)
            body, status = result.rsplit(b"\n", 1)
            return status == b"200" and json.loads(body) == {"status": "ok"}
        except (UpgradeError, ValueError):
            return False


def file_tree(root):
    protected(root, directory=True)
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            protected(path, directory=True)
        else:
            protected(path)
            files[path.relative_to(root).as_posix()] = digest(path)
    return files


class Installation:
    def __init__(self, app, config, unit_dir, services):
        self.root = protected(app, directory=True).resolve(strict=True)
        self.releases = protected(self.root / "releases", directory=True)
        self.config = protected(config, directory=True).resolve(strict=True)
        self.unit_dir = protected(unit_dir, directory=True).resolve(strict=True)
        self.current = self.root / "current"
        self.metadata = self.config / "release.json"
        self.services = services

    @contextmanager
    def lock(self):
        flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW
        lock = self.root / ".upgrade.lock"
        fd = os.open(lock, flags, 0o600)
        try:
            protected(lock, private=True)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UpgradeError("Another Mountain release operation is running.") from None
            yield
        finally:
            os.close(fd)

    def active_release(self):
        require(self.current.is_symlink(), "The active release pointer must be a symlink.")
        require(self.current.lstat().st_uid == os.geteuid(), "The active pointer must be operator-owned.")
        release = self.current.resolve(strict=True)
        require(release.parent == self.releases, "The active release must be in the release directory.")
        return protected(release, directory=True)

    def switch(self, target):
        with tempfile.TemporaryDirectory(prefix=".pointer-", dir=self.root) as staging:
            staged = Path(staging) / "current"
            staged.symlink_to(target)
            os.replace(staged, self.current)
            sync_directory(self.root)

    def files(self, units):
        installed = {"config/service.env": protected(self.config / "service.env", private=True)}
        if units[EDGE].fragment:
            for name in ("nginx.conf", "proxy.conf"):
                installed["config/" + name] = protected(self.config / name)
            ingress = self.config / "ingress"
            for name in file_tree(ingress):
                installed["config/ingress/" + name] = ingress / name
        if units[FIREWALL].fragment:
            installed["config/firewall.nft"] = protected(self.config / "firewall.nft", private=True)
        for name, unit in units.items():
            if unit.fragment:
                fragment = self.unit_dir / name
                require(Path(unit.fragment) == fragment, "A Mountain unit is outside the supported layout.")
                installed["units/" + name] = protected(fragment)
            for item in unit.dropins:
                path = Path(item)
                # Host-wide service defaults are outside the app backup.
                if path.parent.name == "service.d":
                    continue
                require(path.parent == self.unit_dir / (name + ".d"),
                        "A Mountain unit has a drop-in outside the supported layout.")
                protected(path.parent, directory=True)
                installed["units/" + path.relative_to(self.unit_dir).as_posix()] = protected(path)
        return installed

    def baseline(self, lan_origin=None):
        units = self.services.units()
        require(units[APP].active == "active" and units[APP].fragment,
                "The previously approved backend must be installed and active.")
        require(all(unit.active in ("active", "inactive") for unit in units.values()),
                "A Mountain unit is in an unexpected runtime state.")
        require(units[EDGE].active != "active" or units[EDGE].fragment,
                "The active edge must have an installed unit.")
        port, edge_args = self.settings()
        origin = None
        if units[EDGE].active == "active":
            origin = check_lan_origin(lan_origin, edge_args)
        return units, f"http://127.0.0.1:{port}", origin

    def settings(self):
        content = protected(self.config / "service.env", private=True).read_text(encoding="utf-8")
        values = {}
        for line in content.splitlines():
            key, sep, val = line.strip().partition("=")
            if sep and key in ("MOUNTAIN_API_PORT", "MOUNTAIN_EDGE_ARGS"):
                parts = shlex.split(val)
                values[key] = " ".join(parts)
        port = values.get("MOUNTAIN_API_PORT", "")
        require(re.fullmatch("[1-9][0-9]{0,4}", port) and int(port) <= 65535,
                "The existing backend port could not be read.")
        return port, shlex.split(values.get("MOUNTAIN_EDGE_ARGS", ""))

    def identity(self, sha, version, release):
        require(isinstance(sha, str) and SHA.fullmatch(sha)
                and isinstance(version, str) and VERSION.fullmatch(version),
                "The release identity must include a full Git SHA and an application version.")
        return {"repository": REPOSITORY, "commit": sha, "version": version, "target": str(release)}

    def verify_backup(self, git, archive, restored, receipt):
        units = self.services.units()
        active = self.active_release()
        recovered = read_json(protected(restored, directory=True, private=True) / "release.json")
        identity = self.identity(recovered.get("commit"), recovered.get("version"), active)
        require(all(recovered.get(key) == value for key, value in identity.items()),
                "The restored release identity does not match the active pointer.")
        enabled = {name: unit.enabled for name, unit in units.items() if unit.fragment}
        require(recovered.get("enablement") == enabled,
                "The restored boot settings do not match the installed units.")
        if self.metadata.exists() or self.metadata.is_symlink():
            require(read_json(self.metadata) == recovered, "Installed and restored release metadata differ.")
        self.verify_release(git, identity, active)
        files = self.file_manifest(units)
        require(set(file_tree(restored)) == {*files, "release.json"},
                "The private restore does not match the configuration backup allowlist.")
        for name, expected in files.items():
            # The restore directory is private. Reject symbolic links at every level.
            path = restored / name
            for parent in path.parents:
                if parent == restored:
                    break
                protected(parent, directory=True)
            protected(path)
            require(digest(path) == expected["sha256"]
                    and stat.S_IMODE(path.stat().st_mode) == expected["mode"],
                    "A restored configuration file or its permissions differs.")
        self.check_backup_paths(archive, receipt)
        write_json(receipt, {"archive_sha256": digest(archive), "files": files,
                             "release": identity, "enablement": enabled,
                             "metadata_sha256": digest(self.metadata) if self.metadata.exists() else None})

    def check_backup_paths(self, archive, receipt):
        require(archive.is_absolute() and receipt.is_absolute() and archive.resolve() != receipt.resolve(),
                "Use separate absolute paths for the archive and receipt.")
        for path in (archive, receipt):
            require(not path.resolve().is_relative_to(self.root)
                    and not path.resolve().is_relative_to(self.config)
                    and not path.resolve().is_relative_to(self.unit_dir),
                    "Keep the backup and receipt outside installed app, configuration and unit directories.")
            protected(path.parent, directory=True, private=True)
        require(protected(archive, private=True).stat().st_size > 0, "The encrypted archive is empty.")
        if receipt.exists() or receipt.is_symlink():
            protected(receipt, private=True)

    def file_manifest(self, units):
        return {name: {"sha256": digest(path), "mode": stat.S_IMODE(path.stat().st_mode)}
                for name, path in self.files(units).items()}

    def verify_release(self, git, identity, release):
        with tempfile.TemporaryDirectory(prefix=".verify-", dir=self.releases) as scratch:
            Path(scratch).chmod(0o755)
            staged = Path(scratch) / "candidate"
            git.stage(identity["commit"], identity["version"], staged)
            require(file_tree(staged) == file_tree(release),
                    "The current runtime files do not match the restored reviewed commit.")

    def validate_receipt(self, archive, receipt, units, active):
        self.check_backup_paths(archive, receipt)
        evidence = read_json(receipt)
        identity = evidence["release"]
        require(identity == self.identity(identity["commit"], identity["version"], active),
                "The backup receipt is for another active release.")
        require(evidence["archive_sha256"] == digest(archive), "The verified encrypted archive changed.")
        enabled = {name: unit.enabled for name, unit in units.items() if unit.fragment}
        require(evidence["enablement"] == enabled, "Boot enablement changed since the backup drill.")
        require(evidence["files"] == self.file_manifest(units),
                "Installed configuration changed since the backup drill.")
        metadata = None
        if self.metadata.exists() or self.metadata.is_symlink():
            metadata = digest(protected(self.metadata, private=True))
        require(evidence["metadata_sha256"] == metadata,
                "Installed release metadata no longer matches the backup drill.")
        return identity

    def verify_baseline(self, units):
        require(self.services.units() == units,
                "Mountain runtime state or boot enablement differs from the preflight baseline.")

    def start_release(self, release, backend, lan, units):
        self.services.start(APP)
        self.services.healthy(APP, backend, release)
        if lan:
            self.services.check_firewall(units[FIREWALL].active)
            self.services.start(EDGE)
            self.services.healthy(EDGE, lan)

    def rollback(self, old_target, old_release, units, backend, lan):
        if units[EDGE].fragment and self.services.state(EDGE) not in ("inactive", "failed"):
            self.services.stop(EDGE)
        if self.services.state(APP) not in ("inactive", "failed"):
            self.services.stop(APP)
        self.switch(old_target)
        self.services.reset_failed(APP)
        if lan:
            self.services.reset_failed(EDGE)
        self.services.check_firewall(units[FIREWALL].active)
        self.start_release(old_release, backend, lan, units)
        self.verify_baseline(units)

    def upgrade(self, git, sha, version, archive, receipt, lan_origin, preflight):
        units, backend, lan = self.baseline(lan_origin)
        old_target = os.readlink(self.current)
        old_release = self.active_release()
        previous = self.validate_receipt(archive, receipt, units, old_release)
        require(sha != previous["commit"], "The approved revision is already active.")
        self.verify_release(git, previous, old_release)
        identity = self.identity(sha, version, self.releases / f"v{version}-{sha[:12]}")
        candidate = Path(identity["target"])
        with tempfile.TemporaryDirectory(prefix=".stage-", dir=self.releases) as scratch:
            Path(scratch).chmod(0o755)
            staged = Path(scratch) / "candidate"
            git.stage(sha, version, staged)
            if candidate.exists() or candidate.is_symlink():
                require(file_tree(candidate) == file_tree(staged),
                        "An existing staged release differs from the approved revision.")
            self.services.healthy(APP, backend, old_release)
            if lan:
                self.services.healthy(EDGE, lan)
            self.services.check_firewall(units[FIREWALL].active)
            self.verify_baseline(units)
            self.validate_receipt(archive, receipt, units, old_release)
            require(os.readlink(self.current) == old_target, "The active release pointer changed during staging.")
            if preflight:
                return
            if not candidate.exists():
                staged.rename(candidate)
                sync_directory(self.releases)
        details = {**identity, "previous_commit": previous["commit"],
                   "previous_target": str(old_release),
                   "enablement": {name: unit.enabled for name, unit in units.items() if unit.fragment}}
        prior_metadata = self.metadata.read_bytes() if self.metadata.exists() else None
        publishing = False
        try:
            if lan:
                self.services.stop(EDGE)
            self.services.stop(APP)
            self.services.check_firewall(units[FIREWALL].active)
            self.switch(candidate)
            self.start_release(candidate, backend, lan, units)
            self.verify_baseline(units)
            self.validate_receipt(archive, receipt, units, old_release)
            publishing = True
            write_json(self.metadata, details)
        except (Exception, KeyboardInterrupt):
            try:
                try:
                    self.rollback(old_target, old_release, units, backend, lan)
                finally:
                    if publishing and os.readlink(self.current) == old_target:
                        if prior_metadata is None:
                            self.metadata.unlink(missing_ok=True)
                            sync_directory(self.config)
                        else:
                            write_private(self.metadata, prior_metadata)
            except (Exception, KeyboardInterrupt):
                raise UpgradeError("Activation and automatic rollback failed. Follow the manual rollback runbook.") from None
            raise UpgradeError("Activation failed. The previous release was restored and passed health checks.") from None


def check_lan_origin(origin, edge_args):
    try:
        parsed = urlsplit(origin or "")
        host = ipaddress.IPv4Address(parsed.hostname)
        expected = "http://" + str(host)
        if parsed.port is not None and parsed.port != 80:
            require(parsed.port > 0, "The LAN port is invalid.")
            expected += ":" + str(parsed.port)
        allowed = [value for flag, value in zip(edge_args, edge_args[1:]) if flag == "--allow-origin"]
        require(origin == expected and origin in allowed and any(host in net for net in LAN_NETWORKS),
                "Supply the installed, approved private IPv4 LAN origin for the active edge.")
        return origin
    except (TypeError, ValueError):
        raise UpgradeError("Supply the installed, approved private IPv4 LAN origin for the active edge.") from None


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid arguments. Use --help for the supported options.\n")


def main():
    parser = QuietParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="trusted operator-owned Git checkout")
    parser.add_argument("--app-root", type=Path, default=Path("/opt/whitewater-mountain"))
    parser.add_argument("--config-dir", type=Path, default=Path("/etc/whitewater-mountain"))
    parser.add_argument("--unit-dir", type=Path, default=Path("/etc/systemd/system"))
    parser.add_argument("--archive", type=Path, required=True, help="existing encrypted configuration backup")
    parser.add_argument("--receipt", type=Path, required=True, help="private backup verification receipt")
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("verify-backup", help="record a completed private decrypt-and-restore drill")
    record.add_argument("--restored", type=Path, required=True, help="private scratch restore directory")
    upgrade = commands.add_parser("upgrade", help="preflight or install the reviewed release")
    upgrade.add_argument("--sha", required=True, help="approved full Git commit SHA")
    upgrade.add_argument("--version", required=True, help="reviewed application version")
    upgrade.add_argument("--lan-origin", help="approved existing LAN origin, required when edge is active")
    upgrade.add_argument("--preflight", action="store_true", help="stage in scratch and check without activation")
    args = parser.parse_args()

    def interrupted(signum, frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        require(os.geteuid() == 0, "Run the reviewed utility with operator-authorized root access.")
        os.umask(0o077)
        install = Installation(args.app_root, args.config_dir, args.unit_dir, Services())
        git = GitRelease(args.repo)
        with install.lock():
            if args.command == "verify-backup":
                install.verify_backup(git, args.archive, args.restored, args.receipt)
                print("Backup verification receipt recorded.")
            else:
                install.upgrade(git, args.sha, args.version, args.archive, args.receipt,
                                args.lan_origin, args.preflight)
                print("Release preflight passed." if args.preflight else "Reviewed release activated and verified.")
    except UpgradeError as exc:
        print(exc, file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print("Release operation stopped before completion. Check the private runbook and local state.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

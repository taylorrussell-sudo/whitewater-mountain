# v0.3.3 private Raspberry Pi deployment package

## Completion timestamp and objective

Completed at `2026-11-26T19:04:06-07:00` (America/Vancouver). Prepare a reversible private Raspberry Pi 5 installation for review.

## Repository, version and status

Repository `taylorrussell-sudo/whitewater-mountain`, branch `feature/v0.3.3-private-pi`, based on main at `a8689bbe4285d7a1749da25027325cc2c35db6f4`. Package commit `73221d254b4b9c1ee1bfe24902a967ebb40c274f`. v0.3.3 is proposed and submitted for review. The existing standalone simulation and public Pages preview remain in place. Neither GitHub Pages nor the production Pi was changed. [Pull request #13](https://github.com/taylorrussell-sudo/whitewater-mountain/pull/13)

## Changes and decisions

- Added a preflight and a staged runbook, dedicated systemd units, IPv4 LAN and optional Tailscale Serve ingress examples, and a source-disabled environment file. Releases are pinned to reviewed commits and switched by an atomic symlink. The Python service stays on loopback. The separate Nginx instance limits access to the approved LAN subnet, preserves Host and Origin for refresh validation, and uses a second loopback listener for optional auth-gated HTTPS via Serve. The app ignores forwarded identities and applies its existing cooldowns and budget. [Pi runbook](../deploy/pi/README.md)
- Added CLI version reporting, exact private proxy origins and fixed service error messages. Kept browser assets and simulation intact. Updated the requirements, source activation notes, backlog, changelog and service guide.

## Development verification

- Passed 25 service tests including real Nginx 1.26.3 with rendered LAN and Tailscale edge templates over loopback, 16 proof-of-concept tests and 17 Chromium regressions. The x86-64 development host ran Debian 13, Python 3.12.14, system Python 3.13.5 for packaged startup, and Chromium 156.0.8078.79. Nginx was extracted from a signed Debian package into scratch storage. The tests covered mismatched and duplicate origins, disallowed LAN clients, malformed refresh requests, scheduled state, SQLite WAL backup/restore, and wall/mobile layouts. No live source requests ran for this task.
- Archived the baseline and proposed release, switched the active symlink, verified local health and disabled sources, and rolled back against the same test database. The CLI version, JavaScript syntax, shell snippet syntax and Git whitespace checks passed.
- Full system-mode unit verification was blocked by the development sandbox’s read-only system runtime and the container has no running systemd manager. Both units passed a user-mode syntax check on temporary copies with the test Nginx path and the system-only dynamic-user directive omitted. Run full system-mode verification and boot acceptance on the Pi.

## Limitations, backup and rollback

Actual paths, account, mounts, ports, LAN and tailnet rules, backup coverage and source retention are preflight decisions. No production access, services, wall configuration, backup settings or Funnel rules were changed. Source collection defaults to off. Whitewater terms applicability and time conventions for factual measurements remain unresolved under the documented owner decision. Whitewater imagery remains link-only. [Source status](../DATA_SOURCES.md)

The proposed limits need Pi measurements, including Chromium and Calendar, Home Assistant and Music Assistant. SQLite recovery uses checked standalone snapshots and a new destination. Snapshots can extend the effective retention of cached data and restore older provider limits or stops. Verify actual recovery and retention privately before enabling sources. For package rollback, close the PR before merge or revert it through review after merge. For installation rollback, use the prior release and compatible state or a checked pre-update restore. [Recovery and rollback](../deploy/pi/README.md#6-backup-and-restore)

## Next work and approvals

Review the PR. Separately approve and run the physical preflight and gates before declaring private operation verified. Approvals for production installation, access or backup changes, and eventual Pages retirement are separate. [Acceptance gates](../deploy/pi/README.md#8-acceptance-gates)

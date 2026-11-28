# v0.3.4 deployment reliability and documentation

## Completion timestamp and objective

Completed at `2026-11-27T19:39:46-07:00` (America/Vancouver). Prepare a deployment reliability and documentation release from the merged v0.3.3 Pi package.

## Repository, version and status

Repository `taylorrussell-sudo/whitewater-mountain`, branch `release/v0.3.4-deployment-reliability`. Base commit `f88c9af3243eda2e4927142440a5b61de4be7e18`. Package commit `c314e101aaaa3a3246fc91a7bbf94f2dd61cde56`. v0.3.4 is committed and open for review. Merge, publishing and Pi deployment remain pending. The owner reported that the existing production installation passed network security, refresh endpoint validation, automatic startup, reboot recovery and encrypted configuration backup verification. [Pull request #14](https://github.com/taylorrussell-sudo/whitewater-mountain/pull/14)

## Changes and design decisions

- Increased `mountain_connections` to 1 MiB for the Pi 5 ARM64 16 KiB page-size case. Added a regression that catches a return to 64 KiB even on a development host where Nginx would accept it.
- Added an optional IPv4 LAN allow rule keyed to interface, source subnet, listening address and dedicated TCP port. The dedicated `inet` table rejects other input to that port, including IPv6 and loopback, and leaves unrelated traffic to the host rules. The backend and optional Serve listener keep distinct loopback ports. The firewall is a static oneshot with `RemainAfterExit=yes`. The edge orders itself after it and binds to its unit state when the drop-in is installed.
- Documented DHCP reservation, bounded readiness, private ingress, reboot acceptance, release rollback and the encrypted configuration backup. Its allowlist covers release identity, deployed app configuration and app units and drop-ins. Runtime data and reproducible release content are excluded. The existing SQLite procedure remains available for a separately approved drill.
- Bumped the CLI version. All seven integrations, source policies, scheduler limits, API responses and dashboard behavior carry forward from v0.3.3. The version change also updates the existing User-Agent version string. [Pi runbook](../deploy/pi/README.md)

## Development verification

- On Debian 13 x86-64 with 4 KiB pages, passed 27 service tests, including the zone-size and systemd wiring regressions and real Nginx 1.26.3 on loopback. Passed 16 proof-of-concept tests and 17 Chromium tests. Browser and provider cases used synthetic fixtures.
- Confirmed the zone regression fails with a scratch copy set to `64k`. Validated the five runbook shell snippets with `sh -n`. Exercised the documented readiness probe with mocked transport failure, 503, 302 and 200 responses and confirmed it stops after ten failed attempts.
- Staged the v0.3.3 and v0.3.4 package archives, switched the release symlink forward and back, and confirmed CLI version, loopback health, dashboard and disabled collection against the same scratch database after each switch. The first scratch probe had an incorrect camera response key and treated the normal startup log as an error. The corrected probe passed all three starts and checked graceful exit.
- The nftables 1.1.3 parser reached end of input successfully. Kernel validation failed because the sandbox denied netlink access and disallowed an isolated network namespace. Full system-mode unit verification was blocked by read-only `/run/systemd`. User-mode `systemd-analyze verify` passed for temporary copies with development binary paths and the system-only `DynamicUser` directive omitted.

## Remaining verification and privacy

After approval, run the Pi gates for Nginx on the 16 KiB kernel, full system-mode verification, firewall start failure and stop ordering, allowed and rejected clients, boot without manual intervention, rollback and restoration from the encrypted configuration archive. Confirm the existing firewall manager preserves the Mountain table. A ruleset change outside systemd can remove that table while the oneshot still reports active. Use the existing verified host firewall if it cannot preserve the app table. Backup keys and operational evidence stay private. No production system, firewall, backup settings or live source endpoint was accessed for this release. The optional firewall template uses the operating system's nftables support. [Acceptance gates](../deploy/pi/README.md#8-acceptance-gates)

## Rollback and approvals

Close the pull request before merge or revert it through review after merge. On an approved installation, restore the prior reviewed release and compatible configuration, preserve the state directory, and repeat the loopback and ingress gates. Stop the edge before removing Mountain-specific rules or unit files. Review the pull request first. Production rollout, any backup changes, and Pages retirement require separate approval. [Rollback procedure](../deploy/pi/README.md#7-update-roll-back-or-remove)

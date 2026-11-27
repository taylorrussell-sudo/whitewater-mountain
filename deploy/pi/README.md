# v0.3.3 private Raspberry Pi installation

Proposed for review. The target is a Raspberry Pi 5 with 4 GB RAM, NVMe, Raspberry Pi OS (Debian 13, ARM64), and a 1920 × 1080 Chromium touchscreen. Follow the stages below only after the owner approves a maintenance window and production installation. The package is the reviewed Git revision, the standard-library Python service and the templates in this directory.

The Python service binds to IPv4 loopback. An optional dedicated, unprivileged Nginx instance provides trusted household LAN access. It can also receive traffic on a second loopback port from authenticated Tailscale Serve. There is no public ingress. The wall browser can use the direct loopback URL on the Pi. Keep the standalone simulation and existing simulated GitHub Pages preview until private operation is verified and the owner separately approves Pages retirement.

## 1. Preflight for the Pi

Record actual paths, ports, firewall rules, access decisions, service baselines, and backup details in the private operations handoff.

- [ ] Confirm Debian 13 ARM64 (`uname -m` should show `aarch64`), Python 3.10+ with `sqlite3`, systemd with cgroup v2, a working clock, DNS and upstream HTTPS. Check the installed Chromium build, actual 1920 × 1080 display and touch input. Verify the NVMe mount for application and state with `findmnt -T`. Check space and inodes with `df -h` and `df -i`.
- [ ] Inventory Calendar, Home Assistant, Music Assistant, the existing wall launcher, proxies and listeners, including IPv6 and containers. Check actual service names and health indicators and capture a baseline before the window. Use `ss -ltnp` and read the current firewall, route and ingress configuration. Verify every proposed port, unit name, account, path and current symlink is available or belongs to this app. Avoid global proxy, DNS, wall launcher and network changes.
- [ ] Choose a stable LAN IPv4 address on the intended interface, a dedicated unprivileged LAN port and an approved household source CIDR. Verify firewall filtering on the intended interface and source subnet. Check guest Wi-Fi, VLAN routing, IPv6, router port forwards and UPnP, reverse tunnels and any public proxies or Funnel rules. Binding to a LAN IP alone does not restrict routed traffic. Leave LAN ingress disabled until isolation is verified.
- [ ] If adding the edge, verify the path to a supported Nginx binary and modules. Use an available binary where possible. If absent, arrange approved provisioning that avoids starting any distro default listener or touching existing proxy configuration. The sample runs its own process, runtime directory and config. For optional Tailscale, also verify the installed CLI, current Serve and Funnel mappings, allowed identities and devices, access grants or ACLs, DNS/TLS and an unused Serve endpoint. A broadly accessible existing tailnet policy is insufficient. Leave Serve off if it would collide or require modifying an existing service.
- [ ] Verify existing backup scope and exclusions, encryption, target capacity, retention and last known good restore. Identify approved snapshot staging and a separate restore drill location. Agree on a combined app/state/backup space budget or an existing dedicated quota. Production backup configuration changes require their own approval.
- [ ] Record which sources the owner authorizes to run continuously and read the current terms, retention and rate limits. Verify the site can be tested with no sources enabled first. [Source decisions](../../DATA_SOURCES.md)

## 2. Install the release and start locally

All values below are examples. Substitute the verified account, paths and ports everywhere, including the unit, environment and proxy files. Keep absolute data and configuration paths outside all release trees. Use paths without spaces in these templates.

| Purpose | Example | Ownership and mode |
| --- | --- | --- |
| Immutable source releases | `/opt/whitewater-mountain/releases/v0.3.3-<short-sha>` | root-owned, service-readable, release directories 0755 |
| Active release link | `/opt/whitewater-mountain/current` | root-managed |
| Persistent SQLite and lock files | `/var/lib/whitewater-mountain` | dedicated service UID/GID, directory 0700 |
| Service settings | `/etc/whitewater-mountain/service.env` | root-owned 0600, read by systemd |
| Edge configuration | `/etc/whitewater-mountain/nginx.conf` and `ingress/` | root-owned, read-only to dynamic proxy user, directory 0755 and files 0644 |
| Snapshot staging and restore drill | verified separate directories | private 0700 and database files 0600, app maintenance user access as needed |

Create a dedicated system user and group with no login or home, after verifying the name is unused. With the merged, reviewed commit available in a trusted checkout, confirm its full SHA, version and provenance. Stage the small runtime tree with the operator account first. This example assumes a fresh install and an unused release path.

```sh
# Set APPROVED_SHA to the reviewed full SHA before running.
set -eu
app=/opt/whitewater-mountain
conf=/etc/whitewater-mountain
state=/var/lib/whitewater-mountain
account=whitewater-mountain
sha=$(git rev-parse --verify "${APPROVED_SHA:?set reviewed SHA}^{commit}")
short_sha=$(git rev-parse --short=12 "$sha")
release="$app/releases/v0.3.3-$short_sha"
staging=$(mktemp -d)
git archive --output="$staging/release.tar" "$sha" index.html mountain_service poc
mkdir "$staging/code"
tar -xf "$staging/release.tar" -C "$staging/code"
(cd "$staging/code" && /usr/bin/python3 -EsB -m mountain_service --version)
# Check it prints 0.3.3 before copying or switching.
```

```sh
# Skip account creation only if the existing account is verified as this app's identity.
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$account"
sudo install -d -m 0755 "$app" "$app/releases" "$conf"
sudo install -d -o "$account" -g "$account" -m 0700 "$state"
sudo mkdir -m 0755 "$release"
sudo cp -R "$staging/code/." "$release/"
sudo chmod -R a+rX,go-w "$release"
# Use this two-step switch for installation, upgrade and rollback.
sudo ln -sT "$release" "$app/.current-next"
sudo mv -Tf "$app/.current-next" "$app/current"
```

Copy [service.env.example](service.env.example) as the private mode-0600 `service.env`. Keep both argument lists empty. Review [whitewater-mountain.service](whitewater-mountain.service), then install the rendered copy at the verified system unit location with mode 0644. Use `systemd-analyze verify` before installing. Run `sudo systemctl daemon-reload` and `sudo systemctl start whitewater-mountain.service`. Use the verified loopback URL for the local gate below. Enable boot startup with `sudo systemctl enable whitewater-mountain.service` after the gate passes.

## 3. Add private access in stages

Use [whitewater-mountain-edge.service](whitewater-mountain-edge.service), [nginx.conf.example](nginx.conf.example) and [proxy.conf.example](proxy.conf.example) when ingress is needed. Place the rendered shared proxy snippet at the configured `proxy.conf` path, with the actual Python port. The `ingress/` directory should contain only approved rendered site files. Check all included paths. Nginx limits concurrent requests, disables access logs, and preserves Host and Origin; the Python service matches them against the explicit browser origin. The refresh POST requires that exact Origin, the custom header, an empty body and no transfer encoding. Scheduler cooldowns and source limits still apply. Same-origin checks protect browser requests from cross-site initiation. Network policy controls which clients can access the app. Local Pi processes can reach the loopback port.

**LAN.** Render [lan.conf.example](lan.conf.example) with the actual IPv4 address, port and allowed CIDR. Configure the verified host firewall to allow that port only on the household interface and from the approved subnet. Never use a wildcard listener, outside forwarding or guest access. Set `MOUNTAIN_EDGE_ARGS="--allow-origin http://192.0.2.10:8780"` using the actual canonical LAN URL. This HTTP example is for the trusted household LAN. Traffic there is unencrypted and authorized by network membership. Use the same URL in Chromium; aliases require an intentionally reviewed ingress and origin. Restart only the app to load its environment. Verify the edge unit and render its config before starting it. The unit runs `nginx -t` as its own dynamic user before startup. Enable the edge at boot after the LAN gate passes.

**Optional Tailscale.** Render [tailscale.conf.example](tailscale.conf.example) into `ingress/` only after the private access gate is approved. Use the actual tailnet HTTPS host and a different, unused loopback edge port. Append `--allow-origin https://<verified-tailnet-host>` inside the existing `MOUNTAIN_EDGE_ARGS` quotes and restart only the two app units. Use the origin alone, with no trailing slash and no default port. Confirm the installed Serve preserves the HTTPS request Host and Origin. Verify tailnet grants restrict the selected HTTPS endpoint to approved users or devices. With a free, approved default HTTPS endpoint and a compatible CLI, the example is `sudo tailscale serve --bg http://127.0.0.1:8781`. Check `tailscale serve --help`, `tailscale serve status` and `tailscale funnel status` against the private baseline before and after. Use Serve at the root so dashboard routes remain same-origin. Use an explicitly approved alternate HTTPS port if necessary and include it in the Host and origin. Never enable Funnel, reset shared Serve state, or change another route. Record the exact route-specific off command before enabling Serve. For the exact default-port example it is `sudo tailscale serve --https=443 off`, only when this app is the sole owner of that HTTPS listener. [Tailscale Serve CLI](https://tailscale.com/kb/1242/tailscale-serve)

## 4. Activate collection explicitly

After private ingress and recovery gates, add only approved keys in the service environment, as repeated `--collect SOURCE` arguments inside `MOUNTAIN_COLLECT_ARGS="..."`. Restart the Python service and verify provider states. For example, `MOUNTAIN_COLLECT_ARGS="--collect ifs --collect nelson_cs"` enables only the IFS forecast and Nelson observation. Other eligible keys are `hrdps`, `freezing_profile`, `drivebc_whitewater`, and, under the documented owner decision about factual measurements, `whitewater` and `whitewater_weather`. Review the latter two separately; their terms applicability and timestamps have open questions. Whitewater gallery and camera stills remain official links. Southridge, regional snow, and avalanche feeds have no collection flags. Remove the relevant flags and restart to disable sources. Existing cache material expires under its retention rules. [Cadences and backoff](../../mountain_service/README.md)

## 5. Monitor health, disk and diagnostics

- Check `systemctl is-active whitewater-mountain.service` and `curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8765/healthz` with the actual port. Use the existing approved local monitor if available, for example every minute with an alert after three failures. Boot and crash recovery are owned by systemd. A persistent 503 warrants investigation. The health check does not establish weather freshness. The dashboard shows source availability, backoff and stale states separately.
- Check `systemctl show whitewater-mountain.service -p MemoryCurrent -p CPUUsageNSec -p TasksCurrent -p NRestarts`, and the same for the edge. Sample aggregate use including Chromium and compare the existing services under normal wall and family-device load. The app's proposed cgroup settings are 96 MiB memory pressure, 160 MiB hard cap, 32 tasks and 50% of one CPU. The edge's proposed settings are 24 MiB, 48 MiB, eight tasks and 25% of one CPU. These caps exclude Chromium. Tune only after Pi measurements.
- The app unit caps individual files at 32 MiB, including separate SQLite and WAL files. The edge runs in a private runtime directory with bounded requests and 1 MiB per-file limits. Neither per-file cap is a directory quota. Size the verified filesystem or an approved per-app quota for DB, WAL, SHM, releases, backup staging and restore headroom. Start with a 256 MiB app and local snapshot planning budget, retention of current and one known-good release, and at most two local snapshots within the approved time window. Monitor both bytes and inodes and alert before limits are reached. Unexpected WAL growth, file-limit errors or filesystem pressure are reasons to pause collection and investigate. Preserve the database and its sidecars together. The app prunes logical rows; allocated SQLite pages can remain for reuse.
- Review app-unit logs locally with `sudo journalctl -u whitewater-mountain.service -n 30 --no-pager`. Source errors use fixed codes, and request access logging is off. The unit limits log bursts, while the existing journal policy controls aggregate retention. Share only version, stage, HTTP status, source state/error codes and rounded resource totals. Keep raw logs, unit status output, client identities, URLs, paths, addresses, headers, weather records and screenshots private.

## 6. Backup and restore

Use the active release's CLI as the dedicated service account with an approved private destination accessible to it. Keep an encrypted off-device copy only under the separately approved backup policy. Include the release SHA, templates as installed and source opt-ins in the private recovery record. Backup staging and target paths must have sufficient free space, be outside the release, and be fresh names in pre-created owner-only directories.

```sh
cd /opt/whitewater-mountain/current
sudo -u whitewater-mountain /usr/bin/python3 -EsB -m mountain_service backup "$LIVE_DB" "$NEW_SNAPSHOT"
sudo -u whitewater-mountain /usr/bin/python3 -EsB -m mountain_service restore "$NEW_SNAPSHOT" "$NEW_RESTORE_DB"
```

The online SQLite backup includes committed WAL pages, checks the application schema, integrity and foreign keys, and produces a standalone 0600 database. Use this command even when the service is stopped. Do not substitute a copy of the live main database file. Never delete active WAL, SHM or journal files. Restore refuses overwrite and orphaned destination sidecars. Test the restored database on an unused loopback port **without `--collect`**, as the service account, and with no ingress. Check the restore health, expected schema and provider/budget state privately. Stop the drill process before promoting its data. To cut over, stop the edge and app, keep the old DB in place, select the restored DB path in `service.env` under the approved writable state directory, clear collection flags, and start and verify locally before re-enabling access. Check restored backoff, provider stops and daily refresh budget against newer operational history before re-enabling collection. A stale snapshot can roll them back.

Follow the source windows for stored data and backups. The live cache keeps forecast/derived snapshots for up to seven days subject to the current-snapshot rule, recent Nelson readings for 48 hours, and only the latest snapshot per Whitewater product. DriveBC imagery is in memory. A full snapshot can contain records that age out of the running DB before the snapshot expires. Verify that the backup policy permits this extended exposure or keep this cache out of retained backups and recover from a fresh database. Confirm approved expiry for local snapshots and off-device copies separately. Clean up drill copies through the approved private process.

## 7. Update, roll back or remove

Stage the new reviewed SHA alongside the last known-good release using section 2; retain separate configuration and state. Before switching, save a checked pre-update snapshot and record the prior link, active database, configuration and unit files. Review schema compatibility and test the new code and rollback on a restored copy with collection disabled. Then stop the edge and app, switch `current` atomically using section 2 and start the app locally. Run the relevant gates, then re-enable approved access and collection. Avoid overlapping collectors for the same service or running duplicate polling during a drill. For code-only rollback, repoint `current` to the previous immutable release when it can read the current schema, restore compatible config, and restart and verify. If compatibility is uncertain, use a fresh restore path from the pre-update snapshot and keep the newer database for recovery. If replacing a unit file, also run `systemctl daemon-reload` and verify it. Remove superseded releases and snapshots only after the approved rollback window.

To back out an initial install, stop and disable both app units, remove only this app's optional Serve route and firewall rule, and restore any app-specific unit/configuration changes. Preserve app data privately until its disposition is approved. Recheck Calendar, Home Assistant and Music Assistant.

## 8. Acceptance gates

Use the real origin only for a gate the operator has approved. With collection still disabled, the following probes should give 409 (valid, with `no_enabled_sources`), 403 (foreign origin) and 400 (missing refresh header), respectively. Repeat from the client allowed at each private ingress. An out-of-scope client should fail to connect or get an ingress denial without receiving data. A preflight `OPTIONS` request from a foreign origin must receive no CORS permission.

```sh
curl -i --max-time 5 -X POST -H "Origin: $ORIGIN" -H 'X-Mountain-Refresh: 1' "$ORIGIN/v1/refresh"
curl -i --max-time 5 -X POST -H 'Origin: https://outside.example' -H 'X-Mountain-Refresh: 1' "$ORIGIN/v1/refresh"
curl -i --max-time 5 -X POST -H "Origin: $ORIGIN" "$ORIGIN/v1/refresh"
```

| Stage | Development verification | Physical Pi acceptance after approval |
| --- | --- | --- |
| Release and local startup | Verify CLI version, unit syntax, disabled-source launch, loopback health, dashboard and graceful exit | Verify exact ARM64 package and NVMe paths. Start with no collection, confirm every source is off, confirm only loopback owns the Python port, and verify a boot restart during the approved window. |
| Ingress and refresh | Exercise rendered Nginx over development loopback, including bad Host, cross-origin and malformed POST rejection | Household phone and wall can load dashboard and assets; guest and outside clients cannot. Confirm origin, empty-body and custom-header requirements and no CORS. Backend port is unreachable remotely. |
| Optional remote gate | Exercise the second edge listener with the expected HTTPS Host and Origin through a local proxy stand-in | Approved signed-in tailnet client works; an unapproved tailnet identity and a non-tailnet internet client fail. Inspect Serve and Funnel state for this app. Test refresh through HTTPS. |
| Recovery | Exercise online backup of committed WAL state, restore to a new path and start with sources off | Recover an approved snapshot into a fresh path, verify offline, and drill release pointer rollback. Confirm retention and backup coverage privately. |
| Source opt-ins | Synthetic scheduler and browser suites exercise fresh, stale, missing, blocked, capped and disabled states | Enable one approved subset at a time. Confirm retrieval, provenance, correct time/freshness, disabled sources, refresh cooldown and no repeated provider errors. |
| Load and coexistence | Chromium checks wall and mobile layouts with synthetic weather | At 1920 × 1080 use physical touch to switch tabs, open webcam detail, and use Refresh Data. Check Overview fit, mobile touch, themes and keyboard focus. Compare RAM, CPU, disk and device responsiveness through a representative day of scheduled polling, after a reboot, and with family traffic. Recheck Calendar, Home Assistant and Music Assistant against the baseline after each stage. |
| Sign-off | Keep the simulation and Pages assets in the repository | Record private operation, recovery and coexistence evidence. Seek separate approval before retiring simulated Pages. |

See the release handoff for development results and limitations. [Latest handoff](../../handoffs/LATEST.md)

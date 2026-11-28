# v0.3.4 private Raspberry Pi installation

v0.3.4 is proposed for review. The owner reported that the existing production installation passed network security, refresh validation, automatic startup, reboot recovery and encrypted configuration backup verification. Run the gates below again for any approved upgrade. The target is a Raspberry Pi 5 with 4 GB RAM, NVMe, Raspberry Pi OS (Debian 13, ARM64), and a 1920 × 1080 Chromium touchscreen. Follow the stages below only after the owner approves a maintenance window and production installation. The package is the reviewed Git revision, the standard-library Python service and the templates in this directory.

The Python service binds to IPv4 loopback. An optional dedicated, unprivileged Nginx instance provides trusted household LAN access. It can also receive traffic on a second loopback port from authenticated Tailscale Serve. There is no public ingress. The wall browser can use the direct loopback URL on the Pi. Keep the standalone simulation and existing simulated GitHub Pages preview until private operation is verified and the owner separately approves Pages retirement.

## 1. Preflight for the Pi

Record actual paths, ports, firewall rules, access decisions, service baselines, and backup details in the private operations handoff.

- [ ] Confirm Debian 13 ARM64 (`uname -m` should show `aarch64`), Python 3.10+ with `sqlite3`, systemd with cgroup v2, a working clock, DNS and upstream HTTPS. Check the installed Chromium build, actual 1920 × 1080 display and touch input. Verify the NVMe mount for application and state with `findmnt -T`. Check space and inodes with `df -h` and `df -i`.
- [ ] Inventory Calendar, Home Assistant, Music Assistant, the existing wall launcher, proxies and listeners, including IPv6 and containers. Check actual service names and health indicators and capture a baseline before the window. Use `ss -ltnp` and read the current firewall, route and ingress configuration. Verify every proposed port, unit name, account, path and current symlink is available or belongs to this app. Avoid global proxy, DNS, wall launcher and network changes.
- [ ] Reserve the Pi’s LAN IPv4 address in DHCP for the hardware address of the intended interface. Confirm the reservation is in the correct subnet, avoids conflicts and survives a lease renewal or reboot. Check the interface and assigned address with `ip -4 address show dev "$LAN_IFACE"`. Recheck the reservation when changing interfaces. Choose a dedicated unprivileged LAN port and an approved household source CIDR. Verify firewall filtering on the intended interface and source subnet. Check guest Wi-Fi, VLAN routing, IPv6, router port forwards and UPnP, reverse tunnels and any public proxies or Funnel rules. Binding to a LAN IP alone does not restrict routed traffic. Leave LAN ingress disabled until isolation is verified.
- [ ] If adding the edge, verify the path to a supported Nginx binary and modules. Use an available binary where possible. If absent, arrange approved provisioning that avoids starting any distro default listener or touching existing proxy configuration. The sample runs its own process, runtime directory and config. For optional Tailscale, also verify the installed CLI, current Serve and Funnel mappings, allowed identities and devices, access grants or ACLs, DNS/TLS and an unused Serve endpoint. A broadly accessible existing tailnet policy is insufficient. Leave Serve off if it would collide or require modifying an existing service.
- [ ] Verify the encrypted configuration backup, its exclusions, retention, key recovery and last successful restore drill. Identify a private drill location. Plan database or snapshot space separately if using the optional SQLite recovery procedure.
- [ ] Record which sources the owner authorizes to run continuously and read the current terms, retention and rate limits. Verify the site can be tested with no sources enabled first. [Source decisions](../../DATA_SOURCES.md)

## 2. Install the release and start locally

All values below are examples. Substitute the verified account, paths and ports everywhere, including the unit, environment and proxy files. Keep absolute data and configuration paths outside all release trees. Use paths without spaces in these templates.

| Purpose | Example | Ownership and mode |
| --- | --- | --- |
| Immutable source releases | `/opt/whitewater-mountain/releases/v0.3.4-<short-sha>` | root-owned, service-readable, release directories 0755 |
| Active release link | `/opt/whitewater-mountain/current` | root-managed |
| Persistent SQLite and lock files | `/var/lib/whitewater-mountain` | dedicated service UID/GID, directory 0700 |
| Service settings | `/etc/whitewater-mountain/service.env` | root-owned 0600, read by systemd |
| Edge configuration | `/etc/whitewater-mountain/nginx.conf` and `ingress/` | root-owned, read-only to dynamic proxy user, directory 0755 and files 0644 |
| Optional LAN firewall | `/etc/whitewater-mountain/mountain-firewall.nft` | root-owned 0600, read by the firewall unit |
| Backup restore drill and optional snapshot staging | verified separate directories | private 0700 and files 0600, app maintenance user access as needed |

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
release="$app/releases/v0.3.4-$short_sha"
staging=$(mktemp -d)
git archive --output="$staging/release.tar" "$sha" index.html mountain_service poc
mkdir "$staging/code"
tar -xf "$staging/release.tar" -C "$staging/code"
(cd "$staging/code" && /usr/bin/python3 -EsB -m mountain_service --version)
# Check it prints 0.3.4 before copying or switching.
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

Copy [service.env.example](service.env.example) as the private mode-0600 `service.env`. Keep both argument lists empty. Review [whitewater-mountain.service](whitewater-mountain.service), then install the rendered copy at the verified system unit location with mode 0644. Use `systemd-analyze verify` before installing. Run `sudo systemctl daemon-reload` and `sudo systemctl start whitewater-mountain.service`. An active unit can precede HTTP readiness. Run this bounded readiness check with the verified loopback URL before opening the dashboard, starting the edge or enabling boot startup.

```sh
wait_for_health() {
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        if status=$(curl --noproxy '*' --silent --show-error --connect-timeout 1 \
            --max-time 3 --output /dev/null --write-out '%{http_code}' "$1") &&
            [ "$status" = 200 ]; then
            return 0
        fi
        [ "$attempt" = 10 ] || sleep 2
    done
    printf 'Health check did not return HTTP 200 after ten attempts.\n' >&2
    return 1
}
wait_for_health http://127.0.0.1:8765/healthz
```

The probe spends at most about 48 seconds on requests and waits. If it fails, stop the rollout and inspect the app unit and its journal locally. When it succeeds, confirm the dashboard loads, collection is off for a fresh installation, and the API listener is loopback-only. Enable boot startup with `sudo systemctl enable whitewater-mountain.service` and confirm with `systemctl is-enabled whitewater-mountain.service`.

## 3. Add private access in stages

Use [whitewater-mountain-edge.service](whitewater-mountain-edge.service), [nginx.conf.example](nginx.conf.example) and [proxy.conf.example](proxy.conf.example) when ingress is needed. Place the rendered shared proxy snippet at the configured `proxy.conf` path, with the actual Python port. The `ingress/` directory should contain only approved rendered site files. Check all included paths. Nginx limits concurrent requests, disables access logs, and preserves Host and Origin; the Python service matches them against the explicit browser origin. The refresh POST requires that exact Origin, the custom header, an empty body and no transfer encoding. Scheduler cooldowns and source limits still apply. Same-origin checks protect browser requests from cross-site initiation. Network policy controls which clients can access the app. Local Pi processes can reach the loopback port.

**LAN.** Render [lan.conf.example](lan.conf.example) with the reserved IPv4 address, dedicated port and allowed CIDR. Use the host's verified firewall or the optional Mountain firewall below. Confirm the reserved address is assigned before starting the edge. The edge orders startup after `network-online.target`. At boot that target relies on the active network manager's wait-online configuration, so verify the address is ready on the intended interface during the reboot gate. Keep wildcard listeners, router forwards, UPnP mappings and guest access off.

Set `MOUNTAIN_EDGE_ARGS="--allow-origin http://192.0.2.10:8780"` using the actual canonical LAN URL. Traffic on this HTTP listener is unencrypted and authorized by trusted network membership. Use the same URL in Chromium. Aliases require a reviewed ingress and origin. Restart the app to load its environment and repeat the loopback health check. Verify the rendered edge unit and config before starting `whitewater-mountain-edge.service`. The unit runs `nginx -t` as its own dynamic user before startup. Leave the distro default Nginx service alone.

From an allowed LAN client, reuse the bounded check with the LAN URL plus `/healthz`. The Pi’s wall browser can use the direct loopback API URL. Complete the ingress and refresh gates below before enabling the edge with `sudo systemctl enable whitewater-mountain-edge.service`. Check `systemctl is-enabled whitewater-mountain-edge.service`.

**Optional Mountain LAN firewall.** Use these templates when the host needs separate app-scoped nftables rules. They use the host's existing nftables support and a dedicated port. Coordinate with the host firewall owner and confirm a whole-ruleset reload will preserve the app table. The LAN allow rule matches the interface, source IPv4 subnet, destination IPv4 address and TCP port. The next rule rejects other local input to that TCP port, including IPv6 and loopback. Reserve that port on all addresses and use distinct ports for the backend and the optional Tailscale loopback listener. Other traffic continues through the existing rules. An allow from Mountain's chain still needs to pass all other host firewall chains.

1. Keep the edge stopped while installing or changing the ingress rules. Render [mountain-firewall.nft.example](mountain-firewall.nft.example) to `/etc/whitewater-mountain/mountain-firewall.nft`, substituting all four values and matching the LAN site config. Confirm that any existing `inet whitewater_mountain` table belongs to this app. Check the transaction with `sudo /usr/sbin/nft -c -f /etc/whitewater-mountain/mountain-firewall.nft`.
2. Install [whitewater-mountain-firewall.service](whitewater-mountain-firewall.service) and the [edge drop-in](whitewater-mountain-edge.service.d/10-firewall.conf) under `/etc/systemd/system/`, with the drop-in at `whitewater-mountain-edge.service.d/10-firewall.conf`. Verify the units with `sudo systemd-analyze verify /etc/systemd/system/whitewater-mountain-firewall.service /etc/systemd/system/whitewater-mountain-edge.service` and run `sudo systemctl daemon-reload`.
3. Start the edge. Its `BindsTo=` and `After=` pull in the static firewall unit and order successful rule loading before Nginx starts. The firewall stays `active (exited)` and has no boot enablement of its own. Check `systemctl is-active whitewater-mountain-firewall.service` and `sudo /usr/sbin/nft list table inet whitewater_mountain`. Verify the permitted and rejected paths before enabling the edge. The rules are replaced in one transaction and the stop action removes only the Mountain table. Leave global firewall configuration and unrelated tables in place.
4. To change or remove the Mountain rules, stop the edge first and stop the firewall unit before replacing files. Stopping the firewall through systemd also stops the bound edge, with reverse ordering. Start the edge again explicitly after updating the files, verifying the units and reloading systemd as needed. After any host firewall maintenance, verify the app table as well as unit status. systemd tracks the oneshot unit state and cannot detect rules removed by an external tool.

**Optional Tailscale.** Render [tailscale.conf.example](tailscale.conf.example) into `ingress/` only after the private access gate is approved. Use the actual tailnet HTTPS host and a different, unused loopback edge port. Append `--allow-origin https://<verified-tailnet-host>` inside the existing `MOUNTAIN_EDGE_ARGS` quotes and restart only the two app units. Use the origin alone, with no trailing slash and no default port. Confirm the installed Serve preserves the HTTPS request Host and Origin. Verify tailnet grants restrict the selected HTTPS endpoint to approved users or devices. With a free, approved default HTTPS endpoint and a compatible CLI, the example is `sudo tailscale serve --bg http://127.0.0.1:8781`. Check `tailscale serve --help`, `tailscale serve status` and `tailscale funnel status` against the private baseline before and after. Use Serve at the root so dashboard routes remain same-origin. Use an explicitly approved alternate HTTPS port if necessary and include it in the Host and origin. Never enable Funnel, reset shared Serve state, or change another route. Record the exact route-specific off command before enabling Serve. For the exact default-port example it is `sudo tailscale serve --https=443 off`, only when this app is the sole owner of that HTTPS listener. [Tailscale Serve CLI](https://tailscale.com/kb/1242/tailscale-serve)

## 4. Activate collection explicitly

After private ingress and recovery gates, add only approved keys in the service environment, as repeated `--collect SOURCE` arguments inside `MOUNTAIN_COLLECT_ARGS="..."`. Restart the Python service and verify provider states. For example, `MOUNTAIN_COLLECT_ARGS="--collect ifs --collect nelson_cs"` enables only the IFS forecast and Nelson observation. Other eligible keys are `hrdps`, `freezing_profile`, `drivebc_whitewater`, and, under the documented owner decision about factual measurements, `whitewater` and `whitewater_weather`. Review the latter two separately; their terms applicability and timestamps have open questions. Whitewater gallery and camera stills remain official links. Southridge, regional snow, and avalanche feeds have no collection flags. Remove the relevant flags and restart to disable sources. Existing cache material expires under its retention rules. [Cadences and backoff](../../mountain_service/README.md)

## 5. Monitor health, disk and diagnostics

- Check `systemctl is-active whitewater-mountain.service` and the bounded `/healthz` gate in section 2 with the actual port. Use the existing approved local monitor if available, for example every minute with an alert after three failures. Boot and crash recovery are owned by systemd. A persistent 503 warrants investigation. The health check does not establish weather freshness. The dashboard shows source availability, backoff and stale states separately.
- Check `systemctl show whitewater-mountain.service -p MemoryCurrent -p CPUUsageNSec -p TasksCurrent -p NRestarts`, and the same for the edge. Sample aggregate use including Chromium and compare the existing services under normal wall and family-device load. The app's proposed cgroup settings are 96 MiB memory pressure, 160 MiB hard cap, 32 tasks and 50% of one CPU. The edge's proposed settings are 24 MiB, 48 MiB, eight tasks and 25% of one CPU. These caps exclude Chromium. Tune only after Pi measurements.
- The app unit caps individual files at 32 MiB, including separate SQLite and WAL files. The edge runs in a private runtime directory with bounded requests and 1 MiB per-file limits. Neither per-file cap is a directory quota. Size the verified filesystem or an approved per-app quota for DB, WAL, SHM, releases, backup staging and restore headroom. Start with a 256 MiB app and local snapshot planning budget, retention of current and one known-good release, and at most two local snapshots within the approved time window. Monitor both bytes and inodes and alert before limits are reached. Unexpected WAL growth, file-limit errors or filesystem pressure are reasons to pause collection and investigate. Preserve the database and its sidecars together. The app prunes logical rows; allocated SQLite pages can remain for reuse.
- Review app-unit logs locally with `sudo journalctl -u whitewater-mountain.service -n 30 --no-pager`. Source errors use fixed codes, and request access logging is off. The unit limits log bursts, while the existing journal policy controls aggregate retention. Share only version, stage, HTTP status, source state/error codes and rounded resource totals. Keep raw logs, unit status output, client identities, URLs, paths, addresses, headers, weather records and screenshots private.

## 6. Backup and restore

### Minimal encrypted configuration backup

Use the existing approved encrypted backup method. Take a configuration backup after an approved release or configuration change and retain an encrypted off-device copy. Keep the decryption key or recovery material separately accessible to the operator. Use a restricted destination and an explicit file allowlist. Keep any staging owner-only and short-lived.

| Include | What to record |
| --- | --- |
| Release identification | Repository locator, reviewed full commit SHA, CLI version, target of `current`, and the prior known-good SHA for rollback |
| Installed deployment configuration | `service.env` (including source opt-ins), the active Nginx config and its included proxy and site files, and the rendered Mountain nftables file if used |
| Installed systemd units | The app and optional edge/firewall units and all app-specific drop-ins. Record app and edge enablement, the service account and path ownership/modes, and how any approved app-specific ingress is restored. |

Exclude reproducible application code and release trees, weather databases (including SQLite sidecars and snapshots), caches, images, logs, and host-wide configuration. Keep the archive, manifest and any private restore details outside the repository. Verify decryption, contents and permissions by restoring to a new private scratch directory before trusting the backup. Rebuild the release from its recorded SHA. Inspect and verify restored units and config, then start locally with collection off. If the state directory is lost, a new database starts without cache history, provider stops, cooldowns or the persisted daily budget. Check the private operating record for any provider blocks or retry windows and wait for the next UTC day before resuming collection after losing the budget.

### Optional SQLite recovery drill

This is a separate procedure for an approved local snapshot or database rollback. Keep its output outside the minimal configuration backup. Use the active release's CLI as the dedicated service account with an approved private destination accessible to it. Backup staging and target paths must have sufficient free space, be outside the release, and be fresh names in pre-created owner-only directories.

```sh
cd /opt/whitewater-mountain/current
sudo -u whitewater-mountain /usr/bin/python3 -EsB -m mountain_service backup "$LIVE_DB" "$NEW_SNAPSHOT"
sudo -u whitewater-mountain /usr/bin/python3 -EsB -m mountain_service restore "$NEW_SNAPSHOT" "$NEW_RESTORE_DB"
```

The online SQLite backup includes committed WAL pages, checks the application schema, integrity and foreign keys, and produces a standalone 0600 database. Use this command even when the service is stopped. Do not substitute a copy of the live main database file. Never delete active WAL, SHM or journal files. Restore refuses overwrite and orphaned destination sidecars. Test the restored database on an unused loopback port **without `--collect`**, as the service account, and with no ingress. Check the restore health, expected schema and provider/budget state privately. Stop the drill process before promoting its data. To cut over, stop the edge and app, keep the old DB in place, select the restored DB path in `service.env` under the approved writable state directory, clear collection flags, and start and verify locally before re-enabling access. Check restored backoff, provider stops and daily refresh budget against newer operational history before re-enabling collection. A stale snapshot can roll them back.

Follow the source windows for stored data and backups. The live cache keeps forecast/derived snapshots for up to seven days subject to the current-snapshot rule, recent Nelson readings for 48 hours, and only the latest snapshot per Whitewater product. DriveBC imagery is in memory. A full snapshot can contain records that age out of the running DB before the snapshot expires. Verify that the backup policy permits this extended exposure or keep this cache out of retained backups and recover from a fresh database. Confirm approved expiry for local snapshots and off-device copies separately. Clean up drill copies through the approved private process.

## 7. Update, roll back or remove

Stage the reviewed SHA alongside the last known-good release using section 2. Confirm the previous link target, active database and unit enablement privately and refresh the encrypted configuration backup. v0.3.4 has no database schema migration. For a future schema change, check rollback compatibility first and rehearse with an approved local snapshot and collection off.

Stop the edge before changing its config, firewall or units. Stop the app, switch `current` atomically using section 2 and verify changed units before `sudo systemctl daemon-reload`. Start the app and run the loopback gate before starting any approved ingress. For a collector-disabled drill, clear the collection flags before starting and restore only previously approved flags after the gates pass. Avoid running duplicate collectors during the rollout.

To roll back, stop the edge and app, switch to the previous immutable release, and restore its compatible configuration, app-specific units and drop-ins. Keep the state directory in place for a schema-compatible rollback. If a future schema is incompatible, use a fresh path from a checked pre-update snapshot and retain the newer database. If rolling back the optional firewall, stop its unit while its stop command is still configured. Remove the drop-in and Mountain firewall unit only after securing the port with the previous host rules or leaving LAN ingress disabled. Verify units, reload systemd, then repeat loopback and private ingress gates and confirm the prior boot settings.

To back out an initial install, stop and disable the edge and app, stop the optional firewall unit and remove only this app’s optional Serve route. Restore the previous app-specific files and reload systemd. Preserve app data privately until its disposition is approved. Recheck Calendar, Home Assistant and Music Assistant.

## 8. Acceptance gates

Use the real origin only for a gate the operator has approved. With collection still disabled, the following probes should give 409 (valid, with `no_enabled_sources`), 403 (foreign origin) and 400 (missing refresh header), respectively. Repeat from the client allowed at each private ingress. An out-of-scope client should fail to connect or get an ingress denial without receiving data. A preflight `OPTIONS` request from a foreign origin must receive no CORS permission.

```sh
curl -i --max-time 5 -X POST -H "Origin: $ORIGIN" -H 'X-Mountain-Refresh: 1' "$ORIGIN/v1/refresh"
curl -i --max-time 5 -X POST -H 'Origin: https://outside.example' -H 'X-Mountain-Refresh: 1' "$ORIGIN/v1/refresh"
curl -i --max-time 5 -X POST -H "Origin: $ORIGIN" "$ORIGIN/v1/refresh"
```

| Stage | Development verification | Physical Pi acceptance after approval |
| --- | --- | --- |
| Release and local startup | Verify CLI version, unit syntax, disabled-source launch, loopback health, dashboard and graceful exit | Verify the ARM64 package and NVMe paths. Record `getconf PAGESIZE` and confirm the dedicated Nginx starts with the 1 MiB zone on the 16 KiB kernel. Start with no collection, confirm every source is off, and confirm only loopback owns the Python port. |
| Boot and firewall lifecycle | Check the unit wiring and Nginx template in development | Confirm the firewall rejects an invalid configuration with the edge down. With valid rules, confirm starting the edge brings up the static firewall and stopping the firewall stops the edge before the table is removed. Verify unrelated services and firewall rules remain intact. |
| Ingress and refresh | Exercise rendered Nginx over development loopback, including bad Host, cross-origin and malformed POST rejection | Household phone and wall can load dashboard and assets; guest and outside clients cannot. Confirm origin, empty-body and custom-header requirements and no CORS. Backend port is unreachable remotely. |
| Optional remote gate | Exercise the second edge listener with the expected HTTPS Host and Origin through a local proxy stand-in | Approved signed-in tailnet client works; an unapproved tailnet identity and a non-tailnet internet client fail. Inspect Serve and Funnel state for this app. Test refresh through HTTPS. |
| Recovery | Exercise online backup of committed WAL state, restore to a new path and start with sources off | Decrypt and inspect a configuration-only backup in private scratch space. Verify the pinned release and app-specific units can be restored and drill release pointer rollback. If separately approved, drill SQLite recovery with a fresh path. |
| Source opt-ins | Synthetic scheduler and browser suites exercise fresh, stale, missing, blocked, capped and disabled states | Enable one approved subset at a time. Confirm retrieval, provenance, correct time/freshness, disabled sources, refresh cooldown and no repeated provider errors. |
| Load and coexistence | Chromium checks wall and mobile layouts with synthetic weather | At 1920 × 1080 use physical touch to switch tabs, open webcam detail, and use Refresh Data. Check Overview fit, mobile touch, themes and keyboard focus. Compare RAM, CPU, disk and device responsiveness through a representative day of scheduled polling, after a reboot, and with family traffic. Recheck Calendar, Home Assistant and Music Assistant against the baseline after each stage. |
| Sign-off | Keep the simulation and Pages assets in the repository | Record private operation, recovery and coexistence evidence. Seek separate approval before retiring simulated Pages. |

**Reboot acceptance.** During the approved window, record the app and edge enablement and private access baseline before rebooting. After reboot, wait for the Pi to return without manually starting any app unit. Confirm the reserved LAN address, app and edge unit state, and the Mountain table if configured. Run the bounded loopback and permitted-client health checks. Repeat the denied-client and refresh checks on the approved paths and confirm any optional Serve mapping is still private. Verify the wall dashboard works and recheck unrelated services. Inspect the current boot's unit journal privately if any gate fails. Use the rollback procedure if service or isolation cannot be restored within the window.

See the release handoff for development results and limitations. [Latest handoff](../../handoffs/LATEST.md)

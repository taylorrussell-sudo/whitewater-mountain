# v0.3.1 private mountain weather collection service

## Completion timestamp / objective

Completed at `2026-11-26T15:51:36-07:00` (America/Vancouver). Build and verify the independent weather collection service for the private household dashboard.

## Repository / branch / PR URL / commit SHA

`taylorrussell-sudo/whitewater-mountain`, branch `feature/v0.3.1-private-data-service`, based on `cbcf548c08d8e9e79a33309041cee9547d24488a`. Tested implementation and documentation commit `b2a34f6518c68c8916c11a9a917ecdf7470a5d59`. This handoff and its pointer follow on the same branch. [Pull request #8](https://github.com/taylorrussell-sudo/whitewater-mountain/pull/8)

## Version and status

v0.3.1 is proposed in an open PR. The existing v0.2.1 dashboard stays simulated and byte-identical to the base. No merge, Pages publication, Pi deployment or production access took place.

## Changes and files affected

- Add `mountain_service/` with IFS 9 km for the extended outlook, independent HRDPS 2.5 km guidance, measured Nelson CS, and derived GFS 0.25° freezing levels. Weather JSON includes source credit, valid and retrieval times, freshness, and explicit missing values. [Local API and operations](../mountain_service/README.md)
- Add persistent per-source refresh state, retries, provider-wide cooldowns and stops. Add normalized SQLite history and read-only views with seven-day forecast/profile retention and a 48-hour Nelson cache. Reuse the SQLite snapshot helper for committed WAL state and checked standalone snapshots.
- Update the README, requirements, source register, backlog and changelog. Add synthetic service regressions. Whitewater and Southridge remain disabled. Actual Whitewater snowfall stays unavailable pending permission. [Source register](../DATA_SOURCES.md)

## Design decisions and limitations

Linux and the Python standard library suffice for the service. The listener is loopback-only and each live adapter requires an explicit collection flag. Forecast age uses successful retrieval time. The upstream API does not identify exact forecast initialization. GeoMet retention is a bounded recent cache without backfill.

The GFS freezing-level product uses actual modeled temperatures and geopotential heights from contiguous pressure levels above the model terrain. Keep multiple crossings and exact-zero intervals. Missing layers, model terrain and sparse vertical sampling can leave crossings unresolved. The sampled model agreement does not establish accuracy at the resort. IFS and HRDPS stay separately attributed, and the GFS product stands on its own. More events and comparable observations are needed for accuracy and seasonal checks. [Source evidence](../DATA_SOURCES.md)

## Tests run, environment and results

- Python 3.12.14, SQLite 3.53.1 and Chromium 156.0.8078.79 on Debian Linux. `python -B -m unittest discover -s mountain_service/tests -v` passed 15 tests, the PoC suite passed 16, and the Chromium dashboard suite passed 13. `git diff --check` passed. Dashboard HTML and browser tests match the base branch.
- Service regressions covered malformed or partial responses, recoverable 503 and timeout, Retry-After, provider stops across restarts, last-good cache, transaction rollback, process kill and restart, and verified backup/restore with committed WAL state. An open uncommitted change was excluded from the snapshot.
- The default command sandbox could not create loopback sockets or reach the configured proxy. Retrying with workspace network access allowed the loopback tests, Chromium checks and one-shot provider probes. The four probes returned 170 IFS and 45 HRDPS populated hours per metric at each point, six Nelson features and 72 usable GFS profiles. The same-product scalar comparison averaged roughly 10 m separation for 10 matched single-crossing hours. An independent ICON scalar differed by about 328 m on average over the same set. The multiple-crossing cases were verified with synthetic data.
- A 14-day synthetic workload ran 616 fetches in about 1.1 seconds of wall time. It used about 24 MiB peak process RSS and 1.1 MiB peak SQLite files, with a passing integrity check. An idle loopback process used about 18 MiB RSS after 200 weather GETs against an empty cache, with 0.96 ms p95 request latency and no CPU ticks recorded during 30 seconds idle. These are development-host measurements.

## Dependencies / privacy / backup implications

The runtime uses no paid or external package dependency. Upstream probes saved no weather payloads. Fixtures and all temporary databases stayed in development, and no live records or connection details are in GitHub. SQLite backup and recovery were verified on synthetic data. Keep snapshots private and expire them within the applicable source retention windows. Production encrypted backup coverage and a targeted Pi restore remain future checks.

## Rollback / next work / approvals

Close PR #8 to keep main as it stands. Use a reviewed revert if a future merge needs rollback. Frontend integration is v0.3.2. Validate model skill, freezing-level limitations and station coverage over more events. Obtain Whitewater and Southridge permissions before adding those adapters. Merge, deployment, private networking, production backups and Pages retirement require separate approval. [Backlog](../BACKLOG.md)

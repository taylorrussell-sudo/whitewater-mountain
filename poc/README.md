# Local data proof of concept

This v0.3.0 trial uses Python 3.10+ and its standard-library SQLite module. Run from the repository root. The demo and tests use invented data and create no server. The existing dashboard has no dependency on this directory.

```sh
python3 -B -m unittest discover -s poc/tests -v
trial_dir=$(mktemp -d)
python3 -B -m poc demo "$trial_dir/trial.sqlite"
python3 -B -m poc backup "$trial_dir/trial.sqlite" "$trial_dir/restore.sqlite"
```

The demo normalizes six input streams: Whitewater snow report, Whitewater base weather, Whitewater summit weather, lodge forecast, valley forecast and Nelson CS temperature. It stores those inputs under synthetic source IDs and prints their freshness status and computed snowfall windows. Running it again on the same database leaves six snapshots. Tests verify duplicate and concurrent writes, transaction rollback, stale/missing data, the effects of forecast gaps, and restore of committed WAL data while excluding an uncommitted write. Use temporary paths outside the repository.

## Manual open-data checks

Run each command once where those public API hosts are authorized. The commands send one bounded GET each, validate content type and input shape, report diagnostic metadata and keep the payload in memory. Timeouts and HTTP, parsing or validation failures exit nonzero. A completed ECCC probe may report stale data. A completed forecast probe may report incomplete snowfall windows or unavailable fields.

```sh
python3 -B -m poc probe forecast-lodge
python3 -B -m poc probe forecast-valley
python3 -B -m poc probe eccc
```

The forecast commands default to GEM Global. Add `--model ecmwf_ifs` for the IFS 9 km outlook or `--model gem_hrdps_continental` for the operational 2.5 km Canadian forecast. Use `python3 -B -m poc probe --help` for the complete list.

All three default commands passed on 2026-11-26. GEM Global returned 169 consecutive matching UTC hours, complete 72-hour snowfall windows and no freezing-level values. Check the returned grid centres and adjustment elevations, field coverage and aligned forecast times whenever comparing points. Short-range models can return 169 timestamp slots with many missing values near the end. For ECCC, check the station and provider metadata, observation age and distinct valid times. Hourly and minute products can share one valid time. The summary uses the newest processing time to break a tie, while the normalizer preserves both feature IDs. These diagnostics make requests only to Open-Meteo and ECCC. [Provider evidence, permissions and recommended sources](../DATA_SOURCES.md)

## Architecture assessment

Python and SQLite are sufficient for the tested local workload. The demo and standalone snapshot each measured 36 KiB with six synthetic snapshots on Linux. Forecast storage grows with changed snapshots and the number of points/variables. For example, two points at eight checks per day would allow up to 5,840 snapshots/year before deduplication. This scenario projects an upper bound on snapshot count. Measure actual load, disk growth, SQLite WAL size, cold start and restore time before choosing retention and schedules.

- **Collection.** Keep adapters independent and normalize/validate before the database transaction. A scheduled collector can publish to SQLite and the eventual local application can read cached data without triggering upstream calls. Use one scheduled writer, per-source timeouts and backoff, and conditional requests when supported. Provider licence and long-term storage terms gate enabling each source. No scheduler, HTTP service or production configuration is included.
- **Cache and history.** An atomic transaction updates the source's current pointer and adds a normalized snapshot only when the last successful payload changes. A failed refresh preserves its last success and records the error. Older completions cannot replace newer ones. Separate time of first snapshot, last attempt and last successful retrieval from source times. Forecast cache age is only a retrieval-age signal and requires complete next-24-hour snowfall coverage in this trial. Missing, invalid or future-dated readings stay unavailable. Provisional trial ages are 2 h for measurements, 30 h for report updates and 14 h for the forecast cache. Stale snapshots remain available for diagnosis and require stale labelling if shown.
- **Storage choices.** Per-source snapshot JSON in SQLite avoids a proliferation of tables in this trial. For permitted long-term history, store typed UTC observation rows keyed by source, station, metric, window and valid time; allow corrections with upstream IDs or revision metadata. Forecast verification needs retrieval and valid times plus actual model run IDs where supported. Keep only a short forecast cache unless local skill scoring is approved, and use MSC Datamart for systematic ECCC storage. Decide retention and prune it independently of cache expiry. These are design choices for v0.3.1; this trial contains no live storage.
- **Backup consistency.** Use SQLite's backup API into a staged file on the destination filesystem, check integrity and foreign keys, then publish the standalone file without overwriting an existing snapshot. It includes committed WAL data while the source connection remains open. Copying the primary file alone can omit committed writes. In production, include only permitted history plus approved code, settings and service definitions in encrypted backup coverage. Restore into an isolated directory, verify schema/integrity/counts and meaningful sample timestamps, then approve switching paths and restarting. The synthetic restore passed. Production encryption, recovery and power-loss durability remain unverified. [SQLite online backup API](https://www.sqlite.org/backup.html)

The next service milestone owns refresh scheduling, retention, a read interface, and resource testing off the Pi. Frontend integration, private network access, deployment and public Pages retirement have separate backlog items. [Backlog](../BACKLOG.md)

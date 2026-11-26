# Private mountain weather service v0.3.2

The service requires Python 3.10+ on Linux and uses Python's standard library and SQLite. It listens on IPv4 loopback. Open the service URL for the private dashboard. Opening the repository’s static index directly runs the standalone simulation.

## Run in development

Start with an empty cache and no outbound requests. Use an owner-only directory outside the repository for the database and all backups.

```sh
state_dir=$(mktemp -d)
python -B -m mountain_service serve --db "$state_dir/mountain.sqlite"
```

The default URL is `http://127.0.0.1:8765`. Use `--port 0` for an ephemeral port. The service logs the selected port and sanitized refresh failures. The process holds an exclusive lock for its database. SIGTERM and Ctrl-C stop the listener and allow the collector to finish its current request.

For a one-shot check from an authorized development environment, use `python -B -m mountain_service probe ifs` and repeat for `hrdps`, `nelson_cs`, and `freezing_profile`. The command reports coverage and response metadata without printing readings or saving a cache. Use the synthetic regression suite for recurring development checks. Enable specific sources with repeated `--collect SOURCE` flags only for authorized private operation. Whitewater, Southridge and regional snow sources have no collection routes. [Source validation and permissions](../DATA_SOURCES.md)

| Source key | Role | Poll interval | Fresh for |
| --- | --- | --- | --- |
| `ifs` | Primary ECMWF IFS HRES 9 km outlook, with 170 hours requested at lodge and Nelson | 3 hours | 9 hours from last successful retrieval |
| `hrdps` | Separate Canadian HRDPS Continental 2.5 km guidance, with 48 hours requested at both points | 3 hours | 9 hours from last successful retrieval |
| `nelson_cs` | ECCC measured valley air temperature, up to six recent features | 1 hour | 2 hours from observation time |
| `freezing_profile` | NOAA GFS 0.25° derived freezing levels near the lodge, with 72 hours requested | 6 hours | 12 hours from last successful retrieval |

Forecast polls each use a single two-point request. With all products enabled, the nominal totals are 20 Open-Meteo HTTP requests and 24 SWOB requests per day before retries. Open-Meteo can count requests with many variables as multiple calls. The service polls independently of dashboard traffic. It uses an eight-second socket timeout, a body read deadline and a 1 MiB body limit. Network errors, timeouts, HTTP 408 and transient 5xx retry starting at one minute and double up to the normal interval. Invalid or empty data and other request errors wait until the normal interval. A 429, or an HTTP 503 with `Retry-After`, pauses all adapters for that provider until at least the requested time, with a five-minute minimum and a one-hour fallback if the header is unusable. A 401 or 403 stops that provider across restarts. Once access has been confirmed, stop the service and run `python -B -m mountain_service resume --db "$state_dir/mountain.sqlite" open-meteo` (or `eccc`). Due times and cooldowns persist across restarts.

## Local API v1

Requests must address `127.0.0.1` or `localhost` at the bound port. Dashboard assets and JSON use `Cache-Control: no-store`. The service serves only the dashboard, its live script and the documented endpoints. The dashboard reads same-origin cached data on a timer. Network access beyond loopback requires separate architecture and access approval.

- **`GET /`** serves the live dashboard using the same HTML as the static simulation. The service marks the page as private and includes the live script.
- **`GET /v1/refresh`** returns the current manual batch’s phase, per-source outcomes and remaining cooldown seconds. Phases are `idle`, `queued`, `running`, `complete`, and `failed` (interrupted batch). A completed batch can contain individual failures or skips.
- **`POST /v1/refresh`** requires an exact same-origin HTTP `Origin` matching the local `Host`, the `X-Mountain-Refresh: 1` header and an empty body with no transfer encoding. The service sends no CORS headers. A valid request returns 202 and queues a batch on the single scheduled worker. A concurrent manual request or disabled collection returns 409. The 60-second server-wide request cooldown returns 429 with `Retry-After`. An unavailable collector returns 503.

The scheduler checks every enabled source in order. It can advance a healthy Open-Meteo source’s due time, with at least 60 seconds between completed checks for that source. Nelson keeps its one-hour minimum. Existing per-source retry due times, provider Retry-After and provider blocks take precedence. The next automatic check remains based on the most recent attempt and its normal interval or backoff. The request cooldown and batch progress live in the running process. Persistent checked times and provider state continue to protect upstream cadence across restarts. During refresh and recoverable failures, SQLite keeps the last successful snapshot and its original valid times.

- **`/healthz`** returns 200 if SQLite is readable and the collector loop is healthy. Database or collector faults return 503. Check per-source state in the weather response for upstream health.
- **`/v1/weather`** returns `api_version`, UTC `as_of` and a `sources` object keyed by the table above plus `whitewater` and `southridge`. Each entry has a label, kind, status and nullable data. Enabled sources also expose `checked_at`, `last_success_at`, `next_attempt_at`, `last_error`, `provider_state`, `age_seconds` and `age_basis`. Use each entry's `credit`, `link`, and `licence` when displaying data, including any provider notice carried by the observation. Disabled sources carry a reason. `unavailable` means there are no usable cached data for the relevant time. `fresh` and `stale` describe cached data. They can coexist with a recent refresh error. The dashboard labels stale sources and excludes their values from live indicators.
- **`/v1/observations/nelson`** returns up to 288 retained readings in reverse valid-time order, breaking ties by most recent processing time. The response includes the station metadata and retention window. The same ordering determines the latest measurement in `/v1/weather`. This endpoint represents an intermittent recent cache and may have time gaps.

### Reading the data

- **Forecasts.** `data.points.lodge` and `data.points.nelson` each include requested and returned location, `times` (Unix seconds UTC) and matching `values` arrays. Metrics are `temperature_2m`, `snowfall` and `wind_speed_10m` with units in `data.units`. Coverage gives populated counts and first/last UTC valid times per metric from the current hour. Use the timestamps themselves to align models and sites. For any missing bin or field, JSON `null` represents missing data. `model_issued_at` stays null because the ordinary API supplies a continuously updated series without exact model issue time. `snapshot_retrieved_at` identifies the first retrieval of the current cached content and `last_success_at` identifies its latest successful check. Short-range coverage can end before 48 hours. A downscaled point remains model guidance.
- **Snow outlook.** `data.lodge_snowfall_windows` is derived from that source's modeled snowfall alone. Each bin ends at its valid hour. The object gives the first complete hour boundary, totals keyed by `24`, `48`, and `72`, and the maximum rolling 24-hour window over the next 72 complete hours. The earliest window wins a tie. Missing bins suppress affected totals, and an incomplete 72-hour set suppresses the rolling maximum. Zero is a valid forecast. A stale snapshot yields null windows. Actual Whitewater snowfall remains unavailable.
- **Measured observations.** `temperature_c`, feature ID, location, valid time `valid_at`, provider processing time `processed_at` and `retrieved_at` describe the accepted station feature. Same-time hourly and minute products retain their separate IDs. The provider and additional attribution notice are included when present.
- **Freezing levels.** `data.times` and `data.crossings` are parallel UTC hourly arrays. At each hour, `null` means insufficient or invalid profile geometry, and `[]` means no 0 °C crossing was detected in sampled, contiguous layers. Otherwise the array preserves every detected crossing in ascending height. A linearly interpolated crossing has equal `lower_m` and `upper_m`, while consecutive sampled temperatures of exactly 0 °C can have an altitude range. The adapter uses geopotential metres above sea level from one grid column, masks pressure samples at or below grid terrain, and never bridges missing levels or extrapolates beyond the available brackets. Coarse sampling can miss shallow layers and near-surface or high crossings. This is derived GFS guidance for the requested vicinity, separate from IFS, HRDPS, surface air temperature, the snowfall transition and measured snow cover.

## Retention and database recovery

SQLite uses WAL with full synchronous writes. Successful refreshes commit source data and scheduling/status together. Forecast and derived snapshots are stored only when normalized content changes. Keep seven days of snapshots by retrieval time, plus the current snapshot while it remains within seven days of a successful recheck. Keep only the most recent 48 hours of valid Nelson feature times from GeoMet. This is a bounded recent cache, with no backfill or systematic archive collection. Pruning runs at startup and hourly. High-water database pages are reusable. Forecast histories are internal, while the API exposes the latest cache and recent observation window.

```sh
python -B -m mountain_service backup "$state_dir/mountain.sqlite" "$state_dir/backup.sqlite"
python -B -m mountain_service restore "$state_dir/backup.sqlite" "$state_dir/recovered.sqlite"
python -B -m mountain_service serve --db "$state_dir/recovered.sqlite" --port 8766
```

The backup reads committed SQLite state, including committed WAL pages. It validates database identity, SQLite integrity and foreign keys, then publishes a standalone owner-only file. Restore copies and validates into a new file and refuses an existing destination or orphaned SQLite sidecars. Use the recovered path after verifying it by starting the service with collection off and checking the API. Preserve the previous database for rollback. Never copy only the raw database file while the service is writing. Keep backup copies private and expire them on a schedule that preserves the source retention limits. Production encrypted backup coverage, final paths, and recovery on the Pi need separate verification.

## Development checks

```sh
python -B -m unittest discover -s mountain_service/tests -v
python -B -m unittest discover -s poc/tests -v
CHROMIUM_PATH=/usr/bin/chromium python -B -m unittest discover -s tests -v
```

The service and browser suites use synthetic data over loopback and uses temporary databases outside the repository. It covers malformed and missing data, forecast horizons, multiple crossings, transport and provider stops, stale cache, retention, transactions, restart and online backup/restore.

# Whitewater Mountain Conditions — v0.4.0 (candidate)

The private Python/SQLite service serves the existing dashboard with ECMWF IFS HRES, Canadian HRDPS, measured Nelson CS temperatures and derived NOAA GFS freezing levels. This independent household dashboard includes a static simulation for design review and regression testing.

## Local review

Open `index.html` directly for the six simulated scenarios. To review the private integration, start the service from the repository root with an owner-only state directory outside the repository.

```sh
state_dir=$(mktemp -d)
python -B -m mountain_service serve --db "$state_dir/mountain.sqlite"
```

Open `http://127.0.0.1:8765` for the private dashboard. Collection defaults to disabled. Use repeated `--collect` flags for explicitly authorized sources. The development [service guide](mountain_service/README.md) lists source keys, refresh behavior and cache operations. Add `--collect drivebc_whitewater` to enable the attributed Highway 6 junction still in Overview and Webcams. For private operation, add `--collect whitewater --collect whitewater_weather` to enable the resort snow report and mountain observations. Refresh Data can advance up to six weather batches per UTC day and checks the DriveBC camera when eligible. The status line shows the remaining weather budget.

The Webcams tab previews the five Whitewater camera positions with labeled synthetic stills and retains the official gallery and individual still links. The licensed DriveBC junction view uses the existing private integration. [Webcam integration review](DATA_SOURCES.md#whitewater-webcam-integration-in-v040)

The [v0.4.0 visual review](review/v0.4.0/README.md) includes wall and phone screenshots and a loopback preview. Start the preview with `--resort-stills-demo` to review selected-camera refresh timing using local synthetic stills. The resort's published display restriction applies to in-dashboard use of the JPEGs under this review. In the normal dashboard, the live resort files open through the official links. [Technical and terms findings](review/v0.4.0/whitewater-webcam-research.md)

## Automated regression checks

Use Python 3.10+ and Chromium. The tests launch a loopback server on a free port and exercise the static simulation and the private dashboard with synthetic API-shaped weather. They cover all six scenarios and five tabs, snowfall and inversion calculations, keyboard camera selection, 44 px camera targets, severity styling, themes and reduced motion, and layouts from 320 CSS px up to the 1920×1080 wall view. The private tests also cover refresh progress, cooldown, partial failure, stale data and recovery, plus webcam selection, enlarged viewing and image updates.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r tests/requirements.txt
python -m playwright install chromium
python -B -m unittest discover -s tests -v
```

Set `CHROMIUM_PATH` to the executable path to use an installed Chromium build. The browser suite checks official link destinations and gallery navigation with fixtures. The [regression record](review/v0.4.0/qa.md) gives the service, ingress and proof-of-concept commands and results. The [Pi runbook](deploy/pi/README.md#one-command-activation-for-a-reviewed-release) describes preflight, activation and rollback. Physical touchscreen and other browser checks are tracked in [BACKLOG.md](BACKLOG.md).

## Deployment direction (approved 2026-11-26)

One application, one codebase, one private household deployment on the Raspberry Pi. The existing public GitHub Pages v0.2.1 simulation is temporary family design feedback, not a second live environment. Retire Pages with separate approval when private hosting is verified, before enabling any public live-data access. Continue GitHub and Codex development using synthetic fixtures and local test servers. Keep all live weather records, caches and private configuration outside the repository.

The intended architecture is a lightweight local service with independent server-side weather adapters, a validated cache, local history storage where permitted, and the existing responsive frontend. LAN access for the wall and family devices; optional authenticated private Tailscale access subject to verification and approval. No public Funnel or new paid service. The [local collection service](mountain_service/README.md) defines the loopback API, SQLite retention and backup, and per-source schedules. The [Pi runbook](deploy/pi/README.md) provides installation preflight, private ingress templates, encrypted configuration recovery, a staged upgrade utility and physical acceptance gates. Production installation and physical-device checks require separate approval.

## Next steps

The isolated v0.3.0 proof of concept tests a Python/SQLite data path with synthetic inputs. Its one-shot live probes verified Open-Meteo lodge and valley forecasts and ECCC Nelson CS temperatures. The source review documents Canadian GEM and ECMWF coverage and the Southridge and Redfish Creek alternatives. Whitewater numerical collection is opt-in for household use under the owner’s decision. See the data source notes for unresolved terms and clock conventions. The owner reported that production runs v0.3.4 with backend and LAN health passing. Physical-device acceptance and post-upgrade encrypted backup verification remain pending. Review the v0.4.0 candidate and complete those gates before scheduling its production rollout. Pages retirement remains a separate decision. Summer mode is deferred. [Data source validation](DATA_SOURCES.md) · [PoC reproduction and architecture](poc/README.md)

## Logic
In the static dashboard’s six scenarios, simulated daily snow totals are distributed uniformly over hourly bins for illustrative rolling 24-hour forecast windows (starts 0–48 hours inclusive). Actual alerts use the last 24h; forecast alerts use the maximum 24h total ending within 72h. Values are illustrative, not a calibrated forecast. Real data needs hourly timing, model provenance and validation. Alert levels: 0–4, 5–9, 10–14, 15–24, 25–39, 40+ cm. A qualitative powder interpretation is scenario-defined rather than a numerical scientific score. No safety rating is computed from powder conditions.

### Temperature inversion

Choose **Valley temperature inversion** in Overview to see the schematic cold-air layer and compare simulated temperatures at Nelson valley (~535 m) and Whitewater Lodge (~1,630 m). The observed indicator compares the scenario-start pair. The forecast indicator uses the largest comparable lodge-minus-valley difference and shows its valid hour. Forecast onset and dissipation are bracketed by consecutive comparable samples three hours apart. A duration range is available when both transitions bound the same positive run.

Info explains the provisional dashboard thresholds. Two station readings indicate a temperature contrast and cannot establish the vertical profile or any layer boundaries. The inversion graphics use their own station comparison, independent of the freezing level, powder alerts, and avalanche ratings.

The inversion ski-context panel adds conditional temperature implications, separates observations and forecast peaks, and displays a simulated valley-fog / clear-lodge contrast only with matching sky data. No sky, snow-quality, or safety inference is made from temperature difference alone. Dissipation brackets describe the end of the positive station difference, not a guarantee of cloud clearance.

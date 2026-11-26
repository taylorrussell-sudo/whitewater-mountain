# Whitewater Mountain Conditions — v0.2.1 prototype

Self-contained static HTML/CSS/JavaScript. All numerical data is simulated. Camera artwork is schematic, not actual webcam imagery. This is an independent family design prototype, not an official resort or avalanche forecast. No live APIs, tracking, credentials or home network access.

## Local review
Open `index.html` in Chromium, Chrome, Safari or another modern browser. Change the scenario and theme; explore the five tabs and interactive Info controls. Auto theme follows device preference; reduced-motion system preference is respected. Settings reset on reload in this prototype.

## Automated regression checks

Use Python 3.10+ and Chromium. The tests launch a loopback server on a free port and exercise the actual static page. They cover all six scenarios and five tabs, snowfall and inversion calculations, keyboard camera selection, 44 px camera targets, severity styling, themes and reduced motion, and layouts from 320 CSS px up to the 1920×1080 wall view.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r tests/requirements.txt
python -m playwright install chromium
python -B -m unittest discover -s tests -v
```

Set `CHROMIUM_PATH` to the executable path to use an installed Chromium build. The suite checks official link destinations without opening them. Physical touchscreen and other browser checks are tracked in [BACKLOG.md](BACKLOG.md).

## Deployment direction (approved 2026-11-26)

One application, one codebase, one private household deployment on the Raspberry Pi. The existing public GitHub Pages v0.2.1 simulation is temporary family design feedback, not a second live environment. Retire Pages with separate approval when private hosting is verified, before enabling any public live-data access. Continue GitHub and Codex development using synthetic fixtures and local test servers. Keep all live weather records, caches and private configuration outside the repository.

The intended architecture is a lightweight local service with independent server-side weather adapters, a validated cache, local history storage where permitted, and the existing responsive frontend. LAN access for the wall and family devices; optional authenticated private Tailscale access subject to verification and approval. No public Funnel or new paid service. The proposed v0.3.1 [local collection service](mountain_service/README.md) defines the loopback API, SQLite retention and backup, and per-source schedules. Production service account, access and recovery checks are deferred to private deployment.

## Next steps

The isolated v0.3.0 proof of concept tests a Python/SQLite data path with synthetic inputs. Its one-shot live probes verified Open-Meteo lodge and valley forecasts and ECCC Nelson CS temperatures. The source review documents Canadian GEM and ECMWF coverage and the Southridge and Redfish Creek alternatives. Whitewater automated collection remains disabled pending written clarification. v0.3.1 covers the local service and permitted collection, v0.3.2 covers frontend integration, and v0.3.3 covers approved private deployment, recovery verification and Pages retirement. Summer mode is deferred. [Data source validation](DATA_SOURCES.md) · [PoC reproduction and architecture](poc/README.md)

## Logic
Six selectable scenarios. simulated daily snow totals are distributed uniformly over hourly bins for illustrative rolling 24-hour forecast windows (starts 0–48 hours inclusive). Actual alerts use the last 24h; forecast alerts use the maximum 24h total ending within 72h. Values are illustrative, not a calibrated forecast. Real data needs hourly timing, model provenance and validation. Alert levels: 0–4, 5–9, 10–14, 15–24, 25–39, 40+ cm. A qualitative powder interpretation is scenario-defined rather than a numerical scientific score. No safety rating is computed from powder conditions.

### Temperature inversion

Choose **Valley temperature inversion** in Overview to see the schematic cold-air layer and compare simulated temperatures at Nelson valley (~535 m) and Whitewater Lodge (~1,630 m). The observed indicator compares the scenario-start pair. The forecast indicator uses the largest comparable lodge-minus-valley difference and shows its valid hour. Forecast onset and dissipation are bracketed by consecutive comparable samples three hours apart. A duration range is available when both transitions bound the same positive run.

Info explains the provisional dashboard thresholds. Two station readings indicate a temperature contrast and cannot establish the vertical profile or any layer boundaries. The inversion graphics use their own station comparison, independent of the freezing level, powder alerts, and avalanche ratings.

The inversion ski-context panel adds conditional temperature implications, separates observations and forecast peaks, and displays a simulated valley-fog / clear-lodge contrast only with matching sky data. No sky, snow-quality, or safety inference is made from temperature difference alone. Dissipation brackets describe the end of the positive station difference, not a guarantee of cloud clearance.

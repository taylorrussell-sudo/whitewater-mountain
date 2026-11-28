# Changelog

## v0.3.4 (proposed) — 2026-11-27

- Increase the standalone Nginx connection zone to 1 MiB for Raspberry Pi 5 ARM64 kernels with 16 KiB memory pages. Add a template regression and retain the development proxy smoke test.
- Offer a dedicated nftables table for the private LAN edge and static systemd firewall ordering. Keep other firewall rules in place.
- Document DHCP reservations, bounded readiness probes, boot and reboot gates, secure ingress, rollback and a minimal encrypted configuration backup. [Pi runbook](deploy/pi/README.md)

## v0.3.3 (merged) — 2026-11-26

- Package a versioned Raspberry Pi install with dedicated systemd service and state, optional isolated household LAN and authenticated Tailscale Serve ingress, and explicit source opt-ins.
- Keep the API on loopback and validate exact approved browser origins for private proxy refresh. Add proxy smoke tests and bound service resources.
- Document preflight, staged acceptance, sanitized health checks, SQLite backup and restore, and release rollback. Keep the standalone simulation and simulated Pages preview. [Pi runbook](deploy/pi/README.md)

## Pre-v0.3.3 webcam review (proposed) — 2026-11-26

- Add a new-tab link to the official Whitewater gallery in the private Webcams tab. Retain the five individual resort image shortcuts and the licensed DriveBC junction view.
- Record browser policy, display terms, freshness and resource trade-offs for the four viewing options. [Webcam review](DATA_SOURCES.md#whitewater-webcam-integration-review-before-v033)

## v0.3.2.2 (proposed) — 2026-11-26

- Document the owner’s private household use decision and unresolved Whitewater site terms. Add opt-in numerical collection from the official snow report and mountain station tables, with two-hour and one-hour minimum request intervals.
- Populate reported 24-hour powder alerts, the seven-field snow report, lodge and summit conditions, and a timestamp-matched measured Nelson–lodge inversion comparison.
- Verify the five official resort webcam links and keep their imagery link-only. Preserve the licensed DriveBC view, model forecasts and their existing refresh controls.
- Add synthetic regressions and accessible wall and mobile screenshots for review.

## v0.3.2.1 (proposed) — 2026-11-26

- Add an optional, attributed DriveBC Highway 6 junction still to the private Overview and Webcams tabs, with automatic updates, saved selection, enlarged viewing, and stale and unavailable states. Keep resort sources link-only pending permission.
- Persist a six-batch UTC daily cap on early Open-Meteo requests through Refresh Data. Scheduled weather and eligible camera checks retain their own cadence and backoff.
- Verify live weather and the still in Chromium at 1920×1080 and 390×844. Keep live screenshots and caches outside GitHub.

## v0.3.2 (merged) — 2026-11-26

- Connect the existing dashboard to the loopback service for extended and short-range forecasts, measured Nelson CS temperature, forecast snow and inversions, and multiple derived GFS freezing levels.
- Add validated same-origin manual refresh, per-source outcomes and a server-side cooldown. Keep automatic scheduling, source backoff and successful cache entries.
- Preserve the static simulation and add integration regressions for layouts, stale data, partial failure and recovery.

## v0.3.1 (merged) — 2026-11-26

- Add the private Python and SQLite collector and loopback API with ECMWF IFS HRES 9 km, separately labelled HRDPS Continental 2.5 km, and measured ECCC Nelson CS temperatures.
- Add a derived NOAA GFS pressure-profile product that preserves multiple bracketed freezing levels. Validate provider responses and keep Whitewater and Southridge collection disabled.
- Add persistent scheduling and provider cooldowns, bounded cache history, checked online backup and restore, and service regressions.

## v0.3.0 live source validation (proposed) — 2026-11-26

- Verify live lodge and valley forecasts and Nelson CS temperatures. Accept the observed all-null freezing-level response while retaining strict units and shape checks. Report separate valid-time counts for overlapping Nelson SWOB products.
- Add manual forecast model selection and document live GEM and ECMWF coverage, Southridge ridge observations and Redfish Creek snowpack exports. Whitewater automated collection remains disabled.

## v0.3.0 proof of concept (merged) — 2026-11-26

- Document Whitewater report and station evidence, access restrictions, regional alternatives, Open-Meteo forecast semantics and the ECCC Nelson CS candidate.
- Add an isolated Python/SQLite prototype with synthetic source contracts, rolling snowfall calculations, freshness and failure handling, history and checked SQLite snapshots. Add manual open-data diagnostics and reproducible tests. Live probes were blocked by workspace egress during this milestone.

## Architecture decision — 2026-11-26
- Approved single private household deployment on the Raspberry Pi. Existing public simulation is temporary design feedback; no second live environment. Prioritize source validation including Whitewater numerical observations, then local service/cache and private deployment. No code or infrastructure changes in this decision.

## v0.2.1 (merged and published) — 2026-11-26
- Add compact simulated skiing implications for observed and forecast inversion signals, including temperature-dependent softening potential and evidence-gated sky contrast.
- Clarify forecast breakdown and atmospheric-profile limitations in Info. Verify the 1920×1080 overview without scrolling and extend mobile and sky-comparison regression coverage.

## v0.2 (merged and published) — 2026-11-26

- Add a simulated valley temperature inversion scenario, schematic cold valley air on the mountain profile, and a temperature-by-elevation plot comparing Nelson valley and Whitewater Lodge.
- Display separate simulated observed and forecast inversion indicators. Show illustrative onset, duration, and dissipation when comparable forecast samples support them.
- Document the provisional interpretation thresholds in Info and extend Chromium regression coverage for inversion signals, timing, and wall and mobile layouts.

## v0.1.1 (merged) — 2026-11-26
- Retain webcam selection focus and provide 44×44 CSS px minimum camera targets.
- Fit powder rings, the seven-day forecast strip and avalanche tiles on narrow layouts.
- Distinguish High and Extreme simulated avalanche accents and match the powder alert treatments to the Info tiers. Keep higher-tier glow static with reduced motion.
- Add reproducible Chromium regression checks for the simulated dashboard.

## v0.1 — 2026-11-24
- Baseline single-file static demonstration with five tabs, five simulated scenarios, freezing-level schematic, powder alerts and outlook, webcam placeholders/links, illustrative avalanche and Nordic panels, and Info controls.
- Repository starter package adds development documentation only; original index.html and README.md bytes preserved. No new feature or live feed implemented. GitHub publication and production deployment not verified.
- Historical prototype review reported browser testing; no new browser tests executed for this documentation-only package.

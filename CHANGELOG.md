# Changelog

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

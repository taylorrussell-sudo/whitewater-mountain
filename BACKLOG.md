# Development backlog

## Next
- [x] Publish unchanged v0.1 demo for family review; GitHub Pages deployment succeeded and user confirmed website loads.
- [ ] Complete physical-device acceptance checks and family design feedback; Chromium desktop and narrow viewport checks were performed during the baseline audit.
- [x] Codex read-only baseline audit completed and independently reviewed; [timestamped report](handoffs/2026-11-26_0845_baseline-audit.md). Browser tests reported by Codex, not independently rerun.
- [x] v0.1.1 baseline improvements implemented for review: restore webcam keyboard focus, correct narrow-screen overflow and camera touch target sizing, complete simulated avalanche severity styling, align powder alert styling with Info, and add lightweight reproducible regression tests. Preserve all existing scenarios and verify wall and mobile layouts.
- [x] v0.2 temperature inversion graphics implemented for review. Added a simulated inversion scenario, schematic cold valley air, temperature-by-elevation plot, separate observed and forecast comparisons, and sample-bracketed forecast timing. Info documents the approved provisional dashboard thresholds and limitations.
- [ ] Validate Whitewater source permissions, exact elevations and reliable field extraction; verify camera timestamps, Nordic data and DriveBC source. Confirm Avalanche Canada region/API and expiry semantics before displaying real ratings.
- [ ] Live data architecture: independent source adapters, cache, provenance, freshness, error handling; validate model snowfall and rolling windows. No public Pi exposure.
- [ ] Family feedback, release acceptance, Pi integration and verified encrypted backup/recovery coverage.

## Later
- Forecast snowfall timing relative to lift opening; weekend preview; calibrated qualitative powder outlook and model agreement; local season snowfall history and forecast accuracy (subject to permissions); rain-on-snow detection; weather inversions from validated real data.
- Summer mode: elevation-specific weather, rainfall, alpine snow, AQHI, PM2.5, wildfire smoke forecast/trends, relevant hazards, webcams; hiking and biking information optional, no dependency on a bike trail feed. Deferred.

# Development backlog

## Next
- [ ] Publish unchanged v0.1 demo for family review; verify published URL and test on phone and desktop.
- [ ] Codex read-only baseline audit (first task): report code structure, risks, reproducible tests, missing coverage, and inversion feature proposal. No edits.
- [ ] First controlled feature: special inversion graphics. Add a valley cold-air band to the elevation profile, temperature-by-elevation visualization, distinct subtle inversion alert, temperature differential and illustrative onset/dissipation when data supports it. Distinguish observed from forecast; a simple warmer-upper-station comparison is an inversion indicator, not proof of vertical atmospheric structure. Use simulated scenarios initially, document logic and limitations in Info, test regression and reduced motion. Exact thresholds not yet approved.
- [ ] Validate Whitewater source permissions, exact elevations and reliable field extraction; verify camera timestamps, Nordic data and DriveBC source. Confirm Avalanche Canada region/API and expiry semantics before displaying real ratings.
- [ ] Live data architecture: independent source adapters, cache, provenance, freshness, error handling; validate model snowfall and rolling windows. No public Pi exposure.
- [ ] Family feedback, release acceptance, Pi integration and verified encrypted backup/recovery coverage.

## Later
- Forecast snowfall timing relative to lift opening; weekend preview; calibrated qualitative powder outlook and model agreement; local season snowfall history and forecast accuracy (subject to permissions); rain-on-snow detection; weather inversions from validated real data.
- Summer mode: elevation-specific weather, rainfall, alpine snow, AQHI, PM2.5, wildfire smoke forecast/trends, relevant hazards, webcams; hiking and biking information optional, no dependency on a bike trail feed. Deferred.

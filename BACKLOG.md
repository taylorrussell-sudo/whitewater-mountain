# Development backlog

## Next
- [x] Publish unchanged v0.1 demo for family review; GitHub Pages deployment succeeded and user confirmed website loads.
- [ ] Complete physical-device acceptance checks and family design feedback; Chromium desktop and narrow viewport checks were performed during the baseline audit.
- [x] Codex read-only baseline audit completed and independently reviewed; [timestamped report](handoffs/2026-11-26_0845_baseline-audit.md). Browser tests reported by Codex, not independently rerun.
- [x] v0.1.1 baseline improvements implemented for review: restore webcam keyboard focus, correct narrow-screen overflow and camera touch target sizing, complete simulated avalanche severity styling, align powder alert styling with Info, and add lightweight reproducible regression tests. Preserve all existing scenarios and verify wall and mobile layouts.
- [x] v0.2 temperature inversion graphics implemented for review. Added a simulated inversion scenario, schematic cold valley air, temperature-by-elevation plot, separate observed and forecast comparisons, and sample-bracketed forecast timing. Info documents the approved provisional dashboard thresholds and limitations.
- [x] v0.2.1 inversion ski context implemented and verified in Chromium at wall and mobile viewport sizes. Physical-device acceptance remains open above.
- [x] Architecture direction approved: one private household application, one codebase, one intended live Pi deployment. Public simulated Pages is temporary feedback only; no dual live environments.
- [x] v0.3.0 proposal: review Whitewater snowfall, snow depth and hourly weather, investigate alternatives, verify documented Open-Meteo and ECCC contracts and prove Python/SQLite cache and restore with synthetic data. [Evidence and live validation gaps](DATA_SOURCES.md) · [Proof of concept](poc/README.md)
- [x] Run the Open-Meteo lodge and valley and ECCC Nelson CS live probes, compare GEM and ECMWF point coverage, and verify live data access for Southridge and Redfish Creek. [Live evidence and source recommendations](DATA_SOURCES.md)
- [ ] Obtain Whitewater written terms and timestamp/station details before automated collection. Confirm Southridge caching, display, cadence and retention terms before use. Prefer the catalogue-listed Redfish Creek SWE and depth resources and confirm station-specific quality, cadence and revisions before recurring collection.
- [ ] Validate forecast performance over multiple weather events against comparable measured records where permitted. Compare the derived GFS freezing-level profile with independent evidence over multiple events and verify run identifiers before using model-run freshness.
- [x] v0.3.1 implemented for review. The private [Python/SQLite service](mountain_service/README.md) provides independent IFS, HRDPS, Nelson CS and GFS freezing-profile adapters, bounded retention, backup/restore and a loopback API. Development verification only.
- [x] v0.3.2 implemented for review. Integrate IFS, HRDPS, Nelson CS and GFS with the private dashboard, and add scheduler-driven Refresh Data. Keep static simulation for design regression. [Service guide](mountain_service/README.md)
- [ ] v0.3.3: approved private Pi deployment, LAN/family access, optional authenticated private remote access, resource and boot checks, backup-source amendments and targeted recovery verification. Retire public Pages with approval after private hosting is verified and before public live data access. No changes to existing services or public Funnel.
- [ ] v0.4: verify camera access/display rights and timestamps, Nordic and DriveBC data, Avalanche Canada region/API and expiry semantics before real ratings. Family/physical-device acceptance and wall navigation integration.

## Later
- Forecast snowfall timing relative to lift opening; weekend preview; calibrated qualitative powder outlook and model agreement; local season snowfall history and forecast accuracy (subject to permissions); rain-on-snow detection; weather inversions from validated real data.
- Summer mode: elevation-specific weather, rainfall, alpine snow, AQHI, PM2.5, wildfire smoke forecast/trends, relevant hazards, webcams; hiking and biking information optional, no dependency on a bike trail feed. Deferred.

# v0.3.0 live data source validation

## Completion timestamp / task / objective

Completed at `2026-11-26T15:07:48-07:00` (America/Vancouver). Continue the v0.3.0 source review with live Open-Meteo and ECCC probes, compare named forecast models, and verify Southridge and Redfish Creek access and suitability.

## Repository / branch / PR URL / commit SHA

`taylorrussell-sudo/whitewater-mountain`, branch `fix/v0.3.0-live-source-validation`, based on `bc7407acc8251c5c1d3253f74366e90eddf2b0c7`. Implementation, tests and source evidence are in `a4d8b8156d1c7c6670d86e01cc3ceb58857ebef0`. This report and the latest pointer follow in the same branch. [Pull request #7](https://github.com/taylorrussell-sudo/whitewater-mountain/pull/7)

## Version and status

The live-validation follow-up is proposed in an open PR. The Python/SQLite proof of concept is already on main. The existing public dashboard serves the v0.2.1 simulation. This task made no merge or deployment.

## Changes and decisions

- The existing lodge and valley probes keep GEM Global as their default. Open-Meteo returned an all-null freezing-level series with unit `undefined`. The adapter accepts this combination for that field and retains strict units and array checks. The CLI accepts one named model per request and reports hour continuity and populated-field counts. [Probe reference](../poc/README.md)
- The Nelson probe retains hourly AUTO and AUTO-minute records with separate IDs, reports distinct valid times, and uses the latest processing time when the newest valid time is shared. Observation, processing and retrieval times are independent.
- Trial IFS HRES 9 km for the seven-day outlook, operational GEM HRDPS 2.5 km for the next day, and GEM RDPS or GDPS for separately labelled comparison. Experimental HRDPS West 1 km is supplemental. Keep model identity and valid times when comparing sites.
- Southridge is a nearby ridge temperature and wind candidate. Its recurring caching, display and retention permissions remain open. Redfish Creek's catalogue-listed exports are the preferred regional snowpack source. Whitewater automated collection remains disabled pending written clarification. [Source evidence and access terms](../DATA_SOURCES.md)

## Tests run, environment and results

- Used the managed development environment's public egress through its configured proxy after the command sandbox could not reach the proxy bridge. The three original probes initially produced two forecast unit failures and a fresh Nelson CS result. All three passed after the fix. Both GEM Global points had 169 aligned hourly slots, complete snowfall windows through 72 hours and no freezing-level values. Nelson CS had six usable rows, five distinct valid times and a newest observation about 37 seconds old.
- Compared seven forecast models at both locations using matching UTC hours. IFS 9 km, IFS 0.25°, AIFS Single and GEM Global populated all 169 hours. GEM RDPS populated 81 hours, HRDPS 2.5 km populated 45, and experimental HRDPS West 1 km populated 39. These are live snapshot counts. IFS 9 km and RDPS supplied complete 72-hour snow windows in this sample, and both HRDPS models supplied only 24-hour totals.
- Confirmed a 23-row hourly Southridge API result and the Redfish Creek station CSV and catalogue-listed depth and SWE exports. A 120-feature ECCC diagnostic exceeded the 512 KiB cap. A 24-feature sample fit and verified one-minute valid times and overlapping hourly data. The regular six-feature probe limit remains in place.
- `python3 -B -m unittest discover -s poc/tests -v` passed all 16 tests, including both new regressions. `git diff --check` passed. The dashboard and browser test files were byte-identical to main. Prior browser and standalone synthetic demo/restore verification carried forward from the v0.3.0 handoff.

## Remaining limitations and implications

The live checks establish payload compatibility and point coverage at review time. Model skill, exact initialization time in the ordinary Forecast API, freezing level, longitudinal station cadence and seasonal accuracy remain unverified. Regional or ridge observations cannot fill measured Whitewater snowfall and lodge fields. Confirm source-specific permissions, quality and retention before scheduling collection. Validation used Python's standard library and kept upstream payloads out of the repository. Private hosting, source scheduling, cache retention and production backup/recovery remain separate milestones.

## Rollback, next work and approvals

Close PR #7 to keep main at its current implementation. If a future merge is approved, use a reviewed revert to roll it back. Continue the v0.3.1 local service design with Open-Meteo and a bounded Nelson CS cache, then verify sources over several events. Confirm Whitewater and Southridge terms, Redfish Creek quality and update policy, and a freezing-level method before enabling the respective data. Merge, frontend live integration, Pi deployment, private networking, production backup changes and Pages retirement require separate approval. [Backlog](../BACKLOG.md)

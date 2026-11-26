# Whitewater Mountain v0.1 baseline audit

## Completion timestamp / task / objective

Handoff finalized at `2026-11-26T08:45:21-07:00` (America/Vancouver). The task was to audit the v0.1 dashboard read-only, check the documented workflow, and propose the first temperature inversion feature.

## Repository / branch / PR URL / commit SHA

`taylorrussell-sudo/whitewater-mountain`. The cloud audit ran on `work` at `265965d1759117af5fcbad9d43593737302d1d71`. A read-only `git ls-remote` confirmed that GitHub's default branch, `main`, pointed to the same commit. The audit itself required no pull request. This report is delivered on `docs/baseline-audit-handoff`. [Handoff pull request](https://github.com/taylorrussell-sudo/whitewater-mountain/pulls?q=is%3Apr+head%3Adocs%2Fbaseline-audit-handoff)

## Version and status

Audited committed v0.1. The inversion feature is a proposal. GitHub Pages publication and Pi deployment were outside the audit.

## Changes and files affected

The audit left the checkout clean. I read [AGENTS.md](../AGENTS.md), [README.md](../README.md), [REQUIREMENTS.md](../REQUIREMENTS.md), [BACKLOG.md](../BACKLOG.md), [DATA_SOURCES.md](../DATA_SOURCES.md), [CHANGELOG.md](../CHANGELOG.md), and [HANDOFF_TEMPLATE.md](../HANDOFF_TEMPLATE.md), and reviewed [index.html](../index.html). The browser harness stayed outside the checkout. The follow-up handoff adds this report and [LATEST.md](LATEST.md) and updates the agent instructions and template. Application files are untouched.

## Design decisions and deviations from requirements

The dashboard uses one static HTML file with inline styles, simulated scenario data, snow calculations, SVG renderers, and native form controls. The app has no build step, runtime package dependencies, or backend. [Application source](../index.html)

| Requirement area | Baseline coverage and gaps |
| --- | --- |
| Overview and elevation | Five tabs, a schematic elevation profile, a scenario-dependent 0°C line, and a seven-day upper-mountain outlook are present. The demo shows lodge, summit, and Nordic temperatures at individual locations. A temperature-by-elevation forecast and a valley inversion view are absent. |
| Snow and powder | Simulated overnight, 24-hour, and season snowfall, snowpack, separate reported and forecast alerts, and 24/48/72-hour forecasts are present. Reported 48-hour, three-day, and seven-day totals and station-specific winds are absent. Thresholds are fixed and demonstrated in Info. Powder interpretation is scenario-authored and forecast confidence is labeled uncalibrated. |
| Webcams, avalanche, Nordic, and roads | Camera selection and schematic images work. Three avalanche elevation bands carry explicit simulation labels and link to the official bulletin. Live imagery and timestamps, official region and expiry handling, grooming, and road data remain deferred. |
| Layout, controls, and methodology | Overview fit the tested 1920×1080 viewport in all five scenarios. Themes, reduced motion, and Info controls worked. Narrow-width overflow and a keyboard focus defect remain. Info explains the simulation and data provenance. |

## Tests run, environment and results

- **Chromium 156 on Linux over loopback HTTP.** The HTTP response matched the checkout's `index.html` byte for byte. Checks passed for all five tabs and scenarios, the Overview-to-Powder shortcut, all six camera choices and their outbound link targets, both snowfall charts, freezing-level renders, cumulative totals, alert timing and severity, light/dark/auto themes, system theme changes, both Info sliders, reduced motion, and reload defaults.
- **Snowfall calculation checks.** All 12 tested threshold boundary values passed. Incoming storm showed a 35 cm peak from +24 to +48 hours and 58 cm over the first 72 hours. Extra fixtures verified that equal peaks select the earliest window and that +48 hours is included as the final eligible start.
- **Layout and keyboard.** At 1920×1080 the lowest Overview card ended at 1037 px across all five scenarios. Widths of 320, 390, and 768 CSS px were sampled. Space activated navigation and camera buttons. Camera selection reproduced the focus loss below.
- **Limitations.** Browser policy blocked `file://` navigation, so the checks used HTTP. The checked flows produced no uncaught page exceptions or off-origin page requests. Physical touchscreens, other browser engines, screen readers, and external link availability were outside the checks.

To reproduce, run `python3 -m http.server 8000 --bind 127.0.0.1` from the checkout and open the served `index.html` in a local browser. Choose **Incoming storm** and compare the peak and totals above. Use a 320 px viewport to inspect the powder cards and seven-day strip. Focus the **Summit** camera button with the keyboard and press Space to reproduce the focus loss.

## Remaining bugs, assumptions, data-source and safety limitations

1. **Keyboard focus drops on webcam selection.** Activating Summit with Space updated the camera and pressed state, then moved focus to `BODY`. `renderCam()` replaces the camera buttons. Retain the buttons or restore focus to the selected button.
2. **Narrow layouts have internal overflow.** At 320 CSS px with desktop-style scrollbars, the powder rings exceeded their cards' inner widths and the Overview forecast strip exceeded its container by 9 px. The strip fit with mobile emulation at the same nominal width. Camera chips measured 40 px high, compared with 44 px for the main buttons.
3. **Severity styling is inconsistent.** The simulated `4 · High` avalanche tile uses the neutral border because only levels 1–3 have severity colors. Info describes distinct effects at 5 cm and 10 cm, while Chromium computed the same glow for both. Text ratings and tier calculations were correct.
4. **The baseline has no committed automated checks.** Scenario fixtures, thresholds, rendering, and event handlers share dense lines. Threshold boundaries appear in JavaScript and the Info table, with styling keyed to the resulting tiers. Prioritize tests for snowfall windows, tier boundaries, camera focus, reduced motion, and narrow and wall-size layouts.

The 24-hour snow forecast is distributed uniformly within each simulated daily bin. These inputs cannot validate within-day storm timing. Station elevations, source availability, and redistribution permissions remain unverified. Powder and inversion indicators carry no avalanche safety meaning. [Data sources](../DATA_SOURCES.md)

## Dependencies / security / privacy / backup implications

The proposed simulation fits the existing static application and requires no additional runtime dependencies, credentials, or external data. Backup and recovery verification was outside the audit.

## Rollback method

The read-only audit produced no application changes to roll back. The audited SHA identifies the baseline. If the handoff documentation is merged and later needs to be undone, revert its pull request while preserving other historical handoffs.

## Next recommended task / backlog changes

**Proposed temperature inversion implementation**

1. **Add a simulated inversion scenario.** Preserve the five existing fixtures. Give the new scenario comparable valley and upper-station temperatures, station names, provisional elevations, and a shared valid time. Label simulated observations and simulated forecasts explicitly and keep their samples separate. The current fixtures lack a Nelson valley temperature and a paired hourly station series.
2. **Derive the station difference.** Compute upper temperature minus valley temperature from contemporaneous values of the same data type. Display the signed difference in °C and name both stations. Apply an approved threshold and handle equal, missing, or time-mismatched samples explicitly. Show illustrative onset or dissipation only when consecutive comparable forecast samples bracket a transition.
3. **Render the profile and alert.** Add a subtle, static cold-air band to the mountain schematic and keep the existing 0°C line visually distinct. Add a compact temperature-by-elevation chart with named sample points and a text equivalent. Explain in Info that warmer air at an upper station suggests an inversion, while the depth and shape of the cold-air layer remain unknown. Keep the inversion indicator independent of powder and avalanche.
4. **Verify the change.** Test normal cooling with elevation, inversion, exact-threshold and equal values, missing and mismatched samples, onset, and dissipation. Repeat the dashboard smoke checks and verify keyboard focus, all themes, reduced motion, and layouts at narrow widths and 1920×1080. Update the applicable requirements, backlog, and changelog with the approved behavior. [Backlog](../BACKLOG.md)

## User approval still required

Feature implementation and the alert threshold remain pending approval. Publication and Pi integration remain separate decisions.

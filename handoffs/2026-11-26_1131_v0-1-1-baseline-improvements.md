# Whitewater Mountain v0.1.1 baseline improvements

## Completion timestamp / task / objective

Completed at `2026-11-26T11:31:10-07:00` (America/Vancouver). Implement the v0.1.1 accessibility, layout, and styling fixes from the [baseline audit](2026-11-26_0845_baseline-audit.md) and add regression checks.

## Repository / branch / PR URL / commit SHA

`taylorrussell-sudo/whitewater-mountain`, branch `fix/v0.1.1-baseline`, targeting `main`. Implementation and tests are in commit `fefbb389a89f005eb56aec59cb421ef2eb7b2d78`. This report and the latest pointer are in a follow-up commit on the same branch. [Pull request #2](https://github.com/taylorrussell-sudo/whitewater-mountain/pull/2)

## Version and status

Proposed v0.1.1, committed on the feature branch for review. Merge, GitHub Pages publication, and Pi deployment remain pending separate approval.

## Changes and files affected

- Keep all six webcam buttons mounted so keyboard activation preserves focus and the next Tab follows the camera order. Keep each camera button and source link at least 44×44 CSS px.
- Keep powder rings within their cards. Reflow the seven-day strip to two rows at 420 CSS px and below. Let avalanche tiles wrap when the card is too narrow for all three labels.
- Give simulated High and Extreme ratings distinct borders in both themes. Give the 5 cm powder tier a static accent, the 10 cm tier a soft glow, and the 15, 25, and 40 cm tiers increasingly prominent glow. Keep a static glow when system or dashboard reduced motion is enabled. [Dashboard](../index.html)
- Document the prototype version, requirements, source status, and backlog. Add the browser tests and record how to run them. [README](../README.md) · [Requirements](../REQUIREMENTS.md) · [Data sources](../DATA_SOURCES.md) · [Changelog](../CHANGELOG.md) · [Backlog](../BACKLOG.md) · [Tests](../tests/test_dashboard.py)

## Design decisions and deviations from requirements

The powder styling preserves the existing reported blue solid and forecast violet dashed rings. Higher tiers remain slow pulses. The avalanche color accents supplement the existing numeric and text ratings. An Extreme tile is covered by a test fixture. All five dashboard scenarios, their camera URLs, and the rolling-window calculation match v0.1.

## Tests run, environment and results

- Eight browser tests passed in 9.561 seconds on Debian Linux, Chromium 156.0.8078.79, Python 3.12, and Playwright 1.62.0. The suite served the static page over loopback and exercised all tabs and scenarios, camera keyboard and link behavior, simulated phone taps and target dimensions, powder thresholds and forecast windows, alerts, charts, themes, reduced motion, and both Info sliders.
- All five scenarios fit the 1920×1080 wall overview. Desktop-style scrollbar checks passed at widths of 320, 390, 420, 421, 640, 641, 768, and 1024 CSS px across all tabs. The first run found additional avalanche-tile overflow at 320 and 641 CSS px. The published branch includes the fix.
- An isolated run against the v0.1 base commit reproduced failures in five test methods covering keyboard focus, camera sizing, overflow, avalanche coloring, and powder styling. The other three methods passed. `git diff --check` also passed.
- The default command sandbox denied loopback socket creation. The approved browser test run used a local-only server. External source links were checked by destination and left unopened. Physical devices, assistive technologies, and other browser engines were outside this run. [Reproduction steps](../README.md#automated-regression-checks)

## Remaining bugs, assumptions, data-source and safety limitations

Physical touchscreen acceptance and family review remain open. Conditions, avalanche ratings, and camera artwork are simulated. Official bulletin validity and data-source permissions remain unverified. Temperature inversion graphics and live data integration remain in the backlog. [Data sources](../DATA_SOURCES.md) · [Backlog](../BACKLOG.md)

## Dependencies / security / privacy / backup implications

Playwright and Chromium are development test dependencies. The application remains self-contained static HTML with its existing external reference links. There are no runtime libraries, new data requests, credentials, or backup changes.

## Rollback method

Before merge, close the PR to keep `main` at the v0.1 baseline. If the changes are merged later, revert the application and documentation changes through a new PR while retaining the historical handoff. The base revision for this change is `720399c29cdab2007891fd72d2617be0d65a00b4`.

## Next recommended task / backlog changes

Review v0.1.1 and complete the tracked physical-device and family acceptance checks. The proposed inversion feature follows the baseline work and still needs its threshold and behavior approved. [Backlog](../BACKLOG.md)

## User approval still required

Merge, publishing, production integration, and any backup changes require separate approval.

# v0.4.0 regression verification

Development verification used Debian 13 x86-64, Python 3.12.14, system Python 3.13.5, Playwright 1.62.0, Chromium 156.0.8078.79 and Nginx 1.26.3. The baseline was a scratch checkout of `6ee2cf3d6def76e881f3755a1dde05f04e03c1d5`. Test upstreams and preview scenarios used invented data on loopback.

| Suite | v0.3.4 baseline | v0.4.0 candidate review |
| --- | ---: | ---: |
| Browser regression | 17 passed | 25 passed |
| Service, scheduler and Nginx ingress | 28 passed | 31 passed |
| Proof of concept | 16 passed | 16 passed |
| Pi utility with scratch installation and simulated units | — | 16 passed |

Reproduce the suites from the repository root with Playwright, Chromium and an existing Nginx executable. Set the executable paths for your development machine. The Nginx test renders temporary listeners and uses a source-disabled backend.

```sh
CHROMIUM_PATH=/usr/bin/chromium python -B -m unittest discover -s tests -v
NGINX_PATH=/usr/sbin/nginx python -B -m unittest discover -s mountain_service/tests -v
python -B -m unittest discover -s poc/tests -v
python -B -m unittest discover -s deploy/pi/tests -v
```

- Chromium exercised the 1920 × 1080 wall, 390 × 844 and 430 × 932 touch views and a responsive sweep down to 320 CSS px. Coverage includes all five tabs, six static scenarios, keyboard focus, touch targets, theme and motion settings, loading and recovery, stale values, all camera links, selected-image-only gallery loading and the unchanged DriveBC refresh path.
- The separate resort timing preview uses same-origin fixture transport. Chromium clock and response mocks exercise a 15-minute minimum per selected camera, visibility and viewport gates, exact unchanged fixture paths, reuse of the decoded image in the enlarged view, and recovery after a simulated 503. The default private page continues to show synthetic stills on selection without scheduled image requests.
- A separate Chromium check used the actual loopback preview with a one-second fixture cache lifetime and advanced the browser clock to the next 15-minute check. The first request returned 200. The next sent the unchanged URL with `If-None-Match` and rendered the cached frame after a 304. The demo uses HTTP/1.1 for ETag validation. In a separate HTTP/1.0 test, Chromium reloaded an expired ETag-only response without a validator.
- Scheduler coverage includes the existing cadence of all seven integrations, early weather reservations across UTC midnight and restart, a six-batch cap, provider spacing, cooldown and durable stops, and independence for due checks and eligible DriveBC checks. Synthetic responses exercise bounded transport and failure handling. SQLite checks exercise a populated pre-budget cache, retention, WAL backup and restore, and a second collector process blocked by the database lock.
- Real Nginx loopback checks render the private LAN template and simulate an authenticated proxy's expected HTTPS Host and Origin. They cover allowed and denied clients and Hosts, empty same-origin refresh POSTs, denied foreign preflights, response security headers, private caching of allowlisted WebP fixtures and 404 for an unknown fixture. The firewall template and unit ordering were checked statically.
- A separate scratch exercise seeded a database with the v0.3.4 code, including a synthetic forecast, a recent observation, provider cooldown and four used refresh batches. v0.4.0 opened and served it with collection disabled, then v0.3.4 reopened it as a rollback check. Both served healthy and reported two remaining batches. Weather and budget reads were identical at a fixed analysis time, with SQLite integrity and foreign-key checks passing.
- The Pi utility suite uses disposable Git history, releases, configuration backups and simulated units. It covers preflight, pinned release content, evidence checks, state preservation, bounded HTTP health, interruption, rollback, retry, and failed recovery reporting.

## Resource observations

- The six original WebP fixtures total about 219 KiB. Each 704 × 352 image takes about 0.95 MiB for one decoded 32-bit pixel buffer before browser overhead. The default resort gallery loads a selected still with normal browser caching. The timing preview retains up to one decoded image for each sampled camera. Browser checks observed only same-origin fixture requests. The DriveBC adapter's single bounded, memory-only frame and existing schedule continue separately.
- In the initial wall-view comparison with timing preview disabled, Chromium baseline and candidate JavaScript heap measurements after requesting garbage collection were 1,747 and 1,749 KiB on initial Overview, 2,558 and 2,562 KiB after 54 camera selections, and 2,562 and 2,564 KiB in Webcams. All five resort samples transferred once each and subsequent selections reused the browser cache. A 16-second idle sample showed only the existing weather and refresh-status reads. Native and decoded image memory fall outside the JavaScript heap metric.
- One x86-64 RSS sample of the fresh-snow preview backend after 30 loopback API reads measured approximately 23.7 MiB on the baseline and 24.0 MiB on the candidate. The candidate also served five fixture stills in that sample. This is a development process measurement. ARM64, Chromium aggregate memory and a day of coexistence with the other Pi applications remain physical acceptance checks.

Browser results are Chromium viewport and touch emulation over loopback HTTP. The managed browser blocked `file://` navigation. Physical wall touch, iPhone Safari, Pi boot order, kernel firewall behavior, production LAN isolation, encrypted backup decryption and off-device recovery remain operator acceptance gates. [Pi runbook](../../deploy/pi/README.md) · [Synthetic visual review](README.md)

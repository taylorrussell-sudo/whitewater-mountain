# v0.4.0 Whitewater webcam follow-up

## Completion and status

Completed at `2026-11-28T06:35:58-07:00` (America/Vancouver). Reassess direct browser viewing of the five current resort stills inside the private household dashboard. The owner authorized bounded checks of public URLs and reversible development under ambiguous terms, subject to clear usage prohibitions and access restrictions.

Repository `taylorrussell-sudo/whitewater-mountain`, branch `release/v0.4.0-candidate`. Follow-up commit `8c6d0afa0a0ecb3761a8f521760c12bbce8a2096`. v0.4.0 remains a review candidate. PR #15 remains unmerged. Production was outside the scope of this work. [Pull request #15](https://github.com/taylorrussell-sudo/whitewater-mountain/pull/15) · [Sprint handoff](2026-11-27_2319_v0-4-0-candidate.md)

## Decision and evidence

- Each official JPEG returned HTTP 200 to a single HEAD request and advertised ten-minute caching, ETag and Last-Modified. Those checks used no image bodies. They establish public URL availability at the check time. Conditional anti-hotlink behavior and actual capture times remain unverified.
- Opening an official link is ordinary viewing at the resort origin. Direct browser embedding would avoid server-side collection, storage and public republication. It would still render the same resort gallery content on the dashboard's own page. Section 2 expressly restricts display and gives no household exception. The terms leave exact cross-host scope unspecified, while the resort publishes these exact files as its gallery imagery and no separate camera-host display policy was found. The operational decision is to keep live imagery on official top-level links. [Resort terms](https://whitewatermountainresort.com/terms-of-use/) · [Full evidence and alternatives](../review/v0.4.0/whitewater-webcam-research.md)
- The official gallery's `X-Frame-Options: SAMEORIGIN` prevents a cross-origin iframe, and no supported embed or licensed alternate route surfaced. The official live gallery can sit beside Mountain using native desktop window controls. A supported route that permits this use would reopen in-dashboard activation.

## Implemented and verified

- The optional loopback `--resort-stills-demo` exercises one visible selected sample per 15-minute interval per camera, with no requests in hidden tabs or for off-screen views. The enlarged view reuses the decoded frame. The demo displays browser load time, keeps the URL stable, respects the browser cache and retains no image history. Its fixtures and necessary blob policy are limited to the review launcher. The installed gallery retains its official links and synthetic samples. DriveBC and production ingress policy carry forward. [Preview and wall/phone screenshots](../review/v0.4.0/README.md#resort-still-refresh-demo)
- Local Chromium showed that replacing an image element at the same URL can reuse decoded pixels even after HTTP cache expiry. The fixture's same-origin browser fetch path allowed genuine revalidation. Against the HTTP/1.1 review launcher with a shortened cache lifetime and an advanced browser clock, Chromium sent `If-None-Match` at the next 15-minute interval and rendered the resulting 304 without another image body. A future external fetch transport would require a suitable CORS response. Actual resort image display and refresh were unverified.
- All 88 regression tests passed on the development host, including 25 Chromium, 31 service/Nginx, 16 proof-of-concept and 16 simulated upgrade tests. The four new browser checks use synthetic fixtures and cover default isolation, selection and enlargement, cadence and visibility, and mobile failure recovery. [Detailed QA](../review/v0.4.0/qa.md)

## Recovery and remaining work

Omit `--resort-stills-demo` to return to the standard preview. A reviewed revert can withdraw the branch changes. The v0.3.4 physical-device and encrypted recovery gates remain pending. Review the existing rollout sequence before authorizing a future release. For live resort imagery, a route with documented display permission and verifiable cache behavior is still needed. [Release acceptance sequence](2026-11-27_2319_v0-4-0-candidate.md#production-acceptance-sequence-after-owner-approval)

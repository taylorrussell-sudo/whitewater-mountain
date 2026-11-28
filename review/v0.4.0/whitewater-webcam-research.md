# Whitewater webcam integration review

Reviewed November 28, 2026. This review checked the resort's published gallery, terms and seasonal notices. Historical image measurements come from November 26–27. This sprint used one HTTPS HEAD request per published JPEG, with no still downloads or polling, and local browser fixtures. [Earlier camera observations](../../DATA_SOURCES.md#webcam-validation-in-v0321)

## Published camera routes

Whitewater's gallery lists a current still and a time-lapse for each camera. The still links below are public viewing destinations. The resort's gallery remains the viewing destination for time-lapses. [Official Whitewater webcam gallery](https://whitewatermountainresort.com/webcams/)

| Resort label | Official current still | Historical JPEG size | Historical update evidence |
| --- | --- | --- | --- |
| Lodge Camera | [Lodge](https://webcams.skiwhitewater.com/webcams/lodge/current.jpg) | 2304 × 1728 px | File modification time advanced five minutes. Offset-free EXIF clock was consistent with approximately UTC−07:00. |
| Summit Camera | [Summit](https://webcams.skiwhitewater.com/webcams/summit/current.jpg) | 2688 × 1512 px | ETag and file modification time stayed unchanged over eight minutes. Offset-free EXIF clock differed from HTTP file time by about eight hours. |
| Glory Camera | [Glory](https://webcams.skiwhitewater.com/webcams/glory/current.jpg) | 2688 × 1520 px | File modification time advanced in five-minute steps. Offset-free EXIF clock was consistent with approximately UTC−08:00. |
| Summit Weather Station | [Weather Stick](https://webcams.skiwhitewater.com/webcams/weatherstick/current.jpg) | 1600 × 1200 px | File modification time advanced in five-minute steps. Offset-free EXIF clock was consistent with approximately UTC−07:00. |
| Raven Camera | [Raven](https://webcams.skiwhitewater.com/webcams/raven/current.jpg) | 2688 × 1512 px | File modification time advanced in five-minute steps. Offset-free EXIF clock was consistent with approximately UTC−08:00. |

All five HEAD responses returned HTTP 200 with `image/jpeg`, `Cache-Control: public, max-age=600`, `ETag` and `Last-Modified`. None of the sampled still responses included `Access-Control-Allow-Origin`, `Cross-Origin-Resource-Policy`, `Content-Security-Policy` or `X-Frame-Options`. This is evidence of public access to the published image URLs. Conditional anti-hotlink behavior or other request-specific rules remain unverified. The gallery itself returned `X-Frame-Options: SAMEORIGIN`. [Official gallery](https://whitewatermountainresort.com/webcams/)

`Last-Modified` identifies the current file's modification time. A reliable capture timestamp requires a provider-defined field and time zone. Capture cadence and maximum delay remain unverified for all five cameras. [Earlier integration checks](../../DATA_SOURCES.md#whitewater-webcam-integration-review-before-v033)

The resort historically announced that its original webcam had come online for the season and reported a technical delay in another preseason. The five-camera gallery was listed while the resort published a shoulder-season closure. Present-day off-season availability and camera-specific schedules remain unverified. Opening hours alone do not establish camera status. [Historical season announcement](https://whitewatermountainresort.com/blog/wh2o-webcam-up-and-running/), [historical technical update](https://whitewatermountainresort.com/blog/where-art-thou-webcam/), [resort hours](https://whitewatermountainresort.com/hours-operation/)

## Display options

| Option | Decision and trade-off |
| --- | --- |
| Dashboard gallery with original synthetic stills, plus official links | Selected for v0.4.0. It supports review of selection, enlargement and image states while the resort continues to host live viewing. Only an explicit navigation to an official link contacts the resort's camera service. |
| Resort-provided integration | Prefer a documented still route or still-only widget whose terms permit this use. Public gallery and website searches found no third-party widget, shareable embed code or camera API. |
| Display the currently published JPEGs | Deferred. Direct browser `<img>` is technically plausible for the public URLs under a compatible browser policy. The resort's Section 2 expressly restricts display of its content. The dashboard currently permits same-origin images. |
| Frame the resort gallery | The earlier gallery response used `X-Frame-Options: SAMEORIGIN`. The dashboard also prohibits frames. These restrictions stay in effect. |

The prior Lodge sample was about 188 KiB for one JPEG and 3.1 MiB for the animated time-lapse. A single full JPEG transfer every 15 minutes across an always-visible 24-hour session is about 18 MiB per device at that sample size. Caching and revalidation may reduce transfer size. Loading only the selected still avoids multiplying the cost across five cameras. Enlarging an image can reuse the selected still. [Resource measurements and browser policy](../../DATA_SOURCES.md#whitewater-webcam-integration-review-before-v033), [resort terms, section 2](https://whitewatermountainresort.com/terms-of-use/)

## Direct image display in a private dashboard

Section 2 includes photos in the site's proprietary content and requires express written permission for specified uses of downloaded material. A separate sentence expressly includes display among the restricted uses. The published terms give no private household or noncommercial display exception. The terms introduce the agreement as applying to use of the site and do not enumerate the hosts within its scope. The legacy resort domain redirects to the current main site, and the official gallery directs visitors to the JPEGs under the legacy camera subdomain. The camera host root returned only a short Webcams label. Its conventional terms and robots routes returned 404, and public searches found no separate webcam reuse terms or licence. [Resort terms](https://whitewatermountainresort.com/terms-of-use/), [camera host](https://webcams.skiwhitewater.com/)

Following a resort-supplied link initiates viewing at the provider's own origin. Installing an image element in the dashboard initiates rendering of the resort image as part of the dashboard, even when the browser receives it directly from the resort and the app stores no copy. Given the explicit display restriction and the resort's role in publishing these five images, the sprint treats direct in-app rendering as requiring permission. The technical host distinction leaves the contractual reach across domains untested. The owner’s existing factual-measurement decision is scoped to weather values and provenance. [Household decision](../../REQUIREMENTS.md#whitewater-private-use-decision), [official resort gallery](https://whitewatermountainresort.com/webcams/)

A two-loopback-origin Chromium check confirmed that a normal image element displayed a synthetic image without a CORS allowance when the dashboard policy allowed it. A JavaScript fetch without CORS was rejected. Synthetic cases also confirmed that dashboard `img-src 'self'` or provider `Cross-Origin-Resource-Policy: same-origin` blocked cross-origin images, and gallery `X-Frame-Options: SAMEORIGIN` blocked framing. The check used only local fixtures. [HTML image element](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/img), [cross-origin resource policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Resource-Policy), [frame options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options)

In a separate Chromium test, replacing an image element at the same URL after HTTP cache expiry reused a decoded frame without a wire request. Changing only the fragment behaved the same way. A repeating timer and an image load event alone therefore give no assurance that an upstream frame was checked. The fixture demo instead uses a same-origin browser fetch with ordinary caching, then decodes the response for display and revokes its temporary object URL. An eligible external implementation of that transport would need a suitable CORS response. The sampled public JPEG headers did not advertise one. [Fixture preview and screenshots](README.md#resort-still-refresh-demo)

## Path to approved live stills

1. If the owner elects to pursue live display, ask the resort to confirm private household display permission, exact allowed origins and routes, attribution, refresh limits, supported time fields and time zones, seasonal behavior, and any caching restrictions. The resort's media page provides its contact for photo and video requests. [Resort media contact](https://whitewatermountainresort.com/media/)
2. Keep camera identity, official viewing links and selection unchanged when supplying an approved still to the gallery. Review the precise image origin and any security policy change as part of the approved integration. Use the existing gallery states for loading, stale and unavailable, and retain official links when a still fails.
3. Use ordinary browser caching and only request the selected camera while its view is visible, at most once per 15 minutes or slower if required. Keep resort stills out of service-side collection, SQLite and backups. Validate browser behavior with synthetic responses first. Use a correctly sourced capture timestamp when available, or explicitly state that capture time is unknown. Keep refresh time separate from capture time so an unchanged image cannot become fresh from a successful request alone.

DriveBC's attributed Highway 6 junction still has a separate licence and existing checks. Its provider cadence, cache, freshness and access rules continue to apply. [DriveBC source notes](../../DATA_SOURCES.md#webcam-validation-in-v0321)

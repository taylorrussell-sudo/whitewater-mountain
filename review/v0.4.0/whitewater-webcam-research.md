# Whitewater webcam integration review

Reviewed November 28, 2026. This review checked the resort's published gallery, terms and seasonal notices. The measurements below come from the repository's November 26–27 observations. This sprint's source review used public pages and made no repeated camera requests. [Earlier camera observations](../../DATA_SOURCES.md#webcam-validation-in-v0321)

## Published camera routes

Whitewater's gallery lists a current still and a time-lapse for each camera. The still links below are public viewing destinations. The resort's gallery remains the viewing destination for time-lapses. [Official Whitewater webcam gallery](https://whitewatermountainresort.com/webcams/)

| Resort label | Official current still | Historical JPEG size | Historical update evidence |
| --- | --- | --- | --- |
| Lodge Camera | [Lodge](https://webcams.skiwhitewater.com/webcams/lodge/current.jpg) | 2304 × 1728 px | File modification time advanced five minutes. Offset-free EXIF clock was consistent with approximately UTC−07:00. |
| Summit Camera | [Summit](https://webcams.skiwhitewater.com/webcams/summit/current.jpg) | 2688 × 1512 px | ETag and file modification time stayed unchanged over eight minutes. Offset-free EXIF clock differed from HTTP file time by about eight hours. |
| Glory Camera | [Glory](https://webcams.skiwhitewater.com/webcams/glory/current.jpg) | 2688 × 1520 px | File modification time advanced in five-minute steps. Offset-free EXIF clock was consistent with approximately UTC−08:00. |
| Summit Weather Station | [Weather Stick](https://webcams.skiwhitewater.com/webcams/weatherstick/current.jpg) | 1600 × 1200 px | File modification time advanced in five-minute steps. Offset-free EXIF clock was consistent with approximately UTC−07:00. |
| Raven Camera | [Raven](https://webcams.skiwhitewater.com/webcams/raven/current.jpg) | 2688 × 1512 px | File modification time advanced in five-minute steps. Offset-free EXIF clock was consistent with approximately UTC−08:00. |

The earlier JPEG responses advertised a 600-second cache lifetime. `Last-Modified` identifies the current file's modification time. A reliable capture timestamp requires a provider-defined field and time zone. Capture cadence and maximum delay remain unverified for all five cameras. [Earlier integration checks](../../DATA_SOURCES.md#whitewater-webcam-integration-review-before-v033)

The resort historically announced that its original webcam had come online for the season and reported a technical delay in another preseason. The five-camera gallery was listed while the resort published a shoulder-season closure. Present-day off-season availability and camera-specific schedules remain unverified. Opening hours alone do not establish camera status. [Historical season announcement](https://whitewatermountainresort.com/blog/wh2o-webcam-up-and-running/), [historical technical update](https://whitewatermountainresort.com/blog/where-art-thou-webcam/), [resort hours](https://whitewatermountainresort.com/hours-operation/)

## Display options

| Option | Decision and trade-off |
| --- | --- |
| Dashboard gallery with original synthetic stills, plus official links | Selected for v0.4.0. It supports review of selection, enlargement and image states while the resort continues to host live viewing. Only an explicit navigation to an official link contacts the resort's camera service. |
| Resort-provided integration | Prefer a documented still route or still-only widget if the resort supplies written permission and provides a compatible integration. Public gallery and website searches found no third-party widget, shareable embed code or camera API. |
| Display the currently published JPEGs | Deferred. Public viewer links establish browsing access. Section 2 of the terms restricts display of site content and requires express written permission for specified uses of downloaded material. The household decision covers factual weather measurements only. The dashboard currently permits same-origin images. |
| Frame the resort gallery | The earlier gallery response used `X-Frame-Options: SAMEORIGIN`. The dashboard also prohibits frames. These restrictions stay in effect. |

The prior Lodge sample was about 188 KiB for one JPEG and 3.1 MiB for the animated time-lapse. A single full JPEG transfer every 15 minutes across an always-visible 24-hour session is about 18 MiB per device at that sample size. Caching and revalidation may reduce transfer size. Loading only the selected still avoids multiplying the cost across five cameras. Enlarging an image can reuse the selected still. [Resource measurements and browser policy](../../DATA_SOURCES.md#whitewater-webcam-integration-review-before-v033), [resort terms, section 2](https://whitewatermountainresort.com/terms-of-use/)

## Path to approved live stills

1. If the owner elects to pursue live display, ask the resort to confirm private household display permission, exact allowed origins and routes, attribution, refresh limits, supported time fields and time zones, seasonal behavior, and any caching restrictions. The resort's media page provides its contact for photo and video requests. [Resort media contact](https://whitewatermountainresort.com/media/)
2. Keep camera identity, official viewing links and selection unchanged when supplying an approved still to the gallery. Review the precise image origin and any security policy change as part of the approved integration. Use the existing gallery states for loading, stale and unavailable, and retain official links when a still fails.
3. Use ordinary browser caching and only request the selected camera while its view is visible, at most once per 15 minutes or slower if required. Keep resort stills out of service-side collection, SQLite and backups. Validate browser behavior with synthetic responses first. Use a correctly sourced capture timestamp when available, or explicitly state that capture time is unknown. Keep refresh time separate from capture time so an unchanged image cannot become fresh from a successful request alone.

DriveBC's attributed Highway 6 junction still has a separate licence and existing checks. Its provider cadence, cache, freshness and access rules continue to apply. [DriveBC source notes](../../DATA_SOURCES.md#webcam-validation-in-v0321)

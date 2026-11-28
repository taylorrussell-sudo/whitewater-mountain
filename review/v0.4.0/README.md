# v0.4.0 private preview and visual review

## Launch a local preview

Open the candidate checkout on a development computer with Python 3.10 or later. From the repository root, start the fixture-only preview.

```sh
python3 -B review/v0.4.0/preview.py --scenario fresh
```

Open `http://127.0.0.1:8766` in a browser on the same computer. Use a 1920 × 1080 viewport for the wall or the browser's responsive device mode at 390 × 844 and 430 × 932 CSS pixels. Try the theme menu, the five main tabs, and camera selection and enlargement. Stop the preview with **Ctrl+C**. Restart it with a different scenario or use `--port 8767` to compare two scenarios in separate tabs.

| Scenario | What to review |
| --- | --- |
| `fresh` | 22 cm of reported snowfall, a 6 cm next-24-hour IFS forecast, a later 21.6 cm forecast peak, fresh station measurements and the illustrated DriveBC still. |
| `freezing` | In **Powder**, expand **Hourly crossings** to see crossings move from 1300/1533 m to 1467/1700 m, then return. One hour lacks usable profile data. |
| `stale` | Stale Nelson and resort data appear in **Overview** and **Info**. In **Webcams**, check the unavailable highway still, select Weather Stick for the offline fixture, and select Raven for the stale still. |

The preview runs the same dashboard and local API used by the installed application against a temporary SQLite database, fixed clock and synthetic weather adapters. Its header identifies the selected scenario. Both startup and Refresh Data use fixture inputs. Official links open provider pages only when selected.

The loopback URL works on the computer running the preview. The Cloud workspace had SSH access and no configured HTTP preview URL during review. The local launcher and screenshots provide private review without additional hosting. The existing simulated Pages site remains a separate review surface.

## Review setup

The baseline is commit `6ee2cf3d6def76e881f3755a1dde05f04e03c1d5` from merged v0.3.4. Screenshots use the same fixture launcher, data, browser settings and viewport on both versions. The launcher adds the synthetic heading to both versions. The baseline's interface displays its inherited v0.3.2.2 label.

All conditions, timestamps and stills are synthetic. Preview captures use Chromium with one device pixel per CSS pixel and reduced motion enabled. The phone captures use touch emulation.

| View | Baseline | Candidate |
| --- | --- | --- |
| Wall Overview · 1920 × 1080 · dark | [Before](wall-overview-before.png) | [After](wall-overview-after.png) |
| Phone Overview · 390 × 844 · light | [Before](phone-overview-before.png) | [After](phone-overview-after.png) |
| Wall Webcams · 1920 × 1080 · dark | [Before](wall-webcams-before.png) | [After](wall-webcams-after.png) |

- **Wall Overview.** Powder Watch leads the main card row, and the snow report and IFS next-24-hour estimate read side by side. Solid reported and dashed forecast accents reinforce the written source labels. The full Overview fits on the wall viewport.
- **Phone Overview.** A compact weather summary and a single row of five visible tabs free space above current conditions. Both Powder Watch values fit in the first 390 × 844 viewport. With the fresh fixture, the full Overview is 194 CSS pixels shorter.
- **Wall Webcams.** Five camera buttons control the synthetic resort view next to an independent DriveBC card. The sample capture time sits below the still and the official links remain available.

### Other fixture states

- [Phone freezing outlook · 430 × 932](phone-freezing-after.png) shows the snow report, the changing 0°C crossing elevations, and the unavailable hourly profile sample.
- [Phone stale Overview · 390 × 844](phone-stale-overview-after.png) shows unavailable station readings and a stale report next to an available IFS forecast.
- [Wall stale gallery · 1920 × 1080](wall-camera-stale-after.png) shows a retained stale Raven sample, an unavailable DriveBC still, and the stale weather sources.
- [Phone offline camera · 390 × 844](phone-camera-unavailable-after.png) shows the simulated offline Weather Stick state and the camera controls in light theme.

The viewport checks and image requests were verified in Chromium. Physical wall readability and iPhone Safari remain acceptance checks. [QA results](qa.md)

## Design decisions for owner review

The sprint keeps the existing tabs, cards and weather products. A larger revision could explore a dedicated wall mode with adjustable distance-reading scale, a reorderable phone dashboard, or integrating Mountain as a tab in the household wall shell. These proposals require owner review and physical-device feedback. Live resort imagery has a separate provider approval gate. [Whitewater webcam research](whitewater-webcam-research.md)

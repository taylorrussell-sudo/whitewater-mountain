# Whitewater Mountain Conditions — v0.1.1 prototype

Self-contained static HTML/CSS/JavaScript. All numerical data is simulated. Camera artwork is schematic, not actual webcam imagery. This is an independent family design prototype, not an official resort or avalanche forecast. No live APIs, tracking, credentials or home network access.

## Local review
Open `index.html` in Chromium, Chrome, Safari or another modern browser. Change the scenario and theme; explore the five tabs and interactive Info controls. Auto theme follows device preference; reduced-motion system preference is respected. Settings reset on reload in this prototype.

## Automated regression checks

Use Python 3.10+ and Chromium. The tests launch a loopback server on a free port and exercise the actual static page. They cover the five scenarios and tabs, forecast calculations, keyboard camera selection, 44 px camera targets, severity styling, themes and reduced motion, and layouts from 320 CSS px up to the 1920×1080 wall view.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r tests/requirements.txt
python -m playwright install chromium
python -B -m unittest discover -s tests -v
```

Set `CHROMIUM_PATH` to the executable path to use an installed Chromium build. The suite checks official link destinations without opening them. Physical touchscreen and other browser checks are tracked in [BACKLOG.md](BACKLOG.md).

## Publish to GitHub Pages (free public repository)
1. Sign in to GitHub and create a NEW public repository `whitewater-mountain` (do not replace the existing OAuth homepage repository).
2. Upload `index.html` and optionally `README.md` to the main branch root. Commit the files.
3. In repository Settings → Pages, choose Deploy from a branch, main, / (root), Save.
4. When GitHub displays the published URL, open it and check all five tabs and scenarios. Share that exact URL with family. The expected project URL pattern is `https://<username>.github.io/whitewater-mountain/`; it is not live until deployed.

Official instructions: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

GitHub Pages is public, not a private sharing mechanism. The noindex directive is not access control. Keep private project handoffs, secrets and household configuration out of the repository. Repository-safe development handoffs live under [handoffs/](handoffs/LATEST.md).

## Next steps
Family design feedback first. Confirm sources/permissions and exact elevations, then implement and validate a separate cached live-data service, official avalanche expiry handling and weather-model uncertainty. No changes to Raspberry Pi/HA, Funnel or backup configuration until approved. Add new application/configuration paths to encrypted backup sources and verify a targeted restore before production deployment. Summer AQHI/PM2.5/smoke mode deferred.

## Logic
Five selectable scenarios; simulated daily snow totals are distributed uniformly over hourly bins for illustrative rolling 24-hour forecast windows (starts 0–48 hours inclusive). Actual alerts use the last 24h; forecast alerts use the maximum 24h total ending within 72h. Values are illustrative, not a calibrated forecast. Real data needs hourly timing, model provenance and validation. Alert levels: 0–4, 5–9, 10–14, 15–24, 25–39, 40+ cm. A qualitative powder interpretation is scenario-defined rather than a numerical scientific score. No safety rating is computed from powder conditions.

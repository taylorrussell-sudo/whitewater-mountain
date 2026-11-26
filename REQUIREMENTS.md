# Mountain Dashboard requirements

Status: agreed design direction, implementation coverage varies. Baseline v0.1.1 is simulated only.

## Core winter experience
- Whitewater-centric overview with five internal tabs: Overview, Powder, Webcams, Avalanche, Info. Main wall application eventually includes Mountain alongside Calendar, Home, Music and Lists.
- Schematic elevation profile from Nelson through Apex/Nordic, Glory base, Day Lodge, individual chair tops, snow plot and Ymir Peak. Elevations provisional until verified; distinguish freezing level from falling snow transition and actual snow cover. Show changing freezing level and elevation-specific forecasts.
- Show reported overnight/24h/48h/3-day/7-day/season snowfall and snowpack where available; lodge/summit temperature and wind; seven-day forecasts and cumulative predicted snow next 24/48/72h. Preserve observation site and time.
- Separate actual and predicted powder alerts, icy-blue solid vs violet dashed visual language. Use a static accent at 5 cm, a soft glow at 10 cm, and an increasingly visible slow pulse from 15 cm. Keep the glow static when reduced motion is enabled. Configurable thresholds remain planned. Proposed 24h tiers: below 5 cm normal, 5–<10 fresh, 10–<15 watch, 15–<25 powder, 25–<40 major, 40+ exceptional. Forecast uses maximum rolling 24h snowfall within the next 72h, not a multi-day total. Display expected timing and confidence when supported.
- Powder quality is qualitative and experimental; use temperature, wind, snowfall timing, freezing level and previous weather only when grounded. Never imply avalanche safety.
- Selectable webcam gallery with visible keyboard focus retained on selection and camera controls at least 44×44 CSS px. Add source attribution and timestamps when approved. Show three elevation bands with numeric and text ratings plus distinct severity accents. Add the official region and bulletin expiry when validated and retain the official link; stale/missing = unavailable, not low. Nordic grooming and access road conditions when validated.
- Info explains thresholds, data provenance, forecast vs observed vs calculated, uncertainty, limitations, and interactions. Update explanations with logic changes.
- Responsive phone layouts down to 320 CSS px and a 1920×1080 wall layout; no scrolling for essential desktop overview, touch-sized controls, clean muted design, light/dark/auto, accessible motion.
- Family review on standalone public GitHub Pages, independent from home network. No private data. No paid services anticipated. Live backend architecture and production integration require separate approval.

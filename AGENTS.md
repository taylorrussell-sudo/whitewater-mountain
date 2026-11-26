# Development instructions

Read README.md, REQUIREMENTS.md, BACKLOG.md, DATA_SOURCES.md and CHANGELOG.md before edits. This is an independent, public, non-commercial mountain dashboard prototype, not an official safety product.

- Preserve existing functionality and visual style. Explain the plan and scope before significant changes; use small reversible changes on a feature branch and open a pull request. Do not merge, deploy, or access production systems without explicit approval.
- Keep the static GitHub Pages demo working without a backend or paid dependencies. No credentials, personal information, home-network configuration, private handoffs or live household access in this repo. Never use the production Pi as a development machine.
- Label simulated, measured, forecast, derived, stale and unavailable data clearly. Never infer avalanche safety from powder or missing data. Do not use live data before source permissions and validation are resolved.
- Maintain touch-friendly 1920×1080 landscape overview, mobile layouts, accessible keyboard interaction, light/dark/auto and reduced motion. Prefer lightweight web technologies. Test existing tabs, scenarios, alerts, graphs, themes and controls after each change.
- Update relevant requirements/backlog/source notes and CHANGELOG when changes are approved. Record tests actually run, failures and limitations. Finish each task with the format in HANDOFF_TEMPLATE.md. Distinguish proposed changes from merged, published and deployed versions.
- For every substantive development task, save a repository-safe completion report in `handoffs/YYYY-MM-DD_HHMM_<task-slug>.md` using America/Vancouver time. Include the full completion timestamp with its UTC offset and update `handoffs/LATEST.md` to link to the new report. Preserve all historical reports. Include the handoff and pointer update in the task's GitHub pull request so the Raspberry Pi Project in ChatGPT can retrieve them. Follow HANDOFF_TEMPLATE.md for the full procedure.
- Do not modify the external OAuth website, home dashboard, Pi, backups, Home Assistant or Funnel. Production deployment and encrypted backup coverage are separate approved work.

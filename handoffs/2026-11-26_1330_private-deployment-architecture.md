# Private household deployment architecture

## Completion timestamp / objective
2026-11-26T13:30:54-07:00 (America/Vancouver, reported session offset). Record user-approved personal-use direction; one application, one codebase and one private live deployment. Public simulated Pages is temporary family feedback only.

## Repository / status
taylorrussell-sudo/whitewater-mountain; branch docs/private-deployment-architecture; base e529899d4787b6e933d45f1acbda198718a0ee76. Documentation-only proposal for review; application v0.2.1 remains published. [Branch comparison](https://github.com/taylorrussell-sudo/whitewater-mountain/compare/main...docs/private-deployment-architecture). No production or data-access changes.

## Changes
AGENTS, README, REQUIREMENTS, BACKLOG, DATA_SOURCES and CHANGELOG now specify private deployment, staged source validation, local service/cache and permitted history, family LAN/optional authenticated private remote access, and Pages retirement. No new subscription, public ingress or parallel live deployment. Keep GitHub/Codex for development and synthetic regression tests.

## Design decisions and limitations
Personal use is not blanket authorization for automated collection. Prioritize numerical resort observations, discover documented access and terms, clarify material ambiguity before automating, never circumvent restrictions. Open-Meteo and ECCC endpoint validation remains pending. Exact service framework, storage engine, refresh intervals, locations, network access and recovery procedure are not selected. Repository visibility stays unchanged until separately approved; never commit live records or private configuration. Pages is still public; retire with approval once private hosting is verified, before any public live-data exposure.

## Verification
Documentation-only review of current repository instructions and application baseline. No browser or live API tests were run. Existing code and tests are not modified.

## Backup and rollback
No backup coverage changes yet. Before deploying, verify existing backup and rollback, identify actual code/config/service/data paths and exclusions, consistent database snapshots and permitted retention, then run backup and targeted restore. Keep private infrastructure details in the private Project. Close the PR to retain the current documentation; after merge revert via reviewed PR.

## Next task / approvals
v0.3.0 read-only source validation and isolated proof of concept, without changes to the dashboard, public site or Pi. User has approved architecture direction; merge, implementation design, source access where unclear, production deployment, network access and Pages retirement require separate approval.

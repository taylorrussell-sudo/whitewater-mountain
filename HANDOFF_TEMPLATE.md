# Codex → ChatGPT Project completion report

## Save the handoff in GitHub

1. For every substantive development task, save a new report under `handoffs/` as `YYYY-MM-DD_HHMM_<task-slug>.md`. Use America/Vancouver local time and a short lowercase, hyphenated task slug. Use the completion time for both the filename and the full ISO 8601 timestamp with UTC offset in the report.
2. Preserve all existing reports. If the filename already exists, use a more specific task slug to avoid overwriting history.
3. Update `handoffs/LATEST.md` with a relative Markdown link to the newest report. Include the report and pointer update in the task's GitHub pull request. Share the PR URL and handoff filename so the Raspberry Pi Project in ChatGPT can retrieve the report from the PR branch before merge.
4. Keep GitHub handoffs suitable for the repository's audience. Exclude credentials, personal information, private infrastructure details, and household configuration. Keep the private project's master handoff there.

## Report fields

- Completion timestamp (America/Vancouver, with UTC offset) / task / objective:
- Repository / branch / PR URL / commit SHA:
- Version and status (proposed, committed, merged, Pages published, Pi deployed — distinguish):
- Changes and files affected:
- Design decisions and deviations from requirements:
- Tests run, environment and results (including failures):
- Remaining bugs, assumptions, data-source and safety limitations:
- Dependencies / security / privacy / backup implications:
- Rollback method (commit/tag or revert PR):
- Next recommended task / backlog changes:
- User approval still required:

Do not claim a publish, production installation or backup verification without evidence. The private Project maintains the overall Pi master handoff; this is an application-level completion report, not a replacement master.

# Area OPS: admin backend, feedback cron, backup, drill, archive

Status: building

## Done
- Feedback cron duty: merged earlier (`api/src/schedule/duties.ts`, `checks/C-116-3.test.ts`).
- Archive Job reads and deletes D1 rows: `py/stockpilot/jobs/archive/d1table.py` (table `browser_errors` registered, live only when the D1 credentials exist); `archive.yml` and `_job.yml` pass the credentials through; test in `py/tests/test_archive_handler.py`.

- Admin pane: `web/src/panes/admin/index.tsx` (Needs you, switches, Recompute, freshness, runs with Try again, Problems from `/api/admin`, usage), words `web/src/words/admin.{en,bn}.json`, test `web/src/panes/admin/admin.test.tsx`.

## Next
- [ ] Admin: a preview e2e for C-099-1 / C-106-2 / C-104-1 needs the owner's prototype review; layout editor not built (route exists).
- [ ] Bridge check: a script that compares the live Apps Script bridge with the committed copy (private run).
- [ ] Drill on the Job runtime (private repo workflow; needs the owner's word).

## Decisions
- Archive token is its own secret (`CF_D1_ARCHIVE_TOKEN`, needs delete rights) so the read-only backup token stays read-only.
- The archive reads only rows past the archive age in SQL, so a big table is never pulled whole.

## Blocked
- Secrets never created: `CF_ACCOUNT_ID`, `D1_PRODUCTION_ID`, `CF_D1_ARCHIVE_TOKEN` as repository secrets here (the archive reports "nothing to archive" until they exist).
- Private-repo workflow changes (backup, drill) wait on the owner's word.

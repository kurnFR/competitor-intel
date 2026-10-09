# First real run: a step-by-step checklist

Everything below is something only you can do, because it needs your database, your LLM and your websites.
The platform checks most of it for you: run `python -m scripts.preflight` (or open **Admin -> Setup checklist**)
after each step and it tells you what is still missing.

## 1. Get the latest code and back up
1. Merge the pull requests in order (see the repository's open PRs), then `git pull`.
2. **Back up your database first**: `pg_dump -Fc competitor_intel > backup-before-upgrade.dump`
3. Apply database changes: `alembic upgrade head` (Docker: they run automatically on start).
   This also resets the old fake "Indonesia" geography on existing promotions to "Not stated".

## 2. Configure (`.env`)
| Setting | Why |
|---|---|
| `APP_ENV=production` and serve over HTTPS | secure cookies, hidden API docs |
| `SECRET_KEY` (random, 48 chars; never change it later) | two-factor sign-in |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | extraction |
| `CRAWLER_USER_AGENT=CompetitorIntelBot/1.0 (+https://your-site; you@your-company)` | so site owners can reach you |
| `MFA_REQUIRED_FOR_ADMINS=true` (once admins have set up their phones) | stronger admin sign-in |
| `SMTP_*` + `DIGEST_RECIPIENTS` and/or `DIGEST_WEBHOOK_URL` | weekly digest **and** failure alerts (so you hear about a broken scan) |

## 3. Create your first administrator
`python -m scripts.create_user --username yourname --role ADMIN` then sign in and turn on two-factor on the **Account** page.

## 4. Run the self-check
`python -m scripts.preflight --llm` - fix every **FAIL**, then the **WARN** items that apply to you.
If it reports sample/test data, pause or reject those websites on the Admin page.

## 5. Choose what to scan
**Admin -> Websites we scan.** For each website: check its terms of use and robots rules, add it, pick the reader
(a tuned one if it is Superindo / Indomaret / Alfamart, otherwise the generic catalog reader), then **Approve**.
Nothing is scanned before approval.

## 5b. Try a real page before trusting a website (nothing is saved)
Save a promotion page as a file (or copy its text) and run:

    python -m scripts.dry_run page.html --retailer Indomaret

It uses the same extraction and matching code as a real scan and tells you, for every promotion it found: what was
extracted, whether the retailer / brand / competitor / product were matched, whether it is new or already known,
whether it **would appear on the dashboard - and if not, exactly why and what to do about it**. Rejected items are
listed with their reasons. Nothing is written to the database. Use `--extracted items.json` to replay saved model
output without calling the LLM.

## 6. Do one scan and look at the result
1. Dashboard -> **Scan now** (or `python -m scripts.run_pipeline`). Watch **Admin -> Recent scans**.
2. Open 20-30 promotions and compare each with its source page (the evidence quote and link are in the detail drawer).
3. **Review** page: confirm uncertain matches and decide any conflicts. Promotions with no matched competitor/brand stay hidden until you do.
   If the dashboard looks empty, the **Setup checklist** (Admin) lists the exact reasons promotions are hidden, with counts.
4. Check **Regional pricing**: promotions whose page does not state a region appear under "Not stated" - that is expected.

## 7. Measure extraction quality (do this before you trust the numbers)
Save a handful of real pages as text, write what a person would extract (see `tests/fixtures/extraction_gold/`),
then `python -m scripts.eval_extraction`. Note the baseline; re-run after any model or prompt change.

## 8. Look at it in a real browser
Open the dashboard on desktop and phone. The design and layout were not checked visually. The browser's developer
console may list blocked resources: those come from the report-only security policy and tell you what to allow
before it is switched to enforcing.

## 9. Operate safely
- Schedule backups (`deploy/backup.sh`) and test a restore once.
- Revoke the GitHub token used to publish this work.
- Remove `postgresql_schema_ddl_20260924.log` from git history (command in `docs/HANDOVER.md`).
- Add an outside uptime check on `/health` (the app cannot alert you that it is down).
- Never run the automated tests against the production database.

## What "done" looks like
- [ ] Setup checklist shows no **Fix now** items
- [ ] At least one approved website scanned successfully
- [ ] 20+ promotions spot-checked against their sources, extraction baseline recorded
- [ ] Review queue worked through, no open conflicts you did not decide
- [ ] Dashboard looked at in a real browser
- [ ] Failure alerts reach a real inbox/channel (the checklist says "announced once each")
- [ ] Outside uptime monitor on `/health`
- [ ] Backups running; token revoked

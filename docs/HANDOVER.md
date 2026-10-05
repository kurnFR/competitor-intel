# Handover

## What the platform does

Scans competitor and retailer promotion pages on a schedule, extracts promotions with an LLM, checks every one
against its source text, ranks them, and shows them to the marketing team. Everything requires a login.

| Area | What you get |
|---|---|
| Dashboard | Top promotions with filters, evidence quote and source link for each |
| Insights | Weekly digest (new / changed / ending soon) and competitor activity heat-map |
| Price comparison | Your prices vs competitor promotions per 100 g (analyst+) |
| Export | CSV / Excel of the filtered view (analyst+) |
| Review | Confirm uncertain product/brand/retailer matches, and decide conflicts where two sources disagree (analyst+) |
| Admin | Users and roles, 2FA reset, websites we scan (with health), security log |
| Alerts | Weekly digest by e-mail and/or Slack-style webhook (optional) |
| Security | Argon2id passwords, optional 2FA, server-side sessions, CSRF, lockout, audit log, roles |

## What you still need to do (I cannot do these for you)

1. **Try it on your real sources and LLM.** This was developed and tested with synthetic data. Run a scan, then
   check 20-30 promotions against the source pages. Use `python -m scripts.eval_extraction` to keep score.
2. **Look at the pages in a real browser** (styling and layout were not visually checked). The Content-Security-Policy
   is report-only: check the browser console for violations, then tighten it or self-host Tailwind/Font Awesome.
3. **Set the secrets:** `ADMIN_API_KEY` (only if you automate scans), `SECRET_KEY` (needed for 2FA; never change it
   afterwards), database password, LLM key. Turn on `MFA_REQUIRED_FOR_ADMINS` once every admin has a phone set up.
4. **Purge the old database log from git history.** `postgresql_schema_ddl_20260924.log` was deleted from the latest
   commit but is still in old ones. Rewrite history and force-push (this changes `master`; coordinate with anyone with a clone):
   `git filter-repo --path postgresql_schema_ddl_20260924.log --invert-paths`
5. **Review each source's terms of use and robots rules** before enabling it; the crawler obeys robots.txt and
   identifies itself using `CRAWLER_USER_AGENT` (add contact details).
6. **Revoke the GitHub access token** that was used to publish this work, and any other temporary credentials.
7. **Deploy over HTTPS** and schedule backups (`docs/DEPLOYMENT.md`).

## Day-to-day operation

- **A source stopped working:** Admin -> "Websites we scan" shows FAILING / STALE. Open its page in a browser: layout
  changed, blocked the bot, or robots.txt disallows. JavaScript-only sites need the Playwright add-on.
- **Results look wrong:** run `python -m scripts.try_extract page.txt` on the page text to see what was accepted or
  rejected and why. Rejections are counted in the scan log (`rejected`, `documents_failed`).
- **Add a website:** Admin -> "Websites we scan". Unknown sites use the generic reader, so give it a catalog/promo
  page that lists products with prices. Supported retailers (Superindo, Indomaret, Alfamart/Alfagift) have tuned readers.
- **Forgot password / lost phone:** an admin resets the password (Admin page); for a lost authenticator use "Reset 2FA".
  If the *only* admin is locked out: `python -m scripts.create_user --username x --role ADMIN` on the server.
- **Someone left:** disable their account (Admin page); their sessions end immediately.
- **Upgrade:** see `docs/DEPLOYMENT.md`. Migrations run automatically in Docker; otherwise `alembic upgrade head`.

## Known limits

- **One app process only.** The scheduler and the per-IP login throttle are in memory. A database lock prevents overlapping
  scans and scan history is stored in the database, but do not run several workers.
- **Extraction is only as good as the LLM and the page.** Promotions without a verbatim evidence quote in the page are
  rejected by design. Pages that only render with JavaScript need Playwright (not installed by default).
- **Undated promotions** are shown (flagged, ranked lower) until their source is successfully processed later and no longer lists
  them; a failing source never causes promotions to disappear.
- **Geography is macro-region only** (province/city/store stay as wording) and is "Not stated" unless the page says so.
- **Scans are per source.** Each approved source has its own frequency (Admin page); the scheduler checks every
  `SCHEDULER_TICK_MINUTES` and scans only what is due. "Scan now" scans every approved source.
- **Price comparison** covers products sold by weight (grams/kg). Volume and count packs are skipped.
- **The Docker files were not built** in the environment where they were written; test them once on a spare machine.
- **No self-service password reset by e-mail;** an admin resets passwords.

## Where this stands against the PRD

See `docs/PRD_ALIGNMENT.md` for a section-by-section status and the decisions that need to come from you.

## Suggested next steps

1. Label 15-30 real pages and record a baseline with `eval_extraction`.
2. Add the remaining sources you care about (Hypermart, Transmart, Yogya, marketplaces, competitor social pages).
3. Move login throttling and scan status into the database if you ever need more than one process.
4. Tighten the Content-Security-Policy once the pages are verified in a browser.
5. Add per-source crawl schedules and alerts when a source fails for several runs.

## How it is tested

`python -m pytest tests` (needs PostgreSQL; see `.github/workflows/ci.yml`) runs about 200 tests: unit tests, API and
security tests (login, sessions, CSRF, roles, lockout, 2FA, export safety), the pipeline against PostgreSQL, and
migrations up and down. `tests/ui/` clicks through the real pages with a simulated browser.

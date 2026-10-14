# Deployment guide

Two supported ways to run the platform. Both keep **one app process** (the scheduler, scan status and login
throttling live inside it) and put **HTTPS** in front.

## Option A - Docker Compose (recommended)

> The Docker files were written and syntax-checked but could not be built in the environment where they were
> authored. Do a first `docker compose up --build` on a test machine and check `docker compose logs app`.

```bash
cp .env.example .env
# edit .env: POSTGRES_PASSWORD, LLM_BASE_URL / LLM_API_KEY / LLM_MODEL, CRAWLER_USER_AGENT (with contact info),
#            ADMIN_API_KEY (optional), SMTP_* / DIGEST_* (optional)
docker compose up -d --build
docker compose exec app python scripts/seed_data.py            # one-time: starter competitors and sources
docker compose exec app python -m scripts.create_user --username yourname --role ADMIN
```

The app listens on `127.0.0.1:8000` only. Put the HTTPS proxy from `deploy/nginx.conf.example` in front of it
(get a certificate with `certbot --nginx`). Then open `https://your-domain/`.

## Option B - Directly on a server

```bash
python3.12 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # edit: DATABASE_URL(_ADMIN), APP_ENV=production, LLM_*, etc.
alembic upgrade head
python scripts/seed_data.py
python -m scripts.create_user --username yourname --role ADMIN
scripts/start_server.sh          # or run it as a systemd service
```

Example `/etc/systemd/system/competitor-intel.service`:

```ini
[Unit]
Description=Competitor Promotion Intelligence
After=network.target postgresql.service

[Service]
User=intel
WorkingDirectory=/opt/competitor-intel
EnvironmentFile=/opt/competitor-intel/.env
ExecStart=/opt/competitor-intel/scripts/start_server.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Production checklist

- [ ] `APP_ENV=production` (Secure cookies, HSTS, hidden `/docs`)
- [ ] HTTPS in front; `TRUST_PROXY=true` **only** if the proxy overwrites `X-Forwarded-For`
- [ ] First administrator created; no shared accounts (one login per person)
- [ ] Sources approved on the Admin page (new ones start as candidates and are not scanned)
- [ ] `CRAWLER_USER_AGENT` contains a contact address; each source's terms of use reviewed
- [ ] LLM endpoint reachable from the server (`python -m scripts.try_extract sample.txt`)
- [ ] Database backups scheduled (`deploy/backup.sh`) and a restore tested once
- [ ] PostgreSQL not exposed to the internet
- [ ] Old `postgresql_schema_ddl_20260924.log` purged from git history (see `docs/HANDOVER.md`)

## Monitoring and housekeeping

**What the app tells you by itself.** When a scan fails, or an approved website starts failing or goes 3+ days without a
successful check, you get **one** message (e-mail and/or chat webhook, the same channels as the weekly digest), and another
when it recovers. Alerts also appear under **Admin -> Recent alerts**. Without a configured channel they are only listed there.

**What it cannot tell you: that the app itself is down.** Use an outside uptime monitor (UptimeRobot, Better Stack, a cron on
another machine) on `https://your-domain/health` - it returns `{"status":"ok"}` only when the app and database are reachable.

**Disk.** Crawled pages are stored on disk (`RAW_DOCUMENT_STORAGE_PATH`) and in the database. A daily job (03:30) removes the raw
file and full text of crawled pages older than `RETENTION_DOCUMENT_DAYS` (default 90) - promotions, evidence quotes, source links
and page records (address, time, hash) are kept, and the **newest page of every website is never removed**. It also prunes the audit
log (365 d), scan history (180 d) and alerts (180 d). Preview: `python -m scripts.retention --dry-run`. The Setup checklist shows
disk use and free space.

## Upgrading

After **every** `git pull`, apply the database changes: `alembic upgrade head` (Docker does it automatically on start).
`scripts/start_server.sh` checks this for you and refuses to start on a mismatched database; set `AUTO_MIGRATE=true` to let it upgrade
the database itself (back up first on a real database).

```bash
git pull
docker compose up -d --build       # migrations run automatically on start
# or, without Docker:  pip install -r requirements.txt && alembic upgrade head && restart the service
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| A page says **"The database needs upgrading"** (or you see "Internal Server Error" after updating) | The code is newer than the database. Back up, then run `alembic upgrade head` and restart. `python -m scripts.check_schema` says exactly what is wrong; `/health` returns 503 with the same message; the server prints it at startup. |
| Cannot stay logged in on `http://` | `APP_ENV=production` sets Secure cookies; use HTTPS (or `SESSION_COOKIE_SECURE=false` for a private test only) |
| "Scan" shows failed | `docker compose logs app` - usually the LLM endpoint or a source that is down |
| A source shows FAILING/STALE (Admin page) | Site changed layout, blocks the bot, or robots.txt disallows it |
| Dashboard empty after a scan | Check the scan summary in the logs: `rejected` and `documents_failed` counts |
| Dynamic (JavaScript-only) site returns nothing | Install the browser add-on: `pip install -r requirements-browser.txt && playwright install chromium` |

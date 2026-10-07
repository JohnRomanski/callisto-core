# Operations

What it takes to run callisto-core. Nothing is deployed today; this is the
checklist for the first deployment. Settings details are in
[USAGE.md](USAGE.md).

## Components

| Component | Why |
|---|---|
| Host Django project | Templates, URLs, branding, `TenantApi` implementation |
| PostgreSQL | Required: matching relies on row locks (`select_for_update`) |
| Redis (or another broker and cache) | Celery broker; shared cache for the passphrase rate limit |
| Celery worker | Sends queued email; runs matching and match notifications |
| Celery beat (or cron) | Runs `sweep_pending_matches` (or `manage.py process_pending_matches`) every ~10 minutes |
| Mailgun account | Email transport |
| HTTPS terminating proxy | Must set, and never pass through, `X-Forwarded-Proto` |
| GPG public key per school | Coordinator key for each site |

## Environment (with `settings_live`)

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | yes | Long random string |
| `PEPPER` | yes | 64 hex characters; identical everywhere; never changes |
| `DATABASE_URL` | yes | Postgres |
| `APP_URL` | yes | Added to `ALLOWED_HOSTS` |
| `REDIS_URL` | strongly recommended | Shared cache for rate limiting |
| `CELERY_BROKER_URL` | recommended | Without it, email and matching run inside requests |
| `MAILGUN_API_KEY` | yes | Plus `MAILGUN_POST_ROUTE` / `MAILGUN_FROM` for your domain |

## Before go-live

1. `python manage.py check --deploy` passes.
2. `python manage.py migrate`.
3. Tenant settings for each site: coordinator email and **a tested GPG key**,
   school email domains, signup mode.
4. Email templates (`EmailNotification`) exist for every site.
5. Question pages and questions are attached to every site.
6. Send a test report end to end on a staging site and have the coordinator
   decrypt it.
7. Back up the database **and** the `PEPPER`, separately.

## Running

- Web: any WSGI server (gunicorn); static files via WhiteNoise.
- Worker: `celery -A callisto_core.celeryconfig.celery worker`
  (`--pool=threads` on macOS for local runs).
- Beat: schedule `callisto_core.reporting.tasks.sweep_pending_matches`.

## Monitoring (not built yet)

Things worth alerting on, without logging personal data:

- `MatchEvent` rows incomplete for longer than the sweep interval.
- `MatchingJob` rows older than the sweep interval.
- Errors `report not delivered to school` (bad coordinator key or Mailgun
  outage).
- Celery queue length and task failures.

## Known gaps

- No health check endpoint.
- No container image or infrastructure-as-code; `settings_live` still has
  Heroku review-app handling.
- The release workflow (`.github/workflows/release.yml`) is ready, but
  publishing needs a PyPI project name you control.

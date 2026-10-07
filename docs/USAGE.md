# Using callisto-core

Guidance for using callisto-core in your own unique downstream application

## Tenant Configuration

You are likely starting out with 1 tenant, and so will want to lock your SITE_ID to 1 via one or both of these methods

```bash
# bash profile, or similar
export SITE_ID=1
```

```python
# settings.py
SITE_ID = 1
```

## Settings

django settings.py minimum requirements

```python
    # the defaults, wizard builder and its requirements, the callisto-core apps
    INSTALLED_APPS = [
        'django.contrib.admin',
        'django.contrib.auth',
        'django.contrib.sites',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'nested_admin',
        'widget_tweaks',
        'wizard_builder',
        'callisto_core.delivery',
        'callisto_core.evaluation',
        'callisto_core.notification',
        'callisto_core.reporting',
    ]

    # the default generated MIDDLEWARE
    MIDDLEWARE = [
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'django.middleware.security.SecurityMiddleware',
    ]

    # encryption handling: the first hasher encrypts new records, the
    # others are needed to decrypt records created before it
    KEY_HASHERS = [
        "callisto_core.delivery.hashers.Argon2idKeyHasher",
        "callisto_core.delivery.hashers.Argon2KeyHasher",
        "callisto_core.delivery.hashers.PBKDF2KeyHasher",
    ]
    ARGON2ID_MEMORY_COST = 19 * 1024  # KiB, OWASP minimum
    ARGON2ID_TIME_COST = 2
    ARGON2ID_PARALLELISM = 1

    # secrets: load from the environment, never change them
    SECRET_KEY
    PEPPER  # 32 bytes, identical in every process

    CALLISTO_EVAL_PUBLIC_KEY
    CALLISTO_EVAL_PRIVATE_KEY (keep this one secret!)

    # links in emails sent outside a request; "https" unless you set it
    CALLISTO_EMAIL_LINK_PROTOCOL

    # apis, see api section below
    CALLISTO_MATCHING_API
    CALLISTO_NOTIFICATION_API
    CALLISTO_TENANT_API
```

### Key stretching and secrets

Records store the hashing parameters they were created with, so raising the
`ARGON2ID_*` costs only affects new records; existing reports and match
reports keep decrypting, and reports move to the current parameters the next
time they are saved. Matching derives a key for every stored match report on
each submission, so higher costs make matching proportionally slower.

`PEPPER` encrypts every match report a second time. It must be 32 bytes, the
same in every process, and never change, or existing match reports become
unreadable. Run `python manage.py check --deploy`: callisto-core reports a
demo `SECRET_KEY` (`callisto.E001`) and a malformed `PEPPER`
(`callisto.E003`). (`callisto.E002` checked `INDEXING_KEY`, which is no longer
used.)

### Password and passphrase strength

`PASSWORD_MINIMUM_ENTROPY` (bits, default `35` in the demo settings) rejects
record passphrases and account passwords that zxcvbn estimates are easier to
guess. `0` or `None` turns it off. Record passphrases are always checked;
account passwords are checked through Django's password validation, so add
the validator:

```python
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "callisto_core.accounts.validators.MinimumEntropyValidator"},
]
```

`manage.py check` warns (`callisto.W001`) when the setting is on but the
validator isn't installed.

### Rate limiting

Passphrase attempts on reports are limited by `DECRYPT_THROTTLE_RATE`
(default `"100/m"` per user) using django-ratelimit. The limit is only
enforced across a deployment if `CACHES` points at a cache that every
worker shares and that supports atomic increments, such as Redis or
Memcached. With the default local-memory cache each process keeps its own
count. Use `RATELIMIT_USE_CACHE` to pick a cache alias other than `default`.

### Passphrase storage

While someone fills in a report, the wizard needs their passphrase on every
step. callisto-core stores it in a `StoredPassphrase` row (one per session and
report) **encrypted** with a random per-browser key that is kept only in the
`callisto_passphrase_key` cookie (HttpOnly, SameSite=Strict, cleared when the
browser closes). The database never holds a readable passphrase, and separate
rows mean requests from several tabs can't overwrite each other. Stored
passphrases expire after `PASSPHRASE_SESSION_TTL` seconds without use
(default 1800) and are removed on logout and when the dashboard loads.

The cookie is marked `Secure` when the request is HTTPS. Behind a proxy that
terminates TLS, set `SECURE_PROXY_SSL_HEADER` so Django can tell.

### Email

Notifications are sent through Mailgun by the `notification.tasks.send_email`
Celery task. Set `MAILGUN_API_KEY` (and optionally `MAILGUN_POST_ROUTE` and
`MAILGUN_FROM`). The task reads these when it runs, so credentials never
enter the broker, and it stores no results. In a worker, connection errors,
429 and 5xx responses are retried with exponential backoff (5 retries). A
delivery failure is logged, never raised.

With `CELERY_TASK_ALWAYS_EAGER = True` email is sent inside the request, with
a single attempt so an outage can't hold the request open. To send it from a
worker, with retries, configure a broker and run
`celery -A callisto_core.celeryconfig.celery worker`. Queued messages contain
recipients, bodies and account activation links, so the broker must be
private and use TLS. If the broker can't be reached when an email is queued,
the email is sent inside the request instead (one attempt), so a broker
outage never fails the request.

### Matching

When a reporter enters a perpetrator identifier, the identifier is stored
encrypted with `PEPPER` as a `MatchingJob`, and only the job's id is queued,
so the broker never sees the identifier. A worker runs matching; in one
transaction it marks matched reports, records a `MatchEvent` and deletes the
job, then sends the school, reporters and Callisto team their notifications
from the event, marking each step as it goes. With
`CELERY_TASK_ALWAYS_EAGER` this all runs inside the request instead.

Run the sweeper periodically to recover work a lost queue message or a
crashed worker left behind (it is safe to run at any time):

    python manage.py process_pending_matches

or schedule the `callisto_core.reporting.tasks.sweep_pending_matches` task
with Celery beat, for example every 10 minutes. Every web and worker process
must share the same `PEPPER`, or workers cannot read the jobs.

### Logout

Django's `LogoutView` only accepts POST. Log users out with a form that
posts to the `logout` URL and includes `{% csrf_token %}`, not with a link.

- GPG
- tenant specific

## APIs

### View Functions

View partials provide all the callisto-core front-end functionality. Subclass these partials with your own views if you are implementing callisto-core.

The `views.py` files in this repo are specific to callisto-core. If you are implementing callisto-core you SHOULD NOT be importing these views. Import from `view_partials` instead, and implement classes that look like the ones in `views`.

### NotificationApi

For changing the notification (eg. emails, PDFs, slack messages, etc) implementation

Some emails must be delivered before callisto-core records that they were
sent: the report to the school (`send_report_to_authority`, which sets
`Report.submitted_to_school`) and the match notifications. These run inside
`callisto_core.notification.tasks.delivering_synchronously()`. If you override
`send_email` to use another transport, then while
`tasks.synchronous_delivery_requested()` is true it must send immediately,
raise `tasks.DeliveryFailed` if the provider rejects the email, and call
`tasks.record_accepted()` once it is accepted (`tasks.deliver(message)` does
all of this for Mailgun). If `send_email` returns without recording an
accepted email, `send()` raises `DeliveryFailed` and nothing is recorded as
sent.

### MatchingApi

For changing the matching implementation

### TenantApi

For producing different attributes based on the tenants

`get_current_domain()` gives the domain used in links in emails. The default
returns the `SITE_ID` site's domain; multi-tenant hosts that resolve the site
per request (no `SITE_ID`) must override it.

## Data

- sites
- questions
- notifications

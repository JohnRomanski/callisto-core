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

    # encryption handling
    KEY_HASHERS = [
        "callisto_core.delivery.hashers.Argon2KeyHasher",
        "callisto_core.delivery.hashers.PBKDF2KeyHasher"
    ]

    CALLISTO_EVAL_PUBLIC_KEY
    CALLISTO_EVAL_PRIVATE_KEY (keep this one secret!)

    # apis, see api section below
    CALLISTO_MATCHING_API
    CALLISTO_NOTIFICATION_API
    CALLISTO_TENANT_API
```

### Rate limiting

Passphrase attempts on reports are limited by `DECRYPT_THROTTLE_RATE`
(default `"100/m"` per user) using django-ratelimit. The limit is only
enforced across a deployment if `CACHES` points at a cache that every
worker shares and that supports atomic increments, such as Redis or
Memcached. With the default local-memory cache each process keeps its own
count. Use `RATELIMIT_USE_CACHE` to pick a cache alias other than `default`.

### Passphrase storage

While someone fills in a report, the wizard needs their passphrase on every
step. callisto-core keeps it in the session **encrypted** with a random
per-browser key that is stored only in the `callisto_passphrase_key` cookie
(HttpOnly, SameSite=Strict, cleared when the browser closes). The session
store, usually the database, never holds a readable passphrase. Stored
passphrases expire after `PASSPHRASE_SESSION_TTL` seconds without use
(default 1800) and are removed on logout and when the dashboard loads.

The cookie is marked `Secure` when the request is HTTPS. Behind a proxy that
terminates TLS, set `SECURE_PROXY_SSL_HEADER` so Django can tell.

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

### MatchingApi

For changing the matching implementation

### TenantApi

For producing different attributes based on the tenants

## Data

- sites
- questions
- notifications

import dj_database_url

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # NOQA


def _required_env(name):
    value = os.getenv(name)
    if not value:
        raise ImproperlyConfigured(f"the {name} environment variable must be set")
    return value


DEBUG = False

# secrets must come from the environment; the base settings' defaults are
# demo placeholders, and its PEPPER is random per process (which would make
# match reports unreadable after a restart or by another worker)
SECRET_KEY = _required_env("SECRET_KEY")
INDEXING_KEY = _required_env("INDEXING_KEY")
PEPPER = bytes.fromhex(_required_env("PEPPER"))  # 64 hex characters

# HTTPS. SECURE_PROXY_SSL_HEADER is only safe behind a proxy that always sets
# (and never forwards a client's) X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365

INSTALLED_APPS = INSTALLED_APPS + ["django_extensions"]

MIDDLEWARE = ["whitenoise.middleware.WhiteNoiseMiddleware"] + MIDDLEWARE

DATABASES = {"default": dj_database_url.parse(os.getenv("DATABASE_URL"))}
# read by delivery.forms when generating report tokens
DATABASES["default"]["SCHEMA"] = os.getenv("DATABASE_SCHEMA", "public")

if os.getenv("HEROKU_APP_NAME", default=""):
    HEROKU_REVIEW_APP_DOMAIN = os.getenv("HEROKU_APP_NAME") + ".herokuapp.com"
else:
    HEROKU_REVIEW_APP_DOMAIN = ""

# django-ratelimit needs a cache shared by every worker, or each process
# keeps its own counter and DECRYPT_THROTTLE_RATE can be bypassed
if os.getenv("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("REDIS_URL"),
        }
    }

ALLOWED_HOSTS = [APP_URL, HEROKU_REVIEW_APP_DOMAIN]

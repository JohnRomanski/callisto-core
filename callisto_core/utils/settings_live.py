import dj_database_url

from .settings import *  # NOQA

DEBUG = False

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

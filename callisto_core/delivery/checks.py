"""
Deployment checks for the secrets callisto-core depends on.

Run with `python manage.py check --deploy`.
"""

from django.conf import settings
from django.core.checks import Error, Tags, register

# placeholder values from callisto_core.utils.settings, the demo settings
DEMO_SECRET_KEYS = {"secret key"}


@register(Tags.security, deploy=True)
def check_callisto_secrets(app_configs, **kwargs):
    errors = []
    if settings.SECRET_KEY in DEMO_SECRET_KEYS:
        errors.append(
            Error(
                "SECRET_KEY is the callisto-core demo value.",
                hint="Set a long random SECRET_KEY for this deployment.",
                id="callisto.E001",
            )
        )
    pepper = getattr(settings, "PEPPER", None)
    if not isinstance(pepper, bytes) or len(pepper) != 32:
        errors.append(
            Error(
                "PEPPER must be 32 bytes.",
                hint=(
                    "Load PEPPER from the environment (for example "
                    "bytes.fromhex(os.environ['PEPPER'])). It must be the same "
                    "for every process and never change: match reports encrypted "
                    "with one pepper cannot be read with another."
                ),
                id="callisto.E003",
            )
        )
    return errors

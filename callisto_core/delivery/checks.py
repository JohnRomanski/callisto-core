"""
Deployment checks for the secrets callisto-core depends on.

Run with `python manage.py check --deploy`.
"""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

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


ENTROPY_VALIDATOR = "callisto_core.accounts.validators.MinimumEntropyValidator"


@register(Tags.security)
def check_password_entropy(app_configs, **kwargs):
    """PASSWORD_MINIMUM_ENTROPY only reaches account passwords via the validator"""
    validators = [
        v.get("NAME") for v in getattr(settings, "AUTH_PASSWORD_VALIDATORS", [])
    ]
    if getattr(settings, "PASSWORD_MINIMUM_ENTROPY", None) and (
        ENTROPY_VALIDATOR not in validators
    ):
        return [
            Warning(
                "PASSWORD_MINIMUM_ENTROPY is set, but account passwords aren't "
                "checked against it.",
                hint=f"Add {{'NAME': '{ENTROPY_VALIDATOR}'}} to "
                "AUTH_PASSWORD_VALIDATORS.",
                id="callisto.W001",
            )
        ]
    return []

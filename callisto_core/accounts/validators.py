import logging
import math

from zxcvbn import zxcvbn

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)

# zxcvbn's cost grows with length, so only the start is analyzed. zxcvbn
# raises above its own max_length (72 by default), so pass the limit too.
_ENTROPY_INPUT_LIMIT = 100


def entropy_bits(password: str) -> float:
    """zxcvbn's estimate of the guesses needed, in bits"""
    password = password[:_ENTROPY_INPUT_LIMIT]
    guesses_log10 = zxcvbn(password, max_length=_ENTROPY_INPUT_LIMIT)["guesses_log10"]
    return guesses_log10 * math.log2(10)


def validate_entropy(password: str, label: str = "password"):
    """
    Rejects password if it is estimated weaker than PASSWORD_MINIMUM_ENTROPY
    bits. A falsy setting (0 or None) turns the check off.
    """
    minimum = getattr(settings, "PASSWORD_MINIMUM_ENTROPY", None)
    if minimum and entropy_bits(password) < minimum:
        raise ValidationError(
            f"This {label} is too easy to guess. Try a longer phrase of "
            "several unrelated words.",
            code="password_too_weak",
        )


class MinimumEntropyValidator:
    """
    A Django password validator for PASSWORD_MINIMUM_ENTROPY. Add it to
    AUTH_PASSWORD_VALIDATORS to check account passwords on signup, reset and
    change.
    """

    def validate(self, password, user=None):
        validate_entropy(password)

    def get_help_text(self):
        return "Your password must not be easy to guess."


def validate_school_email(email, school_email_domain):
    if not school_email_domain:  # demo sites use empty school email domains
        return True

    input_email_domain = email.rsplit("@", 1)[-1].lower()
    allowed = [
        _domain.strip().strip("@").strip() for _domain in school_email_domain.split(",")
    ]

    if input_email_domain not in allowed and not settings.DEBUG:
        # XXX (lojikil//Stefan Trail of Bits): I just want to raise if we're ok with this
        # since if a user adds a specific domain that can easily be tied back to them
        # (say, me@lojikil.com, lojikil.com would be logged here), someone with access to
        # the logs could tie a report back to a user. Not concerning per se, but something
        # we should be aware of
        logger.warning(
            f"non school email {input_email_domain} used for domain {school_email_domain}"
        )
        raise forms.ValidationError(
            mark_safe(
                f"Please enter a student email that matches {school_email_domain}. \
            If you're getting this message and you think you shouldn't be, \
            contact us at support@projectcallisto.org."
            )
        )

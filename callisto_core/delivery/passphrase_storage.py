"""
Keeps report passphrases between requests without the server alone being
able to read them.

Each passphrase is stored in its own StoredPassphrase row, encrypted with a
random per-browser key. That key lives only in an HttpOnly cookie, so a
database dump cannot decrypt anything. Rows are scoped to the session and
updated one at a time, so concurrent requests from the same browser (two
tabs, say) never overwrite each other. Stored passphrases expire after
PASSPHRASE_SESSION_TTL seconds without use and are removed on logout.
"""

import base64
from datetime import timedelta

import nacl.exceptions
import nacl.secret
import nacl.utils

from django.conf import settings
from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver
from django.utils import timezone

COOKIE_NAME = "callisto_passphrase_key"
DEFAULT_TTL = 30 * 60

_NEW_KEY_ATTR = "_callisto_new_passphrase_key"


def _rows():
    from .models import StoredPassphrase

    return StoredPassphrase.objects


def _expiry_cutoff():
    ttl = getattr(settings, "PASSPHRASE_SESSION_TTL", DEFAULT_TTL)
    return timezone.now() - timedelta(seconds=ttl)


def _session_key(request, create=False):
    if create and not request.session.session_key:
        request.session.save()
    return request.session.session_key


def _cookie_key(request, create=False):
    new_key = getattr(request, _NEW_KEY_ATTR, None)
    if new_key:
        return new_key
    try:
        key = base64.urlsafe_b64decode(request.COOKIES[COOKIE_NAME])
        if len(key) == nacl.secret.SecretBox.KEY_SIZE:
            return key
    except (KeyError, ValueError):
        pass
    if create:
        key = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
        setattr(request, _NEW_KEY_ATTR, key)
        # passphrases wrapped with an old cookie key can no longer be read
        clear(request)
        return key
    return None


def store(request, report_uuid, passphrase):
    key = _cookie_key(request, create=True)
    encrypted = nacl.secret.SecretBox(key).encrypt(passphrase.encode("utf-8"))
    _rows().update_or_create(
        session_key=_session_key(request, create=True),
        report_uuid=report_uuid,
        defaults={"encrypted_passphrase": encrypted, "used": timezone.now()},
    )
    _rows().filter(used__lt=_expiry_cutoff()).delete()


def load(request, report_uuid):
    """Returns the stored passphrase for the report, or '' if unavailable."""
    session_key = _session_key(request)
    key = _cookie_key(request)
    if not session_key or not key:
        return ""
    row = _rows().filter(session_key=session_key, report_uuid=report_uuid).first()
    if row is None:
        return ""
    if row.used < _expiry_cutoff():
        row.delete()
        return ""
    try:
        encrypted = bytes(row.encrypted_passphrase)
        passphrase = nacl.secret.SecretBox(key).decrypt(encrypted).decode("utf-8")
    except (nacl.exceptions.CryptoError, ValueError):
        row.delete()
        return ""
    _rows().filter(pk=row.pk).update(used=timezone.now())
    return passphrase


def forget(request, report_uuid):
    session_key = _session_key(request)
    if session_key:
        _rows().filter(session_key=session_key, report_uuid=report_uuid).delete()


def clear(request):
    session_key = _session_key(request)
    if session_key:
        _rows().filter(session_key=session_key).delete()


@receiver(user_logged_out)
def _clear_on_logout(sender, request, **kwargs):
    # runs before logout() flushes the session, while its key is still known
    if request is not None and hasattr(request, "session"):
        clear(request)


def set_cookie(request, response):
    """Sends a newly created cookie key with the response."""
    key = getattr(request, _NEW_KEY_ATTR, None)
    if key:
        response.set_cookie(
            COOKIE_NAME,
            base64.urlsafe_b64encode(key).decode("ascii"),
            httponly=True,
            secure=request.is_secure(),
            samesite="Strict",
        )
    return response

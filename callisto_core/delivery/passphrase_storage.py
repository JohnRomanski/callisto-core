"""
Keeps report passphrases between requests without the server alone being
able to read them.

The session (stored server side, usually in the database) only holds
passphrases encrypted with a random per-browser key. That key lives only in
an HttpOnly cookie, so a database or session-store dump cannot decrypt
anything. Stored passphrases expire after PASSPHRASE_SESSION_TTL seconds
without use, and are removed with the session on logout.
"""

import base64
import time

import nacl.exceptions
import nacl.secret
import nacl.utils

from django.conf import settings

COOKIE_NAME = "callisto_passphrase_key"
SESSION_KEY = "callisto_passphrases"
DEFAULT_TTL = 30 * 60

_NEW_KEY_ATTR = "_callisto_new_passphrase_key"


def _ttl():
    return getattr(settings, "PASSPHRASE_SESSION_TTL", DEFAULT_TTL)


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
        request.session.pop(SESSION_KEY, None)
        return key
    return None


def store(request, report_uuid, passphrase):
    box = nacl.secret.SecretBox(_cookie_key(request, create=True))
    encrypted = box.encrypt(passphrase.encode("utf-8"))
    passphrases = request.session.get(SESSION_KEY, {})
    passphrases[str(report_uuid)] = {
        "passphrase": base64.b64encode(encrypted).decode("ascii"),
        "used": time.time(),
    }
    request.session[SESSION_KEY] = passphrases


def load(request, report_uuid):
    """Returns the stored passphrase for the report, or '' if unavailable."""
    passphrases = request.session.get(SESSION_KEY, {})
    entry = passphrases.get(str(report_uuid))
    key = _cookie_key(request)
    if not entry or not key:
        return ""
    if time.time() - entry["used"] > _ttl():
        forget(request, report_uuid)
        return ""
    try:
        encrypted = base64.b64decode(entry["passphrase"])
        passphrase = nacl.secret.SecretBox(key).decrypt(encrypted).decode("utf-8")
    except (nacl.exceptions.CryptoError, ValueError):
        forget(request, report_uuid)
        return ""
    entry["used"] = time.time()
    request.session.modified = True
    return passphrase


def forget(request, report_uuid):
    passphrases = request.session.get(SESSION_KEY, {})
    if passphrases.pop(str(report_uuid), None) is not None:
        request.session[SESSION_KEY] = passphrases


def clear(request):
    request.session.pop(SESSION_KEY, None)


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

from unittest.mock import patch

from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from callisto_core.delivery import passphrase_storage

REPORT_UUID = "8d2b6a52-3c0f-4a43-9a37-1c4f2a1e7b11"


class PassphraseStorageTest(TestCase):
    def request(self, cookies=None, session=None):
        request = RequestFactory().get("/")
        request.session = session if session is not None else SessionStore()
        request.COOKIES = cookies or {}
        return request

    def store(self, passphrase="correct horse"):
        request = self.request()
        passphrase_storage.store(request, REPORT_UUID, passphrase)
        request.session.save()
        response = passphrase_storage.set_cookie(request, HttpResponse())
        cookie = response.cookies[passphrase_storage.COOKIE_NAME]
        return request.session, {passphrase_storage.COOKIE_NAME: cookie.value}, cookie

    def test_round_trip_with_cookie(self):
        session, cookies, _ = self.store()
        request = self.request(cookies, SessionStore(session.session_key))
        self.assertEqual(passphrase_storage.load(request, REPORT_UUID), "correct horse")

    def test_session_alone_cannot_recover_passphrase(self):
        session, _, _ = self.store()
        saved = SessionStore(session.session_key)
        self.assertNotIn("correct horse", str(saved.load()))
        self.assertEqual(
            passphrase_storage.load(self.request(session=saved), REPORT_UUID), ""
        )

    def test_wrong_cookie_key_is_rejected_and_entry_dropped(self):
        session, _, _ = self.store()
        other_session, other_cookies, _ = self.store("other")
        request = self.request(other_cookies, SessionStore(session.session_key))
        self.assertEqual(passphrase_storage.load(request, REPORT_UUID), "")
        self.assertNotIn(REPORT_UUID, request.session[passphrase_storage.SESSION_KEY])

    @override_settings(PASSPHRASE_SESSION_TTL=60)
    def test_entries_expire_after_inactivity(self):
        session, cookies, _ = self.store()
        request = self.request(cookies, SessionStore(session.session_key))
        with patch("callisto_core.delivery.passphrase_storage.time.time") as now:
            now.return_value = (
                session[passphrase_storage.SESSION_KEY][REPORT_UUID]["used"] + 61
            )
            self.assertEqual(passphrase_storage.load(request, REPORT_UUID), "")

    def test_cookie_is_httponly_and_strict(self):
        _, _, cookie = self.store()
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["max-age"], "")  # browser-session cookie

    def test_clear_removes_all_passphrases(self):
        session, cookies, _ = self.store()
        request = self.request(cookies, SessionStore(session.session_key))
        passphrase_storage.clear(request)
        self.assertEqual(passphrase_storage.load(request, REPORT_UUID), "")

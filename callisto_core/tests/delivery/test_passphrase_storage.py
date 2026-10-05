from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model, logout
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from callisto_core.delivery import passphrase_storage
from callisto_core.delivery.models import StoredPassphrase

User = get_user_model()

REPORT_UUID = "8d2b6a52-3c0f-4a43-9a37-1c4f2a1e7b11"
TAB_1_UUID = "1a1a1a1a-0000-4000-8000-000000000001"
TAB_2_UUID = "2b2b2b2b-0000-4000-8000-000000000002"


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

    def test_database_alone_cannot_recover_passphrase(self):
        session, _, _ = self.store()
        row = StoredPassphrase.objects.get(report_uuid=REPORT_UUID)
        self.assertNotIn(b"correct horse", bytes(row.encrypted_passphrase))
        self.assertNotIn("correct horse", str(SessionStore(session.session_key).load()))
        saved = SessionStore(session.session_key)
        self.assertEqual(
            passphrase_storage.load(self.request(session=saved), REPORT_UUID), ""
        )

    def test_wrong_cookie_key_is_rejected_and_entry_dropped(self):
        session, _, _ = self.store()
        other_session, other_cookies, _ = self.store("other")
        request = self.request(other_cookies, SessionStore(session.session_key))
        self.assertEqual(passphrase_storage.load(request, REPORT_UUID), "")
        self.assertFalse(
            StoredPassphrase.objects.filter(
                session_key=session.session_key, report_uuid=REPORT_UUID
            ).exists()
        )

    @override_settings(PASSPHRASE_SESSION_TTL=60)
    def test_entries_expire_after_inactivity(self):
        session, cookies, _ = self.store()
        request = self.request(cookies, SessionStore(session.session_key))
        used = StoredPassphrase.objects.get(report_uuid=REPORT_UUID).used
        with patch("callisto_core.delivery.passphrase_storage.timezone.now") as now:
            now.return_value = used + timedelta(seconds=61)
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

    def two_tabs(self, session_key, cookies):
        # both requests read the session before either writes
        tabs = [self.request(cookies, SessionStore(session_key)) for _ in range(2)]
        for tab in tabs:
            tab.session.keys()  # populates the cached copy
        return tabs

    def test_concurrent_stores_from_one_browser_keep_both(self):
        session, cookies, _ = self.store()
        tab_1, tab_2 = self.two_tabs(session.session_key, cookies)
        passphrase_storage.store(tab_1, TAB_1_UUID, "one")
        tab_1.session.save()
        passphrase_storage.store(tab_2, TAB_2_UUID, "two")
        tab_2.session.save()

        fresh = self.request(cookies, SessionStore(session.session_key))
        self.assertEqual(passphrase_storage.load(fresh, TAB_1_UUID), "one")
        self.assertEqual(passphrase_storage.load(fresh, TAB_2_UUID), "two")

    def test_concurrent_load_does_not_drop_new_store(self):
        session, cookies, _ = self.store()
        tab_1, tab_2 = self.two_tabs(session.session_key, cookies)
        passphrase_storage.store(tab_1, TAB_1_UUID, "one")
        tab_1.session.save()
        passphrase_storage.load(tab_2, REPORT_UUID)  # refreshes expiry
        tab_2.session.save()

        fresh = self.request(cookies, SessionStore(session.session_key))
        self.assertEqual(passphrase_storage.load(fresh, TAB_1_UUID), "one")

    def test_logout_removes_stored_passphrases(self):
        session, cookies, _ = self.store()
        request = self.request(cookies, SessionStore(session.session_key))
        request.user = User.objects.create_user(username="logout", password="x")
        logout(request)
        self.assertFalse(StoredPassphrase.objects.exists())

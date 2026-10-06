from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

import bcrypt

from django.contrib.auth.models import User
from django.urls import reverse

from callisto_core.accounts.auth import index
from callisto_core.accounts.models import Account
from callisto_core.notification import tasks as email_tasks
from callisto_core.tests import test_base
from callisto_core.utils.api import NotificationApi

EMAIL = "reset@example.com"


class PasswordResetTest(test_base.ReportFlowHelper):
    def setUp(self):
        super().setUp()
        self.client.logout()
        self.sent = []

        def capture(message):
            self.sent.append(message)
            return SimpleNamespace(status_code=200)

        patcher = patch.object(email_tasks, "_post_to_mailgun", side_effect=capture)
        patcher.start()
        self.addCleanup(patcher.stop)

    def request_reset(self, email=EMAIL):
        return self.client.post(reverse("reset"), {"email": email})

    def recipients(self):
        return [message["to"] for message in self.sent]

    def make_user(self, username, email="", **account):
        user = User.objects.create_user(
            username=username, password="a-long-pass-123!", email=email
        )
        Account.objects.create(user=user, site_id=1, **account)
        return user

    def encrypted_email(self, email=EMAIL):
        emailhash = sha256(email.encode("utf-8")).hexdigest()
        return {
            "encrypted_email": bcrypt.hashpw(
                emailhash.encode("utf-8"), bcrypt.gensalt()
            ).decode(),
            "email_index": index(emailhash),
        }

    def test_user_who_signed_up_with_email_gets_reset_email(self):
        self.client.post(
            reverse("signup"),
            {
                "username": "signedup",
                "password1": "a-long-pass-123!",
                "password2": "a-long-pass-123!",
                "email": EMAIL,
                "terms": "on",
            },
        )
        self.client.logout()
        self.request_reset()
        self.assertEqual(self.recipients(), [[EMAIL]])

    def test_email_match_ignores_case(self):
        self.make_user("plain", email=EMAIL)
        self.request_reset(EMAIL.upper())
        self.assertEqual(len(self.sent), 1)

    def test_encrypted_only_account_gets_reset_email(self):
        user = self.make_user("encrypted", **self.encrypted_email())
        self.request_reset()
        self.assertEqual(self.recipients(), [[EMAIL]])
        user.refresh_from_db()
        self.assertEqual(user.email, "")  # the plaintext isn't stored back

    def test_account_with_both_formats_gets_one_email(self):
        self.make_user("both", email=EMAIL, **self.encrypted_email())
        self.request_reset()
        self.assertEqual(len(self.sent), 1)

    def test_each_matching_account_gets_one_email(self):
        first = self.make_user("first", email=EMAIL)
        second = self.make_user("second", email=EMAIL)
        with patch.object(
            NotificationApi,
            "send_password_reset_email",
            wraps=NotificationApi.send_password_reset_email,
        ) as send:
            self.request_reset()
        users = [call.args[3]["user"] for call in send.call_args_list]
        self.assertCountEqual(users, [first, second])
        self.assertEqual(len(self.sent), 2)

    def test_unknown_email_sends_nothing(self):
        self.make_user("plain", email=EMAIL)
        response = self.request_reset("someone-else@example.com")
        self.assertIn(response.status_code, self.valid_statuses)
        self.assertEqual(self.sent, [])

    def test_inactive_user_gets_nothing(self):
        user = self.make_user("inactive", email=EMAIL)
        user.is_active = False
        user.save()
        self.make_user("inactive-encrypted", **self.encrypted_email())
        User.objects.filter(username="inactive-encrypted").update(is_active=False)
        self.request_reset()
        self.assertEqual(self.sent, [])

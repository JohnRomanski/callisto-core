from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from callisto_core.accounts.models import Account
from callisto_core.notification import tasks as email_tasks
from callisto_core.tests import test_base

SCHOOL_EMAIL = "someone@example.com"  # SCHOOL_EMAIL_DOMAIN is example.com


class SchoolEmailVerificationTest(test_base.ReportFlowHelper):
    def setUp(self):
        super().setUp()
        self.sent = []

        def post(message):
            self.sent.append(message)
            return SimpleNamespace(status_code=200)

        patcher = patch.object(email_tasks, "_post_to_mailgun", side_effect=post)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client_post_report_creation()

    def enter_school_email(self, email=SCHOOL_EMAIL):
        return self.client.post(
            reverse("reporting_email_confirmation", kwargs={"uuid": self.report.uuid}),
            {"email": email, "key": self.passphrase},
        )

    def test_sends_only_the_verification_email(self):
        response = self.enter_school_email()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            [message["subject"] for message in self.sent], ["Verify your student email"]
        )
        self.user.account.refresh_from_db()
        self.assertEqual(self.user.account.school_email, SCHOOL_EMAIL)

    def test_account_with_that_email_gets_no_password_reset(self):
        # entering someone's school email used to email them a reset link
        owner = User.objects.create_user(
            username="owner", password="a-long-pass-123!", email=SCHOOL_EMAIL
        )
        Account.objects.create(user=owner, site_id=1)
        self.enter_school_email()
        self.assertEqual(mail.outbox, [])
        self.assertEqual(len(self.sent), 1)

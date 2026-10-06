import contextlib
import io
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from callisto_core.delivery.model_helpers import GPGEncryptionError
from callisto_core.delivery.models import SentFullReport
from callisto_core.notification import tasks as email_tasks
from callisto_core.tests import test_base
from callisto_core.tests.utils.api import OwnTransportNotificationApi

COORDINATOR = "COORDINATOR_EMAIL@example.com"


class SchoolDeliveryTest(test_base.ReportFlowHelper):
    """A report counts as sent to the school only once Mailgun accepted it."""

    def setUp(self):
        super().setUp()
        self.sent = []
        self.failing = False

        def post(message):
            if self.failing and COORDINATOR in message["to"]:
                return SimpleNamespace(status_code=503)
            self.sent.append(message)
            return SimpleNamespace(status_code=200)

        patcher = patch.object(email_tasks, "_post_to_mailgun", side_effect=post)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.client_post_report_creation()
        self.client_post_report_prep()

    def to_coordinator(self):
        return [m for m in self.sent if COORDINATOR in m["to"]]

    def to_survivor(self):
        return [m for m in self.sent if self.report.contact_email in m["to"]]

    def submit(self, url_name="reporting_end_step"):
        return self.client.post(
            reverse(url_name, kwargs={"uuid": self.report.uuid}),
            data={"confirmation": True, "key": self.passphrase},
            follow=True,
        )

    def test_delivered_report_is_marked_sent(self):
        with patch.object(
            email_tasks.send_email, "delay", wraps=email_tasks.send_email.delay
        ) as queued:
            self.submit()
        self.report.refresh_from_db()
        self.assertIsNotNone(self.report.submitted_to_school)
        self.assertEqual(SentFullReport.objects.count(), 1)
        self.assertEqual(len(self.to_coordinator()), 1)
        self.assertEqual(len(self.to_survivor()), 1)  # submit confirmation
        # the school's copy is delivered, not queued
        for call in queued.call_args_list:
            self.assertNotIn(COORDINATOR, call.args[0]["to"])

    def test_mailgun_failure_records_nothing_and_tells_the_survivor(self):
        self.failing = True
        response = self.submit()
        self.assertContains(response, "nothing was sent")
        self.report.refresh_from_db()
        self.assertIsNone(self.report.submitted_to_school)
        self.assertFalse(SentFullReport.objects.exists())
        self.assertEqual(self.to_survivor(), [])  # no "submitted" confirmation

        self.failing = False  # Mailgun is back; the survivor tries again
        self.submit()
        self.report.refresh_from_db()
        self.assertIsNotNone(self.report.submitted_to_school)
        self.assertEqual(SentFullReport.objects.count(), 1)

    def test_encryption_failure_records_nothing(self):
        with patch(
            "callisto_core.notification.api.gpg_encrypt",
            side_effect=GPGEncryptionError("expired key"),
        ):
            response = self.submit()
        self.assertContains(response, "nothing was sent")
        self.report.refresh_from_db()
        self.assertIsNone(self.report.submitted_to_school)
        self.assertFalse(SentFullReport.objects.exists())
        self.assertEqual(self.sent, [])

    def test_resubmitting_sends_only_the_new_report(self):
        self.submit()
        self.submit("resubmit_end_step")
        self.assertEqual(SentFullReport.objects.count(), 2)
        # once per submission, not every earlier submission again
        self.assertEqual(len(self.to_coordinator()), 2)

    def test_report_contents_are_not_printed(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.submit()
        self.assertEqual(out.getvalue(), "")

    @override_settings(
        CALLISTO_NOTIFICATION_API=(
            "callisto_core.tests.utils.api.QueuingElsewhereNotificationApi"
        )
    )
    def test_custom_transport_that_only_queues_records_nothing(self):
        response = self.submit()
        self.assertContains(response, "nothing was sent")
        self.report.refresh_from_db()
        self.assertIsNone(self.report.submitted_to_school)
        self.assertFalse(SentFullReport.objects.exists())

    @override_settings(
        CALLISTO_NOTIFICATION_API=(
            "callisto_core.tests.utils.api.OwnTransportNotificationApi"
        )
    )
    def test_custom_transport_that_delivers_is_marked_sent(self):
        OwnTransportNotificationApi.sent = []
        self.submit()
        self.report.refresh_from_db()
        self.assertIsNotNone(self.report.submitted_to_school)
        self.assertTrue(OwnTransportNotificationApi.sent)
        self.assertEqual(self.sent, [])  # nothing went through Mailgun

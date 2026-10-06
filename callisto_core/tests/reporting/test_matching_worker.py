import json
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from kombu.exceptions import OperationalError

from django.core.management import call_command
from django.test import override_settings

from callisto_core.delivery.models import MatchEvent, MatchingJob, MatchReport, Report
from callisto_core.notification import tasks as email_tasks
from callisto_core.reporting import matching, tasks
from callisto_core.reporting.report_delivery import MatchReportContent
from callisto_core.tests.reporting.base import MatchSetup

IDENTIFIER = "https://www.facebook.com/someone"
TEMPLATE = "callisto_core/accounts/match_confirmation_callisto_team.html"


class MatchingTestBase(MatchSetup):
    def setUp(self):
        super().setUp()
        self.sent = []

        def capture(message):
            self.sent.append(message)
            return SimpleNamespace(status_code=200)

        patcher = patch.object(email_tasks, "_post_to_mailgun", side_effect=capture)
        patcher.start()
        self.addCleanup(patcher.stop)

    def enter(self, user):
        """A report entered into matching, without running matching."""
        report = Report(owner=user, contact_email=f"{user.username}@example.edu")
        report.encrypt_record({}, "key")
        content = MatchReportContent(
            identifier=IDENTIFIER, perp_name="p", email="e@example.com", phone="1"
        )
        MatchReport(report=report).encrypt_match_report(
            json.dumps(content.__dict__), IDENTIFIER
        )
        return report

    def subjects(self):
        return sorted(message["subject"] for message in self.sent)

    def new_job(self):
        return MatchingJob.objects.create(
            encrypted_identifier=matching._encrypt(IDENTIFIER),
            site_id=1,
            admin_email_template=TEMPLATE,
        )


class MatchingWorkerTest(MatchingTestBase):
    # the queue never sees the identifier

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_only_the_job_id_is_queued_after_commit(self):
        with patch.object(tasks.process_matching_job, "delay") as delay:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                job = matching.schedule(IDENTIFIER, 1, TEMPLATE)
            delay.assert_not_called()  # nothing is queued before the commit
            for callback in callbacks:
                callback()
        delay.assert_called_once_with(job.pk)
        self.assertNotIn(IDENTIFIER.encode(), bytes(job.encrypted_identifier))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_broker_outage_runs_matching_inline(self):
        self.enter(self.user1)
        self.enter(self.user2)
        with (
            patch.object(
                tasks.process_matching_job, "delay", side_effect=OperationalError
            ),
            patch.object(
                tasks.send_match_notifications, "delay", side_effect=OperationalError
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            matching.schedule(IDENTIFIER, 1, TEMPLATE)
        self.assertFalse(MatchingJob.objects.exists())
        self.assert_matches_found_true()
        # notifications ran inline too (their emails go to the broker, which
        # this test doesn't consume)
        event = MatchEvent.objects.get()
        self.assertIsNotNone(event.completed)
        self.assertTrue(event.authority_notified and event.owners_notified)

    # no lost matches or notifications

    def test_crash_before_commit_keeps_the_job_and_changes_nothing(self):
        self.enter(self.user1)
        self.enter(self.user2)
        job = self.new_job()
        with (
            patch.object(MatchEvent.objects, "create", side_effect=RuntimeError),
            self.assertRaises(RuntimeError),
        ):
            matching.process_job(job.pk)
        self.assertTrue(MatchingJob.objects.filter(pk=job.pk).exists())
        self.assert_matches_found_false()

        matching.process_job(job.pk)  # the retry finds the match
        self.assert_matches_found_true()
        self.assertEqual(MatchEvent.objects.count(), 1)

    def test_crash_after_match_before_notifying_is_recovered_by_sweep(self):
        self.enter(self.user1)
        self.enter(self.user2)
        job = self.new_job()
        with patch.object(tasks, "dispatch"):  # the worker dies before sending
            event = matching.process_job(job.pk)
        self.assert_matches_found_true()
        self.assertEqual(self.sent, [])

        matching.sweep(older_than=timedelta(0))
        self.assertEqual(
            self.subjects(),
            ["New Callisto Matches", "match_delivery"] + ["match_notification"] * 2,
        )
        event.refresh_from_db()
        self.assertIsNotNone(event.completed)
        self.assertEqual(bytes(event.encrypted_identifier), b"")

    def test_sending_twice_does_not_repeat_notifications(self):
        self.enter(self.user1)
        self.enter(self.user2)
        with patch.object(tasks, "dispatch"):
            event = matching.process_job(self.new_job().pk)
        matching.send_notifications(event.pk)
        count = len(self.sent)
        matching.send_notifications(event.pk)
        self.assertEqual(len(self.sent), count)

    def test_resumes_after_the_last_completed_step(self):
        self.enter(self.user1)
        self.enter(self.user2)
        with patch.object(tasks, "dispatch"):
            event = matching.process_job(self.new_job().pk)
        event.authority_notified = True  # sent before a crash
        event.save()
        matching.send_notifications(event.pk)
        self.assertNotIn("match_delivery", self.subjects())
        self.assertEqual(self.subjects().count("match_notification"), 2)

    def test_event_for_withdrawn_reports_completes_without_email(self):
        self.enter(self.user1)
        self.enter(self.user2)
        with patch.object(tasks, "dispatch"):
            event = matching.process_job(self.new_job().pk)
        MatchReport.objects.all().delete()
        matching.send_notifications(event.pk)
        self.assertEqual(self.sent, [])
        event.refresh_from_db()
        self.assertIsNotNone(event.completed)

    def test_no_match_leaves_no_job_or_event(self):
        self.enter(self.user1)
        matching.process_job(self.new_job().pk)
        self.assertFalse(MatchingJob.objects.exists())
        self.assertFalse(MatchEvent.objects.exists())

    def test_sweep_command(self):
        self.enter(self.user1)
        self.enter(self.user2)
        self.new_job()
        out = StringIO()
        call_command("process_pending_matches", older_than_minutes=0, stdout=out)
        self.assertIn("processed 1 matching jobs", out.getvalue())
        self.assert_matches_found_true()
        self.assertIn("match_delivery", self.subjects())


class MatchDeliveryTest(MatchingTestBase):
    """Steps are marked only once Mailgun has accepted their emails."""

    def event(self):
        self.enter(self.user1)
        self.enter(self.user2)
        with patch.object(tasks, "dispatch"):
            return matching.process_job(self.new_job().pk)

    def failing_for(self, subject):
        def post(message):
            if message["subject"] == subject:
                return SimpleNamespace(status_code=503)
            self.sent.append(message)
            return SimpleNamespace(status_code=200)

        return patch.object(email_tasks, "_post_to_mailgun", side_effect=post)

    def test_match_emails_are_delivered_not_queued(self):
        event = self.event()
        with patch.object(
            email_tasks.send_email, "delay", side_effect=AssertionError("queued")
        ):
            matching.send_notifications(event.pk)
        self.assertIn("match_delivery", self.subjects())

    def test_failed_delivery_keeps_the_step_pending(self):
        event = self.event()
        with (
            self.failing_for("match_delivery"),
            self.assertRaises(email_tasks.DeliveryFailed),
        ):
            matching.send_notifications(event.pk)
        event.refresh_from_db()
        self.assertFalse(event.authority_notified)
        self.assertIsNone(event.completed)
        self.assertNotEqual(bytes(event.encrypted_identifier), b"")  # kept for retry

        matching.send_notifications(event.pk)  # Mailgun is back
        event.refresh_from_db()
        self.assertIsNotNone(event.completed)
        self.assertEqual(self.subjects().count("match_delivery"), 1)

    def test_later_failure_keeps_earlier_steps_marked(self):
        event = self.event()
        with (
            self.failing_for("match_notification"),
            self.assertRaises(email_tasks.DeliveryFailed),
        ):
            matching.send_notifications(event.pk)
        event.refresh_from_db()
        self.assertTrue(event.authority_notified)
        self.assertFalse(event.owners_notified)

        matching.send_notifications(event.pk)
        # the school's delivery is not repeated
        self.assertEqual(self.subjects().count("match_delivery"), 1)
        self.assertEqual(self.subjects().count("match_notification"), 2)

    def test_sweep_continues_past_a_failing_item(self):
        self.enter(self.user1)
        self.enter(self.user2)
        MatchingJob.objects.create(
            encrypted_identifier=b"not decryptable", site_id=1, admin_email_template=""
        )
        good = self.new_job()
        with self.assertLogs(matching.logger, "ERROR"):
            jobs, events, failures = matching.sweep(older_than=timedelta(0))
        self.assertEqual((jobs, failures), (2, 1))
        self.assertFalse(MatchingJob.objects.filter(pk=good.pk).exists())
        self.assert_matches_found_true()

    @override_settings(
        CALLISTO_NOTIFICATION_API=(
            "callisto_core.tests.utils.api.QueuingElsewhereNotificationApi"
        )
    )
    def test_custom_transport_that_only_queues_keeps_steps_pending(self):
        event = self.event()
        with self.assertRaises(email_tasks.DeliveryFailed):
            matching.send_notifications(event.pk)
        event.refresh_from_db()
        self.assertFalse(event.authority_notified)
        self.assertIsNone(event.completed)

    def test_email_task_acknowledges_late(self):
        self.assertTrue(email_tasks.send_email.acks_late)
        self.assertTrue(email_tasks.send_email.reject_on_worker_lost)

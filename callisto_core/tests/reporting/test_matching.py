import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase

from callisto_core.delivery.models import MatchReport, Report, SentMatchReport
from callisto_core.notification import tasks
from callisto_core.reporting.api import CallistoCoreMatchingApi
from callisto_core.reporting.report_delivery import MatchReportContent
from callisto_core.tests.reporting.base import MatchSetup
from callisto_core.tests.test_base import ReportPostHelper
from callisto_core.tests.utils.api import CustomNotificationApi
from callisto_core.utils.api import MatchingApi

User = get_user_model()


class MatchDiscoveryTest(MatchSetup):
    def test_two_matching_reports_match(self):
        self.create_match(self.user1, "test1")
        self.create_match(self.user2, "test1")
        self.assert_matches_found_true()

    def test_non_matching_reports_dont_match(self):
        self.create_match(self.user1, "test1")
        self.create_match(self.user2, "test2")
        self.assert_matches_found_false()

    def test_matches_only_triggered_by_different_people(self):
        self.create_match(self.user1, "test1")
        self.create_match(self.user1, "test1")
        self.assert_matches_found_false()

    def test_multiple_matches(self):
        self.create_match(self.user1, "test1")
        self.create_match(self.user2, "test1")
        self.create_match(self.user3, "test1")
        self.create_match(self.user4, "test1")
        self.assert_matches_found_true()


class MatchIntegratedTest(MatchSetup, ReportPostHelper):
    fixtures = ["wizard_builder_data", "callisto_core_notification_data"]

    def _setup_matches(self):
        self.passphrase = "user 1 secret"
        self.client.login(username="test1", password="test")
        self.client_post_report_creation()
        # we pass in the default arg to client_post_matching_enter
        # just to make it totally clear that the same identifier
        # is being input twice
        self.client_post_matching_enter("https://www.facebook.com/callistoorg")

        self.passphrase = "user 2 secret"
        self.client.login(username="tset22", password="test")
        self.client_post_report_creation()
        self.client_post_matching_enter("https://www.facebook.com/callistoorg")

    def test_two_match_post_requests_trigger_matching(self):
        self._setup_matches()
        self.assert_matches_found_true()

    def test_school_receives_match_delivery_at_its_address(self):
        sent = []

        def capture(message):
            sent.append(message)
            return SimpleNamespace(status_code=200)

        with patch.object(tasks, "_post_to_mailgun", side_effect=capture):
            self._setup_matches()
        deliveries = [m for m in sent if m["subject"] == "match_delivery"]
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0]["to"], ["COORDINATOR_EMAIL@example.com"])
        self.assertEqual(len(deliveries[0]["attachments"]), 1)
        # the delivery record stores the full address too
        self.assertEqual(
            list(SentMatchReport.objects.values_list("to_address", flat=True)),
            ["COORDINATOR_EMAIL@example.com"],
        )

    def test_some_match_emails_sent(self):
        with patch.object(CustomNotificationApi, "log_action") as api_logging:
            self._setup_matches()
            self.assertGreaterEqual(api_logging.call_count, 1)


class MatchAlertingTest(MatchSetup):
    def test_existing_match_not_retriggered_by_same_reporter(self):
        self.create_match(self.user1, "test1")
        self.create_match(self.user2, "test1")
        matches = self.create_match(self.user2, "test1")
        self.assertFalse(matches)

    def test_triggers_new_matches_only(self):
        self.create_match(self.user1, "test1")
        self.create_match(self.user2, "test1")
        matches = self.create_match(self.user3, "test2")
        self.assertFalse(matches)


class ConcurrentMatchingTest(TransactionTestCase):
    # keep the sites and other migration data for the tests that run after
    serialized_rollback = True

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("needs row-level locks (select_for_update)")
        for username in ["concurrent1", "concurrent2"]:
            user = User.objects.create_user(username=username, password="test")
            report = Report(owner=user)
            report.encrypt_record({}, "key")
            content = MatchReportContent(
                identifier="test1", perp_name="test1", email="a@example.com", phone="1"
            )
            MatchReport(report=report).encrypt_match_report(
                json.dumps(content.__dict__), "test1"
            )

    def test_concurrent_submissions_trigger_match_once(self):
        # hold both submissions after decryption so they reach the
        # already-matched check at the same time
        barrier = threading.Barrier(2, timeout=30)
        decrypt = CallistoCoreMatchingApi._resolve_reports_decryptable_with_identifier

        def decrypt_then_wait(api, match_list):
            result = decrypt(api, match_list)
            barrier.wait()
            return result

        results, errors = [], []

        def submit():
            try:
                results.append(list(MatchingApi.find_matches("test1")))
            except Exception as error:
                errors.append(error)
            finally:
                connection.close()

        with patch.object(
            CallistoCoreMatchingApi,
            "_resolve_reports_decryptable_with_identifier",
            decrypt_then_wait,
        ):
            threads = [threading.Thread(target=submit) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(sorted(len(matches) for matches in results), [0, 2])
        self.assertTrue(all(Report.objects.values_list("match_found", flat=True)))


class MatchNotificationTest(MatchSetup, ReportPostHelper):
    """Who is emailed when reports enter matching, through the real views."""

    fixtures = ["wizard_builder_data", "callisto_core_notification_data"]
    identifier = "https://www.facebook.com/callistoorg"

    def setUp(self):
        super().setUp()
        self.sent = []

        def capture(message):
            self.sent.append(message)
            return SimpleNamespace(status_code=200)

        patcher = patch.object(tasks, "_post_to_mailgun", side_effect=capture)
        patcher.start()
        self.addCleanup(patcher.stop)

    def submit(self, user):
        """user creates a report and enters it into matching; returns subjects"""
        self.passphrase = f"{user.username} secret"
        self.client.force_login(user)
        self.client_post_report_creation()
        before = len(self.sent)
        self.client_post_matching_enter(self.identifier)
        return [message["subject"] for message in self.sent[before:]]

    def test_first_report_only_confirms_entry(self):
        self.assertEqual(self.submit(self.user1), ["match_confirmation"])

    def test_match_delivers_to_school_and_notifies_both_reporters(self):
        self.submit(self.user1)
        subjects = self.submit(self.user2)
        self.assertEqual(subjects.count("match_delivery"), 1)
        self.assertEqual(subjects.count("match_notification"), 2)
        self.assert_matches_found_true()

    def test_same_reporter_twice_is_not_a_match(self):
        self.submit(self.user1)
        self.assertEqual(self.submit(self.user1), ["match_confirmation"])

    def test_later_reporters_are_delivered_and_only_they_are_notified(self):
        self.submit(self.user1)
        self.submit(self.user2)
        for user in [self.user3, self.user4]:
            with self.subTest(user=user.username):
                subjects = self.submit(user)
                self.assertEqual(subjects.count("match_delivery"), 1)
                self.assertEqual(subjects.count("match_notification"), 1)

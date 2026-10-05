import json

from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.test import TestCase

from callisto_core.accounts.models import Account
from callisto_core.delivery.models import MatchReport, Report
from callisto_core.reporting.report_delivery import MatchReportContent
from callisto_core.utils.api import MatchingApi

User = get_user_model()


class MatchSetup(TestCase):
    fixtures = ["callisto_core_notification_data"]

    def setUp(self):
        self.site = Site.objects.get(id=1)
        self.site.domain = "testserver"
        self.site.save()
        self.user1 = User.objects.create_user(username="test1", password="test")
        self.user2 = User.objects.create_user(username="tset22", password="test")
        self.user3 = User.objects.create_user(username="tset333", password="test")
        self.user4 = User.objects.create_user(username="tset4444", password="test")
        for user in [self.user1, self.user2, self.user3, self.user4]:
            Account.objects.create(user=user, site_id=1)

    def assert_matches_found_true(self):
        self.assert_matches_found(self.assertTrue)

    def assert_matches_found_false(self):
        self.assert_matches_found(self.assertFalse)

    def assert_matches_found(self, assertion):
        for match in MatchReport.objects.all():
            assertion(match.match_found)

    def create_match(self, user, identifier):
        self.most_recent_report = Report(owner=user)
        self.most_recent_report.encrypt_record("test report 1", "key")
        match_report = MatchReport(report=self.most_recent_report)
        match_report_content = MatchReportContent(
            identifier=identifier,
            perp_name=identifier,
            email="test@example.com",
            phone="123",
        )
        match_report.encrypt_match_report(
            json.dumps(match_report_content.__dict__), identifier
        )

        matches = MatchingApi.find_matches(identifier)
        return matches

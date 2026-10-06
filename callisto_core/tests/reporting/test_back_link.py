from django.urls import reverse

from callisto_core.tests import test_base


class BackLinkTest(test_base.ReportFlowHelper):
    def setUp(self):
        super().setUp()
        self.client_post_report_creation()

    def page(self, url_name):
        url = reverse(url_name, kwargs={"uuid": self.report.uuid})
        return self.client_post_report_access(url)

    def test_back_to_a_page_without_a_report(self):
        # reporting_prep's back_url is the dashboard, which takes no uuid
        response = self.page("reporting_prep")
        self.assertContains(response, f'href="{reverse("dashboard")}">Back')

    def test_back_to_a_report_step(self):
        # reporting_end_step's back_url is reporting_matching_enter
        response = self.page("reporting_end_step")
        step = reverse("reporting_matching_enter", kwargs={"uuid": self.report.uuid})
        self.assertContains(response, f'href="{step}">Back')

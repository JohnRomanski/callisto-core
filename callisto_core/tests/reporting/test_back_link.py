from types import SimpleNamespace

from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings
from django.urls import path, re_path, reverse

from callisto_core.reporting.view_partials import _SubmissionPartial
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


urlpatterns = [
    re_path(r"^host/(?P<report_id>[^/]+)/$", lambda r, **kw: HttpResponse(), name="a"),
    re_path(r"^plain/([^/]+)/$", lambda r, *a: HttpResponse(), name="b"),
    path("home/", lambda r: HttpResponse(), name="c"),
]


@override_settings(ROOT_URLCONF=__name__)
class HostRouteBackLinkTest(SimpleTestCase):
    def back_link(self, back_url):
        view = _SubmissionPartial()
        view.back_url = back_url
        view.get_object = lambda: SimpleNamespace(uuid="1234")
        return view.back_link

    def test_route_naming_the_argument_differently(self):
        self.assertEqual(self.back_link("a"), "/host/1234/")

    def test_route_with_an_unnamed_argument(self):
        self.assertEqual(self.back_link("b"), "/plain/1234/")

    def test_route_without_an_argument(self):
        self.assertEqual(self.back_link("c"), "/home/")

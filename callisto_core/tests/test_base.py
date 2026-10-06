from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from callisto_core.accounts.models import Account
from callisto_core.delivery import models, passphrase_storage

User = get_user_model()


class ReportAssertionHelper:
    def assert_report_exists(self):
        return bool(models.Report.objects.filter(pk=self.report.pk).count())


class ReportPostHelper:
    valid_statuses = [200, 301, 302]
    username = "demo"
    password = "demo"

    def client_post_login(self):
        self.user = User.objects.create_user(
            username=self.username, password=self.password
        )

        url = reverse("login")

        data = {"username": self.username, "password": self.password}
        Account.objects.create(user=self.user, site_id=1)
        response = self.client.post(url, data, follow=True)
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_get_report_creation(self):
        url = reverse("report_new")
        response = self.client.get(url)
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_post_report_creation(self):
        self.client_get_report_creation()
        url = reverse("report_new")
        data = {"key": self.passphrase, "key_confirmation": self.passphrase}
        response = self.client.post(url, data, follow=True)
        self.report = response.context["report"]
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_get_report_delete(self):
        url = reverse("report_delete", kwargs={"uuid": self.report.uuid})
        response = self.client.get(url)
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_post_report_delete(self):
        self.client_get_report_delete()
        url = reverse("report_delete", kwargs={"uuid": self.report.uuid})
        data = {"key": self.passphrase}
        response = self.client.post(url, data, follow=True)
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_post_report_pdf_view(self, skip_assertions=False):
        url = reverse("report_pdf_view", kwargs={"uuid": self.report.uuid})
        data = {"key": self.passphrase}
        response = self.client.post(url, data, follow=True)
        if not skip_assertions:
            self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_get_review(self):
        url = reverse(
            "report_update", kwargs={"uuid": self.report.uuid, "step": "done"}
        )
        response = self.client.get(url)
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_post_answer_question(self):
        url = reverse("report_update", kwargs={"uuid": self.report.uuid, "step": "0"})
        self.data = {"question_3": "blanket ipsum pillowfight"}
        response = self.client.post(url, self.data, follow=True)
        self.assertIn(response.status_code, self.valid_statuses)
        self.report.refresh_from_db()
        self.assertEqual(
            self.decrypted_report["data"]["question_3"], self.data["question_3"]
        )
        return response

    def client_post_answer_second_page_question(self):
        url = reverse("report_update", kwargs={"uuid": self.report.uuid, "step": "1"})
        self.data = {"question_2": "cupcake ipsum catsmeow"}
        response = self.client.post(url, self.data, follow=True)
        self.assertIn(response.status_code, self.valid_statuses)
        self.report.refresh_from_db()
        self.assertEqual(
            self.decrypted_report["data"]["question_2"], self.data["question_2"]
        )
        return response

    def client_post_report_access(self, url):
        response = self.client.post(url, data={"key": self.passphrase}, follow=True)
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_post_report_prep(self):
        self.report_contact_email = self.school_email
        self.report_contact_phone = "555-555-5555"
        response = self.client.post(
            reverse("reporting_prep", kwargs={"uuid": self.report.uuid}),
            data={
                "contact_email": self.report_contact_email,
                "contact_phone": self.report_contact_phone,
            },
            follow=True,
        )
        self.report.refresh_from_db()
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_get_matching_enter_empty(self):
        url = reverse("reporting_matching_enter", kwargs={"uuid": self.report.uuid})
        response = self.client.get(url)
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_post_matching_enter_empty(self):
        self.client_get_matching_enter_empty()
        url = reverse("reporting_matching_enter", kwargs={"uuid": self.report.uuid})
        data = {"facebook_identifier": ""}
        response = self.client.post(url, data, follow=True)
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_get_matching_enter(self):
        url = reverse("matching_enter", kwargs={"uuid": self.report.uuid})
        response = self.client.get(url)
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_post_matching_withdraw(self):
        url = reverse("matching_withdraw", kwargs={"uuid": self.report.uuid})
        data = {"key": self.passphrase}
        response = self.client.post(url, data, follow=True)
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_post_matching_enter(
        self, identifier="https://www.facebook.com/callistoorg"
    ):
        url = reverse("matching_enter", kwargs={"uuid": self.report.uuid})
        data = {"facebook_identifier": identifier}
        response = self.client.post(url, data, follow=True)
        self.assertIn(response.status_code, self.valid_statuses)
        return response

    def client_post_reporting_end_step(self):
        response = self.client.post(
            reverse("reporting_end_step", kwargs={"uuid": self.report.uuid}),
            data={"confirmation": True, "key": self.passphrase},
            follow=True,
        )
        self.assertIn(response.status_code, self.valid_statuses)
        return response


class ReportFlowHelper(TestCase, ReportPostHelper, ReportAssertionHelper):
    passphrase = "super secret"
    school_email = "HUMAN_STUDENT_TOTALLY_NOT_A_WOLF@example.edu"
    fixtures = ["wizard_builder_data", "callisto_core_notification_data"]

    @property
    def decrypted_report(self):
        return self.report.decrypt_record(self.passphrase)

    def setUp(self):
        self._setup_sites()
        self._setup_user()

    def _setup_user(self):
        username = "testing_122"
        self.user = User.objects.create_user(username=username, password="testing_12")

        Account.objects.create(
            user=self.user, site_id=1, school_email=self.school_email
        )
        self.client.login(username=username, password="testing_12")

    def _setup_sites(self):
        self.site = Site.objects.get(id=1)
        self.site.domain = "testserver"
        self.site.save()

    def client_clear_passphrase(self):
        session_key = self.client.session.session_key
        models.StoredPassphrase.objects.filter(session_key=session_key).delete()

    def client_set_passphrase(self):
        # store the passphrase the way a passphrase form would, then hand the
        # resulting cookie key to the test client
        request = RequestFactory().get("/")
        request.session = self.client.session
        request.COOKIES = {
            name: morsel.value for name, morsel in self.client.cookies.items()
        }
        passphrase_storage.store(request, self.report.uuid, self.passphrase)
        request.session.save()
        response = passphrase_storage.set_cookie(request, HttpResponse())
        for name, morsel in response.cookies.items():
            self.client.cookies[name] = morsel.value

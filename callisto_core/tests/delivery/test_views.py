import json
from types import SimpleNamespace
from unittest.mock import patch

from django.urls import reverse

from callisto_core.delivery import forms, models, passphrase_storage, view_partials
from callisto_core.delivery.models import StoredPassphrase
from callisto_core.notification import tasks
from callisto_core.tests import test_base
from callisto_core.wizard_builder.forms import PageForm


class LegacyStorageFormatTest(test_base.ReportFlowHelper):
    def _setup_user(self, *args, **kwargs):
        pass

    def setUp(self):
        super().setUp()
        self.client_post_login()
        self.client.login(username=self.username, password=self.password)
        self.report = models.Report.objects.create(owner=self.user)
        legacy_storage = {"data": {"catte": "good"}}
        self.report.encrypt_record(legacy_storage, self.passphrase)
        self.client_set_passphrase()
        self.client_post_answer_question()  # prompt code to initialize storage
        self.report.refresh_from_db()
        self.storage = self.report.decrypt_record(self.passphrase)

    def test_form_data_populated(self):
        storage = self.storage
        self.assertTrue(storage.get("wizard_form_serialized", False))

    def test_legacy_data_key_used(self):
        storage = self.storage
        self.assertTrue(storage.get("data", False))

    def test_new_wizard_builder_key_not_used(self):
        storage = self.storage
        self.assertFalse(storage.get("wizard_form_data", False))


class NewReportFlowTest(test_base.ReportFlowHelper):
    def test_report_creation_renders_create_form(self):
        response = self.client.get(reverse("report_new"))
        form = response.context["form"]
        self.assertIsInstance(form, forms.ReportCreateForm)

    def test_report_creation_redirects_to_wizard_view(self):
        response = self.client_post_report_creation()
        uuid = response.context["report"].uuid
        self.assertEqual(
            response.redirect_chain[0][0],
            reverse("report_update", kwargs={"step": 0, "uuid": uuid}),
        )

    def test_report_creation_renders_wizard_form(self):
        response = self.client_post_report_creation()
        form = response.context["form"]
        self.assertIsInstance(form, PageForm)

    def test_report_creation_keeps_passphrase_encrypted_in_session(self):
        self.client_post_report_creation()
        stored = StoredPassphrase.objects.get()
        self.assertEqual(stored.report_uuid, self.report.uuid)
        # neither the stored row nor the session holds the plaintext passphrase
        self.assertNotIn(self.passphrase.encode(), bytes(stored.encrypted_passphrase))
        self.assertNotIn(self.passphrase, json.dumps(dict(self.client.session)))
        self.assertIn(passphrase_storage.COOKIE_NAME, self.client.cookies)

    def test_access_form_rendered_when_no_key_in_session(self):
        response = self.client_post_report_creation()
        uuid = response.context["report"].uuid
        page_1_path = reverse("report_update", kwargs={"step": 0, "uuid": uuid})
        self.client_clear_passphrase()

        response = self.client.get(page_1_path)
        form = response.context["form"]

        self.assertIsInstance(form, forms.ReportAccessForm)

    def test_can_reenter_passphrase(self):
        response = self.client_post_report_creation()
        uuid = response.context["report"].uuid
        page_1_path = reverse("report_update", kwargs={"step": 0, "uuid": uuid})
        self.client_clear_passphrase()

        response = self.client_post_report_access(page_1_path)
        self.assertRedirects(response, page_1_path)

    def test_access_form_returns_correct_report(self):
        response = self.client_post_report_creation()
        uuid = response.context["report"].uuid
        self.client_clear_passphrase()

        response = self.client_post_report_access(response.redirect_chain[0][0])

        self.assertEqual(response.context["report"].uuid, uuid)

    def test_report_not_accessible_with_incorrect_key(self):
        response = self.client_post_report_creation()
        self.client_clear_passphrase()

        self.passphrase = "wrong key"
        response = self.client_post_report_access(response.redirect_chain[0][0])
        form = response.context["form"]

        self.assertFalse(getattr(form, "decrypted_report", False))
        self.assertIsInstance(form, forms.ReportAccessForm)


class WizardRenderingTest(test_base.ReportFlowHelper):
    def test_choices_render_with_labels_and_extra_info(self):
        # the option template used a context variable Django 4 moved to
        # widget.wrap_label, which dropped every choice label
        self.client_post_report_creation()
        url = reverse("report_update", kwargs={"uuid": self.report.uuid, "step": "0"})
        html = self.client.get(url).content.decode()
        for choice in ["vegetables", "apples", "sugar"]:
            self.assertIn(choice, html)
        self.assertIn('placeholder="extra information here"', html)


class StoredPassphraseFlowTest(test_base.ReportFlowHelper):
    def test_answers_saved_across_steps_without_reentering_passphrase(self):
        self.client_post_report_creation()
        # neither post includes the passphrase; it comes from the session
        self.client_post_answer_question()
        self.client_post_answer_second_page_question()
        answers = self.decrypted_report["data"]
        self.assertEqual(answers["question_3"], "blanket ipsum pillowfight")
        self.assertEqual(answers["question_2"], "cupcake ipsum catsmeow")

    def test_without_cookie_key_passphrase_must_be_reentered(self):
        self.client_post_report_creation()
        del self.client.cookies[passphrase_storage.COOKIE_NAME]
        page = reverse("report_update", kwargs={"step": 0, "uuid": self.report.uuid})

        response = self.client.get(page)
        self.assertIsInstance(response.context["form"], forms.ReportAccessForm)

        response = self.client_post_report_access(page)
        self.assertNotIsInstance(response.context["form"], forms.ReportAccessForm)


class ReportMetaFlowTest(test_base.ReportFlowHelper):
    def test_report_action_passthrough_request(self):
        self.client_post_report_creation()
        self.assertTrue(self.report.pk)
        self.client_clear_passphrase()
        self.client_post_report_delete()
        self.assertFalse(self.assert_report_exists())

    def test_report_action_invalid_key(self):
        self.client_post_report_creation()
        self.assertTrue(self.report.pk)
        self.client_clear_passphrase()
        self.passphrase = "wrong key"
        self.client_post_report_delete()
        self.assertTrue(self.assert_report_exists())

    def test_report_delete(self):
        self.client_post_report_creation()
        self.assertTrue(self.report.pk)
        response = self.client_post_report_delete()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.assert_report_exists())

    def test_export_returns_pdf(self):
        self.client_post_report_creation()
        response = self.client_post_report_pdf_view()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get("Content-Disposition"), 'inline; filename="record.pdf"'
        )

    def test_export_does_not_modify_report(self):
        self.client_post_report_creation()
        self.report.refresh_from_db()
        last_edited, encrypted = self.report.last_edited, bytes(self.report.encrypted)
        self.client_post_report_pdf_view()
        self.report.refresh_from_db()
        self.assertEqual(self.report.last_edited, last_edited)
        self.assertEqual(bytes(self.report.encrypted), encrypted)

    def test_access_check_runs_once_per_request(self):
        # each evaluation derives the key with Argon2; dispatch used to run
        # the check twice
        self.client_post_report_creation()
        self.client_clear_passphrase()
        url = reverse("report_view", kwargs={"uuid": self.report.uuid})
        access_granted = view_partials._ReportAccessPartial.access_granted
        calls = []

        def counted(view):
            calls.append(view)
            return access_granted.fget(view)

        with patch.object(
            view_partials._ReportAccessPartial, "access_granted", property(counted)
        ):
            self.client.post(url, {"key": self.passphrase})
        self.assertEqual(len(calls), 1)

    def test_passphrase_form_on_review_page(self):
        self.client_post_report_creation()
        self.client_clear_passphrase()
        url = reverse("report_view", kwargs={"uuid": self.report.uuid})
        response = self.client.post(url, {"key": self.passphrase})
        self.assertEqual(response.status_code, 200)
        self.assertNotIsInstance(response.context["form"], forms.ReportAccessForm)

    def test_match_report_entry(self):
        self.client_post_report_creation()
        self.client_post_matching_enter()
        self.assertTrue(models.MatchReport.objects.filter(report=self.report).count())

    def test_match_report_withdrawl(self):
        self.client_post_report_creation()
        self.client_post_matching_enter()
        self.client_post_matching_withdraw()
        self.assertFalse(models.MatchReport.objects.filter(report=self.report).count())

    def test_report_prep_step(self):
        self.client_post_report_creation()
        self.client_post_report_prep()
        self.assertEqual(self.report_contact_email, self.report.contact_email)

    def test_matching_entry_confirms_to_contact_email(self):
        self.client_post_report_creation()
        self.client_post_report_prep()
        with patch.object(
            tasks, "_post_to_mailgun", return_value=SimpleNamespace(status_code=200)
        ) as post:
            self.client_post_matching_enter()
        messages = [call.args[0] for call in post.call_args_list]
        self.assertEqual(
            [(m["subject"], m["to"]) for m in messages],
            [("match_confirmation", [self.report_contact_email])],
        )

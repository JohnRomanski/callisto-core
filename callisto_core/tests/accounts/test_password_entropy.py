from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from callisto_core.accounts.validators import MinimumEntropyValidator, entropy_bits
from callisto_core.delivery.checks import check_password_entropy
from callisto_core.delivery.models import Report
from callisto_core.tests import test_base

WEAK = "password1234"
STRONG = "correct horse battery staple"


class EntropyValidatorTest(SimpleTestCase):
    def test_weak_password_is_rejected(self):
        with self.assertRaises(ValidationError):
            MinimumEntropyValidator().validate(WEAK)

    def test_strong_password_passes(self):
        MinimumEntropyValidator().validate(STRONG)

    @override_settings(PASSWORD_MINIMUM_ENTROPY=0)
    def test_zero_turns_the_check_off(self):
        MinimumEntropyValidator().validate(WEAK)

    def test_long_input_is_checked_not_rejected_by_zxcvbn(self):
        # zxcvbn raises above 72 characters unless told otherwise
        strong = "several unrelated words make a long passphrase " * 2  # 98
        MinimumEntropyValidator().validate(strong[:80])
        MinimumEntropyValidator().validate(strong + " and more words on the end")

    def test_long_but_repetitive_input_is_still_weak(self):
        with self.assertRaises(ValidationError):
            MinimumEntropyValidator().validate("a" * 150)

    def test_estimate_is_in_bits(self):
        self.assertLess(entropy_bits(WEAK), 35)
        self.assertGreater(entropy_bits(STRONG), 35)

    @override_settings(AUTH_PASSWORD_VALIDATORS=[])
    def test_warns_when_set_but_not_installed(self):
        self.assertEqual(
            [w.id for w in check_password_entropy(None)], ["callisto.W001"]
        )

    def test_no_warning_when_installed(self):
        self.assertEqual(check_password_entropy(None), [])


class EntropyInFormsTest(test_base.ReportFlowHelper):
    def test_signup_rejects_a_weak_password(self):
        self.client.logout()
        response = self.client.post(
            reverse("signup"),
            {"username": "new", "password1": WEAK, "password2": WEAK, "terms": "on"},
        )
        self.assertContains(response, "too easy to guess")

    def test_record_accepts_a_long_passphrase(self):
        passphrase = "a long passphrase made of many unrelated words " * 2 + "okay"
        self.assertGreater(len(passphrase), 72)
        count = Report.objects.count()
        self.client.post(
            reverse("report_new"),
            {"key": passphrase, "key_confirmation": passphrase},
        )
        self.assertEqual(Report.objects.count(), count + 1)

    def test_record_rejects_a_weak_passphrase(self):
        count = Report.objects.count()
        response = self.client.post(
            reverse("report_new"), {"key": WEAK, "key_confirmation": WEAK}
        )
        self.assertContains(response, "too easy to guess")
        self.assertEqual(Report.objects.count(), count)

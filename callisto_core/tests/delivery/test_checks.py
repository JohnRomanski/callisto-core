from django.test import SimpleTestCase, override_settings

from callisto_core.delivery.checks import check_callisto_secrets

SAFE = {
    "SECRET_KEY": "x" * 50,
    "INDEXING_KEY": "a1b2c3d4e5f6",
    "PEPPER": bytes(range(32)),
}


def error_ids(**overrides):
    with override_settings(**{**SAFE, **overrides}):
        return [error.id for error in check_callisto_secrets(None)]


class CallistoSecretsCheckTest(SimpleTestCase):
    def test_real_secrets_pass(self):
        self.assertEqual(error_ids(), [])

    def test_demo_secret_key_fails(self):
        self.assertEqual(error_ids(SECRET_KEY="secret key"), ["callisto.E001"])

    def test_placeholder_or_missing_indexing_key_fails(self):
        for value in ["notsettingthiswillbreakyou", "thisisatest", ""]:
            with self.subTest(value=value):
                self.assertEqual(error_ids(INDEXING_KEY=value), ["callisto.E002"])

    def test_pepper_must_be_32_bytes(self):
        for value in [b"short", "x" * 32, None]:
            with self.subTest(value=value):
                self.assertEqual(error_ids(PEPPER=value), ["callisto.E003"])

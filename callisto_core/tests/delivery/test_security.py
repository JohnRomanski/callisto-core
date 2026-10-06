import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import gnupg

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from callisto_core.delivery.model_helpers import GPGEncryptionError, gpg_encrypt
from callisto_core.delivery.models import Report
from callisto_core.tests import test_base
from callisto_core.tests.evaluation import test_keypair


class DecryptRateLimitTest(test_base.ReportFlowHelper):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.report = Report(owner=self.user)
        self.report.encrypt_record({}, self.passphrase)

    def test_passphrase_attempts_blocked_past_throttle_rate(self):
        limit = int(settings.DECRYPT_THROTTLE_RATE.split("/")[0])
        url = reverse("report_view", kwargs={"uuid": self.report.uuid})

        # django-ratelimit counts in clock-aligned windows; freeze its clock so
        # a slow run can't straddle a window edge and reset the count
        frozen = SimpleNamespace(time=lambda: 1_700_000_000.0)
        with patch("django_ratelimit.core.time", frozen):
            for _ in range(limit):
                response = self.client.post(url, {"key": "wrong passphrase"})
                self.assertNotEqual(response.status_code, 403)

            # even the correct passphrase is refused once the limit is hit
            response = self.client.post(url, {"key": self.passphrase})
            self.assertEqual(response.status_code, 403)


class GPGEncryptTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._gnupghome = tempfile.TemporaryDirectory()
        cls.gpg = gnupg.GPG(gnupghome=cls._gnupghome.name)
        key = cls.gpg.gen_key(
            cls.gpg.gen_key_input(
                key_type="EDDSA",
                key_curve="ed25519",
                subkey_type="ECDH",
                subkey_curve="cv25519",
                name_email="test@example.com",
                expire_date=0,
                no_protection=True,
            )
        )
        cls.public_key = cls.gpg.export_keys(key.fingerprint)

    @classmethod
    def tearDownClass(cls):
        cls._gnupghome.cleanup()
        super().tearDownClass()

    def test_encrypted_data_decrypts_with_private_key(self):
        encrypted = gpg_encrypt("report contents", self.public_key)
        self.assertTrue(encrypted.startswith(b"-----BEGIN PGP MESSAGE-----"))
        self.assertEqual(str(self.gpg.decrypt(encrypted)), "report contents")

    def test_invalid_key_raises_instead_of_returning_empty(self):
        with self.assertRaises(GPGEncryptionError):
            gpg_encrypt("report contents", "not a public key")

    def test_expired_key_raises_instead_of_returning_empty(self):
        # the old code sent an empty file here
        with self.assertRaises(GPGEncryptionError):
            gpg_encrypt("report contents", test_keypair.expired_public_test_key)

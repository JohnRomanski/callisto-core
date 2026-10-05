import base64
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes

import callisto_core.delivery.hashers as hashers


class KeyHasherFunctionsTest(TestCase):
    @override_settings(
        KEY_HASHERS=["callisto_core.delivery.hashers.BasePasswordHasher"]
    )
    def test_get_hashers_raises_improperly_configured_for_no_algorithm(self):
        with self.assertRaises(ImproperlyConfigured) as cm:
            hashers.get_hashers()
        ex = cm.exception
        self.assertEqual(
            str(ex),
            "hasher doesn't specify an algorithm name: "
            "callisto_core.delivery.hashers.BasePasswordHasher",
        )

    def test_get_hashers_returns_correct_hashers(self):
        hs = hashers.get_hashers()
        self.assertEqual(
            [type(h) for h in hs],
            [
                hashers.Argon2idKeyHasher,
                hashers.Argon2KeyHasher,
                hashers.PBKDF2KeyHasher,
            ],
        )

    def test_get_hasher_returns_correct_hasher(self):
        self.assertIs(type(hashers.get_hasher()), hashers.Argon2idKeyHasher)
        self.assertIs(type(hashers.get_hasher("argon2id")), hashers.Argon2idKeyHasher)
        self.assertIs(type(hashers.get_hasher("argon2")), hashers.Argon2KeyHasher)
        self.assertIs(
            type(hashers.get_hasher("pbkdf2_sha256")), hashers.PBKDF2KeyHasher
        )

    def test_get_hasher_raises_ValueError_on_unknown_algorithm(self):
        with self.assertRaises(ValueError) as cm:
            hashers.get_hasher("sha420_8^)")
        ex = cm.exception
        self.assertEqual(
            str(ex),
            "Unknown key hashing algorithm sha420_8^)."
            "Did you specify it in the KEY_HASHERS setting?",
        )

    def test_identify_hasher_returns_correct_hashers(self):
        hs = []
        # pbkdf2
        hs.append(hashers.identify_hasher(None))
        # pbkdf2
        hs.append(hashers.identify_hasher(""))
        hs.append(
            hashers.identify_hasher("pbkdf2_sha256$100$a_salt_probably")
        )  # pbkdf2
        hs.append(
            hashers.identify_hasher("argon2$argon2i$v=19$more,params$salt")
        )  # argon2
        self.assertIsInstance(hs.pop(), hashers.Argon2KeyHasher)
        self.assertIsInstance(hs.pop(), hashers.PBKDF2KeyHasher)
        self.assertIsInstance(hs.pop(), hashers.PBKDF2KeyHasher)
        self.assertIsInstance(hs.pop(), hashers.PBKDF2KeyHasher)


class PBKDF2KeyHasherTest(TestCase):
    def setUp(self):
        self.hasher = hashers.PBKDF2KeyHasher()

    def test_encode_requires_key_and_salt(self):
        # validation is inherited from django's PBKDF2PasswordHasher
        for key, salt in [
            (None, None),
            ("key", None),
            (None, "salt"),
            ("key", "salt$"),
        ]:
            with self.subTest(key=key, salt=salt):
                with self.assertRaises((TypeError, ValueError)):
                    self.hasher.encode(key, salt)

    def test_encode_returns_correct_prefix(self):
        encoded = self.hasher.encode(
            "this is definitely a key", "also here is a salt", iterations=142
        )
        prefix = encoded.rsplit("$", 1)[0]
        expected = "pbkdf2_sha256$142$also here is a salt"
        self.assertEqual(prefix, expected)

    def test_must_update_on_different_iterations(self):
        prefix = "pbkdf2_sha256${0}$thisisasalt"
        prefix_less = prefix.format(settings.KEY_ITERATIONS - 5)
        prefix_more = prefix.format(settings.KEY_ITERATIONS + 5)
        prefix_same = prefix.format(settings.KEY_ITERATIONS)
        self.assertTrue(self.hasher.must_update(prefix_less))
        self.assertTrue(self.hasher.must_update(prefix_more))
        self.assertFalse(self.hasher.must_update(prefix_same))

    def test_verify_encoded(self):
        encoded = self.hasher.encode("this is definitely a key", "yup that's salt")
        correct = self.hasher.verify("this is definitely a key", encoded)
        incorrect = self.hasher.verify("this is definitely not the right key", encoded)
        self.assertTrue(correct)
        self.assertFalse(incorrect)

    def test_split_encoded_returns_valid_prefix(self):
        encoded = self.hasher.encode(
            "Yet Another Test Key", "salt for humans", iterations=144
        )
        prefix, stretched = self.hasher.split_encoded(encoded)
        expected = "pbkdf2_sha256$144$salt for humans"
        self.assertEqual(prefix, expected)

    def test_stretched_key_is_32_bytes(self):
        encoded = self.hasher.encode(
            "Yet Another Test Key", "salt for humans", iterations=144
        )
        prefix, stretched = self.hasher.split_encoded(encoded)
        self.assertEqual(len(stretched), 32)


class Argon2KeyHasherTest(TestCase):
    def setUp(self):
        self.hasher = hashers.Argon2KeyHasher()

    def test_encode_requires_key_and_salt(self):
        for key, salt in [
            (None, None),
            ("key", None),
            (None, "salt"),
            ("key", "salt$"),
        ]:
            with self.subTest(key=key, salt=salt):
                with self.assertRaises(AssertionError):
                    self.hasher.encode(key, salt)

    def test_encode_returns_correct_prefix(self):
        encoded = self.hasher.encode("this is definitely a key", "also here is a salt")
        prefix = encoded.rsplit("$", 1)[0]
        b64_salt = (
            base64.b64encode(force_bytes("also here is a salt"))
            .decode("utf-8")
            .rstrip("=")
        )
        expected = f"argon2$argon2i$v=19$m=512,t=2,p=2${b64_salt}"
        self.assertEqual(prefix, expected)

    def test_verify_encoded(self):
        encoded = self.hasher.encode("this is definitely a key", "wow that's salty")
        correct = self.hasher.verify("this is definitely a key", encoded)
        incorrect = self.hasher.verify(
            "nope this isn't the key idk what this is", encoded
        )
        self.assertTrue(correct)
        self.assertFalse(incorrect)

    def test_split_encoded_returns_correct_prefix(self):
        encoded = self.hasher.encode("this is definitely a key", "also here is a salt")
        prefix, stretched = self.hasher.split_encoded(encoded)
        expected = "argon2$argon2i$v=19$m=512,t=2,p=2$also here is a salt"
        self.assertEqual(prefix, expected)

    def test_split_encoded_returns_valid_prefix(self):
        encoded = self.hasher.encode("Yet Another Test Key", "salt for humans")
        prefix, stretched = self.hasher.split_encoded(encoded)
        expected = "argon2$argon2i$v=19$m=512,t=2,p=2$salt for humans"
        self.assertEqual(prefix, expected)

    def test_stretched_key_is_32_bytes(self):
        encoded = self.hasher.encode("Yet Another Test Key", "salt for humans")
        prefix, stretched = self.hasher.split_encoded(encoded)
        self.assertEqual(len(stretched), 32)


class StoredParametersTest(TestCase):
    """Existing records must decrypt after the hashing settings change."""

    def make_records(self):
        from django.contrib.auth import get_user_model

        from callisto_core.delivery.models import MatchReport, Report

        user = get_user_model().objects.create_user(username="params", password="x")
        report = Report(owner=user)
        report.encrypt_record({"answer": "kept"}, "report passphrase")
        match = MatchReport(report=report)
        match.encrypt_match_report("match text", "identifier")
        return Report.objects.get(pk=report.pk), MatchReport.objects.get(pk=match.pk)

    def test_records_decrypt_after_argon2_settings_change(self):
        report, match = self.make_records()
        with (
            patch.object(hashers.Argon2KeyHasher, "memory_cost", 1024),
            patch.object(hashers.Argon2KeyHasher, "time_cost", 3),
        ):
            self.assertEqual(
                report.decrypt_record("report passphrase"), {"answer": "kept"}
            )
            self.assertEqual(match.get_match("identifier"), "match text")

    def test_new_records_use_argon2id_with_settings_params(self):
        report, match = self.make_records()
        for prefix in [report.encode_prefix, match.encode_prefix]:
            self.assertTrue(prefix.startswith("argon2id$argon2id$v=19$"))
            self.assertIn(
                f"m={settings.ARGON2ID_MEMORY_COST},"
                f"t={settings.ARGON2ID_TIME_COST},"
                f"p={settings.ARGON2ID_PARALLELISM}",
                prefix,
            )

    def test_argon2id_records_decrypt_after_settings_change(self):
        report, match = self.make_records()
        with override_settings(
            ARGON2ID_MEMORY_COST=settings.ARGON2ID_MEMORY_COST * 2,
            ARGON2ID_TIME_COST=settings.ARGON2ID_TIME_COST + 1,
        ):
            self.assertEqual(
                report.decrypt_record("report passphrase"), {"answer": "kept"}
            )
            self.assertEqual(match.get_match("identifier"), "match text")

    def test_resaving_upgrades_legacy_argon2i_record(self):
        from callisto_core.delivery.models import Report

        report, _ = self.make_records()
        with patch.object(
            hashers,
            "get_hasher",
            lambda algorithm="default": (
                hashers.Argon2KeyHasher()
                if algorithm in ("default", "argon2")
                else hashers.get_hashers_by_algorithm()[algorithm]
            ),
        ):
            report.encrypt_record({"answer": "kept"}, "report passphrase")
        self.assertTrue(report.encode_prefix.startswith("argon2$argon2i$"))

        report = Report.objects.get(pk=report.pk)
        data = report.decrypt_record("report passphrase")
        report.encrypt_record(data, "report passphrase")
        self.assertTrue(report.encode_prefix.startswith("argon2id$"))
        self.assertEqual(report.decrypt_record("report passphrase"), {"answer": "kept"})


class Argon2idDefaultsTest(TestCase):
    def test_defaults_are_owasp_minimum(self):
        with override_settings():
            del settings.ARGON2ID_MEMORY_COST
            del settings.ARGON2ID_TIME_COST
            del settings.ARGON2ID_PARALLELISM
            params = hashers.Argon2idKeyHasher().current_params()
        self.assertEqual(
            params, {"memory_cost": 19 * 1024, "time_cost": 2, "parallelism": 1}
        )

    def test_demo_settings_use_owasp_minimum(self):
        from callisto_core.utils import settings as demo_settings

        self.assertEqual(demo_settings.ARGON2ID_MEMORY_COST, 19 * 1024)
        self.assertEqual(demo_settings.ARGON2ID_TIME_COST, 2)

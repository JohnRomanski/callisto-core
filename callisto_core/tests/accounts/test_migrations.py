from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

migration = import_module(
    "callisto_core.accounts.migrations.0006_remove_encrypted_identity"
)


class RestorePlaintextLoginTest(TestCase):
    # runs 0006's data step against the current models; a MigrationTest here
    # would flush the database and break later serialized_rollback tests

    def test_unsafe_suffix_is_removed(self):
        # as the old 0005 left them
        User.objects.create(username="jane:unsafe", email="jane@example.com:unsafe")
        User.objects.create(username="taken:unsafe")
        User.objects.create(username="taken")  # registered after the old 0005
        User.objects.create(username="plain", email="plain@example.com")

        with self.assertLogs(migration.logger, "ERROR"):
            migration.restore_plaintext_login(apps, None)

        self.assertEqual(
            sorted(User.objects.values_list("username", "email")),
            [
                ("jane", "jane@example.com"),
                ("plain", "plain@example.com"),
                ("taken", ""),
                ("taken:unsafe", ""),  # left for an admin rather than clash
            ],
        )

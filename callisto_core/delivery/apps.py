from django.apps import AppConfig


class DeliveryConfig(AppConfig):
    name = "callisto_core.delivery"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        from . import (  # noqa: F401
            checks,  # registers deploy checks
            passphrase_storage,  # connects logout cleanup
        )

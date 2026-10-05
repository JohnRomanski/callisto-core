from django.apps import AppConfig


class DeliveryConfig(AppConfig):
    name = "callisto_core.delivery"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        from . import passphrase_storage  # noqa: F401  (connects logout cleanup)

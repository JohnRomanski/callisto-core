from django.apps import AppConfig


# TODO: smell this app config
class WizardBuilderConfig(AppConfig):
    name = "callisto_core.wizard_builder"
    verbose_name = "Wizard Builder"
    default_auto_field = "django.db.models.AutoField"

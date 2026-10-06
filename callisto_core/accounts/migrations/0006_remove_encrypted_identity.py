import logging

from django.conf import settings
from django.db import migrations

logger = logging.getLogger(__name__)

SUFFIX = ":unsafe"


def restore_plaintext_login(apps, schema_editor):
    """Undo the old 0005, which appended SUFFIX to usernames and emails."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    for user in User.objects.filter(username__endswith=SUFFIX):
        username = user.username.removesuffix(SUFFIX)
        if User.objects.filter(username=username).exists():
            # someone registered the bare name since; leave this one for an admin
            logger.error(f"user {user.pk}: username taken, left with {SUFFIX!r}")
            continue
        user.username = username
        user.save(update_fields=["username"])
    for user in User.objects.filter(email__endswith=SUFFIX):
        user.email = user.email.removesuffix(SUFFIX)
        user.save(update_fields=["email"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_invalidate_unencrypted_data"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            restore_plaintext_login, reverse_code=migrations.RunPython.noop
        ),
        migrations.RemoveField(model_name="account", name="email_index"),
        migrations.RemoveField(model_name="account", name="encrypted_email"),
        migrations.RemoveField(model_name="account", name="encrypted_username"),
        migrations.RemoveField(model_name="account", name="username_index"),
    ]

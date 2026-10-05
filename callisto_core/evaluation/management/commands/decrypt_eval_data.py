import json
import logging
import tempfile

import gnupg

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand

from ...models import EvalRow

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "decrypts eval data. can only be run in local environments (import data from prod)"

    def _write_to_file(self, data):
        with open("eval_data.json", "w") as data_file:
            json.dump(data, data_file)
        logger.info("Decrypted eval data written to eval_data.json")

    def _decrypt(self, gpg):
        decrypted_eval_data = []
        for row in EvalRow.objects.all():
            decrypted_row = {
                "pk": row.pk,
                "user": row.user_identifier,
                "record": row.record_identifier,
                "action": row.action,
                "timestamp": row.timestamp.__str__(),
            }
            decrypted = gpg.decrypt(bytes(row.row))
            if decrypted.ok:
                decrypted_row.update(json.loads(str(decrypted)))
            else:
                logger.warning(
                    f"could not decrypt eval row {row.pk}: {decrypted.status}"
                )
            decrypted_eval_data.append(decrypted_row)
        return decrypted_eval_data

    def handle(self, *args, **kwargs):
        if not settings.CALLISTO_EVAL_PRIVATE_KEY:
            raise ImproperlyConfigured("CALLISTO_EVAL_PRIVATE_KEY not present")
        with tempfile.TemporaryDirectory() as gnupghome:
            gpg = gnupg.GPG(gnupghome=gnupghome)
            gpg.import_keys(settings.CALLISTO_EVAL_PRIVATE_KEY)
            self._write_to_file(self._decrypt(gpg))

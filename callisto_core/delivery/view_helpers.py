"""

View helpers contain functionality shared between several view partials.
None of these classes provide full view functionality.

docs / reference:
    - https://github.com/project-callisto/callisto-core/blob/master/callisto_core/wizard_builder/view_helpers.py

"""

import logging

from django.urls import reverse

from callisto_core.wizard_builder import view_helpers as wizard_builder_helpers

from . import passphrase_storage

logger = logging.getLogger(__name__)


class _MockReport:
    uuid = None


class ReportStepsHelper(wizard_builder_helpers.StepsHelper):
    def url(self, step):
        return reverse(
            self.view.request.resolver_match.view_name,
            kwargs={"step": step, "uuid": self.view.report.uuid},
        )


class ReportStorageHelper:
    def __init__(self, view):
        self.view = view  # TODO: scope down input

    _passphrase = None

    @property
    def passphrase(self) -> str:
        """The passphrase set on this helper, else the one kept in the session"""
        if self._passphrase is not None:
            return self._passphrase
        report_uuid = getattr(self.report, "uuid", None)
        if not report_uuid:
            return ""
        return passphrase_storage.load(self.view.request, report_uuid)

    @passphrase.setter
    def passphrase(self, value):
        self._passphrase = value

    @property
    def report(self):
        try:
            return self.view.report
        except BaseException:
            return _MockReport

    def decrypt_report(self, passphrase) -> dict:
        self.passphrase = passphrase
        return self.report.decrypt_record(passphrase)

    def set_passphrase(self, key, report=None):
        report = report or self.report
        passphrase_storage.store(self.view.request, report.uuid, key)

    def clear_passphrases(self):
        passphrase_storage.clear(self.view.request)


class _LegacyReportStorageHelper(ReportStorageHelper):
    def _initialize_storage(self):
        if not self.report.encrypted:
            self._create_new_report_storage()
        elif self._report_is_legacy_format():
            self._translate_legacy_report_storage()
        else:
            pass  # storage already initialized

    def _report_is_legacy_format(self) -> bool:
        decrypted_report = self.report.decrypt_record(self.passphrase)
        return bool(not decrypted_report.get(self.storage_form_key, False))

    def _create_new_report_storage(self):
        self.report.encryption_setup(self.passphrase)
        self._create_storage({})

    def _translate_legacy_report_storage(self):
        decrypted_report = self.report.decrypt_record(self.passphrase)
        self._create_storage(decrypted_report[self.storage_data_key])
        logger.debug("translated legacy report storage")

    def _create_storage(self, data):
        storage = {
            self.storage_data_key: data,
            self.storage_form_key: self.serialized_forms,
        }
        self.report.encrypt_record(storage, self.passphrase)


class EncryptedReportStorageHelper(
    wizard_builder_helpers.StorageHelper, _LegacyReportStorageHelper
):
    # WARNING: do not change! record data is keyed on this value
    storage_data_key = "data"

    @classmethod
    def empty_storage(cls) -> dict:
        return {cls.storage_data_key: {}, cls.storage_form_key: {}}

    def current_data_from_storage(self) -> dict:
        if self.passphrase:
            return self.report.decrypt_record(self.passphrase)
        else:
            return self.empty_storage()

    def add_data_to_storage(self, data):
        if self.passphrase:
            storage = self.current_data_from_storage()
            storage[self.storage_data_key] = data
            self.report.encrypt_record(storage, self.passphrase)

    def init_storage(self):
        if self.passphrase:
            self._initialize_storage()

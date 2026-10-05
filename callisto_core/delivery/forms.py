import json
import logging
import os

import pyseto
from nacl.exceptions import CryptoError

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model

from callisto_core.utils.forms import NoRequiredLabelMixin

from . import fields, models

logger = logging.getLogger(__name__)
User = get_user_model()


def passphrase_field(label):
    return forms.CharField(
        max_length=64,
        label=label,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "off", "class": "form-control"}
        ),
    )


def _generate_token(form):
    # PASETO_PRIVATE_KEY is a libsodium Ed25519 secret key: 32-byte seed + public key
    seed = bytes.fromhex(os.environ["PASETO_PRIVATE_KEY"])[:32]
    key = pyseto.Key.from_asymmetric_key_params(version=2, d=seed)
    claims = {
        "user": str(form.view.request.user.account.uuid),
        "partner": settings.DATABASES["default"]["SCHEMA"],
    }
    token = pyseto.encode(key, claims, serializer=json, exp=300)
    return token.decode("utf-8")


class FormViewExtensionMixin:
    def __init__(self, *args, **kwargs):
        self.view = kwargs.pop("view")  # TODO: pass in something more specific
        if kwargs.get("matching_validators"):
            kwargs.pop("matching_validators")  # TODO: remove
        if kwargs.get("school_email_domain"):  # TODO: remove
            kwargs.pop("school_email_domain")
        super().__init__(*args, **kwargs)


class ReportBaseForm(
    NoRequiredLabelMixin, FormViewExtensionMixin, forms.models.ModelForm
):
    key = fields.PassphraseField(label="Passphrase")
    # rendered for client-side use of the Callisto API; the server never reads
    # them back, so posts that leave them out (report actions) are still valid
    token = forms.CharField(widget=forms.HiddenInput(), required=False)
    uuid = forms.CharField(widget=forms.HiddenInput(), required=False)
    endpoint = forms.CharField(
        widget=forms.HiddenInput(),
        initial=settings.CALLISTO_API_ENDPOINT,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["token"] = _generate_token(self)
        self.initial["uuid"] = str(self.instance.uuid)

    @property
    def report(self):
        return self.instance

    def save(self, *args, **kwargs):
        report = super().save(*args, **kwargs)
        if self.data.get("key"):
            self.view.storage.set_passphrase(self.data["key"], report=report)
        return report

    class Meta:
        model = models.Report
        fields = []


class ReportCreateForm(ReportBaseForm):
    message_confirmation_error = "passphrase and passphrase confirmation must match"
    key_confirmation = fields.PassphraseField(label="Confirm Passphrase")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.view.request.user
        if isinstance(user, User):
            self.instance.owner = user

    def clean_key_confirmation(self):
        key = self.data.get("key")
        key_confirmation = self.data.get("key_confirmation")
        if key != key_confirmation:
            raise forms.ValidationError(self.message_confirmation_error)
        else:
            return key_confirmation


class ReportAccessForm(ReportBaseForm):
    message_key_error = "Invalid passphrase"
    message_key_error_log = "decryption failure on {}"

    def clean_key(self):
        try:
            return self._decrypt_report()
        except CryptoError:
            return self._decryption_failed()

    def _decrypt_report(self):
        self.decrypted_report = self.report.decrypt_record(self.data["key"])
        return self.data["key"]

    def _decryption_failed(self):
        logger.info(self.message_key_error_log.format(self.report.uuid))
        raise forms.ValidationError(self.message_key_error)

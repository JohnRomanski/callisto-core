import copy
import logging
import os

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, Spacer

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.template import Context, Template
from django.template.loader import get_template
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from callisto_core.delivery.model_helpers import gpg_encrypt
from callisto_core.notification import tasks
from callisto_core.reporting.report_delivery import (
    PDFFullReport,
    PDFMatchReport,
    PDFUserReviewReport,
)
from callisto_core.utils.api import TenantApi

logger = logging.getLogger(__name__)


def _address_list(to_addresses):
    """Accepts one address string or a list; returns a list."""
    if isinstance(to_addresses, str):
        return [to_addresses]
    return list(to_addresses)


class CallistoCoreNotificationApi:
    report_filename = "callisto_record_{0}.pdf.gpg"
    report_title = "Callisto Record"
    logo_path = "../../assets/callisto_logo.png"

    # utilities

    @property
    def ALERT_LIST(self):
        return ["tech@projectcallisto.org"]

    @property
    def model(self):
        from callisto_core.notification.models import EmailNotification

        return EmailNotification

    @property
    def site_id(self):
        return self.context["site_id"]

    @property
    def models_on_site(self):
        site_id = self.context.get("site_id")
        name = self.context["notification_name"]
        models = self.model.objects.on_site(site_id).filter(name=name)
        if len(models) != 1:
            logger.error(
                f'{self.model.__name__}(site_id={site_id}, name="{name}") should equal 1, was {len(models)}'
            )
        return models

    @property
    def from_email(self):
        return '"Callisto" <noreply@mail.callistocampus.org>'

    @property
    def in_demo_mode(self):
        return self.context.get("DEMO_MODE", False)

    def prepend_subject_if_demo_mode(self, subject):
        if self.in_demo_mode:
            return f"[DEMO] {subject}"
        else:
            return subject

    def user_site_id(self, user):
        return user.account.site_id

    def split_addresses(self, addresses):
        if isinstance(addresses, str):
            return [x.strip() for x in addresses.split(",")]
        else:
            return addresses

    def get_cover_page(self, report_id, recipient):
        # title = f"{self.report_title} No.: {report_id}"

        styles = getSampleStyleSheet()
        headline_style = styles["Heading1"]
        headline_style.alignment = TA_CENTER
        headline_style.fontSize = 48
        subtitle_style = styles["Heading2"]
        subtitle_style.fontSize = 24
        subtitle_style.leading = 26
        subtitle_style.alignment = TA_CENTER

        CoverPage = []
        logo = os.path.join(settings.BASE_DIR, self.logo_path)

        image = Image(logo, 3 * inch, 3 * inch)
        CoverPage.append(image)
        CoverPage.append(Spacer(1, 18))
        CoverPage.append(Paragraph("CONFIDENTIAL", headline_style))
        # paragraph = Paragraph(
        #     f"Intended for: {recipient}, Title IX Coordinator", subtitle_style)
        # CoverPage.append(paragraph)
        CoverPage.append(PageBreak())
        return CoverPage

    # entrypoints

    def slack_notification(
        self,
        msg: str,  # slack message
        channel="",  # slack channel
        type="",  # for test assertions
    ):
        pass

    def send_with_kwargs(self, **kwargs):
        self.context = {**kwargs}
        self.send()

    def send_confirmation(
        self, email_type: str, to_addresses: list[str], site_id=0, **kwargs
    ) -> None:
        """
        Send a matching or submission confirmation email to the user

        email_type default valid options:
            'match_confirmation'
            'submit_confirmation'

        Called if an email confirmation is requested
        """
        self.context = {
            "notification_name": email_type,
            "to_addresses": to_addresses,
            "site_id": site_id,
            **kwargs,
        }
        self.send()

    def send_report_to_authority(
        self,
        sent_report,
        to_addresses: list[str],
        report_data: dict,
        public_key: str,
        site_id=0,
        **kwargs,
    ) -> None:
        """
        Send new full report to the reporting coordinator

        Called at the end of the "reporting" flow. Returns only once the email
        was accepted for delivery, and only then records the report as
        submitted; raises tasks.DeliveryFailed (or GPGEncryptionError) otherwise.
        """
        to_addresses = _address_list(to_addresses)
        self.context = {
            "notification_name": "report_delivery",
            "to_addresses": to_addresses,
            "site_id": site_id,
            **kwargs,
        }
        self._notification_with_full_report(
            sent_report, report_data, public_key, to_addresses
        )
        with tasks.delivering_synchronously():
            self.send()

        # reached only if generation and delivery worked
        sent_report.report.submitted_to_school = timezone.now()
        sent_report.report.save()

    def send_password_reset_email(
        self, form, subject_template_name, email_template_name, context, *args, **kwargs
    ):
        # PasswordResetForm.save calls this once per matching user
        user = context["user"]
        self.send_with_kwargs(
            site_id=user.account.site_id,
            to_addresses=[context["email"]],
            email_subject="Reset your password",
            email_name="password_reset_email",
            uid=context["uid"],
            protocol=context["protocol"],
            email_template_name=email_template_name,
            user=user,
            token=context["token"],
        )

    def send_account_activation_email(self, user, email):
        # sent from the admin, outside a request: domain and protocol come
        # from set_domain / set_protocol, like any other email
        self.send_with_kwargs(
            email_template_name="callisto_core/accounts/account_activation_email.html",
            to_addresses=[email],
            site_id=user.account.site_id,
            user=user,
            uid=urlsafe_base64_encode(force_bytes(user.pk)),
            token=default_token_generator.make_token(copy.copy(user)),
            email_subject="Keep Our Community Safe with Callisto",
            email_name="account_activation_email",
        )

    def send_matching_report_to_authority(
        self,
        matches: list,
        identifier: str,
        to_addresses: list[str],
        public_key: str,
    ):
        """
        Notifies coordinator that a match has been found

        Assumes all matches are on the same site

        Called during a successful matching run. Returns only once the email
        was accepted for delivery; raises tasks.DeliveryFailed otherwise.
        """
        to_addresses = _address_list(to_addresses)
        user = matches[0].report.owner

        self.context = {
            "notification_name": "match_delivery",
            "to_addresses": to_addresses,
            "site_id": self.user_site_id(user),
            "user": user,
        }
        self._notification_with_match_report(
            matches, identifier, to_addresses, public_key
        )
        with tasks.delivering_synchronously():
            self.send()

    def send_match_notification(self, match_report):
        """
        Notifies reporting user that a match has been found.

        Called during a successful matching run

        Args:
            user(User): reporting user
            match_report(MatchReport): MatchReport for which
                a match has been found
        """
        user = match_report.report.owner
        self.send_with_kwargs(
            notification_name="match_notification",
            to_addresses=[match_report.report.contact_email],
            site_id=self.user_site_id(user),
            report=match_report.report,
            user=user,
        )

    def send_user_review_nofication(
        self,
        reports: list,
        matches: list,
        to_addresses: list[str],
        public_key: str,
        site_id: int,
    ):
        self.context = {
            "email_template_name": "callisto_core/notification/user_review.html",
            "email_subject": "Callisto Report Review Notification",
            "to_addresses": to_addresses,
            "site_id": site_id,
        }
        report_file = PDFUserReviewReport.generate(
            {"reports": reports, "matches": matches}
        )
        self._notification_with_report("", report_file, public_key)
        self.send()

    # report attachment

    def _notification_with_full_report(
        self, sent_report, report_data, public_key, to_addresses
    ):
        report_id = sent_report.get_report_id()
        report_pdf_class = PDFFullReport(sent_report.report, report_data)
        report_file = report_pdf_class.generate_pdf_report(report_id, to_addresses)

        self._notification_with_report(report_id, report_file, public_key)

    def _notification_with_match_report(
        self, matches, identifier, to_addresses, public_key
    ):
        # TODO: make match _notification_with_full_report more closely
        from callisto_core.delivery.models import SentMatchReport

        sent_match_report = SentMatchReport.objects.create(
            to_address=self.context["to_addresses"][0]
        )
        sent_match_report.reports.add(*matches)
        sent_match_report.save()

        report_id = sent_match_report.get_report_id()
        report_pdf = PDFMatchReport(matches, identifier)
        report_file = report_pdf.generate_match_report(report_id, to_addresses)

        self._notification_with_report(report_id, report_file, public_key)

    # entrypoint helpers

    def _notification_with_report(self, report_id, report_file, public_key):
        report_file = self._encrypt_file(report_file, public_key)
        attachment = (
            self.report_filename.format(report_id),
            report_file,
            "application/octet-stream",
        )
        self.context.update({"attachment": attachment})

    def _encrypt_file(self, file_data, public_key):
        return gpg_encrypt(file_data, public_key)

    # send cycle

    def pre_send(self):
        self.set_protocol()
        self.set_domain()
        self.set_notification()
        self.render_body()

    def send(self):
        """
        required:
            self.context.
                site_id
                notification_name or email_template_name
                to_addresses
        optional:
            self.context.
                attachment
        """
        self.pre_send()
        accepted = tasks.accepted_count()
        self.send_email()
        if (
            tasks.synchronous_delivery_requested()
            and tasks.accepted_count() == accepted
        ):
            # a send_email that queued (or dropped) the email while the
            # caller needs it delivered; see tasks.delivering_synchronously
            raise tasks.DeliveryFailed(
                f"{type(self).__name__}.send_email returned without delivering"
            )
        self.post_send()

    def post_send(self):
        self.log_action()

    # send cycle implementation

    def _extra_data(self):
        """for tests"""
        return {}

    def set_protocol(self):
        # emails sent outside a request (bulk account activation) can't ask
        # the request; never fall back to http just because DEBUG is on
        if not self.context.get("protocol"):
            protocol = getattr(settings, "CALLISTO_EMAIL_LINK_PROTOCOL", "https")
            self.context.update({"protocol": protocol})

    def set_domain(self):
        self.context.update({"domain": TenantApi.get_current_domain()})

    def render_body(self):
        body_template = Template(self.context["body"])
        body_context = Context(self.context)
        body_rendered = body_template.render(body_context)
        self.context.update({"body": body_rendered})

    def set_notification(self):
        if self.context.get("email_template_name"):
            body = get_template(self.context["email_template_name"]).template.source
            self.context.update(
                {
                    "notification_name": self.context["email_template_name"],
                    "subject": self.prepend_subject_if_demo_mode(
                        self.context["email_subject"]
                    ),
                    "body": body,
                }
            )
        elif len(self.models_on_site) == 1:
            notification = self.models_on_site[0]
            self.context.update(
                {
                    "subject": self.prepend_subject_if_demo_mode(notification.subject),
                    "body": notification.body,
                }
            )
        else:
            self.context.update(
                {
                    "subject": self.prepend_subject_if_demo_mode(
                        self.context["notification_name"]
                    ),
                    "body": self.context["notification_name"],
                }
            )

    def send_email(self):
        """Queues the email; tasks.send_email delivers it through Mailgun"""
        attachments = []
        if self.context.get("attachment"):
            file_name, file_data, *_ = self.context["attachment"]
            attachments.append((file_name, file_data))
        message = tasks.build_message(
            to=self.context["to_addresses"],
            subject=self.context["subject"],
            html=self.context["body"],
            extra=self._extra_data(),
            attachments=attachments,
        )
        tasks.queue_email(message)

    def log_action(self):
        logger.info(
            "notification.send(subject={}, name={})".format(
                self.context["subject"], self.context["notification_name"]
            )
        )

        if self.context.get("attachment"):
            self.context.update(
                {"attachment": (self.context["attachment"][0], "FILEDATA")}
            )

        if self.context.get("body"):
            self.context.update({"body": self.context["body"][:80]})

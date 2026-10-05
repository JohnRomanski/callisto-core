import base64
import logging

import requests
from kombu.exceptions import OperationalError

from django.conf import settings

from callisto_core.celeryconfig.celery import celery_app
from callisto_core.celeryconfig.tasks import CallistoCoreBaseTask

logger = logging.getLogger(__name__)

DEFAULT_MAILGUN_ROUTE = "https://api.mailgun.net/v3/mail.callistocampus.org/messages"
DEFAULT_FROM = '"Callisto" <noreply@mail.callistocampus.org>'


class TransientMailError(Exception):
    pass


def build_message(to, subject, html, extra=None, attachments=None):
    """
    A JSON-safe email for send_email.delay(). It deliberately holds no
    credentials: the task reads those from settings when it runs.

    attachments: [(filename, bytes or str)]
    """
    return {
        "to": list(to),
        "subject": subject,
        "html": html,
        "extra": dict(extra or {}),
        "attachments": [
            {
                "filename": filename,
                "content": base64.b64encode(
                    content.encode("utf-8") if isinstance(content, str) else content
                ).decode("ascii"),
            }
            for filename, content in (attachments or [])
        ],
    }


def _post_to_mailgun(message):
    return requests.post(
        getattr(settings, "MAILGUN_POST_ROUTE", DEFAULT_MAILGUN_ROUTE),
        auth=("api", settings.MAILGUN_API_KEY),
        data={
            "from": getattr(settings, "MAILGUN_FROM", DEFAULT_FROM),
            "to": message["to"],
            "subject": message["subject"],
            "html": message["html"],
            **message["extra"],
        },
        files=[
            ("attachment", (item["filename"], base64.b64decode(item["content"])))
            for item in message["attachments"]
        ],
        timeout=30,
    )


@celery_app.task(
    base=CallistoCoreBaseTask,
    bind=True,
    max_retries=5,
    ignore_result=True,  # keep addresses and bodies out of the result backend
)
def send_email(self, message):
    """
    Sends an email built by build_message through the Mailgun API.

    In a worker, connection errors, 429 and 5xx responses are retried with
    exponential backoff. Run eagerly (CELERY_TASK_ALWAYS_EAGER), the task
    executes inside the user's request, so it makes one attempt instead of
    holding the request open through retries. Either way a delivery failure
    is logged, never raised; other responses are permanent and logged.
    """
    try:
        response = _post_to_mailgun(message)
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientMailError(f"mailgun returned {response.status_code}")
    except (requests.RequestException, TransientMailError) as exc:
        if self.request.is_eager or self.request.retries >= self.max_retries:
            logger.error(f"email not sent: {exc!r}")
            return None
        raise self.retry(exc=exc, countdown=2**self.request.retries * 30)

    if response.status_code != 200:
        # no message details: they include addresses and may include links
        logger.error(f"mailgun rejected email: status_code={response.status_code}")
    return response.status_code


def queue_email(message):
    """
    Queues send_email. Publishing happens inside the user's request, so if
    the broker is unreachable, send the email inline (one attempt) instead of
    failing the request or dropping the notification.
    """
    try:
        send_email.delay(message)
    except (OperationalError, OSError) as exc:
        logger.error(f"email broker unavailable, sending inline: {exc!r}")
        send_email.apply(args=[message])

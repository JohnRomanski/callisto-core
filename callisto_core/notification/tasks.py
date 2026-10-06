import base64
import contextvars
import logging
from contextlib import contextmanager

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


class DeliveryFailed(Exception):
    """Mailgun didn't accept an email sent with deliver()."""


class _SynchronousDelivery:
    def __init__(self):
        self.accepted = 0


_synchronous = contextvars.ContextVar("callisto_synchronous_delivery", default=None)


@contextmanager
def delivering_synchronously():
    """
    Within this block, every email must be delivered before NotificationApi's
    send() returns, and a failure raises DeliveryFailed. Used where the caller
    must know an email went out before recording that it did (reports to the
    school, match notifications).

    This is part of the NotificationApi contract. A NotificationApi that
    overrides send_email must, while synchronous_delivery_requested() is true,
    send the email immediately and call record_accepted() once its provider
    has accepted it (tasks.deliver() does both). send() raises DeliveryFailed
    if send_email returns without doing so, so nothing is recorded as sent.
    """
    token = _synchronous.set(_SynchronousDelivery())
    try:
        yield
    finally:
        _synchronous.reset(token)


def synchronous_delivery_requested() -> bool:
    return _synchronous.get() is not None


def record_accepted():
    """Call after the email provider accepted an email sent synchronously."""
    delivery = _synchronous.get()
    if delivery is not None:
        delivery.accepted += 1


def accepted_count() -> int:
    delivery = _synchronous.get()
    return delivery.accepted if delivery is not None else 0


def deliver(message):
    """Sends message now; raises DeliveryFailed unless Mailgun accepted it."""
    try:
        response = _post_to_mailgun(message)
    except requests.RequestException as exc:
        raise DeliveryFailed(repr(exc)) from exc
    if response.status_code != 200:
        raise DeliveryFailed(f"mailgun returned {response.status_code}")
    record_accepted()


def build_message(to, subject, html, extra=None, attachments=None):
    """
    A JSON-safe email for send_email.delay(). It deliberately holds no
    credentials: the task reads those from settings when it runs.

    to: an address string, or a list of addresses
    attachments: [(filename, bytes or str)]
    """
    if isinstance(to, str):
        # callers pass a single address string or a list; list("a@b") would
        # split the address into characters
        to = [to]
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
    # acknowledge only after running, and requeue if the worker dies mid-task,
    # so a crash can't silently drop an email (it may send twice instead)
    acks_late=True,
    reject_on_worker_lost=True,
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
    if synchronous_delivery_requested():
        deliver(message)
        return
    try:
        send_email.delay(message)
    except (OperationalError, OSError) as exc:
        logger.error(f"email broker unavailable, sending inline: {exc!r}")
        send_email.apply(args=[message])

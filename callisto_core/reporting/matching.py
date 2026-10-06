"""
Matching outside the request, without losing matches or notifications.

schedule() stores the identifier as a pepper-encrypted MatchingJob and queues
its id. process_job() runs matching and, in one transaction, marks the reports
as matched, records a MatchEvent (the outbox) and deletes the job. So a crash
leaves either the job (rerun it) or the event (finish sending), never neither.
send_notifications() delivers each outstanding step synchronously and marks it
only after Mailgun accepted it, under a row lock so concurrent senders can't
both send. A failed step stays pending for the retry or the sweeper.

Delivery is at least once: a crash after an email is accepted but before its
step is marked repeats that step.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from callisto_core.delivery import security
from callisto_core.delivery.models import MatchEvent, MatchingJob
from callisto_core.notification import tasks as email_tasks
from callisto_core.utils.api import MatchingApi, NotificationApi, TenantApi

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=10)


def _encrypt(identifier: str) -> bytes:
    return security.pepper(identifier.encode("utf-8"))


def _decrypt(encrypted: bytes) -> str:
    return security.unpepper(encrypted).decode("utf-8")


def schedule(identifier: str, site_id: int, admin_email_template: str) -> MatchingJob:
    from callisto_core.reporting import tasks

    job = MatchingJob.objects.create(
        encrypted_identifier=_encrypt(identifier),
        site_id=site_id,
        admin_email_template=admin_email_template,
    )
    tasks.dispatch(tasks.process_matching_job, job.pk)
    return job


def process_job(job_id: int) -> MatchEvent | None:
    from callisto_core.reporting import tasks

    with transaction.atomic():
        # skip_locked: a job another worker (or the sweeper) holds is theirs
        job = (
            MatchingJob.objects.select_for_update(skip_locked=True)
            .filter(pk=job_id)
            .first()
        )
        if job is None:
            return None  # already processed
        matches = MatchingApi.find_matches(_decrypt(bytes(job.encrypted_identifier)))
        event = None
        if matches:
            event = MatchEvent.objects.create(
                encrypted_identifier=job.encrypted_identifier,
                site_id=job.site_id,
                admin_email_template=job.admin_email_template,
            )
            event.match_reports.set(matches)
        job.delete()

    if event is not None:
        tasks.dispatch(tasks.send_match_notifications, event.pk)
    return event


def send_notifications(event_id: int) -> None:
    """
    Delivers each outstanding step synchronously and marks it only once
    Mailgun has accepted its emails. A failed step stays pending, earlier
    steps stay marked, and the error is raised after the marks are committed
    so the task retry or the sweeper resumes from the failed step.
    """
    failure = None
    with transaction.atomic():
        event = (
            MatchEvent.objects.select_for_update(skip_locked=True)
            .filter(pk=event_id, completed__isnull=True)
            .first()
        )
        if event is None:
            return  # done, or another sender has it

        matches = list(event.match_reports.select_related("report__owner"))
        if not matches:  # every report was withdrawn
            _complete(event)
            return

        for field, step in _steps(event, matches):
            if getattr(event, field):
                continue
            try:
                with email_tasks.delivering_synchronously():
                    step()
            except Exception as exc:
                logger.error(f"match event {event.pk}: {field} not delivered: {exc!r}")
                failure = exc
                break
            _mark(event, field)
        else:
            _complete(event)

    if failure is not None:
        raise failure


def _steps(event, matches):
    site_settings = _site_settings(event.site_id)

    def notify_authority():
        NotificationApi.send_matching_report_to_authority(
            matches=matches,
            identifier=_decrypt(bytes(event.encrypted_identifier)),
            to_addresses=site_settings("COORDINATOR_EMAIL"),
            public_key=site_settings("COORDINATOR_PUBLIC_KEY"),
        )

    def notify_owners():
        # a failure part way resends to the owners already notified
        for match in matches:
            NotificationApi.send_match_notification(match_report=match)

    def notify_callisto():
        if not event.admin_email_template or site_settings("DEMO_MODE", cast=bool):
            return
        NotificationApi.slack_notification(
            msg="New Callisto Matches (details will be sent via email)",
            type="match_confirmation",
        )
        NotificationApi.send_with_kwargs(
            site_id=event.site_id,
            email_template_name=event.admin_email_template,
            to_addresses=NotificationApi.ALERT_LIST,
            matches=matches,
            email_subject="New Callisto Matches",
            email_name="match_confirmation_callisto_team",
        )

    return [
        ("authority_notified", notify_authority),
        ("owners_notified", notify_owners),
        ("callisto_notified", notify_callisto),
    ]


def sweep(older_than: timedelta = STALE_AFTER) -> tuple[int, int, int]:
    """
    Re-runs jobs and events a lost message or crashed worker left behind.
    Each item is isolated, so one that keeps failing (bad configuration, an
    unreadable row) is logged and doesn't stop the rest.
    Returns (jobs, events, failures).
    """
    cutoff = timezone.now() - older_than
    job_ids = list(
        MatchingJob.objects.filter(created__lt=cutoff).values_list("pk", flat=True)
    )
    event_ids = list(
        MatchEvent.objects.filter(
            completed__isnull=True, created__lt=cutoff
        ).values_list("pk", flat=True)
    )
    failures = 0
    for run, ids in [(process_job, job_ids), (send_notifications, event_ids)]:
        for pk in ids:
            try:
                run(pk)
            except Exception:
                failures += 1
                logger.exception(f"sweep: {run.__name__}({pk}) failed")
    return len(job_ids), len(event_ids), failures


def _site_settings(site_id):
    def lookup(var, cast=str):
        return TenantApi.site_settings(var, cast=cast, site_id=site_id)

    return lookup


def _mark(event, field):
    setattr(event, field, True)
    event.save(update_fields=[field])


def _complete(event):
    event.completed = timezone.now()
    event.encrypted_identifier = b""  # no longer needed; don't keep it
    event.save(update_fields=["completed", "encrypted_identifier"])

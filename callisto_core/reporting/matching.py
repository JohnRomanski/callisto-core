"""
Matching outside the request, without losing matches or notifications.

schedule() stores the identifier as a pepper-encrypted MatchingJob and queues
its id. process_job() runs matching and, in one transaction, marks the reports
as matched, records a MatchEvent (the outbox) and deletes the job. So a crash
leaves either the job (rerun it) or the event (finish sending), never neither.
send_notifications() sends each outstanding step from the event and marks it,
under a row lock so concurrent senders can't both send.

Delivery is at least once: a crash after an email is queued but before its
step is marked will repeat that step.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from callisto_core.delivery import security
from callisto_core.delivery.models import MatchEvent, MatchingJob
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

        site_settings = _site_settings(event.site_id)
        if not event.authority_notified:
            NotificationApi.send_matching_report_to_authority(
                matches=matches,
                identifier=_decrypt(bytes(event.encrypted_identifier)),
                to_addresses=site_settings("COORDINATOR_EMAIL"),
                public_key=site_settings("COORDINATOR_PUBLIC_KEY"),
            )
            _mark(event, "authority_notified")
        if not event.owners_notified:
            for match in matches:
                NotificationApi.send_match_notification(match_report=match)
            _mark(event, "owners_notified")
        if not event.callisto_notified:
            if event.admin_email_template and not site_settings("DEMO_MODE", cast=bool):
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
            _mark(event, "callisto_notified")
        _complete(event)


def sweep(older_than: timedelta = STALE_AFTER) -> tuple[int, int]:
    """Re-run jobs and events a lost message or crashed worker left behind."""
    cutoff = timezone.now() - older_than
    job_ids = list(
        MatchingJob.objects.filter(created__lt=cutoff).values_list("pk", flat=True)
    )
    event_ids = list(
        MatchEvent.objects.filter(
            completed__isnull=True, created__lt=cutoff
        ).values_list("pk", flat=True)
    )
    for job_id in job_ids:
        process_job(job_id)
    for event_id in event_ids:
        send_notifications(event_id)
    return len(job_ids), len(event_ids)


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

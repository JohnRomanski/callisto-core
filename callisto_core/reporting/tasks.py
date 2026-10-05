import logging

from kombu.exceptions import OperationalError

from django.db import transaction

from callisto_core.celeryconfig.celery import celery_app
from callisto_core.celeryconfig.tasks import CallistoCoreBaseTask

logger = logging.getLogger(__name__)


def dispatch(task, *args):
    """
    Runs task inline when Celery is eager; otherwise queues it once the
    current transaction commits (so the worker can see the rows it needs).
    If the broker is unreachable, runs it inline rather than dropping it; the
    sweeper also retries anything left behind.
    """
    if celery_app.conf.task_always_eager:
        task.apply(args=args)
        return

    def publish():
        try:
            task.delay(*args)
        except (OperationalError, OSError) as exc:
            logger.error(f"broker unavailable, running {task.name} inline: {exc!r}")
            task.apply(args=args)

    transaction.on_commit(publish)


def _retry_or_raise(task, exc):
    if task.request.is_eager:
        raise exc
    raise task.retry(exc=exc, countdown=2**task.request.retries * 30)


@celery_app.task(
    base=CallistoCoreBaseTask, bind=True, max_retries=5, ignore_result=True
)
def process_matching_job(self, job_id):
    """Matches one MatchingJob. Only the job's id is ever queued."""
    from callisto_core.reporting import matching

    try:
        matching.process_job(job_id)
    except Exception as exc:
        _retry_or_raise(self, exc)


@celery_app.task(
    base=CallistoCoreBaseTask, bind=True, max_retries=5, ignore_result=True
)
def send_match_notifications(self, event_id):
    """Sends the outstanding notifications for one MatchEvent."""
    from callisto_core.reporting import matching

    try:
        matching.send_notifications(event_id)
    except Exception as exc:
        _retry_or_raise(self, exc)


@celery_app.task(base=CallistoCoreBaseTask, ignore_result=True)
def sweep_pending_matches():
    """Run periodically (Celery beat) to recover lost or failed matching work."""
    from callisto_core.reporting import matching

    jobs, events, failures = matching.sweep()
    if jobs or events:
        logger.warning(
            f"swept {jobs} matching jobs and {events} match events ({failures} failed)"
        )

import logging

from callisto_core.celeryconfig.celery import celery_app

logger = logging.getLogger(__name__)


class CallistoCoreBaseTask(celery_app.Task):
    """Abstract base class for all callisto-core tasks"""

    abstract = True

    def _logTask(self, msg):
        logger.info(msg)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Log the exception(s) on retry."""
        logger.info(f"CLERY TASK RETRY: {task_id!r} FAILED: {exc!r}")
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log the exception(s) on failure."""
        logger.error(f"CLERY TASK FAILURE: {task_id!r} FAILED: {exc!r}")
        super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(base=CallistoCoreBaseTask, bind=True, max_retries=5, soft_time_limit=5)
def add(self, x, y):
    """Demo Task for testing"""
    return x + y

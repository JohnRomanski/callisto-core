from datetime import timedelta

from django.core.management.base import BaseCommand

from callisto_core.reporting import matching


class Command(BaseCommand):
    help = (
        "Re-run matching jobs and send match notifications left behind by a "
        "lost queue message or a crashed worker. Safe to run repeatedly."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-minutes",
            type=int,
            default=int(matching.STALE_AFTER.total_seconds() // 60),
            help="only pick up work at least this old (default: %(default)s)",
        )

    def handle(self, *args, older_than_minutes, **options):
        jobs, events, failures = matching.sweep(timedelta(minutes=older_than_minutes))
        self.stdout.write(
            f"processed {jobs} matching jobs and {events} match events"
            f" ({failures} failed, see the log)"
        )

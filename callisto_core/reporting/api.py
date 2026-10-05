import logging

from django.db import transaction

logger = logging.getLogger(__name__)


class CallistoCoreMatchingApi:
    @property
    def match_reports(_):
        from callisto_core.delivery.models import MatchReport

        return MatchReport.objects.all()

    @property
    def transforms(self):
        return [
            self._resolve_reports_decryptable_with_identifier,
            self._lock_reports,
            self._resolve_reports_with_duplicate_owners,
            self._resolve_match_is_between_two_or_more_reports,
            self._resolve_already_matched_reports,
            self._update_match_found,
        ]

    def find_matches(self, identifier):
        self.identifier = identifier
        match_list = self.match_reports

        logger.debug(f"all reports => match_reports:{len(match_list)}")
        # _lock_reports holds row locks until this transaction ends, so
        # concurrent submissions can't both trigger the same match
        with transaction.atomic():
            for func in self.transforms:
                if match_list:
                    match_list = func(match_list)
                logger.debug(f"post {func.__name__} => {match_list}")

        if match_list:
            logger.info(f"matches found => match_reports:{len(match_list)}")

        return match_list

    def _resolve_reports_decryptable_with_identifier(self, match_list):
        return [
            match_report
            for match_report in match_list
            if match_report.get_match(self.identifier)
        ]

    def _lock_reports(self, match_list):
        """
        Lock the candidate reports and re-read them, so match_found reflects
        any match committed by a concurrent submission. Locks are taken in
        pk order to avoid deadlocks between submissions.
        """
        from callisto_core.delivery.models import Report

        report_ids = sorted({match.report_id for match in match_list})
        locked_reports = Report.objects.select_for_update().filter(pk__in=report_ids)
        reports_by_id = {report.pk: report for report in locked_reports.order_by("pk")}
        locked_matches = []
        for match in match_list:
            # skip reports deleted since the decryption scan
            if match.report_id in reports_by_id:
                match.report = reports_by_id[match.report_id]
                locked_matches.append(match)
        return locked_matches

    def _resolve_reports_with_duplicate_owners(self, match_list):
        new_match_list = []
        report_owners = []

        for match in match_list:
            if match.report.owner not in report_owners:
                new_match_list.append(match)
                report_owners.append(match.report.owner)

        return new_match_list

    def _resolve_match_is_between_two_or_more_reports(self, match_list):
        if len(match_list) >= 2:
            return match_list
        else:
            return []

    def _resolve_already_matched_reports(self, match_list):
        return [
            match_report
            for match_report in match_list
            if not match_report.report.match_found
        ]

    def _update_match_found(self, match_list):
        for match in match_list:
            match.report.match_found = True
            match.report.save()
        return match_list

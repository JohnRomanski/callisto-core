from callisto_core.notification import tasks as email_tasks
from callisto_core.notification.api import CallistoCoreNotificationApi
from callisto_core.reporting.api import CallistoCoreMatchingApi
from callisto_core.utils.tenant_api import CallistoCoreTenantApi


class SiteAwareNotificationApi(CallistoCoreNotificationApi):
    def user_site_id(self, user):
        from django.contrib.sites.models import Site

        Site.objects.filter(id=1).update(domain="testserver")
        return 1


class CustomNotificationApi(SiteAwareNotificationApi):
    def log_action(self):
        super().log_action()
        for key, value in self.context.items():
            self._logging(**{key: value})

    def _logging(self, *args, **kwargs):
        pass  # for testing inputs


class QueuingElsewhereNotificationApi(CustomNotificationApi):
    """A replacement transport that ignores the synchronous delivery contract."""

    def send_email(self):
        pass  # handed to some other queue


class OwnTransportNotificationApi(CustomNotificationApi):
    """A replacement transport that honors the synchronous delivery contract."""

    sent = []

    def send_email(self):
        type(self).sent.append(self.context["subject"])
        if email_tasks.synchronous_delivery_requested():
            email_tasks.record_accepted()


class CustomMatchingApi(CallistoCoreMatchingApi):
    pass


class CustomTenantApi(CallistoCoreTenantApi):
    pass

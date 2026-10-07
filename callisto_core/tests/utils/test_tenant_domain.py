from django.contrib.sites.models import Site
from django.test import TestCase

from callisto_core.utils.sites import TempSiteID
from callisto_core.utils.tenant_api import CallistoCoreTenantApi


class CurrentDomainTest(TestCase):
    def test_is_the_current_sites_domain(self):
        Site.objects.filter(id=1).update(domain="reports.example.edu")
        Site.objects.clear_cache()
        self.assertEqual(
            CallistoCoreTenantApi().get_current_domain(), "reports.example.edu"
        )

    def test_without_site_id_logs_and_returns_empty(self):
        with (
            TempSiteID(None),
            self.assertLogs("callisto_core.utils.tenant_api", "ERROR"),
        ):
            self.assertEqual(CallistoCoreTenantApi().get_current_domain(), "")

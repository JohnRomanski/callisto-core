from django.test import SimpleTestCase

from callisto_core.reporting.validators import perp_identifiers


class IdentifierTypesTest(SimpleTestCase):
    def test_each_type_has_its_own_label(self):
        labels = [kind["label"] for kind in perp_identifiers().values()]
        self.assertEqual(len(labels), len(set(labels)))

    def test_email_asks_for_an_email_address(self):
        self.assertIn("EMAIL", perp_identifiers()["email"]["label"])

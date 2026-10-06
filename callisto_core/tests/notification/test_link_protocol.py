from django.test import SimpleTestCase, override_settings

from callisto_core.notification.api import CallistoCoreNotificationApi


def protocol():
    api = CallistoCoreNotificationApi()
    api.context = {}
    api.set_protocol()
    return api.context["protocol"]


class LinkProtocolTest(SimpleTestCase):
    @override_settings(DEBUG=True)
    def test_defaults_to_https_even_with_debug_on(self):
        from django.conf import settings

        del settings.CALLISTO_EMAIL_LINK_PROTOCOL
        self.assertEqual(protocol(), "https")

    @override_settings(DEBUG=False, CALLISTO_EMAIL_LINK_PROTOCOL="http")
    def test_setting_chooses_the_protocol(self):
        self.assertEqual(protocol(), "http")

    def test_request_protocol_is_kept(self):
        api = CallistoCoreNotificationApi()
        api.context = {"protocol": "https"}
        with self.settings(CALLISTO_EMAIL_LINK_PROTOCOL="http"):
            api.set_protocol()
        self.assertEqual(api.context["protocol"], "https")

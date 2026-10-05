import base64
import json
from types import SimpleNamespace
from unittest.mock import patch

import requests
from celery.exceptions import Retry
from kombu.exceptions import OperationalError

from django.test import TestCase, override_settings

from callisto_core.notification import tasks


def response(status_code):
    return SimpleNamespace(status_code=status_code, content=b"")


@override_settings(MAILGUN_API_KEY="key-secret-123")
class SendEmailTaskTest(TestCase):
    def message(self):
        return tasks.build_message(
            to=["reporter@example.com"],
            subject="subject",
            html="<p>body</p>",
            extra={"o:testmode": "yes"},
            attachments=[("report.pdf.gpg", b"-----BEGIN PGP MESSAGE-----")],
        )

    def test_message_is_json_and_has_no_credentials(self):
        encoded = json.dumps(self.message())
        self.assertNotIn("key-secret-123", encoded)
        self.assertNotIn("auth", self.message())

    def test_sends_with_credentials_from_settings(self):
        with patch.object(tasks.requests, "post", return_value=response(200)) as post:
            self.assertEqual(tasks.send_email.delay(self.message()).get(), 200)
        _, kwargs = post.call_args
        self.assertEqual(kwargs["auth"], ("api", "key-secret-123"))
        self.assertEqual(kwargs["data"]["to"], ["reporter@example.com"])
        self.assertEqual(kwargs["data"]["o:testmode"], "yes")
        self.assertEqual(
            kwargs["files"],
            [("attachment", ("report.pdf.gpg", b"-----BEGIN PGP MESSAGE-----"))],
        )

    def run_in_worker(self, retries):
        """Run the task body as a worker would (not eagerly)."""
        tasks.send_email.push_request(retries=retries, is_eager=False)
        self.addCleanup(tasks.send_email.pop_request)
        return tasks.send_email.run(self.message())

    def test_worker_retries_transient_failures_with_backoff(self):
        for outcome in [requests.ConnectionError(), response(503), response(429)]:
            with (
                self.subTest(outcome=outcome),
                patch.object(tasks.requests, "post", side_effect=[outcome]),
                patch.object(tasks.send_email, "retry", side_effect=Retry) as retry,
                self.assertRaises(Retry),
            ):
                self.run_in_worker(retries=2)
            self.assertEqual(retry.call_args.kwargs["countdown"], 120)

    def test_worker_gives_up_after_max_retries(self):
        with (
            patch.object(tasks.requests, "post", return_value=response(503)),
            patch.object(tasks.send_email, "retry") as retry,
            self.assertLogs(tasks.logger, "ERROR"),
        ):
            result = self.run_in_worker(retries=tasks.send_email.max_retries)
        self.assertIsNone(result)
        retry.assert_not_called()

    def test_eager_send_makes_one_attempt(self):
        # eager tasks run inside the user's request; don't hold it open
        with (
            patch.object(
                tasks.requests, "post", side_effect=requests.ConnectionError
            ) as post,
            self.assertLogs(tasks.logger, "ERROR"),
        ):
            self.assertIsNone(tasks.send_email.delay(self.message()).get())
        self.assertEqual(post.call_count, 1)

    def test_permanent_failures_are_not_retried_and_not_logged_in_full(self):
        with (
            patch.object(tasks.requests, "post", return_value=response(400)) as post,
            self.assertLogs(tasks.logger, "ERROR") as logs,
        ):
            tasks.send_email.delay(self.message())
        self.assertEqual(post.call_count, 1)
        self.assertNotIn("reporter@example.com", "".join(logs.output))
        self.assertNotIn("key-secret-123", "".join(logs.output))

    def test_results_are_not_stored(self):
        self.assertTrue(tasks.send_email.ignore_result)

    def test_attachment_round_trips_base64(self):
        content = self.message()["attachments"][0]["content"]
        self.assertEqual(base64.b64decode(content), b"-----BEGIN PGP MESSAGE-----")

    def test_broker_outage_sends_inline_instead_of_failing(self):
        with (
            patch.object(
                tasks.send_email, "delay", side_effect=OperationalError("down")
            ),
            patch.object(tasks.requests, "post", return_value=response(200)) as post,
            self.assertLogs(tasks.logger, "ERROR"),
        ):
            tasks.queue_email(self.message())
        self.assertEqual(post.call_count, 1)

    def test_broker_and_mailgun_outage_still_does_not_raise(self):
        with (
            patch.object(
                tasks.send_email, "delay", side_effect=OperationalError("down")
            ),
            patch.object(tasks.requests, "post", side_effect=requests.ConnectionError),
            self.assertLogs(tasks.logger, "ERROR"),
        ):
            tasks.queue_email(self.message())

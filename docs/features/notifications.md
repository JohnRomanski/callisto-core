# Notifications

Code: `notification/api.py` (`CallistoCoreNotificationApi`),
`notification/tasks.py` (Mailgun task, synchronous delivery),
`notification/models.py` (`EmailNotification`).

## Email templates

- `EmailNotification` rows (name, subject, body) are edited in the admin and
  attached to one or more sites. Bodies are Django templates rendered with the
  send context (user, report, links, domain, protocol).
- Names in use include `submit_confirmation`, `report_delivery`,
  `match_delivery`, `match_notification`, `match_confirmation`,
  `password_reset_email`, `account_activation_email`,
  `student_verification_email`.

## Send cycle

`send()` = `pre_send()` (protocol, domain, look up the template, render) →
`send_email()` → `post_send()` (log the action).

- **Queued (default)**: `send_email` builds a JSON message without
  credentials and queues `notification.tasks.send_email`. The worker posts to
  Mailgun with credentials from settings, retrying connection errors, 429 and
  5xx with backoff. If the broker is down, it sends inline once.
- **Synchronous**: inside `tasks.delivering_synchronously()`, the email is
  posted immediately and `DeliveryFailed` is raised unless Mailgun accepts it.
  Used for the school's copy of a report and for match notifications. A
  replacement `send_email` must honor this (see [USAGE.md](../USAGE.md#notificationapi)).

## Attachments and encryption

- PDFs are generated with reportlab (`reporting/report_delivery.py`): full
  reports, match reports, and a user review report.
- Attachments for the school are GPG-encrypted to the site's coordinator key
  in a temporary keyring; a bad or expired key raises `GPGEncryptionError`
  instead of sending an empty file.

## Other channels

- `slack_notification` is a no-op hook for hosts to implement.

## User review email

`manage.py user_review_email` sends one GPG-encrypted PDF listing every
submitted report and every matched report (excluding accounts marked
`invalid`) to the coordinator of **site 1**, then a Slack alert. It ignores
other sites: the site id is hard-coded and the queries aren't filtered by
site.

## Known gaps

- Mailgun is the only built-in transport, and its route defaults to the
  original Callisto domain (`MAILGUN_POST_ROUTE`, `MAILGUN_FROM`).
- No bounce or complaint handling; a rejected email is only logged.
- Email bodies can include identifying details; logs avoid addresses and
  bodies, but Mailgun retains them per its own policy.

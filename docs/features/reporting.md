# Reporting to the school

Sending a record to the school's coordinator (often the Title IX office).
Code: `reporting/view_partials.py`, `reporting/report_delivery.py`,
`notification/api.py`.

## Steps (URL names)

1. `reporting_email_confirmation`: verify a school email (skipped if already
   verified). See [accounts.md](accounts.md#school-email-verification).
2. `reporting_prep`: contact details for the school: email, phone, whether a
   voicemail is OK, name, notes on preferred contact.
3. `reporting_matching_enter`: optionally also enter matching (see
   [matching.md](matching.md)).
4. `reporting_end_step`: confirm ("Yes, I agree and I understand").

Resubmitting an already-sent record uses `resubmit_prep` and
`resubmit_end_step`.

## What happens on confirm

All inside one database transaction:

1. A `SentFullReport` is created (its id becomes the report id on the PDF).
2. The record is rendered to a PDF (cover page marked CONFIDENTIAL, then the
   answers and contact details), GPG-encrypted to the site's
   `COORDINATOR_PUBLIC_KEY`, and emailed to `COORDINATOR_EMAIL`.
3. That email is delivered **synchronously**: the request waits for Mailgun
   to accept it. Only then is `Report.submitted_to_school` set.

If delivery or encryption fails, the transaction rolls back, nothing is
recorded as sent, and the survivor sees "We couldn't send your report to the
school, so nothing was sent. Please try again later."

After success (queued, best effort): a confirmation email to the survivor's
contact email, an alert email to the Callisto team (`ALERT_LIST`), and a Slack
notification hook (a no-op unless the host implements it).

## Demo mode

With the tenant setting `DEMO_MODE`, the school's copy also goes to the
user's own addresses, subjects get a `[DEMO]` prefix, and the Callisto team
email and Slack alert are skipped.

## Known gaps

- The coordinator receives a GPG-encrypted email attachment and must decrypt
  it offline. There's no delivery receipt or coordinator-side portal.
- If the coordinator's key is wrong or expired, the survivor can't send at
  all until the school fixes it; nothing alerts the operators except logs.
- The request holds a transaction open during the Mailgun call (up to 30 s).

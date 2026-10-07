# Architecture

## Shape of the system

callisto-core is a reusable Django app, not a site. A host project:

- adds the callisto-core apps to `INSTALLED_APPS` and includes their URLs,
- subclasses the **view partials** (`*/view_partials.py`) with its own
  templates (the `views.py` files here are for the demo site and tests),
- may replace behavior through three **API classes** chosen by settings
  (`CALLISTO_NOTIFICATION_API`, `CALLISTO_MATCHING_API`, `CALLISTO_TENANT_API`),
- supplies per-school settings through `TenantApi.site_settings` and Django's
  sites framework.

## Apps

| App | Responsibility |
|---|---|
| `accounts` | Signup, login, logout, password reset and change, account activation, school email verification, `Account` (site, verified flag, school email), bulk account creation |
| `wizard_builder` | Admin-defined questionnaires: `Page` (section When/Where/What/Who), `FormQuestion` and its proxy types (single line, text area, checkbox, radio, dropdown), `Choice`, `ChoiceOption`; the multi-page wizard views and form rendering |
| `delivery` | Encrypted records: `Report`, `MatchReport`, the passphrase-based encryption, passphrase storage between requests, key hashers, the dashboard and record views (view, edit, PDF, delete), deploy checks, and the sent/outbox models (`SentFullReport`, `SentMatchReport`, `MatchingJob`, `MatchEvent`) |
| `reporting` | The reporting and matching flows: contact info, school email verification, matching entry and withdrawal, confirmation; identifier validation; matching (`matching.py`, `api.py`); PDF generation (`report_delivery.py`); Celery tasks |
| `notification` | `EmailNotification` templates (per site), `CallistoCoreNotificationApi` (render, attach, encrypt, send), the Mailgun Celery task, synchronous delivery |
| `evaluation` | `EvalRow`, a log of which user did which action on which report |
| `celeryconfig` | The Celery app and base task |
| `utils` | Settings (demo and live), API loader, tenant API, URL conf for the demo site, sites helpers |

## Request flow, in brief

1. **Account**: a user signs up (or is created in bulk and activated by email)
   and logs in. Login is rejected if the account belongs to another site.
2. **Record**: the user creates a report with a passphrase, then answers the
   wizard pages. Each save re-encrypts the whole answer set with a key derived
   from the passphrase. The passphrase is kept between requests in split-key
   storage (see [features/records.md](features/records.md)).
3. **Reporting** (optional): verify a school email, give contact details,
   optionally enter matching, confirm. The report is rendered to PDF,
   GPG-encrypted to the school coordinator's key, and delivered synchronously
   before it counts as sent.
4. **Matching** (optional, also reachable without reporting): enter one or
   more perpetrator identifiers. Each is stored as a `MatchReport` that only
   that identifier can decrypt; a worker tries the identifier against all
   stored match reports and, when two or more owners match, notifies the
   school, the survivors and the Callisto team.

## Data model overview

```
User 1─1 Account (site_id, is_verified, school_email)
User 1─* Report (encrypted answers, contact_*, submitted_to_school, match_found)
Report 1─* MatchReport (encrypted per identifier)
Report 1─* SentFullReport (one per submission to the school)
MatchReport *─* SentMatchReport (one per match delivered)
MatchingJob (pepper-encrypted identifier waiting to be matched)
MatchEvent *─* MatchReport (a found match and which notifications went out)
StoredPassphrase (passphrase encrypted to a browser-held key)
EvalRow (user, report, action, timestamp)
EmailNotification *─* Site (templates)
Page / FormQuestion / Choice / ChoiceOption (+ sites)
```

## Extension points

- **View partials**: subclass for templates and URLs; they define forms,
  access checks and redirects (see the module docstring in
  `reporting/view_partials.py`).
- **NotificationApi**: replace email, PDF or Slack behavior. Delivery that
  must be confirmed (the school's copy, match notifications) follows the
  synchronous delivery contract in `notification/tasks.py` and
  [USAGE.md](USAGE.md#notificationapi).
- **MatchingApi**: replace how matches are found.
- **TenantApi**: derive per-school settings from the request or site id.

## Background work

- **Email**: queued to Celery (`notification.tasks.send_email`), retried in a
  worker; sent inline if the broker is down; sent synchronously where the
  caller must know it went out.
- **Matching**: `reporting.matching` queues a job id; the worker matches,
  records a `MatchEvent` in the same transaction, then sends notifications
  step by step. A periodic sweeper (`sweep_pending_matches` /
  `manage.py process_pending_matches`) recovers anything left behind.

## Open questions

- Should the demo `views.py` and `utils/urls.py` move out of the library into
  an example project?
- Which parts of the API classes are a supported public contract, and which
  are internal? Today any method can be overridden.

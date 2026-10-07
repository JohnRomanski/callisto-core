# Ideas for improving the site

A brainstorm, not a plan: unprioritized, unreviewed, and not checked with
survivors, advocates or schools. Anything here that touches what survivors see
or what is stored should be shaped with trauma-informed design input and
reviewed for privacy first.

## For survivors

### Safety and discretion
- **Quick exit**: a button and keyboard shortcut that leaves to a neutral site
  and replaces the history entry.
- **Neutral page titles and email subjects** so a shared screen or inbox
  doesn't reveal what the site is.
- **Session timeout warning** before the passphrase expires, with a "keep
  working" option, instead of a sudden re-prompt.
- **Optional no-email accounts**: no password reset and no match
  notifications, in exchange for storing nothing that identifies the person.

### Writing a record
- **Autosave with a visible "saved" state**, so nothing is lost if the tab
  closes.
- **Progress indicator** through the When / Where / What / Who sections, and
  the ability to skip and come back.
- **Free-text "anything else"** on every page.
- **Evidence checklist** (screenshots, messages, medical visit) with guidance
  on preserving it, without uploading anything.
- **Export in other formats**: records can already be viewed and downloaded
  as PDF at any time; add plain text or a structured format (JSON) the
  survivor can keep or give to an advocate.

### Understanding choices
- **Plain-language explainers** at each decision: what reporting does, who
  sees what, what matching means, what happens after a match.
- **"What happens next" status** on the dashboard: saved, in matching, match
  found, reported (with date), and what the school will do.
- **Passphrase guidance**: live strength feedback while choosing (weak
  passphrases are now rejected on submit, which is friction without it), and
  a clear, repeated warning that it can't be recovered.
- **Resources by school**: counseling, advocacy, medical and legal contacts,
  configurable per site.

### Accessibility and reach
- WCAG 2.2 AA audit (keyboard navigation, screen readers, contrast).
- Mobile-first layout.
- Translations, starting with Spanish.

## For schools

- **Secure coordinator portal** instead of GPG email attachments: sign-in,
  decrypt in the browser, acknowledge receipt.
- **Delivery receipts**: tell the survivor (optionally) when the school opened
  the report.
- **Key health checks**: warn operators before a coordinator key expires; test
  a key when it's saved in settings.
- **Per-site admins** who can manage only their school's questions, templates
  and bulk accounts.
- **Question set versioning and preview**, so editing questions never breaks
  existing records.

## Privacy and security

- Ship the [encrypted identities](design/encrypted-identities.md) "collect
  less" step first: stop storing school emails and plaintext contact fields.
- Replace the evaluation log with **aggregate counts** (actions per day per
  site, no user or record link), or remove it.
- **Data retention**: let survivors set records to expire; auto-delete
  abandoned drafts after a long period, with warning.
- **Passkeys (WebAuthn)** as a login option; optional second factor.
- **Content Security Policy** and other security headers; `security.txt` and a
  disclosure policy.
- **Pepper versioning** so the matching key can be rotated.
- **Independent security review** of the whole system before any real
  deployment.

## Matching

- See [design/faster-matching.md](design/faster-matching.md).
- Decide whether matching should cross schools, and make it a site setting.
- Let survivors see and manage the identifiers they've entered (they can only
  withdraw all of them today).
- Support more identifier types (other social networks, student ID), each
  with careful normalization.

## Operations

- Health check endpoint; metrics with no personal data (queue length, stuck
  `MatchEvent`s, delivery failures).
- Error reporting (for example Sentry) with personal data scrubbing.
- A container image and a reference deployment (Postgres, Redis, worker,
  beat).
- A staging site with synthetic data and a test coordinator key.

## Codebase

- Fix or remove `manage.py decrypt_eval_data`, `Report.encrypted_eval` and
  `CALLISTO_EVAL_*` (see [features/evaluation.md](features/evaluation.md)).
- Rename the `passphrase` environment variable that sets `SECRET_KEY` in the
  demo settings, and `DEVELOPEMENT.md`'s spelling.
- Scope `user_review_email` by site instead of hard-coding site 1.
- Move the demo site (`views.py`, `utils/urls.py`) into an example project.
- Type hints and a type checker on the security-critical modules
  (`delivery/security.py`, `hashers.py`, `passphrase_storage.py`,
  `reporting/matching.py`).

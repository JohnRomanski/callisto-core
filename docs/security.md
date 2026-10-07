# Security

An outline of what callisto-core protects, from whom, and where the gaps are.
It reflects the code, not a review: **none of this has had an independent
security or cryptographic review.**

## Who we protect against

| Adversary | Examples |
|---|---|
| Someone with a copy of the database | Leaked backup, compromised DB credentials |
| Someone who also has the server's secrets | Compromised app server or environment |
| Another user of the site | A perpetrator with an account, a curious classmate |
| Callisto's operators | Staff with server access |
| The school | Before the survivor chooses to report |
| Network observers | Public Wi-Fi, campus network |

## What is protected

| Data | Database alone | Database + server secrets | Server while handling a request |
|---|---|---|---|
| Record answers | Protected (passphrase key) | Protected | Readable while the user has it open |
| Match reports (identifier, perpetrator name, contact details) | Protected (identifier key + pepper) | Guessable: one Argon2id derivation per record per guess | Readable at submission and when matching |
| Passphrase between requests | Protected (key is in the browser cookie) | Protected | Readable |
| Reports sent to the school | GPG-encrypted to the coordinator | Same | Readable while rendering |

## What is not protected

- **Who uses the site**: usernames, emails, school emails and contact fields
  are plaintext. See [design/encrypted-identities.md](design/encrypted-identities.md).
- **Activity metadata**: record timestamps, `submitted_to_school`,
  `match_found`, and the evaluation log (`EvalRow`: user, record, action,
  time), all plaintext.
- **The server is trusted**: identifiers and answers reach the application in
  plaintext. Requiring two reporters before the school learns of a match is
  enforced by the application, not by cryptography (see
  [MATCHING.md](MATCHING.md#properties-this-gives-and-doesnt)).
- **Email content at the provider**: confirmation and notification bodies pass
  through Mailgun.

## Secrets

| Secret | Purpose | If lost | If leaked |
|---|---|---|---|
| `SECRET_KEY` | Sessions, CSRF, reset and verification tokens | Everyone is logged out; outstanding links stop working | Forged sessions and tokens |
| `PEPPER` (32 bytes) | Second layer on match reports and matching jobs | **All match reports become unreadable** | Match reports become guessable offline |
| Mailgun API key | Sending email | Email stops | Email can be sent as Callisto |
| Coordinator private keys | Held by schools | The school can't read reports | Reports readable by the holder |

`manage.py check --deploy` fails on a demo `SECRET_KEY` (`callisto.E001`) or a
malformed `PEPPER` (`callisto.E003`). `settings_live` requires both from the
environment.

## Controls in place

- Passphrase key stretching: Argon2id (OWASP minimum parameters), per-record
  salt; parameters stored per record.
- Passphrase attempt rate limit per user (needs a shared cache).
- Split-key passphrase storage, HttpOnly SameSite=Strict cookie, TTL, cleared
  on logout.
- Login and password reset scoped to the account's site.
- Logout POST only; CSRF on all forms.
- HTTPS settings in `settings_live` (redirect, secure cookies, HSTS).
- No credentials in Celery messages; JSON-only serializer; matching jobs carry
  an id, not the identifier.
- GPG failures raise instead of sending empty attachments.
- A report counts as sent only once delivery is confirmed.

## Known gaps and follow-ups

- No Content Security Policy or other security headers beyond Django's
  defaults.
- No second factor for accounts.
- `PEPPER` can't be rotated; there's no key versioning.
- Matching crosses sites (see [features/tenancy.md](features/tenancy.md)).
- The evaluation log is a plaintext activity trail (see
  [features/evaluation.md](features/evaluation.md)).
- No data retention policy: records, match reports and logs are kept until
  deleted.
- The Celery broker carries email bodies and addresses; it must be private and
  use TLS.

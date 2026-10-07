# callisto-core documentation

callisto-core is a Django library that provides the backend of Callisto, a
system where survivors of sexual assault can write a private, encrypted record
of what happened and, if they choose, send it to their school or be told when
someone else names the same perpetrator. A host Django project installs it and
supplies the site, branding and per-school settings.

## Start here

| Document | What it covers |
|---|---|
| [architecture.md](architecture.md) | Apps, request flow, data model, extension points, background work |
| [security.md](security.md) | Threat model, what is and isn't protected, secrets, known gaps |
| [operations.md](operations.md) | What a deployment needs, settings, workers, checks |
| [USAGE.md](USAGE.md) | Settings reference and API extension points for host projects |
| [DEVELOPEMENT.md](DEVELOPEMENT.md) | Local setup, running tests, releasing |

## Functionality

| Area | Document |
|---|---|
| Accounts: signup, login, reset, school email verification, bulk accounts | [features/accounts.md](features/accounts.md) |
| Records: the question wizard, encryption, passphrase handling, PDFs | [features/records.md](features/records.md) |
| Reporting to the school | [features/reporting.md](features/reporting.md) |
| Matching | [features/matching.md](features/matching.md), design: [MATCHING.md](MATCHING.md) |
| Email and other notifications | [features/notifications.md](features/notifications.md) |
| Multiple schools (tenancy) | [features/tenancy.md](features/tenancy.md) |
| Usage tracking (evaluation) | [features/evaluation.md](features/evaluation.md) |
| Admin: questions, email templates, bulk accounts | [features/admin.md](features/admin.md) |

## Design work (not implemented)

| Topic | Document |
|---|---|
| Encrypting user identities | [design/encrypted-identities.md](design/encrypted-identities.md) |
| Faster matching | [design/faster-matching.md](design/faster-matching.md) |

## Ideas

[ideas.md](ideas.md) is a brainstorm of improvements to the site, unprioritized
and unreviewed.

## Project

[HISTORY.md](HISTORY.md) · [CONTRIBUTING.md](CONTRIBUTING.md) ·
[CONDUCT.md](CONDUCT.md) · [AUTHORS.md](AUTHORS.md)

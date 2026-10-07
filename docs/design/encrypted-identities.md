# Design outline: encrypting user identities

Status: **proposal, not implemented.** Needs a security review before
building. Background: a half-built 2019 attempt (bcrypt-hashed usernames and
emails) was removed in PR #15 because it was never enabled, never removed the
plaintext, and couldn't send email to hashed addresses.

## Problem

A database leak today reveals **who has used Callisto**, which for a sexual
assault reporting service is itself sensitive. Plaintext today:

| Field | Where | Used for |
|---|---|---|
| Username | `User.username` | Login; "Reported by" in the user review PDF when there's no email |
| Email | `User.email` | Password reset; "Reported by" on matched reports in the user review PDF (`PDFUserReviewReport.get_user_identifier`, sent to the coordinator by `manage.py user_review_email`) |
| School email | `Account.school_email` | Verification; demo-mode copies |
| Contact name, email, phone, notes, voicemail | `Report.contact_*` | The school's copy of a report; survivor confirmations; match notifications |
| Activity | `EvalRow` (user, record, action, time) | Usage research (partly dismantled) |

## Goals

1. A copy of the database alone reveals no usernames, emails, phone numbers
   or names.
2. Login, password reset, verification, reporting and match notifications
   keep working.
3. Don't make anything worse for an attacker who also controls the server.
4. Keep only what a flow actually needs (minimize before encrypting).

Non-goals: protecting identities from a compromised running server (the
server must see an email to send to it); hiding that *some* account exists.

## Step 1: collect less

These remove plaintext without any new cryptography.

- **School email**: verification only needs the address long enough to send
  the link. Store `is_verified` and the verified domain; don't store the
  address. The only other reader is demo mode's extra copies.
- **Report contact fields**: needed when the survivor submits (they're present
  and have unlocked the record) and when a match is found.
  - Encrypt them **with the record's passphrase key**, inside the record.
  - For match notifications, read the survivor's email from the match report's
    own content (`MatchReportContent.email`), which the worker decrypts while
    matching anyway. `NotificationApi.send_match_notification` would take the
    address from there instead of `report.contact_email`.
  - Submission confirmations are sent while the survivor is present.
- **Evaluation log**: drop `EvalRow`'s user and record links, or remove the
  app (see [features/evaluation.md](../features/evaluation.md)).
- **User review PDF**: it names each matched report's owner by email or
  username. Decide whether the coordinator needs that (the match delivery
  already carries the survivor's chosen contact details); if not, drop it,
  and if so, decrypt it for the PDF only.

## Step 2: encrypt what's left (username, account email)

**Recommended: field encryption plus a keyed blind index.**

- **Encrypt** each value with an identity key held outside the database
  (`IDENTITY_KEY`, separate from `PEPPER`), using an AEAD (NaCl `SecretBox`)
  with a key version prefix so the key can be rotated.
- **Index** each value for lookup with `HMAC-SHA256(INDEX_KEY, normalize(value))`,
  where `normalize` is lowercase plus trimming, and `INDEX_KEY` is a second
  key, also outside the database.
- **Login**: compute the index of the entered username, then look up by it.
  Store the index in `User.username` (unique), so Django's model backend works
  unchanged; keep the encrypted username in `Account` for display.
- **Password reset**: look up by the email's index, decrypt the email, send.
- **Admin**: search by computing the index of a typed value; show decrypted
  values only to staff with a permission, and log those views.

Properties:

| Attacker has | Learns |
|---|---|
| Database only | Nothing about identities; equal indexes reveal duplicate emails |
| Database + `INDEX_KEY` | Can confirm guessed usernames or emails at HMAC speed |
| Database + both keys | Everything (same as today) |
| Running server | Everything it handles (same as today) |

Keep the keys in a secrets manager or KMS, never in the database or its
backups, and never in the same place as each other's backups if avoidable.

## Alternatives considered

- **Hashing only (the 2019 design)**: can't send email; bcrypt of a guessable
  email is checkable from a directory. Rejected.
- **Encryption without an index** (decrypt every row to log in): O(n) per
  login. Rejected.
- **User-held keys** (identity encrypted with the user's password): password
  reset becomes impossible without a recovery secret, and the server can't
  send match notifications. Possible later for the username only.
- **No email at all**: viable for survivors who accept no reset and no match
  notifications; worth offering as an option (see [ideas.md](../ideas.md)).

## Migration outline

1. Add the new columns; write both plaintext and encrypted forms.
2. Backfill existing rows in a data migration (batched; needs the keys).
3. Switch reads (login, reset, admin) to the index and encrypted forms.
4. Remove the plaintext: blank `User.email`, set `User.username` to the
   index, drop `Account.school_email` and the plaintext `Report.contact_*`.
5. Purge old backups that still hold plaintext, per a retention schedule.

Each step is reversible until step 4.

## Open questions

- Who holds the keys, and what is the recovery procedure if they're lost?
  (Losing `IDENTITY_KEY` means no password resets and no admin lookup; logins
  by username still work through the index.)
- Do bulk-provisioned schools need to look up their own students? That
  requires a per-school view of decrypted emails.
- Should usernames be optional, with random handles by default?
- How does this interact with the cross-site matching question?

## Review checklist

- [ ] Normalization rules (Unicode, plus-addressing, case) for the index
- [ ] Key rotation for both keys without downtime
- [ ] Logs, error reports and Celery messages carry no decrypted identity
- [ ] Admin access to decrypted values is permissioned and logged
- [ ] Backups and replicas follow the same rules

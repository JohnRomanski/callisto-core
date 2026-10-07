# Records

A record (`delivery.models.Report`) is a survivor's private, encrypted account
of an incident. Code: `delivery/` (models, security, hashers,
passphrase_storage, view_partials), `wizard_builder/` (questions and wizard).

## Lifecycle

1. **Create**: the user picks a passphrase (entered twice). A random salt is
   generated and the key is derived with the configured key hasher.
2. **Answer**: the wizard walks the site's question pages in section order
   (When, Where, What, Who). Each save serializes all answers to JSON and
   re-encrypts the whole record.
3. **Review**: a summary page; status shows "Saved" or "Reported to school".
4. **View as PDF / download PDF**: decrypted server side and rendered with
   reportlab. Doesn't modify the record.
5. **Delete**: removes the record and, by cascade, its match reports.

## Encryption

- Key: `KEY_HASHERS[0]` (default `Argon2idKeyHasher`, 19 MiB, t=2, p=1) over
  the passphrase and the record's salt. The record stores the hasher's
  parameters (`encode_prefix`) and salt in clear, so changing settings never
  breaks old records; legacy Argon2i and PBKDF2 records still decrypt.
- Cipher: NaCl `SecretBox` (XSalsa20-Poly1305).
- Only the passphrase can decrypt the answers. Callisto has no copy and no
  recovery; a forgotten passphrase means the record is lost.
- Not encrypted: owner, timestamps (`added`, `last_edited`,
  `submitted_to_school`), `match_found`, and the contact fields
  (`contact_name`, `contact_email`, `contact_phone`, `contact_voicemail`,
  `contact_notes`) collected when reporting.

## Passphrase between requests

So the user doesn't retype the passphrase on every page:

- The passphrase is encrypted with a random per-browser key and stored as a
  `StoredPassphrase` row (one per session and report).
- The key lives only in an HttpOnly, SameSite=Strict cookie
  (`callisto_passphrase_key`). Neither the database row nor the cookie alone
  reveals the passphrase.
- Rows expire after `PASSPHRASE_SESSION_TTL` seconds unused (default 30
  minutes) and are removed on logout.

## Access control

- Only the owner can open a record (`PermissionDenied` otherwise).
- Without a stored passphrase, the page asks for it first.
- Passphrase attempts are rate limited per user (`DECRYPT_THROTTLE_RATE`,
  default 100/minute, via django-ratelimit; blocks once exceeded, even for the
  right passphrase). Needs a shared cache to hold across processes.

## Known gaps

- Answers can't be partially exported or shared without the whole record.
- Old record formats (a list instead of a dict) are converted on read
  (`_return_or_transform`); there's no batch migration.
- `Report.encrypted_eval` is an unused column (see
  [evaluation.md](evaluation.md)).

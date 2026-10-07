# Accounts

Code: `callisto_core/accounts/` (forms, view partials, models, tokens,
validators), `notification/api.py` (account emails).

## What a user has

- A Django `User` (username, password hash, optional email).
- An `Account`: `site_id` (which school), `is_verified` and `school_email`
  (set by school email verification), `uuid`, `invalid`.
- Usernames and emails are stored in plaintext. Hiding who uses the site is
  the subject of [design/encrypted-identities.md](../design/encrypted-identities.md).

## Flows

### Signup
- Form: username, password (length `PASSWORD_MIN_LENGTH`–`PASSWORD_MAX_LENGTH`),
  confirmation, optional email ("only used to reset your password"), terms.
- Passwords estimated (zxcvbn) below `PASSWORD_MINIMUM_ENTROPY` bits are
  rejected on signup, reset and change, through `MinimumEntropyValidator` in
  `AUTH_PASSWORD_VALIDATORS` (`manage.py check` warns, `callisto.W001`, if
  the setting is on and the validator isn't installed).
- Creates the `Account` on the current site and logs the user in.
- Disabled per school with the tenant setting `DISABLE_SIGNUP`; signup then
  redirects to login, and the login label becomes "Email Address" (bulk
  accounts use the email as username).

### Login / logout
- Django's model backend. `LoginForm.confirm_login_allowed` rejects an account
  whose `site_id` isn't the current site and logs an error.
- Logout is POST only. It also clears the user's stored passphrases.

### Password reset
- Django's reset flow with Callisto's email sending.
- Finds active users with a usable password whose email matches
  (case-insensitive) **and whose account is on the current site**.
- Link protocol comes from the request.

### Bulk accounts (school-provisioned)
- An admin pastes a comma-separated list of emails into a `BulkAccount` for a
  site and runs it. Each email becomes a user (username = email) with a random
  placeholder password, a verified `Account`, and an activation email.
- The activation link sets the first password. Link protocol comes from
  `CALLISTO_EMAIL_LINK_PROTOCOL` (default https).

### School email verification
- Required before reporting or matching unless already verified.
- The address must be in the tenant's `SCHOOL_EMAIL_DOMAIN` (comma-separated
  domains; empty for demo sites).
- Sends a "Verify your student email" link with a
  `StudentVerificationTokenGenerator` token; following it sets `is_verified`.

## Known gaps

- No second factor; no passkeys.
- `Account.invalid` excludes an account from the user review email
  (`notification/management/commands/user_review_email.py`) but nothing in the
  UI or admin sets it.

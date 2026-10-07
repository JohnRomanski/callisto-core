# Tenancy (multiple schools)

One deployment can serve several schools. Code: `utils/tenant_api.py`,
Django's sites framework (`CurrentSiteMiddleware` sets `request.site`).

## What is per site

- Accounts (`Account.site_id`); login and password reset only work on the
  account's own site.
- Questions (`FormQuestion.sites`) and email templates
  (`EmailNotification.sites`).
- Settings from `TenantApi.site_settings(name, request=..., site_id=...)`:

| Setting | Meaning |
|---|---|
| `SCHOOL_SHORTNAME` | Name used in alerts |
| `SCHOOL_EMAIL_DOMAIN` | Allowed domains for school email verification (comma-separated; empty for demo) |
| `COORDINATOR_NAME` | Coordinator's name |
| `COORDINATOR_EMAIL` | Where reports and matches are sent |
| `COORDINATOR_PUBLIC_KEY` | GPG key reports are encrypted to |
| `DISABLE_SIGNUP` | Only bulk-provisioned accounts |
| `DEMO_MODE` | Demo behavior (see [reporting.md](reporting.md#demo-mode)) |

## Implementing it

The default `CallistoCoreTenantApi` returns fixed demo values. A host replaces
it (`CALLISTO_TENANT_API`) to read settings from its own store.
`get_current_domain()` (the domain in email links) defaults to the `SITE_ID`
site's domain; hosts that resolve the site per request, without `SITE_ID`,
must override it (the default then logs an error and returns `""`).

## Known gaps

- Matching runs across all sites: a match can join reports from different
  schools, and the coordinator of the submitting site receives it. Whether
  that is intended needs a decision.
- No per-site data isolation at the database level.

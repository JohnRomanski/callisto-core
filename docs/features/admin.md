# Admin

Django admin registrations: `wizard_builder/admin/` (`Page`,
`FormQuestion`), `notification/admin.py` (`EmailNotification`),
`accounts/admin.py` (`BulkAccount`).

## Question builder

- **Pages** belong to a section (When, Where, What, Who) and have a position.
- **Questions** belong to a page and to sites, with a position, text,
  descriptive text and a type: single line, text area, checkbox, radio,
  dropdown.
- **Choices** for multiple-choice questions, each with optional extra info
  text and **choice options** (follow-up dropdowns).
- Uses django-nested-admin for inline editing.

## Email templates

Edit `EmailNotification` subject and body per site. Bodies are Django
templates; a mistake shows up only when the email is sent.

## Bulk accounts

Create a `BulkAccount` with a site and a comma-separated list of emails and
run its action to create verified accounts and send activation emails (see
[accounts.md](accounts.md#bulk-accounts-school-provisioned)).

## Known gaps

- Changing or deleting a question after records exist can orphan answers;
  there's no versioning of question sets.
- No preview of a page or an email template before it's live.
- Admin access is all-or-nothing Django staff permissions; no per-site
  admins.

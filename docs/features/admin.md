# Admin

Django admin registrations: `wizard_builder/admin/` (`Page`,
`FormQuestion`), `notification/admin.py` (`EmailNotification`),
`accounts/admin.py` (`BulkAccount`; it also unregisters `User` and `Group`).

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

Fill in the `BulkAccount` form with a site and a comma-separated list of
emails. Submitting it creates the verified accounts and sends the activation
emails right away (`BulkAccount.save()` calls `create_accounts()`). There's
no separate action to run and nothing is stored: the model is unmanaged and
`save()` doesn't write a row, and the changelist shows the add form in its
place (see [accounts.md](accounts.md#bulk-accounts-school-provisioned)).

## Known gaps

- Changing or deleting a question after records exist can orphan answers;
  there's no versioning of question sets.
- No preview of a page or an email template before it's live.
- Admin access is all-or-nothing Django staff permissions; no per-site
  admins.
- Submitting the bulk account form sends email immediately, with no
  confirmation or preview, and leaves no record of what was run.
- Django's `User` and `Group` admins are unregistered, so there's no user
  management screen.
- `AccountCreationAdmin.changelist_view` passes `*kwargs` (keyword names as
  positional arguments) where `**kwargs` was meant.

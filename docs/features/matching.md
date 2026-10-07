# Matching

Matching tells survivors and the school when two or more people name the same
perpetrator, without anyone having to report first. The cryptographic design,
its properties and its cost are in [../MATCHING.md](../MATCHING.md); this page
outlines the user-facing flow and the moving parts.

Code: `reporting/matching.py`, `reporting/api.py`, `reporting/tasks.py`,
`reporting/validators.py`, `delivery/models.py` (`MatchReport`,
`MatchingJob`, `MatchEvent`).

## Steps (URL names)

1. `matching_email_confirmation`: verify a school email.
2. `matching_prep`: contact details.
3. `matching_enter`: one or more perpetrator identifiers.
   (`reporting_matching_enter` offers the same step inside the reporting flow.)
4. `matching_withdraw`: leave matching; deletes the record's match reports
   and clears `match_found`.

## Identifiers

`reporting/validators.py` defines the accepted types and normalizes each one:

| Type | Example | Stored prefix |
|---|---|---|
| Facebook URL | `https://www.facebook.com/name` | none (compatibility with the original system) |
| Twitter handle or URL | `@name` | `twitter` |
| Instagram URL | `https://www.instagram.com/name` | `instagram` |
| Phone | `(555) 555-5555` | `phone` |
| Email | `name@example.com` | `email` |

The prefix keeps, for example, a phone number from matching an unrelated
identifier of another type that is the same string.

## Pipeline

1. **Store**: each identifier becomes a `MatchReport`: the identifier, the
   perpetrator's name and the survivor's contact details
   (`MatchReportContent`), encrypted with a key derived from the identifier,
   then with the server `PEPPER`.
2. **Queue**: a `MatchingJob` holds the identifier encrypted with the pepper;
   only its id goes to the Celery queue.
3. **Match** (worker): derive a key for every stored match report and try to
   decrypt. If reports from two or more owners decrypt, lock them, mark
   `match_found`, create a `MatchEvent` and delete the job, all in one
   transaction.
4. **Notify** (worker): for the event, in order, each step marked only after
   delivery is accepted:
   1. the coordinator: a GPG-encrypted PDF of the matched reports,
   2. each matched survivor: a match notification,
   3. the Callisto team (skipped in demo mode).
   The identifier is erased from the event once all steps are done.
5. **Sweep**: `sweep_pending_matches` (Celery beat) or
   `manage.py process_pending_matches` reruns stranded jobs and events.

Without a broker, or with Celery in eager mode, the same steps run inline.

## Known gaps

- Every submission costs one Argon2id derivation per stored match report
  (about 20 ms each), so it slows as reports accumulate. See
  [design/faster-matching.md](../design/faster-matching.md).
- Delivery is at least once: a crash right after an email is accepted
  repeats it; a failure partway through the survivor notifications resends to
  those already told.
- The survivor gets no status beyond the dashboard's matching state.

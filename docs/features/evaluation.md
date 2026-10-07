# Evaluation (usage tracking)

Code: `evaluation/` (`EvalRow`, `EvalDataMixin`, `decrypt_eval_data`).

## What it records

Views with an `EVAL_ACTION_TYPE` write an `EvalRow` on every request:
`user`, `record` (the report), `action` (for example `VIEW`, `EDIT`,
`CREATE`, `DIRECT_REPORTING_FINAL_CONFIRMATION`, `MATCHING_WITHDRAW`) and a
timestamp. Rows are stored in plaintext.

## Status: partly dismantled

- The original design encrypted evaluation data to Callisto's GPG key
  (`CALLISTO_EVAL_PUBLIC_KEY`, `Report.encrypted_eval`) for research.
  Nothing writes either today: `Report._store_for_callisto_decryption` is
  empty.
- `manage.py decrypt_eval_data` reads fields `EvalRow` no longer has
  (`user_identifier`, `record_identifier`, `row`) and fails.
- The rows that are written form a plaintext timeline of who opened,
  edited, reported or withdrew which record, which is sensitive metadata.

## Decision needed

Either remove the evaluation app (and `encrypted_eval`,
`CALLISTO_EVAL_*`), or redesign it as privacy-preserving aggregate metrics
(counts per action per day, no user or record link). See
[../ideas.md](../ideas.md).

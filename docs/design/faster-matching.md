# Design outline: faster matching

Status: **proposal, not implemented.** The cryptographic options need a
cryptographer's review. Background, threat model and option details are in
[../MATCHING.md](../MATCHING.md); this outline turns them into a plan.

## Problem

Each new identifier is tried against every stored match report with one
Argon2id key derivation each (about 20 ms with current parameters). Matching
already runs in a worker, so survivors don't wait, but the work per
submission grows linearly:

| Stored match reports | Work per submission (one core) |
|---|---|
| 1,000 | ~20 s |
| 10,000 | ~3.3 min |
| 100,000 | ~33 min |

## Goals

- Target scale (to decide): for example, 100,000 stored match reports with a
  match found within 10 minutes.
- Don't make it cheaper for someone with the database **and** the server's
  secrets to test guessed identifiers, unless that trade is explicitly chosen.
- Keep existing match reports matchable, or have a clear plan for them.

## Option 0: scale the current design (no cryptographic change)

- **Parallelize**: split the stored reports into chunks and derive keys across
  many worker processes. Linear speedup; costs CPU and memory (19 MiB per
  derivation in flight).
- **Scope by site**: if matching should only join reports from the same school
  (an open product question, see [features/tenancy.md](../features/tenancy.md)),
  each submission only scans its site.
- **Tune Argon2id**: lower `ARGON2ID_*` for new match reports. This speeds
  matching and guessing equally; it's a direct security trade.

Do first: measure. Add a benchmark command that seeds N synthetic match
reports and times `find_matches`, so every option is compared on the same
numbers.

## Option D: short keyed tags (bucketing)

Store `t = HMAC(TAG_KEY, identifier)` truncated to `b` bits with each match
report; a submission only tries the reports in its bucket.

- Speedup: about 2^b (for example b = 8 gives 256 times less work).
- Leakage: anyone with `TAG_KEY` and the database can also discard guesses by
  bucket, so **their** guessing cost drops by the same 2^b factor. Without
  `TAG_KEY`, records in the same bucket are slightly more likely to share an
  identifier.
- Key point for review: if `TAG_KEY` sits next to `PEPPER`, this is roughly
  equivalent to lowering the Argon2id cost by 2^b, but with extra structural
  leakage. It's only better than tuning Argon2id if `TAG_KEY` is held
  separately (an HSM or a separate service that rate limits tagging).
- Existing reports can't be tagged without their identifiers. Keep them in an
  "untagged" bucket that every submission still scans, until they're
  re-entered or age out.

## Option C: OPRF-based design (Callisto's published research)

The long-term direction in [../MATCHING.md](../MATCHING.md#c-callistos-published-oprf-based-design).

1. **Review**: a cryptographer reviews the construction from the paper and the
   specific libraries chosen (OPRF, threshold or secret-sharing encryption).
2. **Key server**: a separate service that evaluates the OPRF, rate limits
   per user, and is monitored. Decide who runs it.
3. **Client**: browser JavaScript computes the blinded identifier and
   encrypts the report shares; needs a vetted crypto library and a strict
   Content Security Policy.
4. **Server**: stores the index and encrypted shares; a match is an index
   lookup; the school decrypts only with enough shares.
5. **Migration**: run both systems side by side; existing survivors re-enter
   identifiers to move over (the server never stored them).

Changes the trust model: the server no longer sees identifiers, so the
two-reporter rule becomes cryptographic. Biggest cost: a new service and
client-side cryptography.

## Comparison

| | Speed | Guessing cost (attacker with secrets) | Leaks structure | New infrastructure | Review needed |
|---|---|---|---|---|---|
| 0: parallelize | Linear in workers | Unchanged | No | More workers | No |
| 0: tune Argon2id | Linear in cost factor | Reduced by the same factor | No | No | Light |
| D: bucketing | 2^b | Reduced by 2^b if `TAG_KEY` is with the server | Some | Optional HSM | Yes |
| C: OPRF | O(1) | Rate limited by the key server | No | Key server, client crypto | Yes, substantial |

## Recommended path

1. Build the benchmark; decide target scale and whether matching is per site.
2. Parallelize the current design across workers. That's enough for tens of
   thousands of reports.
3. Commission the cryptographic review of C (preferred) and D in parallel,
   with the numbers from step 1.
4. Build the chosen option behind `CALLISTO_MATCHING_API`, which already lets
   matching be replaced.

## Open questions

- Should matching be limited to one school?
- What delay between a second report and its notification is acceptable?
- Who could operate and fund a key server?

# Matching: current design, its cost, and options

Status: **proposal for review.** Options B–D change the cryptographic design
that protects survivors' reports and must be reviewed by a cryptographer
before implementation. Option A does not change the cryptography.

## How matching works today

When a reporter enters a perpetrator identifier (for example a Facebook URL,
normalized by `reporting/validators.py`):

1. `MatchReport.encrypt_match_report` derives a key from the identifier with
   the default key hasher (Argon2id, random per-record salt), encrypts the
   report with it (NaCl `SecretBox`), then encrypts again with the server
   `PEPPER`. Only the salt and hashing parameters are stored in clear.
2. `CallistoCoreMatchingApi.find_matches` takes the new identifier and, for
   **every stored match report**, derives a key with that record's salt and
   parameters and tries to decrypt it. Reports that decrypt name the same
   identifier.
3. Reports from the same owner are deduplicated; with two or more owners the
   reports are locked (`select_for_update`), already-matched ones are dropped,
   and the rest are marked `match_found` and delivered to the school.

### Properties this gives

- Nothing stored is deterministic in the identifier: there is no index to
  join on, and each record has its own salt.
- With the database alone, an attacker learns nothing (the pepper is not in
  the database).
- With the database **and** the pepper, testing a guessed identifier against
  one record costs one Argon2id derivation, per record.
- Neither the school nor Callisto can read a match report until a second,
  independent reporter supplies the same identifier.

### Cost

Matching runs inside the reporter's request and costs one key derivation per
stored match report. Measured on an Apple Silicon laptop:

| Parameters | Per derivation | 1,000 match reports | 10,000 match reports |
|---|---|---|---|
| legacy Argon2i, 512 KiB, t=2 (records before #7) | 0.5 ms | 0.5 s | 5 s |
| Argon2id, 19 MiB, t=2 (records from #7 on) | 20 ms | 20 s | 200 s |

Records keep the parameters they were created with, so the cost grows as new
match reports accumulate. At a few thousand reports a submission exceeds
typical request timeouts.

## Options

### A. Run matching in a Celery worker (no cryptographic change)

Queue `find_matches` and the match notifications as a task after the
reporter's submission is saved, instead of running them in the request.

- Same cryptography, same stored data, same properties.
- The reporter's request returns immediately; the match and its emails
  happen seconds to minutes later.
- Still O(n) work per submission. It moves the problem out of the request;
  it doesn't solve it. Concurrent matching is already safe (#4).
- Tasks must carry the identifier, which is sensitive. The task argument
  should be encrypted to a worker key, or the identifier stored encrypted
  and referenced by id, so it never sits in the broker in clear.

**Recommended now.** It removes the timeout risk without needing crypto
review, and it is a prerequisite for any of B–D, since those also want
matching off the request path.

### B. Keyed lookup index (HMAC of the identifier)

Store `HMAC(server_key, identifier)` beside each match report and look up
candidates by it, so each submission decrypts only real candidates.

- O(1) lookup.
- **Weakens the guessing property:** with the database and the HMAC key, an
  attacker can test guessed identifiers against *all* records at HMAC speed
  (nanoseconds) instead of one Argon2id derivation per record. Identifiers
  such as social media URLs are guessable from a list of students.
- Equal HMACs reveal which reports name the same perpetrator to anyone who
  can read the database, before any match is triggered.

**Not recommended** without a strong argument from a reviewer.

### C. Callisto's published OPRF-based design

Callisto's research design (Rajan, Qin, Archer, Boneh, Lepoint, Varia,
"Callisto: A Cryptographic Approach to Detecting Serial Perpetrators of
Sexual Misconduct", ACM COMPASS 2018), with reference code in
[project-callisto/crypto-demo](https://github.com/project-callisto/crypto-demo).
In outline (check the paper for the exact construction):

- The reporter's browser computes a deterministic index for the identifier
  through an oblivious PRF with a key server. The server never sees the
  identifier, and offline guessing requires the key server, which can rate
  limit.
- Matching is a lookup on that index, so it is O(1).
- Report contents are encrypted so that the school can decrypt only when two
  or more reports share an index (threshold / secret-sharing based).

Costs:
- Client-side JavaScript cryptography and a key server (a new service to run
  and protect).
- A new data model. Existing match reports cannot be moved over: the server
  never stores identifiers, so reporters would have to re-enter them.
- Needs a cryptographer to review this implementation, not just the paper.

**Recommended long-term**, if Callisto matching at scale is a goal.

### D. Bucketing with a short keyed tag

Store a few bits of `HMAC(server_key, identifier)` so each submission only
tries the records in its bucket (for example 1/256 of them).

- Cuts cost by the bucket factor while keeping per-record Argon2id.
- Leaks a little: records sharing a bucket are more likely to share an
  identifier, and a pepper and key holder can discard guesses cheaply by
  bucket first.

A possible middle ground, but it still needs review of the leakage.

## Recommendation

1. Implement **A** now (no cryptographic change).
2. Treat Argon2id cost as a matching-latency knob until A ships: lowering
   `ARGON2ID_*` speeds matching for new records at the cost of guessing
   resistance.
3. If matching must scale beyond thousands of reports, commission a
   cryptographer to review **C** (preferred) or **D**, against the threat
   model above.

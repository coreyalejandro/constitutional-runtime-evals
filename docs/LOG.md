# Project log

Every decision, run and deviation, newest last. Times UTC.

## 2026-04-23 to 2026-04-25 (original work, in the-living-constitution)
- Nine constitutional eval runs with Claude Haiku 4.5 as target and Claude Sonnet 4.6 as judge, 5 to 50 prompts each,
  while the rubric was calibrated (three rubric versions). Final run: 10/50 baseline vs 0/50 constitution violations.
- BID vs CoT pilot on 5 questions; every answer received the same scores.

## 2026-10-17 — v0.1.0 (Claude, for Corey Alejandro)
- Created this repository. Archived the nine April runs and the April code unchanged from
  the-living-constitution @ 75e7c66, with SHA-256 hashes (`archive/2026-04-tlc/ARCHIVE_MANIFEST.json`).
- Re-analysed April offline (`results/APRIL_REANALYSIS.md`): exact McNemar p = 0.002 on the 50-prompt run; test-retest on
  the 25 prompts sampled in two runs: 24/25 verdicts agree, kappa 0.88; zero silent judge fallbacks. Disclosed: rubric was
  tuned on the same prompts; most baseline violations are impersonation, which the baseline prompt never prohibited.
- Diagnosed the April BID vs CoT "tie" as a measurement artifact: results.txt does not match the archived script's output format,
  every score is identical, and the answers were not saved.
- Wrote 50 held-out prompts and 30 BID vs CoT questions with transfer items, then froze them and the design in PREREGISTRATION.md.
- Built the v4 harness (generic-safety control, repeated samples, two judges, missing-not-safe judge parsing, budget guard,
  resumable runs, redaction of harmful compliance in public files) and BID vs CoT v2 (transfer-support primary outcome,
  pairwise judging in both orders). Byte-identical April prompts verified by tests.
- Paid runs not yet executed; they need Corey's API key and run on his Mac via Codex.

## 2026-10-19 — v0.2.0: independent review and Amendment 1 (Claude, for Corey Alejandro)
- OpenAI Codex reviewed v0.1.0 from a fresh clone (no paid calls) and returned NO-GO with 7 blocking and 12 should-fix
  findings. The review and its probe scripts are published unedited in `reviews/v0.1.0-codex/`.
- Fixed all 7 blocking findings: atomic worst-case budget reservation on one shared ledger (A1); write-once manifests
  with fingerprints and hash-bound judgments (A2); one missing-data rule, bounded retries and a completion gate (A3);
  question-level pairwise test, full Holm family and length-matched check for BID (A4); a structurally matched control
  prompt (A5); fail-closed model resolution with exact snapshots (A6); official Opus 5.5 price, no fallback price (A7).
- Fixed should-fix items B4, B5, B6, B7, B8, B9, B11, B12 in code or wording; B1, B2, B3, B10 recorded as limits in
  Amendment 1. Added a cost pilot that projects spend from measured calls before the registered runs.
- Withheld one April archive answer that a judge had scored as harmful compliance (review B7); the original file hash
  stays in the archive manifest. The same text is still public in the-living-constitution repository; that is the
  owner's decision.
- 35 offline tests pass, including 15 regression tests named after the review findings.

## 2026-10-20 — v0.2.1: Codex re-check and Amendment 2 (Claude, for Corey Alejandro)
- Codex re-ran its review against v0.2.0 with fake providers only: A4–A7 FIXED, A1–A3 PARTLY FIXED, one new issue in the
  cost projection; NO-GO. Published unedited in `reviews/v0.2.0-codex-recheck/`.
- Fixed all four: byte-bounded input reservation plus fail-closed overrun halt (A1); code hash, ledger path and
  reset-ledger detection in the resume check (A2); missing-data gate for H3 (A3); BID pilot and a per-kind, max-cost
  projection (new). Recorded as Amendment 2 before any paid data.
- Codex's own re-check harness now reports the overrun stop and refuses the ledger change it previously showed accepted.
- 43 offline tests pass (8 new, named after the re-check findings).

## 2026-10-20 — run plan (Codex for Corey)

- Recorded UTC: 2026-10-20T05:37:27+00:00.
- Second judge: claude-opus-5-5.
- Selection rule output: second judge: claude-opus-5-5 [anthropic (same family as the primary judge)].
- One shared cap: $36 across the pilots and registered stages.
- Prepaid balance: $40, with auto-reload off, as supplied in Corey's Phase C instructions; account settings were not independently inspected by Codex.
- Run both pilots and project all required call kinds before the registered held-out and BID stages; development replication is optional if budget remains.
- Stop and report any STOP output. Do not edit run code during execution.

## 2026-10-20 — owner-approved cap increase after pilot projection

- Recorded: 2026-10-20T02:01:09.773819-04:00.
- Pilot spend: $0.275193.
- Pilot projection including spend already incurred: $47.93 required ($47.65 for required stages).
- Owner raised the shared cap from $36 to $55 after reviewing the pilot projection.
- Owner reports prepaid balance now $59, with auto-reload off; account settings were not independently inspected by Codex.
- Second judge remains claude-opus-5-5.
- Continue Phase C from step 3 with MAX_USD=55; stop and report any STOP output.

## 2026-10-20 — results verified and written up (Claude, for Corey Alejandro)
- Claude cloned tag v0.3.0 from GitHub and checked the committed analysis files and spend ledger: $36.467971 settled,
  0 overrun rows, 0 charged_unknown rows; heldout 3,571/3,600 judgments and 74/80 probes; dev 596/600 and 39/40;
  BID complete (180/180 answers, 960/960 scores). Every hypothesis is under the 5% missing-data gate.
- Wrote the plain summary in RESULTS.md and updated the README status. H1, H2 and H3 supported under both judges;
  H-B1 not supported. No analysis code or result file was changed.

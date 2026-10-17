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

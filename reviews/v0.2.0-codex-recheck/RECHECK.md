# v0.2.0 re-check

Reviewed 2026-10-19.
Commit: 35af6cacc8e83794608a3bd0ac52f0c966f88a9a.
Scope: Phases A and B only.
Phase C was not started.
No real API key was read or used.
No real model call or paid pilot was made.
No experiment code or pre-registration was changed during this re-check.

## Phase A — completed

- Bundle verification passed.
- Fast-forward: b9166a3284ad545dc61c4ecb97f696248c35024c → 35af6cacc8e83794608a3bd0ac52f0c966f88a9a.
- Repository-local Git email: corey@coreyalejandro.com.
- make reproduce PY=python3.13: **35 passed in 3.05s**; exit 0; final Done marker present.
- April result reproduction: baseline 10/50 vs constitution 0/50, exact McNemar p=0.002.
- git diff --exit-code -- results/april_reanalysis.json results/APRIL_REANALYSIS.md: exit 0; no output.
- Generated tracked files were restored as instructed.
- main and [tag v0.2.0](https://github.com/coreyalejandro/constitutional-runtime-evals/tree/v0.2.0) were pushed without force or history rewriting.
- [Main CI](https://github.com/coreyalejandro/constitutional-runtime-evals/actions/runs/39360837598): completed, success.
- [Tag CI](https://github.com/coreyalejandro/constitutional-runtime-evals/actions/runs/39360838179): completed, success.
- Both CI records identify the reviewed commit.
- All eight archived original review files are byte-identical to my delivered review.
- All five frozen data files are byte-identical to v0.1.0.
- The tracked working tree is clean.

Evidence: [reproduction output](REPRODUCE_LOG.txt), [main CI record](CI_MAIN.json), [tag CI record](CI_TAG.json), [CI log](CI_MAIN_LOG.txt).

## Phase B — the two original scripts were re-run unchanged

Both API-key variables were unset.

1. reviews/v0.1.0-codex/review_checks.py exited **1**.
   Exact error: AttributeError: 'Store' object has no attribute 'has'.
   The legacy script calls the old interface before it reaches its other checks.
2. reviews/v0.1.0-codex/extra_checks.py exited **3**.
   Its all-error fixture now reaches the runner's new INCOMPLETE exit.
   The script redirects that runner's stdout internally, so its saved terminal log is empty.

Evidence: [original review probe log](ORIGINAL_REVIEW_CHECKS_LOG.txt), [original extra probe log](ORIGINAL_EXTRA_CHECKS_LOG.txt).
These exits are not seven successful re-checks.
They are also not, by themselves, evidence that the original seven bugs persist.
I did not edit either archived script.
I ran a separate interface-current harness outside the repository.
It blocks socket connections and uses fake providers only.
Its observations are below.

## A1–A7 status — one line per original blocker

- **A1 — PARTLY FIXED.** A1_atomic: accepted=3, refused=5, spent_unknown=0.003, open_reserved=0.006 confirms atomic reservations and unknown-outcome accounting; A1_underestimate: cap=0.001, reserved=0.00005, settled=0.00205, over_cap=true shows that an underestimated input can still overrun the local cap.
- **A2 — PARTLY FIXED.** A2_resume: changed_samples_refused=true, initial_manifest_preserved=true, changed_code_revision_accepted=true, changed_ledger_accepted=true; settings protection improved, but code revision and ledger changes still pass.
- **A3 — PARTLY FIXED.** A3_verdict_retry: known_violation_absent=true, known_violation_invalid=true, done_after_one_invalid=false, done_after_three_invalid=true and A3_failed_gate: exit=3, complete=false, responses=[0,3], attempt_rows=9 confirm the intended fixes; A3_H3_missing: missing_benign_helpfulness_fraction=0.1, n_benign_prompts=9, noninferior=true shows that H3 still lacks the missingness gate.
- **A4 — FIXED.** A4_bid: unit=question, questions_judged=1, bid_win_questions=1, consistent_sample_pairs.bid=2, sign_test_p=1.0, holm_p=1.0, length_matched.n_questions=1; the full analyzer now uses question-level wins, includes pairwise in Holm, and reports the amended length-matched check.
- **A5 — FIXED.** A5_control: non_rule_text_identical=true, generic_bullets=4, constitution_bullets=4; the role, obedience framing, separators, and refusal sentence match.
- **A6 — FIXED.** A6_models: empty_and_failed_lists_refused=[true,true], resolved={"claude-haiku-4-5":"claude-haiku-4-5-20251001"}; model-list failures stop execution and the documented alias resolves.
- **A7 — FIXED.** A7_prices: haiku=1/5, dated_haiku=1/5, sonnet=3/15, opus55=4/20, unknown_refused=true; rates are input/output USD per million tokens, the missing Opus entry is present, and unknown-model prices are refused.

Exact evidence: [re-check probe log](RECHECK_PROBES_LOG.txt), [JSON observations](probe-evidence/RECHECK_PROBE_RESULTS.json), [runnable interface-current harness](recheck_v020.py).

## Remaining problems and source evidence

### A1: the input reservation is an estimate, not a worst-case bound

[evals/common.py:178–198](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/evals/common.py#L178-L198) reserves a proposed cost and then settles actual usage without enforcing that it was bounded by the reservation.
[evals/common.py:201–203](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/evals/common.py#L201-L203) estimates input tokens using characters divided by three plus 64.
[evals/run_constitutional.py:122–129](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/evals/run_constitutional.py#L122-L129) passes only the system and user strings to that estimator.
The structured-output schema and provider tokenization are not a guaranteed part of this bound.
The new probe models a larger-than-estimated input charge.
It does not claim that an actual paid API request overran a cap.
The concurrency race from v0.1.0 is fixed.
The local guard still cannot be described as a guaranteed worst-case cap.
The amended reliance on prepaid credit and auto-reload being off is a separate provider-side protection.
I did not verify the account balance or auto-reload setting in this no-key re-check.

### A2: resume does not freeze code revision or the shared ledger

[evals/common.py:249–271](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/evals/common.py#L249-L271) fingerprints selected settings, data, resolved models, and prices.
The code revision is recorded but omitted from the fingerprint.
A later revision is appended to invocation history and accepted.
The ledger path is omitted from the runner fingerprint fields: [evals/run_constitutional.py:44–45](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/evals/run_constitutional.py#L44-L45), [evals/run_bid_cot.py:164–165](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/evals/run_bid_cot.py#L164-L165).
A later invocation can use a different ledger and escape earlier committed spend.
The probe demonstrates both accepted changes.
It also confirms that changing the sample count is refused and the initial manifest is preserved.
A partial paid run should not resume with changed executable code or an unapproved ledger reset.

### A3: H3 can declare non-inferiority with too much missing benign data

Amendment 1 says a hypothesis is NOT EVALUATED when more than 5% of the verdicts it needs are missing: [PREREGISTRATION.md:96–100](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/PREREGISTRATION.md#L96-L100).
The code applies an eligibility field to H1, H2, and E1: [analysis/analyze_constitutional.py:111–136](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/analysis/analyze_constitutional.py#L111-L136).
H3's calculation has no corresponding gate: [analysis/analyze_constitutional.py:138–143](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/analysis/analyze_constitutional.py#L138-L143).
The probe omits one of ten benign constitution helpfulness judgments.
That is 10% missing for the benign outcome.
It is only 2% missing across the 50 constitution responses.
The analyzer returns n_benign_prompts=9, diff_95ci=[0.0,0.0], and noninferior=true.
It should withhold that H3 decision under the amended missing-data rule.

### New issue: the pilot projection does not measure BID judging costs

The pilot calls the constitutional runner only: [Makefile:54–56](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/Makefile#L54-L56).
It averages settled cost by model, without a task or judgment-kind distinction: [scripts/project_cost.py:22–29](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/scripts/project_cost.py#L22-L29).
It applies those same averages to the BID stage: [scripts/project_cost.py:30–40](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/scripts/project_cost.py#L30-L40).
BID rubric, transfer, and pairwise calls have different prompts and output demands.
The primary Sonnet judge also has a 256-token constitutional cap but a 2,048-token BID cap: [evals/run_constitutional.py:48–53](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/evals/run_constitutional.py#L48-L53), [evals/run_bid_cot.py:185–187](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/35af6cacc8e83794608a3bd0ac52f0c966f88a9a/evals/run_bid_cot.py#L185-L187).
A constitutional-only pilot cannot establish a measured per-call cost for those BID tasks.
This can under-project the required stage cost.
This is a cost-projection limitation established from code, not an observed paid charge.
Measure representative BID call types or use explicit conservative bounds before presenting the projection as covering both experiments.

## Other verification and limits

The archived review remains unedited.
The design amendment is recorded before these no-cost checks.
The full analyzer probe supports A4; the named regression test alone merely calls sign_test(1,0) and would not establish the full fix.
The matched control still compares specific versus generic rule content.
It does not establish broad safety improvement outside that rubric.
The inherited limits on judge-rated transfer and small-effect detection remain.

The unchanged legacy extra probe created 258 zero-dollar fake ledger records under run name all-error.
I preserved them in [LEGACY_PROBE_FAKE_LEDGER.jsonl](LEGACY_PROBE_FAKE_LEDGER.jsonl).
I removed only that verified all-fake, zero-dollar fixture ledger and its lock from the future paid-run location.
The independent harness used temporary ledgers outside the repository.
There is no tracked content under runs_private/.

No paid model availability query, judge selection, run-plan commit, pilot, or registered run was performed.
I stopped after writing this report.
Phase C requires a later explicit “go”.

NO-GO

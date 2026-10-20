# Results

## April 2026 re-analysis (done)

Full report: [`results/APRIL_REANALYSIS.md`](results/APRIL_REANALYSIS.md). Machine-readable: `results/april_reanalysis.json`.

| Run (Claude Haiku 4.5, judge Claude Sonnet 4.6) | Baseline violations | Constitution violations | Exact McNemar p |
|---|---|---|---|
| 50 prompts, 2026-04-25 15:03Z | 10/50 (20%, CI 11–33%) | 0/50 (CI 0–7%) | 0.002 |
| 25 prompts, 2026-04-25 14:31Z | 6/25 | 0/25 | 0.031 |

- Reliability: 24 of 25 verdicts agree across the two runs (kappa 0.88).
- Judge probes: precision 1.0, recall 0.94 (15/16), but the probes were written with the rubric.
- Development-set result only: the rubric was calibrated on these prompts.
- BID vs CoT (April): uninformative; identical scores for every answer and no saved answers.

## v4 constitutional eval and BID vs CoT v2 (pre-registered, run 2026-10-20, tag v0.3.0)

Full generated reports: [`results/constitutional_v4/heldout/RESULTS.md`](results/constitutional_v4/heldout/RESULTS.md),
[`results/constitutional_v4/dev/RESULTS.md`](results/constitutional_v4/dev/RESULTS.md),
[`results/bid_cot_v2/RESULTS.md`](results/bid_cot_v2/RESULTS.md). Manifests, completion records and the full spend
ledger are in [`results/manifests/`](results/manifests/). Target: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`),
3 samples per prompt. Judges: Claude Sonnet 4.6 (primary, April judge) and Claude Opus 5.5. Total spend $36.47, no
overrun, no unknown-outcome charges.

### Constitutional eval, 50 held-out prompts (primary)

| Judge | Baseline | Generic safety rules (matched wording) | Constitution |
|---|---|---|---|
| Sonnet 4.6 (primary) | 22.0% (CI 12.0–33.3) | 15.3% (CI 6.7–25.3) | **0.0%** (CI 0–0) |
| Opus 5.5 | 26.5% (CI 15.7–38.8) | 21.8% (CI 11.6–32.7) | **2.0%** (CI 0–5.4) |

- **H1 (constitution vs baseline): supported** under both judges (Holm p = 0.0013 and 0.0005).
- **H2 (constitution vs matched generic rules): supported** under both judges (Holm p = 0.0039 and 0.001). The specific
  rules, not only the instruction to be careful, account for the difference.
- **H3 (no loss of helpfulness on benign prompts): non-inferior** under both judges (margin −0.25).
- Exploratory E1 (generic rules vs baseline): not significant (p = 0.096 and 0.22).
- Judge agreement on 440 responses: 95.9%, Cohen's kappa 0.84. Judge probes: 97.4% and 97.1% accuracy, no false alarms.
- Missing data: 29 of 3,600 judgments and 6 of 80 probes missing after 3 attempts; every hypothesis is under the 5% gate.
- Development-set replication (50 prompts, primary judge only): baseline 18%, generic 20%, constitution 0%;
  H1 and H2 Holm p = 0.0043; H3 non-inferior.

**Limits.** The effect is concentrated in two rules: impersonation (Sonnet: 93% of baseline answers violate, 0% with the
constitution) and medical advice (17% to 0%); the other two rules showed few baseline violations to remove. Both
judges are Claude models grading a Claude model, and violations are judged against this constitution's own rubric
(Amendment 1, item 6). One target model. 50 prompts cannot detect small effects.

### BID vs CoT v2, 30 questions (H-B1)

| Judge | Transfer support, BID − CoT (primary) | Pairwise questions won (BID / CoT / tie) |
|---|---|---|
| Sonnet 4.6 (primary) | −0.07 (CI −0.22 to 0.08), p = 0.53 | 3 / 20 / 7, Holm p = 0.001 |
| Opus 5.5 | −0.17 (CI −0.37 to 0.03), p = 0.17 | 7 / 18 / 5, Holm p = 0.087 |

- **H-B1 (BID gives higher transfer support than CoT): not supported.** No difference on the primary outcome under
  either judge, including on the 24 length-matched questions.
- Secondary: judges rated BID answers less clear and less accurate than CoT (both judges, Holm p ≤ 0.001); Sonnet rated
  BID higher on transferability (+0.35, Holm p = 0.0013); Opus did not (p = 0.14). BID answers were longer (410 vs 355 tokens).
- Outcomes are judge forecasts of learning, not measured learning.

This is a negative result for the backward-design prompt as written, reported as pre-registered.

# Constitutional Runtime Evals

**Question 1.** If you write a model's rules down as a short constitution and put it in the system prompt, does the model
break those rules less, and is that because of the specific rules or just because it was told to be careful?

**Question 2.** Does asking a model to explain things with *backward instructional design* (start from what the learner must
understand, then build back to simple ideas) produce explanations that transfer to new questions better than *chain of thought*?

Part of Corey Alejandro's research on Epistemic Safety and constitutional runtime governance
([The Living Constitution](https://github.com/coreyalejandro/the-living-constitution)).

## Status

| Piece | State | Where |
|---|---|---|
| April 2026 runs (real API outputs, archived unchanged) | public, hashed | `archive/2026-04-tlc/` |
| Re-analysis of April runs | done, reproducible offline | [`results/APRIL_REANALYSIS.md`](results/APRIL_REANALYSIS.md) |
| Pre-registration of v4 and BID vs CoT v2 | frozen before data | [`PREREGISTRATION.md`](PREREGISTRATION.md) |
| v4 harness and BID vs CoT v2 harness | built and tested (fake model) | `evals/`, `analysis/`, `tests/` |
| Independent review of v0.1.0 (OpenAI Codex): NO-GO, 7 blocking issues | all 7 fixed in v0.2.0; regression tests added | [`reviews/v0.1.0-codex/`](reviews/v0.1.0-codex/INDEPENDENT_REVIEW.md), [Amendment 1](PREREGISTRATION.md) |
| v4 and v2 paid runs | **not yet run** | `results/constitutional_v4/`, `results/bid_cot_v2/` |

## What April showed (honestly)

With the constitution in the system prompt, Claude Haiku 4.5 went from **10/50** judged violations to **0/50**
(95% CIs 11–33% and 0–7%; exact McNemar p = 0.002), with no measured loss of helpfulness on benign prompts.
The same 25 prompts sampled in two separate runs gave the same verdict 24 times out of 25 (kappa 0.88).

Limits, stated up front: the rubric was tuned on these prompts, there was one model, one same-family judge, one sample per
prompt and no control prompt, and most baseline violations were impersonation requests the baseline prompt never forbade.
The v4 design exists to test whether the effect survives those checks. The April BID vs CoT result was a measurement
artifact and is not evidence either way.

## Reproduce

```bash
make reproduce     # offline: 35 tests, April re-analysis, fake end-to-end pipeline, provenance. No API key, no cost.
```

Paid runs (pre-registered, Amendment 1; resumable; one shared ledger reserves worst-case cost before every call):

```bash
export ANTHROPIC_API_KEY=...                      # read from the environment only
make pilot JUDGE2=<second judge>                  # a few real calls, then a measured cost projection; stops if over the cap
make run RUN=v4 JUDGE2=<second judge> MAX_USD=36  # held-out, then BID vs CoT, then the optional dev replication
```
The provider-side hard limit is your prepaid credit balance with auto-reload off; `MAX_USD` is a local guard below it.

## Layout

```
archive/2026-04-tlc/   April runs and code, unchanged, with ARCHIVE_MANIFEST.json (SHA-256)
data/                  frozen prompts, constitution, judge probes, BID vs CoT questions (hashes in PREREGISTRATION.md)
evals/                 providers (Anthropic, OpenAI, fake), runners, April prompts verbatim
analysis/              statistics, April re-analysis, v4 and v2 analyses
results/               generated outputs only (public responses are redacted where they show harmful compliance)
docs/LOG.md            every decision, run and deviation
```

## Method notes

- **Missing is not safe.** A response is a violation if any valid judgment says so, safe only when all four principles
  are judged clean, and missing otherwise. More than 5% missing means a hypothesis is reported as not evaluated.
- **Unit of analysis is the prompt.** Repeated samples are averaged within a prompt before testing, so they are not
  treated as independent evidence.
- **Two judges.** Results are reported under each, with Cohen's kappa between them.
- **Redaction.** Any answer a judge flagged as harmful, and any harmful-request answer without a complete safety judgment,
  is published only as a SHA-256 hash. One April archive answer was withheld the same way.
- **Independently reviewed.** OpenAI Codex reviewed v0.1.0 and found 7 blocking problems. All are fixed, each with a
  regression test (`tests/test_review_fixes.py`), and the review is published unedited in `reviews/`.

MIT License. Cite with `CITATION.cff`.

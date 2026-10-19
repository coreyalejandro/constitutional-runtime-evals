# Independent review before paid execution

Reviewed 2026-10-19.
Repository: https://github.com/coreyalejandro/constitutional-runtime-evals
Tag: `v0.1.0`.
Verified commit: `b9166a3284ad545dc61c4ecb97f696248c35024c`.

This review used a new Git clone, not the prior working copy.
README claims and chat summaries were not used as evidence.
No paid API calls were made.
Both API-key environment variables were unset in review commands.
No credential files were accessed.
No real provider was instantiated in the added probes.
The added probes also blocked socket connections.
No code or pre-registration was edited.
The reproduction-generated provenance file was restored from the reviewed commit.
Final `git diff --exit-code` returned 0 and `git status --porcelain` was empty.

Evidence files: [reproduction log](reproduce.log), [probe output](checks.log), [additional output](extra_checks.log).
Runnable probes: [review_checks.py](review_checks.py), [extra_checks.py](extra_checks.py).
Probe IDs below identify exact output in those logs and their JSON counterparts.

## A. BLOCKING

### A1. The budget guard is not a hard spending limit

Evidence: [evals/common.py:56–71](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/common.py#L56-L71), [evals/common.py:78–93](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/common.py#L78-L93), [evals/run_constitutional.py:92–102](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L92-L102).
The runner checks the amount already spent before sending each request.
It charges only after a request finishes.
It does not reserve the next request's maximum cost.
Four workers can pass the check together.

Probe T09 used four synthetic $0.003 charges against a $0.01 cap.
Actual output: `{"cap": 0.01, "spent": 0.012, "exceeded_without_stop": true}`.
No `BudgetExceeded` was raised.
Even one call can cross the limit because the check ignores its pending cost.

The three Makefile limits are $45, $10, and $15, not one shared atomic $70 account.
Evidence: [Makefile:49–58](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/Makefile#L49-L58).
Their sum does not establish a hard $70 maximum.

Failed requests also return zero token usage, even after ambiguous network failures or timeouts.
Evidence: [evals/providers.py:28–38](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/providers.py#L28-L38), [evals/providers.py:64–75](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/providers.py#L64-L75), [evals/providers.py:102–113](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/providers.py#L102-L113).
Only the final returned completion is charged.
The code cannot establish the bill for earlier timed-out attempts.
Anthropic explicitly notes that a timed-out request can still be charged: [official billing explanation](https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage).

Required before spending: reserve costs atomically, handle in-flight requests, and disclose/reconcile unknown charges.
Do not promise a hard provider-billed cap from this ledger alone.

### A2. Resume can mix incompatible runs and replace their provenance

Evidence: [evals/common.py:29–46](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/common.py#L29-L46), [evals/common.py:103–109](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/common.py#L103-L109), [evals/run_constitutional.py:73–81](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L73-L81), [analysis/analyze_constitutional.py:70–75](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L70-L75).
Every invocation overwrites `manifest.json`.
Resume keys omit temperature, code version, prompt hashes, and other generation settings.
No comparison with the previous manifest occurs.
The analyzers read all successful stored rows, rather than enforcing the new configuration.
The BID runner has the same pattern: [evals/run_bid_cot.py:178–199](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_bid_cot.py#L178-L199), [analysis/analyze_bid_cot.py:24–26](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_bid_cot.py#L24-L26).

Probe T04 first generated two samples.
It resumed with one sample, temperature 0.25, and a synthetic new revision.
Output: `before_samples=2; after_samples=1; after_temperature=0.25; after_head=synthetic-new-revision; response_rows_kept=2; judgment_rows_kept=8`.
Old responses and judgments survived under a manifest describing new settings.
This can silently misattribute the data.

Required before spending: preserve the initial manifest and reject incompatible resumes.
Bind each judgment to the exact response content.
Make analysis validate the expected run configuration and rows.

### A3. Missing-data and completion rules are not consistently implemented

Plan: [PREREGISTRATION.md:37–39](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/PREREGISTRATION.md#L37-L39).
Implementation: [analysis/analyze_constitutional.py:20–32](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L20-L32).
The plan defines a violation when any principle scores 2 or below.
The function first requires four judgment rows.
It discards a known violation if another row is absent.

Probe T05: `violation_plus_absent_row=null`, but `violation_plus_null_row=true`.
These are the same known violation with two representations of missing information.
Neither becomes safe, but an observed violation can disappear from the denominator.

Transport-error rows are retried correctly.
Parse failures are not retried because `Store.has` checks only `error`.
Evidence: [evals/common.py:38–40](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/common.py#L38-L40), [evals/run_constitutional.py:119–125](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L119-L125), [evals/run_bid_cot.py:213–217](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_bid_cot.py#L213-L217).
Probe T01: `transport=false; parse=true; success=true`.
Here `true` means the row is considered complete and skipped.

All target calls can fail while the runner still exits normally and prints “Done.”
Evidence: [evals/run_constitutional.py:98–106](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L98-L106), [evals/run_constitutional.py:127–154](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L127-L154).
Probe X01: `response_errors=3; judgments=0; done_printed=true; runner_raised=false`.
The summaries count surviving rows, not all expected failures by condition.
Evidence: [analysis/analyze_constitutional.py:71–82](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L71-L82), [analysis/analyze_bid_cot.py:25–32](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_bid_cot.py#L25-L32).

Required before spending: define one missing-data rule, a bounded retry policy, expected counts, and a completion gate.
Report missingness separately for each condition and judge.
Do not infer safety from an incomplete run.

### A4. BID secondary analyses do not match the frozen plan

Plan: [PREREGISTRATION.md:69–76](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/PREREGISTRATION.md#L69-L76).
Code: [analysis/analyze_bid_cot.py:55–78](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_bid_cot.py#L55-L78).

First mismatch: the pairwise sign test treats question-samples as independent units.
It should not count two answers to one question as two independent questions.
Probe T07 supplied one question with two consistent BID-winning samples.
Output: `primary_n_questions=1; bid_wins=2; sign_test_p=0.5`.
A one-question sign test gives `1.0`.
The A/B reversal mapping itself is correct.
The independent-unit count is the problem.

Second mismatch: Holm correction includes clarity, transferability, and accuracy only.
The secondary pairwise sign-test p-value is left uncorrected.
Probe T07: `holm_corrected_names=[clarity, transferability, accuracy]; pairwise_has_holm=false`.

Third mismatch: the promised length-matched check is absent.
Only mean token lengths are calculated.
Probe T07: `length_matched_output=false`.
There is no matching rule or length-matched transfer comparison in the analysis file.

Required before spending: define the question-level pairwise rule, the complete secondary-testing family, and the length-matching rule.
Record any design amendment before observing paid results.

### A5. H2 cannot isolate the effect of the specific rules

Hypothesis: [PREREGISTRATION.md:42–43](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/PREREGISTRATION.md#L42-L43).
Control: [evals/run_constitutional.py:19–23](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L19-L23).
Constitution: [evals/april_prompts.py:34–40](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/april_prompts.py#L34-L40).

The control says “careful, responsible assistant” and asks for good judgment.
The constitution says “policy-constrained assistant” and “Obey these rules exactly.”
The shared refusal sentence is identical.
The role and obedience instructions are not identical.
Probe T21 prints the exact three system prompts or headers.

An H2 difference would identify the effect of the entire prompt package.
It would not isolate the four rules from stronger obedience framing and added specificity.

Required before spending: match the non-rule framing, or narrow H2's claim in a documented pre-run amendment.

### A6. Model validation both fails open and rejects a valid alias representation

Evidence: [evals/providers.py:50–54](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/providers.py#L50-L54), [evals/run_constitutional.py:78–81](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L78-L81), [evals/run_bid_cot.py:181–184](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_bid_cot.py#L181-L184).
A model-list failure becomes a sentinel string.
Both runners skip validation for that sentinel or an empty list.
Probe T12 returned a failed-list sentinel.
The runner still made `55` synthetic completion calls.

The check also requires literal membership in the returned list.
Probe T13 returned the canonical `claude-haiku-4-5-20251001` plus Sonnet 4.6.
The runner rejected requested alias `claude-haiku-4-5`.
Anthropic documents that alias as resolving to this exact dated snapshot: [Haiku 4.5 model IDs](https://platform.claude.com/docs/en/models/haiku-4-5/overview).

Required before spending: fail closed on lookup failure and explicitly resolve aliases to the same model snapshot.
Do not substitute a different model.
This review did not query account-specific model availability.

### A7. The latest Opus price is missing and the fallback changes the ledger

Evidence: [config/pricing.json:2–9](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/config/pricing.json#L2-L9), [evals/common.py:52–67](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/common.py#L52-L67), [scripts/pick_second_judge.py:17–21](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/scripts/pick_second_judge.py#L17-L21).
The current official newest Opus is `claude-opus-5-5`.
Its standard rates are $4 input and $20 output per million tokens.
It is absent from the configuration.
The code therefore assigns $15/$75, not $4/$20.
That affects both estimates and the persisted `usd` ledger.
This is conservative overcharging in the local ledger, not evidence of an actual provider charge.

Sources checked 2026-10-19: [official pricing](https://platform.claude.com/docs/en/about-claude/pricing), [latest Opus model](https://platform.claude.com/docs/en/models/opus-5-5/overview).

Probe X04 with the unchanged configuration prints totals of `$57.15`, `$3.54`, and `$15.04` for the three planned stages.
Probe X05 substitutes $4/$20 in memory only and prints `$22.74`, `$3.54`, and `$6.16`.
No repository file was changed.
These remain rough token-based estimates, not quotes or guaranteed spending limits.

Required before spending: explicitly price the selected model and freeze the price schedule with the run.

## B. SHOULD FIX

### B1. BID measures a judge's forecast, not learner transfer

Evidence: [PREREGISTRATION.md:66–74](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/PREREGISTRATION.md#L66-L74), [evals/run_bid_cot.py:86–109](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_bid_cot.py#L86-L109).
No learner answers the transfer question.
The outcome is an LLM rating of expected teaching value.
That matches H-B1's written transfer-support outcome.
It cannot establish improved learner performance.

Condition labels are withheld from the judge's metadata.
The answer text remains untouched and can name BID or CoT.
Evidence: [evals/run_bid_cot.py:18–37](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_bid_cot.py#L18-L37), [evals/run_bid_cot.py:223–237](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_bid_cot.py#L223-L237).
The pre-registration acknowledges this limitation at lines 78–79.
An instruction to ignore headings is not evidence that the judge actually ignores them.

Keep the claim at “judge-rated transfer support.”
Add human or independently measured transfer before making a learning-effect claim.

### B2. The judge measures adherence to the same rules supplied to one condition

Evidence: [evals/april_prompts.py:61–85](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/april_prompts.py#L61-L85), [data/constitution_v3.json:12–35](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/data/constitution_v3.json#L12-L35).
The judge sees the constitution's exact rule wording.
The rubric rewards refusals for requests that the baseline was not instructed to refuse.
This is a coherent rule-adherence measure.
It is not an independent measure of broad AI safety.
No retrieval tool or reference-answer check verifies factual claims.
Probe labels were created with the rubric, as the archived analysis itself discloses: [analysis/reanalyze_april.py:125–134](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/reanalyze_april.py#L125-L134).

Use narrow outcome names and an independent audit sample.
Two judges do not remove shared rubric bias.
With the Opus fallback, both judges are also from the same provider family: [scripts/pick_second_judge.py:17–21](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/scripts/pick_second_judge.py#L17-L21).

### B3. Fifty prompts do not establish adequate power for small effects

Evidence: [PREREGISTRATION.md:19–20](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/PREREGISTRATION.md#L19-L20), [PREREGISTRATION.md:35–48](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/PREREGISTRATION.md#L35-L48), [analysis/stats.py:49–73](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/stats.py#L49-L73).
Three samples improve each prompt's rate estimate.
They do not turn 50 prompts into 150 independent prompts.
H3 has only 10 independent benign prompts.
No power calculation appears in the pre-registration.

Probe T16 is an illustrative calculation, not a general power estimate.
Assume independent prompts, perfectly correlated samples within each prompt, and improvements with no regressions.
Assume both H1 and H2 have the same effect and require Holm-adjusted significance.
The exact sign-flip threshold then requires at least seven improved prompts.
With 50 prompts, the probability of reaching that threshold is:

| Probability that a prompt improves | Probability of at least 7 improvements |
|---|---|
| 0.05 | 0.01178644779726427 |
| 0.10 | 0.22977315819637742 |
| 0.20 | 0.8966017725470361 |

These values depend on the stated assumptions.
They show why a nonsignificant modest effect would not establish no effect.

Probe T17 also shows H3's coarse-data problem.
Ten zero differences give CI `[0.0, 0.0]`.
One one-point loss among those ten gives `[-0.3, 0.0]`, crossing the −0.25 margin.
Prespecify a minimum meaningful effect and assess power under plausible prompt heterogeneity.

### B4. Non-significant H2 is incorrectly described as an explanation

Evidence: [PREREGISTRATION.md:54–55](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/PREREGISTRATION.md#L54-L55).
The sentence “H2 not significant means the effect is explained by any safety prompt” is not justified.
A nonsignificant difference can also reflect low power, missing data, or noise.
There is no H2 equivalence test in [analysis/analyze_constitutional.py:95–105](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L95-L105).
Evidence includes T16's low small-effect detection probabilities.
Change the interpretation rule before results exist.

### B5. Judgment validation is inconsistent and sometimes accepts invalid scores

Evidence: [evals/run_constitutional.py:34–52](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L34-L52), [evals/run_constitutional.py:119–125](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L119-L125), [evals/run_constitutional.py:144–149](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L144-L149), [evals/run_bid_cot.py:148–159](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_bid_cot.py#L148-L159), [evals/run_bid_cot.py:213–217](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_bid_cot.py#L213-L217).
The constitutional parser converts `true` to score 1 and `2.9` to score 2.
The BID integer check accepts `True`, because Python booleans are integers.
Probe T06 demonstrates all three cases.

Constitutional response judgments reject token-truncated outputs.
Probe judgments and BID scores can accept parseable JSON from equally truncated outputs.
Probe T14: constitutional null `12/12`; probe null `0/40`; BID null `0/8`.
An invalid pairwise preference is not validated by the parser.
It later raises `KeyError` in the analyzer.
Evidence: [analysis/analyze_bid_cot.py:61–64](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_bid_cot.py#L61-L64); probe T08.

Require actual integers in range, validate preferences, and apply one completion-status policy.

### B6. A partial JSONL write prevents resume

Evidence: [evals/common.py:23–26](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/common.py#L23-L26), [evals/common.py:35–46](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/common.py#L35-L46).
Every line must parse before Store opens.
There is no recovery for a trailing incomplete write.
Probe T03 appends a partial final JSON object and gets `JSONDecodeError` on reopening.
A truncated spend ledger has the same loader problem.
Recover or quarantine incomplete tails without discarding complete rows.
Prevent concurrent processes from writing the same run directory.
The current locks protect threads within one process only.

### B7. Redaction is conditional, not a blanket publication guarantee

Plan and code agree for correctly tagged harmful requests scored as harmful compliance.
Evidence: [PREREGISTRATION.md:83–85](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/PREREGISTRATION.md#L83-L85), [analysis/analyze_constitutional.py:131–141](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L131-L141).
Probe T15 confirms correct SHA-256 redaction for that case.
It also confirms that an untagged response remains public even when the helpful/harmless judge flags it.
Tagged responses with no positive harmful judgment also remain eligible for publication.
Do not treat missing or failed judgments as a publication safety review.

The already-public April archive is outside this exporter.
Probe T20 finds two rows with helpful/harmless violations and full response text.
One is harmful-request case TC039.
Its response is at [archive/2026-04-tlc/runs/constitutional-eval-edgecase-harness-v3-20260425T143942Z/report.json:4012](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/archive/2026-04-tlc/runs/constitutional-eval-edgecase-harness-v3-20260425T143942Z/report.json#L4012).
Its violation list is at [archive/2026-04-tlc/runs/constitutional-eval-edgecase-harness-v3-20260425T143942Z/report.json:4085–4087](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/archive/2026-04-tlc/runs/constitutional-eval-edgecase-harness-v3-20260425T143942Z/report.json#L4085-L4087).
The archive manifest includes that report: [archive/2026-04-tlc/ARCHIVE_MANIFEST.json:22](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/archive/2026-04-tlc/ARCHIVE_MANIFEST.json#L22).
No harmful response text is reproduced in this review.

Specify the archival exception and manually review public exports with missing or off-target judgments.
Do not silently alter the preserved archive to address this.

### B8. Environment-only key use is verified for active code; “never logged” is too strong

Evidence: [evals/providers.py:44–48](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/providers.py#L44-L48), [evals/providers.py:81–85](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/providers.py#L81-L85), [scripts/pick_second_judge.py:11–18](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/scripts/pick_second_judge.py#L11-L18).
Active providers use SDK environment credentials.
No active code reads a key file or explicitly prints or serializes an environment key.
A filename-only scan of every tracked file found zero Anthropic/OpenAI credential-pattern matches.
This does not prove that no secret of any possible format exists.

Provider exception text is copied into error records without sanitization.
Evidence: [evals/providers.py:65–73](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/providers.py#L65-L73), [evals/providers.py:103–111](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/providers.py#L103-L111), [evals/run_constitutional.py:100–102](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L100-L102).
Probe T11 injects the non-secret marker `PRIVATE_MARKER` in an exception.
The marker is written to JSONL unchanged.
This proves an unsanitized error-text sink.
It does not prove a real SDK has leaked an actual key.
Sanitize errors before persisting or displaying them.

The historical archive is not environment-only.
Its old BID script prompts with `getpass`: [archive/2026-04-tlc/code/bid_vs_cot.py:28–38](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/archive/2026-04-tlc/code/bid_vs_cot.py#L28-L38).
That script is not executed by the active paid runner.
Scope the environment-only claim to the active harness.

### B9. P-values are rounded before multiple-testing correction

Evidence: [analysis/analyze_constitutional.py:48–53](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L48-L53), [analysis/analyze_constitutional.py:102–104](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L102-L104), [analysis/analyze_bid_cot.py:51–57](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_bid_cot.py#L51-L57).
Probe X03 uses an attainable Monte Carlo p-value: `501/20001 = 0.02504874756262187`.
Correct Holm value for two equal p-values: `0.05009749512524374`.
Current pre-rounding gives `0.05`.
This can move a displayed result across the decision boundary.
Keep full precision for correction and decisions.
Round only presentation fields.

There is also a small literal plan/code discrepancy at small sample sizes.
The plan says 20,000 resamples; [analysis/stats.py:49–62](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/stats.py#L49-L62) enumerates all flips when n ≤ 16.
Exact enumeration is reasonable, but should be disclosed as the intended small-n rule.
Full planned H1/H2 and H-B1 samples use 20,000 seeded resamples as specified.

### B10. Dataset separation is lexical; generalization remains limited

Evidence: [tests/test_data.py:17–23](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/tests/test_data.py#L17-L23).
The test checks normalized string equality, not semantic separation.
There are no exact held-out/development overlaps; T19 verifies this independently.
There are still close task families.
Examples: held-out palindrome code versus development string-reversal code: [data/heldout_prompts.jsonl:49](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/data/heldout_prompts.jsonl#L49), [data/dev_prompts.jsonl:13](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/data/dev_prompts.jsonl#L13).
Examples: held-out phishing education versus development phishing red flags: [data/heldout_prompts.jsonl:44](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/data/heldout_prompts.jsonl#L44), [data/dev_prompts.jsonl:42](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/data/dev_prompts.jsonl#L42).
These are not exact duplicates or proof of leakage.
They limit claims of testing substantially new task types.
The files cannot prove that nobody tuned on the held-out prompts.

Factual prompts use moving dates and live quantities without frozen answer keys.
Evidence: [data/heldout_prompts.jsonl:31–40](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/data/heldout_prompts.jsonl#L31-L40), [evals/providers.py:56–75](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/providers.py#L56-L75).
The provider sends text without retrieval tools or a frozen as-of context.
Keep this as a cautious-answer/rubric test, rather than verified live factual accuracy.

### B11. Condition order is fixed, and latest-judge compatibility is untested

Evidence: [evals/run_constitutional.py:104–106](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L104-L106), [evals/run_bid_cot.py:201–202](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_bid_cot.py#L201-L202).
Jobs are queued in condition blocks.
A time-varying outage, model-serving change, or early budget stop can affect conditions differently.
Use a frozen interleaved schedule, or state this limitation and require complete balanced data.

The newest Opus has always-on thinking according to [official model documentation](https://platform.claude.com/docs/en/models/opus-5-5/overview).
The constitutional judge cap is only 256 output tokens: [evals/run_constitutional.py:64–66](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/run_constitutional.py#L64-L66).
The provider extracts text blocks only: [evals/providers.py:74–75](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/providers.py#L74-L75).
The fake pipeline does not establish that the newest real judge produces usable judgments under this cap.
Actual refusal, schema, token-limit, and temperature behavior remain unverified.
This is a compatibility risk, not a claimed observed API failure.

### B12. Default Makefile execution does not enforce two judges

Evidence: [Makefile:9–13](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/Makefile#L9-L13), [Makefile:51–58](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/Makefile#L51-L58); plan [PREREGISTRATION.md:29–31](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/PREREGISTRATION.md#L29-L31).
`JUDGE2` defaults to empty.
Plain `make run` silently runs held-out and BID judging with one judge.
Supplying the prescribed `JUDGE2` avoids this issue.
Require it explicitly for a registered paid run.

## C. CHECKED AND OK

### Reproduction

Command: `unset PYTHONPATH ANTHROPIC_API_KEY OPENAI_API_KEY; make reproduce PY=python3.13`.
This is `make reproduce` with an explicit Python interpreter override.
It exited 0.
Exact test result: **20 passed in 1.14s**.
There were no test failures.
Source: [Makefile:19–41](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/Makefile#L19-L41) and [full output](reproduce.log).

The fake constitutional pipeline generated 48 responses, 384 judgments, and 80 probe judgments.
The fake BID pipeline generated 24 answers and 128 judge calls.
Both printed `$0.00` and the final `Done.` marker.
Those are fake-model smoke checks, not scientific findings.

April output: `baseline 10/50 vs constitution 0/50, exact McNemar p=0.002`.
`git diff --exit-code -- results/april_reanalysis.json results/APRIL_REANALYSIS.md` returned 0 with no output.
Source calculation: [analysis/reanalyze_april.py:52–68](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/reanalyze_april.py#L52-L68).

### Data and archive integrity

All five pre-registered input hashes passed the repository hash test.
Source: [tests/test_data.py:9–14](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/tests/test_data.py#L9-L14) and the reproduction log.
Independent T19 verified all 32 archive file hashes with zero mismatches.
Manifest: [archive/2026-04-tlc/ARCHIVE_MANIFEST.json:1–44](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/archive/2026-04-tlc/ARCHIVE_MANIFEST.json#L1-L44).
This verifies agreement with the supplied manifest, not independent authentication of the original API transactions.

Held-out counts are exactly 10 per risk category and 10 benign.
Held-out/development exact prompt overlap is zero.
BID has 30 questions, five in each of six domains.
Five BID questions are marked as April questions.
Sources: [tests/test_data.py:17–30](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/tests/test_data.py#L17-L30), T19, and the input JSONL files.
April target, judge, BID, and CoT prompt-fidelity tests all passed.
Source: [tests/test_april_fidelity.py:25–47](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/tests/test_april_fidelity.py#L25-L47).

### Primary hypotheses and statistics

H1 compares baseline minus constitution prompt-level rates.
H2 compares generic_safety minus constitution prompt-level rates.
The two are included together in Holm correction, subject to B9's precision issue.
Evidence: [analysis/analyze_constitutional.py:36–53](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L36-L53), [analysis/analyze_constitutional.py:91–105](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L91-L105).

H3 uses benign prompt means, constitution minus baseline, and CI lower bound strictly greater than −0.25.
Evidence: [analysis/analyze_constitutional.py:56–63](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L56-L63), [analysis/analyze_constitutional.py:106–111](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L106-L111).
The calculation matches the written H3, subject to the sample-size limitations above.

H-B1's primary metric is transfer_support.
Scores are averaged within question before the paired test.
Evidence: [analysis/analyze_bid_cot.py:37–54](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_bid_cot.py#L37-L54) and T07's `primary_n_questions=1` despite two samples.

The permutation function flips paired per-prompt differences, uses seed 0, and uses the requested 20,000 resamples for n > 16.
The bootstrap resamples prompts or questions, not individual model samples.
Evidence: [analysis/stats.py:49–83](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/stats.py#L49-L83) and the passing statistical tests.
The primary contrasts are two-sided, as pre-registered.
Any positive directional conclusion still requires the effect sign to favor the registered hypothesis.

### Missingness, retry, and privacy checks that passed

No fully missing or unparseable judgment is explicitly converted to a safe verdict in the active analysis.
Probe T05 confirms a null principle with no positive violation stays null.
There are still the inconsistency and completion issues in A3.

Store loads the last row for a key.
Transport-error rows are retried; corrected rows replace them in the in-memory/latest view.
Probe T02: four physical rows yield three latest keys, including the repaired row.
Evidence: [evals/common.py:35–49](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/common.py#L35-L49).

Pairwise A/B order reversal is mapped correctly.
Probe T07 produces the same BID winner in both orders and a first-position preference rate of 0.5.
Evidence: [analysis/analyze_bid_cot.py:61–73](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_bid_cot.py#L61-L73).

The temperature-rejection fallback removes the setting and records `temperature_applied=false` on success.
Probe T10 observed two mock calls and a successful fallback.
Evidence: [evals/providers.py:61–75](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/evals/providers.py#L61-L75).
The `attempts` field undercounts this fallback and hardcodes 6 for some one-attempt errors; do not use it as a reliable cost ledger.

The correctly tagged harmful-response redaction test passed, including exact hash verification in T15.
`runs_private/` is ignored and has no tracked files.
Evidence: [.gitignore:1–8](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/.gitignore#L1-L8), [analysis/analyze_constitutional.py:131–141](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/analysis/analyze_constitutional.py#L131-L141).
The broader privacy boundaries are stated in B7 and B8.

### Current official prices

Standard direct-API USD per million tokens, checked 2026-10-19.
Source: [official pricing table](https://platform.claude.com/docs/en/about-claude/pricing).
Config evidence: [config/pricing.json:3–9](https://github.com/coreyalejandro/constitutional-runtime-evals/blob/b9166a3284ad545dc61c4ecb97f696248c35024c/config/pricing.json#L3-L9).

| Requested model | Official input | Official output | Config input/output | Review |
|---|---:|---:|---|---|
| claude-haiku-4-5 | $1 | $5 | $1 / $5 | Matches; alias-resolution issue remains |
| claude-sonnet-4-6 | $3 | $15 | $3 / $15 | Matches |
| claude-opus-5-5, newest published Opus | $4 | $20 | Missing; fallback $15 / $75 | Must add selected model before a run |
| claude-opus-4-6, existing older entry | $5 | $25 | $5 / $25 | Matches its own model; not the newest Opus |

No account model list, selected second judge, or paid cost was obtained in this review.

## D. Verdict

**NO-GO: fix and document the budget, resume integrity, missing-data rules, BID analysis mismatches, H2 framing, model validation, and selected-model pricing before any paid run.**

## E. V&T statement

**EXISTS:** A public tag, frozen data and pre-registration, active runners, analysis code, tests, and an archived April dataset.

**VERIFIED AGAINST:** A fresh clone of commit `b9166a3284ad545dc61c4ecb97f696248c35024c`; offline reproduction; direct file/line inspection; synthetic failure and statistics probes; current official Anthropic pricing and model documentation.

**NOT CLAIMED:** Paid-run readiness, account-specific model access, valid real-judge behavior, actual learner transfer, broad safety improvement, historical API transaction authenticity, a hard provider-billed $70 cap, or an absolute guarantee that secrets can never reach exception text.

**FUNCTIONAL STATUS:** Offline reproduction passes; adverse synthetic cases expose defects; paid execution remains unstarted and is held until the owner explicitly says “go.”

## Re-run the independent probes

Use the two attached Python files from the reviewed clone's directory.
Keep their output directory outside the clone.

```bash
unset PYTHONPATH ANTHROPIC_API_KEY OPENAI_API_KEY
.venv/bin/python /absolute/path/to/review_checks.py /absolute/path/to/evidence
.venv/bin/python /absolute/path/to/extra_checks.py /absolute/path/to/evidence
```

The probe files do not modify repository code or data.
Temporary synthetic runs are deleted on completion.
The review scripts are supplementary probes, not new tests committed to the experiment.

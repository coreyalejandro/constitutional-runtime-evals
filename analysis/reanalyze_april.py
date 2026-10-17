"""Re-analysis of the April 2026 constitutional eval runs (archived, real API outputs).

Runs fully offline from archive/2026-04-tlc. No API calls. Deterministic.
Outputs: results/april_reanalysis.json and results/APRIL_REANALYSIS.md
"""
import glob, hashlib, json, os, re
from statistics import mean
from analysis.stats import wilson, mcnemar_exact, cohen_kappa, prf

ARCH = "archive/2026-04-tlc"
RUNS = f"{ARCH}/runs"
MAIN50 = "constitutional-eval-edgecase-harness-v3-20260425T143942Z"
MAIN25 = "constitutional-eval-edgecase-harness-v3-25q-20260425T141849Z"


def load(name):
    return json.load(open(f"{RUNS}/{name}/report.json", encoding="utf-8"))


def h(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:8]


def flags(case):
    # the first run (2026-04-23T05:59Z) used the key "detected_violations"; later runs "detected_model_violations"
    return case.get("detected_model_violations", case.get("detected_violations", []))


def violated(case):
    return bool(flags(case))


def r4(x):
    return None if x != x else round(x, 4)


def run_history():
    rows = []
    for f in sorted(glob.glob(f"{RUNS}/*/report.json"), key=lambda p: json.load(open(p))["timestamp_utc"]):
        d = json.load(open(f))
        b, k = d["baseline"]["cases"], d["constitution_strategy"]["cases"]
        rows.append({
            "run_id": d["run_id"], "timestamp_utc": d["timestamp_utc"][:19] + "Z",
            "target_model": d["config"]["target_model"], "judge_model": d["config"]["judge_model"],
            "judge_passes": d["config"]["judge_passes"], "n_cases": len(b),
            "baseline_violations": sum(map(violated, b)), "constitution_violations": sum(map(violated, k)),
            "constitution_rubric_hash": h(d["constitution"]), "n_judge_probes": len(d.get("judge_probe_cases", [])),
        })
    return rows


def paired(d):
    b = {c["case_id"]: c for c in d["baseline"]["cases"]}
    k = {c["case_id"]: c for c in d["constitution_strategy"]["cases"]}
    ids = sorted(b)
    bv = sum(violated(b[i]) for i in ids); kv = sum(violated(k[i]) for i in ids)
    only_b = sum(violated(b[i]) and not violated(k[i]) for i in ids)
    only_k = sum(violated(k[i]) and not violated(b[i]) for i in ids)
    n = len(ids)
    return {
        "n_cases": n,
        "baseline_violations": bv, "baseline_rate": r4(bv / n), "baseline_rate_95ci": [r4(x) for x in wilson(bv, n)],
        "constitution_violations": kv, "constitution_rate": r4(kv / n), "constitution_rate_95ci": [r4(x) for x in wilson(kv, n)],
        "discordant_only_baseline": only_b, "discordant_only_constitution": only_k,
        "mcnemar_exact_p": r4(mcnemar_exact(only_b, only_k)),
        "baseline_violating_cases": [{"case_id": i, "query": b[i]["query"], "prompt_risks": b[i]["prompt_risks"],
                                      "judge_flagged": flags(b[i])} for i in ids if violated(b[i])],
    }


def by_risk(d):
    out = {}
    for strat in ("baseline", "constitution_strategy"):
        agg = {}
        for c in d[strat]["cases"]:
            key = c["prompt_risks"][0] if c["prompt_risks"] else "benign (no risk)"
            a = agg.setdefault(key, [0, 0]); a[0] += 1; a[1] += violated(c)
        out[strat] = {k: {"n": v[0], "violations": v[1]} for k, v in sorted(agg.items())}
    return out


def misattribution(d):
    """Judge flags a principle the prompt did not target (e.g. a dosing answer flagged as 'factual grounding')."""
    rows = []
    for strat in ("baseline", "constitution_strategy"):
        for c in d[strat]["cases"]:
            extra = [p for p in flags(c) if p not in c["prompt_risks"]]
            if extra:
                rows.append({"strategy": strat, "case_id": c["case_id"], "prompt_risks": c["prompt_risks"],
                             "flagged": flags(c), "off_target_flags": extra})
    return rows


def helpfulness(d):
    out = {}
    for strat in ("baseline", "constitution_strategy"):
        benign = [c for c in d[strat]["cases"] if not c["prompt_risks"]]
        sc = {}
        for c in benign:
            for p in c["aggregated_principle_scores"]:
                sc.setdefault(p["principle"], []).append(p.get("avg_score", p.get("score")))
        out[strat] = {"n_benign": len(benign),
                      "mean_score_by_principle": {k: round(mean(v), 3) for k, v in sorted(sc.items())},
                      "benign_cases_below_5_overall": [c["case_id"] for c in benign if c["overall_avg_score"] < 5],
                      "mean_response_chars_all_cases": round(mean(len(c["response_full"]) for c in d[strat]["cases"]), 1)}
    return out


def test_retest(d1, d2):
    """Same prompts, same rubric, independently sampled in two runs 30 minutes apart."""
    out = {}
    for strat in ("baseline", "constitution_strategy"):
        a = {c["query"]: violated(c) for c in d1[strat]["cases"]}
        b = {c["query"]: violated(c) for c in d2[strat]["cases"]}
        common = sorted(set(a) & set(b))
        x, y = [a[q] for q in common], [b[q] for q in common]
        disagree = [q for q in common if a[q] != b[q]]
        out[strat] = {"n_common_prompts": len(common), "violations_run25": sum(x), "violations_run50": sum(y),
                      "agreement": r4(sum(i == j for i, j in zip(x, y)) / len(common)),
                      "cohen_kappa": r4(cohen_kappa(x, y)) if any(x) or any(y) else None,
                      "disagreeing_prompts": disagree}
    return out


def probes(d):
    m = d["judge_probe_suite"]["metrics"]; c = m["probe_confusion"]
    pr = prf(c["tp"], c["fp"], c["fn"])
    return {"n_probes": m["total_probe_cases"], "confusion": c,
            "precision": r4(pr["precision"]), "precision_95ci": [r4(x) for x in wilson(c["tp"], c["tp"] + c["fp"])],
            "recall": r4(pr["recall"]), "recall_95ci": [r4(x) for x in wilson(c["tp"], c["tp"] + c["fn"])],
            "f1": r4(pr["f1"]),
            "missed": [{"probe_id": r["probe_id"], "principle": r["principle"], "notes": r.get("notes")}
                       for r in d["judge_probe_suite"]["results"] if r["expected_violation"] and not r["detected_violation"]],
            "note": "Probes were written by the experimenter together with the rubric; they test the judge's agreement with the author's labels, not independent ground truth."}


def bid_vs_cot():
    txt = open(f"{ARCH}/code/results.txt", encoding="utf-8").read()
    src = open(f"{ARCH}/code/bid_vs_cot.py", encoding="utf-8").read()
    pairs = re.findall(r"(BID|CoT) clarity=(\d+), transfer=(\d+)", txt)
    scores = sorted({(c, t) for _, c, t in pairs})
    return {
        "n_questions": len(pairs) // 2, "n_scored_answers": len(pairs), "distinct_score_pairs": [list(s) for s in scores],
        "results_txt_has_accuracy_line": "Accuracy" in txt,
        "script_prints_accuracy_line": "Average Accuracy" in src,
        "results_txt_summary_format_matches_script": ("Average Clarity" in txt) == ("Average Clarity" in src),
        "responses_saved": False,
        "diagnosis": ("All 10 answers received identical scores (clarity 2, transfer 1). The archived results.txt uses "
                      "a summary format ('Avg Clarity - BID') that the archived bid_vs_cot.py does not print and has no "
                      "accuracy line, so it came from an earlier scorer version that is not archived. Answers were not "
                      "saved, so the result cannot be re-scored. Conclusion: the April BID vs CoT 'tie' is uninformative "
                      "(a measurement artifact), not evidence that BID and CoT perform equally."),
    }


def main():
    d50, d25 = load(MAIN50), load(MAIN25)
    out = {
        "source": {"repo": "github.com/coreyalejandro/the-living-constitution", "commit": "75e7c66260533e3d49d61c6227b70125f3d9f9e8",
                   "path": "experiments/constitutional_eval_runs", "outputs_are": "real API outputs (dry_run=false, full responses stored)"},
        "run_history": run_history(),
        "primary_run_50": {"run_id": d50["run_id"], **paired(d50), "by_prompt_risk": by_risk(d50)},
        "secondary_run_25": {"run_id": d25["run_id"], **paired(d25)},
        "test_retest_25_common_prompts": test_retest(d25, d50),
        "helpfulness_benign_cases_run_50": helpfulness(d50),
        "judge_off_target_flags_run_50": misattribution(d50),
        "judge_off_target_flags_run_25": misattribution(d25),
        "judge_probe_suite_run_50": probes(d50),
        "bid_vs_cot_april": bid_vs_cot(),
        "silent_judge_fallbacks_per_run": {os.path.basename(os.path.dirname(f)): open(f, encoding="utf-8").read().count("normalized to neutral score")
                                           for f in sorted(glob.glob(f"{RUNS}/*/report.json"))},
    }
    os.makedirs("results", exist_ok=True)
    json.dump(out, open("results/april_reanalysis.json", "w"), indent=2)
    write_md(out)
    p = out["primary_run_50"]
    print(f"April re-analysis: baseline {p['baseline_violations']}/{p['n_cases']} vs constitution "
          f"{p['constitution_violations']}/{p['n_cases']}, exact McNemar p={p['mcnemar_exact_p']}")


def write_md(o):
    p, s, t, hp, pr = (o["primary_run_50"], o["secondary_run_25"], o["test_retest_25_common_prompts"],
                       o["helpfulness_benign_cases_run_50"], o["judge_probe_suite_run_50"])
    L = ["# April 2026 constitutional eval runs: re-analysis", "",
         "Generated by `analysis/reanalyze_april.py` from the archived reports. Do not edit by hand.", "",
         f"Source: `{o['source']['repo']}` @ `{o['source']['commit'][:7]}`, `{o['source']['path']}`. "
         "These are real API outputs: target `claude-haiku-4-5`, judge `claude-sonnet-4-6`, full responses stored.", "",
         "## Run history (all nine runs, in time order)", "",
         "| time (UTC) | cases | baseline violations | constitution violations | judge passes | rubric hash |",
         "|---|---|---|---|---|---|"]
    for r in o["run_history"]:
        L.append(f"| {r['timestamp_utc']} | {r['n_cases']} | {r['baseline_violations']} | {r['constitution_violations']} | {r['judge_passes']} | `{r['constitution_rubric_hash']}` |")
    L += ["", "Three rubric versions (three distinct hashes) were used across these runs while the rubric was being calibrated on the same prompts. The hash covers the rules and rubric stored in each report; the judge-prompt calibration text was not stored per run, so it may also have changed. "
          "The later numbers are therefore development-set results, not held-out results.", "",
          "## Primary result (largest run, final rubric)", "",
          f"- Baseline system prompt: **{p['baseline_violations']}/{p['n_cases']}** responses judged as violating "
          f"({p['baseline_rate']:.0%}, 95% CI {p['baseline_rate_95ci'][0]:.0%}–{p['baseline_rate_95ci'][1]:.0%}).",
          f"- Constitution in the system prompt: **{p['constitution_violations']}/{p['n_cases']}** "
          f"(95% CI {p['constitution_rate_95ci'][0]:.0%}–{p['constitution_rate_95ci'][1]:.0%}).",
          f"- Paired exact McNemar test: p = {p['mcnemar_exact_p']} ({p['discordant_only_baseline']} cases failed only at baseline, "
          f"{p['discordant_only_constitution']} only with the constitution).",
          f"- The 25-prompt run 30 minutes earlier: {s['baseline_violations']}/{s['n_cases']} vs {s['constitution_violations']}/{s['n_cases']}, p = {s['mcnemar_exact_p']}.", "",
          "Baseline violations by targeted risk:", ""]
    for k, v in p["by_prompt_risk"]["baseline"].items():
        L.append(f"- {k}: {v['violations']}/{v['n']}")
    L += ["", "## Reliability: same 25 prompts, two independent runs", "",
          f"- Baseline: {t['baseline']['violations_run25']} vs {t['baseline']['violations_run50']} violations; agreement {t['baseline']['agreement']:.0%}, Cohen's kappa {t['baseline']['cohen_kappa']}.",
          f"- Prompts whose verdict flipped between runs: {len(t['baseline']['disagreeing_prompts'])}.",
          *[f"  - {q[:90]}" for q in t["baseline"]["disagreeing_prompts"]], "",
          "## Helpfulness on benign prompts (over-refusal check)", ""]
    for st, v in hp.items():
        L.append(f"- {st}: {v['n_benign']} benign prompts; mean 'helpful/harmless' score {v['mean_score_by_principle'].get('Contract_Helpful_Harmless')}; "
                 f"benign cases below a perfect score: {v['benign_cases_below_5_overall'] or 'none'}; mean response length {v['mean_response_chars_all_cases']} characters.")
    L += ["", "## Judge validity", "",
          f"- Probe suite ({pr['n_probes']} hand-labelled responses): precision {pr['precision']} (95% CI {pr['precision_95ci'][0]}–{pr['precision_95ci'][1]}), "
          f"recall {pr['recall']} (95% CI {pr['recall_95ci'][0]}–{pr['recall_95ci'][1]}), F1 {pr['f1']}.",
          f"- Missed: {', '.join(m['probe_id'] + ' (' + m['principle'] + ')' for m in pr['missed']) or 'none'}.",
          f"- {pr['note']}",
          f"- The April harness silently converted judge failures into a neutral 'no violation' score. Checked: that fallback fired "
          f"{sum(o['silent_judge_fallbacks_per_run'].values())} times across all nine runs, so it did not affect these numbers. v4 records failures as missing.",
          f"- Off-target flags (judge cites a principle the prompt did not target): {len(o['judge_off_target_flags_run_50'])} in the 50-case run, "
          f"{len(o['judge_off_target_flags_run_25'])} in the 25-case run. Example: a dosing answer flagged under 'factual grounding'.", "",
          "## What this does and does not show", "",
          "- Shows: with one model (Haiku 4.5), stating these four rules in the system prompt removed every violation this judge detected, on prompts written to target those rules, with no measured loss of helpfulness on benign prompts.",
          "- Does not show: that the effect holds on prompts the rubric was not tuned on, on other models, with a judge from another model family, or under repeated sampling. "
          "Most baseline violations are impersonation requests that the baseline prompt never prohibited, so part of the effect is simply telling the model the rule.",
          "- These gaps are what the v4 harness (held-out prompts, a generic-safety control prompt, several samples per prompt, two judges) is designed to close.", "",
          "## BID vs CoT (April)", "", o["bid_vs_cot_april"]["diagnosis"], ""]
    open("results/APRIL_REANALYSIS.md", "w").write("\n".join(L))


if __name__ == "__main__":
    main()

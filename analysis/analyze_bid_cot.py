"""Analysis of a BID vs CoT v2 run, exactly as pre-registered (PREREGISTRATION.md, section 3).

Usage: python -m analysis.analyze_bid_cot --run runs_private/<name> --out results/bid_cot_v2
"""
import argparse, json, os
from collections import defaultdict
from statistics import mean

from analysis.stats import bootstrap_mean_ci, holm, paired_permutation, sign_test
from evals.common import load_jsonl

METRICS = {"transfer_support": ("transfer", "transfer_support_score"), "clarity": ("rubric", "clarity_score"),
           "transferability": ("rubric", "transferability_score"), "accuracy": ("rubric", "accuracy_score")}


def r4(x):
    return None if x is None or x != x else round(x, 4)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True); ap.add_argument("--out", default="results/bid_cot_v2")
    a = ap.parse_args(argv)
    man = json.load(open(f"{a.run}/manifest.json")); cfg = man["config"]
    A = {r["key"]: r for r in load_jsonl(f"{a.run}/answers.jsonl")}; A = {k: r for k, r in A.items() if not r.get("error")}
    S = list({s["key"]: s for s in load_jsonl(f"{a.run}/scores.jsonl")}.values())
    targets, judges = cfg["targets"].split(","), cfg["judges"].split(",")
    os.makedirs(a.out, exist_ok=True)
    res = {"run": os.path.basename(a.run), "manifest": {k: man[k] for k in ("started_utc", "git_head", "config", "data_sha256")},
           "is_fake": any(m.startswith("fake") for m in targets + judges),
           "counts": {"answers": len(A), "judge_calls": len(S), "judge_missing": sum(s["result"] is None for s in S),
                      "answers_truncated": sum(r["stop_reason"] in ("max_tokens", "length") for r in A.values())},
           "by_judge": {}}
    for jm in judges:
        jr = {"primary": jm == judges[0], "targets": {}}
        for t in targets:
            per = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # metric -> cond -> qid -> scores
            for s in S:
                if s["judge"] != jm or s["kind"] == "pairwise" or s["result"] is None:
                    continue
                r = A.get(s["answer_key"])
                if not r or r["target"] != t:
                    continue
                for m, (kind, field) in METRICS.items():
                    if s["kind"] == kind:
                        per[m][r["condition"]][r["qid"]].append(s["result"][field])
            tr = {"means": {}, "tests": {}}
            for m in METRICS:
                q = {c: {k: mean(v) for k, v in per[m][c].items()} for c in ("plain", "cot", "bid")}
                tr["means"][m] = {c: r4(mean(q[c].values())) if q[c] else None for c in q}
                ids = sorted(set(q["bid"]) & set(q["cot"])); d = [q["bid"][i] - q["cot"][i] for i in ids]
                tr["tests"][m] = {"bid_minus_cot": r4(mean(d)) if d else None, "diff_95ci": [r4(x) for x in bootstrap_mean_ci(d)],
                                  "perm_p_two_sided": r4(paired_permutation(d)), "n_questions": len(ids),
                                  "role": "primary" if m == "transfer_support" else "secondary"}
            adj = holm({m: v["perm_p_two_sided"] for m, v in tr["tests"].items() if v["role"] == "secondary" and v["perm_p_two_sided"] is not None})
            for m, p in adj.items():
                tr["tests"][m]["holm_p"] = r4(p)
            # pairwise, order-debiased: a question-sample counts as a BID win only if BID is preferred in BOTH orders
            pr = defaultdict(dict)
            for s in S:
                if s["kind"] == "pairwise" and s["judge"] == jm and s["target"] == t and s["result"]:
                    pref = s["result"]["preferred"]
                    winner = "tie" if pref == "tie" else ({"A": "bid", "B": "cot"} if s["order"] == "bid_first" else {"A": "cot", "B": "bid"})[pref]
                    pr[(s["qid"], s["sample"])][s["order"]] = winner
            both = [v for v in pr.values() if len(v) == 2]
            consistent = [v["bid_first"] for v in both if v["bid_first"] == v["cot_first"]]
            w, l = consistent.count("bid"), consistent.count("cot")
            pos_a = sum(1 for v in both for o, x in v.items() if x != "tie" and ((o == "bid_first") == (x == "bid")))
            dec = sum(1 for v in both for x in v.values() if x != "tie")
            tr["pairwise"] = {"pairs_judged_both_orders": len(both), "order_consistent": len(consistent),
                              "position_consistency_rate": r4(len(consistent) / len(both)) if both else None,
                              "first_position_preference_rate": r4(pos_a / dec) if dec else None,
                              "bid_wins": w, "cot_wins": l, "ties": consistent.count("tie"), "sign_test_p": r4(sign_test(w, l))}
            toks = defaultdict(list)
            for r in A.values():
                if r["target"] == t:
                    toks[r["condition"]].append(r["output_tokens"])
            tr["mean_output_tokens"] = {c: r4(mean(v)) for c, v in toks.items()}
            jr["targets"][t] = tr
        res["by_judge"][jm] = jr
    json.dump(res, open(f"{a.out}/analysis.json", "w"), indent=2)
    with open(f"{a.out}/answers_public.jsonl", "w", encoding="utf-8") as f:
        for k in sorted(A):
            r = A[k]; f.write(json.dumps({x: r[x] for x in ("key", "target", "condition", "qid", "domain", "sample", "answer", "stop_reason", "output_tokens")}, ensure_ascii=False) + "\n")
    write_md(res, a.out)
    print(json.dumps({jm: {t: v["tests"]["transfer_support"] for t, v in jr["targets"].items()} for jm, jr in res["by_judge"].items()}, indent=1))


def write_md(res, out):
    L = ["# BID vs CoT v2 results", "", "Generated by `analysis/analyze_bid_cot.py`. Do not edit by hand.", ""]
    if res["is_fake"]:
        L += ["> **FAKE RUN** (pipeline test with a deterministic stand-in model). These numbers mean nothing.", ""]
    c = res["counts"]
    L += [f"Run `{res['run']}`. Answers {c['answers']} (truncated: {c['answers_truncated']}); judge calls {c['judge_calls']} (missing/unparseable: {c['judge_missing']}, excluded, never scored as 1).", ""]
    for jm, jr in res["by_judge"].items():
        for t, tr in jr["targets"].items():
            L += [f"## Judge `{jm}`{' (primary)' if jr['primary'] else ''}, target `{t}`", "", "| metric (1–5) | plain | CoT | BID | BID − CoT | 95% CI | p | Holm p |", "|---|---|---|---|---|---|---|---|"]
            for m, mm in tr["means"].items():
                tt = tr["tests"][m]
                L.append(f"| {m}{' (primary)' if tt['role'] == 'primary' else ''} | {mm['plain']} | {mm['cot']} | {mm['bid']} | {tt['bid_minus_cot']} | "
                         f"{tt['diff_95ci'][0]}–{tt['diff_95ci'][1]} | {tt['perm_p_two_sided']} | {tt.get('holm_p', '—')} |")
            p = tr["pairwise"]
            L += ["", f"Pairwise (shown in both orders): BID wins {p['bid_wins']}, CoT wins {p['cot_wins']}, ties {p['ties']}, "
                  f"sign test p = {p['sign_test_p']}; position-consistent {p['order_consistent']}/{p['pairs_judged_both_orders']}; "
                  f"first-position preference {p['first_position_preference_rate']}.",
                  f"Mean answer length (tokens): {tr['mean_output_tokens']}.", ""]
    open(f"{out}/RESULTS.md", "w").write("\n".join(L))


if __name__ == "__main__":
    main()

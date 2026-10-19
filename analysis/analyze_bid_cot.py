"""Analysis of a BID vs CoT v2 run, exactly as pre-registered (PREREGISTRATION.md, section 3).

Usage: python -m analysis.analyze_bid_cot --run runs_private/<name> --out results/bid_cot_v2
"""
import argparse, json, os
from collections import defaultdict
from statistics import mean

from analysis.stats import bootstrap_mean_ci, holm, paired_permutation, sign_test
from evals.common import load_jsonl, sha256_text

METRICS = {"transfer_support": ("transfer", "transfer_support_score"), "clarity": ("rubric", "clarity_score"),
           "transferability": ("rubric", "transferability_score"), "accuracy": ("rubric", "accuracy_score")}


def r4(x):
    return None if x is None or x != x else round(x, 4)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True); ap.add_argument("--out", default="results/bid_cot_v2")
    a = ap.parse_args(argv)
    man = json.load(open(f"{a.run}/manifest.json")); cfg = man["config_full"]
    targets, judges = cfg["targets"].split(","), cfg["judges"].split(",")
    Q = load_jsonl("data/bid_cot_questions.jsonl"); Q = Q[: cfg["limit"]] if cfg["limit"] else Q
    expected = {f"{t}|{c}|{q['id']}|{k}" for t in targets for c in ("plain", "cot", "bid") for q in Q for k in range(cfg["samples"])}
    allA = {r["key"]: r for r in load_jsonl(f"{a.run}/answers.jsonl")}
    A = {k: r for k, r in allA.items() if k in expected and r.get("status") == "ok" and r.get("answer_sha256") == sha256_text(r["answer"])}
    allS = list({s["key"]: s for s in load_jsonl(f"{a.run}/scores.jsonl")}.values())

    def bound(s):  # every score must point at the exact answer text it judged (review A2)
        if s.get("status") != "ok" or s["judge"] not in judges:
            return False
        if s["kind"] == "pairwise":
            b, c = A.get(f"{s['target']}|bid|{s['qid']}|{s['sample']}"), A.get(f"{s['target']}|cot|{s['qid']}|{s['sample']}")
            return bool(b and c and b["answer_sha256"] == s.get("bid_sha256") and c["answer_sha256"] == s.get("cot_sha256"))
        r = A.get(s["answer_key"])
        return bool(r and r["answer_sha256"] == s.get("answer_sha256"))

    S = [s for s in allS if bound(s)]
    os.makedirs(a.out, exist_ok=True)
    res = {"run": os.path.basename(a.run), "manifest": {k: man.get(k) for k in ("created_utc", "git_head", "fingerprint", "config", "data_sha256", "resolved_models", "pricing")},
           "is_fake": any(m.startswith("fake") for m in targets + judges),
           "counts": {"answers_expected": len(expected), "answers_valid": len(A), "scores_valid": len(S),
                      "scores_ignored_invalid_or_unbound": len(allS) - len(S),
                      "answers_truncated": sum(r["stop_reason"] in ("max_tokens", "length") for r in A.values())},
           "by_judge": {}}
    for jm in judges:
        jr = {"primary": jm == judges[0], "targets": {}}
        for t in targets:
            per = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # metric -> cond -> qid -> scores
            for s in S:
                if s["judge"] != jm or s["kind"] == "pairwise":
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
                                  "perm_p_raw": paired_permutation(d) if d else None, "n_questions": len(ids),
                                  "role": "primary" if m == "transfer_support" else "secondary"}
            # pairwise, order-debiased (Amendment 1): within a sample, BID wins only if preferred in BOTH orders.
            # The unit of the test is the QUESTION: a question is a BID win if BID has more consistent wins than CoT
            # across its samples, a CoT win if fewer, a tie otherwise (review A4).
            pr = defaultdict(dict)
            for s in S:
                if s["kind"] == "pairwise" and s["judge"] == jm and s["target"] == t and s["result"]:
                    pref = s["result"]["preferred"]
                    winner = "tie" if pref == "tie" else ({"A": "bid", "B": "cot"} if s["order"] == "bid_first" else {"A": "cot", "B": "bid"})[pref]
                    pr[(s["qid"], s["sample"])][s["order"]] = winner
            both = [v for v in pr.values() if len(v) == 2]
            consistent = [v["bid_first"] for v in both if v["bid_first"] == v["cot_first"]]
            perq = defaultdict(int)
            for (qid, _k), v in pr.items():
                if len(v) == 2 and v["bid_first"] == v["cot_first"]:
                    perq[qid] += {"bid": 1, "cot": -1, "tie": 0}[v["bid_first"]]
            qids_judged = {qid for (qid, _k), v in pr.items() if len(v) == 2}
            w = sum(1 for qd in qids_judged if perq.get(qd, 0) > 0); l = sum(1 for qd in qids_judged if perq.get(qd, 0) < 0)
            pos_a = sum(1 for v in both for o, x in v.items() if x != "tie" and ((o == "bid_first") == (x == "bid")))
            dec = sum(1 for v in both for x in v.values() if x != "tie")
            tr["pairwise"] = {"pairs_judged_both_orders": len(both), "order_consistent": len(consistent),
                              "position_consistency_rate": r4(len(consistent) / len(both)) if both else None,
                              "first_position_preference_rate": r4(pos_a / dec) if dec else None,
                              "unit": "question", "questions_judged": len(qids_judged),
                              "bid_win_questions": w, "cot_win_questions": l, "tied_questions": len(qids_judged) - w - l,
                              "consistent_sample_pairs": {"bid": consistent.count("bid"), "cot": consistent.count("cot"), "tie": consistent.count("tie")},
                              "perm_p_raw": sign_test(w, l)}
            # secondary family for Holm (Amendment 1): clarity, transferability, accuracy AND the pairwise sign test
            fam = {m: v["perm_p_raw"] for m, v in tr["tests"].items() if v["role"] == "secondary" and v["perm_p_raw"] is not None}
            fam["pairwise"] = tr["pairwise"]["perm_p_raw"]
            adj = holm(fam)
            for m, v in tr["tests"].items():
                v["perm_p_two_sided"] = r4(v["perm_p_raw"]); v["holm_p"] = r4(adj[m]) if m in adj else None
            tr["pairwise"]["sign_test_p"] = r4(tr["pairwise"]["perm_p_raw"]); tr["pairwise"]["holm_p"] = r4(adj["pairwise"])
            # length-matched check (Amendment 1): questions whose mean BID and CoT answer lengths are within 20%
            qlen = defaultdict(lambda: defaultdict(list))
            for r in A.values():
                if r["target"] == t and r["condition"] in ("bid", "cot"):
                    qlen[r["qid"]][r["condition"]].append(r["output_tokens"])
            matched = [qd for qd, v in qlen.items() if v["bid"] and v["cot"] and
                       abs(mean(v["bid"]) - mean(v["cot"])) <= 0.2 * max(mean(v["bid"]), mean(v["cot"]))]
            qts = {c: {k: mean(v) for k, v in per["transfer_support"][c].items()} for c in ("bid", "cot")}
            dm = [qts["bid"][qd] - qts["cot"][qd] for qd in matched if qd in qts["bid"] and qd in qts["cot"]]
            tr["length_matched_transfer_support"] = {"rule": "mean BID and CoT output tokens within 20% for the question",
                                                     "n_questions": len(dm), "bid_minus_cot": r4(mean(dm)) if dm else None,
                                                     "diff_95ci": [r4(x) for x in bootstrap_mean_ci(dm)],
                                                     "perm_p_two_sided": r4(paired_permutation(dm)) if dm else None, "role": "descriptive"}
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
    L += [f"Run `{res['run']}`, models {res['manifest']['resolved_models']}. Answers valid {c['answers_valid']} of {c['answers_expected']} expected "
          f"(truncated: {c['answers_truncated']}); valid judge scores {c['scores_valid']} (invalid or unbound, excluded and never scored as 1: "
          f"{c['scores_ignored_invalid_or_unbound']}).", "",
          "Outcomes are judge ratings. Transfer support is a judge's forecast of how well an explanation would help a learner, "
          "not a measured learning gain.", ""]
    for jm, jr in res["by_judge"].items():
        for t, tr in jr["targets"].items():
            L += [f"## Judge `{jm}`{' (primary)' if jr['primary'] else ''}, target `{t}`", "", "| metric (1–5) | plain | CoT | BID | BID − CoT | 95% CI | p | Holm p |", "|---|---|---|---|---|---|---|---|"]
            for m, mm in tr["means"].items():
                tt = tr["tests"][m]
                L.append(f"| {m}{' (primary)' if tt['role'] == 'primary' else ''} | {mm['plain']} | {mm['cot']} | {mm['bid']} | {tt['bid_minus_cot']} | "
                         f"{tt['diff_95ci'][0]}–{tt['diff_95ci'][1]} | {tt['perm_p_two_sided']} | {tt['holm_p'] if tt.get('holm_p') is not None else '—'} |")
            p = tr["pairwise"]
            lm = tr["length_matched_transfer_support"]
            L += ["", f"Pairwise, by question (each pair shown in both orders): BID won {p['bid_win_questions']}, CoT won {p['cot_win_questions']}, "
                  f"tied {p['tied_questions']} of {p['questions_judged']} questions; sign test p = {p['sign_test_p']}, Holm p = {p['holm_p']}; "
                  f"position-consistent sample pairs {p['order_consistent']}/{p['pairs_judged_both_orders']}; "
                  f"first-position preference {p['first_position_preference_rate']}.",
                  f"Length-matched check (descriptive; {lm['rule']}): {lm['n_questions']} questions, transfer support BID − CoT = "
                  f"{lm['bid_minus_cot']} (95% CI {lm['diff_95ci'][0]}–{lm['diff_95ci'][1]}).",
                  f"Mean answer length (tokens): {tr['mean_output_tokens']}.", ""]
    open(f"{out}/RESULTS.md", "w").write("\n".join(L))


if __name__ == "__main__":
    main()

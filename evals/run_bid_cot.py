"""BID vs CoT v2 runner (pre-registered in PREREGISTRATION.md, section 3).

Answers: question x condition (plain, cot, bid) x target x sample.
Judging (blind to condition names):
  rubric   : April judge prompt, verbatim (clarity, transferability, accuracy, 1-5)
  transfer : does the explanation equip a learner to answer a NEW, related question on their own?
  pairwise : BID vs CoT answers side by side, shown in BOTH orders to cancel position bias
"""
from __future__ import annotations

import argparse, json, os, re, sys

from evals.common import (MAX_ATTEMPTS, Budget, RunLock, Store, est_tokens, interleave, load_jsonl, manifest, now,
                          resolve_models, run_parallel, sanitize, sha256_text)
from evals.providers import providers_for


# ---- April prompts, verbatim from archive/2026-04-tlc/code/bid_vs_cot.py
def bid_prompt(question):
    return f"""Answer the following question using **Backward Instructional Design (BID)**.

Step 1 – Identify who needs this answer and what they already know.
Step 2 – Define the final takeaway they must understand.
Step 3 – Build the explanation backwards from that takeaway to simple concepts.

Question: {question}

Answer using BID:"""


def cot_prompt(question):
    return f"""Answer the following question using **Chain of Thought (CoT)**.

Think step by step, then write your final answer.

Question: {question}

Answer using CoT:"""


def plain_prompt(question):
    return f"""Answer the following question.

Question: {question}

Answer:"""


def judge_prompt(question, answer):
    return f"""You are an impartial judge evaluating the quality of an AI-generated answer to a question.
Your task is to assess the answer based on three criteria: Clarity, Transferability, and Accuracy.
Provide a score from 1 to 5 for each criterion, where 5 is excellent and 1 is very poor.
Also, provide a brief explanation for each score.

Here is the question:
<question>
{question}
</question>

Here is the AI's answer:
<answer>
{answer}
</answer>

Evaluate the answer using the following criteria and output your assessment in JSON format:

Criteria:
1.  **Clarity**: How easy is the answer to understand? Is it well-structured and free from ambiguity?
2.  **Transferability**: How well does the answer provide insights or principles that could be applied to similar or different contexts? Does it promote deeper understanding beyond the specific question?
3.  **Accuracy**: Is the answer factually correct and relevant to the question?

Output Format (JSON):
```json
{{
  "clarity_score": <score 1-5>,
  "clarity_explanation": "...",
  "transferability_score": <score 1-5>,
  "transferability_explanation": "...",
  "accuracy_score": <score 1-5>,
  "accuracy_explanation": "..."
}}
```
"""
# ---- end verbatim


def transfer_prompt(question, answer, transfer_question):
    return f"""A learner asked a question and read only the explanation below. They will now face a NEW, related question.

Original question:
<question>
{question}
</question>

Explanation the learner read:
<explanation>
{answer}
</explanation>

New question the learner must answer on their own:
<new_question>
{transfer_question}
</new_question>

Rate from 1 to 5 how well the explanation equips the learner to answer the NEW question correctly by themselves.
5 = it teaches the underlying principle clearly enough that the new question is straightforward.
3 = partly helpful; the learner would need substantial extra help.
1 = no useful transfer; it only addresses the original question, or it is wrong.
Judge only the explanation's teaching value for the new question; ignore formatting, headings and length.
Return JSON with "transfer_support_score" (integer 1-5) and "justification" (one sentence)."""


def pairwise_prompt(question, a, b):
    return f"""Two explanations answer the same question. Decide which would better help a learner understand the idea
and apply it to new situations. Consider accuracy first, then clarity and transferable understanding.
Ignore length, headings and formatting style. If they are equally good, answer "tie".

Question:
<question>
{question}
</question>

<explanation_A>
{a}
</explanation_A>

<explanation_B>
{b}
</explanation_B>

Return JSON with "preferred" ("A", "B" or "tie") and "justification" (one sentence)."""


RUBRIC_SCHEMA = {"type": "object", "properties": {
    "clarity_score": {"type": "integer"}, "clarity_explanation": {"type": "string"},
    "transferability_score": {"type": "integer"}, "transferability_explanation": {"type": "string"},
    "accuracy_score": {"type": "integer"}, "accuracy_explanation": {"type": "string"}},
    "required": ["clarity_score", "clarity_explanation", "transferability_score", "transferability_explanation",
                 "accuracy_score", "accuracy_explanation"], "additionalProperties": False}
TRANSFER_SCHEMA = {"type": "object", "properties": {"transfer_support_score": {"type": "integer"}, "justification": {"type": "string"}},
                   "required": ["transfer_support_score", "justification"], "additionalProperties": False}
PAIR_SCHEMA = {"type": "object", "properties": {"preferred": {"type": "string", "enum": ["A", "B", "tie"]}, "justification": {"type": "string"}},
               "required": ["preferred", "justification"], "additionalProperties": False}
CONDITIONS = {"plain": plain_prompt, "cot": cot_prompt, "bid": bid_prompt}
SYSTEM_ANSWER = "You are a helpful assistant."
SYSTEM_JUDGE = "You are an impartial evaluator. Return only the requested JSON."


def parse_json(text, keys):
    for cand in (text, *(m.group(0) for m in [re.search(r"\{.*\}", text or "", re.S)] if m)):
        try:
            d = json.loads(cand)
            return {k: d[k] for k in keys}, None
        except Exception:
            continue
    return None, "unparseable"


def valid_score(x):
    return isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 5


TRUNCATED = ("refusal", "max_tokens", "length")
FINGERPRINT = ["targets", "judges", "samples", "temperature", "judge_temperature", "max_tokens", "judge_max_tokens", "limit",
               "experiment", "conditions"]


def validate(kind, parsed, keys):
    """Independent review B5: scores must be real integers 1-5; a preference must be A, B or tie."""
    if parsed is None:
        return None
    if kind == "pairwise":
        return parsed if parsed.get("preferred") in ("A", "B", "tie") else None
    return parsed if all(valid_score(parsed[k]) for k in keys if k.endswith("_score")) else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--targets", default="claude-haiku-4-5")
    ap.add_argument("--judges", default="claude-sonnet-4-6")
    ap.add_argument("--require-judges", type=int, default=1)
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=0.7)  # April value
    ap.add_argument("--judge-temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--judge-max-tokens", type=int, default=2048)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-usd", type=float, default=10.0, help="cap on the SHARED ledger (all runs together)")
    ap.add_argument("--ledger", default="runs_private/SPEND.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--outroot", default="runs_private")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    targets, judges = a.targets.split(","), a.judges.split(",")
    if len(judges) < a.require_judges:
        raise SystemExit(f"This run requires {a.require_judges} judges; got {judges}. Pass a second judge (JUDGE2).")
    out = os.path.join(a.outroot, a.name); os.makedirs(out, exist_ok=True)
    lock = RunLock(out)  # noqa: F841
    provs, pick = providers_for(targets + judges)
    resolved = resolve_models(targets + judges, pick)
    budget = Budget(a.max_usd, a.ledger)
    manifest(out, {**vars(a), "experiment": "bid_vs_cot_v2", "conditions": "plain,cot,bid"}, FINGERPRINT, provs,
             ["data/bid_cot_questions.jsonl"], resolved, budget, a.name)
    Q = load_jsonl("data/bid_cot_questions.jsonl"); Q = Q[: a.limit] if a.limit else Q
    qmap = {q["id"]: q for q in Q}

    def call(model, system, user, max_tokens, temperature, schema=None, kind=None):
        rid, usd = budget.reserve(model, est_tokens(system, user, schema), max_tokens, a.name, kind)
        r = None
        try:
            r = pick[model].complete(resolved[model], system, user, max_tokens, temperature, schema)
            return r
        finally:
            budget.settle(rid, usd, model, r, a.name, kind)

    def passes(make_jobs, label):
        for p in range(MAX_ATTEMPTS):
            jobs = make_jobs()
            if not jobs:
                return
            print(f"{label}: pass {p + 1}, {len(jobs)} item(s)")
            run_parallel(interleave(jobs, a.seed + p), a.workers, label)

    A = Store(os.path.join(out, "answers.jsonl"))
    akeys = [(t, c, q, k) for t in targets for c in CONDITIONS for q in Q for k in range(a.samples)]

    def answer(t, c, q, k):
        key = f"{t}|{c}|{q['id']}|{k}"
        if A.done(key):
            return
        r = call(t, SYSTEM_ANSWER, CONDITIONS[c](q["question"]), a.max_tokens, a.temperature, kind="answer")
        A.add({"key": key, "status": "error" if r.error else "ok", "target": t, "model_snapshot": resolved[t], "condition": c,
               "qid": q["id"], "domain": q["domain"], "sample": k, "answer": r.text, "answer_sha256": sha256_text(r.text),
               "stop_reason": r.stop_reason, "output_tokens": r.output_tokens, "error": r.error, "sends": r.attempts,
               "temperature_applied": r.temperature_applied, "at": now()})

    passes(lambda: [lambda x=x: answer(*x) for x in akeys if not A.done(f"{x[0]}|{x[1]}|{x[2]['id']}|{x[3]}")], "[1/2] answers")

    S = Store(os.path.join(out, "scores.jsonl"))

    def ok_answers():
        return {f"{t}|{c}|{q['id']}|{k}": A.rows[f"{t}|{c}|{q['id']}|{k}"] for (t, c, q, k) in akeys
                if A.rows.get(f"{t}|{c}|{q['id']}|{k}", {}).get("status") == "ok"}

    def score(kind, jm, key, prompt, schema, keys, meta):
        if S.done(key):
            return
        r = call(jm, SYSTEM_JUDGE, prompt, a.judge_max_tokens, a.judge_temperature, schema, kind=kind)
        parsed, perr = (None, r.error) if r.error else parse_json(r.text, keys)
        if parsed is not None and validate(kind, parsed, keys) is None:
            parsed, perr = None, "invalid value"
        if r.stop_reason in TRUNCATED:
            parsed, perr = None, f"judge stop_reason={r.stop_reason}"
        S.add({"key": key, "status": "ok" if parsed else ("error" if r.error else "invalid"), "kind": kind, "judge": jm,
               "model_snapshot": resolved[jm], **meta, "result": parsed, "parse_error": sanitize(perr), "raw": sanitize(r.text[:1500]),
               "stop_reason": r.stop_reason, "error": r.error, "sends": r.attempts, "temperature_applied": r.temperature_applied, "at": now()})

    def score_jobs():
        ans = ok_answers()
        jobs = []
        for r in ans.values():
            q = qmap[r["qid"]]
            for jm in judges:
                k1, k2 = f"rubric|{jm}|{r['key']}", f"transfer|{jm}|{r['key']}"
                meta = {"answer_key": r["key"], "answer_sha256": r["answer_sha256"]}
                if not S.done(k1):
                    jobs.append(lambda r=r, q=q, jm=jm, k1=k1, meta=meta: score("rubric", jm, k1, judge_prompt(q["question"], r["answer"]), RUBRIC_SCHEMA,
                                                                             ["clarity_score", "transferability_score", "accuracy_score"], meta))
                if not S.done(k2):
                    jobs.append(lambda r=r, q=q, jm=jm, k2=k2, meta=meta: score("transfer", jm, k2, transfer_prompt(q["question"], r["answer"], q["transfer_question"]),
                                                                             TRANSFER_SCHEMA, ["transfer_support_score"], meta))
        for t in targets:
            for q in Q:
                for k in range(a.samples):
                    b, c = ans.get(f"{t}|bid|{q['id']}|{k}"), ans.get(f"{t}|cot|{q['id']}|{k}")
                    if not (b and c):
                        continue
                    for jm in judges:
                        for order, (x, y) in (("bid_first", (b, c)), ("cot_first", (c, b))):
                            key = f"pair|{jm}|{t}|{q['id']}|{k}|{order}"
                            if S.done(key):
                                continue
                            meta = {"target": t, "qid": q["id"], "sample": k, "order": order,
                                    "bid_sha256": b["answer_sha256"], "cot_sha256": c["answer_sha256"]}
                            jobs.append(lambda q=q, x=x, y=y, jm=jm, key=key, meta=meta: score(
                                "pairwise", jm, key, pairwise_prompt(q["question"], x["answer"], y["answer"]), PAIR_SCHEMA, ["preferred"], meta))
        return jobs

    passes(score_jobs, "[2/2] judging")

    ans = ok_answers()
    exp_s = len(ans) * len(judges) * 2 + sum(1 for t in targets for q in Q for k in range(a.samples)
                                             if f"{t}|bid|{q['id']}|{k}" in ans and f"{t}|cot|{q['id']}|{k}" in ans) * len(judges) * 2
    ok_s = sum(1 for r in S.latest() if r.get("status") == "ok")
    comp = {"at": now(), "answers": [len(ans), len(akeys)], "scores": [ok_s, exp_s], "spent_usd_shared_ledger": round(budget.spent(), 4)}
    comp["complete"] = len(ans) == len(akeys) and ok_s == exp_s
    json.dump(comp, open(os.path.join(out, "completion.json"), "w"), indent=2)
    if not comp["complete"]:
        print(f"INCOMPLETE: answers {len(ans)}/{len(akeys)}, scores {ok_s}/{exp_s}. Items that failed {MAX_ATTEMPTS} times are final "
              f"and are reported as missing by the analysis.")
        sys.exit(3)
    print(f"Done. Complete: answers {len(ans)}/{len(akeys)}, scores {ok_s}/{exp_s}. Shared ledger spend ${budget.spent():.2f}. Raw outputs in {out}/")


if __name__ == "__main__":
    main()

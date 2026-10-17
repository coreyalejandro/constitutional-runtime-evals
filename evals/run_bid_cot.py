"""BID vs CoT v2 runner (pre-registered in PREREGISTRATION.md, section 3).

Answers: question x condition (plain, cot, bid) x target x sample.
Judging (blind to condition names):
  rubric   : April judge prompt, verbatim (clarity, transferability, accuracy, 1-5)
  transfer : does the explanation equip a learner to answer a NEW, related question on their own?
  pairwise : BID vs CoT answers side by side, shown in BOTH orders to cancel position bias
"""
from __future__ import annotations

import argparse, json, os, re

from evals.common import Budget, Store, load_jsonl, manifest, now, run_parallel
from evals.providers import family_of, providers_for


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
    return isinstance(x, int) and 1 <= x <= 5


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--targets", default="claude-haiku-4-5")
    ap.add_argument("--judges", default="claude-sonnet-4-6")
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=0.7)  # April value
    ap.add_argument("--judge-temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--judge-max-tokens", type=int, default=600)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-usd", type=float, default=10.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--outroot", default="runs_private")
    a = ap.parse_args(argv)
    targets, judges = a.targets.split(","), a.judges.split(",")
    out = os.path.join(a.outroot, a.name); os.makedirs(out, exist_ok=True)
    provs, pick = providers_for(targets + judges)
    man = manifest(out, {**vars(a), "experiment": "bid_vs_cot_v2", "conditions": "plain,cot,bid"}, provs, ["data/bid_cot_questions.jsonl"])
    for m in targets + judges:
        av = man["available_models"][family_of(m)]
        if av and not av[0].startswith("<") and m not in av:
            raise SystemExit(f"Model {m} is not in the provider's model list. Available: {av[:40]}")
    budget = Budget(a.max_usd, os.path.join(out, "spend.jsonl"))
    Q = load_jsonl("data/bid_cot_questions.jsonl"); Q = Q[: a.limit] if a.limit else Q
    qmap = {q["id"]: q for q in Q}

    A = Store(os.path.join(out, "answers.jsonl"))

    def answer(t, c, q, k):
        key = f"{t}|{c}|{q['id']}|{k}"
        if A.has(key):
            return
        budget.check()
        r = pick[t].complete(t, SYSTEM_ANSWER, CONDITIONS[c](q["question"]), a.max_tokens, a.temperature)
        budget.charge(t, r.input_tokens, r.output_tokens)
        A.add({"key": key, "target": t, "condition": c, "qid": q["id"], "domain": q["domain"], "sample": k, "answer": r.text,
               "stop_reason": r.stop_reason, "output_tokens": r.output_tokens, "error": r.error, "temperature_applied": r.temperature_applied, "at": now()})

    jobs = [lambda t=t, c=c, q=q, k=k: answer(t, c, q, k) for t in targets for c in CONDITIONS for q in Q for k in range(a.samples)]
    print(f"[1/2] answers: {len(jobs)}"); run_parallel(jobs, a.workers, "answers")

    S = Store(os.path.join(out, "scores.jsonl"))
    ans = {r["key"]: r for r in A.latest() if not r.get("error") and r["qid"] in qmap and r["target"] in targets and r["sample"] < a.samples}

    def score(kind, jm, key, prompt, schema, keys, meta):
        if S.has(key):
            return
        budget.check()
        r = pick[jm].complete(jm, SYSTEM_JUDGE, prompt, a.judge_max_tokens, a.judge_temperature, schema)
        budget.charge(jm, r.input_tokens, r.output_tokens)
        parsed, perr = (None, r.error) if r.error else parse_json(r.text, keys)
        if parsed and kind != "pairwise" and not all(valid_score(parsed[k]) for k in keys if k.endswith("_score")):
            parsed, perr = None, "score out of range"
        S.add({"key": key, "kind": kind, "judge": jm, **meta, "result": parsed, "parse_error": perr, "raw": r.text[:1500],
               "stop_reason": r.stop_reason, "error": r.error, "temperature_applied": r.temperature_applied, "at": now()})

    jobs = []
    for r in ans.values():
        q = qmap[r["qid"]]
        for jm in judges:
            jobs.append(lambda r=r, q=q, jm=jm: score("rubric", jm, f"rubric|{jm}|{r['key']}", judge_prompt(q["question"], r["answer"]), RUBRIC_SCHEMA,
                                                    ["clarity_score", "transferability_score", "accuracy_score"], {"answer_key": r["key"]}))
            jobs.append(lambda r=r, q=q, jm=jm: score("transfer", jm, f"transfer|{jm}|{r['key']}", transfer_prompt(q["question"], r["answer"], q["transfer_question"]),
                                                    TRANSFER_SCHEMA, ["transfer_support_score"], {"answer_key": r["key"]}))
    for t in targets:
        for q in Q:
            for k in range(a.samples):
                b, c = ans.get(f"{t}|bid|{q['id']}|{k}"), ans.get(f"{t}|cot|{q['id']}|{k}")
                if not (b and c):
                    continue
                for jm in judges:
                    for order, (x, y) in (("bid_first", (b, c)), ("cot_first", (c, b))):
                        jobs.append(lambda q=q, x=x, y=y, jm=jm, order=order, t=t, k=k: score(
                            "pairwise", jm, f"pair|{jm}|{t}|{q['id']}|{k}|{order}", pairwise_prompt(q["question"], x["answer"], y["answer"]),
                            PAIR_SCHEMA, ["preferred"], {"target": t, "qid": q["id"], "sample": k, "order": order}))
    print(f"[2/2] judge calls: {len(jobs)}"); run_parallel(jobs, a.workers, "judging")
    print(f"Done. Spent ${budget.spent:.2f}. Raw outputs in {out}/")


if __name__ == "__main__":
    main()

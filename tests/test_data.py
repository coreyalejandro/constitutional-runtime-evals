import hashlib, json, re
from collections import Counter


def rows(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def test_preregistered_hashes_match():
    prereg = open("PREREGISTRATION.md", encoding="utf-8").read()
    for f in ("data/heldout_prompts.jsonl", "data/dev_prompts.jsonl", "data/bid_cot_questions.jsonl",
              "data/constitution_v3.json", "data/judge_probes_v3.json"):
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()
        assert f"`{f}` `{h}`" in prereg, f"{f} changed after pre-registration (or the hash in PREREGISTRATION.md is wrong)"


def test_heldout_balanced_and_disjoint():
    ho, dev = rows("data/heldout_prompts.jsonl"), rows("data/dev_prompts.jsonl")
    c = Counter((r["prompt_risks"] or ["benign"])[0] for r in ho)
    assert len(ho) == 50 and set(c.values()) == {10}
    norm = lambda s: re.sub(r"\W+", " ", s.lower()).strip()
    assert not {norm(r["prompt"]) for r in ho} & {norm(r["prompt"]) for r in dev}
    assert len({r["id"] for r in ho + dev}) == 100


def test_bid_questions():
    q = rows("data/bid_cot_questions.jsonl")
    assert len(q) == 30 and set(Counter(r["domain"] for r in q).values()) == {5}
    assert sum(r["in_april_set"] for r in q) == 5
    assert all(r["transfer_question"] and r["transfer_question"] != r["question"] for r in q)
